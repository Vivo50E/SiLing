import assert from 'node:assert/strict';

export async function checkArchives({evaluate, waitFor, viewport, screenshot, pause, cdp,
                                     requests, mode, view, submissions, sessions, groups}) {
  groups.groups.push({id:'archive-project',name:'Archive project fixture',color:'#765abc'});
  groups.members['fixture-0']='archive-project';
  await viewport(1280, 900);
  await evaluate(`localStorage.setItem('orch_slots',JSON.stringify(['fixture-0','fixture-1','fixture-2','fixture-3']));localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en',theme:'dark'}))`);
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('.pane iframe').length===4`);
  await evaluate(`window.archiveAlerts=[];window.alert=text=>archiveAlerts.push(text);window.confirm=()=>false;
    window.archiveFrames=[...document.querySelectorAll('.pane iframe')];
    document.querySelector('[data-run-id="fixture-0"] .pane-input textarea').value='first draft';
    document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').value='second draft'`);
  const requestStart=requests.length;
  const initialState=JSON.stringify(sessions);
  const archive = id => evaluate(`document.querySelector('[data-run-id="${id}"] .btn-pane-more').click();document.querySelector('[data-run-id="${id}"] .btn-archive-session').click()`);
  const openArchives = async () => {
    await evaluate(`document.querySelector('#btn-session-archives').focus()`);
    await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
    await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await waitFor(`document.querySelector('#session-archives').open`);
  };
  const action = (id, name) => evaluate(`document.querySelector('#session-archives [data-id="${id}"][data-action="${name}"]').click()`);
  const closeArchives = () => evaluate(`document.querySelector('#session-archives').close()`);
  await archive('fixture-0'); await pause(100);
  assert.equal(submissions.length,0,'Cancel makes no archive request');
  mode('error'); await evaluate(`window.confirm=()=>true`);
  await archive('fixture-0');
  await waitFor(`archiveAlerts.length===1`);
  assert.equal(await evaluate(`document.querySelectorAll('.pane iframe').length`),4,'Failed save leaves displays intact');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-0"] .pane-input textarea').value`),'first draft');
  mode('ok'); await archive('fixture-0');
  await waitFor(`!document.querySelector('#grid [data-run-id="fixture-0"]')`);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[0]`),null,'Archived slot stays empty');
  assert.ok(await evaluate(`archiveFrames.slice(1).every(f=>f.isConnected)`),'Other displays are preserved');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').value`),'second draft');
  assert.equal(await evaluate(`document.querySelector('#btn-session-archives').dataset.count`),'1');
  assert.match(await evaluate(`document.querySelector('#btn-session-archives').textContent`),/running 1/);
  const ttyCount=()=>requests.filter(r=>r.path.endsWith('/tty')).length;
  const ttyBefore=ttyCount();
  await openArchives();
  await evaluate(`document.querySelector('#session-archives input').value='Archive project fixture';document.querySelector('#session-archives input').dispatchEvent(new Event('input'))`);
  assert.equal(await evaluate(`document.querySelectorAll('#session-archives .archive-item').length`),1,'Archived search includes project-group names');
  await evaluate(`document.querySelector('#session-archives input').value='no-such-session';document.querySelector('#session-archives input').dispatchEvent(new Event('input'))`);
  assert.equal(await evaluate(`document.querySelectorAll('#session-archives .archive-item').length`),0);
  await evaluate(`document.querySelector('#session-archives input').value='';document.querySelector('#session-archives input').dispatchEvent(new Event('input'))`);
  await action('fixture-0','read');
  await waitFor(`document.querySelector('.archive-preview pre').textContent.includes('<literal>')`);
  assert.equal(await evaluate(`document.querySelector('.archive-preview literal')`),null,'Output is literal text');
  assert.match(await evaluate(`document.querySelector('.archive-preview p').textContent`),/not a complete native conversation.*Truncated/);
  await screenshot('archives-desktop-en');
  await action('fixture-0','files');
  await waitFor(`document.querySelector('#folder-modal').hidden===false`);
  assert.equal(await evaluate(`document.querySelector('#session-archives').open`),false,'Files is not obscured by archive dialog');
  await evaluate(`document.querySelector('#folder-modal-close').click()`);
  await openArchives(); await action('fixture-0','restore');
  await waitFor(`document.querySelector('#btn-session-archives').dataset.count==='0'`);
  await closeArchives();
  assert.equal(ttyCount(),ttyBefore,'Read, Files and unarchive never attach terminals');
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[0]`),null,'Unarchive does not change layout');
  await evaluate(`document.querySelector('.session-item[data-id="fixture-0"]').click()`);
  await waitFor(`!!document.querySelector('#grid [data-run-id="fixture-0"] iframe')`);
  assert.equal(await evaluate(`document.querySelector('#grid [data-run-id="fixture-0"] .pane-input textarea').value`),'first draft');

  // Another client files one exact execution. The normal five-second inventory
  // poll must reconcile it, without affecting related or running sessions.
  view.entries['fixture-1']={archived:true,revision:1,archived_at:Date.now()/1000};view.revision++;
  await waitFor(`!document.querySelector('#grid [data-run-id="fixture-1"]')`);
  assert.equal(await evaluate(`sessionStorage.getItem('orch_archived_draft:fixture-1')`),'second draft');
  await evaluate(`localStorage.setItem('orch_slots',JSON.stringify(['fixture-0','fixture-1','fixture-2','fixture-3']))`);
  const reloadStart=requests.length;
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('.pane iframe').length===3`);
  await pause(200);
  assert.equal(requests.slice(reloadStart).some(r=>r.path==='/api/sessions/fixture-1/tty'),false,'Old workspace never reattaches archived execution');
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[1]`),null);
  await evaluate(`window.archiveAlerts=[];window.alert=text=>archiveAlerts.push(text);window.confirm=()=>true`);
  await openArchives(); await action('fixture-1','restore');
  await waitFor(`document.querySelector('#btn-session-archives').dataset.count==='0'`);
  await closeArchives();
  await evaluate(`document.querySelector('.session-item[data-id="fixture-1"]').click()`);
  await waitFor(`!!document.querySelector('#grid [data-run-id="fixture-1"] iframe')`);
  assert.equal(await evaluate(`document.querySelector('#grid [data-run-id="fixture-1"] .pane-input textarea').value`),'second draft','Draft survives refresh and explicit reopening');

  mode('lost'); await archive('fixture-0');
  await waitFor(`archiveAlerts.length===1`);
  await waitFor(`!document.querySelector('#grid [data-run-id="fixture-0"]')`);
  assert.equal(view.entries['fixture-0'].revision,3,'Lost response is reconciled by read, not repeated write');
  mode('ok');
  await evaluate(`document.querySelector('#layout-picker [data-layout="cols-3x2"]').click()`);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots')).includes('fixture-0')`),false,'Automatic layout fill excludes archived records');
  await viewport(390,844);
  await evaluate(`{const c=document.querySelector('[data-appearance="language"]');c.value='zh';c.dispatchEvent(new Event('change'));}`);
  await waitFor(`!!document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]')`);
  await evaluate(`document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]').click()`);
  await waitFor(`document.querySelector('#mobile-reader-output').textContent.includes('<literal>')`);
  const mobileTty=ttyCount();
  await evaluate(`document.querySelector('#mobile-reader-archive').click()`);
  await waitFor(`document.querySelector('#mobile-reader-detail').hidden`);
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]')`),null);
  await evaluate(`document.querySelector('#mobile-reader-archives').click()`);
  await action('fixture-2','read');
  await waitFor(`document.querySelector('.archive-preview pre').textContent.includes('<literal>')`);
  assert.equal(await evaluate(`document.querySelector('#session-archives-title').textContent`),'已归档会话');
  assert.ok(await evaluate(`document.documentElement.scrollWidth<=innerWidth && document.querySelector('#session-archives').scrollWidth<=document.querySelector('#session-archives').clientWidth`));
  assert.ok(await evaluate(`[...document.querySelectorAll('#session-archives button')].every(b=>b.getBoundingClientRect().height>=44)`));
  await screenshot('archives-mobile-zh');
  await evaluate(`document.documentElement.dataset.appTheme='light'`);
  await screenshot('archives-mobile-zh-light');
  await action('fixture-2','restore');
  await waitFor(`!!document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]')`);
  await closeArchives();
  await waitFor(`document.activeElement.id==='mobile-reader-archives'`);
  assert.equal(ttyCount(),mobileTty,'Mobile archiving and reading never attaches terminal');
  assert.equal(JSON.stringify(sessions),initialState,'Filing never mutates execution, flags, names or groups');
  assert.equal(groups.members['fixture-0'],'archive-project','Archive preserves project-group membership');
  // An ended execution remains inspectable and returns to the ordinary list
  // when explicitly unarchived; it must not be silently restarted.
  sessions[2].alive=false; sessions[2].agent_exited=true;
  await evaluate(`document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]').click();document.querySelector('#mobile-reader-archive').click()`);
  await waitFor(`document.querySelector('#mobile-reader-detail').hidden`);
  await evaluate(`document.querySelector('#mobile-reader-archives').click()`); await action('fixture-2','restore');
  await waitFor(`!!document.querySelector('#mobile-reader-list [data-run-id="fixture-2"]')`);
  await closeArchives();
  await viewport(1280,900);
  await waitFor(`!!document.querySelector('.session-item[data-id="fixture-2"]')`);
  mode('metadata-error');
  await evaluate(`localStorage.setItem('orch_slots',JSON.stringify(['fixture-0','fixture-1','fixture-2','fixture-3']))`);
  const unavailableStart=requests.length;
  await cdp('Page.reload');
  await waitFor(`document.querySelectorAll('#grid .empty-slot[role="status"]').length===4`);
  assert.equal(requests.slice(unavailableStart).some(r=>r.path.endsWith('/tty')),false,'Unknown archive state cannot replay old layout into terminals');
  assert.match(await evaluate(`document.querySelector('#grid .empty-slot').textContent`),/归档状态不可用/);
  mode('ok'); await evaluate(`document.querySelector('#btn-refresh').click()`);
  await waitFor(`!!document.querySelector('#grid [data-run-id="fixture-1"] iframe')`);
  assert.equal(await evaluate(`document.querySelector('#grid [data-run-id="fixture-0"]')`),null,'Retry honors archived identity');
  // Every page boot also checks available updates; that fixture-only request
  // is unrelated to session control. No other mutations are permitted here.
  assert.deepEqual(requests.slice(requestStart).filter(r=>r.method==='POST'
    && !['/api/session-archives','/api/self-update/fetch'].includes(r.path)),[],
    'Archive workflow never sends, stops, creates or restarts agents');
  console.log('PASS: archive cancellation/failure/lost response, authoritative shared state, preserved frames/drafts, old layout exclusion, bounded output/Files, explicit unarchive and Chinese mobile');
}
