'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { keyFromSeed, publicKey } = require('./sign-release.cjs');
const file = process.argv[2] || path.join(os.homedir(), '.config/siling/desktop-update-key');
const configFile = path.join(__dirname, 'sparkle-config.json');
const config = JSON.parse(fs.readFileSync(configFile));
try {
  let seed;
  if (fs.existsSync(file)) {
    if (!fs.lstatSync(file).isFile()) throw Error('Key must be a regular file');
    if ((fs.statSync(file).mode & 0o077) !== 0) throw Error('Key permissions must be 0600');
    seed = fs.readFileSync(file, 'utf8').trim();
  } else {
    if (config.publicKey) throw Error('Public key already pinned: restore the existing private key instead of rotating it');
    seed = crypto.randomBytes(32).toString('base64');
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.writeFileSync(file, seed + '\n', { flag: 'wx', mode: 0o600 });
  }
  const pub = publicKey(keyFromSeed(seed));
  if (config.publicKey && config.publicKey !== pub) throw Error('Private key does not match pinned public key');
  config.publicKey = pub;
  fs.writeFileSync(configFile, JSON.stringify(config, null, 2) + '\n');
  console.log('Public update key pinned. Private key stored at: ' + file);
  console.log('Back up the private key securely; configure it as SILING_UPDATE_PRIVATE_KEY in the desktop-updates GitHub environment.');
} catch (error) { console.error(error.message); process.exitCode = 1; }
