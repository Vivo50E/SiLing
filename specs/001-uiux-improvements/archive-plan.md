# Manual session archive — local persisted-session increment

2026-10-05: user approved implementation after confirming that Archive is filing,
not Stop. Implements the local core of FR-027–029 / US1-A8–A10; SC-011 is not
fully accepted until physical-device and remote-node support is delivered.

## Contract

- Dashboard-owned `.session-archives.json`, atomic file locking and replacement;
  keys are exact execution `run_id`s, never directories or native conversation IDs.
- `/api/session-archives` uses existing authentication and compare-and-set entry
  revisions. Duplicate requests are idempotent; stale conflicting changes fail.
- `/api/sessions` includes archive metadata independently of execution inventory.
  Archive read/write failures are explicit and never reset corrupt metadata.
- Local `run` / `task` records only. Remote nodes, orphan tmux and legacy logs
  return an explicit unsupported response without network/control side effects.
- Browsers apply only confirmed state, keep drafts in tab-scoped sessionStorage
  (in-memory fallback with warning), close only matching displays, retain all
  other slots. Old layouts and automatic fill cannot reopen archived records.
- Saved active-session bulk restore skips archived source records. Explicit new
  executions use their new run identity and do not inherit archival state.
- Sidebar and mobile expose the archived count/running count, search, bounded
  output and Files. Unarchive returns to the list, not to a pane or execution.
- Existing Mission/notifications still consume the full session inventory;
  filing never disables monitoring or suppresses attention records.

## Validation plan

Backend: authentication, restart persistence, exact-record isolation, idempotency,
CAS conflict and parallel edits, corruption/write failures, unsupported remote /
orphan cases, cache-independent reads and saved-snapshot exclusion.
Browser: cancel/save/failure/unknown, drafts and other frames, auto-fill/layout
replay, simulated second-client changes, archived reading/Files, unarchive,
Chinese mobile and desktop keyboard paths. Full `make verify` and browser suite.
Physical iOS/Android and supported remote-node filing remain explicit follow-ups.
