"""Reviewed argument adapters for fixed Jira read tools; ignore tool descriptions."""
import re

PROJECT = re.compile(r'[A-Z][A-Z0-9_]{0,31}')


def shape(value):
    if not isinstance(value, dict):
        return {}
    if 'anyOf' in value:
        options = value['anyOf']
        if not isinstance(options, list):
            return {}
        actual = [item for item in options if isinstance(item, dict) and item.get('type') != 'null']
        return actual[0] if len(actual) == 1 else {}
    return value


def properties(tool):
    schema = tool.inputSchema
    if not isinstance(schema, dict) or not isinstance(schema.get('properties'), dict):
        return {}, None
    required = schema.get('required', [])
    if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
        return {}, None
    return schema['properties'], required


def field_value(props):
    field = shape(props.get('fields'))
    if field.get('type') == 'string':
        return 'summary,status'
    if field.get('type') == 'array' and shape(field.get('items')).get('type') == 'string':
        return ['summary', 'status']
    return None


def issue_arguments(tool, key):
    props, required = properties(tool)
    ids = [name for name in ('issue_key', 'issue_id') if name in props]
    if len(ids) != 1 or required is None:
        return None
    name = ids[0]
    if shape(props[name]).get('type') != 'string':
        return None
    args = {name: key}
    if 'fields' in props:
        fields = field_value(props)
        if fields is None:
            return None
        args['fields'] = fields
    for flag in ('expand_comments', 'expand_attachments', 'expand_changelog', 'full_text', 'include_raw_adf'):
        if flag in props and shape(props[flag]).get('type') == 'boolean':
            args[flag] = False
    if 'page' in props and shape(props['page']).get('type') == 'integer':
        args['page'] = 1
    return args if set(required) <= set(args) else None


def search_profile(tool):
    props, required = properties(tool)
    limits = [name for name in ('limit', 'top_k') if name in props]
    if (len(limits) != 1 or required is None or shape(props.get('jql')).get('type') != 'string'
            or shape(props[limits[0]]).get('type') != 'integer' or field_value(props) is None):
        return None
    supported = {'jql', 'fields', limits[0]}
    if 'page' in props and shape(props['page']).get('type') == 'integer':
        supported.add('page')
    supported.update(flag for flag in ('expand_comments', 'expand_changelog', 'full_text')
                     if flag in props and shape(props[flag]).get('type') == 'boolean')
    if not set(required) <= supported:
        return None
    return {'limit': limits[0], 'project_required': limits[0] == 'top_k', 'fields': field_value(props)}


def search_arguments(tool, jql):
    profile = search_profile(tool)
    if profile is None:
        return None
    props, _ = properties(tool)
    args = {'jql': jql, 'fields': profile['fields'], profile['limit']: 8}
    if 'page' in props and shape(props['page']).get('type') == 'integer':
        args['page'] = 1
    for flag in ('expand_comments', 'expand_changelog', 'full_text'):
        if flag in props and shape(props[flag]).get('type') == 'boolean':
            args[flag] = False
    return args
