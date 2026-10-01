'use strict';
const path = require('node:path');
const electron = require('electron');
const { app, BrowserWindow, Menu, ipcMain, dialog } = electron;
const { dashboardURL } = require('./policy.cjs');
const { BrowserHost } = require('./browser-host.cjs');

app.setName('SiLing');
app.setPath('userData', path.join(app.getPath('appData'), 'SiLing Desktop'));
let window;
app.whenReady().then(async () => {
  const dashboard = dashboardURL(process.env.SILING_DASHBOARD_URL || 'http://127.0.0.1:7860/');
  window = new BrowserWindow({ width: 1440, height: 960, minWidth: 800, minHeight: 600,
    title: 'SiLing · 司令', webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'), partition: 'persist:siling-dashboard-v1',
      nodeIntegration: false, contextIsolation: true, sandbox: true,
      webviewTag: false, navigateOnDragDrop: false,
    },
  });
  const host = new BrowserHost(electron, window, dashboard);
  ipcMain.handle('siling:browser', (event, message) => host.request(event, message));
  app.setAboutPanelOptions({ applicationName: 'SiLing · 司令', applicationVersion: app.getVersion(),
    version: `Electron ${process.versions.electron}`, copyright: 'Dashboard version: Settings → About SiLing' });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'SiLing', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] },
    { role: 'windowMenu' },
  ]));
  await window.loadURL(dashboard.href);
}).catch(() => {
  // URLs may include login tokens: do not put the underlying error in logs.
  dialog.showErrorBox('SiLing could not connect',
    'Check SILING_DASHBOARD_URL and that the Dashboard is running. Use its root URL. HTTPS certificates must be trusted by this computer. No service was restarted.');
  app.quit();
});
app.on('window-all-closed', () => app.quit());
