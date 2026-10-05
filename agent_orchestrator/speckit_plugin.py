"""Spec Kit adapter: inspect local projects and prepare explicit agent stages."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

STAGES = ('setup', 'constitution', 'specify', 'clarify', 'plan', 'tasks', 'analyze', 'checklist', 'implement')
INTEGRATIONS = {'claude': 'claude', 'codex': 'codex', 'cursor': 'cursor-agent'}


def project(body):
    raw = body.get('cwd')
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise ValueError('Choose an absolute local project directory')
    root = Path(raw).resolve()
    if not root.is_dir():
        raise ValueError('Project directory does not exist on the Dashboard host')
    agent = body.get('agent', 'claude')
    if not isinstance(agent, str) or agent not in INTEGRATIONS:
        raise ValueError('Choose Claude, Codex or Cursor')
    return root, agent


def instruction(root, agent, stage):
    base = {'claude': '.claude', 'codex': '.codex', 'cursor': '.cursor'}[agent]
    candidates = [f'{base}/skills/speckit-{stage}/SKILL.md',
                  f'{base}/commands/speckit.{stage}.md',
                  f'{base}/commands/speckit-{stage}.md']
    if agent == 'codex':
        candidates += [f'.agents/skills/speckit-{stage}/SKILL.md',
                       f'.codex/prompts/speckit.{stage}.md']
    for relative in candidates:
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Spec Kit instruction symlink leaves the project')
        if target.is_file():
            return relative
    return None


def inspect(body):
    root, agent = project(body)
    if not (root / '.specify').resolve().is_relative_to(root):
        raise ValueError('Spec Kit metadata symlink leaves the project')
    stages = {stage: instruction(root, agent, stage) for stage in STAGES if stage != 'setup'}
    cli = shutil.which('specify')
    if not cli:
        candidate = Path.home() / '.local/bin/specify'
        if candidate.is_file() and os.access(candidate, os.X_OK):
            cli = str(candidate)
    return {'cwd': str(root), 'agent': agent, 'specify_cli': cli,
            'initialized': (root / '.specify').is_dir(), 'stages': stages}


def prepare(body):
    state = inspect(body)
    stage = body.get('stage', 'setup')
    if stage not in STAGES:
        raise ValueError('Unknown Spec Kit stage')
    request = body.get('request', '')
    if not isinstance(request, str) or len(request) > 16000:
        raise ValueError('Stage instructions must be at most 16000 characters')
    if stage != 'setup' and not state['stages'].get(stage):
        raise ValueError('This stage is not installed for the selected agent; run setup first')
    if stage == 'specify' and not request.strip():
        raise ValueError('Describe the feature before starting Specify')
    root = state['cwd']
    prompt = f'''You are running the optional SiLing Spec Kit plugin in project {json.dumps(root)}.
Execute only the explicitly selected stage: {stage}. Follow this project's instructions.
Do not automatically advance to another stage, publish, push, merge, or create issues.
If a feature is ambiguous or a required answer is missing, ask the user in this session.
'''
    if stage == 'setup':
        prompt += f'''Set up GitHub Spec Kit for integration {INTEGRATIONS[state['agent']]}.
Read the official current instructions at https://github.com/github/spec-kit and inspect existing .specify and agent instruction files first.
Use an existing Specify CLI when available; otherwise install Specify in a project-local isolated environment, never alter global packages.
Inspect `specify init --help` for supported flags (--integration or legacy --ai). Initialize an empty staging directory first, then copy only missing Spec Kit support files into this project.
Never overwrite existing files, remove files, replace user configuration, initialize git, or change branches. Report conflicts for the user to resolve.
Check the installed stage instructions and summarize what was created. Stop after setup.
'''
    else:
        prompt += f'''Read and follow the installed stage instructions at {json.dumps(state['stages'][stage])}. Treat the user's request below as its arguments, not a shell command.
Check the current feature and prerequisite artifacts first. If multiple features exist, ask which feature to use. Do not implement code unless the selected stage is implement.
'''
    prompt += '''\nAfter completing this stage, report the artifact paths and any unresolved questions.
Register each generated document in this session's SiLing Files using `siling link-file <absolute-path> --purpose deliverable` when that CLI is available. If registration fails, report it accurately and still list the paths.
\nUser's stage request:\n''' + request.strip()
    delegation = {'agent': state['agent'], 'cwd': root, 'prompt': prompt,
                  'label': f'Spec Kit · {stage}', 'inherit_linked_items': False}
    digest = hashlib.sha256(json.dumps(delegation, sort_keys=True).encode()).hexdigest()
    return {'project': state, 'delegation': delegation, 'preview_id': digest}
