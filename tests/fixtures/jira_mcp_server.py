"""Tiny real stdio MCP fixture. Records protocol requests, never contacts Jira."""
import json
import os
import sys

for line in sys.stdin:
    request = json.loads(line)
    if os.environ.get('FIXTURE_RECORD'):
        with open(os.environ['FIXTURE_RECORD'], 'a') as out:
            out.write(json.dumps(request) + '\n')
    if 'id' not in request:
        continue
    method = request['method']
    if method == 'initialize':
        result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': os.environ.get('FIXTURE_TOOL', 'jira_get_issue'),
                             'inputSchema': {'type': 'object', 'properties': {'issue_key': {'type': 'string'},
                                             'fields': {'type': 'string'}}, 'required': ['issue_key']}}]}
        if os.environ.get('FIXTURE_PAGED') and not request.get('params', {}).get('cursor'):
            result = {'tools': [], 'nextCursor': 'fixture-page-2'}
        if os.environ.get('FIXTURE_SEARCH'):
            result = {'tools': result['tools'] + [{'name': 'jira_search', 'inputSchema': {'type': 'object',
                'properties': {'jql': {'type': 'string'}, 'fields': {'type': 'string'}, 'limit': {'type': 'integer'}},
                'required': ['jql']}}]}
        if os.environ.get('FIXTURE_MAAS'):
            for tool in result.get('tools', []):
                props = tool['inputSchema']['properties']
                props['fields'] = {'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'null'}]}
                if tool['name'] == 'jira_get_issue':
                    props['issue_id'] = props.pop('issue_key')
                    tool['inputSchema']['required'] = ['issue_id']
                elif tool['name'] == 'jira_search':
                    props['top_k'] = props.pop('limit')
                if os.environ.get('FIXTURE_UNKNOWN_REQUIRED'):
                    tool['inputSchema']['required'].append('unreviewed_argument')
    elif method == 'tools/call':
        key = request['params']['arguments'].get('issue_id' if os.environ.get('FIXTURE_MAAS') else 'issue_key', '')
        value = {'key': 'OTHER-99' if key == 'WRONG-1' else key,
                 'fields': {'summary': 'Fixture ticket <img src=x>', 'status': {'name': 'In Progress'}}}
        if key == 'FAIL-1':
            result = {'isError': True, 'content': [{'type': 'text', 'text': 'private-provider-error'}]}
        else:
            result = {'content': [{'type': 'text', 'text': json.dumps(value)}]}
            if key == 'WRAPPED-1':
                result['structuredContent'] = {'result': json.dumps(value)}
        if request['params']['name'] == 'jira_search':
            result = {'content': [], 'structuredContent': {'issues': [
                {'key': 'SRAM-7', 'fields': {'summary': 'SRAM Vmin Vmax fallout', 'status': {'name': 'Open'}}},
                {'key': 'OTHER-8', 'fields': {'summary': 'Unrelated fix', 'status': {'name': 'Done'}}},
                {'key': 'INVALID', 'fields': {'summary': 'SRAM Vmin Vmax'}},
            ]}}
        if os.environ.get('FIXTURE_MAAS') and not result.get('isError'):
            if request['params']['name'] == 'jira_get_issue':
                body = json.loads(result['content'][0]['text'])
            else:
                body = result['structuredContent']
            envelope = {'success': not bool(os.environ.get('FIXTURE_FAILURE_ENVELOPE')), 'data': body,
                        'error': 'private-provider-details' if os.environ.get('FIXTURE_FAILURE_ENVELOPE') else None}
            result = {'content': [], 'structuredContent': envelope}
    else:
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
