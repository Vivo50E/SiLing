/* New-session choices: shared groups and the selected node's CLI catalog. */
(() => {
  window.SiLingSessionOptions = ({api, message, groups, target, visible}) => {
    const $ = id => document.getElementById(id);
    const choice = $('new-model-choice'), input = $('new-model');
    let key = '', sequence = 0, rows = [], status = '', groupMarkup = '', modelMarkup = '';
    function renderModels() {
      const signature = JSON.stringify([rows, message(status), message('default'), message('Custom model…')]);
      if (signature === modelMarkup) return;
      modelMarkup = signature;
      const selected = choice.value;
      choice.replaceChildren(new Option(message('default'), ''), ...rows.map(row => new Option(`${row.label} · ${row.id}`, row.id)), new Option(message('Custom model…'), '__custom__'));
      choice.value = [...choice.options].some(o => o.value === selected) ? selected : '__custom__';
      if (!input.value) choice.value = '';
      input.hidden = choice.value !== '__custom__';
      $('new-model-status').textContent = message(status);
      $('new-model-refresh').disabled = status === 'Loading models…';
      $('new-model-refresh').textContent = message('Refresh models');
    }
    choice.addEventListener('change', () => {
      input.hidden = choice.value !== '__custom__';
      if (!input.hidden) { input.value = ''; input.focus(); }
      else input.value = choice.value;
    });
    async function load(force = false) {
      if (!visible()) { sequence++; key = ''; return; }
      const context = target();
      const next = JSON.stringify(context);
      if (!force && next === key) { renderModels(); return; }
      const previous = key ? JSON.parse(key) : null;
      if (previous && (previous.agent !== context.agent || previous.node_id !== context.node_id)) { input.value = ''; choice.value = ''; }
      key = next;
      const seq = ++sequence;
      rows = []; status = 'Loading models…'; renderModels();
      try {
        const result = await api('/api/models?' + new URLSearchParams({...context, refresh:String(force)}));
        if (seq !== sequence || !visible()) return;
        rows = Array.isArray(result.models) ? result.models : [];
        status = result.error || !rows.length ? 'Models unavailable. Retry or enter a custom model.' : 'Models reported by the selected CLI; availability depends on its account and provider.';
      } catch (_) {
        if (seq !== sequence || !visible()) return;
        rows = []; status = 'Models unavailable. Retry or enter a custom model.';
      }
      renderModels();
    }
    $('new-model-refresh').addEventListener('click', () => void load(true));
    $('new-cwd').addEventListener('change', () => void load());
    return {
      resetGroup() {
        const data = groups();
        this.update();
        $('new-group').value = data.groups.some(g => g.id === data.filter) ? data.filter : '';
      },
      update() {
        const data = groups(), select = $('new-group');
        const signature = JSON.stringify([data.groups, message('Ungrouped')]);
        if (signature !== groupMarkup) {
          const selected = select.value;
          select.replaceChildren(new Option(message('Ungrouped'), ''), ...data.groups.map(g => new Option(g.name, g.id)));
          select.value = data.groups.some(g => g.id === selected) ? selected : '';
          groupMarkup = signature;
        }
        $('new-group-label').textContent = message('Project group');
        void load();
      },
      close() { sequence++; key = ''; },
    };
  };
})();
