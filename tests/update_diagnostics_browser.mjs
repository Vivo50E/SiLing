import assert from 'node:assert/strict';
export async function checkUpdateDiagnostics({evaluate,waitFor,cdp,viewport,screenshot,mode,applies}) {
  await viewport(1280,900);
  mode('failed');
  await evaluate(`document.querySelector('#btn-settings').click();document.querySelector('[data-settings-section=connections]').click();document.querySelector('#btn-self-update').click()`);
  await waitFor(`document.querySelector('#self-update-error') && !document.querySelector('#self-update-error').hidden`);
  assert.ok(await evaluate(`document.querySelector('#self-update-error-output').textContent.includes('Diagnostic <img src=x> detail')`));
  assert.equal(await evaluate(`document.querySelector('#self-update-error-output img')`),null,'Diagnostics are text, never HTML');
  assert.equal(await evaluate(`document.querySelector('#self-update-reminder').open`),false);
  await evaluate(`document.querySelector('#self-update-error').scrollIntoView({block:'center'})`);
  await screenshot('update-error-desktop');
  await cdp('Page.reload');
  await waitFor(`document.querySelector('#self-update-error') && !document.querySelector('#self-update-error').hidden`);
  await evaluate(`document.querySelector('#btn-settings').click();document.querySelector('[data-settings-section=connections]').click()`);
  assert.ok(await evaluate(`document.querySelector('#btn-self-update').title.includes('Fixture tests failed')`),'Polling/reload retains failure');
  await viewport(390,844);
  await evaluate(`document.querySelector('#self-update-error').scrollIntoView({block:'center'})`);
  await screenshot('update-error-mobile');
  mode('ok');
  await evaluate(`document.querySelector('#btn-self-update').click()`);
  await waitFor(`document.querySelector('#self-update-reminder').open`);
  assert.equal(await evaluate(`document.querySelector('#self-update-error').hidden`),true,'Retry clears stale error');
  assert.equal(applies.length,0,'No automatic application');
  await evaluate(`document.querySelector('#self-update-later').click()`);
  console.log('PASS: visible update error, safe text, reload persistence, retry clearing and explicit approval');
}
