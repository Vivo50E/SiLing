'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const VERSION = '2.10.0';
const DIGEST = 'c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c';
async function sdk() {
  const archive = await fetch(`https://github.com/sparkle-project/Sparkle/releases/download/${VERSION}/Sparkle-${VERSION}.tar.xz`, { signal: AbortSignal.timeout(120000) });
  if (!archive.ok) throw Error('Sparkle download failed');
  const chunks = []; let length = 0;
  for await (const chunk of archive.body) {
    length += chunk.length; if (length > 64 * 1024 * 1024) throw Error('Sparkle archive too large');
    chunks.push(chunk);
  }
  const bytes = Buffer.concat(chunks);
  if (createHash('sha256').update(bytes).digest('hex') !== DIGEST) throw Error('Sparkle checksum mismatch');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-sparkle-sdk-'));
  try {
    const file = path.join(root, 'sdk.tar.xz'); fs.writeFileSync(file, bytes);
    execFileSync('/usr/bin/tar', ['-xf', file, '-C', root]);
    return root;
  } catch (error) { fs.rmSync(root, { recursive: true, force: true }); throw error; }
}
function configuration(env = process.env) {
  const stored = require('./sparkle-config.json');
  const publicKey = env.SILING_UPDATE_PUBLIC_KEY || stored.publicKey;
  const feed = env.SILING_UPDATE_FEED_URL || stored.feedURL;
  if (!publicKey) return null;
  if (!/^[A-Za-z0-9+/]{43}=$/.test(publicKey) || Buffer.from(publicKey, 'base64').length !== 32) throw Error('Invalid update public key');
  const url = new URL(feed);
  if (url.username || url.password || !(url.protocol === 'https:' || url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))) throw Error('Update feed must use HTTPS (loopback HTTP allowed for tests)');
  return { publicKey, feed: url.href.replaceAll('%7Barch%7D', '{arch}') };
}
function buildHelper(root, target, arch) {
  const contents = path.join(target, 'Contents');
  fs.mkdirSync(path.join(contents, 'MacOS'), { recursive: true });
  fs.mkdirSync(path.join(contents, 'Frameworks'));
  fs.mkdirSync(path.join(contents, 'Resources'));
  fs.copyFileSync(path.join(root, 'LICENSE'), path.join(contents, 'Resources/Sparkle-LICENSE'));
  execFileSync('/usr/bin/ditto', [path.join(root, 'Sparkle.framework'), path.join(contents, 'Frameworks/Sparkle.framework')]);
  fs.writeFileSync(path.join(contents, 'Info.plist'), `<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.vivo50e.siling.updater</string>
<key>CFBundleExecutable</key><string>SiLingUpdater</string>
<key>CFBundleName</key><string>SiLing Updater</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSUIElement</key><true/>
</dict></plist>`);
  execFileSync('/usr/bin/xcrun', ['clang', '-arch', arch === 'x64' ? 'x86_64' : 'arm64',
    '-mmacosx-version-min=12.0', '-fobjc-arc', '-framework', 'Cocoa', '-framework', 'Sparkle',
    '-F', root, '-Wl,-rpath,@executable_path/../Frameworks',
    path.join(__dirname, 'native/updater.m'), '-o', path.join(contents, 'MacOS/SiLingUpdater')], { stdio: 'pipe' });
}
module.exports = { VERSION, DIGEST, sdk, configuration, buildHelper };
