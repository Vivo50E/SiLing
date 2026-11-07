"""On-demand Jira links from saved attachments and bounded pane output."""
import re
from urllib.parse import urlsplit, urlunsplit


def task_terms(run):
    """Bounded words from the pane's user-visible task name, never its transcript."""
    stop = set('the and for with from this that fix update implement add task session interactive terminal codex claude cursor agent resume new test'.split())
    for field in ('display_name', 'label', 'task'):
        title = str(run.get(field) or '')[:300]
        if re.search(r'(?i)https?://|bearer\s|password|secret|token|api.?key|xox[baprs]-|sk-', title):
            return []
        title = re.sub(r'\b[A-Z][A-Z0-9_]*-[1-9][0-9]*\b', '', title)
        words = re.findall(r'[A-Za-z][A-Za-z0-9]{2,}|[\u3400-\u9fff]{2,12}', title)
        terms = list(dict.fromkeys(word.lower() for word in words if len(word) <= 24 and word.lower() not in stop))[:5]
        if len(terms) >= 2 or (len(terms) == 1 and re.fullmatch(r'[\u3400-\u9fff]{4,12}', terms[0])):
            return terms
    return []


def matches_task(title, terms):
    words = set(re.findall(r'[a-z][a-z0-9]*', title.lower()))
    return bool(terms) and all(term in words if term.isascii() else term in title for term in terms)


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
