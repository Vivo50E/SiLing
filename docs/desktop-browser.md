# Desktop browser panes

The optional Electron desktop client displays websites in independent Chromium
`WebContentsView` instances, not Dashboard iframes. A site that disallows iframe
embedding can still load as a top-level page. The existing Python Dashboard and
tmux sessions remain unchanged; closing this client does not stop Agents.

## Start from source

Use Node.js 22.12+ (24 LTS recommended) and npm, and start the Dashboard separately.
From the repository root:

```bash
npm ci --prefix apps/desktop
SILING_DASHBOARD_URL="http://127.0.0.1:7860/" npm start --prefix apps/desktop
```

Set `SILING_DASHBOARD_URL` to the root URL of your trusted Dashboard, including
its login token when needed. To use a running instance's URL without pasting its
token into shell history, use `SILING_DASHBOARD_URL="$(./siling url -q --no-copy)"` before
the same npm command. Do not publish this URL. Remote connections require HTTPS;
certificates must be trusted by the computer. The client does not bypass TLS
errors or install certificates. HTTP is accepted for loopback development only.

This is a source-launched desktop client, not an installer or an update to an
existing Edge/Safari PWA. It does not start, deploy, or restart a Dashboard.
The macOS About menu shows the desktop package and Electron versions; Dashboard
Settings → About SiLing continues to show the running server build.

## Use a browser pane

1. Make room in the grid by expanding Layout or closing a pane (not terminating
   its session).
2. In an empty slot, choose **Open browser pane / 打开浏览器面板**.
3. Enter a complete HTTP(S) address. An address without a scheme uses HTTPS.
4. Use Back, Forward, Reload, Stop, Open externally, Zoom, and Close. Drag its
   header or use the numbered selector to swap slots without reloading Agents.
   Cmd/Ctrl+L focuses its address bar; Escape exits its enlarged view.

Addresses and placement are saved in this desktop client's local profile.
Only the current address, not navigation history or unsaved forms, is restored
after restarting the client. Closing/replacing a browser pane or shrinking the
layout past its slot discards that pane, so finish unsaved forms first. Reloading
the Dashboard recreates browser views. Browser panes are currently ungrouped;
they appear under All/Ungrouped, not a named project filter. They are excluded
from Agent snapshots and are not shared with phones or other devices.

Browser logins use a dedicated persistent cookie jar shared by browser panes,
separate from Dashboard authentication and existing Edge profiles. Login is not
automatically inherited from Edge. Popup windows, downloads, and device/site
permission requests are blocked in this first increment; use the external
browser for popup-based SSO, downloads, or permissions. Websites may additionally
restrict embedded-browser login even though their pages render normally.
Terminal links retain the existing internal/external routing settings; targeting
a particular browser pane, project assignment, and a signed installer are later
increments, not features of this release.

## Security and verification

Website views have no preload bridge or Node.js access. Sandbox, context
isolation, and web security stay enabled. Only the configured Dashboard's root
main frame can invoke the narrow pane-control bridge. Browser requests to the
configured Dashboard origin and loopback aliases at its port are blocked; do not
expose a privileged Dashboard through additional unprotected host aliases.
Unsupported protocols and credential-bearing URLs are rejected. Website popups
cannot create privileged windows. Never disable these protections to make a
site load. Keep the pinned Electron dependency updated with security releases.

```bash
make verify PYTHON=/path/to/project/venv/bin/python
npm test --prefix apps/desktop
npm run test:integration --prefix apps/desktop
```

The integration check uses temporary profiles and local fixture servers, never
your running Dashboard, browser cookies, or Agent sessions.
