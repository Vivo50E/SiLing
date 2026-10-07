import assert from 'node:assert/strict';

export async function checkGroupOrder({evaluate,waitFor,cdp,viewport,screenshot,pause,requests,groups,frameLoads,fail}) {
  await waitFor(`!!document.querySelector('#pane-group-tabs')`);
  await viewport(1280,900);
  await waitFor(`document.querySelectorAll('.pane iframe').length===4 && [...document.querySelectorAll('.pane iframe')].every(f=>f.contentDocument?.querySelector('textarea'))`);
  // Reordering edits only group metadata and preserves filtering, slots and frames.
  groups.groups=[{id:'project-fixture',name:'Group A',color:'blue'},{id:'group-b',name:'Group B',color:'teal'},{id:'group-c',name:'Group C',color:'pink'}];
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('[data-group-reorder]').length===3`);
  await waitFor(`document.querySelectorAll('.pane iframe').length===4 && [...document.querySelectorAll('.pane iframe')].every(f=>f.contentDocument?.querySelector('textarea'))`);
  await evaluate(`document.querySelector('[data-group-filter="all"]').click()`);
  const groupOrderFrames=frameLoads();
  const groupOrderSlots=await evaluate(`localStorage.getItem('orch_slots')`);
  const orderIds=()=>evaluate(`Array.from(document.querySelectorAll('[data-group-reorder]')).map(b=>b.dataset.groupFilter)`);
  const pointerGroup=async(id)=>evaluate(`(()=>{const r=document.querySelector('[data-group-filter="'+${JSON.stringify(id)}+'"]').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  const dragGroup=async(from,to,cancel=false)=>{
    const start=await pointerGroup(from),end=await pointerGroup(to);end.x-=10;
    await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...start,button:'left',buttons:1,clickCount:1});
    for(let i=1;i<=8;i++) {await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:start.x+(end.x-start.x)*i/8,y:end.y,button:'left',buttons:1});await pause(20);}
    if(cancel) await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...end,button:'left',buttons:0,clickCount:1});
  };
  const groupWrites=()=>requests.filter(r=>r.path==='/api/pane-groups'&&r.method==='POST').length;
  let writes=groupWrites();
  await dragGroup('group-c','project-fixture');
  await waitFor(`document.querySelector('[data-group-reorder]').dataset.groupFilter==='group-c'`);
  assert.deepEqual(await orderIds(),['group-c','project-fixture','group-b']);
  assert.equal(groupWrites(),writes+1,'One drop saves one move');
  assert.equal(await evaluate(`localStorage.getItem('siling_group_filter')||'all'`),'all','Dragging never filters');
  assert.equal(await evaluate(`localStorage.getItem('orch_slots')`),groupOrderSlots);
  assert.equal(frameLoads(),groupOrderFrames,'Dragging never reloads terminals');
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('#pane-group-tabs button')).slice(0,2).map(b=>b.dataset.groupFilter)`),['all','ungrouped'],'Fixed tabs stay at the front');
  writes=groupWrites();
  await dragGroup('group-b','group-c',true);
  await pause(150);
  assert.equal(groupWrites(),writes,'Escape cancels without saving');
  assert.deepEqual(await orderIds(),['group-c','project-fixture','group-b']);
  fail(true);
  await dragGroup('group-b','group-c');
  await waitFor(`document.querySelector('#pane-group-status').textContent.includes('失败')||document.querySelector('#pane-group-status').textContent.includes('failed')`);
  assert.deepEqual(await orderIds(),['group-c','project-fixture','group-b'],'Failed saves retain the authoritative order');
  fail(false);
  await evaluate(`document.querySelector('[data-group-filter="group-b"]').focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowLeft',code:'ArrowLeft',modifiers:1,windowsVirtualKeyCode:37});
  await waitFor(`Array.from(document.querySelectorAll('[data-group-reorder]'))[1].dataset.groupFilter==='group-b'`);
  await screenshot('group-order-desktop');
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('[data-group-reorder]').length===3`);
  assert.deepEqual(await orderIds(),['group-c','group-b','project-fixture'],'Saved order survives reload');
  const point=await pointerGroup('group-b');
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',buttons:1,clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',buttons:0,clickCount:1});
  await waitFor(`document.querySelector('[data-group-filter="group-b"]').getAttribute('aria-pressed')==='true'`);
  await evaluate(`document.querySelector('[data-group-filter="all"]').click()`);
  groups.groups.forEach((g,index)=>{g.name=['C','B','A'][index];});
  await viewport(1024,844);
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('[data-group-reorder]').length===3`);
  await evaluate(`{const tabs=document.querySelector('#pane-group-tabs');tabs.scrollLeft=tabs.scrollWidth;}`);
  await cdp('Emulation.setTouchEmulationEnabled',{enabled:true});
  const touchStart=await pointerGroup('project-fixture'),touchEnd=await pointerGroup('group-b');touchEnd.x-=10;
  await cdp('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{...touchStart,id:1}]});
  for(let i=1;i<=8;i++){await cdp('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:touchStart.x+(touchEnd.x-touchStart.x)*i/8,y:touchEnd.y,id:1}]});await pause(20);}
  await cdp('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await waitFor(`Array.from(document.querySelectorAll('[data-group-reorder]'))[1].dataset.groupFilter==='project-fixture'`);
  await screenshot('group-order-touch-tablet');
  await cdp('Emulation.setTouchEmulationEnabled',{enabled:false});
  await viewport(1280,900);
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('.pane iframe').length===4`);
  await waitFor(`document.querySelectorAll('.pane iframe').length===4 && [...document.querySelectorAll('.pane iframe')].every(f=>f.contentDocument?.querySelector('textarea'))`);
  console.log('PASS: group drag/touch ordering, fixed tabs, cancellation, failed saves, keyboard moves, persistence and ordinary filter clicks');
}
