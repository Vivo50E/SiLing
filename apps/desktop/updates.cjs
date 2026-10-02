'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
function createUpdater(electron, build, options = {}) {
  const { app, dialog } = electron;
  const launch = options.spawn || spawn;
  const resources = options.resources || process.resourcesPath;
  const host = options.host || path.resolve(path.dirname(process.execPath), '../..');
  const helper = path.join(resources || '', 'SiLingUpdater.app/Contents/MacOS/SiLingUpdater');
  const supported = (options.platform || process.platform) === 'darwin' && app.isPackaged
    && build.updateChannel === 'sparkle' && (options.exists || fs.existsSync)(helper);
  const zh = app.getLocale().startsWith('zh');
  const tr = (en, cn) => zh ? cn : en;
  let child, ready = false, pending = false, stopped = false;
  const unsupported = () => dialog.showMessageBox({
    message: tr('Install the update-enabled SiLing client first', '请先安装支持在线更新的 SiLing 客户端'),
    detail: tr('This build has no Sparkle updater or release public key. Install an update-enabled build once; future updates install inside the app.',
      '此构建未包含 Sparkle 更新组件或发布公钥。首次安装新版客户端后，后续可直接在应用内更新。') });
  function start() {
    if (!supported || child || stopped) return;
    ready = false;
    const proc = launch(helper, [host, String(process.pid)], { stdio: ['pipe', 'pipe', 'ignore'] });
    child = proc;
    let buffer = '';
    const fail = () => {
      if (child !== proc) return;
      const notify = pending;
      child = undefined; ready = false; pending = false;
      if (notify && !stopped) void dialog.showMessageBox({ type: 'error',
        message: tr('Could not start desktop updates. Try again.', '无法启动客户端更新，请重试。') });
    };
    proc.on('error', fail); proc.on('exit', fail);
    proc.stdin.on('error', fail);
    proc.stdout.on('data', data => {
      if (child !== proc) return;
      buffer += data.toString();
      if (buffer.length > 8192) { proc.kill(); fail(); return; }
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index); buffer = buffer.slice(index + 1);
        if (line === '{"event":"ready"}') {
          ready = true;
          if (pending) { pending = false; proc.stdin.write('check\n'); }
        }
      }
    });
  }
  return {
    menu: { id: 'siling-desktop-update', label: tr('Check for Desktop Updates…', '检查客户端更新…'),
      click: async () => {
        if (!supported) { await unsupported(); return; }
        if (stopped) return;
        pending = true; start();
        if (ready && child) { pending = false; child.stdin.write('check\n'); }
      } },
    start,
    dispose() { stopped = true; child?.stdin.end(); },
  };
}
module.exports = { createUpdater };
