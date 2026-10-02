'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const crypto = require('node:crypto');
const { createUpdater } = require('../apps/desktop/updates.cjs');
const { configuration } = require('../apps/desktop/sparkle-build.cjs');
const signing = require('../apps/desktop/sign-release.cjs');
function fixture(options = {}) {
  const child = new EventEmitter();child.stdout = new PassThrough(); child.stdin = new PassThrough();
  child.kill = () => { child.emit('exit',1); };
  const writes=[];child.stdin.on('data', d => writes.push(d.toString()));
  const dialogs=[], launches=[];
  const updater=createUpdater({ app: { isPackaged:true, getLocale:()=> 'zh' }, dialog:{ showMessageBox:async o=>dialogs.push(o) } },
    {updateChannel:'sparkle'}, { platform:'darwin', resources:'/fixture/resources', host:'/fixture/SiLing.app', exists:()=>true,
      spawn:(...args)=>{launches.push(args);return child;}, ...options });
  return {child, writes, dialogs, launches, updater};
}
test('one helper serves background startup and coalesced menu checks, using only fixed commands', async()=>{
  const f=fixture();f.updater.start();f.updater.start();
  await f.updater.menu.click();await f.updater.menu.click();assert.equal(f.launches.length,1);
  assert.equal(f.writes.length,0);
  f.child.stdout.write('{"event":"rea');f.child.stdout.write('dy"}\n');
  assert.deepEqual(f.writes,['check\n']);
  await f.updater.menu.click();assert.equal(f.writes.length,2);
  assert.deepEqual(f.launches[0][1],['/fixture/SiLing.app',String(process.pid)]);
  f.updater.dispose();assert.equal(f.child.stdin.writableEnded,true);
});
test('helper launch errors are retryable and never expose raw errors', async()=>{
  const f=fixture();await f.updater.menu.click();f.child.emit('error',Error('secret URL'));
  assert.equal(f.dialogs.length,1);assert.ok(!JSON.stringify(f.dialogs).includes('secret'));
  await f.updater.menu.click();assert.equal(f.launches.length,2);f.updater.dispose();
});
test('missing helper and unsupported platform never spawn',async()=>{
  for(const options of [{exists:()=>false},{platform:'linux'}]){
    const f=fixture(options);f.updater.start();await f.updater.menu.click();
    assert.equal(f.launches.length,0);assert.equal(f.dialogs.length,1);f.updater.dispose();
  }
});
test('build configuration accepts pinned keys and HTTPS, refusing credentials and unsafe feeds',()=>{
  const key=crypto.randomBytes(32).toString('base64');
  const good={SILING_UPDATE_PUBLIC_KEY:key,SILING_UPDATE_FEED_URL:'https://example.com/appcast-{arch}.xml'};
  assert.equal(configuration(good).feed,'https://example.com/appcast-{arch}.xml');
  for(const url of ['http://remote.example/a','file:///a','https://user:secret@example.com/a'])
    assert.throws(()=>configuration({...good,SILING_UPDATE_FEED_URL:url}));
  assert.throws(()=>configuration({...good,SILING_UPDATE_PUBLIC_KEY:'bad'}));
});
test('Ed25519 archive and appcast signatures bind exact bytes; different keys and tampering fail',()=>{
  const key=signing.keyFromSeed(crypto.randomBytes(32).toString('base64'));
  const other=signing.keyFromSeed(crypto.randomBytes(32).toString('base64'));
  const bytes=Buffer.from('fixture archive'), signature=signing.sign(bytes,key);
  assert.equal(crypto.verify(null,bytes,crypto.createPublicKey(key),Buffer.from(signature,'base64')),true);
  assert.equal(crypto.verify(null,Buffer.from('tampered'),crypto.createPublicKey(key),Buffer.from(signature,'base64')),false);
  assert.equal(crypto.verify(null,bytes,crypto.createPublicKey(other),Buffer.from(signature,'base64')),false);
  const xml=signing.appcast({tag:'desktop-v0.3.0-sparkle.'+'a'.repeat(12),arch:'arm64',build:'42',version:'0.3.0',size:bytes.length,signature},key);
  const match=/<!-- sparkle-signatures:\nedSignature: (\S+)\nlength: (\d+)\n-->/.exec(xml);
  assert.ok(match);
  assert.equal(crypto.verify(null,Buffer.from(xml).subarray(0,Number(match[2])),crypto.createPublicKey(key),Buffer.from(match[1],'base64')),true);
  assert.match(xml,/<sparkle:version>42<\/sparkle:version>/);
  assert.match(xml,/mac-arm64.zip/);
  assert.throws(()=>signing.keyFromSeed('bad'));
  const seed=crypto.randomBytes(32).toString('base64');
  assert.equal(signing.publicKey(signing.keyFromSeed(seed+'\n')),signing.publicKey(signing.keyFromSeed(seed)));
});
