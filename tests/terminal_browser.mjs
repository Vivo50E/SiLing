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
}finally{
  ws?.close();browser?.kill('SIGKILL');ttyd.kill();selectionServer.close();
  try{tmux('kill-server');}catch{}
  await pause(300);fs.rmSync(profile,{recursive:true,force:true});
}
