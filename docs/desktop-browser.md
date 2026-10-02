# Desktop browser panes

The optional Electron desktop client displays websites in independent Chromium
`WebContentsView` instances, not Dashboard iframes. A site that disallows iframe
embedding can still load as a top-level page. The existing Python Dashboard and
tmux sessions remain unchanged; closing this client does not stop Agents.

## Build and install SiLing.app (macOS)

Use Node.js 22.12+ and the macOS command-line tools. From the repository root:

```bash
npm ci --prefix apps/desktop
npm run package:mac --prefix apps/desktop
npm run test:packaged --prefix apps/desktop
```

The output is `dist/desktop/SiLing-darwin-arm64/SiLing.app` on Apple Silicon
(`SiLing-darwin-x64` on Intel). You can select `-- --arch arm64` or `-- --arch x64`;
this does not produce a universal binary. Choose a fresh `-- --out /absolute/path`
for subsequent builds: existing output directories are never overwritten.
The generated application uses SiLing's existing icon, `com.vivo50e.siling`
bundle identity, branded helper processes, and the desktop package version.

Builds use local ad-hoc signing with strict signature verification, not a
Developer ID certificate or Apple notarization. No personal certificate is read.
They are not a Developer ID-signed release; do not disable Gatekeeper,
remove quarantine flags or bypass HTTPS certificate checks to distribute them.
A distributable signed/notarized installer remains a separate release task.

To install, copy the generated **SiLing.app** in Finder to your Applications
folder (or `~/Applications`). If an older app has that name, quit and back it up
before explicitly replacing it. Building alone does not install or launch it.
Quit any source-launched Electron client before opening the packaged app: they
share the same SiLing desktop profile and should not run concurrently.

On first double-click, paste the root Dashboard URL from `siling url`, including
its token if needed. The input is masked. Connection settings are saved with
owner-only (`0600`) permissions in
`~/Library/Application Support/SiLing Desktop/connection.json`; this file is
**not encrypted** and must not be shared. The application preserves the source
client's existing profile and login partitions. It never embeds this file,
tokens, certificates, outputs, or the Python backend in a build.

The native **SiLing → Dashboard Connection… / Dashboard 连接设置…** menu can change
the connection; confirmation warns that reopening the workbench can discard
unsaved page forms and input drafts. Agent processes keep running. A failed
initial connection returns to setup so the address can be corrected. Settings
follow the macOS language (Chinese or English). `SILING_DASHBOARD_URL`, when
explicitly supplied at process launch, overrides the saved URL for that launch
only. Remote connections require HTTPS with a certificate trusted by this Mac.

The Dashboard must already be running. Desktop builds do not start or restart
it. Desktop updates require obtaining a new build and explicitly replacing the app after
quitting it; Dashboard **Update** updates the server, not this app bundle.
There is no desktop auto-updater or DMG in this increment.

## Automated preview releases

[Desktop preview release](https://github.com/Vivo50E/SiLing/actions/workflows/desktop-release.yml)
checks `main` daily at **10:17 UTC** (03:17 Pacific daylight time, 02:17 standard
time). Maintainers can also choose **Run workflow → main**. GitHub schedules may
be delayed and are disabled after 60 days of inactivity in a public repository;
check the Actions page if daily checks stop.

A successful preview for the same commit skips all builds. Otherwise CI runs the
full Python suite on 3.10/3.13 and native Electron integration, packaging and
packaged-app smoke tests on both Apple Silicon and Intel Macs. All jobs use the
same pinned `main` commit. Only after every check passes does CI publish a
[prerelease](https://github.com/Vivo50E/SiLing/releases), never a stable Latest
release. Tags contain the desktop base version and 12-character source commit,
for example `desktop-v0.3.0-preview.0123456789ab`; the full SHA is in release notes.
The native About dialog still shows the base package version, not the preview tag.

Download the `mac-arm64.zip` (Apple Silicon) or `mac-x64.zip` (Intel) asset. The ZIP
contains **SiLing.app**, preserving executable permissions and symlinks. Download
both ZIPs and `SHA256SUMS.txt` to verify with `shasum -a 256 -c SHA256SUMS.txt`, or
compare `shasum -a 256 <your-zip>` against the matching line in that file.

**These previews are ad-hoc signed, not Apple-notarized.** Gatekeeper may block
internet-downloaded builds; this pipeline is not yet a frictionless public
installer. Do not disable security checks; use the local source-build path above
if needed. A Developer ID certificate, notarization and secure signing-secret
configuration are a separate release increment.

Failures leave no public partial release. An interrupted upload may leave a draft;
rerun the workflow to rebuild and finish that commit's draft. Published assets and
tags are never overwritten. Intermediate Actions artifacts expire after 14 days;
published releases remain until a maintainer removes them. To pause periodic
publishing, disable this workflow in Actions. Nothing is installed on your Mac,
and no Dashboard, Agent session or desktop connection settings are changed.

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

This development command still runs the unbranded `Electron.app` executable;
use the packaged `SiLing.app` above for the correct Dock and application identity.
Neither launch method upgrades an existing Edge/Safari PWA, starts, deploys, or
restarts a Dashboard. Without an environment override, source startup uses a
saved connection or falls back to `http://127.0.0.1:7860/`.
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
npm run test:packaged --prefix apps/desktop -- /absolute/path/SiLing.app
```

The integration and packaged-app checks use temporary profiles and local fixture
servers, never your running Dashboard, browser cookies, or Agent sessions. The
packaged check verifies bundle metadata, icon, signing integrity, a strict runtime
file allowlist, connection IPC isolation, first launch, saved connection restore,
and invalid-connection recovery. It must run on the matching Mac architecture.
