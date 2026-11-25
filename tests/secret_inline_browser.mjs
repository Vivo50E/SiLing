import assert from 'node:assert/strict';
export async function checkInlineSecrets({evaluate,waitFor,viewport,cdp,screenshot,privateSubmissions,brokerRegistrations,sentPrompts,frameCount}) {
  await viewport(1280,900);
  await evaluate(`localStorage.setItem('orch_layout','cols-2');localStorage.setItem('orch_slots',JSON.stringify(['fixture-0','fixture-1']))`);
  await cdp('Page.reload');
  const card='[data-run-id="fixture-0"]';
  await waitFor(`!!document.querySelector('${card} iframe')`);
  const frames=frameCount(), prompts=sentPrompts.length;
  await evaluate(`document.querySelector('${card} .pane-input textarea').value='preserved ordinary draft'`);
  const open=async kind=>{
    await evaluate(`document.querySelector('${card} .btn-pane-more').click();document.querySelector('${card} .btn-secret-${kind==='config'?'input':'operations'}').click()`);
    await waitFor(`!!document.querySelector('${card} .pane-secret-card[open]')`);
  };
  const close=async()=>{
    await evaluate(`document.querySelector('${card} .pane-secret-card [data-close]').click()`);
    await waitFor(`!document.querySelector('${card} .pane-secret-card')`);
  };
  for(const kind of ['config','operations']) {
    await open(kind);
    assert.equal(await evaluate(`document.querySelector('${card} .pane-secret-card').matches(':modal')`),false);
    assert.equal(await evaluate(`document.querySelector('${card} .pane-secret-card [data-value]').type`),'password');
    assert.ok(await evaluate(`(()=>{const c=document.querySelector('${card}').getBoundingClientRect(),d=document.querySelector('${card} .pane-secret-card').getBoundingClientRect();return d.left>=c.left&&d.right<=c.right&&d.top>=c.top&&d.bottom<=c.bottom;})()`),'Card stays inside its source pane');
    await evaluate(`window.retainedSecretField=document.querySelector('${card} .pane-secret-card [data-value]');retainedSecretField.value='fixture-private-cancel';retainedSecretField.focus()`);
    await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await waitFor(`!document.querySelector('${card} .pane-secret-card')`);
    assert.equal(await evaluate('retainedSecretField.value'),'','Detached field is erased');
  }
  await open('config');
  const storage=await evaluate('JSON.stringify(localStorage)');
  await evaluate(`{const d=document.querySelector('${card} .pane-secret-card');d.querySelector('[data-directory]').value='/fixture/config';d.querySelector('[data-name]').value='API_TOKEN';d.querySelector('[data-value]').value='fixture-safe-config';d.querySelector('[data-confirm]').checked=true;d.querySelector('[data-submit]').click();}`);
  await waitFor(`document.querySelector('${card} [data-status]').textContent.includes('Saved')`);
  assert.equal(privateSubmissions.at(-1).value,'fixture-safe-config');
  assert.equal(await evaluate(`document.querySelector('${card} [data-value]').value`),'');
  await screenshot('inline-secret-config');await close();
  await open('operations');
  await evaluate(`document.querySelector('${card} [data-value]').value='fixture-safe-operation';document.querySelector('${card} [data-submit]').click()`);
  await waitFor(`document.querySelector('${card} [data-status]').textContent.includes('Registered')`);
  assert.equal(brokerRegistrations.at(-1).scope,'fixture-0');
  assert.equal(await evaluate(`document.querySelector('${card} [data-value]').value`),'');
  await screenshot('inline-secret-operation');
  assert.equal(await evaluate('JSON.stringify(localStorage)'),storage);
  assert.equal(sentPrompts.length,prompts,'No credential is sent to the agent');
  assert.equal(frameCount(),frames,'Opening and closing preserves terminal frames');
  assert.equal(await evaluate(`document.querySelector('${card} .pane-input textarea').value`),'preserved ordinary draft');
  // Other panes remain usable while the private card is open.
  await evaluate(`document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').focus()`);
  assert.equal(await evaluate(`document.activeElement.closest('.pane-card').dataset.runId`),'fixture-1');
  await evaluate(`window.retainedSecretField=document.querySelector('${card} [data-value]');retainedSecretField.value='fixture-hide';document.querySelector('${card}').style.display='none'`);
  await waitFor(`!document.querySelector('${card} .pane-secret-card')`);
  assert.equal(await evaluate('retainedSecretField.value'),'');
  await evaluate(`document.querySelector('${card}').style.display=''`);
  await open('config');
  await evaluate(`window.retainedSecretField=document.querySelector('${card} [data-value]');retainedSecretField.value='fixture-reassigned';document.querySelector('${card}').dataset.runId='fixture-reassigned'`);
  await waitFor(`!document.querySelector('.pane-secret-card')`);
  assert.equal(await evaluate('retainedSecretField.value'),'','Reassigning the source clears its field');
  await evaluate(`document.querySelector('[data-run-id="fixture-reassigned"]').dataset.runId='fixture-0'`);
  await viewport(900,844);await open('operations');await screenshot('inline-secret-narrow');
  assert.ok(await evaluate(`(()=>{const r=document.querySelector('${card} .pane-secret-card').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()`));
  await evaluate(`window.retainedSecretField=document.querySelector('${card} [data-value]');retainedSecretField.value='fixture-mobile-switch'`);
  await viewport(390,844);
  await waitFor(`!document.querySelector('${card} .pane-secret-card')`);
  assert.equal(await evaluate('retainedSecretField.value'),'','Switching into the mobile reader clears hidden pane input');
  assert.equal(await evaluate(`JSON.stringify(localStorage).includes('fixture-safe')`),false);
  console.log('PASS: pane-local nonmodal credentials, exact session, masked/cleared values, no prompt/storage/frame mutation, hidden-pane cleanup, other pane input, narrow layout and mobile reader cleanup');
}
