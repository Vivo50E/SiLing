# US2-A1 validation — 2026-10-05

## Delivered scope

Phone list → single read-only snapshot → Files / return, search and attention filter,
explicit one-terminal interaction, and independent desktop layout/draft preservation.
This is a partial US2 delivery, not completion of the UIUX spec or SC-004.

Root cause: responsive CSS previously hid/reflowed desktop cards without stopping
their automatic terminal attachments; `/read` lacked snapshot/truncation evidence.
The implementation separates mobile navigation and gates desktop attachment at
boot, queued work and late response boundaries. Existing authenticated APIs remain.

## Evidence

- `make verify`: **422 tests passed**, no skips, plus repository/Python/Shell/JS/JSON checks.
  Repeated after integrating concurrent main change `9accea8` (Cursor partial redraw fix).
- Initial regressions failed on the old implementation: missing bounds/metadata and
  missing phone list. Added nine backend tests and extended remote proxy coverage.
- Full `tests/ui_browser.mjs`: PASS using isolated API/terminal fixtures in headless Edge.
  Mobile checks include zero boot terminal requests; all/attention/search; list scroll/focus
  restoration; Files; literal text; timestamp/truncation/older-node unknown state;
  failed refresh retaining original snapshot; empty output; late A→B responses;
  explicit single terminal; no send/stop/restart/resume calls; unchanged desktop preferences;
  preserved desktop drafts; suppression of queued/late desktop attachments.
- Browser sizes: 360/390/430px and 780×390 landscape for the reader; existing desktop,
  narrow settings and 4×3/4×4 layout regressions also pass. Screenshots reviewed.
- Real tmux/ttyd browser smoke: PASS for copy/selection, scrollback, Shift+Enter,
  long links, theme scrollbars and drag cleanup, using a disposable tmux socket.
- Additional isolated Dashboard API smoke: background shell → tty proxy → harmless
  command input → bounded snapshot with metadata → stop owned session: PASS.
  Fixture setup was corrected to register the session and include the viewport in the
  requested line window; no production session was used.
- `git diff --check`: PASS. Python 3.13.5, Node 26.0.0, tmux 3.7c, ttyd 1.7.7.

## Modified components

- `static/mobile-reader.js` / `.css`: mobile controller and themed surface.
- `static/index.html`: routing, responsive transport suspension/restoration and boot guards.
- `static/ui-messages.js`: reviewed Chinese copy; English source labels.
- `agent_orchestrator/dashboard.py`: optional character cap and additive snapshot metadata.
- Backend, proxy and browser tests; bilingual README, baseline, plan and task evidence.

## Limits and next step

Physical iOS Safari/Android Chrome touch, keyboard, backgrounding and TLS acceptance
has **not** been performed. A mobile multiline composer, complete Files redesign,
monitor center and service settings are outside this increment. Snapshot read time
is not last agent-output time; the latter remains unknown. Log tail scanning cost
is not bounded by the response character cap. Older nodes may ignore the cap;
the browser additionally bounds rendered text and reports missing metadata as unknown.

Development and testing used an isolated worktree. Applying this increment to the
running Dashboard or restarting it requires separate approval. After that approval,
validate the phone flow on a physical device before claiming complete US2 acceptance.
