/* Command approval cards. Values never enter ordinary drafts or browser storage. */
(() => {
  function create({api, ui}) {
    let rows = [], busy = false;
    const dismissed = new Set();
    const stateLabel = state => ui.message(state === 'pending' ? 'Awaiting secret approval' : state);
    const cards = () => [...document.querySelectorAll('.pane-card[data-run-id]')];
    const endpoint = row => `/api/sessions/${encodeURIComponent(row.run_id)}/secret-requests/${row.id}`;
    async function open(card, runId, selected) {
      if (!window.isSecureContext || !card.getClientRects().length) return;
      if (!selected) {
        try { rows = (await api('/api/secret-requests', {promptForToken:false, cache:'no-store'})).requests; }
        catch (_) { return; }
      }
      const own = rows.filter(row => row.run_id === runId);
      let row = selected || own.find(r => r.state === 'pending') || own.at(-1);
      const dialog = document.createElement('dialog');
      dialog.className = 'ui-dialog session-secrets-dialog';
      dialog.setAttribute('aria-label', ui.message('Session secrets'));
      dialog.innerHTML = `<div class="modal-head"><h2 data-ui-message="Session secrets">Session secrets</h2><button type="button" data-close>×</button></div>
        <form class="modal-body" autocomplete="off">
        <details><summary data-ui-message="How keys are protected">How keys are protected</summary><p data-ui-message="Only approve commands you trust. The command can read the secret and access files and network as the Dashboard user.">Only approve commands you trust. The command can read the secret and access files and network as the Dashboard user.</p></details>
        <label><span data-ui-message="Request">Request</span><select data-requests></select></label>
        <button type="button" data-instructions data-ui-message="Copy instructions for agent">Copy instructions for agent</button>
        <p data-reason></p><p data-location></p><pre data-command style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>
        <label><span data-ui-message="Secret source">Secret source</span><select data-source><option value="input" data-ui-message="Enter a secret">Enter a secret</option><option value="session" data-ui-message="Reuse this session's secret">Reuse this session's secret</option><option value="keychain" data-ui-message="Use saved Keychain secret">Use saved Keychain secret</option></select></label>
        <label data-value-label><span data-name></span><input data-value type="password" required autocomplete="new-password" autocapitalize="off" autocorrect="off" spellcheck="false" maxlength="16384"></label>
        <label class="session-secret-save"><input type="checkbox" data-save><span data-ui-message="Save for future sessions in macOS Keychain (this directory and variable)">Save for future sessions in macOS Keychain (this directory and variable)</span></label>
        <p class="ui-secondary" data-ui-message="Default: memory only, one hour, this session. Every command needs approval. Command output is withheld; only exit status returns to the agent.">Default: memory only, one hour, this session. Every command needs approval. Command output is withheld; only exit status returns to the agent.</p>
        <p data-status role="status" aria-live="polite"></p>
        <button type="submit" class="primary" data-approve data-ui-message="Approve and run once">Approve and run once</button>
        <button type="button" data-cancel data-ui-message="Reject / stop command">Reject / stop command</button>
        <button type="button" data-forget data-ui-message="Forget session secret">Forget session secret</button>
        <button type="button" data-delete data-ui-message="Delete saved Keychain secret">Delete saved Keychain secret</button>
        </form>`;
      const show = window.SilingSecretInline.mount(dialog, card, runId);
      ui.translate(dialog);
      const el = name => dialog.querySelector(`[data-${name}]`);
      const clear = () => { el('value').value = ''; };
      const hide = () => { if (document.hidden) clear(); };
      for (const item of own) {
        const option = document.createElement('option'); option.value = item.id;
        option.textContent = `${item.name} · ${stateLabel(item.state)} · ${item.id.slice(0,6)}`;
        el('requests').append(option);
      }
      if (row) el('requests').value = row.id;
      el('requests').parentElement.hidden = own.length < 2;
      const update = () => {
        const pending = row?.state === 'pending';
        el('approve').disabled = !pending;
        el('cancel').disabled = !row || !['pending','running'].includes(row.state);
        el('source').disabled = !pending;
        el('source').querySelector('[value="session"]').disabled = !row?.session_value_available;
        el('source').querySelector('[value="keychain"]').disabled = !row?.keychain_supported;
        el('save').disabled = !pending || !row?.keychain_supported;
        el('forget').disabled = !row?.session_value_available;
        el('delete').disabled = !row?.keychain_supported;
        el('value').disabled = !pending || el('source').value !== 'input';
        el('status').textContent = row ? `${stateLabel(row.state)}${row.exit_code == null ? '' : ` · exit ${row.exit_code}`}` : ui.message('No command requests. Ask the agent to use siling secret request.');
        if (!pending) clear();
      };
      const display = () => {
        clear(); el('save').checked = false; el('source').value = 'input';
        el('name').textContent = row?.name || '';
        el('reason').textContent = row?.reason || '';
        el('location').textContent = row ? `${ui.message('Dashboard host')} · ${row.cwd} · ${row.timeout}s` : '';
        // JSON argv makes argument boundaries explicit without shell interpolation.
        el('command').textContent = row ? JSON.stringify(row.argv) : '';
        update();
      };
      dialog.refreshRequest = list => {
        const latest = list.find(r => r.id === row?.id);
        if (latest) {row = latest; update();}
        else if (row) {row = {...row, state:'expired'}; update();}
      };
      el('requests').onchange = () => {row = own.find(r => r.id === el('requests').value); display();};
      el('source').onchange = () => {clear(); update();};
      el('close').onclick = () => dialog.close();
      el('instructions').onclick = async () => {
        try {
          await navigator.clipboard.writeText('When you need a credential, do not ask me to paste it into chat or a file. Run siling secret request --name ENV_VAR --cwd /absolute/project --reason "Why it is needed" -- /absolute/executable args. Never put the credential in this command. SiLing will ask me to enter it and approve the exact command in a pane card. Check siling secret requests for status. Execution is on the Dashboard host, not inside the existing terminal or SSH shell. Output is withheld; only exit status is returned. Each use requires approval. Do not request arbitrary commands that print, persist or export credentials.');
          el('status').textContent = ui.message('Copied');
        } catch (_) { el('status').textContent = ui.message('Copy failed'); }
      };
      document.addEventListener('visibilitychange', hide); window.addEventListener('pagehide', clear);
      dialog.addEventListener('close', () => {
        clear(); if (row) dismissed.add(row.id);
        document.removeEventListener('visibilitychange', hide); window.removeEventListener('pagehide', clear);
        dialog.remove();
      }, {once:true});
      let submitting = false;
      const act = async (action, body) => {
        if (submitting || !row || !card.isConnected || card.dataset.runId !== runId || !dialog.open) {clear(); return;}
        submitting = true;
        try {
          const data = await api(`${endpoint(row)}/${action}`, {method:'POST', body, promptForToken:false, cache:'no-store', headers:{'X-Siling-User-Intent':'approve-secret'}});
          if (data.request) row = data.request;
          else row = {...row, session_value_available:false};
          if (dialog.isConnected) update();
        } catch (_) {
          if (dialog.isConnected) el('status').textContent = ui.message('Unable to complete action. Check request state or unlock Keychain. No plaintext fallback.');
        } finally {body.value = ''; clear(); submitting = false;}
      };
      dialog.querySelector('form').onsubmit = event => {
        event.preventDefault();
        const body = {source:el('source').value, value:el('value').value, save:el('save').checked};
        clear(); void act('approve', body);
      };
      el('cancel').onclick = () => {clear(); void act('cancel', {});};
      el('forget').onclick = () => {clear(); void act('forget', {});};
      el('delete').onclick = () => {clear(); void act('forget', {saved:true});};
      display(); show({preserveFocus:!!selected});
    }
    async function poll() {
      if (busy || document.hidden) return;
      busy = true;
      try {
        rows = (await api('/api/secret-requests', {promptForToken:false, cache:'no-store'})).requests;
        for (const card of cards()) {
          const existing = card.querySelector('.session-secrets-dialog[open]');
          if (existing) {existing.refreshRequest(rows); continue;}
          if (!card.getClientRects().length || card.querySelector('.pane-secret-card[open]')) continue;
          const row = rows.find(r => r.run_id === card.dataset.runId && r.state === 'pending' && !dismissed.has(r.id));
          if (row) void open(card, row.run_id, row);
        }
        const ids = new Set(rows.map(r => r.id));
        for (const id of dismissed) if (!ids.has(id)) dismissed.delete(id);
      } catch (_) { /* Old/offline Dashboards do not affect terminal input. */ }
      finally {busy = false;}
    }
    return {open, poll};
  }
  window.SilingSessionSecrets = {create};
})();
