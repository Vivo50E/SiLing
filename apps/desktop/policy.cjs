'use strict';

const MAX_PANES = 16;
const ID = /^browser~[a-zA-Z0-9-]{1,64}$/;
const loopback = host => host.replace(/\.$/, '') === 'localhost' || host === '[::1]'
  || /^127\./.test(host) || /^\[::ffff:7f[0-9a-f]{2}:/.test(host);

function httpURL(value) {
  if (typeof value !== 'string' || value.length > 16384) throw Error('Invalid web address');
  let url;
  try { url = new URL(value); } catch { throw Error('Enter a complete HTTP(S) address'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw Error('Only HTTP(S) addresses without embedded credentials are supported');
  }
  return url;
}

function dashboardURL(value) {
  const url = httpURL(value);
  if (url.pathname !== '/' || (url.protocol === 'http:' && !loopback(url.hostname))) {
    throw Error('Use the Dashboard root URL; remote connections require HTTPS');
  }
  return url;
}

function isDashboard(value, dashboard) {
  try {
    const url = new URL(value);
    // Also block loopback aliases of the configured Dashboard listener.
    const port = value => value.port || (['https:', 'wss:'].includes(value.protocol) ? '443' : '80');
    return port(url) === port(dashboard) && (url.hostname.replace(/\.$/, '') === dashboard.hostname.replace(/\.$/, '') || loopback(url.hostname));
  } catch { return false; }
}

function browserURL(value, dashboard) {
  const url = httpURL(value);
  if (isDashboard(url.href, dashboard)) throw Error('Open the Dashboard in its control view, not a browser pane');
  return url.href;
}

function trustedSender(event, contents, dashboard) {
  if (event.sender !== contents || event.senderFrame !== contents.mainFrame) return false;
  try {
    const url = new URL(event.senderFrame.url);
    return url.origin === dashboard.origin && url.pathname === '/';
  } catch { return false; }
}

function bounds(value, width, height, scale = 1) {
  if (!value || !['x', 'y', 'width', 'height'].every(k => Number.isFinite(value[k]))) return null;
  if (!Number.isFinite(scale) || scale <= 0 || scale > 5) return null;
  const x = Math.max(0, Math.ceil(value.x * scale));
  const y = Math.max(0, Math.ceil(value.y * scale));
  const right = Math.min(width, Math.floor((value.x + value.width) * scale));
  const bottom = Math.min(height, Math.floor((value.y + value.height) * scale));
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

module.exports = { MAX_PANES, ID, httpURL, dashboardURL, browserURL, isDashboard, trustedSender, bounds };
