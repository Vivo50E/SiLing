(() => {
  async function open({api, ui, runId, card}) {
    if (!window.isSecureContext) { alert(ui.message('Secret configuration requires HTTPS or localhost.')); return; }
    if (document.querySelector('.secret-config-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'ui-dialog secret-config-dialog';
    dialog.setAttribute('aria-label', ui.message('Secret configuration'));
    dialog.innerHTML = `
      <div class="modal-head"><h2 data-ui-message="Secret%20configuration">Secret configuration</h2><button type="button" data-close data-ui-label="Close">×</button></div>
      <form class="modal-body" autocomplete="off">
        <p data-target></p>
        <p class="ui-secondary" data-ui-message="Writes%20directly%20to%20backend.env.%20No%20terminal%20input%20or%20agent%20message%20is%20sent.">Writes directly to backend.env. No terminal input or agent message is sent.</p>
        <label><span data-ui-message="Configuration%20destination">Configuration destination</span><select data-destination><option value="node" data-ui-message="This%20pane%27s%20Dashboard%20host">This pane's Dashboard host</option><option value="ssh" data-ui-message="SSH%20host">SSH host</option></select></label>
        <label data-host-label hidden><span data-ui-message="SSH%20alias%20or%20user%40host">SSH alias or user@host</span><input data-host autocomplete="off" spellcheck="false" maxlength="255"></label>
        <label><span data-ui-message="Existing%20absolute%20configuration%20directory">Existing absolute configuration directory</span><input data-directory required autocomplete="off" spellcheck="false" maxlength="4096" placeholder="/absolute/config/directory"></label>
        <p class="ui-secondary" data-ui-message="Only%20backend.env%20is%20written%2C%20with%20owner-only%20permissions.%20Symlinks%20and%20tracked%20or%20unignored%20Git%20files%20are%20rejected.">Only backend.env is written, with owner-only permissions. Symlinks and tracked or unignored Git files are rejected.</p>
        <label><span data-ui-message="Environment%20variable%20name">Environment variable name</span><input data-name required pattern="[A-Za-z_][A-Za-z0-9_]{0,127}" maxlength="128" autocomplete="off" spellcheck="false" placeholder="SLACK_BOT_TOKEN"></label>
        <label><span data-ui-message="Secret%20value">Secret value</span><input data-value type="password" required maxlength="4096" autocomplete="new-password" autocapitalize="off" autocorrect="off" spellcheck="false"></label>
        <p class="ui-secondary" data-ui-message="The%20value%20is%20cleared%20on%20send%2C%20close%20or%20hidden%20tab.%20Never%20enter%20it%20in%20the%20host%2C%20directory%2C%20name%20or%20chat%20fields.">The value is cleared on send, close or hidden tab. Never enter it in the host, directory, name or chat fields.</p>
        <label style="display:flex;gap:8px;margin:12px 0"><input data-confirm type="checkbox" required><span data-ui-message="I%20understand%20backend.env%20stores%20plaintext.%20Agents%20or%20programs%20with%20file%20access%20can%20read%20it%3B%20use%20a%20separate%20account%20or%20host%20for%20isolation.">I understand backend.env stores plaintext. Agents or programs with file access can read it; use a separate account or host for isolation.</span></label>
        <p data-status role="status" aria-live="polite"></p>
        <button type="submit" class="primary" data-submit data-ui-message="Save%20to%20backend.env">Save to backend.env</button>
      </form>`;
    document.body.append(dialog); ui.translate(dialog); ui.containDialogFocus(dialog);
    const el = name => dialog.querySelector(`[data-${name}]`);
    el('target').textContent = card.querySelector('.pane-drag-region')?.textContent.trim() || runId;
    const clear = () => { el('value').value = ''; };
    const hidden = () => { if (document.hidden) clear(); };
    document.addEventListener('visibilitychange', hidden); window.addEventListener('pagehide', clear);
    el('close').onclick = () => { clear(); dialog.close(); };
    dialog.addEventListener('cancel', clear);
    dialog.addEventListener('close', () => {
      clear(); document.removeEventListener('visibilitychange', hidden); window.removeEventListener('pagehide', clear);
      dialog.remove(); if (card.isConnected) card.querySelector('.btn-pane-more').focus({preventScroll:true});
    }, {once:true});
    el('destination').onchange = () => {
      const ssh = el('destination').value === 'ssh';
      el('host-label').hidden = !ssh; el('host').required = ssh;
      el('directory').value = ''; el('host').value = ''; clear(); el('confirm').checked = false;
    };
    for (const name of ['host','directory','name']) el(name).addEventListener('input', () => { el('confirm').checked = false; });
    dialog.querySelector('form').onsubmit = async event => {
      event.preventDefault(); if (el('submit').disabled) return;
      if (!card.isConnected || card.dataset.runId !== runId) { clear(); dialog.close(); return; }
      const spec = {directory:el('directory').value, host:el('destination').value==='ssh'?el('host').value:'',
        name:el('name').value, value:el('value').value, confirm:el('confirm').checked};
      if (!spec.confirm || !spec.value || new TextEncoder().encode(spec.value).length > 4096 || /[\x00-\x1f\x7f$`]/.test(spec.value)) {
        spec.value = ''; clear(); el('status').textContent = ui.message('Enter one line of up to 4096 bytes without controls, dollar signs or backticks'); return;
      }
      clear(); el('submit').disabled = true;
      const controls = [...dialog.querySelectorAll('input,select')]; controls.forEach(control => { control.disabled = true; });
      try {
        await api(`/api/sessions/${encodeURIComponent(runId)}/secret-config`, {method:'POST',body:spec,promptForToken:false,cache:'no-store'});
        if (dialog.isConnected) el('status').textContent = ui.message('Saved to backend.env. No terminal input was sent.');
      } catch (_) {
        if (dialog.isConnected) el('status').textContent = ui.message('Configuration write could not be confirmed. Check the destination before retrying.');
      } finally {
        spec.value = ''; controls.forEach(control => { control.disabled = false; }); el('confirm').checked = false; el('submit').disabled = false;
      }
    };
    dialog.showModal(); el('directory').focus();
  }
  window.SilingSecretConfig = {open};
})();
