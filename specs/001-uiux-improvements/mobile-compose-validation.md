# Mobile replies — validation record

2026-10-06. US2-A2/A3 increment; FR-008/009 plus FR-004/024/025/026.
SC-004 remains partially accepted. Contract: [mobile-compose-plan.md](mobile-compose-plan.md).

## Automated evidence

- Initial `make verify PYTHON=<project-venv>/bin/python`: 481 tests passed,
  warnings as errors, plus repository/Python/Shell/JavaScript/JSON checks.
  Final integration verification is pending below.
- Eight new backend tests cover authentication before delivery, exact multiline
  Unicode input, strict key/body/size validation, missing/ended/archived targets,
  sanitized failures, and no retry or trailing Enter after an unknown paste.
- Remote HTTP/WebSocket regression additionally verifies qualified-target input
  forwarding and rejection by older nodes without legacy-send fallback or retries.
- `UI_MOBILE_COMPOSE_ONLY=1 UI_BROWSER=<Chromium> node tests/ui_browser.mjs`
  passed: separate drafts, Files/back, captured target and late response isolation,
  double-click protection, 401 without auth replay, offline/reconnect, explicit
  special keys and interrupt cancellation, Enter/IME, pending reload, 12-second
  timeout, background abort, storage failure, ended/offline targets, bilingual
  themes, 360/390/430px and landscape/keyboard-sized viewports.
- Isolated real tmux smoke passed: owned background shell, authenticated tty
  attachment, new input endpoint, multiline Chinese output, Escape/Tab/Ctrl+C,
  unchanged source metadata and explicit cleanup of that shell only.

## Findings and limits

- New tests failed before implementation on the missing endpoint/reply control.
  The browser harness now waits for inventory before choosing its initial session;
  its mutation budget includes only the nine explicit input attempts and extra
  reload required by this increment. No navigation-driven sends are allowed.
- Optional `tests/terminal_browser.mjs` passed synchronization, resize, palette,
  direct input, Shift+Enter and hard-wrapped web-link checks, then failed the
  existing “Bare SSH path fragments are visible” assertion. The unchanged base
  `ac0146c` reproduced the same failure in a separate worktree. This is unresolved,
  not a passing full terminal suite; later copy/history assertions were not reached.
- Browser emulation is not physical iOS Safari/PWA or Android Chrome acceptance.
  Native Claude/Codex interaction and copy/history need a separate device/agent
  matrix. No performance, cross-device or exactly-once execution claim is made.
- Client cancellation cannot retract an already accepted operation. Unknown
  results require checking output and explicit acknowledgment before more input.
  Ordinary drafts are tab-local sessionStorage, not secret input or durable backup.
  Older remote nodes reject `/input`; there is deliberately no retrying fallback.

## Rollout and follow-up

No running Dashboard update/restart is authorized by code delivery. After a
separately approved update, validate soft keyboard visibility, IME, rotation,
background/reconnect and native agent behavior on real phones. Roll back code
without clearing `siling_mobile_draft_v1:` entries; older code ignores these
drafts. No process or persisted-session schema migration is needed.
