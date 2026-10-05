# Specifications / 规格导航

Current contract: [UI/UX improvements](001-uiux-improvements/spec.md) (Chinese).
Evidence and remaining work: [baseline](001-uiux-improvements/baseline.md).
Quality review: [requirements checklist](001-uiux-improvements/checklists/requirements.md).

当前规格是持续维护的需求契约，不是已完成功能列表。历史报告留在 `docs/`，
每次实现后更新基线与有日期的证据，不再维护两份相互冲突的完整需求。

## Spec Kit workflow

Official [GitHub Spec Kit](https://github.com/github/spec-kit/tree/v1.1.0) v1.1.0,
commit `f1d3a4f8337ebbd3ae22760a9c12e3352b93a175`, generated the checked-in
`.specify/` infrastructure and `.agents/skills/speckit-*` Codex integration.
Its [MIT license](../.specify/LICENSE) is retained. This adds no application runtime dependency.

Initialization used `specify init staging --integration codex --integration-options="--skills"
--script sh --ignore-agent-tools --non-interactive` in an empty staging directory;
only missing files were brought into the repository. Existing `AGENTS.md` was not changed.
The [constitution](../.specify/memory/constitution.md) records existing repository rules.
Templates, scripts and agent skills remain the generated upstream versions.

To install the same CLI in your own development environment (Python 3.11+):

```bash
uv tool install 'git+https://github.com/github/spec-kit.git@f1d3a4f8337ebbd3ae22760a9c12e3352b93a175'
```

Normal repository tests do not require this CLI. Do not rerun `init --force` over
existing instructions; stage and review upgrades, preserving local changes.

For this existing feature, select it explicitly from the repository root before
starting your coding agent:

```bash
export SPECIFY_FEATURE_DIRECTORY=specs/001-uiux-improvements
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
```

The environment variable is inherited by agents started from that shell.
For an already running agent or a Dashboard-launched stage, include
`SPECIFY_FEATURE_DIRECTORY=specs/001-uiux-improvements` in the request and ask it
to apply that value to stage scripts. The active `.specify/feature.json` pointer is
intentionally ignored by Git; a fresh clone must select the feature explicitly.
Feature directories do not have to match Git branch names.

In Codex, use `$speckit-clarify` to refine this spec, then `$speckit-plan` for
one reviewed increment. After reviewing the plan, use `$speckit-tasks` and
`$speckit-analyze`; `$speckit-implement` requires a separate implementation request.
These are **agent skills**, not `specify clarify` shell subcommands.
Only Codex integration is bundled here; Claude/Cursor integration may be staged
separately using the [Dashboard plugin guide](../docs/spec-kit-plugin.md).

初始化只执行 constitution → specify → clarify 质量复查。
2026-10-05 经用户明确要求开始实施后，US2-A1 手机阅读切片进入
[Plan](001-uiux-improvements/plan.md) → [Tasks](001-uiux-improvements/tasks.md) → Analyze → Implement。
这不代表其他故事已获实施验收；后续每个切片仍需独立审阅，运行版本更新仍需单独批准。
