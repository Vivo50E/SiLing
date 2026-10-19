"""Invocation-local instructions for a pane's remote coding coordinator.

This is a prompt policy, not a sandbox or a remote job scheduler. Never read
credentials or start paid jobs while saving/checking a preference.
"""
from pathlib import Path
import argparse
import json
import os
import shutil

MODES = ("local", "devin", "cmux-cloud")


def validate(mode):
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("proxy_mode must be local, devin or cmux-cloud")
    return mode


def devin_skill():
    home = Path.home()
    roots = [Path(os.environ.get("CODEX_HOME") or home / ".codex") / "skills",
             home / ".claude/skills", home / ".agents/skills"]
    return next((root / "delegate-to-devin/SKILL.md" for root in roots
                 if (root / "delegate-to-devin/SKILL.md").is_file()), None)


def cmux_cli():
    return shutil.which("cmux") or next((str(p) for p in (
        Path("/Applications/cmux.app/Contents/Resources/bin/cmux"),
        Path.home() / "Applications/cmux.app/Contents/Resources/bin/cmux",
    ) if p.is_file() and os.access(p, os.X_OK)), "")


def availability():
    return {"devin": bool(devin_skill()), "cmux-cloud": bool(cmux_cli())}


def instructions(mode):
    validate(mode)
    intro = "[SiLing pane execution preference]\n"
    if mode == "local":
        return intro + ("Remote proxy mode is OFF for this pane. This replaces any earlier SiLing "
                        "proxy preference in this conversation. Follow the user's ordinary workflow. "
                        "Acknowledge briefly, then wait for the next user task; do not replay old tasks.")
    policy = (
        f"Remote proxy mode: {mode}. This replaces earlier SiLing proxy preferences for this pane. "
        "For subsequent code changes, fixes, refactors and tests, act as the local coordinator: "
        "delegate implementation and expensive builds/tests to the selected remote provider. "
        "Keep local work to clarification, bounded read-only inspection, planning, progress tracking "
        "and reviewing returned diffs/test evidence. Do not implement locally or start local coding "
        "subagents unless the user explicitly overrides this preference. Ordinary questions can be "
        "answered locally. Preserve this preference in conversation summaries.\n"
        "Before delegating, establish the repository URL, source branch/commit, requested scope, "
        "acceptance checks and allowed side effects. Reuse the remote session for follow-ups; "
        "persist its URL/IDs in this pane's run directory (ORCH_RUN_DIR). After a resume, recover "
        "them from conversation history or the source directory recorded in session metadata "
        "(resumed_from_run_dir). A fork is a separate task: do not share a mutable remote "
        "workspace/session with its parent. "
        "Report the remote URL/IDs and progress; creation alone is not completion. Review the actual "
        "diff and test results before reporting success. Do not merge, deploy, upload credentials, "
        "or overwrite local changes without the user's applicable authorization. If the provider, "
        "authentication or repository access is unavailable, report the blocker and wait; never "
        "silently fall back to local implementation.\n"
    )
    if mode == "devin":
        skill = devin_skill()
        policy += (f"Read and use the delegate-to-devin skill at {json.dumps(str(skill))}. "
                   if skill else "Find and read the delegate-to-devin skill; it was not found at launch. ")
        policy += ("Follow its credential handling, session reuse, monitoring and review workflow. "
                   "Do not replace it with guessed API calls.\n")
    else:
        cli = cmux_cli() or "cmux"
        policy += (
            f"Use cmux Cloud via {json.dumps(cli)}. Check installed CLI help and authentication first. "
            "Official reference: https://cmux.com/docs/cloud/cli . Use cmux auth status, "
            "cmux vm ls --json and cmux vm route --json to inspect existing resources. "
            "Use cmux vm agent to run the coding agent remotely, selecting a supported agent, "
            "an explicit machine, a bounded prompt and an isolated remote working directory. "
            "Record machine/workspace/terminal IDs and inspect terminal output until complete. "
            "Reuse these resources for follow-ups. Check repository contents before any --sync "
            "upload; prefer a remote clone at the agreed commit, excluding secrets and unrelated "
            "files. Return a branch/commit or patch plus test evidence for review; do not pull over "
            "a dirty local tree. If no machine is available, establish cost/size with the user "
            "before provisioning one.\n"
        )
    return intro + policy + "Acknowledge this preference briefly, then wait for the next user task; do not replay old tasks."


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=MODES)
    args = parser.parse_args()
    print(instructions(args.mode))
