/* Explicit local configuration references; credentials never enter the browser. */
(() => {
  'use strict';
  window.SilingJiraMCP = ({api, ui, changed}) => {
    const box = document.createElement('details');
    box.id = 'jira-mcp-settings';
    box.innerHTML = `<summary data-title></summary><p class="ui-secondary" data-help></p>
      <fieldset><label class="settings-row"><span data-file-label></span><input data-file value="~/.claude.json" autocomplete="off"></label>
      <button type="button" data-servers></button>
      <label class="settings-row"><span data-server-label></span><select data-server></select></label>
      <label class="settings-row"><span data-base-label></span><input data-base type="url" placeholder="https://your-team.atlassian.net" autocomplete="off"></label>
      <div class="settings-inline-actions"><button type="button" data-connect></button><button type="button" data-disconnect></button></div></fieldset>
      <p role="status" data-status></p>`;
    document.querySelector('#settings-section-browsing').append(box);
    const el = key => box.querySelector(`[data-${key}]`);
    for (const [key, message] of Object.entries({title:'Jira MCP connection',
      help:'Reuse a trusted MCP JSON configuration. Only jira_get_issue is called; only ticket keys leave SiLing. OAuth login must already be handled by your MCP server or bridge.',
      'file-label':'MCP configuration file', servers:'Read servers', 'server-label':'MCP server',
      'base-label':'Jira site URL (optional if JIRA_URL is configured)', connect:'Test & connect', disconnect:'Disconnect'})) ui.setMessage(el(key), message);
    let busy = false, connected = false;
    const setBusy = value => {busy = value; box.querySelector('fieldset').disabled = value;};
    const show = cfg => {
      connected = cfg.enabled === true;
      ui.setMessage(el('status'), connected ? 'Jira MCP connected. Tickets are identified when their list loads or refreshes.' : 'Jira MCP disconnected. Saved links remain available.');
      if (connected) {
        el('file').value = cfg.config_file;
        el('server').replaceChildren(new Option(cfg.server_name, cfg.server_name));
        el('base').value = cfg.base_url;
      }
      el('disconnect').hidden = !connected;
    };
    const request = (action, body) => api(`/api/jira/mcp/${action}`, {method:'POST',
      headers:{'X-Siling-Jira-MCP':'user-click'}, body});
    const run = async task => {
      if (busy) return;
      setBusy(true); ui.setMessage(el('status'), 'Checking Jira MCP…');
      try {await task();}
      catch {ui.setMessage(el('status'), 'Could not connect. Check the configuration, server authentication and Jira URL.');}
      finally {setBusy(false);}
    };
    el('file').oninput = () => el('server').replaceChildren();
    el('servers').onclick = () => run(async () => {
      const result = await request('servers', {config_file:el('file').value.trim()});
      el('server').replaceChildren(...result.servers.map(server => new Option(server.name, server.name)));
      ui.setMessage(el('status'), result.servers.length ? 'Select the Jira MCP server, then test the connection.' : 'No MCP servers found in this file.');
    });
    el('connect').onclick = () => run(async () => {
      const result = await request('connect', {config_file:el('file').value.trim(), server_name:el('server').value, base_url:el('base').value.trim()});
      if (result.error) {
        ui.setMessage(el('status'), result.error === 'unsupported_tool' ? 'This MCP must expose jira_get_issue with issue_key.' :
          result.error === 'sdk_missing' ? 'Install the Dashboard requirements to enable the MCP client.' :
          'Could not connect. Check the configuration, server authentication and Jira URL.');
      } else {show(result); changed?.();}
    });
    el('disconnect').onclick = () => run(async () => {show(await request('disconnect', {})); changed?.();});
    show({});
    return {async refresh() {
      if (busy) return;
      try {show(await api('/api/jira/mcp'));}
      catch {ui.setMessage(el('status'), 'Could not read Jira MCP connection status.');}
    }};
  };
})();
