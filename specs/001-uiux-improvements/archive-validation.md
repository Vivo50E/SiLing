# Session archive — validation record

2026-10-06. Local persisted-session increment only; SC-011 remains partially
accepted. Scope and state contract: [archive-plan.md](archive-plan.md).

## Automated evidence

- `make verify PYTHON=<project-venv>/bin/python`: 465 tests passed, warnings as
  errors; repository structure, Python/Shell/JavaScript/JSON checks passed.
- Ten archive backend tests cover authentication, independent execution identity,
  Dashboard restart persistence, atomic writes, concurrent records, revision
  conflicts/idempotence, invalid timestamps/corrupt storage, unsupported targets,
  and skipping archived sources in active-snapshot restoration.
- `UI_BROWSER=<Chromium executable> node tests/ui_browser.mjs`: full browser suite
  passed, including archives, existing private input, resources, groups, pane
  movement/restart/recovery, Files and mobile navigation. No uncaught errors.
- Optional focused repeat: `UI_ARCHIVES_ONLY=1 UI_BROWSER=<Chromium executable>
  node tests/ui_browser.mjs`. Covers cancelled/failed/lost responses, simulated
  second-client polling, unchanged other iframe nodes and input drafts, draft
  recovery across reload, old-layout/automatic-fill exclusion, project search,
  literal bounded output, Files, keyboard entry/focus, ended-session unarchive,
  unavailable metadata recovery and Chinese 390px dark/light screenshots.

An isolated real tmux/Dashboard smoke also passed: create an owned background
shell, attach its tty proxy, send input, archive, read output/Files, unarchive,
then explicitly stop the test shell. Archiving preserved the same process PID
and source metadata. Only the disposable test server/session was cleaned up.

## Findings and limits

- Regression tests caught boot-time automatic fill replacing archived empty
  slots. Saved layouts now replay their explicit slots and gaps; deliberate
  layout selection still fills eligible sessions. Existing Link tests explicitly
  reopen their source instead of depending on boot-time automatic fill.
- One earlier full browser run timed out on the existing transient SSH status
  text assertion; later complete runs passed. No production workaround was added.
- Screenshots and API/browser fixtures are not iOS/Android or two physical-device
  acceptance. Network delays and suspended tabs can exceed a foreground polling
  interval; clients reconcile when reachable again.
- Remote nodes, orphan tmux sessions and legacy log entries are explicitly
  unsupported. Existing output is a bounded snapshot, not a complete native
  conversation. Draft persistence is per tab; storage failure keeps an in-memory
  copy and warns the user. Archiving does not release running agent resources.

## Rollout and follow-up

Code delivery does not authorize applying or restarting the running Dashboard.
After an approved update, smoke-test archive/unarchive on desktop and iOS Safari,
including a second connected device. Add remote support as a separate increment.
Rollback code without deleting `.session-archives.json`; older code will ignore
the filing metadata and can display previously archived sessions again. Logs,
native resume IDs and Files are not moved by this feature.
