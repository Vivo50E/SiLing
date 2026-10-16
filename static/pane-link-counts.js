/* Bounded, once-per-pane discovery; never poll logs or provider CLIs. */
(() => {
  'use strict';
  const cache = new Map(), queue = [];
  let active = 0, request;
  const key = (id, kind) => JSON.stringify([id, kind]);
  function paint(button, value) {
    let badge = button.querySelector('.pane-link-count');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'pane-link-count';
      button.append(badge);
    }
    badge.textContent = value;
    const zh = document.documentElement.lang.startsWith('zh');
    const description = value === '…' ? (zh ? '正在统计' : 'Counting') : value === '?' ?
      (zh ? '统计失败，打开列表重试' : 'Count unavailable; open list to retry') :
      (zh ? `最近统计：${value}` : `Last count: ${value}`);
    badge.title = description;
    button.setAttribute('aria-description', description);
  }
  function display(id, kind, value) {
    for (const card of document.querySelectorAll('.pane-card[data-run-id]')) {
      if (card.dataset.runId === id) {
        const button = card.querySelector(`.btn-${kind}`);
        if (button) paint(button, value);
      }
    }
  }
  function drain() {
    while (active < 2 && queue.length) {
      const {id, kind, entry} = queue.shift();
      active++;
      request(`/api/sessions/${encodeURIComponent(id)}/${kind}${kind === 'reviews' ? '?branch=false' : ''}`)
        .then(data => {
          if (cache.get(key(id, kind)) !== entry) return;
          entry.value = new Set(data.items.map(item => item.url)).size;
          display(id, kind, entry.value);
        }).catch(() => {
          if (cache.get(key(id, kind)) !== entry) return;
          entry.value = '?';
          display(id, kind, '?');
        }).finally(() => { active--; drain(); });
    }
  }
  window.SilingPaneLinkCounts = {
    update(card, row, api) {
      if (api) request = api;
      if (!request) return;
      for (const kind of ['reviews', 'jira']) {
        const button = card.querySelector(`.btn-${kind}`);
        if (!button || button.hidden || button.disabled) continue;
        const fingerprint = JSON.stringify(row.linked_folders || []);
        const id = key(row.run_id, kind);
        let entry = cache.get(id);
        if (!entry || entry.fingerprint !== fingerprint) {
          entry = {fingerprint, value: '…'};
          cache.set(id, entry);
          queue.push({id: row.run_id, kind, entry});
        }
        paint(button, entry.value);
      }
      drain();
    },
    loaded(id, kind, items) {
      const previous = cache.get(key(id, kind));
      const value = new Set(items.map(item => item.url)).size;
      // Replace the entry so a slower initial request cannot overwrite a refresh.
      cache.set(key(id, kind), {...previous, value});
      display(id, kind, value);
    }
  };
})();
