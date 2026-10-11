<div align="center">

# SiLing · 司令

**Know what every coding agent is doing, what matters next, and how to get the work back.**

[![CI](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml/badge.svg)](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![macOS and Linux](https://img.shields.io/badge/macOS%20%7C%20Linux-local--first-24292f)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**English** | [中文](README_CN.md)

</div>

SiLing (Chinese name: **司令**) is an independent project originally forked from
[Agent Orchestrator by YAMY1234](https://github.com/YAMY1234/agent-orchestrator-public).
This repository has left GitHub's fork network and is maintained independently;
its original Git history and attribution are preserved.
The original project provides the local-first, tmux-backed multi-agent Dashboard;
SiLing builds on that foundation with additional session controls, terminal
interaction improvements, and a more configurable workbench. Thanks to the
original authors and contributors for the foundation. The [MIT License](LICENSE)
retains both the original project's copyright notice and SiLing's notice.

## What SiLing adds

The following are additions and improvements maintained in
[Vivo50E/SiLing](https://github.com/Vivo50E/SiLing), not a list of upstream features:

- **More ways to start work:** managed Terminal-only sessions for manual commands,
  import of existing native agent conversations, a configurable default Working
  dir, and session creation directly from empty panes.
- **Restart an individual agent:** restart supported sessions using their saved
  native conversation identity, with working-directory and CLI checks. This is
  separate from reconnecting the display and can reload updated MCP configuration.
  Stop and Terminate preserve the saved conversation ID, including when several
  agents share a working directory.
- **Better terminal interaction:** reliable multiline input, improved Codex
  scrollback and return to live input, and cross-screen text selection/copying in
  Terminal, Codex and Cursor panes. Cursor full-screen and partial repaints use
  [synchronized output](docs/cursor-redraw.md) through tmux and browser painting
  to hide intermediate replay screens, including separate clear/repaint writes.
  Terminal sizing is rechecked after container and font changes.
- **Links and file previews:** optional in-Dashboard web browsing, local terminal
  paths that open in Files, read-only remote file snapshots from SSH terminals
  with a configured file host, more reliable wrapped links (including long URL
  query strings), and Markdown previews that follow the app theme.
- **A configurable workbench:** grouped Settings, light/dark/system themes,
  adjustable panel opacity, density and text size, reduced motion, consistent
  icons, and distinct agent identity badges. Dashboard controls support English
  and Chinese via Settings; agent output, user content, and raw backend errors
  remain unchanged.
- **Project groups for panes:** named, color-coded groups, individual or bulk
  assignment, and filtering without restarting terminals. Group metadata is
  shared by devices connected to the same Dashboard.
- **Installable app and controlled updates:** PWA installation, the `siling` CLI,
  and updates that test a specific candidate commit in isolation before explicit
  approval to apply it. Publishing to this repository's `main` does not deploy it.

The inherited foundation includes multi-agent layouts, task priorities and states,
linked files/folders/URLs, session save/restore, Mission Control, remote nodes, and
experimental workspace sync. Those capabilities are credited to Agent Orchestrator.

**Scope:** the UI work is incremental. Mobile now defaults to a session list and
single-session read-only snapshots, with explicit multiline replies and isolated drafts.
Physical phone acceptance and a service-wide Settings editor remain pending. See the
[UI/UX specification and current baseline](docs/uiux-improvement-spec.md) for boundaries.

## Dashboard at a glance

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

Inside Codex, Claude Code and Cursor Agent panes, **Shift+Enter** inserts a
newline; ordinary Enter keeps its normal submit behavior. SiLing translates
the shortcut before ttyd loses the Shift modifier, without changing global
tmux settings. Plain Terminal and unknown/custom agents retain native keys.
The bottom input box also supports Shift+Enter or Option/Alt+Enter for newlines.

Pane **More → Secret operations** registers an API key with a name and an immutable
HTTPS operation (GET or POST, Bearer or X-API-Key, optional fixed POST body).
Tell the agent only the name, then use `siling secret call deploy`; `siling secret list`
lists references in the current `ORCH_RUN_ID` scope. No CLI accepts a key, arbitrary
command, request override, or key export. Keys live only in Dashboard memory, expire
after 15 minutes or one hour, and disappear on revoke or Dashboard shutdown.
Expired keys are cleared by an idle expiry worker. Existing in-flight calls may
finish before revoke returns; calls are never automatically retried.

The broker alone adds the authentication header, verifies the remote TLS certificate
and does not use environment proxies or follow redirects. It returns only HTTP
status, never response bodies, headers, or raw exceptions—even if an API echoes
the key. This is suitable for fixed operations such as a deployment webhook or
authentication check; arbitrary API data retrieval and local-command injection are
not supported. The CLI uses loopback access or an SSH tunnel to the Dashboard.
Remote Nodes must run a version supporting this API and use HTTPS or a loopback tunnel.

The security boundary is the broker API on a trusted host. Dashboard administrators
can manage/call all registered operations; session labels do not replace OS user
isolation. This does not protect against an agent or another process with the same
OS privileges attacking Dashboard memory, files, or credentials. For that threat
model, run agents under a separate OS identity/sandbox with no Dashboard admin token.
Python/HTTP/TLS may temporarily copy keys in memory; this is not cryptographic
memory-zeroization or an encrypted persistent vault. Keep key values exclusively
in the private value field, never in URLs, request bodies, ordinary commands or chat.

Pane **More → Secret configuration** writes one environment variable directly to
`backend.env` on the pane's Dashboard node or an explicitly selected SSH host.
Choose an existing absolute directory, enter the variable name and masked value,
and acknowledge the plaintext file boundary. Nothing is pasted into tmux or sent
as an agent message. The old private-input API is retired, including forwarding
requests from old pages to older Remote Nodes.

The writer preserves other single-line dotenv entries, updates duplicate entries
for the selected name, and replaces the file with owner-only (`0600`) permissions.
It rejects symlinks, hard links, unsafe directories, multiline dotenv files, and
tracked or unignored targets inside Git repositories. Add `backend.env` to your
ignore rules before using it in a repository. Values cannot contain control
characters, dollar signs or backticks. SSH requires preconfigured noninteractive
authentication, a verified host key and Python 3; values travel on stdin only.
HTTPS or loopback is required for Dashboard and Remote Node requests. The field
clears on send, close or hidden tab; failures never restore or automatically retry
it. Responses contain status only, without file content or SSH errors.

This prevents the key from passing through chat or terminal input; it does not
hide a plaintext file from agents/programs with file access. Use a separate OS
account or SSH host for that isolation, or the volatile controlled-operation
broker when a fixed API call is sufficient. Temporary `0600` staging files stay
outside Git on the same filesystem and are removed on handled failure; a process
crash may leave one behind. This is not an encrypted credential vault.

Click an absolute local path or a `file://` link in a terminal to open it in SiLing’s
Files preview. The clicked item is linked to that session automatically; agents do
not need to run `link-file` first. Codex’s `label (/path)` output is also clickable,
including indented hard-wrapped paths. Paths must exist on the session’s host and be
inside the configured allowed roots (`ORCH_LINKED_FOLDER_ROOTS` for extra roots).
Bare inferred paths need a directory component or filename suffix, so slash commands
such as `/help` and `/approve` remain plain text. For a root-level name without a
suffix (such as `/README` or `/tmp`), use an explicit `file://` or OSC hyperlink.

In Terminal, Codex and Cursor panes, drag to select text and keep holding the mouse while
scrolling the wheel to extend the selection across screens, directly in the pane.
Release the mouse, then press ⌘C (macOS) or Ctrl+Shift+C to copy the complete
selection. Typing returns to live input. Option-drag retains xterm's screen-local
selection. If the selection has expired, copying keeps the clipboard unchanged and
shows a brief hint to select text again. This uses tmux's `copy-pipe-no-clear -CP`
support for clipboard transfer;
tmux 3.7c is the CI-tested version (older distro packages may lack these flags).
Ended Terminal panes offer **Reopen terminal** to start a new shell in the same pane with the original name, working directory, theme, and linked files. The old log remains available; SSH connections and shell processes are not restored.

Terminal selection highlights exclude leading spaces while you drag, without moving
the drag anchor. Multiline selections remove the common leading spaces from nonblank lines, keeping
relative code indentation and blank lines. A line without leading spaces, mixed
tab indentation, rectangular selections, and ambiguous soft wraps are left unchanged.
Ctrl-drag passes mouse input to terminal applications; other agent panes retain
their mouse behavior (Option-drag on macOS selects text). Newly started or
resumed Codex sessions use inline rendering to preserve terminal scrollback.
Existing alternate-screen sessions must be resumed to use this launch setting;
history never stored in the terminal buffer cannot be recovered by scrolling.
In Terminal, Codex and Cursor panes, typing or pasting while browsing tmux history returns to the
live terminal before sending the input. Scrolling and text selection stay in
history; escape-prefixed navigation keys keep their history behavior.
Wheel-created history mode also exits automatically when you scroll down to
the latest screen (custom tmux wheel bindings are preserved).

## Group panes by project

Use **Manage groups** below the toolbar to create, rename, recolor, or delete a
group. Select several live sessions there to assign them together, or use a
pane's **More → Project group** selector. Each session belongs to at most one
group; group names and colored markers are separate from priority flags.

The group manager shows a color-coded group list beside the editor (stacked on
phones). Choose from 12 visible swatches, use the system color picker, or enter
any six-digit HEX color such as `#12abef`. The name and color preview update
immediately; **Save changes** applies them. Expand **Assign sessions** for bulk
selection, including Select all/Clear and a selected-session count.
Existing named colors remain supported. Custom colors retain a nearest legacy
color in storage, so older servers can read the groups; editing a group with an
older server resets its custom color. Refresh older Dashboard tabs after updating.

Drag named group tabs left or right to reorder them; the order is saved on the
Dashboard and shared across devices. **All** and **Ungrouped** stay first.
Alt+Left/Right moves a focused group with the keyboard; Escape cancels a drag.
Sorting tabs does not move panes until you choose **Arrange by group**.

Choose **All**, **Ungrouped**, or a group to filter the current open panes and
live session list. **Arrange by group** packs open panes in group-tab order, keeping
relative order within each group and putting ungrouped panes last; empty slots follow.
**Settings → Appearance → Fit layout when entering a group** (off by default)
fits the desktop grid to the selected group's open panes. All restores the manual
layout; mobile keeps its single-column presentation. This preference and arranged
positions are saved in this browser. Filtering does not change saved slot positions,
restart agents, reload terminal frames, or discard input drafts. A group can
contain sessions not currently pinned; open them from the filtered session list.
Explicitly locating a session outside the filter returns to All. **New session →
Project group** assigns a group when creating a session, including on remote nodes.
Opening New from a named group preselects that group; otherwise it defaults to
Ungrouped. Directories do not automatically determine membership.

The **?** button in New session shows mode and startup instructions on hover,
keyboard focus or a tap. Escape or clicking outside dismisses the help.

The **Model** dropdown reads the selected node's installed Cursor, Claude or Codex
CLI catalog without sending a prompt or starting inference. Results are cached for
five minutes; **Refresh models** queries again. Catalogs depend on the CLI account
and provider and do not guarantee access to every listed model. Choose **Custom
model…** for other providers or when querying fails. Terminal does not query models.

Groups are stored in `outputs/.pane-groups.json`, with locked, atomic writes.
Other devices using this Dashboard receive changes on the normal session poll
(about five seconds); the selected filter and pane layout remain browser-local.
Membership follows native conversation identity on the same node when resuming
or restarting an agent. Plain Terminal sessions use their run ID. Deleting a
group only ungroups its sessions; it never stops or deletes them. Back up this
metadata file with `outputs/`; it is separate from the active-session snapshot.
Groups do not synchronize between independently hosted Dashboards.

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

## Artifacts and explicit workflows

**Files** now distinguishes references from deliverables and shows verification,
source session and host. Preview requests use session-scoped artifact IDs. SSH
previews are labelled snapshots; URL registration does not claim reachability.
Legacy linked items remain readable. Use `siling link-file /absolute/report.md
--purpose deliverable --description "Validation evidence"` to register a result;
the command prints its artifact ID. Roles can also be changed in Files.

**Workspace → Workflows** accepts a reviewed `implement → test → review → approval`
graph. Validate the JSON, then start it. Each agent needs its own prepared workspace;
results require explicit reports and verified deliverables. The dialog supports
approval, graceful cancellation, local retry and execution reconciliation. See
[the workflow guide](docs/workflows.md) and [example](examples/workflow.json).
Approval records a decision; it does not deploy or merge.

The sidebar footer separates alive, ended and total session records and retains
the last refresh time; these counts are not the number of open panes or busy agents.

Session status tooltips show execution and connection separately, observation
source/time, logical session ID and execution attempt. Resume retains lineage and
native resume IDs; an offline remote node has unknown execution state. Reconnect
only restores the display, resume opens a new native attempt, and reopening a shell
starts a fresh shell without replaying old commands.

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

Ended panes retain their history with a read-only notice. When native resume metadata is available, **Resume session** continues the conversation in the same pane slot. Failed recovery keeps the log and allows retry.

## Every task has a home with Linked Items

![Linked Items showing a task workspace, file tree, and Markdown status report](docs/assets/linked-items.webp)

A task is more than its terminal transcript. It usually has a project folder,
plans, test evidence, result tables, screenshots, and a few reference pages.
Linked Items attaches that context directly to the session.

The **Link** button opens file discovery for the source pane, including ordinary
Terminal and SSH sessions. Review selected text or load the current screen, confirm
the host/directory, then choose **Identify with Claude**. A separate background
worker extracts file paths without sending input to the pane or using model tools.
Tasks are persisted, deduplicated, cancellable, and visible when you reopen Link;
interrupted tasks require an explicit retry after a Dashboard restart. Already
linked files remain when cancelled. Identification is limited to 45 seconds and
$0.10 per call; up to eight files are checked, with two workers and eight active
or queued tasks globally. The last 128 tasks are retained (20 shown per pane).
Only the reviewed text is sent to the configured Claude model, not full history.
This first worker handles files, not project-wide scans, directories or web pages;
existing manual folder/URL linking remains available. **Find files** uses ordinary
path matching without a model.

For a spec or report, run `siling link-file /absolute/path/spec.md --label "Spec"`.
The user can then open it from the pane's **Files** panel without copying a
terminal path. Wrapped HTTP(S) links highlight all visible segments on hover.
Bare HTTP(S) URLs split by CLI hard line breaks are also joined when the lines
have consistent indentation and end near the pane edge. Clicking a segment
preserves the full query string; blank lines and following prose are not joined.

- Link a whole project or task folder and browse its tree without leaving the
  Dashboard.
- Link individual files or URLs when the task spans several locations.
- Preview Markdown, source files (including SQL), images, CSV data, and reports.
- **Copy all** copies the full text file, including content beyond a truncated preview.
- Optionally open terminal, Markdown, and linked HTTP(S) URLs in an embedded
  Browser tab via **Settings → Browsing & files → Open web links inside SiLing**.
  Open the browser from the top **More → Browser** menu.
- On the Dashboard's Mac, **Open external links via macOS** is on by default:
  external links use the system browser rather than the PWA's opening path.
  Edge still chooses the profile according to its settings; this does not force
  a profile. Turn the option off to restore browser-native opening. Internal
  browsing takes precedence. Direct remote/phone connections and unsupported
  hosts keep opening on the viewing device. Forwarded requests are ineligible;
  disable this option for headerless localhost tunnels, which look local to the
  server. Existing terminal displays may need **Reconnect display** after updating.
- Adjust popup and expanded-panel background opacity from 60% to 100% via
  **Settings → Appearance → Panel opacity**; the default is fully opaque.
- Keep implementation notes, validation evidence, and release artifacts close
  to the agent that produced them.
- Recover context quickly when resuming work days later.

The Dashboard does not create a second copy of your project. It remembers the
real workspace and gives each task a stable place from which to track its work.

### Files from ordinary Terminal and SSH sessions

Open a pane's **More → Terminal files** to manage file context and identify
files in selected output. This works with ordinary shell/tmux sessions and
programs launched inside SSH; the program does not need to call `siling link-file`.

- **Auto** detects local shell working directories and direct SSH destinations.
  Set the remote base directory once for relative paths such as `reports/test.md`.
  For SSH commands with custom flags, configure a host alias in `~/.ssh/config`
  and choose manual SSH mode. Remote directory changes must be updated here.
- File context is saved per session on the Dashboard host. Supported existing
  browser-local SSH bindings migrate on first use. New observed output retains
  its host/directory context when the pane switches back to a local shell.
  Older or ambiguous output asks you to choose a context instead of guessing.
- Automatic discovery periodically examines bounded new terminal output,
  verifies file-shaped paths and adds readable files to Files. It does not call
  a model. Disable it in the same dialog. Relative path clicks use their recorded
  directory; existing absolute links and URLs continue to work.
- Local `~/...` paths resolve against the Dashboard user’s home directory, independent
  of the selected base directory. SSH `~` paths require an absolute remote path.
  Background identification shows each failed path and its verification reason.
- Without a selection, use **Read current terminal output**, review the text and
  host/directory, then identify files. Reading does not call the model; long output
  is limited to its last 16000 characters. You can also paste or edit the text.
- Select terminal text, then choose **Find files**, or **Identify with Claude**
  for wrapped/natural-language output. The latter sends only the dialog text to
  the model configured in the Dashboard user's Claude CLI. It disables tools,
  hooks, skills and MCP, has a 45-second timeout and a $0.10 call budget, and
  verifies returned paths before linking them. It requires an installed,
  authenticated Claude CLI. Ordinary discovery works without it.

Remote file reads require existing noninteractive SSH access, a verified host
key and remote `python3`. SiLing need not be installed remotely. Previews are
local snapshots up to 16 MiB; clicking a terminal link refreshes the snapshot.
Automatic discovery caches results and checks at most eight candidates per
batch. It samples live output (up to 200 scrollback rows between polls), so use
selected-text identification for older or rapidly scrolling output. Local files
and snapshot directories must be within configured linked-file allowed roots.
Remote Nodes use the same APIs on their node; older nodes retain legacy links.

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
Cursor records model menu changes per process, including selections made before sending
another message. Restart, Resume, and Restore saved carry this conversation-bound
selection and its parameters into the replacement process; another pane’s shared
model preference cannot overwrite it. The capture contains model fields only, never
credentials. Existing Cursor processes need one restart after updating to load the
capture hook; choose the desired model after that first restart. Older runs without
a capture still use Cursor’s native last-used model. New chats accept an explicit model.
Before stopping Cursor, Restart checks `agent status --format json` without opening
browser login. Missing/unreadable credentials or a check timeout leave the old agent
running. This checks credential availability, not future token validity; credentials
remain in Cursor’s own store. Explicit token/API-key environments keep their own auth.
Confirmation is required. A missing resume ID, invalid workspace, or missing CLI
prevents the stop; an exit timeout never triggers a force kill. CLI lookup uses
the service PATH first, then `~/.local/bin`; background launches use the resolved
absolute executable path. The new SiLing run replaces
only that pane, carrying its name, palette, flag, linked files, and composer draft.
Unsaved terminal input and in-flight work may be lost; prefer restarting between
turns. If launching fails after exit, the saved source remains available via
Resume. Remote nodes must also support the restart endpoint. Terminal-only panes
do not offer this action. **Reconnect display** never restarts the agent.
Lead is a role; P0/P1/P2 are priorities; Blocked/Watching/Done are manual flags.
They still share one saved field, so selecting one replaces the previous flag.

**Settings → Appearance** controls app theme (system/dark/light), density,
interface text size, reduced motion, and language (system/English/Chinese).
Language applies to Dashboard controls, Settings, session creation, pane actions,
file navigation, and status labels, including tooltips and input hints. Switching
does not reload terminals or discard drafts. Agent output, user-defined names,
file contents and raw backend error details remain unchanged.
These preferences are browser-local and do not restart sessions or
change terminal palettes. **Terminal** applies a palette to open panes explicitly;
terminal scrollbars follow each pane's palette, including dark and light variants.
**Notifications** holds priority reminders; **Connections & updates** holds the
login-link copy action and verified-update controls. Displayed login links mask
credentials, but the copied link grants access: share it only with trusted devices.

The [Spec Kit UI/UX contract](specs/001-uiux-improvements/spec.md) and
[current baseline](specs/001-uiux-improvements/baseline.md) separate requirements
from implemented or unverified behavior. The [first implementation report](docs/uiux-implementation-status.md)
is historical evidence. The [mobile reader increment](specs/001-uiux-improvements/plan.md)
adds list/search/attention filters, bounded output with source/read-time/truncation,
Files and return navigation. Reading does not attach a terminal; **Open interactive terminal**
explicitly connects one display. Back disconnects that display, not the agent.
Desktop drafts/layout are preserved across narrow-screen transitions; returning to desktop
reconnects suspended displays. Snapshot time is not last agent-output time; failures retain
the previous snapshot with a stale warning. Full phone keyboard/device acceptance and
service-wide settings editing remain pending. See [the Spec Kit workflow](specs/README.md).

### Reply from a phone

In a session's reading view, choose **Reply**. Enter inserts a newline; only **Send**
submits (up to 8,000 characters). Esc, Tab and Ctrl+C have separate buttons;
Ctrl+C asks for confirmation. Ordinary drafts stay in this browser tab's session
storage, separately for each execution and from desktop drafts. Do not enter secrets
here. Closing the tab can discard drafts; a storage warning means reload may lose them.

“Terminal input accepted” does not confirm agent execution. If delivery is unknown
(timeout, lost connection, backgrounding or reload during sending), the draft remains
and further sends are blocked. Check output before explicitly allowing another send:
the previous input may already have arrived. Reconnection never resends automatically.
Known ended/offline sessions cannot receive input. Remote nodes need the new input
endpoint; there is no fallback to the older, retrying send route. See the
[mobile reply plan](specs/001-uiux-improvements/mobile-compose-plan.md) and
[verification boundaries](specs/001-uiux-improvements/mobile-compose-validation.md).

### Archive a session

Choose **Archive session** in a pane's More menu or the session list; on phones,
use the session detail action. Confirming hides only that execution's displays
on devices sharing this Dashboard. **The agent keeps running**; monitoring,
existing logs, Files, labels and flags remain unchanged. No files are moved.
Connected foreground pages reconcile the shared state on the five-second poll.
Each browser keeps its normal input draft in that tab's session storage.

Open **Archived** in the sidebar or phone session list to search, inspect bounded
output snapshots, open Files or **Unarchive**. The running count helps identify
agents still consuming resources. Unarchive returns the record to the list; it
does not open a pane or restart execution. Saved layouts exclude archived records.
This increment supports persisted local sessions, not remote nodes, orphan tmux
sessions or legacy log entries. See the [archive plan](specs/001-uiux-improvements/archive-plan.md).

### Inspect host resources

The toolbar beside **Mission** shows compact CPU, memory usage (total minus
available) and output-volume usage rings, without taking a separate row.
Hover for host/status information; click for details. A `!` marks incomplete,
stale or failed observations. Narrow phones use the resource chip icon instead.
It adapts to phones and light/dark themes; unavailable or stale values never
appear as live rings. Visible pages read the shared cache every five seconds;
background tabs pause requests. Opening details does not create a second loop.
You can also open **Workspace → Host resources** on desktop, or the **Host resources** chip
icon in the phone toolbar, for this Dashboard
host's CPU (all cores normalized to 0–100%), available/total memory, used/total
swap and free space on its output/project volumes. This is not the phone's or
remote nodes' resource usage. Missing directories/metrics show unknown.
The server samples once every five seconds, shared by all viewers; each sample
has a two-second timeout. Failed metrics retain their original time and become
stale after 15 seconds. Refresh reads the cache; it does not start another sampler.

This first increment is observation only: native memory pressure, session rankings,
remote aggregation, trends and pressure alerts are not implemented. Nonzero swap
alone does not prove exhaustion; archiving does not release running agents.
Install updated `requirements.txt` in the Dashboard environment for `psutil`;
a missing collector dependency shows an explicit `psutil` installation hint without
preventing startup. Install into the interpreter/virtualenv actually used by the
Dashboard, not a different shell Python; collection retries automatically without
restarting agents. A missing configured project directory is reported separately;
it does not mean the host disk is unavailable, and monitoring never creates it.
Set `ORCH_RESOURCE_MONITOR_ENABLED=0` before an explicitly approved service
restart to disable collection. The setting is service-wide, not browser-local.

### Check the SiLing version

Open **Settings → About SiLing** on desktop or mobile to see the running version
and full Git commit. Versions use `0.3.0+g<first 12 commit characters>`; every
committed update changes the build suffix without a manual version-string edit.
`.dirty` denotes local changes at startup; `unknown` denotes missing or
unverified Git metadata, not a verified release build.

The version is captured at Dashboard service startup. Fetching or pushing code
alone does not change it. After an approved update restarts the service, reopen
About or choose **Refresh version**. This never restarts Agents or reconnects
terminals. The version belongs to the connected Dashboard, not its remote nodes
or the Agent CLIs.

## Quick start

### Optional desktop browser panes

The [Electron desktop client](docs/desktop-browser.md) adds real Chromium browser
panes alongside Agents: choose **Open browser pane** in an empty grid slot, then
enter a URL. It supports navigation, reload, move/swap, zoom, and local address
restore without restarting Agents. Website views have no terminal-control bridge
and use a separate login profile. Build a branded **SiLing.app** on macOS with
`npm ci --prefix apps/desktop` and `npm run package:mac --prefix apps/desktop`;
on first launch, paste your Dashboard URL into the connection window. The build
is locally ad-hoc signed, not Apple-notarized, and does not install or update the
Dashboard. See the desktop guide for installation and separate update steps.
CI also checks `main` daily at 10:17 UTC and publishes tested Apple Silicon/Intel
[desktop builds](https://github.com/Vivo50E/SiLing/releases) only for new commits.
These are ad-hoc signed, **not notarized**; macOS may block downloaded builds.
See [preview build details](docs/desktop-browser.md#automated-online-releases).
This is not an upgrade to the existing PWA; popup login, downloads, site permissions,
project assignment and phone browser panes are not included in this first version.

The desktop client uses **Sparkle + Ed25519** for automatic online updates,
without an Apple Developer subscription. **SiLing → Check for Desktop Updates…**
opens the native download/install flow; updates replace the client and relaunch
it while Agent sessions keep running. Install the first update-enabled build
once. See the desktop guide for release-key setup and first-launch limitations.
Dashboard updates remain separate.

### Dashboard setup

Requirements: macOS or Linux, `tmux`, Python 3.10+, and at least one supported
agent CLI (`codex`, `claude`, or `agent`). Install `ttyd` for the complete
interactive terminal experience shown above.

```bash
git clone https://github.com/Vivo50E/SiLing.git
cd SiLing

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
an approval reminder opens even if Settings was closed, showing the verified
branch and commit. Choose **Approve and restart** to apply it, or **Later**
to keep working; the **approve update** button in Settings remains available.
Approval performs the exact verified fast-forward and restarts the Dashboard.
Changing either commit invalidates the approval token. The workflow never applies uncommitted code,
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

## Roadmap

See [Roadmap #1](https://github.com/Vivo50E/SiLing/issues/1) for planned Subagent
collaboration, MCP management, multi-device workflows and mobile UX. Planned
features are not claims of current support.

## Current scope

### Repository navigation and development checks

Contributors and Agents can use the [documentation index](docs/README.md),
[architecture map](docs/architecture/README.md), and `make map` to find component
responsibilities, entrypoints and tests. `tools/` is development-only; `scripts/`
remains session-runtime code. `workspace.json` is a navigation catalog, not a
package-manager configuration or inferred dependency graph.
Run `make verify PYTHON=.venv/bin/python` for layout, syntax and full-suite checks;
isolated worktrees can select an absolute path to an existing dependency runtime.
Existing CLI/import paths, update verification and runtime data locations remain
compatible. See [CONTRIBUTING](CONTRIBUTING.md) for commands and workflow.

### Product boundaries

The Dashboard-first workflow is the primary supported experience. Resume is
best-effort because each agent CLI exposes different session metadata. The
project targets trusted local developer machines rather than hosted multi-user
deployments. The older YAML recipe runner remains available for advanced use.

SiLing is released under the [MIT License](LICENSE).

## Optional Spec Kit plugin

Open **Settings → Plugins → Spec Kit**, enable the plugin, and enter a local project directory. Preview and launch Setup or a single specification stage in a separate Claude, Codex, or Cursor session. Review each result before proceeding. [Usage and limitations](docs/spec-kit-plugin.md).

Pane **⋯ → Disconnect SSH** recovers a stalled foreground SSH client while keeping the local shell. **⋯ → Switch pane type** opens Terminal, Claude, Codex or Cursor in the same pane and asks whether to keep or stop the previous session. A **Background N** badge opens related-session controls. [Details](docs/pane-types-and-ssh.md).

Choose **Settings → Browsing & files → Default web link destination** to open links in an internal iframe, a new web pane, or an external browser. [Browser behavior](docs/desktop-browser.md#default-web-link-destination).

Dense desktop layouts fit the viewport. Short panes keep the terminal visible and move secondary controls into **⋯**; choose **Write a message** to expand the pane and use its preserved draft. Zoom restores the full toolbars. Narrow screens below 820px use the mobile list and single-session reader instead of stacking desktop terminals.

Cursor launches use synchronized full-screen repaint delivery with tmux 3.7+ to avoid displaying intermediate history replays in small panes. Existing Cursor processes need a restart/resume after updating SiLing. [Cause, validation and activation](docs/cursor-redraw.md).

Settings → Appearance → **Always show pane priority** keeps the priority selector visible even in short panes. Off by default; saved in this browser and applied immediately without restarting sessions.

Terminal zoom preserves the last painted frame while tmux repaints at the new size, avoiding an intermediate text jump. The visual cover does not intercept input. During resizing it waits for 120 ms of quiet output before revealing the new frame, with a 600 ms maximum even if output never settles.

During resize, a live prompt on the last terminal row keeps its bottom position in the retained frame, preventing a second downward jump when tmux restores history. Selected text, local scrollback browsing and cursors above the last row keep top alignment.

Use **More → Session management → Fork to new pane** to branch a Claude or Codex conversation using its native CLI fork command. The original keeps running and the child gets its own conversation identity. The dialog also offers configuration-only copies for Claude, Codex, Cursor and Terminal; these start fresh and do not copy command history or SSH connections. Both sessions use the same working directory (not a Git worktree), so file edits are shared. Linked files, appearance and group membership are inherited. Saved history is used; unsent input and in-progress output may be absent. A full layout expands to the next size where possible; at maximum capacity the child remains in the session list.

Pane More keeps Rename, Reconnect display, and Close pane at the top. Expand Appearance and position, Files and connections, Secret configuration and operations, or Session management for other controls; restart, archive, switch type, and terminate are under Session management. Closing a pane keeps its session running.

Rename a session using the sidebar pencil or pane More → Rename session. The shared in-page dialog works in browsers and Electron; an empty name restores the automatic title, and failed saves preserve your input for retry.
