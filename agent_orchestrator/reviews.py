"""On-demand PR/MR discovery and local index. No terminal input or provider writes."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import yaml

from .json_store import edit_json

MAX_ITEMS = 1000
SCAN_BYTES = 4 * 1024 * 1024
STATUS_TTL = 60
STATUS_LIMIT = 24
STATUS_BUDGET = 12
STATUS_ERRORS = {'host_unconfigured', 'unsupported', 'cli_missing', 'timeout', 'unavailable'}
STATUS_FIELDS = ('state', 'status_checked_at', 'status_attempted_at', 'status_error')


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


def _row_state(row):
    state = str(row.get('state', '')).lower()
    state = 'open' if state == 'opened' else state
    if state not in {'open', 'closed', 'merged'}:
        return 'unknown'
    return 'draft' if state == 'open' and (row.get('isDraft') or row.get('draft') or row.get('work_in_progress')) else state


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
                            state=_row_state(row),
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


def provider_hosts():
    """Use configured CLI host keys only; never return or persist credentials."""
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    hosts = {'gh': {'github.com'}, 'glab': {'gitlab.com'}}
    glab_dir = Path(os.environ.get('GLAB_CONFIG_DIR') or base / 'glab-cli')
    if not os.environ.get('GLAB_CONFIG_DIR') and not os.environ.get('XDG_CONFIG_HOME') and sys.platform == 'darwin':
        glab_dir = Path.home() / 'Library' / 'Application Support' / 'glab-cli'
    glab_path = glab_dir / 'config.yml'
    if not os.environ.get('GLAB_CONFIG_DIR'):
        try:
            configured_path = Path(_run(['glab', 'config', 'path'], None, timeout=1))
            if configured_path.is_absolute():
                glab_path = configured_path
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    configs = [('gh', Path(os.environ.get('GH_CONFIG_DIR') or base / 'gh') / 'hosts.yml'),
               ('glab', glab_path)]
    for provider, path in configs:
        try:
            with path.open() as config:
                raw = config.read(1048577)
            if len(raw) > 1048576:
                continue
            data = yaml.safe_load(raw)
            configured = data.get('hosts', {}) if provider == 'glab' and isinstance(data, dict) else data
            if isinstance(configured, dict):
                hosts[provider].update(str(host).lower() for host in configured
                                       if isinstance(configured[host], dict) and
                                       re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', str(host)))
        except (OSError, ValueError, yaml.YAMLError):
            pass
    for provider, variable in [('gh', 'GH_HOST'), ('glab', 'GITLAB_HOST')]:
        host = os.environ.get(variable, '').lower()
        if re.fullmatch(r'[a-z0-9.-]+(?::[0-9]+)?', host):
            hosts[provider].add(host)
    return hosts


def lookup_review(item, cwd, hosts, timeout=3):
    """Resolve a numeric review with a fixed CLI command on a trusted host."""
    result = {'status_attempted_at': time.time(), 'status_error': 'unsupported'}
    canonical = review_url(item.get('url', ''))
    if not canonical:
        return result
    parsed = urlsplit(canonical['url'])
    project = canonical['project']
    if (parsed.scheme != 'https' or
            not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', project) or
            any(part in {'.', '..'} for part in project.split('/'))):
        return result
    provider = 'gh' if canonical['kind'] == 'PR' else 'glab'
    if parsed.netloc not in hosts[provider]:
        result['status_error'] = 'host_unconfigured'
        return result
    if provider == 'gh':
        args = ['gh', 'pr', 'view', str(canonical['number']), '--repo', f'{parsed.netloc}/{project}',
                '--json', 'url,title,state,isDraft']
    else:
        args = ['glab', 'mr', 'view', str(canonical['number']), '--repo', f'https://{parsed.netloc}/{project}',
                '--output', 'json']
    try:
        row = json.loads(_run(args, cwd if cwd and Path(cwd).is_dir() else None, timeout=timeout))
        if not isinstance(row, dict):
            raise ValueError('invalid review')
        actual = review_url(row.get('url') or row.get('web_url'))
        if (not actual or actual['number'] != canonical['number'] or actual['kind'] != canonical['kind'] or
                urlsplit(actual['url']).netloc != parsed.netloc or
                (actual['project'].lower() if provider == 'gh' else actual['project']) !=
                (project.lower() if provider == 'gh' else project)):
            raise ValueError('review identity mismatch')
        state = _row_state(row)
        if state == 'unknown':
            raise ValueError('invalid review state')
        result.update(state=state, title=str(row.get('title') or canonical['title'])[:500],
                      status_checked_at=result['status_attempted_at'], status_error='')
    except FileNotFoundError:
        result['status_error'] = 'cli_missing'
    except subprocess.TimeoutExpired:
        result['status_error'] = 'timeout'
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        result['status_error'] = 'unavailable'
    return result


def _status_metadata(record):
    result = {}
    for name in ('status_checked_at', 'status_attempted_at'):
        value = record.get(name)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            result[name] = value
    error = record.get('status_error')
    if error in STATUS_ERRORS or error == '':
        result['status_error'] = error
    return result


def refresh_statuses(items, cwd, *, force=False):
    now = time.time()
    due = [item for item in items if force or now - item.get('status_attempted_at', 0) >= STATUS_TTL]
    due.sort(key=lambda item: item.get('status_attempted_at', 0))
    updates = {}
    if due:
        hosts = provider_hosts()
        deadline = time.monotonic() + STATUS_BUDGET
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, min(len(due), STATUS_LIMIT), 4):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                batch = due[start:min(start + 4, STATUS_LIMIT)]
                results = pool.map(lambda item: lookup_review(item, cwd, hosts, min(3, remaining)), batch)
                updates.update((item['url'], result) for item, result in zip(batch, results))
    pending = sum(item['url'] not in updates and now - item.get('status_attempted_at', 0) >= STATUS_TTL
                  for item in items)
    return updates, pending


def _apply_statuses(items, statuses):
    for item in items:
        status = statuses.get(item['url'], {})
        item.update({name: status[name] for name in STATUS_FIELDS if name in status})
        if item['source'] != 'linked' and status.get('title'):
            item['title'] = str(status['title'])[:500]


def discover(run, text, directory, *, lookup=True, status_lookup=False, force_status=False):
    """Remember observed links and incrementally inspect logs without saving text.

    The per-session index is separate from linked folders and source transcripts.
    A process-safe merge also prevents a slower count request losing branch results.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    observed_at = time.time()
    fresh = collect(run, text, lookup=lookup)
    branch_urls = {item['url'] for item in fresh['items'] if item['source'] == 'branch' and item['state'] != 'unknown'}
    with edit_json(directory / 'reviews.json', create=True) as state:
        statuses = state.setdefault('statuses', {})
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
                item.update(_status_metadata(record))
                saved[item['url']] = item
        for item in historical + fresh['items']:
            if item['source'] != 'linked':
                previous = saved.get(item['url'])
                # A plain output URL must not erase a previously fetched title/state.
                if not previous or item['source'] == 'branch':
                    saved[item['url']] = item
        for item in fresh['items']:
            if item['source'] == 'branch' and item['state'] != 'unknown':
                if observed_at >= statuses.get(item['url'], {}).get('status_attempted_at', 0):
                    statuses[item['url']] = dict(state=item['state'], title=item['title'],
                                                status_checked_at=observed_at, status_attempted_at=observed_at, status_error='')
        _apply_statuses(list(saved.values()), statuses)
        state['items'] = list(saved.values())[:MAX_ITEMS]
        result = {item['url']: item for item in state['items']}
        for item in fresh['items']:
            if item['source'] == 'linked':
                # Manual links supply labels, not a new provider status. Keep
                # the last observed status available to initial pane badges.
                previous = result.get(item['url'], {})
                result[item['url']] = dict(item, state=previous.get('state', item['state']))
        _apply_statuses(list(result.values()), statuses)
        fresh['items'] = list(result.values())[:MAX_ITEMS]
        fresh['history_pending'] = pending
        fresh['limit_reached'] = len(result) >= MAX_ITEMS
    if status_lookup:
        candidates = [item for item in fresh['items'] if item['url'] not in branch_urls]
        updates, pending_statuses = refresh_statuses(candidates, run.get('cwd'), force=force_status)
        with edit_json(directory / 'reviews.json') as state:
            statuses = state.setdefault('statuses', {})
            for url, update in updates.items():
                previous = statuses.get(url, {})
                if update['status_attempted_at'] >= previous.get('status_attempted_at', 0):
                    statuses[url] = {**previous, **update}
            # Bound the cache without adding removed manual links to associations.
            state['statuses'] = dict(sorted(statuses.items(), key=lambda pair:
                                           pair[1].get('status_attempted_at', 0), reverse=True)[:MAX_ITEMS])
            _apply_statuses(state.get('items', []), state['statuses'])
            _apply_statuses(fresh['items'], state['statuses'])
        fresh['status_pending'] = pending_statuses
    fresh['status_failed'] = sum(bool(item.get('status_error')) for item in fresh['items'])
    return fresh
