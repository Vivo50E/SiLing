import assert from 'node:assert/strict';

export async function checkPaneStartup({evaluate,waitFor,cdp,viewport,pause,screenshot,url,requests,frameLoads,hold,held,release}) {
  await viewport(1280,800);
  const script=await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.startupPollTimers=[];
    const nativeInterval=window.setInterval;
    window.setInterval=(callback,delay,...args)=>{
      if(delay===30000||delay===300000)window.startupPollTimers.push(callback);
      return nativeInterval(callback,delay,...args);
    };
  `});
  try {
    for (const fail of [false,true]) {
      hold();
      await cdp('Page.navigate',{url});
      await waitFor(`document.querySelectorAll('.pane iframe').length===4`);
      await waitFor(`Array.from(document.querySelectorAll('.pane iframe')).every(f=>f.contentDocument?.readyState==='complete')`);
      assert.ok(held.some(item=>item.path==='/api/sync/status'),'Sync request stays pending while panes load');
      assert.ok(held.some(item=>item.path==='/api/self-update/fetch'),'Update request stays pending while panes load');
      const count=path=>requests.filter(item=>item.path===path).length;
      const before=[count('/api/sync/status'),count('/api/self-update'),count('/api/self-update/fetch')];
      await evaluate(`window.startupPollTimers.forEach(callback=>{callback();callback();})`);
      await pause(150);
      assert.deepEqual([count('/api/sync/status'),count('/api/self-update'),count('/api/self-update/fetch')],before,
        'Automatic polls do not accumulate behind slow checks');
      if (!fail) {
        await evaluate(`document.querySelector('#btn-self-update').click()`);
        for(let i=0;i<100&&held.filter(item=>item.path==='/api/self-update/fetch').length<2;i++)await pause(50);
        const manual=held.findLast(item=>item.path==='/api/self-update/fetch');
        assert.equal(held.filter(item=>item.path==='/api/self-update/fetch').length,2,
          'Explicit update check still runs while the automatic check is pending');
        held.splice(held.indexOf(manual),1);manual.release();
        await waitFor(`document.querySelector('#btn-self-update').textContent==='approve update'`);
        assert.equal(count('/api/self-update/apply'),0,'Verification still waits for separate approval');
      }
      await evaluate(`window.startupFrame=document.querySelector('.pane iframe');window.startupInput=document.querySelector('.pane-input textarea');startupInput.value='Keep this unsent draft';startupInput.focus();startupInput.setSelectionRange(5,9);`);
      const loads=frameLoads();
      await evaluate(`window.startupStatusChanged=false;{const observer=new MutationObserver(()=>{window.startupStatusChanged=true;observer.disconnect();});observer.observe(document.querySelector('#btn-self-update'),{childList:true});}`);
      release(fail);
      await waitFor('window.startupStatusChanged');
      await waitFor(fail ? `document.querySelector('#btn-self-update').title.includes('503')`
        : `document.querySelector('#btn-self-update').title.includes('agent/self-improve-fixture')`);
      assert.equal(await evaluate(`startupFrame===document.querySelector('.pane iframe')`),true,'Late status keeps the terminal frame');
      assert.equal(frameLoads(),loads,'Late status does not reload terminal frames');
      assert.deepEqual(await evaluate(`[startupInput.value,startupInput.selectionStart,startupInput.selectionEnd]`),
        ['Keep this unsent draft',5,9],'Late status preserves draft and selection');
      if (fail) {
        release(false);
        await evaluate(`window.startupPollTimers.forEach(callback=>callback())`);
        await waitFor(`document.querySelector('#btn-self-update').title.includes('agent/self-improve-fixture')`);
        assert.equal(await evaluate(`startupFrame===document.querySelector('.pane iframe')`),true,
          'Successful polling resumes after a failure without replacing the terminal');
      }
      if (!fail) await screenshot('panes-with-background-checks');
    }
  } finally {
    release(false);
    await cdp('Page.removeScriptToEvaluateOnNewDocument',{identifier:script.identifier});
    await cdp('Page.navigate',{url:new URL('/fixture-tty/startup-reset',url).href});
  }
  console.log('PASS: pending/failed background checks preserve pane startup, bounded polling, terminal frames and drafts');
}
