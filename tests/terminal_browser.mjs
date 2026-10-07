// Opt-in terminal behavior test: requires tmux, ttyd, UI_BROWSER, and project Python.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import http from 'node:http';
import {spawn, execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const executable=process.env.UI_BROWSER;
if (!executable) throw Error('Set UI_BROWSER to a Chromium browser executable');
const python=process.env.PYTHON || 'python3';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const profile=fs.mkdtempSync('/tmp/siling-terminal-smoke-');
const artifacts=process.env.TERMINAL_ARTIFACT_DIR || profile;
fs.mkdirSync(artifacts,{recursive:true});
const socket=path.join(profile,'tmux.sock');
const tmux=(...args)=>execFileSync('tmux',['-S',socket,...args],{encoding:'utf8'});
tmux('-f','/dev/null','new-session','-d','-s','check','-x','80','-y','24','/bin/sh');
tmux('set-option','-t','check','mouse','on');
tmux('set-option','-t','check','status','off');
tmux('send-keys','-t','check',"i=1; while [ $i -le 150 ]; do echo smoke-history-$i; i=$((i+1)); done",'Enter');
const listener=http.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
let livePreviewReads=0;
const selectionServer=http.createServer((req,res)=>{
  try {
    const requestUrl=new URL(req.url,'http://localhost');
    const normalize=requestUrl.pathname==='/trim';
    const previewOnly=requestUrl.searchParams.get('preview_only')==='true';
    if(normalize && previewOnly) livePreviewReads++;
    const script=normalize ? `import json;from agent_orchestrator.dashboard import _tmux_trim_selection,_tmux_selection_preview;print(json.dumps({'adjusted':${previewOnly ? "False" : "_tmux_trim_selection('check')"},'preview':_tmux_selection_preview('check')}))` : "import json;from agent_orchestrator.dashboard import _tmux_copy_selection;print(json.dumps({'text':_tmux_copy_selection('check')}))";
    const text=execFileSync(python,['-c',script],{cwd:root,env:{...process.env,TMUX:`${socket},0,0`},encoding:'utf8'});
    res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Content-Type','application/json');res.end(text);
  }catch(error){res.writeHead(500);res.end(String(error));}
});
await new Promise(r=>selectionServer.listen(0,'127.0.0.1',r));
const selectionPort=selectionServer.address().port;
const ttyd=spawn('ttyd',['-i','127.0.0.1','-p',String(port),'-W','tmux','-S',socket,'-T','sync','attach','-t','check'],{stdio:'ignore'});
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
  await cdp('Page.enable'); await cdp('Runtime.enable');
  await viewport(1280, 800);
  await pause(500);
  await cdp('Page.navigate',{url:`http://127.0.0.1:${port}`});
  for(let i=0;i<80;i++){if(await evaluate('!!window.term'))break;await pause(100);}
  assert.ok(await evaluate('!!window.term'));
  await evaluate('window.term.focus()');
  await cdp('Input.insertText',{text:'echo SMOKE_INPUT_OK'});
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await pause(500);
  const history=tmux('capture-pane','-t','check','-p','-S','-');
  assert.ok(history.includes('smoke-history-1'));
  assert.ok(history.split('\n').some(line=>line==='SMOKE_INPUT_OK'));
  const injection=execFileSync(python,['-c',"from agent_orchestrator.terminal_theme import _TTYD_INTERACTION_SCRIPT as s;print(s.split('>',1)[1].rsplit('</script>',1)[0])"],{cwd:root,encoding:'utf8'});
  await evaluate(`Object.defineProperty(window,'frameElement',{value:{dataset:{inlineSelection:'true',nativeSelection:'true'}}});window.localMessages=[];Object.defineProperty(window,'parent',{value:{postMessage: message=>window.localMessages.push(message)}});void 0;`);
  await evaluate(injection);
  // Let initial font fitting and ttyd's 300 ms resize overlay settle.
  await pause(500);
  // Browser rendering must remain frozen across split synchronized updates.
  await evaluate(`new Promise(resolve => term.write('\\x1b[?1049hBASELINE\\x1b[?25l', resolve))`);
  await pause(100);
  const beforeSyncPaint=(await cdp('Page.captureScreenshot',{format:'png'})).data;
  await evaluate(`window.syncRenders=0;window.syncObserver=term.onRender(()=>window.syncRenders++);new Promise(resolve=>term.write('\\x1b[?2026h\\x1b[2J\\x1b[HPARTIAL',resolve))`);
  await pause(150);
  assert.equal(await evaluate('window.syncRenders'),0,'Do not paint an unfinished synchronized frame');
  const duringSyncPaint=(await cdp('Page.captureScreenshot',{format:'png'})).data;
  fs.writeFileSync(path.join(artifacts,'sync-before.png'),Buffer.from(beforeSyncPaint,'base64'));
  fs.writeFileSync(path.join(artifacts,'sync-during.png'),Buffer.from(duringSyncPaint,'base64'));
  assert.ok(duringSyncPaint===beforeSyncPaint,'Visible pixels remain unchanged until the end marker');
  assert.ok(await evaluate("term.buffer.active.getLine(0).translateToString(true).includes('PARTIAL')"),'Parsing continues while rendering is held');
  await evaluate(`new Promise(resolve=>term.write('\\x1b[HFINAL-FRAME\\x1b[?2026l',resolve))`);
  await pause(100);
  assert.ok(await evaluate('window.syncRenders>0'),'End marker releases final rendering');
  await evaluate(`window.syncRenders=0;new Promise(resolve=>term.write('\\x1b[?2026hWATCHDOG',resolve))`);
  await pause(150);
  assert.equal(await evaluate('window.syncRenders'),0);
  await pause(1100);
  assert.ok(await evaluate('window.syncRenders>0'),'A missing end marker cannot freeze the pane');
  await evaluate(`window.syncObserver.dispose();new Promise(resolve=>term.write('\\x1b[?1049l',resolve))`);
  await pause(100);
  // The parser fixture left tmux's alternate screen; restore the real client
  // buffer before testing tmux coordinates, links and selection.
  await evaluate(`new Promise(resolve=>term.write('\\x1b[?1049h',resolve))`);
  tmux('refresh-client');
  await pause(150);
  console.log('PASS: synchronized browser paint, incremental parsing and missing-end timeout');
  await evaluate(`window.tmuxSyncStarts=0;window.tmuxSyncProbe=term.parser.registerCsiHandler({prefix:'?',final:'h'},params=>{if(params.includes(2026))window.tmuxSyncStarts++;return false;});`);
  tmux('send-keys','-t','check','echo BROWSER_SYNC_ROUNDTRIP','Enter');
  await pause(300);
  assert.ok(await evaluate('window.tmuxSyncStarts>0'),'Real tmux client emits synchronized updates through ttyd');
  await evaluate('window.tmuxSyncProbe.dispose()');
  console.log('PASS: tmux to ttyd to browser synchronization negotiation');
  // A resize must not expose xterm's provisional old rows before tmux's
  // authoritative repaint. Delay incoming writes to inspect the visible cover.
  const resizeCover = await evaluate(`(async()=>{window.resizeWrite=term.write;window.resizeWrites=[];term.write=function(...args){resizeWrites.push(args)};const before=[...document.querySelectorAll('.xterm-screen canvas')].map(c=>c.toDataURL());window.resizeParent=term.element.parentElement;window.resizeParentStyle=resizeParent.getAttribute('style');resizeParent.style.width=(resizeParent.clientWidth-64)+'px';term.fit();const cover=document.querySelector('.siling-resize-snapshot');const result={present:!!cover,pixelsMatch:JSON.stringify([...cover?.querySelectorAll('canvas')||[]].map(c=>c.toDataURL()))===JSON.stringify(before),pointerEvents:cover&&getComputedStyle(cover).pointerEvents};await new Promise(r=>setTimeout(r,70));result.waiting=!!document.querySelector('.siling-resize-snapshot');return result;})()`);
  assert.equal(resizeCover.present,true,'Resize keeps the last painted frame');
  assert.equal(resizeCover.pixelsMatch,true,'Snapshot preserves actual canvas pixels without scaling');
  assert.equal(resizeCover.pointerEvents,'none','Snapshot never intercepts terminal input');
  assert.equal(resizeCover.waiting,true,'Intermediate paints remain covered while waiting for remote output');
  await evaluate(`term.write=resizeWrite;for(const args of resizeWrites)term.write(...args);resizeWrites=[];`);
  await pause(120);
  assert.equal(await evaluate(`!!document.querySelector('.siling-resize-snapshot')`),false,'A completed tmux frame releases the snapshot');
  await screenshot('resize-complete');
  await evaluate(`term.write=function(...args){resizeWrites.push(args)};if(resizeParentStyle===null)resizeParent.removeAttribute('style');else resizeParent.setAttribute('style',resizeParentStyle);term.fit();`);
  await pause(320);
  assert.equal(await evaluate(`!!document.querySelector('.siling-resize-snapshot')`),false,'Missing remote output cannot leave a stale overlay');
  await evaluate(`term.write=resizeWrite;for(const args of resizeWrites)term.write(...args);resizeWrites=[];`);
  await pause(150);
  console.log('PASS: resize retains painted pixels until synchronized output, preserves input and has a bounded fallback');
  // Growing a live shell brings older tmux history into view above the prompt.
  // The retained frame must already be at that final bottom position.
  const anchored = await evaluate(`(()=>{term.write=function(...args){resizeWrites.push(args)};const b=term.buffer.active;const before={rows:term.rows,cursor:b.cursorY,line:b.getLine(b.viewportY+b.cursorY).translateToString(true),cell:document.querySelector('.xterm-screen').getBoundingClientRect().height/term.rows};resizeParent.style.height=(resizeParent.clientHeight+96)+'px';term.fit();const canvas=document.querySelector('.siling-resize-snapshot canvas');return {...before,newRows:term.rows,offset:canvas?new DOMMatrix(getComputedStyle(canvas).transform).m42:null};})()`);
  assert.equal(anchored.cursor,anchored.rows-1,'Fixture has a live prompt on the bottom row');
  assert.ok(anchored.newRows>anchored.rows,'Fixture expands terminal height');
  assert.ok(Math.abs(anchored.offset-(anchored.newRows-anchored.rows)*anchored.cell)<0.1,'Snapshot prompt is at the final bottom position before output arrives');
  await evaluate(`term.write=resizeWrite;for(const args of resizeWrites)term.write(...args);resizeWrites=[];`);
  await pause(350);
  assert.equal(await evaluate(`term.buffer.active.getLine(term.buffer.active.viewportY+term.rows-1).translateToString(true)`),anchored.line,'tmux confirms the same prompt at the predicted position');
  // A full-screen cursor at the top must not be treated as a bottom prompt.
  await evaluate(`new Promise(resolve=>term.write('\\x1b[H',resolve))`);
  const topOffset=await evaluate(`(()=>{term.write=function(...args){resizeWrites.push(args)};if(resizeParentStyle===null)resizeParent.removeAttribute('style');else resizeParent.setAttribute('style',resizeParentStyle);term.fit();const c=document.querySelector('.siling-resize-snapshot canvas');return c?new DOMMatrix(getComputedStyle(c).transform).m42:null;})()`);
  assert.equal(topOffset,0,'Top-positioned full-screen content keeps its original anchor');
  await evaluate(`term.write=resizeWrite;for(const args of resizeWrites)term.write(...args);resizeWrites=[];`);
  await pause(350);
  console.log('PASS: live bottom prompt is aligned before resized history arrives; top cursor remains top-aligned');
  // A late layout/font change can miss ttyd's one window-resize fit.
  // Change only the container, so the browser window emits no resize event.
  await evaluate(`window.fitParent=term.element.parentElement;window.fitOriginalStyle=fitParent.getAttribute('style');window.narrowCols=term.cols;fitParent.style.width='600px';fitParent.style.height='500px';`);
  await pause(250);
  const shrunk=await evaluate('term.cols');
  assert.ok(shrunk<await evaluate('window.narrowCols'),'Container resize converges without a window resize notification');
  await evaluate(`fitParent.style.width='1280px';fitParent.style.height='800px';`);
  await pause(250);
  assert.ok(await evaluate('term.cols')>shrunk,'Zoom expansion does not retain narrow columns');
  const settledCols=await evaluate('term.cols');
  await pause(300);
  assert.equal(await evaluate('term.cols'),settledCols,'Converged layout does not keep resizing');
  await evaluate(`if(fitOriginalStyle===null)fitParent.removeAttribute('style');else fitParent.setAttribute('style',fitOriginalStyle);`);
  await pause(500);
  console.log('PASS: terminal size converges after missed resize and zoom changes');
  // Real Cursor-style clear-then-render through Node -> tmux -> ttyd -> xterm.
  await evaluate(`window.blankPaints=0;window.blankObserver=term.onRender(()=>{const b=term.buffer.active;let text='';for(let row=0;row<term.rows;row++)text+=b.getLine(b.viewportY+row)?.translateToString(true)||'';if(!text.trim())window.blankPaints++;});`);
  const shellQuote=value=>"'"+value.replaceAll("'", "'\\''")+"'";
  const clearThenRender='process.stdout.write("\\x1b[2J\\x1b[3J\\x1b[H");setTimeout(()=>process.stdout.write("CLEAR_REPAINT_FINISHED\\n"),200)';
  const hook=process.env.CURSOR_TEST_HOOK || path.join(root,'scripts/cursor-sync-output.cjs');
  tmux('send-keys','-t','check',`env SILING_CURSOR_SYNC_ONCE=1 NODE_OPTIONS=${shellQuote('--require="'+hook+'"')} node -e ${shellQuote(clearThenRender)}`,'Enter');
  for(let attempt=0;attempt<50;attempt++){
    if(tmux('capture-pane','-t','check','-p').split('\n').some(line=>line.trim()==='CLEAR_REPAINT_FINISHED'))break;
    await pause(100);
  }
  await pause(200);
  assert.equal(await evaluate('window.blankPaints'),0,'Separate erase/repaint writes must not publish a blank browser frame');
  assert.ok(tmux('capture-pane','-t','check','-p').split('\n').some(line=>line.trim()==='CLEAR_REPAINT_FINISHED'));
  await evaluate('window.blankObserver.dispose()');
  console.log('PASS: clear-then-render stays visible across the complete terminal pipeline');




  // Real xterm viewport: scrollbar colors must follow the terminal palette,
  // including palette changes after ttyd receives its WebSocket preferences.
  const palettes=JSON.parse(execFileSync(python,['-c',"import json;from agent_orchestrator.terminal_theme import _TTYD_THEME_PALETTES;print(json.dumps(_TTYD_THEME_PALETTES))"],{cwd:root,encoding:'utf8'}));
  palettes.dark={background:'#2b2b2b',foreground:'#d2d2d2'};
  await evaluate('window.originalTheme=term.options.theme;window.originalCols=term.cols;window.originalRows=term.rows');
  for(const [name,palette] of Object.entries(palettes)) {
    await evaluate(`term.options.theme=${JSON.stringify(palette)};term.refresh(0,term.rows-1)`);
    await pause(150);
    const style=await evaluate(`(()=>{const v=document.querySelector('.xterm-viewport'),s=getComputedStyle(v);return {scheme:s.colorScheme,colors:s.scrollbarColor,overflow:s.overflowY,background:s.backgroundColor,thumb:getComputedStyle(v,'::-webkit-scrollbar-thumb').backgroundColor};})()`);
    assert.equal(style.scheme,['dark','soft-dark'].includes(name)?'dark':'light',name+' scrollbar scheme');
    assert.notEqual(style.colors,'auto',name+' explicitly colors the native scrollbar');
    assert.ok(style.colors.endsWith(style.background),name+' track matches terminal background');
    assert.notEqual(style.thumb,'rgba(0, 0, 0, 0)',name+' WebKit fallback has a visible thumb');
    assert.equal(style.overflow,'scroll','Scrollbar remains available');
  }
  assert.ok(await evaluate('term.cols===originalCols && term.rows===originalRows'),'Palette styling does not change terminal dimensions');
  await evaluate('term.options.theme=originalTheme;term.refresh(0,term.rows-1)');
  console.log('PASS: native terminal scrollbars follow all five palettes without resizing the terminal');
  // The real ttyd encoder must distinguish newline from submit. Run a raw
  // byte recorder in our private tmux server; no model or live agent is used.
  const recorder = String.raw`import os,termios,tty
original=termios.tcgetattr(0)
try:
 tty.setraw(0)
 os.write(1,b'\x1b[?2004h\r\nKEY_RECORDER_READY\r\n')
 while True:
  b=os.read(0,1)
  if b==b'\x04': break
  os.write(1,('KEYBYTE:%02x\r\n'%b[0]).encode())
finally:
 os.write(1,b'\x1b[?2004l')
 termios.tcsetattr(0,termios.TCSADRAIN,original)
`;
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  const recorderCommand = `import base64;exec(base64.b64decode('${Buffer.from(recorder).toString('base64')}'))`;
  tmux('send-keys','-t','check',`${quote(python)} -c ${quote(recorderCommand)}`,'Enter');
  for(let i=0;i<50;i++){if(tmux('capture-pane','-t','check','-p').split('\n').includes('KEY_RECORDER_READY'))break;await pause(100);}
  assert.ok(tmux('capture-pane','-t','check','-p').split('\n').includes('KEY_RECORDER_READY'),'Raw recorder started');
  const keysScript=fs.readFileSync(path.join(root,'static/terminal-keys.js'),'utf8');
  await evaluate(keysScript);
  await evaluate(`window.testSession={agent:'claude',alive:true};window.emittedKeys=[];term.onData(data=>emittedKeys.push(data));SiLingTerminalKeys.install(document,()=>testSession,()=>term);term.focus()`);
  for(const [agent,expected] of [['claude','\n'],['cursor','\n'],['terminal','\r'],['custom','\r'],['codex','\x1b[200~\n\x1b[201~']]) {
    await evaluate(`testSession.agent=${JSON.stringify(agent)};emittedKeys=[];term.focus()`);
    await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',modifiers:8,windowsVirtualKeyCode:13,text:'\r'});
    await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',modifiers:8,windowsVirtualKeyCode:13});
    assert.deepEqual(await evaluate('emittedKeys'),[expected],agent+' emits one newline payload, not a second CR');
  }
  await evaluate(`term.input('\x04',true)`);
  await pause(300);
  const keyBytes=tmux('capture-pane','-t','check','-p','-S','-').split('\n').filter(line=>/^KEYBYTE:[0-9a-f]{2}$/.test(line)).map(line=>line.slice(-2));
  assert.deepEqual(keyBytes,Array.from(Buffer.from('\n\n\r\r\x1b[200~\n\x1b[201~'),byte=>byte.toString(16).padStart(2,'0')),'tmux delivers the entire newline/paste payload without a submit');
  await evaluate(`testSession.agent='terminal';emittedKeys=[];term.focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  assert.deepEqual(await evaluate('emittedKeys'),['\r'],'ordinary Enter remains submit');
  console.log('PASS: real ttyd Shift+Enter byte routing through tmux; plain Terminal and Enter unchanged');
  await evaluate("new Promise(resolve=>term.write(" + JSON.stringify("\r\n\u001b]8;;file:///tmp/siling-fixture.png\u0007CLICK-ARTIFACT\u001b]8;;\u0007") + ",resolve))");
  const cell=await evaluate(`(()=>{const b=term.buffer.active;for(let y=b.viewportY;y<b.length;y++){const line=b.getLine(y).translateToString();const x=line.indexOf('CLICK-ARTIFACT');if(x>=0){const r=document.querySelector('.xterm-screen').getBoundingClientRect();return {x:r.x+(x+2.5)*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows};}}})()`);
  assert.ok(cell,'Fixture hyperlink is visible');
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...cell,button:'left',buttons:1,clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...cell,button:'left',buttons:0,clickCount:1});
  assert.equal(await evaluate(`window.localMessages.at(-1)?.path`),'/tmp/siling-fixture.png');
  await evaluate("new Promise(resolve=>term.write(" + JSON.stringify("\r\n\u590d\u5236\u6548\u679c\u56fe (/Users/\r\n  demo/Documents/OSS/project/\r\n  outputs/run/artifacts/copy-\r\n  history.png)\u3002") + ",resolve))");
  const hardCells=await evaluate(`(()=>{const b=term.buffer.active;const cells=[];const r=document.querySelector('.xterm-screen').getBoundingClientRect();for(let y=b.viewportY;y<b.length;y++){const line=b.getLine(y).translateToString();for(const marker of ['复制效果图','demo/Documents','history.png']){const x=line.indexOf(marker);if(x>=0)cells.push({x:r.x+(x+1.5)*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows});}}return cells;})()`);
  assert.equal(hardCells.length,3);
  for(const cell of hardCells){
    await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...cell,button:'left',buttons:1,clickCount:1});
    await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...cell,button:'left',buttons:0,clickCount:1});
    assert.equal(await evaluate(`window.localMessages.at(-1)?.path`),'/Users/demo/Documents/OSS/project/outputs/run/artifacts/copy-history.png');
  }
  // Claude's mouse policy + a real tmux redraw of hard-wrapped authorization
  // output. All values are synthetic; intercept opens without navigating.
  const authorization='https://example.invalid/v1/authorize?response_type=code&client_id=fixture-client&code_challenge=fixture-challenge&code_challenge_method=S256&redirect_uri=http%3A%2F%2Flocalhost%3A12345%2Fcallback&state=fixture-state';
  await evaluate(`window.frameElement.dataset.inlineSelection='false';window.frameElement.dataset.nativeSelection='false';window.openedUrls=[];window.open=url=>openedUrls.push(url);`);
  const columns=await evaluate('term.cols');
  const chunks=authorization.match(new RegExp('.{1,'+(columns-4)+'}','g'));
  assert.ok(chunks.length>1);
  tmux('send-keys','-t','check',"printf '%s\\n' '' "+chunks.map(s=>"'  "+s+"'").join(' '),'Enter');
  await pause(500);
  await evaluate('term.scrollToBottom()');
  const urlCells=await evaluate(`(()=>{const chunks=${JSON.stringify(chunks)};const b=term.buffer.active;const r=document.querySelector('.xterm-screen').getBoundingClientRect();return chunks.map(chunk=>{for(let y=b.viewportY;y<Math.min(b.length,b.viewportY+term.rows);y++){if(b.getLine(y).translateToString(true)==='  '+chunk)return {x:r.x+3.5*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows};}})})()`);
  assert.ok(urlCells.every(Boolean),'All hard-wrapped URL fragments are visible');
  for(const cell of urlCells) {
    await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...cell,buttons:0});
    assert.equal(await evaluate(`document.querySelector('.siling-link-highlight')?.children.length`),chunks.length);
    await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...cell,button:'left',buttons:1,clickCount:1});
    await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...cell,button:'left',buttons:0,clickCount:1});
    assert.equal(await evaluate(`openedUrls.at(-1)`),authorization,'Clicking every fragment preserves the exact OAuth query');
  }
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...urlCells[0],buttons:0});
  await screenshot('hard-wrapped-web-link');
  await evaluate(`window.frameElement.dataset.inlineSelection='true';window.frameElement.dataset.nativeSelection='true';`);
  console.log('PASS: hard-wrapped web URL click targets and hover ranges under Claude mouse policy');
  const barePath='/localhome/demo/work/'+('reports/'.repeat(18))+'test_report.md';
  const pathChunks=barePath.match(new RegExp('.{1,'+(columns-4)+'}','g'));
  const prefix='报告文件已更新完毕：';
  const firstWidth=columns-4-prefix.length*2;
  const announcedChunks=[barePath.slice(0,firstWidth),...barePath.slice(firstWidth).match(new RegExp('.{1,'+(columns-4)+'}','g'))];
  const bareRows=pathChunks.map((part,i)=>'  '+part+(i===pathChunks.length-1?'？':''));
  const announcedRows=announcedChunks.map((part,i)=>'  '+(i===0?prefix:'')+part);
  for (const pathRows of [bareRows,announcedRows]) {
    tmux('send-keys','-t','check',"printf '%s\\n' '' "+pathRows.map(s=>"'"+s+"'").join(' '),'Enter');
    await pause(500);
    await evaluate('term.scrollToBottom()');
    const pathCells=await evaluate(`(()=>{const rows=${JSON.stringify(pathRows)};const b=term.buffer.active;const r=document.querySelector('.xterm-screen').getBoundingClientRect();return rows.map(row=>{const indent=row.startsWith('  '+${JSON.stringify(prefix)})?2+${prefix.length*2}:2;for(let y=b.viewportY;y<Math.min(b.length,b.viewportY+term.rows);y++){if(b.getLine(y).translateToString(true)===row)return {x:r.x+(indent+1.5)*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows};}})})()`);
    assert.ok(pathCells.length>1 && pathCells.every(Boolean),'Bare SSH path fragments are visible');
    for(const cell of pathCells) {
      await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...cell,buttons:0});
      assert.equal(await evaluate(`document.querySelector('.siling-link-highlight')?.children.length`),pathRows.length);
      await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...cell,button:'left',buttons:1,clickCount:1});
      await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...cell,button:'left',buttons:0,clickCount:1});
      assert.equal(await evaluate(`window.localMessages.at(-1)?.path`),barePath);
    }
    await screenshot(pathRows===bareRows?'hard-wrapped-ssh-path':'announcement-ssh-path');
  }
  console.log('PASS: bare and Chinese-prefixed SSH paths highlight and open complete targets from every line');
  await evaluate(`window.frameElement.dataset.fileContext='true';window.silingFileContextForRow=()=> 'historical-ssh-context';`);
  tmux('send-keys','-t','check',"printf '%s\\n' 'reports/relative-result.md'",'Enter');
  await pause(500);
  let relativeCell;
  for(let attempt=0;attempt<50 && !relativeCell;attempt++){
    relativeCell=await evaluate(`(()=>{const b=term.buffer.active;const r=document.querySelector('.xterm-screen').getBoundingClientRect();for(let y=b.viewportY;y<b.length;y++){if(b.getLine(y).translateToString(true)==='reports/relative-result.md')return{x:r.x+2.5*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows};}})()`);
    if(!relativeCell)await pause(100);
  }
  assert.ok(relativeCell);
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...relativeCell,buttons:0});
  assert.ok(await evaluate(`document.querySelector('.siling-link-highlight')?.children.length>0`));
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...relativeCell,button:'left',buttons:1,clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...relativeCell,button:'left',buttons:0,clickCount:1});
  assert.deepEqual(await evaluate('window.localMessages.at(-1)'),{type:'siling:open-local-path',path:'reports/relative-result.md',context_id:'historical-ssh-context'});
  await evaluate(`window.frameElement.dataset.fileContext='false';`);
  console.log('PASS: relative file highlight and click retain historical SSH context');
  await evaluate(fs.readFileSync(path.join(root,'static/terminal-files.js'),'utf8'));
  await evaluate(`window.observedContext={id:'observed-remote',host:'fixture-ssh',cwd:'/remote'};window.fileDiscovery=[];window.fileObserver=SilingTerminalFiles.create({api:async(url,options={})=>{if(url.endsWith('/file-context'))return{configured:true,current:observedContext,settings:{auto_discover:true},contexts:[observedContext]};fileDiscovery.push(options.body);return{files:[],errors:[]};},openViewer:async()=>{}});window.observerFrame={dataset:{fileContext:'true'},isConnected:true,contentWindow:window,addEventListener:(name,fn)=>{window.startFileObserver=fn;}};fileObserver.attach(observerFrame,'browser-fixture');startFileObserver();`);
  tmux('send-keys','-t','check',"printf '%s\\n' '/tmp/remote-observer-report.md'",'Enter');
  await pause(4500);
  assert.ok(await evaluate(`fileObserver.states.get('browser-fixture').records.some(r=>r.text==='/tmp/remote-observer-report.md' && r.context==='observed-remote')`),'Real xterm markers capture remote output context: '+JSON.stringify(await evaluate(`({error:fileObserver.states.get('browser-fixture').error,records:fileObserver.states.get('browser-fixture').records.map(r=>({text:r.text,context:r.context})).slice(-6),bufferType:term.buffer.active.type})`)));
  await evaluate(`window.observedContext={id:'observed-local',host:'',cwd:'/local'};`);
  tmux('send-keys','-t','check',"printf '%s\\n' '/tmp/local-observer-report.md'",'Enter');
  await pause(4500);
  assert.ok(await evaluate(`fileObserver.states.get('browser-fixture').records.some(r=>r.text==='/tmp/remote-observer-report.md' && r.context==='observed-remote')`),'Remote output is not relabeled on host change');
  assert.ok(await evaluate(`fileObserver.states.get('browser-fixture').records.some(r=>r.text==='/tmp/local-observer-report.md' && r.context==='observed-local')`),'New output receives new local context');
  assert.ok(await evaluate(`fileDiscovery.some(body=>body?.automatic===true && body.text.includes('/tmp/local-observer-report.md'))`));
  await evaluate(`observerFrame.isConnected=false;fileObserver.states.get('browser-fixture').stop();`);
  console.log('PASS: real xterm observer records host transitions and triggers automatic discovery');
  // Exercise tmux history itself, not a separately rendered text snapshot.
  await evaluate(`window.silingTrimSelection=(previewOnly=false)=>fetch('http://127.0.0.1:${selectionPort}/trim?preview_only='+previewOnly).then(r=>r.json());window.silingReadSelection=()=>fetch('http://127.0.0.1:${selectionPort}').then(r=>r.json());Object.defineProperty(navigator.clipboard,'write',{value:async items=>{window.copiedText=await(await items[0].getType('text/plain')).text();}});void 0;`);
  tmux('send-keys','-t','check',"printf '   trim-command\\n'",'Enter');
  await pause(300);
  let trimLine=await evaluate(`(()=>{const b=term.buffer.active;for(let y=b.length-1;y>=0;y--){if(b.getLine(y)?.translateToString(true)==='   trim-command')return y-b.viewportY;}return -1;})()`);
  assert.ok(trimLine>=0);
  const geometry=await evaluate(`(()=>{const r=document.querySelector('.xterm-screen').getBoundingClientRect();return{x:r.x,y:r.y,w:r.width/term.cols,h:r.height/term.rows};})()`);
  const dragLine=async(row,start,end,modifiers=0,endRow=row,whileHeld=null)=>{
    const point=(col,y=row)=>({x:geometry.x+(col+.2)*geometry.w,y:geometry.y+(y+.5)*geometry.h});
    await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...point(start),button:'left',buttons:1,clickCount:1,modifiers});
    await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...point(end,endRow),button:'left',buttons:1,modifiers});
    await pause(100);
    if(whileHeld) {
      // Selection masks are painted on animation frames. Wait for that render
      // boundary while the mouse is still held, including on a busy CI host.
      await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      await whileHeld();
    }
    await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...point(end,endRow),button:'left',buttons:0,clickCount:1,modifiers});
    await pause(500);
  };
  await dragLine(trimLine,0,15,0,trimLine,async()=>{
    for(let i=0;i<40 && !(await evaluate(`document.querySelector('.siling-selection-margin').children.length`));i++) await pause(50);
    assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>0`),'tmux highlight trims while mouse is still held');
    assert.equal(tmux('display-message','-p','-t','check','#{selection_start_x}').trim(),'0','Live preview never moves the drag anchor');
    const readsAtRest=livePreviewReads;
    await pause(300);
    assert.ok(livePreviewReads-readsAtRest<=2,'Stationary drag does not continuously poll tmux');
    await screenshot('live-tmux-selection');
  });
  assert.equal(tmux('display-message','-p','-t','check','#{selection_start_x}').trim(),'3','tmux highlight skips leading spaces on mouse release');
  const trimmedCopy=await evaluate('silingReadSelection().then(r=>r.text)');
  assert.ok(trimmedCopy.startsWith('trim-command'),'tmux copied text matches adjusted highlight');
  await screenshot('trimmed-tmux-selection');
  tmux('send-keys','-t','check','-X','cancel');
  await pause(200);
  tmux('send-keys','-t','check',"printf '  if ready:\\n      run()\\n\\n  done()\\n'",'Enter');
  await pause(300);
  const tmuxCodeRow=await evaluate(`(()=>{const b=term.buffer.active;for(let y=b.length-1;y>=0;y--){if(b.getLine(y)?.translateToString(true)==='  if ready:')return y-b.viewportY;}return -1;})()`);
  assert.ok(tmuxCodeRow>=0);
  await dragLine(tmuxCodeRow,0,8,0,tmuxCodeRow+3,async()=>{
    for(let i=0;i<40 && !(await evaluate(`document.querySelector('.siling-selection-margin').children.length>=3`));i++) await pause(50);
    assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>=3`),'Multiline tmux margin updates before mouseup');
  });
  await evaluate('window.copiedText=undefined');
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'c',code:'KeyC',modifiers:4,windowsVirtualKeyCode:67});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'c',code:'KeyC',modifiers:4,windowsVirtualKeyCode:67});
  for(let i=0;i<50 && !(await evaluate('window.copiedText'));i++) await pause(50);
  assert.equal(await evaluate('window.copiedText'),'if ready:\n    run()\n\ndone()','tmux common indentation is removed while nested code indentation survives');
  assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>=3`),'tmux visible common margin is excluded from highlighting');
  await screenshot('multiline-dedent-tmux');
  tmux('send-keys','-t','check','-X','cancel');
  await pause(200);
  tmux('send-keys','-t','check','i=1; while [ $i -le 150 ]; do echo cross-screen-$i; i=$((i+1)); done','Enter');
  await pause(400);
  await evaluate('term.select(0,term.buffer.active.viewportY,5)');
  const area=await evaluate(`(()=>{const r=document.querySelector('.xterm-screen').getBoundingClientRect();return {x:r.x+10,top:r.y+10,bottom:r.bottom-35}})()`);
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:area.x,y:area.bottom,button:'left',buttons:1,clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:area.x+30,y:area.top+20,button:'left',buttons:1});
  for(let i=0;i<10;i++){
    await cdp('Input.dispatchMouseEvent',{type:'mouseWheel',x:area.x+30,y:area.top+20,buttons:1,deltaX:0,deltaY:-150});
    await pause(50);
  }
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:area.x+40,y:area.top+25,button:'left',buttons:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:area.x+40,y:area.top+25,button:'left',buttons:0,clickCount:1});
  await pause(100);
  assert.equal(tmux('display-message','-p','-t','check','#{selection_present}').trim(),'1','Drag release retains tmux selection');
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'c',code:'KeyC',modifiers:4,windowsVirtualKeyCode:67});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'c',code:'KeyC',modifiers:4,windowsVirtualKeyCode:67});
  for(let i=0;i<50;i++){if(await evaluate('!!window.copiedText'))break;await pause(100);}
  const copied=await evaluate('window.copiedText');
  assert.ok(copied && copied.split('\n').length>await evaluate('term.rows'),'Copy includes more than a screen of selected history');
  assert.equal(tmux('display-message','-p','-t','check','#{selection_present}').trim(),'1','Copy leaves the selection highlighted');
  await screenshot('inline-selection');
  console.log('PASS: real tmux drag + wheel cross-screen selection and copy, plus local links');
  // Populate xterm's normal scrollback for visible native-scrollbar evidence.
  // tmux's alternate-screen history above is separate from this browser buffer.
  await evaluate(`new Promise(resolve=>term.write('\x1b[?1049l\x1b[?1000l\x1b[?1002l\x1b[?1003l'+Array.from({length:200},(_,i)=>'Scrollbar fixture line '+i+'\\r\\n').join(''),resolve))`);
  await pause(150);
  await evaluate(`new Promise(resolve=>term.write('\\r\\n   trim-command\\r\\n',resolve))`);
  trimLine=await evaluate(`(()=>{const b=term.buffer.active;for(let y=b.length-1;y>=0;y--){if(b.getLine(y)?.translateToString(true)==='   trim-command')return y-b.viewportY;}return -1;})()`);
  await evaluate(`window.frameElement.dataset.inlineSelection='false'`);
  await dragLine(trimLine,0,15,0,trimLine,async()=>{
    assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>0`),'Native margin updates before mouseup');
    assert.equal(await evaluate('term.getSelectionPosition().start.x'),0,'Native live preview keeps the original anchor');
    assert.equal(await evaluate('term.getSelection()'),'trim-command');
    await screenshot('live-native-selection');
  });
  assert.equal(await evaluate('term.getSelection()'),'trim-command','Native selection skips leading spaces before copying');
  assert.equal(await evaluate('term.getSelectionPosition().start.x'),3);
  await screenshot('trimmed-native-selection');
  await dragLine(trimLine,15,0);
  assert.equal(await evaluate('term.getSelection()'),'trim-command','Reverse drag trims the same selection');
  await evaluate(`window.nativeTrimRow=term.getSelectionPosition().start.y;term.select(0,nativeTrimRow,term.cols+1);document.dispatchEvent(new MouseEvent('mouseup',{button:0,bubbles:true}))`);
  await pause(50);
  assert.match(await evaluate('term.getSelection()'),/^trim-command\r?\n/,'Multiline common margin is removed');
  assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>0`),'Excluded whitespace is removed from the highlight');
  await evaluate(`term.select(0,nativeTrimRow,3);document.dispatchEvent(new MouseEvent('mouseup',{button:0,bubbles:true}))`);
  await pause(50);
  assert.equal(await evaluate('term.getSelection()'),'   ','Whitespace-only selections stay selectable');
  await evaluate(`new Promise(resolve=>term.write('\\r\\n  if ready:\\r\\n      run()\\r\\n\\r\\n  done()\\r\\n',resolve))`);
  const codeRow=await evaluate(`(()=>{const b=term.buffer.active;for(let y=b.length-1;y>=0;y--){if(b.getLine(y)?.translateToString(true)==='  if ready:')return y;}return -1;})()`);
  const visibleCodeRow=codeRow-await evaluate('term.buffer.active.viewportY');
  await dragLine(visibleCodeRow,0,8,0,visibleCodeRow+3,async()=>{
    assert.equal(await evaluate('term.getSelection()'),'if ready:\n    run()\n\ndone()','Native multiline dedent follows the drag before release');
    assert.ok(await evaluate(`document.querySelector('.siling-selection-margin').children.length>=3`));
    await screenshot('live-native-multiline');
  });
  await dragLine(visibleCodeRow+3,8,0,0,visibleCodeRow,async()=>{
    assert.equal(await evaluate('term.getSelection()'),'if ready:\n    run()\n\ndone()','Reverse multiline drag also updates before release');
  });
  await evaluate(`term.select(0,${codeRow},term.cols*3+8);document.dispatchEvent(new MouseEvent('mouseup',{button:0,bubbles:true}))`);
  await pause(50);
  assert.equal(await evaluate('term.getSelection()'),'if ready:\n    run()\n\ndone()','Relative code indentation and blank lines survive');
  const copiedNative=await evaluate(`(()=>{const data=new DataTransfer();document.dispatchEvent(new ClipboardEvent('copy',{clipboardData:data,bubbles:true,cancelable:true}));return data.getData('text/plain');})()`);
  assert.equal(copiedNative,'if ready:\n    run()\n\ndone()','Browser copy uses the same dedented selection');
  await screenshot('multiline-dedent-native');
  await evaluate(`term.select(2,${codeRow},term.cols+10);document.dispatchEvent(new MouseEvent('mouseup',{button:0,bubbles:true}))`);
  await pause(50);
  assert.match(await evaluate('term.getSelection()'),/^if ready:\n      run/,'A first line selected without its margin prevents dedenting the following code');
  await evaluate(`term.select(0,${codeRow},term.cols+10);term._core._selectionService._activeSelectionMode=3;window.rectangleRaw=term._core._selectionService.selectionText;document.dispatchEvent(new MouseEvent('mouseup',{button:0,bubbles:true}))`);
  await pause(50);
  assert.equal(await evaluate('term.getSelection()'),await evaluate('window.rectangleRaw'),'Explicit rectangle selection stays unchanged');
  await evaluate(`term._core._selectionService._activeSelectionMode=0;term.clearSelection()`);
  console.log('PASS: multiline native and tmux dedent, matching highlights and clipboard, relative indentation, blanks, and rectangle preservation');
  console.log('PASS: native and tmux single-line highlights skip leading spaces, including reverse native drag');
  assert.ok(await evaluate(`{const v=document.querySelector('.xterm-viewport');v.scrollHeight>v.clientHeight}`),'Fixture has native scrollback');
  const beforeScroll=await evaluate('term.buffer.active.viewportY');
  await cdp('Input.dispatchMouseEvent',{type:'mouseWheel',x:600,y:300,deltaX:0,deltaY:-250});
  await pause(150);
  assert.ok(await evaluate('term.buffer.active.viewportY')<beforeScroll,'Wheel still scrolls native history');
  for(const [name,palette] of Object.entries(palettes)) {
    await evaluate(`term.options.theme=${JSON.stringify(palette)};term.refresh(0,term.rows-1)`);
    await pause(150);
    await screenshot('scrollbar-'+name);
  }
  console.log('PASS: native scrollback remains scrollable with themed scrollbar');
  // Losing focus while dragging out of an iframe must stop xterm's repeat timer.
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:100,y:200,button:'left',buttons:1,modifiers:1,clickCount:1});
  await evaluate(`document.dispatchEvent(new MouseEvent('mousemove',{clientX:100,clientY:-30,buttons:1,bubbles:true,altKey:true}))`);
  assert.ok(await evaluate('term._core._selectionService._dragScrollIntervalTimer!==undefined'),'Native drag owns an auto-scroll timer');
  assert.ok(await evaluate('term._core._selectionService._dragScrollAmount!==0'),'Dragging past viewport requests scrolling');
  await evaluate(`window.dispatchEvent(new Event('blur'))`);
  assert.equal(await evaluate('term._core._selectionService._dragScrollIntervalTimer'),undefined,'Blur stops native drag auto-scroll');
  const stoppedAt=await evaluate('term.buffer.active.viewportY');await pause(250);
  assert.equal(await evaluate('term.buffer.active.viewportY'),stoppedAt,'No runaway scrolling after leaving iframe');
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:100,y:200,button:'left',buttons:0,clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:100,y:200,button:'left',buttons:1,modifiers:1,clickCount:1});
  await evaluate(`document.dispatchEvent(new MouseEvent('mousemove',{clientX:200,clientY:250,buttons:1,bubbles:true,altKey:true}))`);
  const selectedBeforeZoom=await evaluate('term.getSelection()');
  assert.ok(selectedBeforeZoom.length>0,'Second drag still selects text after interruption');
  await evaluate('window.silingCancelTerminalDrag()');
  assert.equal(await evaluate('term._core._selectionService._dragScrollIntervalTimer'),undefined,'Zoom cancellation stops drag timer');
  assert.equal(await evaluate('term.getSelection()'),selectedBeforeZoom,'Canceling drag preserves text for copying');
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:200,y:250,button:'left',buttons:0,clickCount:1});
  console.log('PASS: leaving the iframe stops drag auto-scroll');

}finally{
  ws?.close();browser?.kill('SIGKILL');ttyd.kill();selectionServer.close();
  try{tmux('kill-server');}catch{}
  await pause(300);fs.rmSync(profile,{recursive:true,force:true});
}
