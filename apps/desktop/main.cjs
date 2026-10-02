'use strict';
const path = require('node:path');
const electron = require('electron');
const { app, BrowserWindow, Menu, ipcMain, dialog } = electron;
const { dashboardURL } = require('./policy.cjs');
const { BrowserHost } = require('./browser-host.cjs');
const { DEFAULT_URL, readConnection, connectionDialog } = require('./connection.cjs');

app.setName('SiLing');
app.setPath('userData', app.commandLine.hasSwitch('user-data-dir')
  ? path.resolve(app.commandLine.getSwitchValue('user-data-dir'))
  : path.join(app.getPath('appData'), 'SiLing Desktop'));
let window, host, connecting = false;

async function connect(initial, choose = false) {
  if (connecting) return;
  connecting = true;
  let value = initial, failed = false;
  try {
    while (true) {
      if (choose) {
        value = await connectionDialog(electron, value || DEFAULT_URL, failed);
        if (!value) return;
      }
      try {
        const dashboard = dashboardURL(value);
        host?.clear();
        ipcMain.removeHandler('siling:browser');
        if (window && !window.isDestroyed()) window.destroy();
        window = new BrowserWindow({ width: 1440, height: 960, minWidth: 800, minHeight: 600,
          title: 'SiLing · 司令', webPreferences: {
            preload: path.join(__dirname, 'preload.cjs'), partition: 'persist:siling-dashboard-v1',
            nodeIntegration: false, contextIsolation: true, sandbox: true,
            webviewTag: false, navigateOnDragDrop: false,
          },
        });
        host = new BrowserHost(electron, window, dashboard);
        ipcMain.handle('siling:browser', (event, message) => host.request(event, message));
        await window.loadURL(dashboard.href);
        return;
      } catch {
        host?.clear();
        ipcMain.removeHandler('siling:browser');
        if (window && !window.isDestroyed()) window.destroy();
        window = null;
        // Recover locally without logging tokens or bypassing certificate checks.
        choose = true;
        failed = true;
      }
    }
  } finally {
    connecting = false;
    if (!window || window.isDestroyed()) app.quit();
  }
}

app.whenReady().then(async () => {
  app.setAboutPanelOptions({ applicationName: 'SiLing · 司令', applicationVersion: app.getVersion(),
    version: `Electron ${process.versions.electron}`, copyright: 'Dashboard version: Settings → About SiLing' });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'SiLing', submenu: [{ role: 'about' }, {
      label: app.getLocale().startsWith('zh') ? 'Dashboard 连接设置…' : 'Dashboard Connection…',
      click: async () => {
        if (connecting) return;
        const zh = app.getLocale().startsWith('zh');
        const { response } = await dialog.showMessageBox(window, { type: 'question',
          message: zh ? '更改连接会重新打开工作台，未保存的网页和输入草稿可能丢失。Agent 不会停止。' : 'Changing connections reopens the workbench. Unsaved web forms and drafts may be lost. Agents keep running.',
          buttons: zh ? ['取消', '继续'] : ['Cancel', 'Continue'], defaultId: 0, cancelId: 0 });
        if (response === 1) await connect(readConnection(app.getPath('userData')) || DEFAULT_URL, true);
      },
    }, { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] },
    { role: 'windowMenu' },
  ]));
  const value = process.env.SILING_DASHBOARD_URL || readConnection(app.getPath('userData'));
  await connect(value || DEFAULT_URL, app.isPackaged && !value);
}).catch(() => {
  // URLs may include login tokens: do not put the underlying error in logs.
  dialog.showErrorBox('SiLing could not connect',
    'Check SILING_DASHBOARD_URL and that the Dashboard is running. Use its root URL. HTTPS certificates must be trusted by this computer. No service was restarted.');
  app.quit();
});
app.on('window-all-closed', () => { if (!connecting) app.quit(); });
