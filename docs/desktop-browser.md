# Desktop browser panes

The optional Electron desktop client displays websites in independent Chromium
`WebContentsView` instances, not Dashboard iframes. A site that disallows iframe
embedding can still load as a top-level page. The existing Python Dashboard and
tmux sessions remain unchanged; closing this client does not stop Agents.

## Default web link destination

In **Settings → Browsing & files → Default web link destination**, choose:

- **Internal iframe**: open the existing Projects browser overlay.
- **New web pane**: open alongside session panes. Electron uses its existing native browser; an ordinary web client uses a sandboxed iframe. Existing panes are preserved, and a full grid expands to the next supported layout when possible. At maximum capacity, free a pane before retrying.
- **External browser**: preserve the existing browser/macOS opening behavior.

The choice is saved on this client and applies to terminal, Markdown and Files web links. Existing internal/external preferences migrate automatically. Browser pane addresses and layout are also saved on this client. Ordinary web iframes cannot bypass embedding restrictions and their sandbox may prevent login/storage features; use external opening or Electron's native web pane for those sites. Web iframe panes provide address navigation, reload, external opening, resize, move and close; native desktop panes also provide browser back/forward controls.

中文：在 **设置 → 浏览与文件 → 网页链接默认打开方式** 选择「内部 iframe」「新建网页面板」或「外部浏览器」。偏好保存在当前客户端。新网页面板优先使用空位，满时自动扩展到下一个布局，不覆盖会话；最大布局无空位时会提示。Electron 使用原生网页面板，普通浏览器使用受限 iframe；无法嵌入或登录受限的网站可外部打开。

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
For automatic online updates without a paid Apple account, use the Sparkle
release pipeline described below.

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
it.

## Free automatic online updates

SiLing uses Sparkle 2 with its own Ed25519 release key. No Apple Developer
subscription or Developer ID certificate is needed for this update mechanism.
The bundled native helper checks and downloads updates in the background;
**SiLing → Check for Desktop Updates… / 检查客户端更新…** opens Sparkle's update
window. Choose its install/relaunch action to replace the client automatically.
You can defer installation instead. Save unsaved forms and drafts before
restarting. Dashboard and Agent processes continue running, and the desktop
connection file and browser profiles stay in place.

Install the first update-enabled client once. Old Electron builds without
Sparkle cannot bootstrap themselves. These builds remain ad-hoc signed and
not Apple-notarized: macOS can still require approval or block a first launch.
The updater does not disable Gatekeeper, TLS or signature checks. Install the
app in a writable Applications directory, such as `~/Applications`; running
from an archive, read-only volume, or a translocated location can prevent updates.

Both appcast feeds and ZIPs are Ed25519-signed. The embedded public key validates
updates before extraction, and increasing numeric build numbers prevent
rollback. Automatic checks do not send system profiles. Sparkle's distribution
is downloaded from its official release with a pinned SHA-256 at build time.
The helper and framework are included in the app, so users need no Node, Xcode,
Git or separate updater installation. The update signing key is independent
of Apple's code-signing certificates.

### Release key setup

The public key is pinned in `apps/desktop/sparkle-config.json`. A maintainer's
private seed is stored outside the repository with `0600` permissions. To
initialize a new project key (only before clients have been distributed), run:

```bash
npm run update:key --prefix apps/desktop
```

The default private-key path is `~/.config/siling/desktop-update-key`. Back it up
securely. The tool refuses to replace an existing pinned key with an unrelated
one. Losing this key can require users to reinstall the client; never casually
regenerate or rotate it. The private seed must not be committed, embedded in
binaries, written to logs, or pasted into issues/chat.

Configure the existing seed as GitHub environment **desktop-updates** secret
**SILING_UPDATE_PRIVATE_KEY** using GitHub's secret settings or `gh secret set`
with file input. Only the final publish job receives it. Build and test jobs
use the public key only. No Apple credentials are required.

### Automated online releases

**Desktop online update release** checks `main` daily at **10:17 UTC** and can
also be started via **Run workflow → main**. It binds the release to one commit,
uses full Git history for monotonically increasing build numbers, and requires:

- Full Python verification on Python 3.10 and 3.13.
- Native Apple Silicon and Intel Electron integration and packaged-app tests.
- Actual Sparkle A → B replacement/relaunch plus wrong-key and tampered-ZIP
  rejection tests using isolated apps and throwaway keys.

Publication creates a draft, uploads both ZIPs, signed architecture-specific
appcasts and SHA-256 sums, then publishes as **Latest** only when every upload
has completed. The clients read `appcast-arm64.xml` or `appcast-x64.xml` from
that release. Missing or mismatched release keys stop publication. Existing
published assets are never overwritten; retryable drafts remain private.
Keep Latest reserved for desktop releases with appcasts. Legacy `-preview.*`
releases remain available but are not used as an automatic update feed.

Closing/restarting the Electron client does not update the Python Dashboard.
Dashboard **Update** remains a separate server operation. A local build is not
publication or installation; review and authorize those actions separately.

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
