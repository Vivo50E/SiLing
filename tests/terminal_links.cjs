// Exercise the injected script with cell-accurate buffers and a small DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8');
const listeners = {}, documentListeners = {}, callbacks = {}, timers = [];
function element() {
  return {
    style: {}, children: [],
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
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
};
global.window = {term, frameElement: {dataset: {nativeSelection: 'true'}},
  addEventListener() {}, open: url => opened.push(url)};
window.parent = window;
global.document = {
  querySelector: () => screen, createElement: element,
  addEventListener: (name, fn) => { documentListeners[name] = fn; },
};
global.setTimeout = fn => timers.push(fn);
eval(source);

function row(chars, wrapped = false, id = 0) {
  const cells = [...chars].map(char => ({getChars: () => char, getWidth: () => 1,
    extended: id ? {urlId: id} : {}}));
  while (cells.length < term.cols) cells.push(empty());
  return {isWrapped: wrapped, getCell: col => cells[col], cells};
}
function hover(x, y) {
  listeners.mousemove({coords: [x, y], buttons: 0});
  return screen.children.find(el => el.className === 'siling-link-highlight').children;
}
function click(x, y, moved = false, altKey = false, ctrlKey = false) {
  const event = {coords: [x, y], button: 0, clientX: x * 10, clientY: y * 20, altKey, ctrlKey,
    preventDefault() {}, stopImmediatePropagation() {}};
  listeners.mousedown(event);
  mouse.triggerMouseEvent({});
  documentListeners.mouseup({...event, clientX: event.clientX + (moved ? 20 : 0)});
  mouse.triggerMouseEvent({});
  timers.splice(0).forEach(fn => fn());
}

const url = 'https://example.test/wrapped';
rows = [row(url.slice(0, 20)), row(url.slice(20) + ')', true)];
for (const [x, y] of [[2, 0], [2, 1]]) {
  const spans = hover(x, y);
  assert.equal(spans.length, 2, 'hovering either half underlines both');
  assert.equal(spans[0].style.width, '200px');
  assert.equal(spans[1].style.width, `${(url.length - 20) * 10}px`, 'Markdown closing bracket is excluded');
  click(x, y);
  assert.equal(opened.at(-1), url);
}
const count = opened.length;
click(2, 0, true);
assert.equal(opened.length, count, 'dragging a native link must select, not open');
click(2, 0, false, true);
assert.equal(opened.length, count, 'Option-click remains selection');

// tmux can re-emit different OSC ids on hard-separated physical lines.
rows = [row('first link segment', false, 1), row('second segment', false, 2), row('plain')];
for (const y of [0, 1]) {
  assert.equal(hover(2, y).length, 2);
  click(2, y);
  assert.equal(opened.at(-1), url);
}
hover(2, 0);
callbacks.scroll();
assert.equal(screen.children[0].children.length, 0);
hover(2, 0);
callbacks.resize();
assert.equal(screen.children[0].children.length, 0);
hover(2, 0);
callbacks.write();
assert.equal(screen.children[0].children.length, 0);
hover(2, 0);
listeners.mouseleave();
assert.equal(screen.children[0].children.length, 0);

// Wide and surrogate-pair characters before a literal URL must not offset it.
const prefix = row('');
prefix.cells[0] = {getChars: () => '中', getWidth: () => 2, extended: {}};
prefix.cells[1] = {getChars: () => '', getWidth: () => 0, extended: {}};
prefix.cells[2] = {getChars: () => '😀', getWidth: () => 2, extended: {}};
prefix.cells[3] = {getChars: () => '', getWidth: () => 0, extended: {}};
for (let x = 4; x < 20; x++) prefix.cells[x] = row(url).cells[x - 4];
rows = [prefix, row(url.slice(16), true)];
const spans = hover(2, 1);
assert.equal(spans.length, 2);
assert.equal(spans[0].style.left, '40px');
assert.equal(spans[0].style.width, '160px');
assert.equal(spans[1].style.width, `${(url.length - 16) * 10}px`);
click(2, 1);
assert.equal(opened.at(-1), url);

// Local artifacts use the parent viewer, including OSC labels and wrapped paths.
const messages = [];
window.location = {origin: 'http://localhost'};
window.parent = {postMessage: (message, origin) => messages.push({message, origin})};
const local = '/tmp/sample/image.png';
rows = [row(local.slice(0,20)), row(local.slice(20), true)];
click(2,0);
assert.deepEqual(messages.at(-1), {message:{type:'siling:open-local-path',path:local},origin:'http://localhost'});
const localCount = messages.length;
click(2,0,true);
click(2,0,false,true);
click(2,0,false,false,true);
assert.equal(messages.length,localCount,'drag and Option-drag must not open files');
term._core._oscLinkService.getLinkData = () => ({uri:'file:///tmp/My%20Report.png:12'});
rows=[row('report screenshot',false,1)];
click(2,0);
assert.equal(messages.at(-1).message.path,'/tmp/My Report.png');
term._core._oscLinkService.getLinkData = () => ({uri:'file://other-host/tmp/private.png'});
rows=[row('remote file',false,1)];
click(2,0);
assert.equal(messages.length,localCount+1,'remote file authorities are not local paths');
term._core._oscLinkService.getLinkData = () => ({uri:'javascript:alert(1)'});
click(2,0);
assert.equal(messages.length,localCount+1,'unsupported schemes are ignored');

rows = [row('/tmp/a.py:12:3')];
click(2,0);
assert.equal(messages.at(-1).message.path,'/tmp/a.py');
const beforeRelative = messages.length;
rows = [row('src/main.py')];
click(5,0);
assert.equal(messages.length,beforeRelative,'relative paths without a known cwd are not misread as absolute');

const fileUri='file:///tmp/a%20b.png';
rows=[row(fileUri.slice(0,20)),row(fileUri.slice(20),true)];
click(18,0);
assert.equal(messages.at(-1).message.path,'/tmp/a b.png','Click the end of an encoded file URI');

// Codex prints local Markdown links as label (path), hard-wrapped with indent.
const hardPath = '/Users/demo/Documents/OSS/project/outputs/run/artifacts/copy-history.png';
rows = [row('效果图 (/Users/'), row('  demo/Documents/'), row('  OSS/project/'),
  row('  outputs/run/'), row('  artifacts/copy-'), row('  history.png)。')];
term.rows = rows.length;
for (const [x,y] of [[1,0],[9,0],[4,2],[4,5]]) {
  click(x,y);
  assert.equal(messages.at(-1).message.path,hardPath,'Label and every hard-wrapped segment open the entire path');
}

const beforePadding = messages.length;
click(18,0);
assert.equal(messages.length,beforePadding,'Blank padding beside a hard-wrapped path is not clickable');
