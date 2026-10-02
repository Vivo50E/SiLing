'use strict';
const crypto = require('node:crypto');
const fs = require('node:fs');
function keyFromSeed(seed) {
  seed = (seed || '').trim();
  if (!/^[A-Za-z0-9+/]{43}=$/.test(seed || '')) throw Error('Expected a base64 Ed25519 seed');
  return crypto.createPrivateKey({ key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(seed, 'base64')]), type: 'pkcs8', format: 'der' });
}
function publicKey(key) { return crypto.createPublicKey(key).export({ type: 'spki', format: 'der' }).subarray(-32).toString('base64'); }
function sign(data, key) { return crypto.sign(null, data, key).toString('base64'); }
function signedFeed(xml, key) {
  const bytes = Buffer.from(xml);
  return `${xml}<!-- sparkle-signatures:\nedSignature: ${sign(bytes, key)}\nlength: ${bytes.length}\n-->\n`;
}
function appcast({ tag, arch, build, size, signature, version, url }, key) {
  // All interpolated values are constrained; this function never accepts arbitrary XML.
  if (!/^desktop-v\d+\.\d+\.\d+-sparkle\.[a-f0-9]{12}$/.test(tag) || !['arm64','x64'].includes(arch)
      || !/^[1-9][0-9]*$/.test(String(build)) || !/^\d+\.\d+\.\d+$/.test(version)
      || !Number.isSafeInteger(size) || size < 1 || !/^[A-Za-z0-9+/]{86}==$/.test(signature)) throw Error('Invalid appcast metadata');
  const expected = `https://github.com/Vivo50E/SiLing/releases/download/${tag}/SiLing-${tag}-mac-${arch}.zip`;
  if (url && url !== expected) throw Error('Unexpected archive URL');
  return signedFeed(`<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><title>SiLing</title><item><title>SiLing ${version} (build ${build})</title><sparkle:version>${build}</sparkle:version><sparkle:shortVersionString>${version}</sparkle:shortVersionString><sparkle:minimumSystemVersion>12.0</sparkle:minimumSystemVersion><enclosure url="${expected}" length="${size}" type="application/octet-stream" sparkle:edSignature="${signature}"/></item></channel></rss>\n`, key);
}
if (require.main === module) {
  try {
    const key = keyFromSeed(process.env.SILING_UPDATE_PRIVATE_KEY);
    const pinned = require('./sparkle-config.json').publicKey;
    if (!pinned || publicKey(key) !== pinned) throw Error('Release signing key does not match the pinned public key');
    const [archive, tag, arch, build] = process.argv.slice(2);
    const bytes = fs.readFileSync(archive);
    process.stdout.write(appcast({ tag, arch, build, size: bytes.length, signature: sign(bytes, key), version: require('./package.json').version }, key));
  } catch { console.error('Release signing failed: check key configuration and release inputs.'); process.exitCode = 1; }
}
module.exports = { keyFromSeed, publicKey, sign, signedFeed, appcast };
