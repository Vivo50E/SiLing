/* Explicit local configuration references; credentials never enter the browser. */
(() => {
  'use strict';
  window.SilingJiraMCP = ({api, ui, changed}) => {
    const box = document.createElement('details');
    box.id = 'jira-mcp-settings';
    box.innerHTML = `<summary data-title></summary><p class="ui-secondary" data-help></p>
      <fieldset><label class="settings-row"><span data-source-label></span><select data-source>
        <option value="local" data-local-option></option><option value="custom" data-custom-option></option></select></label>
      <label class="settings-row" data-custom hidden><span data-file-label></span><input data-file value="~/.claude.json" autocomplete="off"></label>
      <button type="button" data-servers></button>
      <label class="settings-row"><span data-server-label></span><select data-server></select></label>
      <label class="settings-row"><span data-base-label></span><input data-base type="url" placeholder="https://your-team.atlassian.net" autocomplete="off"></label>
      <div class="settings-inline-actions"><button type="button" data-connect></button><button type="button" data-disconnect></button></div></fieldset>
      <p role="status" data-status></p>`;
    document.querySelector('#settings-section-browsing').append(box);
    const el = key => box.querySelector(`[data-${key}]`);
    for (const [key, message] of Object.entries({title:'Jira MCP connection',
      help:'Read existing Codex or Claude Code MCP configuration. Only jira_get_issue is called. Private CLI OAuth sessions are not copied; servers that require them need a supported authentication bridge.',
      'source-label':'Configuration source', 'local-option':'Local Codex / Claude Code', 'custom-option':'Custom configuration file',
      'file-label':'MCP configuration file', servers:'Read servers', 'server-label':'MCP server',
      'base-label':'Jira site URL (optional if JIRA_URL is configured)', connect:'Test & connect', disconnect:'Disconnect'})) ui.setMessage(el(key), message);
    let busy = false, connected = false, revision = 0, localLoaded = false, localServers = [];
    const setBusy = value => {busy = value; box.querySelector('fieldset').disabled = value;};
    const updateSource = () => {
      el('custom').hidden = el('source').value === 'local';
      ui.setMessage(el('servers'), el('source').value === 'local' ? 'Read local MCP servers' : 'Read servers');
    };
    const localOptions = rows => {
      localServers = rows;
      el('server').replaceChildren(...rows.map((server,index)=>new Option(
        `${server.source === 'codex' ? 'Codex' : 'Claude Code'} · ${server.name}`,String(index))));
    };
    const show = cfg => {
      connected = cfg.enabled === true;
      ui.setMessage(el('status'), connected ? 'Jira MCP connected. Tickets are identified when their list loads or refreshes.' : 'Jira MCP disconnected. Saved links remain available.');
      if (connected) {
        el('file').value = cfg.config_file;
        el('source').value = ['codex','claude'].includes(cfg.config_source) ? 'local' : 'custom';
        if (el('source').value === 'local') {
          localOptions([{source:cfg.config_source,config_file:cfg.config_file,name:cfg.server_name}]);
          localLoaded = true;
        } else el('server').replaceChildren(new Option(cfg.server_name, cfg.server_name));
        el('base').value = cfg.base_url;
      }
      updateSource();
      el('disconnect').hidden = !connected;
    };
    const request = (action, body) => api(`/api/jira/mcp/${action}`, {method:'POST',
      headers:{'X-Siling-Jira-MCP':'user-click'}, body});
    const run = async task => {
      if (busy) return;
      revision++;
      setBusy(true); ui.setMessage(el('status'), 'Checking Jira MCP…');
      try {await task();}
      catch {ui.setMessage(el('status'), 'Could not connect. Check the configuration, server authentication and Jira URL.');}
      finally {setBusy(false);}
    };
    const readServers = () => run(async () => {
      const source = el('source').value, file = el('file').value.trim();
      const result = await request(source === 'local' ? 'local-servers' : 'servers', source === 'local' ? {} : {config_file:file});
      if (source !== el('source').value || (source === 'custom' && file !== el('file').value.trim())) return;
      if (source === 'local') {localOptions(result.servers);localLoaded=true;}
      else el('server').replaceChildren(...result.servers.map(server => new Option(server.name, server.name)));
      ui.setMessage(el('status'), result.servers.length ? 'Select the Jira MCP server, then test the connection.' :
        source === 'local' ? 'No local MCP servers found. Use a custom configuration file if needed.' : 'No MCP servers found in this file.');
    });
    el('file').oninput = () => {revision++;el('server').replaceChildren();};
    el('source').onchange = () => {revision++;el('server').replaceChildren();updateSource();if(el('source').value==='local')readServers();};
    el('servers').onclick = readServers;
    box.addEventListener('toggle',()=>{if(box.open && el('source').value==='local' && !localLoaded)readServers();});
    el('connect').onclick = () => run(async () => {
      const native = el('source').value === 'local' ? localServers[Number(el('server').value)] : null;
      if (el('source').value === 'local' && !native) {
        ui.setMessage(el('status'), 'No local MCP servers found. Use a custom configuration file if needed.');return;
      }
      const result = await request('connect', {config_file:native?.config_file || el('file').value.trim(), server_name:native?.name || el('server').value, base_url:el('base').value.trim()});
      if (result.error) {
        ui.setMessage(el('status'), ['auth_required','native_auth_required'].includes(result.error) ?
          'MCP configuration was read, but its authentication cannot be inherited. Use a supported OAuth bridge or configured credentials.' :
          result.error === 'unsupported_tool' ? 'This MCP must expose jira_get_issue with issue_key.' :
          result.error === 'sdk_missing' ? 'Install the Dashboard requirements to enable the MCP client.' :
          'Could not connect. Check the configuration, server authentication and Jira URL.');
      } else {show(result); changed?.();}
    });
    el('disconnect').onclick = () => run(async () => {show(await request('disconnect', {})); changed?.();});
    show({});
    return {async refresh() {
      if (busy) return;
      const current = revision;
      try {const cfg=await api('/api/jira/mcp');if(current===revision && !busy)show(cfg);}
      catch {if(current===revision && !busy)ui.setMessage(el('status'), 'Could not read Jira MCP connection status.');}
    }};
  };
})();
