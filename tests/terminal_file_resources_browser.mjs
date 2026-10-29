import assert from 'node:assert/strict';
export async function checkTerminalFileResources({evaluate}) {
  const result = await evaluate(`(async () => {
    const card = document.createElement('div'); card.className='cached-pane';
    const frame = document.createElement('iframe');frame.dataset.fileContext='true';
    card.appendChild(frame);document.body.appendChild(card);
    await new Promise(resolve => {frame.onload=resolve;frame.src='about:blank';});
    let calls=0,write,disposed=0;
    frame.contentWindow.term={rows:0,buffer:{active:{type:'normal',length:0,baseY:0,cursorY:0}},
      registerMarker:()=>({line:0,dispose(){}}),onWriteParsed:fn=>{write=fn;return{dispose(){disposed++;}}},
      parser:{registerCsiHandler:()=>({dispose(){disposed++;}})}};
    const controller=window.SilingTerminalFiles.create({api:async()=>{calls++;return{configured:true,current:{id:'local'},settings:{auto_discover:false}};}});
    controller.attach(frame,'resource-browser');frame.dispatchEvent(new Event('load'));
    await new Promise(resolve=>setTimeout(resolve,20));
    const state=controller.states.get('resource-browser');
    write();await new Promise(resolve=>setTimeout(resolve,4200));
    const hiddenCalls=calls;
    card.classList.remove('cached-pane');await new Promise(resolve=>setTimeout(resolve,4200));
    const shownCalls=calls;
    controller.detach('resource-browser');card.remove();
    return {hiddenCalls,shownCalls,states:controller.states.size,disposed,frameReleased:state.frame===null,stopReleased:state.stop===null};
  })()`);
  assert.equal(result.hiddenCalls,1,'Real hidden iframe does not poll on each interval');
  assert.equal(result.shownCalls,2,'Visible iframe catches up without reconnecting');
  assert.equal(result.states,0);assert.equal(result.disposed,3);
  assert.equal(result.frameReleased,true);assert.equal(result.stopReleased,true);
  console.log('PASS: real iframe visibility throttle, catchup and resource release');
}
