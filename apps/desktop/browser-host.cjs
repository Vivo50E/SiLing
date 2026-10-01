'use strict';
const policy = require('./policy.cjs');

class BrowserHost {
  constructor(electron, window, dashboard) {
    this.electron = electron;
    this.window = window;
    this.dashboard = dashboard;
    this.panes = new Map();
    // The bridge only belongs to this exact Dashboard root, never linked files.
    const guardDashboard = (event, target) => {
      let allowed = false;
      try { const url = new URL(target); allowed = url.origin === dashboard.origin && url.pathname === '/'; } catch {}
      if (!allowed) event.preventDefault();
    };
    window.webContents.on('will-navigate', guardDashboard);
    window.webContents.on('will-redirect', guardDashboard);
    window.webContents.on('will-attach-webview', event => event.preventDefault());
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    this.session = electron.session.fromPartition('persist:siling-web-v1');
    this.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    this.session.setPermissionCheckHandler(() => false);
    // Web pages never receive the Dashboard's cookie jar or access its APIs.
    this.session.webRequest.onBeforeRequest((details, callback) => {
      callback({ cancel: policy.isDashboard(details.url, dashboard) });
    });
    this.session.on('will-download', (event, _item, contents) => {
      event.preventDefault();
      for (const [id, pane] of this.panes) if (pane.view.webContents === contents) {
        pane.error = 'Download blocked — use Open externally'; this.emit(id);
      }
    });
    // A blocked navigation can still emit did-start-navigation. Only a
    // committed main-frame document replaces the trusted UI and its views.
    window.webContents.on('did-navigate', () => this.clear());
    window.webContents.on('render-process-gone', () => this.clear());
    window.on('closed', () => this.clear());
  }

  emit(id, extra = {}) {
    const pane = this.panes.get(id);
    if (!pane || pane.view.webContents.isDestroyed() || this.window.isDestroyed()) return;
    const wc = pane.view.webContents;
    this.window.webContents.send('siling:browser-state', {
      id, url: wc.getURL(), title: wc.getTitle(), loading: wc.isLoading(),
      back: wc.navigationHistory.canGoBack(), forward: wc.navigationHistory.canGoForward(),
      error: pane.error, ...extra,
    });
  }

  create(id, url) {
    const { WebContentsView, Menu } = this.electron;
    const view = new WebContentsView({ webPreferences: {
      session: this.session, nodeIntegration: false, contextIsolation: true,
      sandbox: true, webSecurity: true, allowRunningInsecureContent: false,
      webviewTag: false, navigateOnDragDrop: false,
    } });
    const pane = { view, error: '' };
    this.panes.set(id, pane);
    this.window.contentView.addChildView(view);
    view.setVisible(false);
    const wc = view.webContents;
    const guard = (event, target) => {
      try { policy.browserURL(target, this.dashboard); }
      catch { event.preventDefault(); pane.error = 'Navigation blocked'; this.emit(id); }
    };
    wc.on('will-navigate', guard);
    wc.on('will-redirect', guard);
    wc.on('will-attach-webview', event => event.preventDefault());
    // Initial release deliberately delegates popup-based login to the user's
    // browser, rather than silently granting a website a privileged window.
    wc.setWindowOpenHandler(() => {
      pane.error = 'Popup blocked — use Open externally'; this.emit(id);
      return { action: 'deny' };
    });
    wc.on('context-menu', (_event, params) => {
      Menu.buildFromTemplate([
        { role: 'copy', enabled: !!params.selectionText },
        { role: 'paste', enabled: params.isEditable }, { role: 'selectAll' },
      ]).popup({ window: this.window });
    });
    wc.on('before-input-event', (event, input) => {
      if (input.type !== 'keyDown') return;
      if (((input.meta || input.control) && input.key.toLowerCase() === 'l') || (input.key === 'Escape' && pane.zoomed)) {
        event.preventDefault();
        this.window.webContents.focus();
        this.emit(id, { focusAddress: input.key !== 'Escape', escape: input.key === 'Escape' });
      }
    });
    for (const name of ['did-navigate', 'did-navigate-in-page', 'page-title-updated', 'did-stop-loading']) {
      wc.on(name, () => this.emit(id));
    }
    wc.on('did-start-loading', () => { pane.error = ''; this.emit(id); });
    wc.on('did-fail-load', (_event, code, _description, _url, isMainFrame) => {
      if (isMainFrame && code !== -3) { pane.error = `Page failed to load (${code})`; this.emit(id); }
    });
    wc.on('render-process-gone', () => { pane.error = 'Page process stopped — reload to retry'; this.emit(id); });
    this.load(id, url);
    return pane;
  }

