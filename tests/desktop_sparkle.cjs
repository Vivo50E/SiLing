'use strict';
// Real Sparkle replacement of two disposable Electron app bundles. No user sessions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const crypto = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');
const { createRequire } = require('node:module');
const requireDesktop = createRequire(path.resolve(__dirname, '../apps/desktop/package.json'));
const { createPackage } = requireDesktop('@electron/asar');
const signing = require('../apps/desktop/sign-release.cjs');
const sparkle = require('../apps/desktop/sparkle-build.cjs');
const baseline = process.argv[2] || path.resolve(__dirname, `../dist/desktop/SiLing-darwin-${process.arch}/SiLing.app`);
if (!baseline || process.platform !== 'darwin') throw Error('Provide a packaged SiLing.app on macOS');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-sparkle-test-'));
const bundleID = 'com.vivo50e.siling.fixture.' + crypto.randomBytes(6).toString('hex');
const key = signing.keyFromSeed(crypto.randomBytes(32).toString('base64'));
const publicKey = signing.publicKey(key);
let sdkRoot, server, processA, driver, state = 'good', zip, goodFeed, badFeed;
const pids = new Set();
const run = (cmd,args) => execFileSync(cmd,args,{encoding:'utf8',stdio:['ignore','pipe','pipe']});
const pause = ms => new Promise(r => setTimeout(r,ms));
async function wait(check,label) { for(let i=0;i<300;i++){if(await check())return;await pause(100);}throw Error('Timeout: '+label); }
const live = pid => {try{process.kill(pid,0);return true;}catch{return false;}};
const installed = path.join(root,'installed/SiLing.app');
const profile = path.join(root,'profile');fs.mkdirSync(profile);fs.writeFileSync(path.join(profile,'connection-fixture'),'preserve me');
const marker = path.join(root,'started.json');
async function app(target,version,feed) {
  fs.mkdirSync(path.dirname(target),{recursive:true});run('/usr/bin/ditto',[baseline,target]);
  const plist = path.join(target,'Contents/Info.plist');
  for(const [name,value] of Object.entries({CFBundleIdentifier:bundleID,CFBundleVersion:version,SUPublicEDKey:publicKey,SUFeedURL:feed}))
    run('/usr/bin/plutil',['-replace',name,'-string',String(value),plist]);
  for(const [name,value] of Object.entries({SUEnableAutomaticChecks:false,SURequireSignedFeed:true,SUVerifyUpdateBeforeExtraction:true}))
    run('/usr/bin/plutil',['-replace',name,'-bool',String(value),plist]);
  const source = path.join(root,'source'+version);fs.mkdirSync(source);
  fs.writeFileSync(path.join(source,'package.json'),JSON.stringify({name:'siling-update-fixture',version:'0.3.0',main:'main.cjs'}));
  fs.writeFileSync(path.join(source,'main.cjs'),`const {app,BrowserWindow}=require('electron');const fs=require('fs');app.setPath('userData',${JSON.stringify(profile)});app.whenReady().then(()=>{fs.writeFileSync(${JSON.stringify(marker)},JSON.stringify({version:${JSON.stringify(version)},pid:process.pid}));new BrowserWindow({show:false});});`);
  fs.rmSync(path.join(target,'Contents/Resources/app.asar'));
  await createPackage(source,path.join(target,'Contents/Resources/app.asar'));
  run('/usr/bin/codesign',['--force','--deep','--sign','-',target]);
}
async function update(expected) {
  driver=spawn(path.join(root,'TestUpdater.app/Contents/MacOS/TestUpdater'),[installed],{stdio:['ignore','pipe','pipe']});
  let output='';driver.stdout.on('data',d=>output+=d);driver.stderr.on('data',d=>output+=d);
  const timer=setTimeout(()=>driver.kill('SIGKILL'),60000);
  const code=await new Promise(r=>driver.once('exit',r));clearTimeout(timer);
  if(code!==expected)throw Error('Update driver '+code+'\n'+output);
  return output;
}
(async()=>{
  try {
    sdkRoot = await sparkle.sdk();
    const helper=path.join(root,'TestUpdater.app');
    sparkle.buildHelper(sdkRoot,helper,process.arch);
    run('/usr/bin/plutil',['-replace','CFBundleIdentifier','-string',bundleID+'.driver',path.join(helper,'Contents/Info.plist')]);
    run('/usr/bin/plutil',['-replace','CFBundleExecutable','-string','TestUpdater',path.join(helper,'Contents/Info.plist')]);
    run('/usr/bin/xcrun',['clang','-fobjc-arc','-framework','Cocoa','-framework','Sparkle','-F',sdkRoot,'-Wl,-rpath,@executable_path/../Frameworks',path.join(__dirname,'sparkle_update_driver.m'),'-o',path.join(helper,'Contents/MacOS/TestUpdater')]);
    run('/usr/bin/codesign',['--force','--deep','--sign','-',helper]);
    server=http.createServer((req,res)=>{
      if(req.url==='/app.zip'){res.setHeader('Content-Type','application/zip');res.end(state==='tampered'?Buffer.concat([zip.subarray(0,-1),Buffer.from([zip.at(-1)^1])]):zip);}
      else {res.setHeader('Content-Type','application/xml');res.end(state==='wrong-key'?badFeed:goodFeed);}
    });
    await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
    await app(installed,'1',base+'/feed.xml');
    const productionHelper=path.join(installed,'Contents/Resources/SiLingUpdater.app/Contents/MacOS/SiLingUpdater');
    if(fs.existsSync(productionHelper)) {
      const probe=spawn(productionHelper,[installed,String(process.pid)],{stdio:['pipe','pipe','pipe']});
      pids.add(probe.pid); let events=''; probe.stdout.on('data',data=>events+=data);
      await wait(()=>events.includes('{"event":"ready"}'),'packaged helper readiness');
      probe.stdin.end();await new Promise(resolve=>probe.once('exit',resolve));
      console.log('PASS: packaged production helper starts and exits through its private pipe');
    }
    const replacement=path.join(root,'new/SiLing.app');await app(replacement,'2',base+'/feed.xml');
    const archive=path.join(root,'app.zip');run('/usr/bin/ditto',['-c','-k','--sequesterRsrc','--keepParent',replacement,archive]);zip=fs.readFileSync(archive);
    const xml=`<?xml version="1.0"?><rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><title>Fixture</title><item><title>Fixture 2</title><sparkle:version>2</sparkle:version><enclosure url="${base}/app.zip" length="${zip.length}" type="application/octet-stream" sparkle:edSignature="${signing.sign(zip,key)}"/></item></channel></rss>\n`;
    goodFeed=signing.signedFeed(xml,key);
    badFeed=signing.signedFeed(xml,signing.keyFromSeed(crypto.randomBytes(32).toString('base64')));
    processA=spawn(path.join(installed,'Contents/MacOS/SiLing'),[],{stdio:'ignore'});pids.add(processA.pid);
    await wait(()=>fs.existsSync(marker),'version A launch');assert.equal(JSON.parse(fs.readFileSync(marker)).version,'1');
    state='wrong-key';await update(2);assert.equal(JSON.parse(fs.readFileSync(marker)).version,'1');assert.ok(live(processA.pid));
    console.log('PASS: wrong feed signing key rejected, old app preserved');
    await pause(2000);
    state='tampered';await update(2);assert.equal(JSON.parse(fs.readFileSync(marker)).version,'1');assert.ok(live(processA.pid));
    console.log('PASS: modified ZIP rejected before installation, old app preserved');
    await pause(2000);
    state='good';await update(0);
    await wait(()=>JSON.parse(fs.readFileSync(marker)).version==='2','version B relaunch');
    const next=JSON.parse(fs.readFileSync(marker));pids.add(next.pid);
    assert.notEqual(next.pid,processA.pid);await wait(()=>!live(processA.pid),'old process exit');
    assert.equal(run('/usr/bin/plutil',['-extract','CFBundleVersion','raw','-o','-',path.join(installed,'Contents/Info.plist')]).trim(),'2');
    assert.equal(fs.readFileSync(path.join(profile,'connection-fixture'),'utf8'),'preserve me');
    console.log('PASS: real Sparkle Ed25519 verification, atomic Electron A → B replacement, relaunch and profile preservation');
  } finally {
    if(fs.existsSync(marker))try{pids.add(JSON.parse(fs.readFileSync(marker)).pid);}catch{}
    for(const pid of pids)try{process.kill(pid,'SIGTERM');}catch{}
    driver?.kill();server?.close();
    // Sparkle uses the fixture bundle ID for caches/preferences even with a custom app profile.
    fs.rmSync(path.join(os.homedir(), 'Library/Caches', bundleID), {recursive:true,force:true});
    fs.rmSync(path.join(os.homedir(), 'Library/Preferences', bundleID+'.plist'), {force:true});
    fs.rmSync(path.join(os.homedir(), 'Library/Preferences', bundleID+'.driver.plist'), {force:true});
    if(sdkRoot)fs.rmSync(sdkRoot,{recursive:true,force:true});
    // Keep failed fixtures for diagnosis only when explicitly requested.
    if(process.env.KEEP_SPARKLE_FIXTURE!=='1')fs.rmSync(root,{recursive:true,force:true});
    else console.log('Fixture:',root);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
