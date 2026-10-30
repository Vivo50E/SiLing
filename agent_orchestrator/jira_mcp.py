"""Explicitly connected Jira MCP, bounded key resolution and persistent associations."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

from . import jira
from .json_store import edit_json, write_json

KEY = re.compile(r'(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,10})(?![A-Za-z0-9_])')
ERRORS = {'sdk_missing', 'unsupported_tool', 'connection_failed', 'config_changed', 'busy'}


def read_json(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def web_base(value):
    value = str(value).strip().rstrip('/')
    url = urlsplit(value)
    # Accessing port also rejects malformed/non-numeric authority ports.
    _ = url.port
    if (url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(ord(c) < 33 for c in value)
            or (url.scheme == 'http' and url.hostname not in {'localhost', '127.0.0.1', '::1'})
            or any(p in {'.', '..'} for p in url.path.split('/'))):
        raise ValueError('Use HTTPS, or HTTP on loopback, without credentials or query parameters.')
    return urlunsplit((url.scheme, url.netloc.lower(), url.path, '', ''))


def server_config(path, name):
    path = Path(path).expanduser()
    if not path.is_absolute() or path.stat().st_size > 1048576:
        raise ValueError('Choose an absolute MCP JSON configuration path (at most 1 MiB).')
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError('Expected a JSON mcpServers object.')
    servers = raw.get('mcpServers', {})
    if not isinstance(servers, dict):
        raise ValueError('Expected a JSON mcpServers object.')
    if name is None:
        return [{'name': k} for k, v in servers.items() if isinstance(k, str) and isinstance(v, dict)][:100]
    server = servers.get(name)
    if not isinstance(server, dict) or server.get('disabled') is True:
        raise ValueError('Select an enabled MCP server from this file.')
    # Resolve environment references locally; never return expanded configuration to browsers.
    def expand(value):
        if not isinstance(value, str):
            raise ValueError('MCP command, arguments, headers and environment values must be strings.')
        def replacement(match):
            if match[1] not in os.environ:
                raise ValueError('A required MCP environment variable is missing.')
            return os.environ[match[1]]
        return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', replacement, value)
    if server.get('command'):
        args, env = server.get('args', []), server.get('env', {})
        if not isinstance(args, list) or not isinstance(env, dict) or len(args) > 100:
            raise ValueError('Invalid MCP arguments or environment.')
        cwd = Path(expand(server.get('cwd', str(path.parent)))).expanduser()
        if not cwd.is_absolute() or not cwd.is_dir():
            raise ValueError('MCP working directory must be an existing absolute directory.')
        result = {'command': expand(server['command']), 'args': [expand(a) for a in args],
                  'env': {k: expand(v) for k, v in env.items()}, 'cwd': str(cwd)}
    elif server.get('url'):
        headers = server.get('headers', {})
        if not isinstance(headers, dict) or server.get('type', 'http') not in {'http', 'sse', 'streamable-http'}:
            raise ValueError('Expected stdio, HTTP or SSE MCP configuration.')
        result = {'url': web_base(expand(server['url'])), 'headers': {k: expand(v) for k, v in headers.items()},
                  'type': server.get('type', 'http')}
    else:
        raise ValueError('Expected stdio, HTTP or SSE MCP configuration.')
    return result


def fingerprint(server):
    return hashlib.sha256(json.dumps(server, sort_keys=True).encode()).hexdigest()


def call_worker(server, keys):
    try:
        with subprocess.Popen([sys.executable, '-m', 'agent_orchestrator.jira_mcp_worker'],
                              stdin=subprocess.PIPE, cwd=Path(__file__).resolve().parent.parent,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                stdout, _ = process.communicate(json.dumps({'server': server, 'keys': keys}), timeout=32)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                return {'error': 'connection_failed'}
            data = json.loads(stdout) if process.returncode == 0 and len(stdout) < 65536 else {}
        if not isinstance(data, dict):
            return {'error': 'connection_failed'}
        if data.get('error'):
            return {'error': data['error'] if data['error'] in ERRORS else 'connection_failed'}
        if not isinstance(data.get('items'), list) or not isinstance(data.get('failed'), list):
            return {'error': 'connection_failed'}
        return data
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'error': 'connection_failed'}


class JiraMCP:
    def __init__(self, outputs):
        self.path = Path(outputs) / '.jira-mcp.json'
        self.slots = threading.BoundedSemaphore(2)
        self.config_lock = threading.Lock()

    def status(self):
        cfg = read_json(self.path)
        return {k: cfg[k] for k in ('enabled', 'config_file', 'server_name', 'base_url') if k in cfg}

    def connect(self, body):
        if set(body) != {'config_file', 'server_name', 'base_url'}:
            raise ValueError('Specify config_file, server_name and base_url only.')
        path, name = body['config_file'], body['server_name']
        if not isinstance(path, str) or not isinstance(name, str) or not name or len(name) > 200:
            raise ValueError('Select an MCP configuration file and server.')
        server = server_config(path, name)
        base = web_base(body['base_url'] or server.get('env', {}).get('JIRA_URL', ''))
        with self.config_lock:
            before = read_json(self.path)
        if not self.slots.acquire(blocking=False):
            return {'error': 'busy'}
        try:
            result = call_worker(server, [])
        finally:
            self.slots.release()
        if result.get('error'):
            return result
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_lock:
            if read_json(self.path) != before:
                return {'error': 'config_changed'}
            write_json(self.path, {'enabled': True, 'config_file': str(Path(path).expanduser()),
                                  'server_name': name, 'base_url': base, 'fingerprint': fingerprint(server),
                                  'connection_id': uuid.uuid4().hex})
        return self.status()

    def disconnect(self):
        with self.config_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.path, {'enabled': False, 'connection_id': uuid.uuid4().hex})
        return {'enabled': False}

    def discover(self, run, text, directory, *, lookup=True, force=False):
        result = jira.collect(run, text)
        directory = Path(directory)
        path = directory / 'jira.json'
        saved = read_json(path)
        items = {i['url']: i for i in saved.get('items', []) if isinstance(i, dict) and jira.ticket_url(i.get('url', ''))}
        for item in result['items']:
            if item['source'] == 'linked' or item['url'] not in items:
                items[item['url']] = {**items.get(item['url'], {}), **item}
        cfg = read_json(self.path)
        result['connected'] = cfg.get('enabled') is True
        if lookup and cfg.get('enabled'):
            # Full URLs from other sites are not evidence for this Jira instance.
            clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text[-262144:])
            evidence = '\n'.join(str(run.get(k) or '') for k in ('task', 'display_name', 'initial_prompt'))[-32768:]
            # Agent cwd is stable repository evidence. A shell/SSH pane may have cd'ed elsewhere.
            if run.get('agent') in {'claude', 'codex', 'cursor'} and run.get('cwd'):
                try:
                    branch = subprocess.run(['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'],
                                            cwd=run['cwd'], capture_output=True, text=True, timeout=2)
                    if branch.returncode == 0:
                        evidence += '\n' + branch.stdout[:4096]
                except (OSError, subprocess.TimeoutExpired):
                    pass
            # Reuse already discovered PR/MR titles without new provider commands.
            review_items = read_json(directory / 'reviews.json').get('items', [])
            evidence += '\n' + '\n'.join(str(i.get('title', ''))[:500] for i in review_items if isinstance(i, dict))[:32768]
            context = evidence + '\n' + clean
            context_links = jira.collect({}, context)['items']
            context = re.sub(r'https?://[^\s<>"\x00-\x20]+', '', context)
            candidates = list(dict.fromkeys(KEY.findall(context)))[:100]
            candidates += [i['key'] for i in context_links if i['url'] == cfg['base_url'] + '/browse/' + i['key']]
            candidates += [i['key'] for i in items.values() if i['url'] == cfg['base_url'] + '/browse/' + i['key']]
            connection = fingerprint({'server': cfg.get('fingerprint'), 'base_url': cfg['base_url']})
            attempts = saved.get('attempts', {}) if saved.get('connection') == connection else {}
            due = [key for key in dict.fromkeys(candidates) if force or time.time() - attempts.get(key, 0) >= 60]
            due.sort(key=lambda key: attempts.get(key, 0))
            keys = due[:8]
            result['pending'] = max(0, len(due) - len(keys))
            if keys:
                started = time.time()
                if not self.slots.acquire(blocking=False):
                    result['mcp_error'] = 'busy'
                else:
                    try:
                        server = server_config(cfg['config_file'], cfg['server_name'])
                        if fingerprint(server) != cfg.get('fingerprint'):
                            response = {'error': 'config_changed'}
                        else:
                            response = call_worker(server, keys)
                        # Disconnect/reconfigure while a query runs must not save its response.
                        with self.config_lock:
                            if read_json(self.path) != cfg:
                                return {**result, 'items': list(items.values())[:1000], 'mcp_error': 'config_changed'}
                            if response.get('error'):
                                result['mcp_error'] = response['error']
                            else:
                                now = started
                                updates = []
                                for row in response.get('items', []):
                                    if not isinstance(row, dict) or row.get('key') not in keys:
                                        continue
                                    key = row['key']
                                    updates.append({'url': cfg['base_url'] + '/browse/' + key, 'key': key,
                                                    'title': str(row.get('title') or key)[:500],
                                                    'state': str(row.get('state') or '')[:100], 'source': 'mcp',
                                                    'checked_at': now})
                                directory.mkdir(parents=True, exist_ok=True)
                                with edit_json(path, create=True) as state:
                                    previous = {i['url']: i for i in state.get('items', [])}
                                    previous.update({i['url']: i for i in updates
                                                     if i['checked_at'] >= previous.get(i['url'], {}).get('checked_at', 0)})
                                    state['items'] = list(previous.values())[-1000:]
                                    old_attempts = state.get('attempts', {}) if state.get('connection') == connection else {}
                                    old_attempts.update({key: max(now, old_attempts.get(key, 0)) for key in keys})
                                    state['attempts'] = dict(sorted(old_attempts.items(), key=lambda kv: kv[1])[-1000:])
                                    state['connection'] = connection
                                items.update(previous)
                                # Manual labels take precedence over a provider title.
                                for item in result['items']:
                                    if item['source'] == 'linked':
                                        items[item['url']].update(title=item['title'], source='linked')
                                result['failed'] = len(response.get('failed', []))
                    except (OSError, ValueError, KeyError, TypeError):
                        result['mcp_error'] = 'connection_failed'
                    finally:
                        self.slots.release()
        result['items'] = list(items.values())[:1000]
        return result
