# Local host resources: validation and handoff

2026-10-05 · [Plan](resource-plan.md) · partial FR-030/033, not full SC-012/013.

## Delivered

The previous health/agent-busy indicators did not measure host utilization.
An isolated sampler now supplies authenticated cached CPU, available memory,
swap and configured output/project volume observations. Desktop entry:
Workspace → Host resources. Phone entry: toolbar chip icon. Collection defaults
to five seconds, times out after two seconds, and expires after fifteen seconds.
Each metric preserves its own last observation time across failure; CPU needs
two valid samples and discards reset/sleep-gap baselines. No pressure verdict,
process inspection, session controls, storage migration or remote connections.

## Evidence

- Full `make verify`: **436 tests passed**, no skips; repository, Python,
  shell, JavaScript/inline-script and JSON checks passed.
- Ten new resource unit/API tests cover normalized CPU, first/reset/wake
  samples, Linux guest counters and macOS-shaped metrics, partial failures,
  wall/monotonic expiry, disabled/unsupported collection, immutable cached reads,
  one worker across repeated starts/readers, cleanup, authenticated GET/no-store,
  unchanged public health, and a real hung child killed by the deadline.
- Full isolated `tests/ui_browser.mjs`: PASS. Resource scenarios include
  literal hostname rendering, units/missing values, failed/expired/disabled
  snapshots, auth failures without repeated prompts, simulated wake/recheck,
  late replies after closing, English/Chinese, desktop/390px layouts, visible
  44px phone entry, Escape/focus return, no session-control requests and no
  terminal iframe reloads while inspecting resources. Screenshots reviewed.
- Existing real tmux/ttyd browser smoke: PASS for synchronized painting,
  resizing, theme scrollbars, Shift+Enter, copy/selection/history, wrapped links
  and file-context transitions, using only its disposable shell/socket.
- Real macOS ARM64 collector + isolated authenticated TestClient: five metrics
  become fresh, repeated reads work, writes are rejected and shutdown joins the
  worker. This is not a production or load-capacity measurement.
- Python 3.13, psutil 7.2.2, Node 26, headless Edge. `git diff --check`: PASS.

Browser fixture corrections: send the full native Escape key sequence and await
its asynchronous focus return; isolate synthetic clock/wake events from the
earlier group tests; wait for the preceding shell's frame before testing that a
web pane does not reload it. An intermediate existing browser scenario also hit
a CDP evaluation timeout; the full rerun passed with expression-level diagnostics.
No product regression was suppressed by weakening assertions or increasing timeouts.

## Changed components

- `agent_orchestrator/resources.py`, Dashboard lifecycle and `/api/resources`.
- `static/resources.js` / `.css`, Dashboard adapters, messages and chip icon.
- `requirements.txt`: psutil 7.x, imported only by the isolated collector.
- Resource unit/browser tests, existing browser fixture readiness, bilingual
  README, spec/baseline and this increment's plan/evidence.

## Limits, activation and rollback

No deployment or running-Dashboard restart was performed. Install the updated
requirements in the approved runtime before activation; missing psutil leaves
metrics unavailable without breaking Dashboard startup. Set
`ORCH_RESOURCE_MONITOR_ENABLED=0` before a separately approved restart to disable
the sampler. This service-wide override is not a Settings editor.

Session rankings, remote aggregation, native memory-pressure signals, paging
rates, 15-minute trends, counts, alerts and new-session warnings remain pending.
Archiving still does not release running agents. Real Linux host acceptance,
physical iOS/Android and the 12/24-session, three-client overhead/latency budgets
have not been performed. A new bounded child every five seconds adds overhead;
this report makes no CPU/memory budget or capacity claim. Next: establish those
baselines, then implement sustained pressure alerts and session attribution.
