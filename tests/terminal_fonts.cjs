// Execute the real injected patch, stopping once font setup reaches rendering.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = require('node:fs').readFileSync(0, 'utf8');
const stock = 'Consolas,Liberation Mono,Menlo,Courier,monospace';
for (const [platform, font, expected] of [
  ['MacIntel', stock, 'Consolas,Liberation Mono,Menlo,Courier,"PingFang SC","Apple Color Emoji",monospace'],
  ['Linux x86_64', stock, stock],
  ['Win32', stock, stock],
  ['MacIntel', 'My Custom Mono', 'My Custom Mono'],
]) {
  let writes = 0;
  let value = font;
  const options = {get fontFamily() {return value;}, set fontFamily(v) {writes++;value=v;}};
  const stop = new Error('Font initialization finished');
  const core = {coreMouseService: {}, _selectionService: {}, get _renderService() {throw stop;}};
  const context = {window: {term: {_core:core, options}, navigator:{platform}}, document:{querySelector:()=>({})}};
  assert.throws(() => vm.runInNewContext(source, context), error => error === stop);
  assert.equal(value, expected);
  assert.equal(writes, expected === font ? 0 : 1);
  core.coreMouseService.__orchInteractionPatch = true;
  vm.runInNewContext(source, context);
  assert.equal(writes, expected === font ? 0 : 1, 'Reinstall must not invalidate glyph caches');
}
