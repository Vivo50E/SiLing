'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const metadata = require('./package.json');
const sparkle = require('./sparkle-build.cjs');

// Never package a checkout, node_modules, local config, tokens or transcripts.
const RUNTIME_FILES = Object.freeze(['main.cjs', 'preload.cjs', 'policy.cjs',
  'browser-host.cjs', 'updates.cjs', 'connection.cjs', 'connection-preload.cjs', 'connection.html', 'connection.js']);

function stageApp(source, target, license, buildCommit = '', updateChannel = '', buildNumber = metadata.version) {
  fs.mkdirSync(target, { recursive: true });
  for (const file of RUNTIME_FILES) {
    const input = path.join(source, file);
    if (!fs.lstatSync(input).isFile()) throw Error(`Not a regular runtime file: ${file}`);
    fs.copyFileSync(input, path.join(target, file));
  }
  fs.copyFileSync(license, path.join(target, 'LICENSE'));
  fs.writeFileSync(path.join(target, 'package.json'), JSON.stringify({
    name: metadata.name, productName: metadata.productName, version: metadata.version,
    description: metadata.description, main: metadata.main, license: 'MIT', buildCommit, updateChannel, buildNumber,
  }, null, 2) + '\n');
}

function packageOptions(dir, out, icon, arch) {
  if (!['arm64', 'x64'].includes(arch)) throw Error('Use --arch arm64 or --arch x64');
  return { dir, out, icon, arch, platform: 'darwin', name: 'SiLing', executableName: 'SiLing',
    appBundleId: 'com.vivo50e.siling', helperBundleId: 'com.vivo50e.siling.helper',
    appVersion: metadata.version, buildVersion: metadata.version,
    electronVersion: metadata.devDependencies.electron, asar: true, prune: false,
    overwrite: false, darwinDarkModeSupport: true,
    appCategoryType: 'public.app-category.developer-tools',
    appCopyright: 'Copyright © 2026 Agent Orchestrator contributors and SiLing contributors',
    extendInfo: { CFBundleDisplayName: 'SiLing', CFBundleName: 'SiLing' },
    // Local ad-hoc identity only: never select a certificate from the user's keychain.
    osxSign: { identity: '-', identityValidation: false, continueOnError: false,
      preAutoEntitlements: false, preEmbedProvisioningProfile: false,
      optionsForFile: () => ({ hardenedRuntime: false, entitlements: [], timestamp: 'none' }) },
  };
}

async function build(args = process.argv.slice(2)) {
  if (process.platform !== 'darwin') throw Error('Build this macOS application on a Mac');
  let out = path.resolve(__dirname, '../../dist/desktop'), arch = process.arch;
  for (let i = 0; i < args.length; i += 2) {
    if (!['--out', '--arch'].includes(args[i]) || !args[i + 1]) throw Error('Usage: package:mac -- [--out path] [--arch arm64|x64]');
    if (args[i] === '--out') out = path.resolve(args[i + 1]);
    else arch = args[i + 1];
  }
  packageOptions('', out, '', arch);
  const update = sparkle.configuration();
  let sdkRoot;
  const destination = path.join(out, `SiLing-darwin-${arch}`);
  if (fs.existsSync(destination)) throw Error('Output already exists; choose a new --out directory');
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-package-'));
  try {
    const stage = path.join(temporary, 'app');
    const root = path.resolve(__dirname, '../..');
    let commit = '';
    try {
      const clean = !execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
      if (clean) commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
    } catch { /* Source archives remain buildable, with an unknown identity. */ }
    let buildNumber = metadata.version;
    let helper;
    if (update) {
      buildNumber = process.env.SILING_UPDATE_BUILD_NUMBER || execFileSync('git', ['rev-list', '--count', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
      if (!/^[1-9][0-9]{0,9}$/.test(buildNumber)) throw Error('Update builds require a positive numeric build number');
      sdkRoot = await sparkle.sdk();
      helper = path.join(temporary, 'SiLingUpdater.app');
      sparkle.buildHelper(sdkRoot, helper, arch);
    }
    stageApp(__dirname, stage, path.resolve(root, 'LICENSE'), commit, update ? 'sparkle' : '', buildNumber);
    const iconset = path.join(temporary, 'SiLing.iconset');
    fs.mkdirSync(iconset);
    const sourceIcon = path.resolve(__dirname, '../../static/icons/orchestrator-512.png');
    for (const size of [16, 32, 128, 256, 512]) {
      for (const scale of [1, 2]) {
        const file = `icon_${size}x${size}${scale === 2 ? '@2x' : ''}.png`;
        execFileSync('/usr/bin/sips', ['-z', String(size * scale), String(size * scale),
          sourceIcon, '--out', path.join(iconset, file)], { stdio: 'pipe' });
      }
    }
    const icon = path.join(temporary, 'SiLing.icns');
    execFileSync('/usr/bin/iconutil', ['-c', 'icns', iconset, '-o', icon]);
    const { packager } = await import('@electron/packager');
    const options = packageOptions(stage, out, icon, arch);
    if (update) {
      options.buildVersion = buildNumber;
      // extraResource uses fs.cp without verbatimSymlinks and rewrites framework
      // links to staging paths. ditto preserves the relative bundle links.
      options.afterCopy = [async ({ buildPath }) => {
        execFileSync('/usr/bin/ditto', [helper, path.join(path.dirname(buildPath), 'SiLingUpdater.app')]);
      }];
      options.extendInfo = { ...options.extendInfo, SUPublicEDKey: update.publicKey,
        SUFeedURL: update.feed.replaceAll('{arch}', arch), SUEnableAutomaticChecks: true,
        SUAutomaticallyUpdate: true, SUAllowsAutomaticUpdates: true, SUEnableSystemProfiling: false,
        SUUpdateCheckInterval: 14400, SURequireSignedFeed: true, SUVerifyUpdateBeforeExtraction: true,
        SUSignedFeedFailureExpirationInterval: 0 };
    }
    const results = await packager(options);
    for (const result of results) {
      const bundle = path.join(result, 'SiLing.app');
      execFileSync('/usr/bin/codesign', ['--verify', '--deep', '--strict', bundle], { stdio: 'pipe' });
      console.log(bundle);
    }
    console.log('Local ad-hoc build; Sparkle updates use Ed25519 signatures. No installation or service restart.');
  } finally {
    if (sdkRoot) fs.rmSync(sdkRoot, { recursive: true, force: true });
    // Only the temporary staging directory created by this invocation.
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

module.exports = { RUNTIME_FILES, stageApp, packageOptions };
if (require.main === module) build().catch(error => { console.error(error.message); process.exitCode = 1; });
