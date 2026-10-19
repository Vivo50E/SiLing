/* Per-pane remote coding preference. Saving never sends input to a live CLI. */
(() => {
  window.SilingProxyMode = ({ui, api, sessions, restart, canRestart}) => {
    const message = key => ui.message(key);
    const names = {local:'Local execution', devin:'Devin', 'cmux-cloud':'cmux Cloud'};
    const dialog = document.createElement('dialog');
    dialog.id = 'proxy-mode-dialog'; dialog.className = 'ui-dialog';
    dialog.setAttribute('aria-labelledby', 'proxy-mode-heading');
    dialog.innerHTML = `<form class="modal-body"><h2 id="proxy-mode-heading"></h2>
      <p class="proxy-context ui-secondary"></p><label><span class="proxy-label"></span>
      <select class="proxy-select"><option value="local">Local execution</option><option value="devin">Devin</option><option value="cmux-cloud">cmux Cloud</option></select></label>
      <p class="proxy-help ui-secondary"></p><p class="proxy-status" role="status"></p>
      <label class="proxy-restart"><input type="checkbox" style="width:auto" /><span></span></label>
      <p class="proxy-error" role="alert" hidden></p>
      <div class="settings-inline-actions"><button type="button" class="proxy-cancel"></button><button type="submit" class="primary"></button></div></form>`;
    document.body.appendChild(dialog); ui.containDialogFocus(dialog);
    const select = dialog.querySelector('select'), checkbox = dialog.querySelector('input');
    const error = dialog.querySelector('.proxy-error'), submit = dialog.querySelector('[type=submit]');
    let current = '', busy = false, opener, generation = 0, available = null;
    const status = () => {
      const key = select.value;
      dialog.querySelector('.proxy-status').textContent = key === 'local' ? '' :
        available === null ? message('Checking provider tools…') : available[key] ?
          message('Provider tool found. Authentication and repository access are checked by the agent when delegating.') :
          message(key === 'devin' ? 'Install the delegate-to-devin skill on the session host before delegating.' : 'Install cmux and sign in to cmux Cloud on the session host before delegating.');
    };
    select.onchange = status;
    dialog.querySelector('.proxy-cancel').onclick = () => { if (!busy) dialog.close(); };
    dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
    dialog.addEventListener('close', () => { current = ''; generation++; opener?.focus({preventScroll:true}); });
    function decorate(card, row) {
      let badge = card.querySelector('.pane-proxy-badge');
      if (!badge) {
        badge = document.createElement('button'); badge.className = 'pane-proxy-badge';
        badge.style.cssText = 'font-size:10px;flex-shrink:0;padding:1px 5px';
        card.querySelector('.pane-head')?.appendChild(badge);
        badge.onclick = () => open(row.run_id, badge);
      }
      const selected = row.proxy_mode || 'local', applied = row.proxy_mode_applied || 'local';
      const pending = selected !== applied;
      badge.hidden = selected === 'local' && !pending;
      badge.textContent = `${message(names[selected] || selected)}${pending ? ' · ↻' : ''}`;
      badge.title = message(pending ? 'Proxy mode saved; restart or resume to apply' : 'Proxy instructions loaded at launch; remote job status is reported by the agent');
      badge.disabled = !!(row.remote && row.node_online === false);
    }
    async function open(runId, trigger) {
      const row = sessions().find(s => s.run_id === runId);
      if (!row || busy || dialog.open) return;
      current = runId; opener = trigger; const version = ++generation;
      dialog.querySelector('h2').textContent = message('Proxy mode');
      dialog.querySelector('.proxy-context').textContent = row.display_name || row.task || runId;
      dialog.querySelector('.proxy-label').textContent = message('Code execution provider');
      select.options[0].textContent = message('Local execution');
      dialog.querySelector('.proxy-help').textContent = message('The local agent coordinates; code changes and expensive tests go to the remote provider. This is an agent instruction, not a sandbox. Saving applies on the next restart or resume and leaves the current task running.');
      dialog.querySelector('.proxy-restart span').textContent = message('Restart agent after saving (confirmation required)');
      dialog.querySelector('.proxy-cancel').textContent = message('Cancel');
      submit.textContent = message('Save proxy mode');
      checkbox.checked = false; checkbox.disabled = !canRestart(row);
      dialog.querySelector('.proxy-restart').hidden = checkbox.disabled;
      select.value = row.proxy_mode || 'local'; available = null; status();
      error.hidden = true; dialog.showModal(); select.focus();
      const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 10000);
      try {
        const data = await api(`/api/sessions/${encodeURIComponent(runId)}/proxy-mode`, {signal:abort.signal});
        if (generation !== version) return;
        available = data.available || {}; status();
      } catch (err) {
        if (generation === version) { dialog.querySelector('.proxy-status').textContent = message('Provider check failed. You can still save and check the session host.'); }
      } finally { clearTimeout(timeout); }
    }
    dialog.querySelector('form').onsubmit = async event => {
      event.preventDefault(); if (busy || !current) return;
      const id = current, mode = select.value, doRestart = checkbox.checked && !checkbox.disabled;
      busy = true; submit.disabled = true; select.disabled = true; error.hidden = true;
      const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 15000);
      try {
        const data = await api(`/api/sessions/${encodeURIComponent(id)}/proxy-mode`, {method:'POST', body:{mode}, signal:abort.signal});
        if (!data?.ok) throw Error(message('Proxy mode was not saved'));
        const row = sessions().find(s => s.run_id === id);
        if (row) {
          row.proxy_mode = data.proxy_mode; row.proxy_mode_applied = data.proxy_mode_applied;
          document.querySelectorAll('.pane-card').forEach(card => { if (card.dataset.runId === id) decorate(card, row); });
        }
        dialog.close();
        if (doRestart) await restart(id);
      } catch (err) { error.textContent = err.message; error.hidden = false; }
      finally { clearTimeout(timeout); busy = false; submit.disabled = false; select.disabled = false; }
    };
    return {open, decorate};
  };
})();
