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
const fileDiscoveries = [];
let frameLoads = 0;
let pendingCreation;
let pendingRestart;
const groupFixture = {groups: [], members: {}};
let failGroupSave = false;
let systemBrowserAvailable = false;
let failBrowserOpen = false;
const systemBrowserOpens = [];
const linkedFixtures = new Map();
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  requests.push({ method: req.method, path: url.pathname });
  if (url.pathname.startsWith('/fixture-tty/')) {
    frameLoads++;
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><body style="background:#151b24;color:#d9e2ef;font:14px monospace"><pre>Isolated terminal fixture\nNo live session or credentials loaded.</pre><textarea aria-label="Terminal input"></textarea></body>');
  }
  if (url.pathname.endsWith('/file-context')) {
    const reply=()=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({configured:true,current:{id:'fixture-context',host:'fixture-ssh',cwd:'/remote/work'},settings:{mode:'auto',auto_discover:true},contexts:[{id:'fixture-context',host:'fixture-ssh',cwd:'/remote/work'}]}));};
    if(req.method==='PUT') {req.resume();req.on('end',reply);} else reply();
    return;
  }
  if (url.pathname.endsWith('/discover-files')) {
    let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
      const data=JSON.parse(body);fileDiscoveries.push(data);assert.equal(data.context_id,'fixture-context');assert.equal(data.text,'reports/test.md');
      res.setHeader('Content-Type','application/json');res.end(JSON.stringify({files:[{source_path:'/remote/work/reports/test.md',folder:{path:'/fixture/report.md'}}],errors:[]}));
    });return;
  }
  if (url.pathname.endsWith('/folders') || url.pathname.endsWith('/ssh-file')) {
    const id = url.pathname.split('/')[3];
    res.setHeader('Content-Type','application/json');
    if (req.method === 'POST') {
      let body=''; req.on('data',chunk=>body+=chunk); req.on('end',()=>{
        const value=JSON.parse(body);
        if (url.pathname.endsWith("/ssh-file")) { assert.equal(value.host,"fixture-ssh"); assert.equal(value.path,"/remote/artifact.png"); value.path="/fixture/ssh-preview.png"; }
        const folder={path:value.path,label:value.label,type:'file',exists:true,allowed:true,
          entries:[{rel:'',name:'artifact.png',type:'file',previewable:true}],loaded_dirs:['']};
        linkedFixtures.set(id,[folder]);res.end(JSON.stringify({ok:true,folder}));
      });
      return;
    }
    return res.end(JSON.stringify({folders:linkedFixtures.get(id)||[]}));
  }
  if (url.pathname.endsWith('/folders/file/raw')) {
    res.setHeader('Content-Type','image/png');
    return res.end(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64'));
  }
  if (url.pathname.endsWith('/folders/file')) {
    res.setHeader('Content-Type','application/json');
    return res.end(JSON.stringify({ok:true,kind:'markdown',name:'report.md',path:'/fixture/report.md',content:'# Readable Markdown\n\nAn isolated preview fixture.'}));
  }
  if (url.pathname.endsWith('/pane')) {
    res.setHeader('Content-Type', 'text/plain');
    return res.end(Array.from({length: 300}, (_, i) => `history-${i} <literal>`).join('\n'));
  }
  if (url.pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/api/browser/open') {
      let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
        assert.equal(req.headers['x-siling-browser-open'],'user-click');
        systemBrowserOpens.push(JSON.parse(body).url);
        if(failBrowserOpen) res.writeHead(503);
        res.end(JSON.stringify(failBrowserOpen?{detail:'Fixture system open failed'}:{ok:true}));
      });
      return;
    }
    if (url.pathname === '/api/pane-groups') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', () => {
        if (failGroupSave) { res.writeHead(503); res.end(JSON.stringify({detail:'Fixture save failed'})); return; }
        const edit = JSON.parse(body);
        if (edit.action === 'create') groupFixture.groups.push({id:'project-fixture', name:edit.name, color:edit.color});
        if (edit.action === 'update') Object.assign(groupFixture.groups.find(g => g.id === edit.group_id), {name:edit.name, color:edit.color});
        if (edit.action === 'assign') for (const id of edit.run_ids) groupFixture.members[id] = edit.group_id;
        if (edit.action === 'delete') {
          groupFixture.groups = groupFixture.groups.filter(g => g.id !== edit.group_id);
          for (const id of Object.keys(groupFixture.members)) if (groupFixture.members[id] === edit.group_id) groupFixture.members[id] = '';
        }
        res.end(JSON.stringify({ok:true}));
      });
      return;
    }
    if (url.pathname === '/api/create') { pendingCreation = res; return; }
    if (url.pathname.endsWith('/restart')) { pendingRestart = res; return; }
    let value = { ok: true };
    if (url.pathname === '/api/config') value = { projects_browser_url: '', remote_nodes: [], system_browser_available: systemBrowserAvailable };
    if (url.pathname === '/api/health') value = { ttyd: true };
    if (url.pathname === '/api/sessions') value = { sessions, snapshot: { ready: true }, pane_groups: groupFixture };
    if (url.pathname === '/api/host') value = { best_url: 'https://dashboard.example/?token=fixture-secret' };
    if (url.pathname.endsWith('/tty')) value = { ok: true, selection_copy: url.pathname.includes('/fixture-1/') ? undefined : true, url: '/fixture-tty/' + url.pathname.split('/')[3] };
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
  if (!baseline) {
    const groupFrames = frameLoads;
    const oldSlots = await evaluate(`localStorage.getItem('orch_slots')`);
    const waitFor = async expression => {
      for (let i=0; i<100; i++) { if (await evaluate(expression)) return; await pause(100); }
      assert.fail('Timed out: ' + expression);
    };
    await waitFor(`Array.from(document.querySelectorAll('.pane iframe')).every(f=>f.contentDocument?.querySelector('textarea'))`);
    const newlineResults = await evaluate(`(()=>{
      return ['fixture-0','fixture-1','fixture-2','fixture-3'].map(id=>{
        const frame=document.querySelector('[data-run-id="'+id+'"] iframe');
        const input=frame.contentDocument.querySelector('textarea');
        input.classList.add('xterm-helper-textarea');
        const sent=[];frame.contentWindow.term={input:(data,user)=>sent.push([data,user])};
        const press=extra=>input.dispatchEvent(new frame.contentWindow.KeyboardEvent('keydown',
          {key:'Enter',shiftKey:true,bubbles:true,cancelable:true,...extra}));
        const native=press({});
        const ordinary=press({shiftKey:false});
        const composing=press({isComposing:true});
        delete frame.contentWindow.term;
        return {id,sent,native,ordinary,composing};
      });
    })()`);
    assert.deepEqual(newlineResults, [
      {id:'fixture-0',sent:[['\n',true]],native:false,ordinary:true,composing:true},
      {id:'fixture-1',sent:[['\x1b[200~\n\x1b[201~',true]],native:false,ordinary:true,composing:true},
      {id:'fixture-2',sent:[],native:true,ordinary:true,composing:true},
      {id:'fixture-3',sent:[['\n',true]],native:false,ordinary:true,composing:true},
    ], 'Dashboard installs agent-specific newline routing inside each iframe');
    console.log('PASS: iframe Shift+Enter routing, native Enter, IME and plain Terminal behavior');
    const deviceUrl='https://example.invalid/device?state=unchanged&code=fixture';
    assert.equal(await evaluate(`(()=>{const original=window.open;const opened=[];window.open=url=>opened.push(url);try {
      silingOpenWebUrl(${JSON.stringify(deviceUrl)},document.querySelector('.pane iframe').contentWindow);
      return opened[0];
    }finally{window.open=original;}})()`),deviceUrl,'Remote capability opens on the viewing device');
    assert.equal(systemBrowserOpens.length,0,'Remote/phone view never calls host opener');
    await evaluate(`document.querySelector('[data-run-id="fixture-0"] .pane-input textarea').value='group draft';document.querySelector('#btn-pane-groups').click();document.querySelector('#group-name').value='Project <A>';document.querySelector('#group-name').dispatchEvent(new Event('input'))`);
    assert.equal(await evaluate(`document.querySelectorAll('#group-palette [data-color]').length`),12);
    await evaluate(`document.querySelector('#group-palette [data-color="#edb84d"]').click()`);
    assert.equal(await evaluate(`document.querySelector('#group-color').value`),'#edb84d');
    assert.equal(await evaluate(`document.querySelector('#group-palette [data-color="#edb84d"]').getAttribute('aria-pressed')`),'true');
    await evaluate(`document.querySelector('#group-color').value='#12abef';document.querySelector('#group-color').dispatchEvent(new Event('input'))`);
    assert.equal(await evaluate(`document.querySelector('#group-hex').value`),'#12abef');
    await evaluate(`document.querySelector('#group-hex').value='#GGGGGG';document.querySelector('#group-hex').dispatchEvent(new Event('input'));document.querySelector('#group-save').click()`);
    assert.equal(groupFixture.groups.length,0,'Invalid hex is blocked before any write');
    await evaluate(`document.querySelector('#group-hex').value='#12AbEf';document.querySelector('#group-hex').dispatchEvent(new Event('input'))`);
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#group-preview .group-dot')).backgroundColor`),'rgb(18, 171, 239)');
    assert.equal(await evaluate(`document.querySelector('#group-preview span').textContent`),'Project <A>','Preview escapes names');
    await screenshot('project-groups-color-preview');
    await evaluate(`document.querySelector('#group-save').click()`);
    await waitFor(`document.querySelector('[data-group-filter="project-fixture"]') !== null`);
    assert.equal(groupFixture.groups[0].color,'#12abef');
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('[data-edit-group="project-fixture"] .group-dot')).backgroundColor`),'rgb(18, 171, 239)');
    await evaluate(`document.querySelector('.group-assignment summary').focus()`);
    await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
    await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    assert.equal(await evaluate(`document.querySelector('.group-assignment').open`),true);
    await evaluate(`document.querySelector('#group-select-all').click()`);
    assert.equal(await evaluate(`document.querySelectorAll('#group-session-list input:checked').length`),sessions.filter(s=>s.alive).length);
    await evaluate(`document.querySelector('#group-select-none').click()`);
    assert.equal(await evaluate(`document.querySelector('#group-assign').disabled`),true);
    await evaluate(`document.querySelector('#group-session-list input[value="fixture-0"]').click();document.querySelector('#group-session-list input[value="fixture-1"]').click();document.querySelector('#group-target').value='project-fixture';document.querySelector('#group-target').dispatchEvent(new Event('change'));document.querySelector('#group-assign').click()`);
    await waitFor(`document.querySelector('[data-run-id="fixture-0"] .pane-group-badge').textContent==='Project <A>'`);
    await evaluate(`document.querySelector('#pane-groups-dialog').close();document.querySelector('[data-group-filter="project-fixture"]').click()`);
    assert.equal(await evaluate(`document.querySelectorAll('#grid .pane-card.group-hidden').length`), 2);
    assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-2"]').inert`), true);
    assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-0"] .pane-input textarea').value`), 'group draft');
    assert.equal(await evaluate(`localStorage.getItem('orch_slots')`), oldSlots);
    assert.equal(frameLoads, groupFrames, 'Filtering never reloads a terminal iframe');
    assert.ok(await evaluate(`(()=>{const bar=document.querySelector('#pane-group-bar').getBoundingClientRect();const main=document.querySelector('.main').getBoundingClientRect();return bar.right<=main.right+1&&bar.left>=main.left&&bar.top>=document.querySelector('.topbar-global').getBoundingClientRect().bottom-1})()`), 'Group bar occupies its own row within the workbench');
    await screenshot('project-group-filter');
    await evaluate(`document.querySelector('[data-group-filter="ungrouped"]').click();document.querySelector('[data-group-filter="all"]').click()`);
    assert.equal(await evaluate(`document.querySelectorAll('#grid .pane-card.group-hidden').length`), 0);
    await evaluate(`document.querySelector('[data-run-id="fixture-2"] .btn-pane-more').click();const gs=document.querySelector('[data-run-id="fixture-2"] .pane-group-select');gs.value='project-fixture';gs.dispatchEvent(new Event('change'))`);
    await waitFor(`document.querySelector('[data-run-id="fixture-2"] .pane-group-badge').textContent==='Project <A>'`);
    await evaluate(`document.querySelector('[data-run-id="fixture-2"] .pane-menu').close();document.querySelector('#btn-pane-groups').click();document.querySelector('[data-edit-group="project-fixture"]').click();document.querySelector('#group-name').value='Renamed'`);
    assert.equal(await evaluate(`document.querySelector('#group-hex').value`),'#12abef','Saved custom color reopens accurately');
    failGroupSave = true;
    await evaluate(`document.querySelector('#group-save').click()`);
    await waitFor(`document.querySelector('#group-result').textContent.includes('not confirmed')`);
    assert.equal(groupFixture.groups[0].name, 'Project <A>');
    assert.equal(await evaluate(`document.querySelector('#group-name').value`),'Renamed','Failed save preserves the draft');
    assert.equal(await evaluate(`document.querySelector('#group-hex').value`),'#12abef');
    failGroupSave = false;
    await evaluate(`document.querySelector('#group-save').click()`);
    await waitFor(`document.querySelector('[data-run-id="fixture-0"] .pane-group-badge').textContent==='Renamed'`);
    await evaluate(`document.querySelector('.group-assignment').open=false`);
    await screenshot('project-groups-desktop');
    await evaluate(`document.documentElement.dataset.appTheme='light'`);
    assert.equal(await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--surface-rgb').trim()`),'255 255 255');
    await screenshot('project-groups-light');
    for(const hex of ['#ffffff','#000000','#12abef']) {
      await evaluate(`document.querySelector('#group-hex').value=${JSON.stringify(hex)};document.querySelector('#group-hex').dispatchEvent(new Event('input'))`);
      assert.equal(await evaluate(`document.querySelector('#group-preview').style.getPropertyValue('--group-color')`),hex);
    }
    await evaluate(`document.documentElement.dataset.appTheme='dark'`);
    await viewport(390, 844);
    assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth && document.querySelector('#pane-groups-dialog').scrollWidth<=document.querySelector('#pane-groups-dialog').clientWidth`), 'Groups dialog fits mobile width');
    await screenshot('project-groups-mobile');
    await viewport(1280, 800);
    await evaluate(`document.querySelector('#pane-groups-dialog').close()`);
    // Simulate another browser changing metadata; normal session polling must reconcile it.
    groupFixture.groups[0].name = 'From another device';
    await waitFor(`document.querySelector('[data-run-id="fixture-0"] .pane-group-badge').textContent==='From another device'`);
    await evaluate(`document.querySelector('[data-group-filter="project-fixture"]').click();document.querySelector('#btn-pane-groups').click();document.querySelector('[data-edit-group="project-fixture"]').click();window.confirm=()=>true;document.querySelector('#group-delete').click()`);
    await waitFor(`document.querySelector('[data-group-filter="project-fixture"]') === null`);
    assert.equal(await evaluate(`document.querySelector('[data-group-filter="all"]').getAttribute('aria-pressed')`), 'true');
    assert.equal(await evaluate(`document.querySelectorAll('#grid .pane-card.group-hidden').length`), 0);
    assert.equal(frameLoads, groupFrames, 'Assignment, rename, delete and filtering preserve terminal frames');
    assert.equal(requests.some(r => /\/(stop|terminate|restart)$/.test(r.path)), false);
    await evaluate(`document.querySelector('#pane-groups-dialog').close();document.querySelector('[data-run-id="fixture-0"] .pane-input textarea').value=''`);
  }
  if (!baseline) {
    assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-2"] iframe').dataset.inlineSelection`), 'true', 'Shell uses inline selection when supported');
    assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-1"] iframe').dataset.inlineSelection`), 'false', 'Older nodes retain native selection');
  }

  if (!baseline) {
    const beforeLinks=frameLoads;
    await evaluate(`window.postMessage({type:'siling:open-local-path',path:'/fixture/spoof.png'},location.origin)`);
    await evaluate(`window.dispatchEvent(new MessageEvent('message',{origin:'https://untrusted.example',source:document.querySelector('.pane iframe').contentWindow,data:{type:'siling:open-local-path',path:'/fixture/spoof.png'}}))`);
    await pause(100);
    assert.equal(linkedFixtures.size,0,'Messages from outside terminal frames are ignored');
    await evaluate(`document.querySelectorAll('.pane iframe')[2].contentWindow.eval("parent.postMessage({type:'siling:open-local-path',path:'/fixture/artifact.png'},location.origin)")`);
    for(let i=0;i<80;i++) {
      if(await evaluate(`!!document.querySelector('#folder-modal-preview img')?.naturalWidth`)) break;
      await pause(100);
    }
    assert.equal(linkedFixtures.get('fixture-2')?.[0].path,'/fixture/artifact.png','Link attaches to its source terminal session');
    assert.ok(await evaluate(`document.querySelector('#folder-modal-preview img')?.naturalWidth > 0`),'Click message opens a rendered image');
    assert.equal(frameLoads,beforeLinks,'Opening a file preserves terminal frames');
    await screenshot('terminal-local-link');
    await evaluate(`document.querySelector('#folder-modal-close').click()`);
    await evaluate(`{const input=document.querySelector('[data-run-id="fixture-2"] .pane-ssh-host');input.value='fixture-ssh';input.dispatchEvent(new Event('change'));}`);
    await evaluate(`document.querySelectorAll('.pane iframe')[2].contentWindow.eval("parent.postMessage({type:'siling:open-local-path',path:'/remote/artifact.png'},location.origin)")`);
    for(let i=0;i<80;i++) {
      if(linkedFixtures.get('fixture-2')?.[0].path === '/fixture/ssh-preview.png' && await evaluate(`!!document.querySelector('#folder-modal-preview img')?.naturalWidth`)) break;
      await pause(100);
    }
    assert.equal(linkedFixtures.get('fixture-2')?.[0].path,'/fixture/ssh-preview.png','SSH pane previews returned snapshot');
    assert.equal(frameLoads,beforeLinks,'SSH file preview preserves terminal frames');
    await screenshot('terminal-ssh-link');
    await evaluate(`document.querySelector('#folder-modal-close').click();{const input=document.querySelector('[data-run-id="fixture-2"] .pane-ssh-host');input.value='';input.dispatchEvent(new Event('change'));}`);
    assert.equal(await evaluate(`localStorage.getItem('siling_ssh_host:fixture-2')`),null);

  }

  if (!baseline) {
    const beforePreviewFrames = frameLoads;
    linkedFixtures.set('fixture-0', [{path:'/fixture/report.md',label:'Report',type:'file',exists:true,allowed:true,
      entries:[{rel:'',name:'report.md',type:'file',kind:'markdown',previewable:true}],loaded_dirs:['']}]);
    // Stub only the CDN parser/sanitizer: exercise the actual Files opening and
    // rendering path with representative HTML, without external network access.
    const previewHtml = '<h1>Readable Markdown</h1><p>正文应该清晰可读。Theme-aware document preview.</p><blockquote>Quoted supporting text remains readable.</blockquote><p>Inline <code>example()</code> and <a href="https://example.invalid/">documentation link</a>.</p><pre><code>const ready = true;</code></pre><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody><tr><td>Text contrast</td><td>Readable</td></tr></tbody></table>';
    await evaluate(`window.marked={parse:()=>${JSON.stringify(previewHtml)}};window.DOMPurify={sanitize:html=>html};document.querySelector('[data-run-id="fixture-0"] .btn-folders').click()`);
    for (let i=0;i<80;i++) {
      if(await evaluate(`!!document.querySelector('.markdown-body h1')`)) break;
      await pause(50);
    }
    assert.ok(await evaluate(`!!document.querySelector('.markdown-body h1')`),'Files renders the Markdown preview');
    assert.ok(await evaluate(`[...document.querySelectorAll('.folder-section-title')].every(el=>getComputedStyle(el).backgroundImage==='none')`),'Files headers must not keep a fixed light gradient behind theme-colored text');
    const previewContrast = async () => evaluate(`(()=>{
      const rgb = color => color.match(/[\\d.]+/g).map(Number);
      const luminance = color => rgb(color).slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
      const over = (fg,bg) => {const a=fg[3]??1;return [0,1,2].map(i=>fg[i]*a+bg[i]*(1-a)).concat(1)};
      function background(el) {if(!el)return [255,255,255,1];const c=rgb(getComputedStyle(el).backgroundColor);return over(c,background(el.parentElement))}
      return [...document.querySelectorAll('.markdown-body h1,.markdown-body p,.markdown-body blockquote,.markdown-body code,.markdown-body a,.markdown-body th,.markdown-body td,.markdown-body .file-plain,.folder-section-title')].map(el=>{
        const bg=background(el);const fg=over(rgb(getComputedStyle(el).color),bg);
        const a=luminance('rgb('+fg.slice(0,3).join(',')+')'),b=luminance('rgb('+bg.slice(0,3).join(',')+')');
        return {tag:el.tagName,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
      });
    })()`);
    for (const [theme,scheme] of [['dark','dark'],['light','light'],['system','dark'],['system','light']]) {
      await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:scheme}]});
      await evaluate(`{const c=document.querySelector('[data-appearance="theme"]');c.value=${JSON.stringify(theme)};c.dispatchEvent(new Event('change'));}`);
      await screenshot(`markdown-${theme}-${scheme}`);
      const contrast = await previewContrast();
      assert.ok(contrast.length>=10,'Measure all representative Markdown elements');
      assert.ok(contrast.every(item=>item.contrast>=4.5),`Markdown contrast in ${theme}/${scheme}: ${JSON.stringify(contrast)}`);
      console.log(`Markdown ${theme}/${scheme}: minimum contrast ${Math.min(...contrast.map(item=>item.contrast)).toFixed(2)}:1`);
    }
    await evaluate(`window.marked.parse=()=>{throw Error('offline renderer fixture')};document.querySelector('#folder-modal-refresh').click()`);
    for(let i=0;i<80;i++) {
      if(await evaluate(`!!document.querySelector('.markdown-body .file-plain')`)) break;
      await pause(50);
    }
    assert.ok(await evaluate(`!!document.querySelector('.markdown-body .file-plain')`),'Unavailable parser uses the plaintext fallback');
    for(const theme of ['dark','light']) {
      await evaluate(`{const c=document.querySelector('[data-appearance="theme"]');c.value=${JSON.stringify(theme)};c.dispatchEvent(new Event('change'));}`);
      assert.ok((await previewContrast()).every(item=>item.contrast>=4.5),`Plaintext fallback stays readable in ${theme}`);
    }
    await evaluate(`document.querySelector('#folder-modal-close').click();{const c=document.querySelector('[data-appearance="theme"]');c.value='dark';c.dispatchEvent(new Event('change'));}`);
    assert.equal(frameLoads,beforePreviewFrames,'Preview and theme changes preserve terminal frames');
    console.log('PASS: Files Markdown contrast in dark, light and both system themes; plaintext fallback');
  }

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
  assert.equal(await evaluate(`document.querySelector('#settings-panel-opacity').closest('label').querySelector('.settings-row-title').textContent`),'面板不透明度');
  assert.equal(await evaluate(`document.querySelector('#btn-apply-global-theme').textContent`),'应用到已打开面板');
  assert.equal(await evaluate(`document.querySelector('.btn-progress').textContent`),'进度');
  assert.equal(await evaluate(`document.querySelector('.btn-monitor').textContent`),'监控');
  assert.ok(await evaluate(`document.querySelector('.pane-input textarea').placeholder.includes('换行')`));
  assert.equal(await evaluate(`document.querySelector('.pane-theme-select option[value="soft-dark"]').textContent`),'柔和深色');
  assert.equal(await evaluate(`document.querySelector('.pane-state-select option[value="blocked"]').textContent`),'受阻');
  assert.equal(await evaluate(`document.querySelector('#folder-modal-copy').textContent`),'复制路径');
  assert.equal(await evaluate(`document.querySelector('#new-cwd-field > span').textContent`),'工作目录');
  assert.equal(await evaluate(`document.querySelector('#new-kind option[value="resume"]').textContent`),'恢复');
  assert.equal(await evaluate(`document.querySelector('#new-kind option[value="resume"]').value`),'resume','Translation never changes API values');
  assert.ok(await evaluate(`document.querySelector('[data-priority-filter="all"]').textContent.startsWith('全部')`));
  assert.ok(await evaluate(`document.querySelector('.si-agent .ui-secondary').textContent.includes('会话')`));
  assert.ok(await evaluate(`document.querySelector('.btn-folders').textContent.startsWith('文件')`));
  assert.equal(await evaluate(`document.querySelector('.pane-input textarea').value`),'preserved draft');
  assert.equal(frameLoads,frames,'Language changes preserve terminal connections');
  // A filename or task called "Settings" is user content, not UI copy.
  await evaluate(`{const p=document.createElement('p');p.id='untranslated-user-data';p.textContent='Settings / 项目 / Close';document.body.append(p);}`);
  await pause(50);
  assert.equal(await evaluate(`document.querySelector('#untranslated-user-data').textContent`),'Settings / 项目 / Close');
  await screenshot('settings-zh');
  await evaluate(`document.querySelector('#settings-close').click();document.querySelector('#btn-new').click()`);
  await screenshot('new-session-zh');
  await evaluate(`document.querySelector('#new-close').click();document.querySelector('#btn-settings').click()`);
  await evaluate(`{const c=document.querySelector('[data-appearance="language"]');c.value='en';c.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`document.querySelector('.btn-progress').textContent`),'Progress');
  assert.equal(await evaluate(`document.querySelector('.btn-monitor').textContent`),'Monitor');
  assert.equal(await evaluate(`document.querySelector('#new-cwd-field > span').textContent`),'Working dir');
  assert.equal(await evaluate(`document.querySelector('#btn-apply-global-theme').textContent`),'Apply to open panes');
  assert.ok(!/\p{Script=Han}/u.test(await evaluate(`document.querySelector('.pane-input textarea').placeholder`)));
  await evaluate(`document.querySelector('#untranslated-user-data').remove()`);
  await screenshot('settings-en');
  console.log('PASS: English/Chinese labels, tooltips and placeholders switch without changing drafts, API values, user content or terminal frames');
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
  assert.equal(requests.filter(r => r.path === '/api/pane-groups' && r.method === 'POST').length, 6, 'Only explicit group edits write group metadata');
  assert.deepEqual(requests.filter(r => r.method !== 'GET' && r.path !== '/api/pane-groups'), [{ method: 'POST', path: '/api/self-update/fetch' }, {method:'POST',path:'/api/sessions/fixture-2/folders'}, {method:'POST',path:'/api/sessions/fixture-2/ssh-file'}], 'Only boot-time fetch and explicitly clicked files may mutate other state');
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
  // Restart only the selected agent, preserving the draft and any moved slot.
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-2"] .btn-restart-session').hidden`),true,'Terminal is not an agent restart target');
  await evaluate(`window.restartPrompts=[];window.restartAlerts=[];window.confirm=text=>{restartPrompts.push(text);return false};window.alert=text=>restartAlerts.push(text);document.querySelector('[data-run-id="fixture-1"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-1"] .btn-restart-session').click()`);
  assert.equal(pendingRestart,undefined,'Cancel sends no restart request');
  assert.ok(await evaluate(`restartPrompts[0].includes('interrupts running work')`),'Confirmation explains interruption');
  await evaluate(`window.confirm=()=>true;document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').value='restart draft';document.querySelector('[data-run-id="fixture-1"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-1"] .btn-restart-session').click()`);
  for(let i=0;i<50&&!pendingRestart;i++) await pause(50);
  assert.ok(pendingRestart);
  pendingRestart.end(JSON.stringify({ok:false,stage:'stop',reason:'fixture exit timeout'}));
  pendingRestart=undefined;
  for(let i=0;i<50;i++) {
    if(await evaluate(`restartAlerts.length===1 && !document.querySelector('[data-run-id="fixture-1"] .btn-restart-session').disabled`)) break;
    await pause(50);
  }
  assert.ok(await evaluate(`restartAlerts[0].includes('fixture exit timeout')`),'Failure is actionable');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').value`),'restart draft');
  const beforeRestartFrames=frameLoads;
  await evaluate(`document.querySelector('[data-run-id="fixture-1"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-1"] .btn-restart-session').click()`);
  for(let i=0;i<50&&!pendingRestart;i++) await pause(50);
  assert.ok(pendingRestart);
  await evaluate(`document.querySelector('[data-run-id="fixture-1"] .btn-restart-session').dispatchEvent(new Event('click'))`);
  assert.equal(requests.filter(r=>r.path.endsWith('/restart')).length,2,'Duplicate click while pending sends no request');
  sessions[1].alive=false;
  await clickIcon('#btn-refresh'); await pause(250);
  assert.ok(await evaluate(`JSON.parse(localStorage.getItem('orch_slots')).includes('fixture-1')`),'Polling retains restarting pane');
  assert.ok(await evaluate(`document.querySelector('[data-run-id="fixture-1"] .pane').inert`),'Restart blocks terminal input');
  assert.ok(await evaluate(`document.querySelector('[data-run-id="fixture-1"] .pane-input textarea').disabled`));
  await screenshot('agent-restarting');
  await evaluate(`document.querySelector('[data-run-id="fixture-2"] .btn-pane-more').click();{const move=document.querySelector('[data-run-id="fixture-2"] .pane-move-select');move.value='0';move.dispatchEvent(new Event('change'));}`);
  sessions.push({...sessions[1],alive:true,run_id:'fixture-restarted',tmux_session:'fixture-restarted'});
  pendingRestart.end(JSON.stringify({ok:true,run_id:'fixture-restarted',restarted_from:'fixture-1'}));
  for(let i=0;i<80;i++) {
    if(await evaluate(`!!document.querySelector('[data-run-id="fixture-restarted"] iframe')`)) break;
    await pause(100);
  }
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[2]`),'fixture-restarted','Restart follows moved pane instead of overwriting another pane');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-restarted"] .pane-input textarea').value`),'restart draft');
  assert.equal(frameLoads,beforeRestartFrames+1,'Only the restarted pane attaches a new iframe');
  pendingRestart=undefined;
  await evaluate(`document.querySelector('[data-run-id="fixture-restarted"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-restarted"] .btn-restart-session').click()`);
  for(let i=0;i<50&&!pendingRestart;i++) await pause(50);
  assert.ok(pendingRestart);
  sessions.at(-1).alive=false;
  pendingRestart.end(JSON.stringify({ok:false,stage:'resume',reason:'fixture spawn failure',hint:'Use Resume on the saved source'}));
  for(let i=0;i<50;i++) {
    if(await evaluate(`restartAlerts.length===2`)) break;
    await pause(50);
  }
  await clickIcon('#btn-refresh'); await pause(250);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('orch_slots'))[2]`),'fixture-restarted','Stopped source remains available after failed restart');
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-restarted"] .pane-input textarea').value`),'restart draft','Failed launch preserves draft');
  assert.equal(requests.filter(r=>r.path.endsWith('/kill')).length,0,'UI never escalates restart to a force kill');
  systemBrowserAvailable=true;
  await evaluate(`localStorage.removeItem('siling_system_browser');localStorage.setItem('siling_open_links_internally','0')`);
  await cdp('Page.reload');
  for(let i=0;i<100;i++) {
    if(await evaluate(`document.querySelector('#settings-system-browser')?.disabled===false && !!document.querySelector('.pane iframe')?.contentDocument?.querySelector('textarea')`))break;
    await pause(100);
  }
  assert.equal(await evaluate(`document.querySelector('#settings-system-browser').checked`),true);
  await evaluate(`window.webOpens=[];window.webAlerts=[];window.open=url=>webOpens.push(url);window.alert=message=>webAlerts.push(message)`);
  const nativeUrl='https://example.invalid/native?redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Fcallback&state=exact-value';
  await evaluate(`silingOpenWebUrl(${JSON.stringify(nativeUrl)},document.querySelector('.pane iframe').contentWindow)`);
  for(let i=0;i<50&&systemBrowserOpens.length<1;i++)await pause(50);
  assert.deepEqual(systemBrowserOpens,[nativeUrl]);
  assert.deepEqual(await evaluate('webOpens'),[],'Native opening does not also open a PWA tab');
  assert.equal(await evaluate(`silingOpenWebUrl(${JSON.stringify(nativeUrl)},window)`),false,'Unrecognized source cannot use terminal bridge');
  await evaluate(`(()=>{const a=document.createElement('a');a.dataset.openWebLink='';a.href=${JSON.stringify(nativeUrl)};document.body.append(a);a.click();a.remove();})()`);
  for(let i=0;i<50&&systemBrowserOpens.length<2;i++)await pause(50);
  assert.deepEqual(systemBrowserOpens,[nativeUrl,nativeUrl],'Markdown/Files anchors share native route');
  await evaluate(`{const s=document.querySelector('#settings-system-browser');s.checked=false;s.dispatchEvent(new Event('change'));}silingOpenWebUrl(${JSON.stringify(nativeUrl)},document.querySelector('.pane iframe').contentWindow)`);
  assert.deepEqual(await evaluate('webOpens'),[nativeUrl],'Opt-out uses browser window.open');
  assert.equal(await evaluate(`localStorage.getItem('siling_system_browser')`),'0');
  await evaluate(`{const s=document.querySelector('#settings-system-browser');s.checked=true;s.dispatchEvent(new Event('change'));const i=document.querySelector('#settings-open-links-internally');i.checked=true;i.dispatchEvent(new Event('change'));}silingOpenWebUrl(location.origin+'/fixture-tty/web',document.querySelector('.pane iframe').contentWindow)`);
  assert.equal(await evaluate(`document.querySelector('#projects-browser-modal').hidden`),false,'Internal setting takes precedence');
  assert.equal(systemBrowserOpens.length,2);
  failBrowserOpen=true;
  await evaluate(`{const i=document.querySelector('#settings-open-links-internally');i.checked=false;i.dispatchEvent(new Event('change'));}silingOpenWebUrl(${JSON.stringify(nativeUrl)},document.querySelector('.pane iframe').contentWindow)`);
  for(let i=0;i<50;i++){if(await evaluate('webAlerts.length>0'))break;await pause(50);}
  assert.equal(systemBrowserOpens.length,3,'One request, without automatic retries');
  assert.equal(await evaluate('webAlerts.length'),1,'System failure is visible');
  assert.deepEqual(await evaluate('webOpens'),[nativeUrl],'Failure never silently opens a duplicate in another profile');
  console.log('PASS: system browser routing, remote-device fallback, opt-out, internal precedence and failure handling');
  const beforeFileContextFrames=frameLoads;
  await evaluate(`document.querySelector('[data-run-id="fixture-2"] .btn-pane-more').click();document.querySelector('[data-run-id="fixture-2"] .btn-terminal-files').click()`);
  for(let i=0;i<50;i++){if(await evaluate(`!!document.querySelector('dialog[open] [data-text]')`))break;await pause(50);}
  assert.ok(await evaluate(`!!document.querySelector('dialog[open] [data-context]')`),'Ordinary Terminal exposes file context and selected-text discovery');
  const discoveryRequests=()=>requests.filter(r=>r.path.endsWith('/discover-files')).length;
  const beforeInvalid=discoveryRequests();
  for(const invalid of ['', '   ', 'x'.repeat(16001)]) {
    await evaluate(`document.querySelector('dialog[open] [data-text]').value=${JSON.stringify(invalid)};document.querySelector('dialog[open] [data-model]').click()`);
    await pause(100);
    assert.equal(discoveryRequests(),beforeInvalid,'Invalid text must never be sent to Claude');
    assert.ok(await evaluate(`document.querySelector('dialog[open] [data-status]').textContent.length>0`));
  }
  await evaluate(`document.querySelector('dialog[open] [data-load]').click()`);
  for(let i=0;i<50;i++){if(await evaluate(`document.querySelector('dialog[open] [data-text]').value.includes('history-')`))break;await pause(50);}
  assert.ok(await evaluate(`document.querySelector('dialog[open] [data-text]').value.includes('history-')`),'Load terminal output without a selection');
  assert.equal(discoveryRequests(),beforeInvalid,'Reading output does not call Claude or discover files');
  await evaluate(`document.querySelector('dialog[open] [data-text]').value='reports/test.md';document.querySelector('dialog[open] [data-scan]').click()`);
  for(let i=0;i<50;i++){if(await evaluate(`document.querySelector('dialog[open] [data-results]')?.children.length===1`))break;await pause(50);}
  assert.equal(await evaluate(`document.querySelector('dialog[open] [data-results] button').textContent`),'/remote/work/reports/test.md');
  await evaluate(`document.querySelector('dialog[open] [data-model]').click()`);
  for(let i=0;i<50;i++){if(fileDiscoveries.some(r=>r.intelligent===true))break;await pause(50);}
  assert.ok(fileDiscoveries.some(r=>r.intelligent===true && r.text==='reports/test.md'),'Explicit Claude action sends reviewed valid text');
  assert.equal(frameLoads,beforeFileContextFrames,'File context dialog preserves terminal frames');
  await screenshot('terminal-file-context');
  await evaluate(`document.querySelector('dialog[open] [data-save]').click()`);await pause(150);
  await evaluate(`document.querySelector('dialog[open] [data-close]').click()`);
  await evaluate(`(async()=>{
    const controller=window.SilingTerminalFiles.create({
      api:async()=>({configured:true,current:{id:'viewport'},contexts:[{id:'viewport'}],settings:{}}),
      openViewer:()=>{},
    });
    const buffer={viewportY:10,getLine:y=>({translateToString:()=>y===10?'x'.repeat(16001):'wrong row'})};
    const term={getSelection:()=>'',rows:1,buffer:{active:buffer}};
    controller.states.set('viewport',{frame:{contentWindow:{term}}});
    await controller.configure('viewport','initial');
    document.querySelector('dialog[open] [data-load]').click();
  })()`);
  assert.equal(await evaluate(`document.querySelector('dialog[open] [data-text]').value`),'x'.repeat(16000),'Viewport text is bounded and does not read unrelated rows');
  assert.ok(await evaluate(`document.querySelector('dialog[open] [data-status]').textContent.includes('16000')`),'Truncation is explicit');
  await evaluate(`document.querySelector('dialog[open] [data-close]').click()`);
  console.log('PASS: ordinary Terminal file context, selected relative file discovery, persistence UI and frame preservation');
  assert.deepEqual(errors, [], 'No uncaught browser errors');
  console.log(JSON.stringify({ result: 'PASS', frameLoads, screenshots: artifacts }));
  }
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close();
}
