/* Pane-local credential UI. Never owns or persists credential values. */
(() => {
  function mount(dialog, card, runId) {
    for (const previous of card.querySelectorAll('.pane-secret-card[open]')) previous.close();
    dialog.classList.add('pane-secret-card');
    dialog.setAttribute('aria-modal', 'false');
    card.append(dialog);
    const clear = () => { const input = dialog.querySelector('[data-value]'); if (input) input.value = ''; };
    const valid = () => card.isConnected && dialog.parentElement === card && card.dataset.runId === runId;
    const observer = new MutationObserver(() => {
      if (!valid() || !card.getClientRects().length) {
        clear(); if (dialog.open) dialog.close();
      }
    });
    observer.observe(document.body, {subtree:true, childList:true, attributes:true,
      attributeFilter:['hidden','style','class','data-run-id']});
    // Prevent pane/global shortcuts and paste handlers from seeing form input.
    for (const type of ['keydown','keyup','keypress','paste','copy','cut','pointerdown','click','dblclick']) {
      dialog.addEventListener(type, event => {
        event.stopPropagation();
        if (type === 'keydown' && event.key === 'Escape') {
          event.preventDefault(); clear(); dialog.close();
        }
      });
    }
    dialog.addEventListener('close', () => { clear(); observer.disconnect(); }, {once:true});
    return ({preserveFocus = false} = {}) => {
      if (!valid()) {
        clear(); observer.disconnect(); dialog.dispatchEvent(new Event('close')); return false;
      }
      const active = document.activeElement;
      if (!preserveFocus) card.scrollIntoView({block:'nearest', inline:'nearest'});
      dialog.show();
      if (preserveFocus && active?.isConnected) active.focus({preventScroll:true});
      return true;
    };
  }
  window.SilingSecretInline = {mount};
})();