  load(id, url) {
    const pane = this.panes.get(id);
    pane.error = '';
    void pane.view.webContents.loadURL(url).catch(() => {
      if (!pane.error) pane.error = 'Page failed to load';
      this.emit(id);
    });
  }

  remove(id) {
    const pane = this.panes.get(id);
    if (!pane) return;
    this.panes.delete(id);
    if (!this.window.isDestroyed()) this.window.contentView.removeChildView(pane.view);
    if (!pane.view.webContents.isDestroyed()) pane.view.webContents.close({ waitForBeforeUnload: false });
  }

  clear() { for (const id of [...this.panes.keys()]) this.remove(id); }

  async request(event, message) {
    if (!policy.trustedSender(event, this.window.webContents, this.dashboard)) throw Error('Untrusted desktop request');
    if (!message || typeof message !== 'object') throw Error('Invalid desktop request');
    if (message.action === 'external-url') {
      await this.electron.shell.openExternal(policy.browserURL(message.url, this.dashboard));
      return { ok: true };
    }
    if (message.action === 'sync') {
      if (!Array.isArray(message.panes) || message.panes.length > policy.MAX_PANES) throw Error('Too many browser panes');
      const ids = new Set();
      // Validate the entire batch before modifying native views.
      const panes = message.panes.map(item => {
        if (!item || !policy.ID.test(item.id) || ids.has(item.id)) throw Error('Invalid browser pane identity');
        ids.add(item.id);
        return { ...item, url: item.url ? policy.browserURL(item.url, this.dashboard) : '' };
      });
      for (const id of [...this.panes.keys()]) if (!ids.has(id)) this.remove(id);
      const [width, height] = this.window.getContentSize();
      for (const item of panes) {
        const pane = this.panes.get(item.id) || (item.url && this.create(item.id, item.url));
        if (!pane) continue;
        pane.zoomed = item.zoomed === true;
        const rect = policy.bounds(item.bounds, width, height, this.window.webContents.getZoomFactor());
        if (rect) pane.view.setBounds(rect);
        pane.view.setVisible(!!rect);
      }
      return { ok: true };
    }
    if (!policy.ID.test(message.id)) throw Error('Invalid browser pane identity');
    let pane = this.panes.get(message.id);
    if (message.action === 'navigate') {
      const url = policy.browserURL(message.url, this.dashboard);
      if (!pane) {
        if (this.panes.size >= policy.MAX_PANES) throw Error('Too many browser panes');
        pane = this.create(message.id, url);
      } else this.load(message.id, url);
    } else {
      if (!pane) throw Error('Enter an address first');
      const wc = pane.view.webContents;
      if (message.action === 'back' && wc.navigationHistory.canGoBack()) wc.navigationHistory.goBack();
      else if (message.action === 'forward' && wc.navigationHistory.canGoForward()) wc.navigationHistory.goForward();
      else if (message.action === 'reload') wc.reload();
      else if (message.action === 'stop') wc.stop();
      else if (message.action === 'external') {
        await this.electron.shell.openExternal(policy.browserURL(wc.getURL(), this.dashboard));
      } else if (!['back', 'forward'].includes(message.action)) throw Error('Unknown browser action');
    }
    this.emit(message.id);
    return { ok: true };
  }
}

module.exports = { BrowserHost };
