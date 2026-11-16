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
      <div class="settings-inline-actions"><button type="button" data-connect></button><button type="button" data-login></button><button type="button" data-disconnect></button></div></fieldset>
      <button type="button" data-cancel-login hidden></button>
      <label class="settings-row"><span data-topic-label></span><input type="checkbox" data-topic></label>
      <p class="ui-secondary" data-topic-help></p><p role="status" data-status></p>`;
    document.querySelector('#settings-section-browsing').append(box);
    const el = key => box.querySelector(`[data-${key}]`);
    for (const [key, message] of Object.entries({title:'Jira MCP connection',
      help:'One Dashboard Jira connection serves every pane, regardless of its agent. Reads ticket keys and searches task-name keywords. CLI OAuth sessions are separate; importing configuration does not sign in.',
      'source-label':'Configuration source', 'local-option':'Local Codex / Claude Code', 'custom-option':'Custom configuration file',
      'file-label':'MCP configuration file', servers:'Read servers', 'server-label':'MCP server',
      'base-label':'Jira site URL (optional if JIRA_URL is configured)', connect:'Test & connect', login:'Log in with browser', 'cancel-login':'Cancel login', disconnect:'Disconnect'})) ui.setMessage(el(key), message);
    const topicKey = 'siling_jira_topics_v1';
    window.SilingJiraTopics = {enabled() {
      try {return localStorage.getItem(topicKey) === 'true';} catch {return false;}
    }};
    ui.setMessage(el('topic-label'), 'Automatically search Jira by task topic');
    ui.setMessage(el('topic-help'), 'Uses your local Claude CLI’s configured model to understand the task name and up to 2,000 characters of saved initial description. No conversation upload or tools. Up to $0.10 and 25 seconds per analysis; results are cached. Visible active panes check Jira every 10 minutes.');
    el('topic').checked = window.SilingJiraTopics.enabled();
    el('topic').onchange = () => {
      try {localStorage.setItem(topicKey, String(el('topic').checked));} catch {el('topic').checked=false;}
      changed?.();
    };
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
      catch {ui.setMessage(el('status'), 'Could not read the MCP configuration or reach the Dashboard. Check the selected file, server and Dashboard connection.');}
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
        const errors = {
          jira_url_required:'Enter the Jira site URL (for example https://your-team.atlassian.net). This is the Jira website, not the MCP endpoint.',
          invalid_jira_url:'Invalid Jira site URL. Use HTTPS without credentials, query parameters or a fragment.',
          auth_required:'The MCP server requires authentication (401/403). Use Log in with browser on this Mac to authorize Dashboard separately.',
          native_auth_required:'This MCP uses CLI-specific authentication. Configure a supported authenticated MCP connection for Dashboard.',
          timeout:'The MCP server did not respond within the time limit. Check its availability and retry.',
          network_error:'Could not reach the MCP server. Check VPN, DNS, TLS certificates and proxy settings.',
          server_error:'The MCP server returned a server error. Check the service and retry.'
        };
        ui.setMessage(el('status'), errors[result.error] || (
          result.error === 'unsupported_tool' ? 'This MCP must expose jira_get_issue with issue_key.' :
          result.error === 'sdk_missing' ? 'Install the Dashboard requirements to enable the MCP client.' :
          'The MCP handshake failed. Check the service transport and protocol configuration.'));
      } else {show(result); changed?.();}
    });
    const loginErrors = {
      oauth_local_mac_required:'Open Dashboard directly on this Mac to use browser login.',
      keychain_unavailable:'macOS Keychain is unavailable or locked. No plaintext credentials were saved.',
      oauth_not_supported:'Browser login requires an HTTP MCP with supported OAuth discovery and no configured auth headers.',
      oauth_metadata_invalid:'The server OAuth metadata failed validation. Check the MCP service configuration.',
      oauth_registration_denied:'The OAuth server rejected client registration. Your administrator may need to allow SiLing.',
      oauth_scope_unsupported:'The MCP server does not advertise a supported read scope.',
      oauth_token_failed:'OAuth token exchange failed. Check the server policy and retry login.',
      oauth_denied:'Browser authorization was declined. You can retry login.',
      oauth_timeout:'Browser login timed out. Retry and complete authorization within four minutes.',
      unsupported_tool:'Login succeeded, but this MCP must expose jira_get_issue with issue_key.',
      config_changed:'MCP configuration changed during login. Select the server and retry.',
      oauth_busy:'Another Jira login is already running.',
      oauth_failed:'Browser login failed. Check Keychain, the system browser and MCP availability.'
    };
    el('login').onclick = () => run(async () => {
      const native = el('source').value === 'local' ? localServers[Number(el('server').value)] : null;
      if (el('source').value === 'local' && !native) {
        ui.setMessage(el('status'), 'No local MCP servers found. Use a custom configuration file if needed.');return;
      }
      let state=await request('oauth-start',{config_file:native?.config_file || el('file').value.trim(),
        server_name:native?.name || el('server').value,base_url:el('base').value.trim()});
      if(state.error) {ui.setMessage(el('status'),loginErrors[state.error] || loginErrors.oauth_failed);return;}
      const id=state.id;
      el('cancel-login').hidden=false;
      try {
        const deadline=Date.now()+300000;
        while (['starting','waiting','verifying'].includes(state.state) && Date.now()<deadline) {
          ui.setMessage(el('status'),state.state==='verifying' ? 'Authorization received. Verifying Jira tools…' :
            'Complete Jira authorization in the system browser. Closing Settings does not cancel login.');
          await new Promise(resolve=>setTimeout(resolve,1000));
          state=await request('oauth-status',{});
          if(state.id!==id)break;
        }
        if(state.id===id && state.state==='connected') {
          show(await api('/api/jira/mcp'));changed?.();
        } else ui.setMessage(el('status'),state.state==='cancelled' ? 'Jira browser login cancelled.' :
          loginErrors[state.error] || 'Browser login failed. Check Keychain, the system browser and MCP availability.');
      } finally {el('cancel-login').hidden=true;}
    });
    el('cancel-login').onclick=async()=>{
      el('cancel-login').disabled=true;
      try {await request('oauth-cancel',{});}
      catch {ui.setMessage(el('status'),'Could not cancel Jira login. Keep Settings open and retry.');}
      finally {el('cancel-login').disabled=false;}
    };
    el('disconnect').onclick = () => run(async () => {const cfg=await request('disconnect', {});show(cfg);if(cfg.error)ui.setMessage(el('status'),loginErrors[cfg.error] || loginErrors.oauth_failed);changed?.();});
    show({});
    return {async refresh() {
      if (busy) return;
      const current = revision;
      try {const cfg=await api('/api/jira/mcp');if(current===revision && !busy)show(cfg);}
      catch {if(current===revision && !busy)ui.setMessage(el('status'), 'Could not read Jira MCP connection status.');}
    }};
  };
})();
