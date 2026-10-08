/* Long session instructions are available on hover, focus or an explicit tap. */
(() => {
  window.SiLingSessionHelp = ({button, panel, visible}) => {
    let pinned = false, timer;
    function close() {
      clearTimeout(timer); pinned = false;
      panel.hidden = true; button.setAttribute('aria-expanded', 'false');
    }
    function position() {
      const anchor = button.getBoundingClientRect(), box = panel.getBoundingClientRect();
      panel.style.left = Math.max(16, Math.min(anchor.right-box.width, innerWidth-box.width-16)) + 'px';
      panel.style.top = Math.max(16, Math.min(anchor.bottom+8, innerHeight-box.height-16)) + 'px';
    }
    function show() {
      clearTimeout(timer);
      if (button.hidden || !visible()) return;
      panel.hidden = false; button.setAttribute('aria-expanded', 'true'); position();
    }
    function leave() {
      if (!pinned && document.activeElement !== button) timer = setTimeout(close, 180);
    }
    button.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') show(); });
    button.addEventListener('pointerleave', leave);
    button.addEventListener('focus', show);
    button.addEventListener('blur', leave);
    button.addEventListener('click', () => {
      if (pinned) close();
      else { pinned = true; show(); }
    });
    panel.addEventListener('pointerenter', () => clearTimeout(timer));
    panel.addEventListener('pointerleave', leave);
    document.addEventListener('pointerdown', event => {
      if (!button.contains(event.target) && !panel.contains(event.target)) close();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !panel.hidden) {
        close(); event.preventDefault(); event.stopImmediatePropagation();
      }
    }, true);
    window.addEventListener('blur', close);
    window.addEventListener('resize', () => { if (!panel.hidden) position(); });
    return {
      close,
      available(value) { button.hidden = !value; if (!value) close(); },
    };
  };
})();
