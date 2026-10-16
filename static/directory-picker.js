/* A native chooser only fills a path; it never saves or starts a session. */
(() => {
  'use strict';
  window.SilingDirectoryPicker = ({api, message, button, input, status, available, context, visible}) => {
    let generation = 0, busy = false;
    const update = () => {
      status.hidden = !status.textContent;
      button.dataset.uiMessage = encodeURIComponent(busy ? 'Choosing folder…' : 'Choose folder…');
      button.textContent = message(busy ? 'Choosing folder…' : 'Choose folder…');
      button.disabled = busy || !available();
      const hint = available() ? 'Choose a folder on this Mac' : 'Finder selection is available only for local sessions viewed directly on this Mac. Enter remote paths manually.';
      button.dataset.uiTitle = encodeURIComponent(hint); button.title = message(hint);
    };
    const invalidate = () => {generation++; status.textContent = ''; update();};
    input.addEventListener('input', () => {generation++;});
    button.addEventListener('click', async () => {
      if (busy || !available()) return;
      const seq = ++generation, target = context(), original = input.value;
      busy = true; status.textContent = ''; update();
      try {
        const result = await api('/api/directories/pick', {method:'POST',
          headers:{'X-SiLing-Directory-Pick':'user-click'}, body:{cwd:original}, promptForToken:false});
        if (seq !== generation || context() !== target || !visible() || input.value !== original) return;
        if (result?.cancelled) return;
        if (!result?.ok || typeof result.path !== 'string' || !result.path.startsWith('/')) throw Error();
        input.value = result.path;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        input.dispatchEvent(new Event('change', {bubbles:true}));
      } catch (_) {
        if (seq === generation && context() === target && visible()) status.textContent = message('Unable to choose a folder. Enter the path manually or retry.');
      } finally {busy = false; update();}
    });
    update();
    return {update, invalidate};
  };
})();
