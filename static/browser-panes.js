/* Desktop-only native views. No Electron APIs are exposed to website content. */
(() => {
  window.SiLingBrowserPanes = function ({ ui, slots, place, clear, setSlot, drag, zoom, unzoom, swap }) {
    const bridge = window.silingDesktop;
    const enabled = bridge?.version === 1;
    const key = 'siling_browser_panes_v1';
    const records = new Map();
    const cards = new Map();
    const zh = () => document.documentElement.lang.startsWith('zh');
    const t = (en, cn) => zh() ? cn : en;
    let lastLayout = '';
    let busy = false;
    let storageError = false;
    const validId = id => typeof id === 'string' && /^browser~[a-zA-Z0-9-]{1,64}$/.test(id);
    if (enabled) {
      try {
        const saved = JSON.parse(localStorage.getItem(key) || '[]');
        if (Array.isArray(saved)) for (const item of saved.slice(0, 16)) {
          if (item && validId(item.id) && typeof item.url === 'string') {
            let url = '';
            try {
              const parsed = new URL(item.url);
              if (['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password
                  && parsed.origin !== location.origin && item.url.length <= 16384) url = parsed.href;
            } catch { /* A corrupt saved address restores as a blank pane. */ }
            records.set(item.id, { id: item.id, url });
          }
        }
      } catch { storageError = true; }
    }
    const isBrowser = id => enabled && records.has(id);
    function save() {
      try { localStorage.setItem(key, JSON.stringify([...records.values()].map(({id, url}) => ({id, url})))); }
      catch { storageError = true; }
    }
    function status(card, value) {
      card.querySelector('.browser-status').textContent = value || (storageError
        ? t('Could not save browser panes on this device', '无法在此设备保存浏览器面板') : '');
    }
    function errorText(value) {
      const known = {
        'Navigation blocked': '已阻止此导航',
        'Popup blocked — use Open externally': '已阻止弹窗，请使用“外部打开”',
        'Download blocked — use Open externally': '已阻止下载，请使用“外部打开”',
        'Page process stopped — reload to retry': '网页进程已停止，请刷新重试',
        'Page failed to load': '网页加载失败',
      };
      return zh() ? (known[value] || (value.startsWith('Page failed to load (') ? value.replace('Page failed to load', '网页加载失败') : value)) : value;
    }
    async function command(id, action, url) {
      const card = cards.get(id);
      if (!card) return;
      try {
        await bridge.request({ id, action, url });
        if (action === 'navigate' && records.has(id)) {
          records.get(id).url = url; save();
          const input = card.querySelector('.browser-address');
          delete input.dataset.editing;
          input.value = url;
        }
      } catch {
        status(card, t('Could not open this address. Use HTTP(S); the Dashboard itself is not allowed.', '无法打开此地址。请使用 HTTP(S)；不允许在此打开 Dashboard 本身。'));
      }
    }
    function makeButton(card, name, en, cn, content, handler) {
      const button = card.querySelector(`[data-browser-action="${name}"]`);
      button.title = t(en, cn);
      button.setAttribute('aria-label', t(en, cn));
      button.innerHTML = content;
      button.onclick = handler;
      return button;
    }
    function label(card, id) {
      const action = name => () => command(id, name);
      makeButton(card, 'back', 'Back', '后退', '←', action('back'));
      makeButton(card, 'forward', 'Forward', '前进', '→', action('forward'));
      makeButton(card, 'reload', 'Reload', '刷新', ui.icon('refresh'), action('reload'));
      makeButton(card, 'stop', 'Stop loading', '停止加载', '■', action('stop'));
      makeButton(card, 'external', 'Open externally', '外部打开', '↗', action('external'));
      makeButton(card, 'zoom', 'Zoom pane', '放大面板', ui.icon('zoom'), () => zoom(card));
      makeButton(card, 'close', 'Close browser pane', '关闭浏览器面板', ui.icon('close'), () => {
        unzoom(card); clear(id);
      });
      card.querySelector('.browser-kind').textContent = t('Browser', '浏览器');
      card.querySelector('.browser-address').setAttribute('aria-label', t('Web address', '网页地址'));
      card.querySelector('.browser-address').placeholder = 'https://…';
      card.querySelector('.browser-go').textContent = t('Go', '前往');
      card.querySelector('.browser-move').title = t('Move / swap with pane', '移动 / 交换面板');
      card.querySelector('.browser-move').setAttribute('aria-label', t('Move / swap with pane', '移动 / 交换面板'));
      card.querySelector('.browser-surface').textContent = t('Enter a web address above. Desktop browser panes stay on this device.', '在上方输入网址。桌面浏览器面板仅保存在此设备。');
      status(card, errorText(records.get(id)?.error || ''));
    }
    function ensure(id, index) {
      if (!isBrowser(id)) return null;
      let card = cards.get(id);
      if (!card) {
        card = document.createElement('div');
        card.className = 'pane-card browser-card';
        card.dataset.runId = id;
        card.dataset.browserId = id;
        card.innerHTML = `<div class="pane-head"><div class="pane-drag-region"><span class="slot-badge"></span><span class="browser-kind"></span><span class="title"></span></div><div class="pane-actions"><select class="browser-move"></select><button data-browser-action="zoom"></button><button data-browser-action="close"></button></div></div>
          <form class="browser-toolbar"><button type="button" data-browser-action="back" disabled></button><button type="button" data-browser-action="forward" disabled></button><button type="button" data-browser-action="reload"></button><button type="button" data-browser-action="stop"></button><input class="browser-address" spellcheck="false" autocomplete="off"><button class="browser-go" type="submit"></button><button type="button" data-browser-action="external"></button></form>
          <div class="browser-status" role="status"></div><div class="browser-surface"></div>`;
        cards.set(id, card);
        card.querySelector('.browser-address').value = records.get(id).url;
        card.querySelector('.browser-address').addEventListener('input', event => {
          event.target.dataset.editing = '1';
        });
        card.querySelector('form').addEventListener('submit', event => {
          event.preventDefault();
          let url = card.querySelector('.browser-address').value.trim();
          if (!/^[a-z][a-z0-9+.-]*:/i.test(url)) url = 'https://' + url;
          void command(id, 'navigate', url);
        });
        card.querySelector('.browser-move').addEventListener('change', event => {
          swap(slots().indexOf(id), Number(event.target.value));
        });
        card.querySelector('.pane-head').addEventListener('dblclick', event => {
          if (!event.target.closest('button, select, input')) zoom(card);
        });
        label(card, id);
        document.getElementById('grid').appendChild(card);
        drag(card);
      }
      setSlot(card, index);
      const select = card.querySelector('.browser-move');
      if (select.options.length !== slots().length) {
        select.replaceChildren(...slots().map((_slot, i) => new Option(String(i + 1), String(i))));
      }
      select.value = String(index);
      return card;
    }
    function reconcile() {
      if (!enabled) return;
      for (const [id, card] of cards) {
        if (!slots().includes(id)) { unzoom(card); card.remove(); cards.delete(id); }
      }
      for (const id of records.keys()) if (!slots().includes(id)) records.delete(id);
      save();
    }
    function add(index) {
      if (!enabled) return;
      const id = 'browser~' + crypto.randomUUID();
      records.set(id, { id, url: '' });
      if (!place(id, index)) { records.delete(id); return; }
      save();
      cards.get(id)?.querySelector('.browser-address').focus();
    }
    function emptyButton(card, index) {
      if (!enabled) return;
      const button = document.createElement('button');
      button.className = 'new-browser-pane';
      button.textContent = t('Open browser pane', '打开浏览器面板');
      button.addEventListener('click', event => { event.stopPropagation(); add(index); });
      button.addEventListener('keydown', event => event.stopPropagation());
      card.querySelector('.empty-slot-inner').appendChild(button);
    }
    async function sync() {
      if (!enabled || busy) return;
      const modal = !!document.querySelector('dialog[open], .modal-scrim:not([hidden]), #grid.drag-active');
      const zoomed = document.querySelector('.zoomed-pane');
      const panes = [...cards].map(([id, card]) => {
        const surface = card.querySelector('.browser-surface');
        const rect = surface.getBoundingClientRect();
        const visible = !modal && !document.hidden && (!zoomed || zoomed === card)
          && !card.classList.contains('group-hidden') && rect.width > 0 && rect.height > 0;
        const probeX = Math.max(0, Math.min(innerWidth - 1, rect.x + rect.width / 2));
        const probeY = Math.max(0, Math.min(innerHeight - 1, rect.y + rect.height / 2));
        const uncovered = visible && document.elementFromPoint(probeX, probeY) === surface;
        return { id, url: records.get(id)?.url || '', zoomed: zoomed === card, bounds: uncovered
          ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null };
      });
      const encoded = JSON.stringify(panes);
      if (encoded === lastLayout) return;
      busy = true;
      try { await bridge.request({ action: 'sync', panes }); lastLayout = encoded; }
      catch { for (const card of cards.values()) status(card, t('Desktop browser unavailable. Check the address or reload the Dashboard.', '桌面浏览器暂不可用，请检查网址或刷新 Dashboard。')); }
      finally { busy = false; }
    }
    if (enabled) {
      bridge.onState(state => {
        const card = cards.get(state.id);
        const record = records.get(state.id);
        if (!card || !record) return;
        if (/^https?:\/\//.test(state.url || '') && state.url !== record.url) {
          record.url = state.url; save();
          const input = card.querySelector('.browser-address');
          if (!input.dataset.editing) input.value = state.url;
        }
        card.querySelector('.title').textContent = state.title || '';
        card.querySelector('.title').title = state.title || '';
        card.querySelector('[data-browser-action="back"]').disabled = !state.back;
        card.querySelector('[data-browser-action="forward"]').disabled = !state.forward;
        record.error = state.error || '';
        status(card, errorText(record.error) || (state.loading ? t('Loading…', '正在加载…') : ''));
        if (state.focusAddress) { card.querySelector('.browser-address').focus(); card.querySelector('.browser-address').select(); }
        if (state.escape) unzoom(card);
      });
      // Native child views sit above HTML. Hide them for dialogs/dragging and
      // reposition without reloading on resize, zoom, scrolling and slot swaps.
      setInterval(sync, 100);
      new MutationObserver(() => { void sync(); }).observe(document.body, {
        subtree: true, attributes: true, attributeFilter: ['hidden', 'open', 'class', 'style'],
      });
      new MutationObserver(() => {
        for (const [id, card] of cards) label(card, id);
        document.querySelectorAll('.new-browser-pane').forEach(button => {
          button.textContent = t('Open browser pane', '打开浏览器面板');
        });
      }).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    }
    return { enabled, isBrowser, ensure, reconcile, emptyButton, add };
  };
})();
