// Exercise the injected script with cell-accurate buffers and a small DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8');
const listeners = {}, documentListeners = {}, callbacks = {}, timers = [];
function element() {
  return {
    style: {setProperty(name, value) { this[name] = value; }}, children: [],
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this[name] = value; },
    remove() {},
  };
}
const screen = Object.assign(element(), {
  addEventListener: (name, fn) => { listeners[name] = fn; },
  querySelector: () => null,
  getBoundingClientRect: () => ({left: 0, top: 0, width: 200, height: 100}),
});
const empty = () => ({getChars: () => '', getWidth: () => 1, extended: {}});
let rows = [], opened = [], reports = 0;
const buffer = {viewportY: 0, get length() { return rows.length; }, getLine: y => rows[y]};
const selection = {
  shouldForceSelection: e => !!e.altKey,
  _getMouseBufferCoords: e => e.coords,
};
const mouse = {triggerMouseEvent: () => { reports++; }};
const term = {
  cols: 20, rows: 5, buffer: {active: buffer}, options: {},
  _core: {coreMouseService: mouse, _selectionService: selection,
    _oscLinkService: {getLinkData: () => ({uri: 'https://example.test/wrapped'})}},
  onScroll: fn => { callbacks.scroll = fn; },
  onResize: fn => { callbacks.resize = fn; },
  onWriteParsed: fn => { callbacks.write = fn; },
  onRender: fn => { callbacks.render = fn; },
};
global.window = {term, frameElement: {dataset: {nativeSelection: 'true'}},
  addEventListener() {}, open: url => opened.push(url)};
window.parent = window;
global.document = {
  head: element(), documentElement: element(),
  querySelector: () => screen, createElement: element,
  addEventListener: (name, fn) => { documentListeners[name] = fn; },
};
global.setTimeout = fn => timers.push(fn);
eval(source);

window.frameElement.dataset.inlineSelection = 'true';
let preview = {}, reads = 0, copied = 'existing clipboard', alerts = [], read;
window.silingTrimSelection = async () => ({adjusted: false, preview});
window.silingReadSelection = async () => { reads++; return read(); };
window.alert = text => alerts.push(text);
global.ClipboardItem = window.ClipboardItem = class { constructor(data) { this.data = data; } };
Object.defineProperty(global, 'navigator', {value: {clipboard: {
  write: async items => { copied = await (await items[0].data['text/plain']).text(); },
}}});
const settle = () => new Promise(resolve => setImmediate(resolve));
const copy = () => documentListeners.keydown({key: 'c', metaKey: true, ctrlKey: false,
  shiftKey: false, preventDefault() {}, stopImmediatePropagation() {}});
async function drag(altKey = false) {
  listeners.mousedown({button: 0, clientX: 10, clientY: 10, detail: 1, coords: [0, 0], altKey});
  documentListeners.mousemove({buttons: 1, clientX: 30, clientY: 20});
  documentListeners.mouseup({button: 0, buttons: 0, ctrlKey: false});
  for (const callback of timers.splice(0)) callback();
  await settle();
}
(async () => {
  read = async () => { throw Error('409 Conflict: No terminal text is selected'); };
  await drag();
  copy(); await settle(); copy(); await settle();
  assert.equal(reads, 0, 'empty final preview must clear the stale copy state');
  assert.deepEqual(alerts, []);
  assert.equal(copied, 'existing clipboard');

  preview = {text: '    first\n    second', start: {x: 0, y: 0}, end: {x: 10, y: 1}, viewport: 0};
  read = async () => ({text: preview.text});
  await drag(); copy(); await settle();
  assert.equal(copied, 'first\nsecond');
  copy(); await settle();
  assert.equal(reads, 2, 'a valid selection can be copied repeatedly');

  navigator.clipboard.write = async items => {
    try { copied = await (await items[0].data['text/plain']).text(); }
    catch (_) { throw new DOMException('ClipboardItem data rejected'); }
  };
  read = async () => ({text: '', selected: false});
  copy(); await settle();
  assert.equal(copied, 'first\nsecond', 'expired selection must preserve the clipboard');
  assert.deepEqual(alerts, [], 'expired selection must not open a blocking alert');
  const expiredReads = reads;
  copy(); await settle(); assert.equal(reads, expiredReads);

  await drag();
  read = async () => { throw Error('409 Conflict: No terminal text is selected'); };
  copy(); await settle();
  assert.deepEqual(alerts, [], 'older remote nodes must get the same expiry handling');
  assert.ok(document.documentElement.children.some(child => child.role === 'status'),
    'expiry must offer a nonblocking status hint');

  await drag();
  read = async () => { throw Error('connection unavailable'); };
  copy(); await settle();
  assert.deepEqual(alerts, ['Copy failed: connection unavailable']);
  alerts = [];

  let resolveRead;
  read = () => new Promise(resolve => { resolveRead = resolve; });
  await drag(); copy(); copy(); await settle();
  const pendingReads = reads;
  await drag(true);
  resolveRead({text: 'old selection'}); await settle();
  assert.equal(copied, 'first\nsecond', 'a response from an old drag must not be copied');
  assert.deepEqual(alerts, []);
  copy(); await settle(); assert.equal(reads, pendingReads, 'Option selection must clear tmux copy state');

  await drag(); read = async () => ({text: preview.text});
  navigator.clipboard.write = async () => { throw Error('clipboard permission denied'); };
  copy(); await settle();
  assert.deepEqual(alerts, ['Copy failed: clipboard permission denied']);
  console.log('terminal copy selection behavior passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
