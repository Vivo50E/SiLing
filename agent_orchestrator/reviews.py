"""On-demand PR/MR discovery and local index. No terminal input or provider writes."""
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit

from .json_store import edit_json

MAX_ITEMS = 1000
SCAN_BYTES = 4 * 1024 * 1024


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
    # A fork may have PRs targeting either its own origin or upstream.
    targets = list(dict.fromkeys([target] + ([origin] if origin else [])))
    found = {}
    failed = False
    supported = False
    for host, project in targets:
        if host == 'github.com' or 'github' in host:
            args = ['gh', 'pr', 'list', '--repo', f'{host}/{project}', '--head', branch,
                    '--state', 'all', '--limit', '100', '--json', 'url,title,state,isDraft,headRepositoryOwner']
            provider = 'GitHub'
        elif 'gitlab' in host:
            args = ['glab', 'mr', 'list', '--repo', f'https://{host}/{project}', '--source-branch', branch,
                    '--all', '--per-page', '100', '--output', 'json']
            provider = 'GitLab'
        else:
            continue
        supported = True
        try:
            rows = json.loads(_run(args, cwd, timeout=8))
            if not isinstance(rows, list):
                raise ValueError('invalid provider response')
            for row in rows[:100]:
                item = review_url(row.get('url') or row.get('web_url'))
                if not item:
                    continue
                # GitHub head filters also return same-named branches in other forks.
                owner = (row.get('headRepositoryOwner') or {}).get('login')
                if provider == 'GitHub' and origin and owner and owner.lower() != origin[1].split('/')[0].lower():
                    continue
                item.update(title=str(row.get('title') or item['title'])[:500],
                            state='draft' if row.get('isDraft') or row.get('draft') else str(row.get('state') or 'unknown').lower(),
                            source='branch')
                found[item['url']] = item
        except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
            failed = True
    warning = ''
    if failed:
        warning = 'Branch lookup unavailable. Check gh/glab installation and login on the session host; existing links are still available.'
    elif not supported:
        warning = 'Repository host is not supported for automatic lookup. Add a PR/MR link below.'
    return list(found.values()), branch, warning


def collect(run, text='', *, lookup=True, text_limit=262144):
    items = {}
    for record in run.get('linked_folders') or []:
        item = review_url(record.get('path', ''))
        if item:
            item.update(source='linked', title=str(record.get('label') or item['title'])[:500])
            items[item['url']] = item
    # Bound terminal/log inspection; no full transcript scan and no URL requests.
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text[-text_limit:])
    for raw in re.findall(r'https?://[^\s<>"\x00-\x20]+', clean):
        item = review_url(raw.rstrip('.,;:!?)\u3002\uff0c\uff09]}`\''))
        if item and item['url'] not in items:
            item['source'] = 'output'
            items[item['url']] = item
        if len(items) >= MAX_ITEMS:
            break
    found, branch, warning = branch_reviews(run.get('cwd')) if lookup else ([], '', '')
    for item in found:
        items[item['url']] = item
    return {'items': list(items.values())[:MAX_ITEMS], 'branch': branch, 'warning': warning}


def discover(run, text, directory, *, lookup=True):
    """Remember observed links and incrementally inspect logs without saving text.

    The per-session index is separate from linked folders and source transcripts.
    A process-safe merge also prevents a slower count request losing branch results.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fresh = collect(run, text, lookup=lookup)
    with edit_json(directory / 'reviews.json', create=True) as state:
        pending = False
        historical = []
        if run.get('run_dir') and run.get('log_file'):
            try:
                with (Path(run['run_dir']) / run['log_file']).open('rb') as log:
                    stat = os.fstat(log.fileno())
                    identity = [stat.st_dev, stat.st_ino]
                    offset = state.get('offset', 0) if state.get('log_identity') == identity else 0
                    if not isinstance(offset, int) or not 0 <= offset <= stat.st_size:
                        offset = 0
                    # Overlap catches URLs split by the previous byte boundary.
                    log.seek(max(0, offset - min(8192, SCAN_BYTES // 4)))
                    chunk = log.read(SCAN_BYTES)
                    state['offset'] = log.tell()
                    state['log_identity'] = identity
                    pending = log.tell() < stat.st_size
                    if pending:
                        # Do not index a truncated /pull/123 as /pull/1.
                        boundary = max(chunk.rfind(separator) for separator in (b' ', b'\n', b'\r', b'\t'))
                        chunk = chunk[:boundary + 1]
                    historical = collect({}, chunk.decode('utf-8', 'replace'), lookup=False, text_limit=SCAN_BYTES)['items']
            except OSError:
                pass
        saved = {}
        for record in state.get('items', []):
            if not isinstance(record, dict):
                continue
            item = review_url(record.get('url', ''))
            if item:
                item.update(title=str(record.get('title') or item['title'])[:500],
                            state=str(record.get('state') or 'unknown')[:50],
                            source=record.get('source') if record.get('source') in {'branch', 'output'} else 'output')
                saved[item['url']] = item
        for item in historical + fresh['items']:
            if item['source'] != 'linked':
                previous = saved.get(item['url'])
                # A plain output URL must not erase a previously fetched title/state.
                if not previous or item['source'] == 'branch':
                    saved[item['url']] = item
        state['items'] = list(saved.values())[:MAX_ITEMS]
        result = {item['url']: item for item in state['items']}
        for item in fresh['items']:
            if item['source'] == 'linked':
                # Manual links supply labels, not a new provider status. Keep
                # the last observed status available to initial pane badges.
                previous = result.get(item['url'], {})
                result[item['url']] = dict(item, state=previous.get('state', item['state']))
        fresh['items'] = list(result.values())[:MAX_ITEMS]
        fresh['history_pending'] = pending
        fresh['limit_reached'] = len(result) >= MAX_ITEMS
        return fresh
