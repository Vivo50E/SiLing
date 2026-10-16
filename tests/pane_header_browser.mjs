import assert from 'node:assert/strict';
export async function checkPaneHeader({evaluate,waitFor,cdp,viewport,screenshot}) {
  await viewport(1280,900);
  await waitFor(`document.querySelectorAll('.pane-card iframe').length>0`);
  const badge='.pane-card .pane-head .slot-badge';
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.pane-head .dot')).display`),'none');
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#session-list .dot')).display==='none'`),false,'Sidebar status remains available');
  await evaluate(`window.headerFrames=[...document.querySelectorAll('.pane-card iframe')];document.querySelector('.pane-card .pane-input textarea').value='header draft';document.querySelector('#settings-show-pane-numbers').checked=false;document.querySelector('#settings-show-pane-numbers').dispatchEvent(new Event('change'))`);
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('${badge}')).display`),'none');
  assert.equal(await evaluate(`[...document.querySelectorAll('.pane-card iframe')].every((f,i)=>f===headerFrames[i])`),true,'Changing number visibility preserves frames');
  assert.equal(await evaluate(`document.querySelector('.pane-card .pane-input textarea').value`),'header draft');
  await evaluate(`document.querySelector('.pane-card .btn-zoom').click()`);
  await waitFor(`!!document.querySelector('.zoomed-pane')`);
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.zoomed-pane .slot-badge')).display`),'none');
  await evaluate(`document.querySelector('.zoomed-pane .btn-zoom').click()`);
  await screenshot('pane-header-hidden');
  await cdp('Page.reload');
  await waitFor(`!!document.querySelector('${badge}')`);
  assert.equal(await evaluate(`document.querySelector('#settings-show-pane-numbers').checked`),false);
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('${badge}')).display`),'none','Preference survives reload');
  await evaluate(`{const c=document.querySelector('[data-appearance="language"]');c.value='zh';c.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`document.querySelector('label[for="settings-show-pane-numbers"] .settings-row-title').textContent`),'显示 pane 编号');
  await evaluate(`document.querySelector('#settings-reset-appearance').click()`);
  assert.equal(await evaluate(`document.querySelector('#settings-show-pane-numbers').checked`),true);
  assert.notEqual(await evaluate(`getComputedStyle(document.querySelector('${badge}')).display`),'none');
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.pane-head .dot')).display`),'none');
  console.log('PASS: hidden pane status dots, optional numbers, zoom, saved preference, bilingual setting, reset and frame/draft preservation');
}
