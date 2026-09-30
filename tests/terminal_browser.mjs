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
const selectionServer=http.createServer((req,res)=>{
  try {
    const text=execFileSync(python,['-c',"import json;from agent_orchestrator.dashboard import _tmux_copy_selection;print(json.dumps({'text':_tmux_copy_selection('check')}))"],{cwd:root,env:{...process.env,TMUX:`${socket},0,0`},encoding:'utf8'});
    res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Content-Type','application/json');res.end(text);
  }catch(error){res.writeHead(500);res.end(String(error));}
});
await new Promise(r=>selectionServer.listen(0,'127.0.0.1',r));
const selectionPort=selectionServer.address().port;
const ttyd=spawn('ttyd',['-i','127.0.0.1','-p',String(port),'-W','tmux','-S',socket,'attach','-t','check'],{stdio:'ignore'});
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
  const relativeCell=await evaluate(`(()=>{const b=term.buffer.active;const r=document.querySelector('.xterm-screen').getBoundingClientRect();for(let y=b.viewportY;y<b.length;y++){if(b.getLine(y).translateToString(true)==='reports/relative-result.md')return{x:r.x+2.5*r.width/term.cols,y:r.y+(y-b.viewportY+.5)*r.height/term.rows};}})()`);
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
  await evaluate(`window.silingReadSelection=()=>fetch('http://127.0.0.1:${selectionPort}').then(r=>r.json());Object.defineProperty(navigator.clipboard,'write',{value:async items=>{window.copiedText=await(await items[0].getType('text/plain')).text();}});void 0;`);
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
