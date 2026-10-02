'use strict';
// Test the actual .app, never the user's Dashboard, credentials or app profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { spawn, execFileSync } = require('node:child_process');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const desktopRequire = createRequire(path.join(root, 'apps/desktop/package.json'));
const metadata = desktopRequire('./package.json');
const { RUNTIME_FILES } = desktopRequire('./package-mac.cjs');
const bundle = path.resolve(process.argv[2] || path.join(root, `dist/desktop/SiLing-darwin-${process.arch}/SiLing.app`));
const executable = path.join(bundle, 'Contents/MacOS/SiLing');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-packaged-test-'));
let child, socket, closed, log = '', nextId = 0;
const pending = new Map();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const requests = [];
const server = http.createServer((req, res) => {
  requests.push({ method: req.method, path: new URL(req.url, 'http://localhost').pathname });
  res.setHeader('Content-Type', 'text/html');
  res.end('<!doctype html><title>SiLing packaged fixture</title><h1 id="fixture">Isolated Dashboard</h1>');
});
const website = http.createServer((_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.setHeader('X-Frame-Options', 'DENY');
  res.end('<!doctype html><title>Packaged browser fixture</title><h1 id="website">Independent website</h1>');
});

async function wait(check, label) {
  for (let i = 0; i < 150; i++) {
    if (child?.exitCode !== null && child?.exitCode !== undefined) throw Error('App exited: ' + log);
    try { const value = await check(); if (value) return value; } catch {}
    await pause(100);
  }
  throw Error('Timed out: ' + label + '\n' + log);
}
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timeout = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 10000);
    pending.set(id, { resolve, reject, timeout });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const reply = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  if (reply.exceptionDetails) throw Error('Renderer evaluation failed');
  return reply.result.value;
}
async function attach(urlMatch) {
  socket?.close();
  const port = Number(fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]);
  const target = await wait(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json())
    .find(item => item.type === 'page' && urlMatch(item.url)), 'renderer target');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = event => {
    const message = JSON.parse(event.data), request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id); clearTimeout(request.timeout);
    if (message.error) request.reject(Error(message.error.message)); else request.resolve(message.result);
  };
}
async function start(extraEnv = {}) {
  const activePort = path.join(profile, 'DevToolsActivePort');
  if (fs.existsSync(activePort)) fs.unlinkSync(activePort);
  const env = { ...process.env, ...extraEnv };
  delete env.ELECTRON_RUN_AS_NODE;
  if (!Object.hasOwn(extraEnv, 'SILING_DASHBOARD_URL')) delete env.SILING_DASHBOARD_URL;
  log = '';
  child = spawn(executable, [`--user-data-dir=${profile}`, '--remote-debugging-port=0', '--disable-gpu', '--disable-desktop-updates'], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  closed = new Promise(resolve => child.once('close', resolve));
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  await wait(() => fs.existsSync(activePort), 'debug port');
}
async function stop() {
  socket?.close(); socket = null;
  for (const request of pending.values()) { clearTimeout(request.timeout); request.reject(Error('Fixture stopped')); }
  pending.clear();
  if (child && child.exitCode === null) {
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    await closed;
    clearTimeout(timer);
  }
  child = null;
}
async function screenshot(name) {
  if (!process.env.DESKTOP_ARTIFACT_DIR) return;
  fs.mkdirSync(process.env.DESKTOP_ARTIFACT_DIR, { recursive: true });
  const capture = await command('Page.captureScreenshot');
  fs.writeFileSync(path.join(process.env.DESKTOP_ARTIFACT_DIR, name), Buffer.from(capture.data, 'base64'));
}

async function run() {
  execFileSync('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle], { stdio: 'pipe' });
  const plist = key => execFileSync('/usr/bin/plutil', ['-extract', key, 'raw', '-o', '-', path.join(bundle, 'Contents/Info.plist')], { encoding: 'utf8' }).trim();
  assert.equal(plist('CFBundleName'), 'SiLing');
  assert.equal(plist('CFBundleDisplayName'), 'SiLing');
  assert.equal(plist('CFBundleExecutable'), 'SiLing');
  assert.equal(plist('CFBundleIdentifier'), 'com.vivo50e.siling');
  assert.equal(plist('CFBundleShortVersionString'), metadata.version);
  const { extractFile } = desktopRequire('@electron/asar');
  const packaged = JSON.parse(extractFile(path.join(bundle, 'Contents/Resources/app.asar'), 'package.json'));
  assert.equal(plist('CFBundleVersion'), packaged.buildNumber || metadata.version);
  if (packaged.updateChannel === 'sparkle') {
    const framework = path.join(bundle, 'Contents/Resources/SiLingUpdater.app/Contents/Frameworks/Sparkle.framework');
    assert.equal(fs.readlinkSync(path.join(framework, 'Sparkle')), 'Versions/Current/Sparkle');
    assert.match(plist('SUPublicEDKey'), /^[A-Za-z0-9+/]{43}=$/);
    assert.ok(fs.existsSync(path.join(bundle, 'Contents/Resources/SiLingUpdater.app/Contents/MacOS/SiLingUpdater')));
  }
  const icon = path.join(bundle, 'Contents/Resources', plist('CFBundleIconFile'));
  assert.equal(fs.readFileSync(icon).subarray(0, 4).toString(), 'icns');
  assert.ok(fs.statSync(icon).size > 10000);
  const { listPackage } = desktopRequire('@electron/asar');
  const entries = listPackage(path.join(bundle, 'Contents/Resources/app.asar')).map(file => file.replace(/^\//, '')).sort();
  assert.deepEqual(entries, [...RUNTIME_FILES, 'LICENSE', 'package.json'].sort());
  const helpers = fs.readdirSync(path.join(bundle, 'Contents/Frameworks')).filter(file => file.endsWith('.app'));
  assert.ok(helpers.length > 0 && helpers.every(file => file.startsWith('SiLing Helper')));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  await new Promise(resolve => website.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/?token=fixture-only`;
  const webURL = `http://127.0.0.1:${website.address().port}/`;
  await start();
  await attach(value => value.endsWith('/connection.html'));
  await wait(() => evaluate(`!!document.querySelector('#url').value`), 'setup ready');
  assert.equal(await evaluate('typeof require'), 'undefined');
  assert.equal(await evaluate('typeof silingDesktop'), 'undefined');
  assert.equal(await evaluate(`document.querySelector('#url').type`), 'password');
  await screenshot('packaged-connection.png');
  const invalid = await evaluate(`window.silingConnection.save('http://remote.example/')`);
  assert.equal(invalid.ok, false);
  assert.equal(fs.existsSync(path.join(profile, 'connection.json')), false);
  await evaluate(`document.querySelector('#url').value=${JSON.stringify(url)};document.querySelector('form').requestSubmit();true`);
  await attach(value => value === url);
  await wait(() => evaluate(`!!document.querySelector('#fixture')`), 'Dashboard loaded');
  assert.deepEqual(await evaluate('[typeof require, typeof silingDesktop.request, typeof silingConnection]'), ['undefined', 'function', 'undefined']);
  assert.equal(JSON.parse(fs.readFileSync(path.join(profile, 'connection.json'))).url, url);
  assert.equal(fs.statSync(path.join(profile, 'connection.json')).mode & 0o777, 0o600);
  // Exercise the signed renderer helpers and native WebContentsView in the real bundle.
  await evaluate(`silingDesktop.request({action:'sync',panes:[{id:'browser~fixture',url:${JSON.stringify(webURL)},bounds:{x:20,y:100,width:500,height:350}}]})`);
  await attach(value => value === webURL);
  await wait(() => evaluate(`!!document.querySelector('#website')`), 'packaged native browser');
  assert.deepEqual(await evaluate('[typeof require,typeof silingDesktop,typeof silingConnection]'), ['undefined', 'undefined', 'undefined']);
  await attach(value => value === url);
  await evaluate(`silingDesktop.request({action:'sync',panes:[]})`);
  await stop();
  await start();
  await attach(value => value === url);
  await wait(() => evaluate(`!!document.querySelector('#fixture')`), 'saved connection restored');
  await stop();
  await start({ SILING_DASHBOARD_URL: 'http://remote.example/' });
  await attach(value => value.endsWith('/connection.html'));
  await wait(() => evaluate(`document.querySelector('#status').textContent.length>0`), 'bad connection is recoverable');
  assert.equal(log.includes('fixture-only'), false);
  assert.ok(requests.length > 0);
  assert.equal(requests.some(item => item.method !== 'GET' || /\/(kill|stop|restart)$/.test(item.path)), false);
  console.log('PASS: packaged SiLing identity, icon, version, helpers, exact allowlist, first launch, private save, native browser isolation, restart and failure recovery');
}

run().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  await stop();
  for (const fixture of [server, website]) { fixture.closeAllConnections(); fixture.close(); }
  fs.rmSync(profile, { recursive: true, force: true });
});
