'use strict';
// Cursor's Ink renderer can replay its complete transcript in one write when
// the live region is taller than the viewport. A PTY splits that write into
// many reads. DEC synchronized output keeps those intermediate screens hidden.
const BEGIN = Buffer.from('\x1b[?2026h');
const END = Buffer.from('\x1b[?2026l');
// Refresh the one-second tmux sync deadline inside very large replays. Only
// insert at ground-state character boundaries, never inside UTF-8 or ANSI strings.
function frame(data) {
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
function install(stream) {
  if (!stream.isTTY) return false;
  const original = stream.write;
  stream.write = function (chunk, encoding, callback) {
    if (!(typeof chunk === 'string' || chunk instanceof Uint8Array)) {
      return original.apply(this, arguments);
    }
    const data = typeof chunk === 'string'
      ? Buffer.from(chunk, typeof encoding === 'string' ? encoding : 'utf8')
      : Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    // Do not nest transactions owned by Cursor's existing fullscreen widgets.
    if (!data.includes(Buffer.from('\x1b[2J')) || data.at(-1)!==10
        || data.includes(BEGIN) || data.includes(END)) {
      return original.apply(this, arguments);
    }
    return original.call(this, frame(data),
      typeof encoding === 'function' ? encoding : callback);
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
