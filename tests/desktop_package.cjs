'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { RUNTIME_FILES, stageApp, packageOptions } = require('../apps/desktop/package-mac.cjs');
const { readConnection, writeConnection, trustedSetup, setupURL } = require('../apps/desktop/connection.cjs');
const source = path.resolve(__dirname, '../apps/desktop');
const metadata = require('../apps/desktop/package.json');

test('macOS bundle has explicit SiLing branding and only local ad-hoc signing', () => {
  const options = packageOptions('/stage', '/output', '/icon.icns', 'arm64');
  assert.equal(options.name, 'SiLing');
  assert.equal(options.executableName, 'SiLing');
  assert.equal(options.appBundleId, 'com.vivo50e.siling');
  assert.equal(options.appVersion, metadata.version);
  assert.equal(options.buildVersion, metadata.version);
  assert.equal(options.extendInfo.CFBundleDisplayName, 'SiLing');
  assert.equal(options.overwrite, false);
  assert.equal(options.osxSign.identity, '-');
  assert.equal(options.osxSign.identityValidation, false);
  assert.equal(options.osxSign.continueOnError, false);
  assert.equal(options.osxSign.preEmbedProvisioningProfile, false);
  assert.deepEqual(options.osxSign.optionsForFile().entitlements, []);
  assert.equal(options.osxNotarize, undefined);
  assert.equal(packageOptions('/a', '/b', '/c', 'x64').arch, 'x64');
  assert.throws(() => packageOptions('/a', '/b', '/c', '../escape'));
});
test('staging only copies explicit runtime files and MIT notice, never local secrets', t => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-stage-test-'));
  t.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const fixture = path.join(temporary, 'source'), target = path.join(temporary, 'staged');
  fs.mkdirSync(fixture);
  for (const file of RUNTIME_FILES) fs.copyFileSync(path.join(source, file), path.join(fixture, file));
  for (const file of ['.env', 'connection.json', 'dashboard.local.json', 'package-lock.json']) fs.writeFileSync(path.join(fixture, file), 'private fixture');
  fs.mkdirSync(path.join(fixture, 'outputs'));
  fs.writeFileSync(path.join(fixture, 'outputs/transcript'), 'private fixture');
  stageApp(fixture, target, path.resolve(__dirname, '../LICENSE'), 'a'.repeat(40));
  assert.equal(JSON.parse(fs.readFileSync(path.join(target, 'package.json'))).buildCommit, 'a'.repeat(40));
  assert.deepEqual(fs.readdirSync(target).sort(), [...RUNTIME_FILES, 'LICENSE', 'package.json'].sort());
  assert.equal(JSON.parse(fs.readFileSync(path.join(target, 'package.json'))).devDependencies, undefined);
  assert.match(fs.readFileSync(path.join(target, 'LICENSE'), 'utf8'), /Agent Orchestrator contributors/);
  fs.unlinkSync(path.join(fixture, RUNTIME_FILES[0]));
  fs.symlinkSync(path.join(fixture, '.env'), path.join(fixture, RUNTIME_FILES[0]));
  assert.throws(() => stageApp(fixture, target, path.resolve(__dirname, '../LICENSE')), /Not a regular/);
});
test('connection URL is validated and persisted privately, invalid input cannot replace it', t => {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-connection-test-'));
  t.after(() => fs.rmSync(profile, { recursive: true, force: true }));
  assert.equal(readConnection(profile), '');
  const url = 'https://dashboard.example/?token=fixture%2Btoken';
  assert.equal(writeConnection(profile, url), url);
  assert.equal(readConnection(profile), url);
  assert.equal(fs.statSync(path.join(profile, 'connection.json')).mode & 0o777, 0o600);
  for (const bad of ['http://remote.example/', 'file:///tmp/a', 'https://a.example/api/', null]) {
    assert.throws(() => writeConnection(profile, bad));
    assert.equal(readConnection(profile), url);
  }
  writeConnection(profile, 'http://localhost:7860/');
  assert.equal(readConnection(profile), 'http://localhost:7860/');
  assert.deepEqual(fs.readdirSync(profile), ['connection.json']);
  fs.writeFileSync(path.join(profile, 'connection.json'), '{broken');
  assert.equal(readConnection(profile), '');
});
test('only the exact local connection window main frame can configure the app', () => {
  const contents = { mainFrame: { url: setupURL } };
  assert.equal(trustedSetup({ sender: contents, senderFrame: contents.mainFrame }, contents), true);
  assert.equal(trustedSetup({ sender: {}, senderFrame: contents.mainFrame }, contents), false);
  assert.equal(trustedSetup({ sender: contents, senderFrame: { url: setupURL } }, contents), false);
  for (const url of ['https://dashboard.example/', setupURL + '?fake', 'file:///tmp/other.html']) {
    contents.mainFrame.url = url;
    assert.equal(trustedSetup({ sender: contents, senderFrame: contents.mainFrame }, contents), false);
  }
});
