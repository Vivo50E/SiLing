# Workspace Architecture / 工作区架构

## Current decision / 当前决策

SiLing currently ships one coupled Python service and browser UI, not multiple
independently deployable packages. This first structural increment creates an
agent-readable component map and shared checks without changing runtime paths.
It is a monorepo foundation, not a claim that package extraction is complete.

司令目前仍是一个共同部署的 Python 服务与浏览器界面。本阶段先建立组件边界、
可查询导航与统一验证；不靠空的 `apps/`、`packages/` 目录宣称完成拆包。
现有启动入口、导入路径、公开文档 URL 和运行数据保持兼容。

## Repository map / 目录职责

```text
SiLing/
├── siling, orchestrator.py, dashboard.py  # CLI and compatibility entrypoints
├── agent_orchestrator/                   # Python backend and orchestration
├── static/                               # Dashboard UI and PWA assets
├── scripts/                              # Session runtime operations
├── launchd/                              # macOS installation and deployment
├── tools/                                # Development-only validation
├── tests/                                # Regression and browser checks
├── docs/architecture/                    # Architecture decisions and boundaries
├── docs/assets/                          # Reviewed public documentation images
├── examples/                             # Portable configuration examples
├── tasks/                                # Public task recipes
├── skills/                               # Legacy recipe prompt resources
├── workspace.json                        # Machine-readable component catalog
└── Makefile                              # Shared contributor/CI commands
```

`outputs/`, `projects/`, `.dashboard-certs/`, `dashboard.local.json` and
`tasks/private/` are ignored runtime/private data, **not workspace packages**.
Do not move them when organizing source. `skills/` contains prompt resources
loaded by the legacy YAML runner; it is not a promise of automatic skill
discovery by every coding Agent.

## Boundaries / 模块边界

| Area | Responsibilities | Read first |
| --- | --- | --- |
| CLI and tasks | Command parsing, YAML recipes, run lifecycle | `cli.py`, `config.py`, `task_runner.py` |
| Dashboard | API composition, auth, live session view | `dashboard.py`, `dashboard_network.py` |
| Session state | Persistence, activity, grouping, metrics | `state.py`, `json_store.py`, `native_activity.py`, `pane_groups.py`, `conversation_metrics.py` |
| Terminal and files | Key routing, terminal colors, SSH previews | `terminal_theme.py`, `terminal_files.py`, `ssh_files.py`, `static/terminal-*.js` |
| Remote work | Node transport and workspace sync | `remote_nodes.py`, `sync_status.py`, `sync_transfer.py` |
| Updates | Candidate verification, approval and build identity | `self_update.py`, `version.py` |
| Browser UI | DOM composition, preferences, messages and groups | `static/index.html`, `ui-foundation.js`, `ui-messages.js`, `pane-groups.js` |

Python filenames above are relative to `agent_orchestrator/` unless otherwise
qualified. Browser filenames are relative to `static/`.

- `tools/` is development-only. Backend and session-runtime Python code must
  not import `tools` or `tests`; the checker enforces static absolute imports.
- Browser code calls authenticated APIs; do not copy server credentials into
  client files. Production code must not require browser-test dependencies.
- Put new bounded behavior in a focused module with tests, instead of growing
  `dashboard.py` or the inline script merely because they already exist.
- `workspace.json` lists component roots, entrypoints, guides and relevant
  tests. It is navigation metadata, not an inferred dependency graph, ownership
  authorization, or permission to run only a subset of tests.
- Update the catalog when adding or moving a component. CI rejects missing
  roots/files, overlapping roots, escaping paths and stale check patterns.

## Agent workflow / Agent 工作流程

1. Read root `AGENTS.md`, this map, and the relevant implementation/tests.
   `make map` prints the validated catalog as JSON.
2. State the user-visible problem, affected components and invariants before
   editing. Use an isolated development worktree; preserve others' changes.
3. Add regression tests. Use focused tests while developing, then `make verify`
   for the full suite and structural/syntax checks. For UI or terminal work,
   run the opt-in browser checks described in [CONTRIBUTING](../../CONTRIBUTING.md).
4. Report changed files, evidence, limits and deployment status. Keep public
   artifacts free of real session content and credentials.
5. A commit/push is not deployment. Verification and explicit update approval
   remain separate; reorganizing source must not restart live Agents.

Existing root `AGENTS.md` is preserved. Its direct Python commands remain valid;
the Makefile is an additional consistent entrypoint, not a new runtime dependency.

## Deferred extraction / 后续拆分

The largest coupling remains the Dashboard API and inline UI. A later migration
can put application composition under `apps/` and genuinely reusable libraries
under `packages/`, but each extraction needs its own acceptance boundary:

1. Extract a bounded UI module or API service with explicit inputs/outputs;
   retain API URLs and behavioral tests before moving deployment paths.
2. Introduce a shared path resolver and package-data strategy. Replace current
   root-relative assumptions in launchers, static serving, tests and deployment.
3. Validate a clean checkout, detached update worktree, installed runtime,
   legacy entrypoints and rollback. Migrate one component at a time.
4. Add package-manager workspaces/lockfiles only when actual package boundaries
   and dependency ownership exist; do not duplicate dependency definitions.

No new framework, package manager, remote cache, deployment service or public
access is introduced by this structural increment.

## References / 参考

Monorepo organization depends on explicit relationships and shared tooling,
not a mandatory folder spelling: [Nx monorepo overview](https://nx.dev/docs/kb/what-is-a-monorepo).
Python workspaces are for actual cooperating packages:
[uv workspace concepts](https://docs.astral.sh/uv/concepts/projects/workspaces/).
These inform the design; SiLing does not depend on either tool.
