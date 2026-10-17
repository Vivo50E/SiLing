import assert from 'node:assert/strict';
export async function checkRestartAll({evaluate,waitFor,cdp,viewport,pause,bodies,configure,ready,release,stop}) {
  const rows=['first','fail','changed','background','terminal','offline','archived','stopped','missing'].map(name=>({run_id:'bulk-'+name,display_name:'Restart '+name,kind:'run',agent:name==='terminal'?'terminal':name==='fail'?'claude':name==='background'?'cursor':'codex',resume_id:name==='missing'?'':'native-'+name,alive:name!=='stopped',remote:name==='offline',node_online:name!=='offline'}));
  configure(rows);await viewport(1280,900);
  await evaluate(`localStorage.clear();localStorage.setItem('orch_layout','cols-2');localStorage.setItem('orch_slots',JSON.stringify(['bulk-first','bulk-terminal']));localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en'}))`);
  await cdp('Page.reload');await waitFor(`!!document.querySelector('[data-run-id="bulk-first"] textarea')`);
  await waitFor(`!!document.querySelector('[data-run-id="bulk-terminal"] iframe')?.contentDocument?.querySelector('textarea')`);
  await evaluate(`window.keptFrame=document.querySelector('[data-run-id="bulk-terminal"] iframe');document.querySelector('[data-run-id="bulk-first"] textarea').value='keep restart draft';document.querySelector('#btn-workspace-menu').click();document.querySelector('#btn-restart-all').click()`);
  await waitFor(`!document.querySelector('.restart-all-start').disabled`);
  assert.equal(await evaluate(`document.querySelectorAll('.restart-all-list li').length`),4);
  assert.match(await evaluate(`document.querySelector('.restart-all-help').textContent`),/interrupts running work/);
  assert.equal(bodies.length,0);
  await evaluate(`document.querySelector('.restart-all-close').click()`);assert.equal(bodies.length,0);
  await evaluate(`document.querySelector('#btn-restart-all').click()`);await waitFor(`!document.querySelector('.restart-all-start').disabled`);
  await evaluate(`document.querySelector('.restart-all-start').click();document.querySelector('.restart-all-start').dispatchEvent(new Event('click'))`);
  for(let i=0;i<100&&!ready();i++)await pause(50);
  assert.ok(ready());assert.equal(bodies.length,1);
  stop('bulk-changed');
  await evaluate(`document.querySelector('.restart-all-stop').click()`);release();
  await waitFor(`document.querySelector('.restart-all-status').textContent.includes('Finished:')`);
  assert.equal(bodies.length,1);
  await waitFor(`document.querySelector('[data-run-id="bulk-first-restarted"] textarea')?.value==='keep restart draft'`);
  assert.equal(await evaluate(`JSON.parse(localStorage.orch_slots)[0]`),'bulk-first-restarted');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="bulk-terminal"] iframe')===keptFrame`),true);
  // The newly restarted conversation should not be restarted a second time in this page.
  await evaluate(`document.querySelector('.restart-all-close').click();document.querySelector('#btn-restart-all').click()`);
  await waitFor(`!document.querySelector('.restart-all-start').disabled`);
  await evaluate(`document.querySelector('.restart-all-start').click()`);
  await waitFor(`document.querySelector('.restart-all-status').textContent.includes('Finished:')`);
  assert.deepEqual(bodies.map(b=>b.run_id),['bulk-first','bulk-fail','bulk-background']);
  assert.match(await evaluate(`document.querySelector('.restart-all-status').textContent`),/1 restarted, 1 failed/);
  assert.equal(await evaluate(`JSON.parse(localStorage.orch_slots)[1]`),'bulk-terminal');
  console.log('PASS: restart-all review/cancel, sequential requests, stop remaining, partial failure, eligibility, background session, slots/drafts and terminal preservation');
}
