"""On-demand Jira links from saved attachments and bounded pane output."""
import re
from urllib.parse import urlsplit, urlunsplit


def ticket_url(value):
    try:
        value = str(value).strip()
        url = urlsplit(value)
        if (url.scheme not in {'http', 'https'} or not url.hostname
                or url.username or url.password or any(ord(c) < 32 for c in value)):
            return None
        match = re.fullmatch(r'(.*/browse/)([A-Z][A-Z0-9_]*-[1-9][0-9]*)/?', url.path)
        if not match:
            return None
        prefix, key = match.groups()
        return {'url': urlunsplit((url.scheme, url.netloc.lower(), prefix + key, '', '')),
                'key': key, 'title': key}
    except ValueError:
        return None


def collect(run, text=''):
    items = {}
    for record in run.get('linked_folders') or []:
        item = ticket_url(record.get('path', ''))
        if item:
            item.update(source='linked', title=str(record.get('label') or item['key'])[:500])
            items[item['url']] = item
        if len(items) >= 100:
            break
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text[-262144:])
    for raw in re.findall(r'https?://[^\s<>"\x00-\x20]+', clean):
        if len(items) >= 100:
            break
        item = ticket_url(raw.rstrip('.,;:!?)\u3002\uff0c\uff09]}`\''))
        if item and item['url'] not in items:
            item['source'] = 'output'
            items[item['url']] = item
    return {'items': list(items.values())}
