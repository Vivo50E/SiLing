"""Read-only, on-demand PR/MR discovery. No terminal input or background polling."""
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit


def review_url(value):
    try:
        url = urlsplit(str(value).strip())
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
            return None
        match = re.fullmatch(r'/(.+)/-/merge_requests/([1-9][0-9]*)(?:/(?:diffs|commits))?/?', url.path)
        kind = 'MR'
        if not match:
            match = re.fullmatch(r'/([^/]+/[^/]+)/pull/([1-9][0-9]*)(?:/(?:files|commits|checks))?/?', url.path)
            kind = 'PR'
        if not match or any(c in str(value) for c in '\r\n\t'):
            return None
        project, number = match.groups()
        path = f'/{project}/{"-/merge_requests" if kind == "MR" else "pull"}/{number}'
        return {'url': urlunsplit((url.scheme, url.netloc.lower(), path, '', '')),
                'kind': kind, 'number': int(number), 'project': project,
                'title': f'{kind} {"!" if kind == "MR" else "#"}{number}', 'state': 'unknown'}
    except ValueError:
        return None


def _run(args, cwd, timeout=3):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GH_PROMPT_DISABLED': '1',
           'GLAB_PROMPT_DISABLED': '1', 'NO_COLOR': '1'}
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('command unavailable')
    return result.stdout.strip()


def _remote(value):
    # Strip credentials; never pass a raw Git remote to a provider CLI.
    if '://' not in value:
        match = re.fullmatch(r'(?:[^@/]+@)?([^:/]+):(.+)', value)
        if not match:
            return None
        host, project = match.groups()
    else:
        parsed = urlsplit(value)
        host, project = parsed.hostname, parsed.path.lstrip('/')
    project = project.removesuffix('.git').rstrip('/')
    if not host or not re.fullmatch(r'[A-Za-z0-9._-]+', host) or not re.fullmatch(r'[A-Za-z0-9._/-]+', project) or '/' not in project:
        return None
    return host.lower(), project


def branch_reviews(cwd):
    if not cwd:
        return [], '', 'No repository directory is available. Add a PR/MR link below.'
    try:
        branch = _run(['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'], cwd)
        origin = _remote(_run(['git', 'remote', 'get-url', 'origin'], cwd))
        try:
            target = _remote(_run(['git', 'remote', 'get-url', 'upstream'], cwd)) or origin
        except (OSError, ValueError, subprocess.SubprocessError):
            target = origin
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], '', 'No Git branch or remote found. Add a PR/MR link below.'
    if not target:
        return [], branch, 'Repository host is not supported for automatic lookup. Add a PR/MR link below.'
    host, project = target
    try:
        if host == 'github.com' or 'github' in host:
            args = ['gh', 'pr', 'list', '--repo', f'{host}/{project}', '--head', branch,
                    '--state', 'all', '--limit', '30', '--json', 'url,title,state,isDraft,headRepositoryOwner']
            provider = 'GitHub'
        elif 'gitlab' in host:
            args = ['glab', 'mr', 'list', '--repo', f'https://{host}/{project}', '--source-branch', branch,
                    '--all', '--per-page', '30', '--output', 'json']
            provider = 'GitLab'
        else:
            return [], branch, 'Repository host is not supported for automatic lookup. Add a PR/MR link below.'
        rows = json.loads(_run(args, cwd, timeout=8))
        if not isinstance(rows, list):
            raise ValueError('invalid provider response')
        found = []
        for row in rows[:30]:
            item = review_url(row.get('url') or row.get('web_url'))
            if not item:
                continue
            # GitHub head filters can also return same-named branches from other forks.
            owner = (row.get('headRepositoryOwner') or {}).get('login')
            if provider == 'GitHub' and origin and owner and owner.lower() != origin[1].split('/')[0].lower():
                continue
            item.update(title=str(row.get('title') or item['title'])[:500],
                        state='draft' if row.get('isDraft') or row.get('draft') else str(row.get('state') or 'unknown').lower(),
                        source='branch')
            found.append(item)
        return found, branch, ''
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
        return [], branch, 'Branch lookup unavailable. Check gh/glab installation and login on the session host; existing links are still available.'


def collect(run, text='', *, lookup=True):
    items = {}
    for record in run.get('linked_folders') or []:
        item = review_url(record.get('path', ''))
        if item:
            item.update(source='linked', title=str(record.get('label') or item['title'])[:500])
            items[item['url']] = item
    # Bound terminal/log inspection; no full transcript scan and no URL requests.
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text[-262144:])
    for raw in re.findall(r'https?://[^\s<>"\x00-\x20]+', clean):
        item = review_url(raw.rstrip('.,;:!?)\u3002\uff0c\uff09]}`\''))
        if item and item['url'] not in items:
            item['source'] = 'output'
            items[item['url']] = item
        if len(items) >= 100:
            break
    found, branch, warning = branch_reviews(run.get('cwd')) if lookup else ([], '', '')
    for item in found:
        items[item['url']] = item
    return {'items': list(items.values())[:100], 'branch': branch, 'warning': warning}
