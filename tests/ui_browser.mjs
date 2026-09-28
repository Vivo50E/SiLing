// Opt-in full-page browser checks. No dependencies or running Dashboard needed.
// UI_BROWSER=/path/to/chromium node tests/ui_browser.mjs [screenshot-directory]
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { spawn, execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const executable = process.env.UI_BROWSER;
if (!executable) throw Error('Set UI_BROWSER to a Chromium-based browser executable.');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const artifacts = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'siling-ui-artifacts-'));
fs.mkdirSync(artifacts, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-ui-test-'));
const baseline = process.env.UI_BASELINE === '1';
const sessions = ['claude', 'codex', 'terminal', 'cursor', 'custom-agent'].map((agent, i) => ({
  run_id: `fixture-${i}`, kind: 'task', agent, task: `Task ${i + 1} — a long title for narrow panes`,
  display_name: `Task ${i + 1} — a long title for narrow panes`, alive: true,
  tmux_session: `fixture-${i}`, terminal_theme: 'soft-dark', panel_state: i === 0 ? 'p0' : '',
  remote: i === 4, node_id: i === 4 ? 'fixture-remote' : '', node_online: i !== 4,
}));
const requests = [];
let frameLoads = 0;
let pendingCreation;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  requests.push({ method: req.method, path: url.pathname });
  if (url.pathname.startsWith('/fixture-tty/')) {
    frameLoads++;
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><body style="background:#151b24;color:#d9e2ef;font:14px monospace"><pre>Isolated terminal fixture\nNo live session or credentials loaded.</pre><textarea aria-label="Terminal input"></textarea></body>');
  }
  if (url.pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/api/create') { pendingCreation = res; return; }
    let value = { ok: true };
    if (url.pathname === '/api/config') value = { projects_browser_url: '', remote_nodes: [] };
    if (url.pathname === '/api/health') value = { ttyd: true };
    if (url.pathname === '/api/sessions') value = { sessions, snapshot: { ready: true } };
    if (url.pathname === '/api/host') value = { best_url: 'https://dashboard.example/?token=fixture-secret' };
    if (url.pathname.endsWith('/tty')) value = { ok: true, url: '/fixture-tty/' + url.pathname.split('/')[3] };
    return res.end(JSON.stringify(value));
  }
  const relative = url.pathname === '/' ? 'static/index.html' : url.pathname.slice(1);
  if (baseline && relative === 'static/index.html') {
    res.setHeader('Content-Type', 'text/html');
    return res.end(execFileSync('git', ['show', '5de0bdb:static/index.html'], { cwd: root }));
  }
  const target = path.resolve(root, relative);
  if (!target.startsWith(root + path.sep) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
    res.writeHead(404); return res.end();
  }
  res.setHeader('Content-Type', target.endsWith('.svg') ? 'image/svg+xml' : target.endsWith('.css') ? 'text/css' : target.endsWith('.js') ? 'text/javascript' : 'text/html');
  res.end(fs.readFileSync(target));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser, ws;
const errors = [];
try {
  browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run', '--disable-extensions', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
  const activePort = path.join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 100 && !fs.existsSync(activePort); i++) await pause(100);
  const debugPort = fs.readFileSync(activePort, 'utf8').split('\n')[0];
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
  ws = new WebSocket(targets.find(t => t.type === 'page' && t.url === 'about:blank').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
  const pending = new Map();
  let serial = 0;
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    const item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id); clearTimeout(item.timeout);
    message.error ? item.reject(Error(JSON.stringify(message.error))) : item.resolve(message.result);
  });
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timeout = setTimeout(() => { pending.delete(id); reject(Error(`CDP timed out: ${method}`)); }, 12000);
    pending.set(id, { resolve, reject, timeout }); ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, timeout: 8000 });
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const viewport = async (width, height) => {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
    await pause(150);
  };
  const screenshot = async name => {
    const shot = await cdp('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(artifacts, name + '.png'), Buffer.from(shot.data, 'base64'));
  };
  const clickIcon = async selector => {
    const point = await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}+' svg').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
    await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 });
    await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 });
  };
  await cdp('Page.enable'); await cdp('Runtime.enable');
  await viewport(1280, 800);
  await cdp('Page.addScriptToEvaluateOnNewDocument', { source: `if(!localStorage.getItem('orch_layout')){localStorage.setItem('orch_layout','cols-2x2');localStorage.setItem('orch_slots',JSON.stringify(['fixture-0','fixture-1','fixture-2','fixture-3']));localStorage.setItem('siling_appearance_v1',JSON.stringify({language:'en',theme:'dark'}));}` });
  await cdp('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  for (let i = 0; i < 80; i++) {
    if (await evaluate(`document.querySelectorAll('.pane iframe').length === 4`)) break;
    await pause(100);
  }
  assert.equal(await evaluate(`document.querySelectorAll('.pane iframe').length`), 4, JSON.stringify(errors));
  console.log('Dashboard booted with four isolated terminal frames');
  await screenshot('desktop-before-interaction');
  if (baseline) {
    await evaluate(`document.querySelector('#btn-settings').click()`);
    await screenshot('settings-baseline');
    console.log('Baseline screenshots captured');
  } else {
  assert.ok(await evaluate(`(()=>{const e=document.querySelector('.topbar-global');return e.scrollWidth<=e.clientWidth})()`), 'Toolbar must fit at 1280px');
  assert.equal(await evaluate(`document.querySelectorAll('#btn-toggle-tty').length`), 1);
  assert.equal(await evaluate(`document.querySelectorAll('.pane-drag-region .agent-badge').length`), 4);
  assert.ok(await evaluate(`document.querySelector('.brand-mark').naturalWidth > 0`), 'Bundled brand SVG loads');
  assert.equal(await evaluate(`document.querySelectorAll('.pane-drag-region .agent-glyph svg').length`), 4);
  assert.equal(await evaluate(`document.querySelectorAll('.si-agent .agent-glyph svg').length`), 5);
  await evaluate(`document.querySelector('#btn-new-primary').focus()`);
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  assert.equal(await evaluate(`document.activeElement.id`),'btn-search-primary');
  assert.equal(await evaluate(`getComputedStyle(document.activeElement).outlineStyle`),'solid','Keyboard focus stays visible');
  await evaluate(`document.querySelector('#btn-organize').disabled=true`);
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#btn-organize')).cursor`),'not-allowed');
  await evaluate(`document.querySelector('#btn-organize').disabled=false`);
  // Exercise the actual notification handler with isolated permission states.
  await evaluate(`Object.defineProperty(Notification,'permission',{configurable:true,get:()=> 'granted'})`);
  await clickIcon('#btn-notif');
  assert.equal(await evaluate(`document.querySelector('#btn-notif').getAttribute('aria-pressed')`), 'true');
  assert.equal(await evaluate(`document.querySelector('#btn-notif path').getAttribute('d')`), await evaluate(`new DOMParser().parseFromString(SiLingUI.icon('bell'),'text/html').querySelector('path').getAttribute('d')`));
  await clickIcon('#btn-notif');
  await evaluate(`Object.defineProperty(Notification,'permission',{configurable:true,get:()=> 'denied'})`);
  await clickIcon('#btn-notif');
  assert.ok(await evaluate(`document.querySelector('#btn-notif').getAttribute('aria-label').includes('blocked')`));
  assert.equal(await evaluate(`document.querySelector('#btn-notif path').getAttribute('d')`), await evaluate(`new DOMParser().parseFromString(SiLingUI.icon('bellBlocked'),'text/html').querySelector('path').getAttribute('d')`));
  await clickIcon('#btn-notif');
  sessions[0].linked_folders = [{path:'/fixture/report.md',type:'file',label:'Report'}];
  await clickIcon('#btn-refresh');
  for(let i=0;i<50;i++) {
    if(await evaluate(`document.querySelector('[data-run-id="fixture-0"] .btn-folders').textContent==='files 1'`)) break;
    await pause(100);
  }
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-0"] .btn-folders').textContent`),'files 1');
  assert.equal(await evaluate(`document.querySelectorAll('.btn-folders svg').length`),4,'Polling keeps file icons');
  assert.equal(await evaluate(`document.querySelectorAll('#btn-mission-control svg').length`),1,'Polling keeps mission icon');
  const frames = frameLoads;
  await evaluate(`document.querySelector('#btn-search-primary').click();const search=document.querySelector('#sess-search-input');search.value='codex';search.dispatchEvent(new Event('input'));`);
  await pause(150);
  assert.equal(await evaluate(`document.querySelectorAll('.session-item').length`), 1, 'Search filters live sessions by agent');
  await evaluate(`document.querySelector('#sess-search-clear').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('.session-item').length`), 5);
  await evaluate(`document.querySelector('.pane-input textarea').value='preserved draft';document.querySelector('#btn-settings').click();`);
  assert.equal(await evaluate(`document.querySelector('#settings-modal').open`), true);
  await clickIcon('[data-settings-section="terminal"]');
  assert.equal(await evaluate(`document.querySelector('#settings-section-terminal').hidden`),false);
  await clickIcon('[data-settings-section="appearance"]');
  for (let i = 0; i < 18; i++) {
    await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    assert.ok(await evaluate(`document.querySelector('#settings-modal').contains(document.activeElement)`), 'Settings traps keyboard focus');
  }
  await evaluate(`for(const [name,value] of Object.entries({theme:'light',density:'compact',fontSize:'16',motion:'reduce'})){const c=document.querySelector('[data-appearance="'+name+'"]');c.value=value;c.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`getComputedStyle(document.body).backgroundColor`), 'rgb(245, 247, 250)');
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('siling_appearance_v1')).theme`), 'light');
  await evaluate(`window.realSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('full')};const c=document.querySelector('[data-appearance="fontSize"]');c.value='15';c.dispatchEvent(new Event('change'));`);
  assert.ok(await evaluate(`document.querySelector('#settings-save-status').classList.contains('error')`), 'Failed persistence is visible');
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('siling_appearance_v1')).fontSize`), 16, 'Failed save leaves persisted preference intact');
  await evaluate(`{Storage.prototype.setItem=window.realSetItem;const c=document.querySelector('[data-appearance="fontSize"]');c.value='16';c.dispatchEvent(new Event('change'));}`);
  await screenshot('settings-light');
  assert.equal(await evaluate(`document.querySelectorAll('.settings-nav svg').length`),5,'Applying appearance keeps navigation icons');
  await evaluate(`{const c=document.querySelector('[data-appearance="language"]');c.value='zh';c.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`document.querySelector('[data-settings-section="appearance"] span').textContent`),'外观');
  assert.equal(await evaluate(`document.querySelectorAll('.settings-nav svg').length`),5,'Translation keeps icons');
  await evaluate(`{const c=document.querySelector('[data-appearance="language"]');c.value='en';c.dispatchEvent(new Event('change'));}`);
  await evaluate(`{const c=document.querySelector('[data-appearance="theme"]');c.value='system';c.dispatchEvent(new Event('change'));}`);
  for(const [scheme,foreground] of [['dark','rgb(13, 17, 23)'],['light','rgb(255, 255, 255)']]) {
    await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:scheme}]});
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#btn-new-primary')).color`),foreground,'System theme uses readable foreground on primary buttons');
  }
  await evaluate(`{const c=document.querySelector('[data-appearance="theme"]');c.value='light';c.dispatchEvent(new Event('change'));}`);
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  assert.equal(await evaluate(`document.querySelector('#settings-modal').open`), false);
  // Native dialog queues its close event; wait for the registered focus restore.
  for(let i=0;i<50;i++) {
    if(await evaluate(`document.activeElement.id==='btn-settings'`)) break;
    await pause(20);
  }
  assert.equal(await evaluate(`document.activeElement.id`), 'btn-settings');
  assert.equal(await evaluate(`document.querySelector('.pane-input textarea').value`), 'preserved draft');
  assert.equal(frameLoads, frames, 'Appearance must not reload terminal frames');
  await screenshot('desktop-light');
  await evaluate(`document.querySelector('.btn-pane-more').click()`);
  assert.equal(await evaluate(`document.querySelector('.pane-menu').open`), true);
  await screenshot('pane-actions');
  await evaluate(`const move=document.querySelector('.pane-move-select');move.value='1';move.dispatchEvent(new Event('change'));`);
  assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem('orch_slots')).slice(0,2)`), ['fixture-1', 'fixture-0']);
  assert.equal(frameLoads, frames, 'Moving a pane must preserve terminal frames');
  await evaluate(`document.querySelector('.btn-zoom').click()`);
  assert.equal(frameLoads, frames, 'Zoom must preserve terminal frames');
  await evaluate(`document.querySelector('.btn-zoom').click();document.querySelector('#btn-layout-menu').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('#layout-picker button').length`), 10);
  await screenshot('layout-chooser');
  await evaluate(`document.querySelector('#layout-menu').close()`);
  for (const [width, height] of [[1440,900],[768,1024],[390,844],[320,740]]) {
    await viewport(width, height);
    assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), `Page overflow at ${width}`);
    await clickIcon('.btn-pane-more');
    assert.ok(await evaluate(`(()=>{const r=document.querySelector('.pane-menu[open]').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()`), `Menu clipped at ${width}`);
    await screenshot(`pane-menu-${width}`);
    await clickIcon('.pane-menu[open] [data-dialog-close]');
    assert.equal(await evaluate(`!!document.querySelector('.pane-menu[open]')`),false,'Clicking close SVG dismisses dialog');
    await evaluate(`document.querySelector('#btn-settings').click()`);
    assert.ok(await evaluate(`(()=>{const r=document.querySelector('#settings-modal .modal').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()`), `Settings clipped at ${width}`);
    await screenshot(`settings-${width}`);
    await evaluate(`document.querySelector('#settings-close-2').click()`);
  }
  await evaluate(`document.querySelector('.btn-pane-more').click();document.querySelector('.pane-menu[open] .btn-unpin').click()`);
  assert.ok(await evaluate(`!JSON.parse(localStorage.getItem('orch_slots')).includes('fixture-0')`), 'Close pane only unpins');
  assert.deepEqual(requests.filter(r => r.method !== 'GET'), [{ method: 'POST', path: '/api/self-update/fetch' }], 'Only the existing boot-time update fetch is allowed; presentation must not mutate sessions');
  // Hold a real UI request open, fill its intended slot, then return the result.
  await viewport(1280, 800);
  await evaluate(`document.querySelector('[data-run-id="fixture-1"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-1"] .btn-unpin').click();`);
  await evaluate(`document.querySelector('.empty-slot[data-slot="0"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));document.querySelector('#new-agent').value='terminal';document.querySelector('#new-agent').dispatchEvent(new Event('change'));document.querySelector('#new-submit-bg').click();`);
  for (let i=0;i<50&&!pendingCreation;i++) await pause(100);
  assert.ok(pendingCreation, 'Enter on an empty pane can create a session');
  await evaluate(`document.querySelector('#new-close').click();document.querySelector('.session-item[data-id="fixture-1"]').click();`);
  await pause(350); // Sidebar deliberately waits for a possible double-click.
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[0]`), 'fixture-1');
  pendingCreation.end(JSON.stringify({ ok: true, run_id: 'fixture-created' }));
  await pause(200);
  assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem('orch_slots')).slice(0,2)`), ['fixture-1','fixture-created'], 'A delayed create uses another empty pane');
  assert.ok(await evaluate(`document.querySelector('.empty-slot[data-slot="1"]').getAttribute('aria-busy') === 'true'`), 'Reserved pane remains pending before inventory arrives');
  assert.deepEqual(errors, [], 'No uncaught browser errors');
  console.log(JSON.stringify({ result: 'PASS', frameLoads, screenshots: artifacts }));
  }
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close();
}
