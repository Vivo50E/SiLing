/* Manage volatile credentials without placing values in agent messages. */
(() => {
  'use strict';
  async function open({api, ui, runId, card}) {
    if (!window.isSecureContext) {
      alert(ui.message('Secret operations require HTTPS or localhost.'));
      return;
    }
    if (document.querySelector('.secret-operations-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'ui-dialog secret-operations-dialog';
    dialog.setAttribute('aria-label', ui.message('Secret operations'));
    dialog.innerHTML = `
      <div class="modal-head"><h2 data-ui-message="Secret%20operations">Secret operations</h2><button type="button" data-close data-ui-label="Close">×</button></div>
      <form class="modal-body" autocomplete="off">
        <p data-target></p>
        <p class="ui-secondary" data-ui-message="Credentials%20stay%20in%20SiLing%20memory.%20Agents%20call%20a%20name%3B%20they%20cannot%20read%20the%20key%20or%20change%20its%20fixed%20HTTPS%20operation.%20Response%20bodies%20and%20headers%20are%20withheld.">Credentials stay in SiLing memory. Agents call a name; they cannot read the key or change its fixed HTTPS operation. Response bodies and headers are withheld.</p>
        <label><span data-ui-message="Name">Name</span><input data-name required pattern="[A-Za-z][A-Za-z0-9_\\-]{0,63}" maxlength="64" autocomplete="off"></label>
        <label><span data-ui-message="HTTPS%20endpoint%20(no%20query%20parameters)">HTTPS endpoint (no query parameters)</span><input data-url type="url" required placeholder="https://api.example.com/action" autocomplete="off"></label>
        <label><span data-ui-message="Fixed%20method">Fixed method</span><select data-method><option>GET</option><option>POST</option></select></label>
        <label><span data-ui-message="Authentication">Authentication</span><select data-auth><option value="bearer">Authorization: Bearer</option><option value="api-key">X-API-Key</option></select></label>
        <label><span data-ui-message="API%20key">API key</span><input data-value type="password" required autocomplete="new-password" autocapitalize="off" autocorrect="off" spellcheck="false" maxlength="4096"></label>
        <label><span data-ui-message="Fixed%20POST%20body%20(optional%20JSON)">Fixed POST body (optional JSON)</span><textarea data-body rows="2" maxlength="4096" disabled autocomplete="off" spellcheck="false"></textarea></label>
        <label><span data-ui-message="Lifetime">Lifetime</span><select data-ttl><option value="900" data-ui-message="15%20minutes">15 minutes</option><option value="3600" data-ui-message="1%20hour">1 hour</option></select></label>
        <p class="ui-secondary" data-ui-message="Keys%20expire%20and%20are%20erased%20when%20the%20Dashboard%20stops.%20They%20are%20never%20exported%20to%20agent%20environment%20variables%20or%20saved%20in%20files.">Keys expire and are erased when the Dashboard stops. They are never exported to agent environment variables or saved in files.</p>
        <p class="ui-secondary" data-ui-message="This%20protects%20the%20broker%20API%20boundary%2C%20not%20against%20other%20programs%20with%20your%20OS%20account%20or%20administrator%20access.">This protects the broker API boundary, not against other programs with your OS account or administrator access.</p>
        <p data-status role="status" aria-live="polite"></p>
        <button type="submit" class="primary" data-submit data-ui-message="Register%20operation">Register operation</button>
        <div data-operations></div>
      </form>`;
    document.body.append(dialog); ui.translate(dialog); ui.containDialogFocus(dialog);
    const el = name => dialog.querySelector(`[data-${name}]`);
    el('target').textContent = card.querySelector('.pane-drag-region')?.textContent.trim() || runId;
    const endpoint = `/api/sessions/${encodeURIComponent(runId)}/secret-operations`;
    const clear = () => {el('value').value = '';};
    const hide = () => {if (document.hidden) clear();};
    const error = () => {clear(); el('status').textContent = ui.message('Unable to save or load secret operations. Check the endpoint and session. The key field has been cleared.');};
    const load = async () => {
      try {
        const data = await api(endpoint, {promptForToken:false, cache:'no-store'});
        if (!dialog.isConnected) return;
        el('operations').replaceChildren();
        if (!data.operations.length) {
          const text = document.createElement('p'); text.textContent = ui.message('No active secret operations'); el('operations').append(text);
        }
        for (const operation of data.operations) {
          const row = document.createElement('div'); row.className = 'secret-operation-row';
          const summary = document.createElement('p');
          summary.textContent = `${operation.name} · ${operation.method} ${operation.url} · ${new Date(operation.expires_at*1000).toLocaleTimeString()}`;
          row.append(summary);
          const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = ui.message('Copy call command');
          copy.onclick = async () => {
            // Only server-validated names, never the value, reach clipboard.
            if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(operation.name)) return;
            try {await navigator.clipboard.writeText(`siling secret call ${operation.name}`);} catch (_) {error();}
          };
          const revoke = document.createElement('button'); revoke.type = 'button'; revoke.textContent = ui.message('Revoke');
          revoke.onclick = async () => {
            revoke.disabled = true;
            try {await api(`${endpoint}/${encodeURIComponent(operation.name)}`,{method:'DELETE',promptForToken:false}); await load();}
            catch (_) {error(); revoke.disabled = false;}
          };
          row.append(copy,revoke); el('operations').append(row);
        }
      } catch (_) {if (dialog.isConnected) error();}
    };
    document.addEventListener('visibilitychange', hide); window.addEventListener('pagehide', clear);
    el('close').onclick = () => {clear(); dialog.close();};
    dialog.addEventListener('cancel', clear);
    dialog.addEventListener('close', () => {
      clear(); document.removeEventListener('visibilitychange', hide); window.removeEventListener('pagehide', clear);
      dialog.remove(); if (card.isConnected) card.querySelector('.btn-pane-more').focus({preventScroll:true});
    }, {once:true});
    el('method').onchange = () => {el('body').disabled = el('method').value !== 'POST'; if (el('body').disabled) el('body').value = '';};
    el('submit').onclick = () => {if (!el('value').value) el('status').textContent = '';};
    dialog.querySelector('form').onsubmit = async event => {
      event.preventDefault(); if (el('submit').disabled) return;
      if (!card.isConnected || card.dataset.runId !== runId) {clear(); dialog.close(); return;}
      const spec = {name:el('name').value,url:el('url').value,method:el('method').value,auth:el('auth').value,
        body:el('body').value,value:el('value').value,ttl:Number(el('ttl').value)};
      clear(); el('submit').disabled = true;
      try {
        await api(endpoint,{method:'POST',body:spec,promptForToken:false,cache:'no-store'});
        spec.value = '';
        if (dialog.isConnected) {el('status').textContent = ui.message('Registered. Share only its name or call command with the agent.'); await load();}
      } catch (_) {if (dialog.isConnected) error();}
      finally {spec.value = ''; el('submit').disabled = false;}
    };
    dialog.showModal(); el('name').focus(); await load();
  }
  window.SilingSecretOperations = {open};
})();
