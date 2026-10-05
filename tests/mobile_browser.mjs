// Invoked by the existing isolated Dashboard fixture, never a live server.
import assert from 'node:assert/strict';

export async function checkMobileReader({evaluate, viewport, waitFor, screenshot, requests, pause, mode, delayed, release}) {
  await waitFor(`document.querySelectorAll('#mobile-reader-list button[data-run-id]').length === 5`);
  const prefs = await evaluate(`['orch_slots','orch_layout','orch_tty'].map(k=>localStorage.getItem(k))`);
  assert.equal(requests.filter(r=>r.path.endsWith('/tty')).length,0,'Mobile boot must not attach terminals');
  await evaluate(`{const list=document.querySelector('#mobile-reader-list');list.style.maxHeight='120px';list.scrollTop=80;list.querySelectorAll('button')[2].click();document.querySelector('#mobile-reader-back').click();}`);
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-list').scrollTop`),80,'Back restores list scroll');
  await evaluate(`{document.querySelector('#mobile-reader-list').style.maxHeight='';const filter=document.querySelector('#mobile-reader-filter');filter.value='attention';filter.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`document.querySelectorAll('#mobile-reader-list button').length`),1,'Manual blocked flag belongs in attention filter');
  await evaluate(`document.querySelector('#mobile-reader-search').value='Task 1';document.querySelector('#mobile-reader-search').dispatchEvent(new Event('input'));document.querySelector('#mobile-reader-list button').click()`);
  await waitFor(`document.querySelector('#mobile-reader-output').textContent.includes('<literal>')`);
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-output literal')`),null);
  assert.match(await evaluate(`document.querySelector('#mobile-reader-meta').textContent`),/Snapshot read at/);
  assert.match(await evaluate(`document.querySelector('#mobile-reader-meta').textContent`),/Truncated/);
  const metadata = await evaluate(`document.querySelector('#mobile-reader-meta').textContent`);
  mode('error');
  await evaluate(`document.querySelector('#mobile-reader-refresh').click()`);
  await waitFor(`document.querySelector('#mobile-reader-notice').textContent.includes('stale')`);
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-meta').textContent`),metadata,'Failure retains original snapshot timestamp');
  assert.match(await evaluate(`document.querySelector('#mobile-reader-output').textContent`),/<literal>/);
  mode('legacy');
  await evaluate(`document.querySelector('#mobile-reader-refresh').click()`);
  await waitFor(`document.querySelector('#mobile-reader-output').textContent==='legacy snapshot'`);
  assert.match(await evaluate(`document.querySelector('#mobile-reader-meta').textContent`),/Snapshot time unknown.*Truncation unknown/);
  mode('empty');
  await evaluate(`document.querySelector('#mobile-reader-refresh').click()`);
  await waitFor(`document.querySelector('#mobile-reader-notice').textContent==='No output yet'`);
  mode('ok');
  await evaluate(`document.querySelector('#mobile-reader-refresh').click()`);
  await waitFor(`document.querySelector('#mobile-reader-output').textContent.includes('<literal>')`);
  for(const width of [360,390,430,780]) {
    await viewport(width,width===780?390:844);
    assert.ok(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'No page overflow');
    assert.ok(await evaluate(`document.querySelector('#mobile-reader-back').getBoundingClientRect().height>=44`));
    await screenshot('mobile-reader-'+width);
  }
  await evaluate(`document.querySelector('#mobile-reader-files').click()`);
  await waitFor(`document.querySelector('#folder-modal').hidden === false`);
  await evaluate(`document.querySelector('#folder-modal-close').click();document.querySelector('#mobile-reader-back').click()`);
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-search').value`),'Task 1');
  assert.equal(await evaluate(`document.querySelector('#mobile-reader-filter').value`),'attention');
  assert.equal(await evaluate(`document.activeElement.dataset.runId`),'fixture-0');
  assert.deepEqual(await evaluate(`['orch_slots','orch_layout','orch_tty'].map(k=>localStorage.getItem(k))`),prefs);
  assert.equal(requests.filter(r=>r.path.endsWith('/tty')).length,0,'Reading and Files never attach');
  mode('delay');
  await evaluate(`document.querySelector('#mobile-reader-list button').click()`);
  for(let i=0;i<50&&!delayed();i++) await pause(100);
  assert.ok(delayed());
  await evaluate(`{document.querySelector('#mobile-reader-back').click();const filter=document.querySelector('#mobile-reader-filter');filter.value='all';filter.dispatchEvent(new Event('change'));const q=document.querySelector('#mobile-reader-search');q.value='Task 2';q.dispatchEvent(new Event('input'));document.querySelector('#mobile-reader-list button').click();}`);
  await waitFor(`document.querySelector('#mobile-reader-output').textContent.includes('<literal>')`);
  release(); await pause(100);
  assert.ok(!(await evaluate(`document.querySelector('#mobile-reader-output').textContent`)).includes('WRONG'));
  await evaluate(`document.querySelector('#mobile-reader-back').click()`);
  await evaluate(`document.querySelector('#mobile-reader-list button').click();document.querySelector('#mobile-reader-interact').click()`);
  await waitFor(`document.querySelectorAll('#mobile-reader iframe').length===1`);
  await evaluate(`document.querySelector('#mobile-reader-back').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('#mobile-reader iframe').length`),0);
  assert.equal(requests.some(r=>/\/(send|stop|restart|resume)$/.test(r.path)),false,'Reader never sends or controls session lifecycle');
  await pause(100);
  console.log('PASS: mobile boot, bounded literal output, Files, return, explicit single terminal and desktop preferences');
}
