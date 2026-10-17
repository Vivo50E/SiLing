import assert from 'node:assert/strict';
export async function checkPaneCache({evaluate,waitFor,cdp,viewport,pause}) {
  await viewport(1280,900);
  await evaluate(`localStorage.setItem('orch_layout','1');localStorage.setItem('orch_slots',JSON.stringify(['fixture-0']))`);
  await cdp('Page.reload');
  await waitFor(`!!document.querySelector('.pane-card[data-run-id="fixture-0"] iframe')?.contentDocument?.querySelector('textarea')`);
  await evaluate(`window.cachedFrame=document.querySelector('.pane-card[data-run-id="fixture-0"] iframe');window.cachedDoc=cachedFrame.contentDocument;cachedDoc.body.style.height='4000px';cachedFrame.contentWindow.scrollTo(0,600);document.querySelector('.pane-card[data-run-id="fixture-0"] .pane-input textarea').value='keep history draft'`);
  const click=async id=>{await evaluate(`document.querySelector('.session-item[data-id="${id}"]').dispatchEvent(new MouseEvent('click',{bubbles:true,shiftKey:true}))`);await pause(200);};
  await click('fixture-1');
  await waitFor(`document.querySelector('.pane-card[data-run-id="fixture-0"]').classList.contains('cached-pane')`);
  await viewport(1000,900);
  await click('fixture-0');
  assert.equal(await evaluate(`document.querySelector('.pane-card[data-run-id="fixture-0"] iframe')===cachedFrame`),true,'Resize while hidden must not recreate the terminal');
  assert.equal(await evaluate(`cachedFrame.contentDocument===cachedDoc`),true);
  assert.equal(await evaluate(`cachedFrame.contentWindow.scrollY`),600,'History offset survives return');
  await click('fixture-1');
  await evaluate(`document.querySelector('[data-layout="cols-2x2"]').click()`);
  await click('fixture-0');
  assert.equal(await evaluate(`document.querySelector('.pane-card[data-run-id="fixture-0"] iframe')===cachedFrame`),true,'Layout change must reuse cached terminal');
  assert.equal(await evaluate(`document.querySelector('.pane-card[data-run-id="fixture-0"] .pane-input textarea').value`),'keep history draft');
  console.log('PASS: hidden pane reuse across window/layout resize, history offset and draft preservation');
}
