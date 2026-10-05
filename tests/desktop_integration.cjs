'use strict';
// Run with Electron. All servers, profile data and pages are isolated fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const electron = require('electron');
const { app, BrowserWindow, ipcMain } = electron;
const { BrowserHost } = require('../apps/desktop/browser-host.cjs');
const { dashboardURL } = require('../apps/desktop/policy.cjs');
const root = path.resolve(__dirname, '..');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-desktop-test-'));
app.setPath('userData', profile);
// Reproducible fixture rendering on CI and Macs with other GPU clients open.
app.disableHardwareAcceleration();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let window, host, dashboardServer, websiteServer, ttyLoads = 0;
const requests = [];
const fixture = { run_id: 'fixture-terminal', agent: 'terminal', kind: 'task', alive: true,
  display_name: 'Isolated terminal fixture', task: 'Fixture', tmux_session: 'fixture-terminal' };
const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`)));
const wait = async (check, label) => {
  for (let i = 0; i < 150; i++) { if (await check()) return; await pause(100); }
  throw Error('Timed out: ' + label);
};
const evaluate = source => window.webContents.executeJavaScript(source, true);
async function sendInput(contents, event, selector = null) {
  // sendInputEvent requires the containing BrowserWindow to be focused.
  // A DOM input.focus() alone does not activate a background CI/test window.
  window.show();
  app.focus({ steal: true });
  window.focus();
  await wait(() => window.isFocused(), 'fixture window focus');
  contents.focus();
  await wait(() => contents.isFocused(), 'native input focus');
  // Activating a macOS window can restore the previous focused control.
  // Focus the fixture field after native window/view activation, then send
  // the actual keyboard event (never assign its value programmatically).
  if (selector) await contents.executeJavaScript(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  contents.sendInputEvent(event);
}

async function run() {
  await app.whenReady();
  dashboardServer = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    requests.push(url.pathname);
    if (url.pathname === '/fixture-tty') {
      ttyLoads++;
      res.setHeader('Content-Type', 'text/html');
      return res.end('<textarea aria-label="Fixture terminal"></textarea>');
    }
    if (url.pathname.startsWith('/api/')) {
      let data = { ok: true };
      if (url.pathname === '/api/health') data = { ttyd: true };
      if (url.pathname === '/api/config') data = { projects_browser_url: '', remote_nodes: [] };
      if (url.pathname === '/api/sessions') data = { sessions: [fixture], snapshot: { ready: true }, pane_groups: { groups: [], members: {} } };
      if (url.pathname.endsWith('/tty')) data = { ok: true, url: '/fixture-tty' };
      res.setHeader('Content-Type', 'application/json');
      return res.end(JSON.stringify(data));
    }
    const file = path.resolve(root, url.pathname === '/' ? 'static/index.html' : url.pathname.slice(1));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.png') ? 'image/png' : 'text/html');
    res.end(fs.readFileSync(file));
  });
  const dashboard = dashboardURL(await listen(dashboardServer) + '/');
  websiteServer = http.createServer((req, res) => {
    if (req.url === '/redirect-dashboard') { res.writeHead(302, { Location: dashboard.href }); return res.end(); }
    if (req.url === '/download') { res.setHeader('Content-Disposition', 'attachment; filename="fixture.txt"'); return res.end('fixture'); }
    if (req.url === '/fail') { req.socket.destroy(); return; }
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Content-Security-Policy', "frame-ancestors 'none'");
    res.setHeader('Content-Type', 'text/html');
    res.end(`<!doctype html><title>Browser fixture ${req.url}</title><body style="background:#202938;color:#eee;font:18px system-ui;padding:28px"><h1>Independent browser pane</h1><p>This page refuses iframe embedding.</p><a href="/second">Next page</a><input aria-label="Web input"><script>window.fixture=true</script></body>`);
  });
  const website = await listen(websiteServer);
  window = new BrowserWindow({ width: 1440, height: 960, show: true, webPreferences: {
    preload: path.join(root, 'apps/desktop/preload.cjs'), partition: 'persist:siling-dashboard-test',
    sandbox: true, contextIsolation: true, nodeIntegration: false,
    // macOS may occlude this fixture while another app is used. Keep the test
    // renderer visible/ticking; production retains normal background throttling.
    backgroundThrottling: false,
  } });
  host = new BrowserHost(electron, window, dashboard);
  ipcMain.handle('siling:browser', (event, message) => host.request(event, message));
  const errors = [];
  window.webContents.on('preload-error', (_event, _path, error) => errors.push(error.message));
  window.webContents.on('console-message', event => {
    if (event.level === 'error') console.error('Fixture renderer:', event.message);
  });
  await window.loadURL(dashboard.href);
  await wait(() => evaluate(`!!document.querySelector('.pane iframe')?.contentDocument?.querySelector('textarea')`), 'terminal ready');
  await evaluate(`document.querySelector('[data-layout="cols-2x2"]').click()`);
  await wait(() => evaluate(`document.querySelectorAll('.new-browser-pane').length === 3`), 'desktop empty slot actions');
  const baseline = ttyLoads;
  await evaluate(`document.querySelector('.pane-input textarea').value='keep my draft'; document.querySelector('.new-browser-pane').click()`);
  await evaluate(`{const input=document.querySelector('.browser-address');input.value=${JSON.stringify(website + '/first?full=query&state=preserved')};input.form.requestSubmit();}`);
  await wait(() => host.panes.size === 1 && [...host.panes.values()][0].view.webContents.getTitle().startsWith('Browser fixture'), 'native website loaded');
  const [id, pane] = [...host.panes][0];
  const web = pane.view.webContents;
  const webId = web.id;
  await wait(() => pane.view.getVisible(), 'native view visible');
  assert.equal(await web.executeJavaScript('window.fixture'), true, 'X-Frame-Options DENY does not block top-level WebContentsView');
  assert.deepEqual(await web.executeJavaScript('[typeof require,typeof process,typeof silingDesktop]'), ['undefined', 'undefined', 'undefined']);
  assert.equal(await evaluate(`typeof document.querySelector('.pane iframe').contentWindow.silingDesktop`), 'undefined');
  await evaluate(`location.href=${JSON.stringify(website + '/')}`);
  await pause(150);
  assert.equal(window.webContents.getURL(), dashboard.href, 'Trusted Dashboard cannot navigate into a website');
  await evaluate(`location.href=location.origin+'/static/preview.html'`);
  await pause(150);
  assert.equal(window.webContents.getURL(), dashboard.href, 'Same-origin file previews cannot inherit the bridge');
  assert.notEqual(web.session, window.webContents.session, 'Website cookie jar is isolated');
  await window.webContents.session.cookies.set({ url: dashboard.href, name: 'fixture_auth', value: 'fixture-only' });
  assert.equal((await web.session.cookies.get({ name: 'fixture_auth' })).length, 0);
  assert.equal(await web.executeJavaScript(`fetch(${JSON.stringify(dashboard.href + 'api/forbidden')}).then(()=>false,()=>true)`), true);
  assert.equal(requests.includes('/api/forbidden'), false, 'No request reaches privileged Dashboard');
  assert.equal(await web.executeJavaScript(`navigator.mediaDevices.getUserMedia({audio:true}).then(()=>false,()=>true)`), true);
  await web.executeJavaScript(`document.querySelector('a').click()`, true);
  await wait(() => web.getURL().endsWith('/second'), 'page link navigation');
  await wait(() => evaluate(`!document.querySelector('[data-browser-action="back"]').disabled`), 'back available');
  await evaluate(`document.querySelector('[data-browser-action="back"]').click()`);
  await wait(() => web.getURL().includes('full=query&state=preserved'), 'history and full query');
  await evaluate(`document.querySelector('[data-browser-action="forward"]').click()`);
  await wait(() => web.getURL().endsWith('/second'), 'forward history');
  await web.executeJavaScript(`location.hash='fixture-hash'`, true);
  await wait(() => evaluate(`document.querySelector('.browser-address').value.endsWith('#fixture-hash')`), 'in-page address updates');
  await web.executeJavaScript(`document.querySelector('input').focus()`);
  await sendInput(web, { type: 'char', keyCode: 'x' }, 'input');
  await wait(() => web.executeJavaScript(`document.querySelector('input').value==='x'`), 'direct typing');
  await evaluate(`document.querySelector('[data-browser-action="zoom"]').click()`);
  await wait(() => pane.view.getBounds().width > 700, 'native zoom bounds');
  await sendInput(web, { type: 'keyDown', keyCode: 'ESC' });
  await wait(() => evaluate(`!document.querySelector('.browser-card').classList.contains('zoomed-pane')`), 'Escape leaves native pane zoom');
  await sendInput(web, { type: 'keyDown', keyCode: 'l', modifiers: ['meta'] });
  await wait(() => evaluate(`document.activeElement.classList.contains('browser-address')`), 'Cmd+L focuses address');
  await evaluate(`document.querySelector('#btn-settings').click()`);
  await wait(() => !pane.view.getVisible(), 'settings obscures native view');
  await evaluate(`document.querySelector('#settings-close').click()`);
  await wait(() => pane.view.getVisible(), 'view restored after dialog');
  const rect = await evaluate(`{const r=document.querySelector('.browser-surface').getBoundingClientRect();({x:r.x,y:r.y,width:r.width,height:r.height})}`);
  assert.ok(Math.abs(pane.view.getBounds().x - rect.x) < 2 && Math.abs(pane.view.getBounds().width - rect.width) < 2, 'Native view tracks grid geometry');
  await evaluate(`document.documentElement.lang='zh'`);
  await wait(() => evaluate(`document.querySelector('.browser-kind').textContent==='浏览器'`), 'Chinese browser controls');
  assert.equal(await evaluate(`document.querySelector('.new-browser-pane').textContent`), '打开浏览器面板');
  await evaluate(`document.documentElement.lang='en'`);
  await evaluate(`{const s=document.querySelector('.browser-move');s.value='2';s.dispatchEvent(new Event('change'));}`);
  assert.equal([...host.panes.values()][0].view.webContents.id, webId, 'Slot swaps preserve native renderer');
  assert.equal(ttyLoads, baseline, 'Browser create, navigation, zoom, settings and swap do not reconnect terminal');
  assert.equal(await evaluate(`document.querySelector('.pane-input textarea').value`), 'keep my draft');
  await evaluate(`document.querySelector('#btn-sort-panes').click()`);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots')).includes(${JSON.stringify(id)})`), true);
  await web.executeJavaScript(`window.open(${JSON.stringify(website + '/popup')})`);
  await wait(() => pane.error.includes('Popup blocked'), 'popup denied');
  await web.executeJavaScript(`location.href=${JSON.stringify(website + '/download')}`, true);
  await wait(() => pane.error.includes('Download blocked'), 'download denied visibly');
  await assert.rejects(host.request({ sender: web, senderFrame: web.mainFrame }, { action: 'sync', panes: [] }), /Untrusted/);
  await assert.rejects(host.request({ sender: window.webContents, senderFrame: window.webContents.mainFrame }, { action: 'navigate', id, url: 'file:///etc/passwd' }));
  await assert.rejects(host.request({ sender: window.webContents, senderFrame: window.webContents.mainFrame }, { action: 'navigate', id, url: dashboard.href }));
  await web.loadURL(website + '/redirect-dashboard').catch(() => {});
  assert.notEqual(web.getURL(), dashboard.href, 'Redirect cannot enter Dashboard');
  await web.loadURL(website + '/fail').catch(() => {});
  await wait(() => pane.error.includes('failed'), 'load failure visible');
  await web.loadURL(website + '/restored');
  await wait(() => evaluate(`JSON.parse(localStorage.getItem('siling_browser_panes_v1'))[0]?.url.endsWith('/restored')`), 'latest address saved');
  await window.loadURL(dashboard.href);
  await wait(() => host.panes.size === 1 && [...host.panes.values()][0].view.webContents.getURL().endsWith('/restored'), 'Dashboard reload restores browser address');
  await wait(() => [...host.panes.values()][0].view.getVisible(), 'restored pane visible');
  const restoredContents = [...host.panes.values()][0].view.webContents;
  await evaluate(`const preference=document.querySelector('#settings-open-links-internally');preference.value='pane';preference.dispatchEvent(new Event('change'));silingOpenWebUrl(${JSON.stringify(website+'/preference')},document.querySelector('.pane iframe').contentWindow)`);
  await evaluate(`{const card=[...document.querySelectorAll('.browser-card')].at(-1);card.querySelector('input').value=${JSON.stringify(website + '/another')};card.querySelector('form').requestSubmit();}`);
  await wait(() => host.panes.size === 2, 'two independent browser panes');
  await evaluate(`[...document.querySelectorAll('.browser-card')].at(-1).querySelector('[data-browser-action="close"]').click()`);
  await wait(() => host.panes.size === 1, 'closing only the second browser');
  assert.equal([...host.panes.values()][0].view.webContents.id, restoredContents.id);
  assert.equal(errors.length, 0, errors.join('\n'));
  if (process.env.DESKTOP_ARTIFACT_DIR) {
    window.show();
    await wait(() => ![...host.panes.values()][0].view.webContents.isLoading(), 'website ready for capture');
    await pause(300);
    fs.mkdirSync(process.env.DESKTOP_ARTIFACT_DIR, { recursive: true });
    fs.writeFileSync(path.join(process.env.DESKTOP_ARTIFACT_DIR, 'desktop-browser.png'), (await window.capturePage()).toPNG());
    // BrowserWindow captures its main renderer, not native child views. Keep
    // the actual website capture separate, never fabricate a composite.
    fs.writeFileSync(path.join(process.env.DESKTOP_ARTIFACT_DIR, 'native-website.png'), (await [...host.panes.values()][0].view.webContents.capturePage()).toPNG());
  }
  await evaluate(`document.querySelector('[data-browser-action="close"]').click()`);
  await wait(() => host.panes.size === 0, 'close releases native view');
  assert.equal(requests.some(url => /\/(kill|stop|restart)$/.test(url)), false, 'No Agent lifecycle mutation');
  console.log('PASS: native browser navigation, isolation, keyboard input, layout, dialogs, restore, errors and Agent preservation');
}

run().then(() => cleanup(0), async error => {
  console.error(error);
  if (window && !window.isDestroyed()) {
    console.error('Fixture state:', await evaluate(`({hidden:document.hidden,panes:[...document.querySelectorAll('.browser-card')].map(n=>({class:n.className,status:n.querySelector('.browser-status').textContent,rect:n.querySelector('.browser-surface').getBoundingClientRect().toJSON()}))})`).catch(() => 'unavailable'));
  }
  cleanup(1);
});
function cleanup(code) {
  host?.clear();
  if (window && !window.isDestroyed()) window.destroy();
  for (const server of [dashboardServer, websiteServer]) { server?.closeAllConnections(); server?.close(); }
  // Only our mkdtemp-created fixture profile; never a user browser profile.
  app.once('quit', () => fs.rmSync(profile, { recursive: true, force: true }));
  app.exit(code);
}
