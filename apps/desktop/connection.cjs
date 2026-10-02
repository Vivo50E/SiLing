'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomUUID } = require('node:crypto');
const { dashboardURL } = require('./policy.cjs');

const DEFAULT_URL = 'http://127.0.0.1:7860/';
const setupURL = pathToFileURL(path.join(__dirname, 'connection.html')).href;
function readConnection(profile) {
  try { return dashboardURL(JSON.parse(fs.readFileSync(path.join(profile, 'connection.json'), 'utf8')).url).href; }
  catch { return ''; }
}
function writeConnection(profile, value) {
  const url = dashboardURL(value).href;
  fs.mkdirSync(profile, { recursive: true, mode: 0o700 });
  // A fixed app-owned file, never a renderer-selected path. Atomic and private.
  const temporary = path.join(profile, `connection-${randomUUID()}.tmp`);
  const fd = fs.openSync(temporary, 'wx', 0o600);
  try {
    try {
      fs.writeFileSync(fd, JSON.stringify({ url }) + '\n');
      fs.fsyncSync(fd);
    } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, path.join(profile, 'connection.json'));
  } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  return url;
}
function trustedSetup(event, contents) {
  return event.sender === contents && event.senderFrame === contents.mainFrame
    && event.senderFrame.url === setupURL;
}

function connectionDialog(electron, initial = DEFAULT_URL, failed = false) {
  const { BrowserWindow, ipcMain, app } = electron;
  const win = new BrowserWindow({ width: 590, height: 490, resizable: false,
    title: 'SiLing · 司令', backgroundColor: '#0d1117', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'connection-preload.cjs'),
      nodeIntegration: false, sandbox: true, contextIsolation: true, webviewTag: false },
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', event => event.preventDefault());
  const channel = 'siling:connection';
  let complete;
  const result = new Promise(resolve => { complete = resolve; });
  ipcMain.handle(channel, (event, message) => {
    if (!trustedSetup(event, win.webContents)) throw Error('Untrusted connection sender');
    if (message?.action === 'read') return { url: initial, failed, chinese: app.getLocale().startsWith('zh') };
    if (message?.action !== 'save') return { ok: false };
    try {
      const url = writeConnection(app.getPath('userData'), message.url);
      // Let the IPC reply reach the renderer before closing its window.
      setImmediate(() => { complete(url); win.close(); });
      return { ok: true };
    } catch { return { ok: false }; } // Never echo a token-bearing URL or filesystem error.
  });
  win.on('closed', () => { ipcMain.removeHandler(channel); complete(null); });
  win.loadURL(setupURL).catch(() => { complete(null); win.destroy(); });
  return result;
}

module.exports = { DEFAULT_URL, readConnection, writeConnection, trustedSetup, setupURL, connectionDialog };
