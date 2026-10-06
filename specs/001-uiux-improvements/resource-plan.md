# Implementation plan: local host resource overview

2026-10-05 · US3-A6/A9, partial FR-030/033; supporting FR-024/025.

## Scope and contract

First increment only: desktop Workspace → Host resources; mobile toolbar chip. Show the
connected Dashboard host, normalized CPU, available/total physical memory, used/
total swap and free space on configured output/project volumes. Each metric has
its own observation time, source and availability. No healthy/critical verdict:
available memory is not the OS memory-pressure signal, and nonzero swap is not
an exhaustion alarm. Native pressure remains explicitly unavailable.

Authenticated `GET /api/resources` returns a cached, no-store snapshot; public
health is unchanged. One sampler per Dashboard process, independent of client
count. Default 5-second cadence, 2-second subprocess timeout, no overlap/backlog,
15-second expiry. Failed metrics retain their last value/time but show failure;
never relabel them fresh after another metric succeeds. CPU uses successive OS
counter deltas over the sample interval, normalized to 0–100% across all cores;
first/reset/sleep-gap samples are unknown. No process enumeration or raw arguments.

Use psutil 7.x ([metric definitions](https://psutil.readthedocs.io/stable/index.html))
inside the short-lived collector, not request handlers. Missing dependency or
unsupported platform yields unavailable, not a Dashboard startup failure.
`ORCH_RESOURCE_MONITOR_ENABLED=0` disables collection at service startup; this is
a service-level override, not a browser preference or an implemented Settings editor.
No storage migration or automatic session/system control.

## Delivery tasks and checks

- [x] Collector/service: independent failure handling, cached reads, timeout,
  lifecycle cleanup, disable, CPU counter/wake handling and immutable snapshots.
- [x] API: existing token gate, no-store, no sampling on reads or public health.
- [x] UI: literal text, bilingual responsive dialog, focus return, bounded
  requests, 15-second expiry while offline, foreground recheck; no TTY reloads.
- [x] Regression: provider fixtures for macOS/Linux metrics and failures;
  real macOS collector smoke; full `make verify`, isolated browser suite,
  existing isolated tmux/ttyd smoke, diff review.

Evidence and remaining limits: [resource-validation.md](resource-validation.md).

## Deferred / acceptance limits

Session attribution/rankings, remote aggregation, native memory pressure, paging
rates, 15-minute charts, session/display counts, sustained pressure alerts,
new-session warnings and Settings controls are separate increments. Archive
remains independent. Do not mark FR-030/033 or SC-012/013 fully complete.
Linux real-host, physical iOS/Android and 12/24-session 10-minute overhead budgets
require separate evidence; fixtures do not establish these claims.

## Risks and rollback

An extra bounded process every five seconds has measurable overhead; verify on
the host without stress-loading user sessions. Network-backed volume queries
may time out; retain old timestamps. Disable via the environment override and
an explicitly approved service restart if needed. Pushing main never restarts
the running Dashboard; missing psutil requires the normal dependency install.
