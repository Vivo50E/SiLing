"""Isolated, read-only MCP client. Configuration arrives via stdin, never argv."""
import asyncio
from contextlib import AsyncExitStack
from datetime import timedelta
import json
import os
import signal
import sys
import re

from . import jira, jira_topics


def result_data(result):
    if result.isError:
        return None
    data = result.structuredContent
    if data is None:
        data = next((json.loads(c.text) for c in result.content
                     if c.type == 'text' and len(c.text) <= 65536), None)
    if isinstance(data, dict) and 'result' in data:
        data = data['result']
        if isinstance(data, str) and len(data) <= 65536:
            data = json.loads(data)
    return data


def issue_row(data):
    if not isinstance(data, dict) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,10}', str(data.get('key', ''))):
        return None
    fields = data.get('fields') if isinstance(data.get('fields'), dict) else data
    state = fields.get('status', '')
    if isinstance(state, dict):
        state = state.get('name', '')
    title = fields.get('summary')
    return {'key': data['key'], 'title': title[:500] if isinstance(title, str) and title else data['key'],
            'state': state[:100] if isinstance(state, str) else ''}


async def query(payload):
    # Lazy imports keep a missing optional installation from breaking Dashboard startup.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import PaginatedRequestParams
    import anyio
    import httpx

    server = payload['server']
    with anyio.fail_after(25):
        async with AsyncExitStack() as stack:
            if server.get('command'):
                params = StdioServerParameters(command=server['command'], args=server.get('args', []),
                                               env={**server.get('env', {}), 'READ_ONLY_MODE': 'true'},
                                               cwd=server.get('cwd'))
                error_log = stack.enter_context(open(os.devnull, 'w'))
                streams = await stack.enter_async_context(stdio_client(params, errlog=error_log))
            else:
                if server.get('type') == 'sse':
                    transport = sse_client(server['url'], headers=server.get('headers', {}), sse_read_timeout=8)
                else:
                    client = await stack.enter_async_context(httpx.AsyncClient(
                        headers=server.get('headers', {}), timeout=8, follow_redirects=False))
                    transport = streamable_http_client(server['url'], http_client=client)
                streams = await stack.enter_async_context(transport)
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1],
                                                                     read_timeout_seconds=timedelta(seconds=8)))
            await session.initialize()
            # Tool descriptions/annotations are untrusted. Never let the server choose a command.
            tool, search, cursor = None, None, None
            for _ in range(5):
                tools = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
                tool = next((t for t in tools.tools if t.name == 'jira_get_issue'), tool)
                search = next((t for t in tools.tools if t.name == 'jira_search'), search)
                if (tool is not None and search is not None) or not tools.nextCursor:
                    break
                cursor = tools.nextCursor
            if tool is None:
                return {'error': 'unsupported_tool'}
            schema = tool.inputSchema
            if 'issue_key' not in schema.get('properties', {}) or any(
                    key not in {'issue_key', 'fields'} for key in schema.get('required', [])):
                return {'error': 'unsupported_tool'}
            items, failed = [], []
            for key in payload.get('keys', [])[:8]:
                args = {'issue_key': key}
                if 'fields' in schema.get('properties', {}):
                    args['fields'] = 'summary,status'
                try:
                    result = await session.call_tool('jira_get_issue', args)
                    row = issue_row(result_data(result))
                    if row is None or row['key'] != key:
                        failed.append(key)
                        continue
                    items.append(row)
                except Exception:
                    failed.append(key)
            supported = bool(search and not server.get('search_disabled')
                             and {'jql', 'fields', 'limit'} <= set(search.inputSchema.get('properties', {}))
                             and set(search.inputSchema.get('required', [])) <= {'jql', 'fields', 'limit'})
            response = {'items': items, 'failed': failed, 'search_supported': supported}
            terms = payload.get('terms', [])
            topics = payload.get('topics', [])
            if terms or topics:
                if (not jira_topics.valid_topics(topics)
                        or not isinstance(terms, list) or len(terms) > 5
                        or any(not isinstance(t, str) or not re.fullmatch(r'[a-z][a-z0-9]{2,23}|[\u3400-\u9fff]{2,12}', t) for t in terms)):
                    response['search_error'] = 'invalid_terms'
                elif not supported:
                    response['search_error'] = 'unsupported_search'
                else:
                    try:
                        groups = ([terms] if terms else []) + topics
                        clauses = [' AND '.join('summary ~ "' + term + '"' for term in group) for group in groups]
                        jql = (clauses[0] if len(clauses) == 1 else ' OR '.join('(' + clause + ')' for clause in clauses)) + ' ORDER BY updated DESC'
                        data = result_data(await session.call_tool('jira_search', {
                            'jql': jql, 'fields': 'summary,status', 'limit': 8}))
                        rows = data.get('issues') if isinstance(data, dict) else data
                        if not isinstance(rows, list):
                            raise ValueError('Invalid search response')
                        for data in rows[:8]:
                            row = issue_row(data)
                            if row:
                                topic_match = any(jira.matches_task(row['title'], words) for words in topics)
                                if topic_match or jira.matches_task(row['title'], terms):
                                    items.append({**row, 'match': 'topic' if topic_match else 'task'})
                    except Exception:
                        response['search_error'] = 'search_failed'
            return response


def main():
    def cancel(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, cancel)
    try:
        result = asyncio.run(query(json.loads(sys.stdin.read(1048576))))
    except ImportError:
        result = {'error': 'sdk_missing'}
    except BaseException as exc:
        # Never send provider messages, headers, stderr or credentials to the parent.
        result = {'error': 'connection_failed'}
        pending = [exc]
        while pending:
            error = pending.pop()
            pending.extend(getattr(error, 'exceptions', ()))
            response = getattr(error, 'response', None)
            if getattr(response, 'status_code', None) in (401, 403):
                result = {'error': 'auth_required'}
                break
            if isinstance(error, TimeoutError) or type(error).__name__ in {'ConnectTimeout', 'ReadTimeout', 'WriteTimeout', 'PoolTimeout'}:
                result = {'error': 'timeout'}
            elif type(error).__name__ in {'ConnectError', 'ProxyError'}:
                result = {'error': 'network_error'}
            elif getattr(response, 'status_code', 0) >= 500:
                result = {'error': 'server_error'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
