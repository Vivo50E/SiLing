"""Isolated, read-only MCP client. Configuration arrives via stdin, never argv."""
import asyncio
from contextlib import AsyncExitStack
from datetime import timedelta
import json
import os
import signal
import sys


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
            tool, cursor = None, None
            for _ in range(5):
                tools = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
                tool = next((t for t in tools.tools if t.name == 'jira_get_issue'), None)
                if tool is not None or not tools.nextCursor:
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
                    if result.isError:
                        failed.append(key)
                        continue
                    data = result.structuredContent
                    if data is None:
                        data = next((json.loads(c.text) for c in result.content
                                     if c.type == 'text' and len(c.text) <= 65536), None)
                    if isinstance(data, dict) and 'result' in data:
                        data = data['result']
                        if isinstance(data, str) and len(data) <= 65536:
                            data = json.loads(data)
                    if not isinstance(data, dict) or data.get('key') != key:
                        failed.append(key)
                        continue
                    fields = data.get('fields') if isinstance(data.get('fields'), dict) else data
                    state = fields.get('status', '')
                    if isinstance(state, dict):
                        state = state.get('name', '')
                    title = fields.get('summary')
                    items.append({'key': key, 'title': (title[:500] if isinstance(title, str) and title else key),
                                  'state': state[:100] if isinstance(state, str) else ''})
                except Exception:
                    failed.append(key)
            return {'items': items, 'failed': failed}


def main():
    def cancel(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, cancel)
    try:
        result = asyncio.run(query(json.loads(sys.stdin.read(1048576))))
    except ImportError:
        result = {'error': 'sdk_missing'}
    except BaseException:
        # Never send provider messages, headers, stderr or credentials to the parent.
        result = {'error': 'connection_failed'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
