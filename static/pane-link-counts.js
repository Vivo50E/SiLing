/* Bounded, once-per-pane discovery; never poll logs or provider CLIs. */
(() => {
  'use strict';
  const cache = new Map(), queue = [];
  let active = 0, request;
  const key = (id, kind) => JSON.stringify([id, kind]);
  function reviewState(items) {
    const states = items.map(item => String(item.state || '').toLowerCase());
    if (states.some(state => ['open', 'opened', 'draft'].includes(state))) return 'open';
    return states.length && states.every(state => state === 'merged') ? 'merged' : '';
  }
  function paint(button, value, state = '') {
    if (state) button.dataset.reviewState = state;
    else delete button.dataset.reviewState;
    let badge = button.querySelector('.pane-link-count');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'pane-link-count';
      button.append(badge);
    }
    badge.textContent = value;
    const zh = document.documentElement.lang.startsWith('zh');
    let description = value === '…' ? (zh ? '正在统计' : 'Counting') : value === '?' ?
      (zh ? '统计失败，打开列表重试' : 'Count unavailable; open list to retry') :
      (zh ? `最近统计：${value}` : `Last count: ${value}`);
    if (state === 'open') description += zh ? ' · 有进行中的 PR/MR' : ' · Has open PRs / MRs';
    if (state === 'merged') description += zh ? ' · 全部已合并' : ' · All PRs / MRs merged';
    badge.title = description;
    button.setAttribute('aria-description', description);
  }
  function display(id, kind, value, state = '') {
    for (const card of document.querySelectorAll('.pane-card[data-run-id]')) {
      if (card.dataset.runId === id) {
        const button = card.querySelector(`.btn-${kind}`);
        if (button) paint(button, value, state);
      }
    }
  }
  function drain() {
    while (active < 2 && queue.length) {
      const {id, kind, entry} = queue.shift();
      if (cache.get(key(id, kind)) !== entry) continue;
      active++;
      request(`/api/sessions/${encodeURIComponent(id)}/${kind}${kind === 'reviews' ? '?branch=false' : '?lookup=true'}`)
        .then(data => {
          if (cache.get(key(id, kind)) !== entry) return;
          entry.value = new Set(data.items.map(item => item.url)).size;
          entry.state = kind === 'reviews' ? reviewState(data.items) : '';
          display(id, kind, entry.value, entry.state);
        }).catch(() => {
          if (cache.get(key(id, kind)) !== entry) return;
          entry.value = '?';
          display(id, kind, '?');
        }).finally(() => { active--; drain(); });
    }
  }
  window.SilingPaneLinkCounts = {
    invalidate(kind) {
      for (const id of cache.keys()) if (JSON.parse(id)[1] === kind) cache.delete(id);
    },
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
        paint(button, entry.value, entry.state);
      }
      drain();
    },
    loaded(id, kind, items) {
      const previous = cache.get(key(id, kind));
      const value = new Set(items.map(item => item.url)).size;
      const state = kind === 'reviews' ? reviewState(items) : '';
      // Replace the entry so a slower initial request cannot overwrite a refresh.
      cache.set(key(id, kind), {...previous, value, state});
      display(id, kind, value, state);
    }
  };
})();
