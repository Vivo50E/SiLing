const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const settle = () => new Promise(setImmediate);
async function fixture() {
  const timers = new Map(); let serial = 0, now = 1000, writes, load;
  let calls = 0, disposed = 0, context = 'local', deferred;
  const sandbox = {window:{}, document:{documentElement:{lang:'en'}, hidden:false},
    localStorage:{getItem:()=>null}, AbortController,
    Date:{now:()=>now}, setInterval:(fn)=>{timers.set(++serial,fn);return serial;}, clearInterval:id=>timers.delete(id)};
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('static/terminal-files.js','utf8'),sandbox);
  const controller = sandbox.window.SilingTerminalFiles.create({api:async (_url, options={})=>{
    calls++; if(deferred) await deferred.promise;
    if(options.signal?.aborted) throw new Error('aborted');
    return {configured:true,current:{id:context},settings:{auto_discover:false}};
  }});
  const buffer={type:'normal',baseY:0,cursorY:0,length:1,getLine:()=>({translateToString:()=>'/tmp/example.md'})};
  const term={buffer:{active:buffer},rows:1,
    registerMarker:()=>({line:0,isDisposed:false,dispose(){this.isDisposed=true;}}),
    onWriteParsed:fn=>{writes=fn;return {dispose(){disposed++;}};},
    parser:{registerCsiHandler:()=>({dispose(){disposed++;}})}};
  const frame={dataset:{fileContext:'true'},isConnected:true,hiddenPane:false,contentWindow:{term},
    closest(){return this.hiddenPane ? {} : null;},
    addEventListener:(_e,fn)=>load=fn,removeEventListener:(_e,fn)=>{if(load===fn)load=null;}};
  controller.attach(frame,'test');load();await settle();
  const tick=async(ms=4000)=>{now+=ms;for(const fn of [...timers.values()])fn();await settle();};
  return {controller,frame,sandbox,timers,tick,emit:()=>writes?.(),calls:()=>calls,disposed:()=>disposed,
    defer(){let resolve;deferred={promise:new Promise(r=>resolve=r)};return resolve;},load:()=>load};
}
(async()=>{
  const f=await fixture();await f.tick();const base=f.calls();
  await f.tick();await f.tick();assert.equal(f.calls(),base,'Idle terminal must not poll context');
  f.emit();await f.tick();assert.equal(f.calls(),base+1,'Output triggers a fresh context');
  f.frame.hiddenPane=true;f.emit();const hidden=f.calls();await f.tick();assert.equal(f.calls(),hidden,'Hidden output is throttled');
  await f.tick(30000);assert.equal(f.calls(),hidden+1,'Hidden output still receives bounded maintenance');
  f.sandbox.document.hidden=true;f.frame.hiddenPane=false;f.emit();const background=f.calls();await f.tick();assert.equal(f.calls(),background,'Background tab uses the same throttle');
  f.sandbox.document.hidden=false;await f.tick();assert.equal(f.calls(),background+1,'Returning shows pending output promptly');
  const old=f.controller.states.get('test');f.controller.detach('test');
  assert.equal(f.controller.states.size,0);assert.equal(f.timers.size,0);assert.equal(old.frame,null);
  assert.equal(old.stop,null);assert.equal(old.records.length,0);assert.equal(old.lastLine,null);
  assert.ok(f.disposed()>=3);assert.equal(f.load(),null,'Detach removes the frame load callback');
  assert.equal(f.frame.contentWindow.silingFileContextForRow,undefined);
  const g=await fixture();const release=g.defer();g.emit();await g.tick();
  const stale=g.controller.states.get('test');g.controller.detach('test');release();await settle();
  assert.equal(stale.frame,null);assert.equal(stale.records.length,0,'Late context response cannot resurrect detached markers');
  const h=await fixture();h.frame.isConnected=false;await h.tick();
  assert.equal(h.controller.states.size,0,'Externally removed/mobile frame is cleaned automatically');
  console.log('PASS: idle suppression, hidden throttling, foreground catchup, detach and in-flight cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
