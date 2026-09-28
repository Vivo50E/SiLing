<div align="center">

# SiLing

**Know what every coding agent is doing, what matters next, and how to get the work back.**

[![CI](https://github.com/YAMY1234/agent-orchestrator-public/actions/workflows/ci.yml/badge.svg)](https://github.com/YAMY1234/agent-orchestrator-public/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![macOS and Linux](https://img.shields.io/badge/macOS%20%7C%20Linux-local--first-24292f)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文文档](README_CN.md)

</div>

![SiLing managing six live coding-agent sessions in a readable 3x2 view](docs/assets/dashboard-hero.webp)

<p align="center"><sub>On a smaller screen, the 3x2 layout keeps every session readable while preserving task names, priority colors, busy and idle state, files, and controls.</sub></p>

![SiLing zoomed out to twelve live coding-agent sessions](docs/assets/dashboard-overview.webp)

<p align="center"><sub>On a larger display, switch to 4x3 and watch twelve live panes at once while the sidebar keeps all sixteen sessions organized. Local paths are normalized for publication.</sub></p>

![Any live SiLing session expanded over the multi-task dashboard](docs/assets/focus-mode.webp)

<p align="center"><sub>Expand any session to inspect its full TTY output and controls, then return to the multi-task view without interrupting the underlying work.</sub></p>

Codex and Claude Code are powerful inside a terminal. The difficulty starts
when five or ten terminals are running at once: tab titles stop being useful,
important work gets buried, an idle agent looks like a busy one, and closing a
window can make a valuable session hard to find again.

SiLing turns those terminal sessions into a durable, visual task
board. Each agent gets a name, priority, live state, workspace, files, and a
path back into the session.

## The control you lose with terminal tabs

| Terminal-only workflow | SiLing |
| --- | --- |
| Every tab looks the same | Give each task a memorable custom label |
| Urgent work disappears among other windows | Sort and group with `P0`, `P1`, and `P2` |
| No quick answer to “is it still working?” | See busy, idle duration, watching, blocked, and done states |
| The output exists, but the task context is elsewhere | Link its project folder, files, and reference URLs |
| Closing the terminal loses your mental index | Capture native resume metadata and search ended sessions |
| A restart destroys your screen layout | Save active sessions and restore supported work into its panes |

## One front door for every coding agent

<p align="center">
  <img src="docs/assets/new-session.webp" width="520" alt="Start a Cursor Agent, Claude Code, or OpenAI Codex CLI session from one dialog">
</p>

Start Cursor Agent, Claude Code, OpenAI Codex CLI, or a plain login shell from
the same dialog. Give the task a human label, choose its workspace, and launch
it directly into a background tmux session. Terminal sessions never
auto-approve prompts, so they are suitable for commands you want to run
yourself. The Dashboard then becomes the stable place to find that work again
instead of relying on a terminal tab title.

The same flow can create a new task or resume a stopped one. You can open an
iTerm window when you want it, or keep the session entirely in the background
and interact through the browser TTY.

## A command center for real parallel work

Choose anything from one focused pane to dense `4x4` and `5x3` grids. The
overview above uses twelve panes while the sidebar keeps all sixteen sessions
organized; smaller layouts give each agent more room when you need to read or
intervene.

- Use full interactive TTY panes or lightweight plain-text streaming.
- Send input to any agent without switching terminal windows.
- Zoom, reconnect, stop, close, or open linked files per pane.
- Drag tasks between slots without restarting the underlying session.
- Keep Codex, Claude Code, and Cursor Agent work in the same view.

The browser is only the control surface. Background tmux sessions continue
running when the tab is closed.

Click an absolute local path or a `file://` link in a terminal to open it in SiLing’s
Files preview. The clicked item is linked to that session automatically; agents do
not need to run `link-file` first. Codex’s `label (/path)` output is also clickable,
including indented hard-wrapped paths. Paths must exist on the session’s host and be
inside the configured allowed roots (`ORCH_LINKED_FOLDER_ROOTS` for extra roots).

In Terminal and Codex panes, drag to select text and keep holding the mouse while
scrolling the wheel to extend the selection across screens, directly in the pane.
Release the mouse, then press ⌘C (macOS) or Ctrl+Shift+C to copy the complete
selection. Typing returns to live input. Option-drag retains xterm's screen-local
selection. This uses tmux's `copy-pipe-no-clear -CP` support for clipboard transfer.
Ctrl-drag passes mouse input to terminal applications; other agent panes retain
their mouse behavior (Option-drag on macOS selects text). Newly started or
resumed Codex sessions use inline rendering to preserve terminal scrollback.
Existing alternate-screen sessions must be resumed to use this launch setting;
history never stored in the terminal buffer cannot be recovered by scrolling.
In Codex panes, typing or pasting while browsing tmux history returns to the
live terminal before sending the input. Scrolling and text selection stay in
history; escape-prefixed navigation keys keep their history behavior.
Wheel-created history mode also exits automatically when you scroll down to
the latest screen (custom tmux wheel bindings are preserved).

## Priority and state you can read at a glance

<p align="center">
  <img src="docs/assets/priority-status.webp" width="360" alt="P0, P1, P2, blocked, watching, and done task groups">
</p>

The sidebar is designed to answer “where should I look?” before you read any
terminal output:

- **P0 — red:** urgent or decision-blocking work.
- **P1 — amber:** important work that should stay visible.
- **P2 — blue:** normal background work.
- **Watching — green:** progressing without immediate intervention.
- **Blocked — purple:** waiting for input or an external dependency.
- **Done — dimmed/green:** finished work stays recognizable without competing
  with active tasks.

Custom labels replace opaque session IDs with names you will remember, such as
“Auth migration” or “Release automation.” The idle badge shows how long a pane
has remained quiet. Busy detection waits for sustained activity, so one line of
terminal noise does not make a task look continuously productive.

Pane borders, priority pills, and terminal status lines work together: you can
scan red, yellow, blue, and green across the grid, then open only the task that
actually needs attention.

## Native lifecycle signals and useful notifications

Terminal output is a useful activity signal, but it cannot always distinguish
an agent that is thinking from one that has returned control to the user.
SiLing can install native Claude Code lifecycle hooks so waiting,
permission, failure, and completion transitions update the same sidebar and
Mission Control timeline:

```bash
siling install-agent-hooks
```

The default hook is observe-only: it records lifecycle state and does not
approve permissions. Notifications open the matching full TTY view, are
acknowledged when that session is inspected, and replace an older notification
from the same session instead of accumulating duplicates.

Automatic permission handling is a separate, explicit opt-in for trusted
single-user environments. `--claude-permission-policy siling` applies
only to Claude sessions launched by SiLing, but it still grants
requested tools without a human confirmation; review that tradeoff before
enabling it.

## Close the terminal without losing the work

The usual failure mode with terminal agents is not that the process crashed;
it is that the human no longer knows which tab, directory, or resume command
belonged to the task.

SiLing keeps several layers of recovery information:

1. It records the task label, agent type, workspace, logs, and local metadata.
2. When an agent CLI exposes a native session ID, it captures the corresponding
   Codex, Claude Code, or Cursor resume command.
3. **Save active** records the current pane layout and recoverable active
   sessions.
4. After a reboot or Dashboard restart, **Restore saved** recreates supported
   sessions in background tmux and returns them to their saved slots.
5. Ended sessions remain searchable and can be resumed from the new-session
   flow.

<p align="center">
  <img src="docs/assets/resume-session.webp" width="488" alt="Search an ended coding-agent session and resume it in the background">
</p>

<p align="center"><sub>Search by task name, agent, workspace, model, or native resume ID, then bring the session back in the background or in iTerm.</sub></p>

Recovery is best-effort because the agent CLIs expose different metadata, but
the Dashboard makes that state explicit instead of leaving it hidden in a
terminal scrollback buffer.

## Every task has a home with Linked Items

![Linked Items showing a task workspace, file tree, and Markdown status report](docs/assets/linked-items.webp)

A task is more than its terminal transcript. It usually has a project folder,
plans, test evidence, result tables, screenshots, and a few reference pages.
Linked Items attaches that context directly to the session.

For a spec or report, run `siling link-file /absolute/path/spec.md --label "Spec"`.
The user can then open it from the pane's **Files** panel without copying a
terminal path. Wrapped HTTP(S) links highlight all visible segments on hover.

- Link a whole project or task folder and browse its tree without leaving the
  Dashboard.
- Link individual files or URLs when the task spans several locations.
- Preview Markdown, source files, images, CSV data, and reports.
- Optionally open terminal, Markdown, and linked HTTP(S) URLs in an embedded
  Projects tab via **Settings → Browsing & files → Open web links inside SiLing**.
- Adjust popup and expanded-panel background opacity from 60% to 100% via
  **Settings → Appearance → Panel opacity**; the default is fully opaque.
- Keep implementation notes, validation evidence, and release artifacts close
  to the agent that produced them.
- Recover context quickly when resuming work days later.

The Dashboard does not create a second copy of your project. It remembers the
real workspace and gives each task a stable place from which to track its work.

### Workbench appearance and controls

Use **New**, **Search**, and **Layout** in the toolbar. Layout retains all ten
grid options with visual previews. **Workspace** contains save/restore, sorting,
and close-all actions. Closing a pane does not stop its session.

Each pane shows an agent glyph-and-name badge, a flag selector, Files, Zoom, and **More**.
Agent glyphs are original UI symbols, not official brand logos. Common toolbar,
pane, and Settings navigation icons are bundled SVGs; no icon CDN is required.
More contains reconnect, terminal palette, move/swap, close pane, and terminate.
**More → Restart agent** interrupts the selected Claude/Codex/Cursor process and
launches a background session with the same saved native conversation ID. Use it
to reload MCP configuration; independent MCP servers are not updated or restarted.
Confirmation is required. A missing resume ID or invalid workspace prevents the
stop; an exit timeout never triggers a force kill. The new SiLing run replaces
only that pane, carrying its name, palette, flag, linked files, and composer draft.
Unsaved terminal input and in-flight work may be lost; prefer restarting between
turns. If launching fails after exit, the saved source remains available via
Resume. Remote nodes must also support the restart endpoint. Terminal-only panes
do not offer this action. **Reconnect display** never restarts the agent.
Lead is a role; P0/P1/P2 are priorities; Blocked/Watching/Done are manual flags.
They still share one saved field, so selecting one replaces the previous flag.

**Settings → Appearance** controls app theme (system/dark/light), density,
interface text size, reduced motion, and language (English/Chinese for the new
controls). These preferences are browser-local and do not restart sessions or
change terminal palettes. **Terminal** applies a palette to open panes explicitly;
**Notifications** holds priority reminders; **Connections & updates** holds the
login-link copy action and verified-update controls. Displayed login links mask
credentials, but the copied link grants access: share it only with trusted devices.

The first UI/UX implementation increment and its remaining work are tracked in
[the implementation report](docs/uiux-implementation-status.md). Mobile single-task
navigation and service-wide settings editing are not included in this increment.

## Quick start

Requirements: macOS or Linux, `tmux`, Python 3.10+, and at least one supported
agent CLI (`codex`, `claude`, or `agent`). Install `ttyd` for the complete
interactive terminal experience shown above.

```bash
git clone https://github.com/YAMY1234/agent-orchestrator-public.git
cd agent-orchestrator-public

PYTHON=python3.11  # use any installed Python 3.10+
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x siling
mkdir -p ~/.local/bin
ln -sf "$PWD/siling" ~/.local/bin/siling
siling dashboard
```

Open [http://127.0.0.1:7860](http://127.0.0.1:7860), create a session, assign a
label and priority, then choose **Start in Background**.

To give New Session a default Working dir without changing the project-browser
root, set `new_session_working_dir` in the ignored `dashboard.local.json`, or
set `ORCH_NEW_SESSION_WORKING_DIR`. If omitted, SiLing uses `~/Workflows` when
that directory exists, then falls back to `projects_root`. Click any empty pane
to open New Session and place the created session directly in that pane.

### Install as a macOS app

The Dashboard includes Progressive Web App support. After starting it, choose
**File → Add to Dock** in Safari, or use the install button in the Chrome/Edge
address bar. It then runs in its own window and appears in the Dock, Launchpad,
and Spotlight. The local `siling dashboard` backend must remain running to
provide sessions and TTY access; if it is unavailable, the app shows a reconnect
screen instead of displaying stale cached session state.

The `siling` launcher resolves symlinks back to this repository and uses its
virtualenv automatically. If `~/.local/bin` is not on `PATH`, run `./siling`
from the repository or add that directory to your shell's `PATH`.

The older `orchestrator.py` entrypoint, `ORCH_*` environment variables, state
directories, and `orch-*` tmux names remain compatible with existing sessions.

## A practical daily workflow

1. Create a background session and give it a human label.
2. Assign `P0`, `P1`, or `P2` so it lands in the right group.
3. Link the task or project folder so its artifacts stay easy to find.
4. Watch busy and idle duration instead of opening every pane repeatedly.
5. Send input only where a decision, permission, or clarification is needed.
6. Save active sessions before a restart; stop completed work with resume
   metadata preserved.

## Start sessions from the CLI

```bash
siling run                              # Cursor Agent
siling run claude                       # Claude Code
siling run codex                        # OpenAI Codex CLI
siling run codex investigate /path/to/project
```

The browser and CLI workflows use the same local sessions and metadata.

### Import sessions created before SiLing

Choose **New session → Import existing** to scan native Codex, Claude Code, and
Cursor Agent history. Search or filter the results, select up to 100 sessions,
and import them into the Resume picker. Import creates only an SiLing
metadata index under `outputs/`; original transcripts stay in their native
locations and are never copied, moved, edited, or deleted. Already indexed
native session IDs are automatically hidden from the import list.

## Let one agent delegate to another

An agent does not have to stop at reporting that more work is needed. From an
SiLing session it can create a named child task with an exact agent,
model, effort, workspace, and priority:

```bash
siling delegate --agent codex --model gpt-5.6-sol --effort high \
  --label dependency-audit --priority p1 \
  --prompt "Audit the dependency update and report targeted test evidence."
```

The child appears in the Dashboard immediately. It inherits the parent
workspace and Linked Items by default, while remaining an independent tmux
session. Agents can also list sessions, read a bounded head or tail of their
TTY history, inspect live status, send follow-ups, and change an idle
Codex/Claude session's model or effort through `siling session` commands. See the
[agent delegation guide](docs/agent-delegation.md) for the complete workflow,
idempotent automation, and remote-node behavior.

### Approve and apply updates

The Dashboard's **apply update** action discovers both candidate branches in
separate Git worktrees whose names begin with `agent/self-improve-` and new
commits on the current branch's Git upstream. If no tracking branch is set, it
falls back to `origin/<current-branch>` and then `origin/main`. Remote refs are
refreshed on startup, every five minutes, and whenever the button is clicked.

Updates require a clean working tree and a fast-forward path. The first click
runs the complete suite against the exact candidate—upstream code is tested in
a temporary detached worktree without changing local files. After tests pass,
the button becomes **approve update**; the second click performs the exact
verified fast-forward and restarts the Dashboard. Changing either commit
invalidates the approval token. The workflow never applies uncommitted code,
force-merges, or rebases user work.

Verification uses the Dashboard's Python runtime for both the suite and nested
Python CLI commands, even when the temporary checkout has no `.venv`. It does
not install packages into system Python or change the running service's PATH.

## Keep it running on macOS

The managed installer creates an isolated runtime, installs dependencies,
generates a private token, and registers a user LaunchAgent:

```bash
./launchd/deploy.sh --install  # first install
./launchd/deploy.sh            # later code updates
./launchd/deploy.sh --dry-run  # preview an update
```

It preserves outputs, linked projects, certificates, local configuration, and
private task recipes across deployments. The LaunchAgent listens on
`127.0.0.1` by default.

Useful overrides:

```bash
ORCH_PYTHON=/path/to/python3.12 ./launchd/deploy.sh --install
ORCH_DASHBOARD_PORT=9000 ./launchd/deploy.sh --install
ORCH_DASHBOARD_HOST=0.0.0.0 ./launchd/deploy.sh --install
```

## Remote access

Non-loopback binds require authentication. For LAN or VPN access, use a token
and HTTPS:

```bash
ORCH_DASHBOARD_TOKEN=mysecret siling dashboard --host 0.0.0.0 --https
```

The URL helper detects the running Dashboard's protocol and bind address:

```bash
siling url            # print and copy the best authenticated URL
siling url -q         # print only the URL
siling url --json     # inspect all reachable candidates
```

## One Dashboard for local and remote agents

Remote Nodes keep agent processes and tmux sessions on their execution
machines while presenting them in the same local Dashboard. Sessions are
grouped by location, remote TTY input/output is proxied through a small HTTP
and WebSocket control plane, and the remote work continues if the browser or
local Dashboard closes.

Run the remote service with `siling dashboard --node-only`, connect it through
an SSH tunnel, and list it in the ignored `dashboard.local.json`. This does
not require copying projects or enabling workspace sync. See the
[Remote Nodes guide](docs/remote-nodes.md) for a generic two-machine setup,
safe token handling, automatic tunnels, and optional self-service reconnect.

## Experimental workspace sync (off by default)

If you use a local computer and a remote development server, the optional
**sync status** view keeps the handoff visible. It shows files changed only on
the local machine, files changed only on the remote machine, matching changes,
and true two-sided conflicts. Filesystem events update local changes quickly;
a low-frequency reconciliation catches missed events and refreshes the remote
view.

This feature is separate from Remote Nodes and is disabled unless
`sync_status.enabled` is explicitly set in the ignored local configuration.
Monitoring is read-only by default. **Sync now** transfers currently safe
one-sided additions and updates, while **Sync when idle** waits for affected
local and remote agent workspaces to become quiet. Continuous auto sync is
another explicit opt-in and starts off. Conflicts, Git refs, oversized files,
and deletions are never applied automatically. Start with narrow `paths` and a
manual baseline; do not point a first trial at an entire home directory.

For a faster handoff, each session pane has its own **Sync** action. It derives
the smallest useful scope from that session's working directory and filesystem
Linked Items, previews the exact projects or task artifacts, then syncs only
that scope. A path is busy only when an active terminal with changing output or
background shell work maps to the same Git project or Linked Item; a generic
Projects-root cwd does not block unrelated work. A normal click waits for those
affected paths to become idle, while Shift-click syncs the currently safe items
immediately. During a queued or running sync the same button becomes **Cancel**.
The workspace-wide actions remain available as a fallback.

After a session-scoped project sync is verified, SiLing also
publishes a dormant resume handoff for Claude Code and Codex when
`remote_code_root` is configured. The native transcript and session metadata
are copied to the remote machine, where the task appears as resumable but is
not started. This keeps the final decision to switch machines explicit and
avoids launching a second agent automatically.

The comparison baseline lives outside the project tree in SiLing's
local state directory. Copy
[`examples/dashboard.local.json`](examples/dashboard.local.json), select the
workspaces that should be tracked, and enable `sync_status` only after the same
SiLing revision is available on both machines.

## Local-first security

SiLing can send input to local terminal sessions and should be
treated as a privileged developer tool.

- The default bind is localhost-only.
- Non-loopback access requires a token.
- Tokens are stored outside the tracked source tree with user-only permissions.
- Runtime data remains local and may contain prompts, transcripts, paths, and
  resume metadata.
- Never publish `outputs/`, `projects/`, `.dashboard-certs/`, local
  configuration, or private task recipes.

See [SECURITY.md](SECURITY.md) for deployment and vulnerability-reporting
guidance. Development checks and contribution instructions are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Current scope

The Dashboard-first workflow is the primary supported experience. Resume is
best-effort because each agent CLI exposes different session metadata. The
project targets trusted local developer machines rather than hosted multi-user
deployments. The older YAML recipe runner remains available for advanced use.

SiLing is released under the [MIT License](LICENSE).
