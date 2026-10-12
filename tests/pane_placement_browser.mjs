import assert from 'node:assert/strict';
export async function checkPanePlacement({evaluate,waitFor,cdp,viewport,pause,configure}) {
  const ids=Array.from({length:16},(_,i)=>'placement-'+i);
  configure([...ids.map(run_id=>({run_id,kind:'task',agent:'claude',resume_id:'native-'+run_id,display_name:run_id,alive:true})),
    {run_id:'placement-extra',kind:'task',agent:'terminal',display_name:'Extra live session',alive:true},
    {run_id:'placement-ended',kind:'task',agent:'claude',resume_id:'original-conversation',display_name:'Recovered PM',alive:false}]);
  await viewport(1280,900);
  const boot=async(layout,slots)=>{
    await evaluate(`localStorage.clear();localStorage.setItem('orch_layout',${JSON.stringify(layout)});localStorage.setItem('orch_slots',${JSON.stringify(JSON.stringify(slots))});localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en'}));`);
    await cdp('Page.reload');
    await waitFor(`document.querySelectorAll('#grid .pane iframe').length===${slots.length}`);
    await evaluate(`window.placementAlerts=[];window.alert=text=>placementAlerts.push(text)`);
  };
  const click=async(id,meta=false)=>{
    await evaluate(`document.querySelector('.session-item[data-id="${id}"]').dispatchEvent(new MouseEvent('click',{bubbles:true,metaKey:${meta}}))`);await pause(400);
  };
  await boot('1',[ids[0]]);
  await evaluate(`window.originalFrame=document.querySelector('[data-run-id="placement-0"] iframe');document.querySelector('[data-run-id="placement-0"] .pane-input textarea').value='preserve draft'`);
  await click('placement-extra');
  await waitFor(`JSON.parse(localStorage.orch_slots).includes('placement-extra')`);
  assert.deepEqual(await evaluate('JSON.parse(localStorage.orch_slots)'),[ids[0],'placement-extra']);
  assert.equal(await evaluate(`document.querySelector('[data-run-id="placement-0"] iframe')===originalFrame`),true);
  assert.equal(await evaluate(`document.querySelector('[data-run-id="placement-0"] .pane-input textarea').value`),'preserve draft');
  await boot('cols-4x4',ids);
  await evaluate(`window.originalFrames=[...document.querySelectorAll('#grid .pane iframe')]`);
  await click('placement-extra');await click('placement-extra',true);
  assert.deepEqual(await evaluate('JSON.parse(localStorage.orch_slots)'),ids,'Full-grid clicks never evict pane 1');
  assert.equal(await evaluate('placementAlerts.length'),2);
  assert.match(await evaluate('placementAlerts[0]'),/Existing panes were kept/);
  await evaluate(`document.querySelector('[data-run-id="placement-0"] .btn-pane-more').click();document.querySelector('[data-run-id="placement-0"] .btn-fork-pane').click()`);
  await waitFor(`document.querySelector('#fork-pane-dialog').open`);
  await evaluate(`document.querySelector('#fork-pane-dialog form').requestSubmit()`);
  await waitFor(`!document.querySelector('#fork-pane-dialog').open`);
  assert.deepEqual(await evaluate('JSON.parse(localStorage.orch_slots)'),ids,'Fork at maximum capacity preserves every pane');
  assert.equal(await evaluate(`[...document.querySelectorAll('#grid .pane iframe')].every((f,i)=>f===originalFrames[i])`),true);
  assert.equal(await evaluate(`!!document.querySelector('.session-item[data-id="placement-ended"]')`),false,'Default list stays concise');
  await evaluate(`const q=document.querySelector('#sess-search-input');q.value='Recovered PM';q.dispatchEvent(new Event('input'))`);
  await waitFor(`!!document.querySelector('.session-item[data-id="placement-ended"]')`);
  await click('placement-ended');
  assert.deepEqual(await evaluate('JSON.parse(localStorage.orch_slots)'),ids,'Recoverable ended session cannot evict another pane either');
  await evaluate(`document.querySelector('[data-run-id="placement-15"] .btn-pane-more').click();document.querySelector('[data-run-id="placement-15"] .btn-unpin').click()`);
  await waitFor(`JSON.parse(localStorage.orch_slots)[15]===null`);
  await click('placement-ended');
  await waitFor(`JSON.parse(localStorage.orch_slots)[15]==='placement-ended'`);
  assert.deepEqual((await evaluate('JSON.parse(localStorage.orch_slots)')).slice(0,15),ids.slice(0,15));
  assert.ok(await evaluate(`!!document.querySelector('[data-run-id="placement-ended"] .btn-resume-ended')`),'Recovered log retains resume action');
  console.log('PASS: automatic growth preserves frame/draft; full-grid click, toggle and fork preserve all panes; ended-session search restores history into a free slot');
}
