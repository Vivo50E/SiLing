'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const policy = require('../apps/desktop/policy.cjs');
const dashboard = policy.dashboardURL('http://127.0.0.1:7860/?token=fixture');

test('Dashboard accepts loopback HTTP or trusted HTTPS, root only', () => {
  assert.equal(policy.dashboardURL('https://dashboard.example/').origin, 'https://dashboard.example');
  for (const url of ['http://remote.example/', 'file:///tmp/a', 'https://a.example/file', 'https://user:pass@a.example/']) {
    assert.throws(() => policy.dashboardURL(url));
  }
});
test('Web URLs retain complete queries and reject dangerous schemes and credentials', () => {
  const url = 'https://web.example/auth?redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Fcallback&state=exact#hash';
  assert.equal(policy.browserURL(url, dashboard), url);
  assert.equal(policy.browserURL('http://localhost:3000/', dashboard), 'http://localhost:3000/');
  for (const input of ['javascript:alert(1)', 'file:///etc/passwd', 'data:text/html,hi', 'ftp://a/', 'https://user:secret@a/', null, {}, 'x'.repeat(17000)]) {
    assert.throws(() => policy.browserURL(input, dashboard));
  }
});
test('Browser requests cannot reach Dashboard through HTTP, WebSocket or loopback aliases', () => {
  for (const host of ['127.0.0.1', 'localhost', 'localhost.', '[::1]', '127.0.0.2', '[::ffff:127.0.0.1]']) {
    for (const scheme of ['http', 'https', 'ws', 'wss']) {
      assert.equal(policy.isDashboard(`${scheme}://${host}:7860/api/send`, dashboard), true);
    }
  }
  assert.throws(() => policy.browserURL(dashboard.href, dashboard));
  assert.equal(policy.isDashboard('https://example.com/', dashboard), false);
  const remote = policy.dashboardURL('https://dashboard.example/');
  assert.equal(policy.isDashboard('wss://dashboard.example/api/ws', remote), true);
});
test('Only the exact Dashboard main frame can send IPC', () => {
  const contents = { mainFrame: { url: dashboard.href } };
  assert.equal(policy.trustedSender({ sender: contents, senderFrame: contents.mainFrame }, contents, dashboard), true);
  assert.equal(policy.trustedSender({ sender: contents, senderFrame: { url: dashboard.href } }, contents, dashboard), false);
  assert.equal(policy.trustedSender({ sender: {}, senderFrame: contents.mainFrame }, contents, dashboard), false);
  for (const url of ['http://127.0.0.1:7860/static/file.html', 'https://evil.example/', 'about:blank']) {
    contents.mainFrame.url = url;
    assert.equal(policy.trustedSender({ sender: contents, senderFrame: contents.mainFrame }, contents, dashboard), false);
  }
});
test('Native rectangles are finite, clipped, zoom-aware and fail closed', () => {
  assert.deepEqual(policy.bounds({ x: -10, y: 20, width: 2000, height: 1000 }, 800, 600), { x: 0, y: 20, width: 800, height: 580 });
  assert.deepEqual(policy.bounds({ x: 10, y: 20, width: 100, height: 50 }, 800, 600, 1.5), { x: 15, y: 30, width: 150, height: 75 });
  for (const input of [null, {}, { x: NaN, y: 0, width: 10, height: 10 }, { x: 900, y: 0, width: 10, height: 10 }, { x: 0, y: 0, width: -5, height: 10 }]) {
    assert.equal(policy.bounds(input, 800, 600), null);
  }
});
