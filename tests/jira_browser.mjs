import assert from 'node:assert/strict';
export async function checkJira({evaluate,waitFor,cdp,viewport,screenshot,requests,pause,mode,configure}) {
  await waitFor(`!!document.querySelector('#session-list .session-item')`);await viewport(1280,900);
  // Stop the preceding Dashboard before replacing shared fixture sessions:
  // its polling/rendering can otherwise rewrite the next case's saved slots.
  const origin=await evaluate('location.origin');
  await cdp('Page.navigate',{url:origin+'/fixture-tty/jira-reset'});
  await waitFor(`location.pathname==='/fixture-tty/jira-reset' && document.readyState==='complete'`);
  configure();
  await evaluate(`localStorage.clear();localStorage.setItem('orch_layout','cols-2');localStorage.setItem('orch_slots',JSON.stringify(['jira-on','jira-off']));localStorage.setItem('siling_web_link_target','external');localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en'}))`);
  await cdp('Page.navigate',{url:origin+'/'});await waitFor(`document.querySelectorAll('#grid iframe').length===2`);
  const on='[data-run-id="jira-on"] .btn-jira',off='[data-run-id="jira-off"] .btn-jira';
  assert.equal(await evaluate(`document.querySelector('${on}').hidden`),true);
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('${on}')).display`),'none');
  assert.equal(requests.some(r=>r.path.endsWith('/jira')),false,'Disabled feature never queries');
  await evaluate(`window.jiraFrames=[...document.querySelectorAll('#grid iframe')];document.querySelector('[data-run-id="jira-on"] textarea').value='jira draft';document.querySelector('#jira-enabled').checked=true;document.querySelector('#jira-enabled').dispatchEvent(new Event('change'));document.querySelector('#btn-pane-groups').click()`);
  await waitFor(`document.querySelector('#pane-groups-dialog').open`);
  await evaluate(`document.querySelector('[data-edit-group="jira-group"]').click()`);
  assert.equal(await evaluate(`document.querySelector('#group-jira-row').hidden`),false);
  assert.equal(await evaluate(`document.querySelector('${on}').hidden`),true,'Master alone does not enable group');
  await evaluate(`document.querySelector('#group-jira-enabled').checked=true;document.querySelector('#group-save').click()`);
  await waitFor(`!document.querySelector('${on}').hidden`);
  assert.equal(await evaluate(`document.querySelector('${off}').hidden`),true,'Other group remains disabled');
  await waitFor(`document.querySelector('${on} .pane-link-count')?.textContent==='1'`);
  await evaluate(`document.querySelector('#pane-groups-dialog').close();document.querySelector('${on}').click()`);
  await waitFor(`document.querySelectorAll('#pane-jira li').length===1`);
  // Configure a referenced MCP server without changing the terminal or exposing credentials.
  await evaluate(`document.querySelector('#pane-jira').close();document.querySelector('#btn-settings').click();document.querySelector('[data-settings-section="browsing"]').click();document.querySelector('#jira-mcp-settings').open=true`);
  await waitFor(`document.querySelector('#jira-mcp-settings [data-status]').textContent.includes('disconnected')`);
  await evaluate(`document.querySelector('#jira-mcp-settings [data-file]').value='/fixture/mcp.json';document.querySelector('#jira-mcp-settings [data-servers]').click()`);
  await waitFor(`document.querySelector('#jira-mcp-settings [data-server]').value==='jira-fixture'`);
  await evaluate(`document.querySelector('#jira-mcp-settings [data-base]').value='https://jira.example';document.querySelector('#jira-mcp-settings [data-connect]').click()`);
  await waitFor(`document.querySelector('#jira-mcp-settings [data-status]').textContent.includes('MCP connected')`);
  await screenshot('jira-mcp-connection');
  await evaluate(`document.querySelector('#settings-close').click();document.querySelector('${on}').click()`);
  await waitFor(`document.querySelector('#pane-jira li small')?.textContent.includes('In Progress · MCP')`);
  for (const [value, message] of [['mcp-error','unavailable'],['changed','Reconnect'],['partial','could not be verified'],['pending','remain']]) {
    mode(value);await evaluate(`document.querySelector('#pane-jira [data-refresh]').click()`);
    await waitFor(`document.querySelector('#pane-jira [data-status]').textContent.includes(${JSON.stringify(message)})`);
    assert.equal(await evaluate(`document.querySelectorAll('#pane-jira li').length`),1,'Provider failures retain saved tickets');
  }
  assert.ok(requests.some(r=>r.path.endsWith('/jira')&&r.search==='?lookup=true&refresh=true'),'Explicit refresh bypasses lookup cache');
  mode('ok');await evaluate(`document.querySelector('#pane-jira [data-refresh]').click()`);
  await waitFor(`!document.querySelector('#pane-jira [data-refresh]').disabled`);
  assert.equal(await evaluate(`!!document.querySelector('#pane-jira img')`),false);
  await screenshot('jira-tickets');
  const count=requests.filter(r=>r.path.endsWith('/jira')).length;await pause(1100);
  assert.equal(requests.filter(r=>r.path.endsWith('/jira')).length,count,'No background polling');
  await evaluate(`document.querySelector('#pane-jira-url').value='https://jira.example/browse/DEMO-13';document.querySelector('#pane-jira form').requestSubmit()`);
  await waitFor(`document.querySelector('#pane-jira-url').value==='' && !document.querySelector('#pane-jira [data-add]').disabled`);
  assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/api/sessions/jira-on/folders').length,1);
  mode('error');await evaluate(`document.querySelector('#pane-jira [data-refresh]').click()`);
  await waitFor(`document.querySelector('#pane-jira [data-status]').textContent.includes('Retry')`);
  mode('empty');await evaluate(`document.querySelector('#pane-jira [data-refresh]').click()`);
  await waitFor(`document.querySelector('#pane-jira [data-status]').textContent.includes('No related')`);
  assert.equal(await evaluate(`document.querySelector('${on} .pane-link-count').textContent`),'0');
  mode('ok');await evaluate(`document.querySelector('#pane-jira [data-refresh]').click()`);
  await waitFor(`document.querySelectorAll('#pane-jira li').length===1`);
  await evaluate(`window.jiraOpen=window.open;window.jiraOpened=[];window.open=(...args)=>jiraOpened.push(args);document.querySelector('#pane-jira a').click()`);
  await waitFor(`jiraOpened.length===1`);assert.equal(await evaluate(`jiraOpened[0][0]`),'https://jira.example/browse/DEMO-12');
  await evaluate(`window.open=jiraOpen;document.querySelector('#jira-enabled').checked=false;document.querySelector('#jira-enabled').dispatchEvent(new Event('change'))`);
  assert.equal(await evaluate(`document.querySelector('${on}').hidden`),true);
  await evaluate(`document.querySelector('#jira-enabled').checked=true;document.querySelector('#jira-enabled').dispatchEvent(new Event('change'))`);
  assert.equal(await evaluate(`document.querySelector('${on}').hidden`),false,'Group preference retained while master disabled');
  assert.equal(await evaluate(`[...document.querySelectorAll('#grid iframe')].every((f,i)=>f===jiraFrames[i])`),true);
  assert.equal(await evaluate(`document.querySelector('[data-run-id="jira-on"] textarea').value`),'jira draft');
  // Opening Settings refreshes the connection asynchronously. Wait for that
  // read before clicking Disconnect, so a late read cannot replace its result.
  await evaluate(`new Promise(resolve=>{const status=document.querySelector('#jira-mcp-settings [data-status]');const observer=new MutationObserver(()=>{observer.disconnect();resolve();});observer.observe(status,{childList:true});document.querySelector('#btn-settings').click();})`);
  await evaluate(`document.querySelector('#jira-mcp-settings [data-disconnect]').click()`);
  await waitFor(`document.querySelector('#jira-mcp-settings [data-status]').textContent.includes('disconnected')`);
  await evaluate(`document.querySelector('#settings-close').click()`);
  await evaluate(`localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'zh'}))`);await cdp('Page.reload');
  await waitFor(`document.querySelector('${on}') && !document.querySelector('${on}').hidden`);
  assert.equal(await evaluate(`document.querySelector('#jira-enabled').checked`),true);
  await viewport(740,900);await evaluate(`document.querySelector('${on}').click()`);
  await waitFor(`document.querySelector('#pane-jira h2')?.textContent==='相关 Jira tickets'`);
  await screenshot('jira-tickets-zh');
  console.log('PASS: Jira master/group opt-in, persistent group preference, scoped icons, on-demand links/add/open/error/empty, bilingual narrow view and iframe/draft preservation');
}
