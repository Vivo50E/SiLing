import assert from 'node:assert/strict';
export async function checkArrangeNames({evaluate,waitFor,cdp,viewport,screenshot,configure}) {
  const names=['Pane 10','Pane 2','alpha','Zeta','SAME','same','U10','U2'];
  const rows=names.map((display_name,i)=>({run_id:'arr-'+i,display_name,kind:'run',agent:'terminal',alive:true,group:i<2||i===4||i===5?'arr-a':i<4?'arr-b':''}));
  await waitFor(`!!document.querySelector('#session-list .session-item')`);
  configure(rows);await viewport(1280,900);
  await evaluate(`localStorage.clear();localStorage.setItem('orch_layout','cols-3x3');localStorage.setItem('orch_slots',JSON.stringify(['arr-0',null,'arr-3','arr-5','arr-6','arr-1','arr-4','arr-7','arr-2']));localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en'}))`);
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('#grid .pane iframe').length===8`);
  await evaluate(`window.arrangeFrames=new Map([...document.querySelectorAll('#grid .pane-card[data-run-id]')].map(card=>[card.dataset.runId,card.querySelector('iframe')]));document.querySelector('[data-run-id="arr-0"] .pane-input textarea').value='keep draft';document.querySelector('#btn-arrange-groups').click()`);
  const expected=['arr-2','arr-3','arr-1','arr-0','arr-5','arr-4','arr-7','arr-6',null];
  assert.deepEqual(await evaluate(`JSON.parse(localStorage.orch_slots)`),expected,'Group tab order precedes natural names; equal names stay stable; ungrouped and blanks finish');
  assert.equal(await evaluate(`[...arrangeFrames].every(([id,frame])=>document.querySelector('[data-run-id="'+id+'"] iframe')===frame)`),true,'Arrange preserves every terminal iframe');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="arr-0"] .pane-input textarea').value`),'keep draft');
  await evaluate(`document.querySelector('#btn-arrange-groups').click()`);
  assert.deepEqual(await evaluate(`JSON.parse(localStorage.orch_slots)`),expected,'Repeated arrange is stable');
  await screenshot('arrange-natural-names');
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('#grid .pane iframe').length===8`);
  assert.deepEqual(await evaluate(`JSON.parse(localStorage.orch_slots)`),expected,'Arranged positions survive reload');
  console.log('PASS: group-first natural name order, case-insensitive stable ties, ungrouped/empty slots, iframe/draft preservation and persisted layout');
}
