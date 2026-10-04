# Raven roadmap implementation (#2)

This document tracks the implementation of issue #2; completion of one increment
is not completion of the roadmap. Existing delegation, Files, terminal and native
lifecycle mechanisms remain the integration points.

## M1: background Link

Implemented in f986110: reviewed text only; tool-free Claude extraction; captured
source/context; durable bounded jobs; deduplication; cancellation; process cleanup;
restart interruption; explicit retry. Model subprocess behavior uses controlled
CLI fixtures, not a real paid model or private production transcript.

Acceptance extended: real controlled subprocess deadline/cancellation, queued
cancellation/shutdown, stale responses after closing a source dialog, narrow-screen
layout and keyboard dismissal. These are fixture tests, not paid-model evaluations.

## M2: artifacts

Extend each linked_folders record with optional artifact metadata, preserving legacy
records and CLI round trips. Identity uses host + source path + item type (SSH cache
path is not identity). Preserve original source run across resume/copy operations.
Store role (reference/deliverable), description, discovery source, verification
receipt and provenance. Listing rechecks local availability; a URL is unverified,
not claimed reachable. Remote previews are explicitly snapshots, not a claim that
the remote host is currently online. Preview requests use a session-scoped artifact
ID resolved against existing links; existing path APIs remain compatible.

## M3: state and recovery

Reuse native_activity events first and label terminal activity as inferred. Return
separate execution, connection, attention and observation metadata. Persist stable
logical session identity and execution-attempt ancestry when resuming; preserve
native resume IDs. Reconnect is read-only and never replays commands. Surface
source/time and explicit reconnect/resume/rerun distinctions in the UI.

## M4: explicit workflows

Introduce fixed, user-reviewed graphs referencing existing delegate sessions.
Validate IDs/dependencies/cycles/input artifact references before spawning. Runs
persist, use bounded concurrency, stop downstream on failure, and require a
validated explicit result before success. Approval nodes pause without performing
merge/publish/deploy. Retry only failed/cancelled nodes; uncertain in-flight writes
require review after restart. Workers use isolated worktrees/directories; unsupported
remote/isolation combinations fail before execution. No autonomous graph planning.

## Validation and release

For each stage: behavioral tests, complete repository suite, browser tests, relevant
real ttyd/tmux smoke tests, bilingual and narrow-screen checks. Keep production
sessions unchanged. Publish status and runtime deployment status separately.

Implementation status: M1 acceptance audit and M2–M4 code are implemented in this
increment. The workflow entrypoint is Workspace → Workflows and `siling workflow`;
see `docs/workflows.md` and `examples/workflow.json`.

Validation evidence (isolated fixtures only):
- Full `make verify`: 377 tests passed (no skipped tests), including Python warnings
  as errors and repository syntax checks; Python 3.13 from the existing project venv.
- Browser suite: resource-ID previews, role persistence, graph review/start/approval,
  duplicate clicks, English/Chinese narrow layouts, keyboard dismissal and stale Link responses.
- Real tmux/ttyd suite: input, clipboard, native/tmux selection, multiline indentation,
  scrollback, links and palette changes. Its drag assertion now waits for the actual
  animation-frame paint while the mouse stays held instead of assuming a 100 ms render.
- Workflow behavioral/API tests: invalid graph/inputs, concurrency, failure propagation,
  current-attempt receipts, graceful cancellation ownership, approval, retry and restart.

Limits: no paid Claude/Codex execution or production workflow was started for testing.
Workflows use explicitly prepared isolated directories/worktrees, local delegates,
manual reviewed graphs and explicit result reports. Reads/reconnects do not dispatch.
After a restart/capacity wait, Continue ready nodes is explicit; uncertain starts
require a uniquely matching receipt, otherwise inspection. Approval records a
workflow decision and never performs a deployment/merge itself. This is not an
autonomous DAG planner, remote workflow runner, or new agent sandbox.

Code publication and runtime deployment are separate. Runtime updates/restarts were
not performed by this implementation work. Do not close the roadmap on the basis
of an unverified production or paid-agent end-to-end run.
