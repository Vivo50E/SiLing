'use strict';
// Cursor's Ink renderer can replay its complete transcript in one write when
// the live region is taller than the viewport. A PTY splits that write into
// many reads. DEC synchronized output keeps those intermediate screens hidden.
const BEGIN = Buffer.from('\x1b[?2026h');
const END = Buffer.from('\x1b[?2026l');
// Refresh the one-second tmux sync deadline inside very large replays. Only
// insert at ground-state character boundaries, never inside UTF-8 or ANSI strings.
function frame(data, rows = 0) {
  // tmux 3.7c's whole-screen erase is sent straight to the client even in
  // application sync mode. Ink's clear+home prefix can use equivalent line
  // erasures, which tmux collects and defers until the synchronized redraw.
  // Only translate this exact prefix: arbitrary cursor state/escape strings
  // must remain untouched. Requiring an explicit history erase also preserves
  // tmux's scroll-on-clear semantics; do not translate a plain clear+home.
  if (Number.isInteger(rows) && rows > 0 && rows <= 1000) {
    const withHistory = Buffer.from('\x1b[2J\x1b[3J\x1b[H');
    const prefix = data.subarray(0, withHistory.length).equals(withHistory) ? withHistory : null;
    if (prefix) {
      let erase = '';
      for (let row = 1; row <= rows; row++) erase += `\x1b[${row};1H\x1b[2K`;
      if (prefix === withHistory) erase += '\x1b[3J';
      data = Buffer.concat([Buffer.from(erase+'\x1b[H'), data.subarray(prefix.length)]);
    }
  }
  let state='text', previous='', start=0, lastRefresh=0;
  const pieces=[BEGIN];
  for(let i=0;i<data.length;i++) {
    const b=data[i];
    if(state==='text' && ((b>=32 && b<127) || b===10 || b===13 || (b>=194 && b<=244)) && i-lastRefresh>=65536) {
      pieces.push(data.subarray(start,i),BEGIN);start=i;lastRefresh=i;
    }
    if(state==='text') { if(b===27) state='escape'; }
    else if(state==='escape') {
      if(b===91) state='csi';
      else if([93,80,88,94,95].includes(b)) state='string';
      else if(b>=48 && b<=126) state='text';
    } else if(state==='csi') { if(b>=64 && b<=126) state='text'; }
    else if(state==='string') {
      if(b===7) state='text';
      else if(b===27) {previous=state;state='string-escape';}
    } else if(state==='string-escape') state=b===92?'text':previous;
  }
  if(state!=='text') return data; // Not a complete frame; leave it untouched.
  pieces.push(data.subarray(start),END);
  return Buffer.concat(pieces);
}
// Track controls across writes: never insert markers inside a split escape,
// UTF-8 character, or a transaction owned by Cursor itself.
function inspect(data, context) {
  const startsClean = context.state === 'text' && !context.utf8;
  let redraw = false, native = context.sync;
  for (const b of data) {
    if (context.state === 'text') {
      if (context.utf8 && b >= 128 && b < 192) { context.utf8--; continue; }
      context.utf8 = b >= 194 && b <= 223 ? 1 : b >= 224 && b <= 239 ? 2 : b >= 240 && b <= 244 ? 3 : 0;
      if (b === 27) context.state = 'escape';
    } else if (context.state === 'escape') {
      if (b === 91) { context.state = 'csi'; context.params = ''; }
      else if ([93,80,88,94,95].includes(b)) context.state = 'string';
      else if (b >= 48 && b <= 126) context.state = 'text';
    } else if (context.state === 'csi') {
      if (b >= 64 && b <= 126) {
        const command = String.fromCharCode(b);
        if ('ABCDEFGHJKSTf'.includes(command)) redraw = true;
        if (context.params.startsWith('?') && context.params.slice(1).split(';').includes('2026') && (command === 'h' || command === 'l')) {
          context.sync = command === 'h'; native = true;
        }
        context.state = 'text';
      } else if (context.params.length < 128) context.params += String.fromCharCode(b);
    } else if (context.state === 'string') {
      if (b === 7) context.state = 'text';
      else if (b === 27) context.state = 'string-escape';
    } else if (context.state === 'string-escape') {
      context.state = b === 92 ? 'text' : b === 27 ? 'string-escape' : 'string';
    }
  }
  return startsClean && context.state === 'text' && !context.utf8 && !native && redraw;
}
function install(stream) {
  if (!stream.isTTY) return false;
  const original = stream.write;
  const context = {state: 'text', params: '', utf8: 0, sync: false};
  let clearTimer = null, clearTarget = null;
  const cancelClear = () => {
    clearTimeout(clearTimer);
    clearTimer = null;
    clearTarget = null;
  };
  const finishClear = () => {
    const target = clearTarget;
    cancelClear();
    if (target) original.call(target, END);
  };
  if (stream === process.stdout) process.once('exit', finishClear);
  stream.write = function (chunk, encoding, callback) {
    if (!(typeof chunk === 'string' || chunk instanceof Uint8Array)) {
      return original.apply(this, arguments);
    }
    const data = typeof chunk === 'string'
      ? Buffer.from(chunk, typeof encoding === 'string' ? encoding : 'utf8')
      : Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    // Ink also redraws using line erasure/cursor motion, particularly during
    // working updates and shrinking a terminal. These need not end in a newline.
    const redraw = inspect(data, context);
    const controlsOnly = !data.toString('utf8').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '').trim();
    const complete = context.state === 'text' && !context.utf8;
    // Never carry our transaction into a native transaction or split control.
    if (clearTarget && (!complete || context.sync || data.includes(BEGIN) || data.includes(END))) finishClear();
    const cb = typeof encoding === 'function' ? encoding : callback;
    if (redraw && controlsOnly) {
      // Ink clears the previous layout before computing its replacement.
      // Ending sync here would deliberately publish a blank intermediate frame.
      clearTarget = this;
      if (!clearTimer) {
        clearTimer = setTimeout(finishClear, 900);
        clearTimer.unref();
      }
      const prepared = frame(data, this.rows);
      return original.call(this, prepared.subarray(0, prepared.length - END.length), cb);
    }
    if (clearTarget && complete && !controlsOnly) {
      cancelClear();
      return original.call(this, redraw ? frame(data, this.rows) : Buffer.concat([data, END]), cb);
    }
    if (!redraw) return original.apply(this, arguments);
    return original.call(this, frame(data, this.rows), cb);
  };
  return true;
}
module.exports = { install, frame };
if (process.env.SILING_CURSOR_SYNC_ONCE === '1') {
  delete process.env.SILING_CURSOR_SYNC_ONCE;
  // The hook applies to this Cursor process only, not commands it launches.
  // Restore the exact original options, even when Node resolves /tmp or
  // symlinked repository paths differently from the launcher.
  const previous = process.env.SILING_CURSOR_PREVIOUS_NODE_OPTIONS;
  delete process.env.SILING_CURSOR_PREVIOUS_NODE_OPTIONS;
  if (previous) process.env.NODE_OPTIONS = previous;
  else delete process.env.NODE_OPTIONS;
  install(process.stdout);
}
