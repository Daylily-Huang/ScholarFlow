"""Keep source headings and authored reading landmarks separate."""
from html import escape


def landmark_id(start):
    return 'f-read-' + start


def outline_errors(data, records, guide):
    outline = guide.get('reading_outline', [])
    if not isinstance(outline, list):
        return ['guide.reading_outline must be an array']
    positions = {item['id']: (sn, bn, item) for sn, section in enumerate(data['sections'])
                 for bn, item in enumerate(section['items'])}
    roles = {r['id']: r.get('role', 'body') for r in records}
    errors, seen, last = [], set(), (-1, -1)
    for entry in outline:
        if (not isinstance(entry, dict) or not isinstance(entry.get('start'), str)
            or not isinstance(entry.get('title'), str) or not entry['title'].strip()):
            errors.append('Reading landmark needs start and nonempty title'); continue
        start = entry['start']
        if start not in positions:
            errors.append('Reading landmark start is not a source block: ' + start); continue
        sn, bn, item = positions[start]
        if start in seen: errors.append('Duplicate reading landmark start: ' + start)
        if (sn, bn) <= last: errors.append('Reading landmarks must follow source order')
        seen.add(start); last = (sn, bn)
        if landmark_id(start) in positions: errors.append('Reading landmark id collides with source block')
        if data['sections'][sn].get('kind', 'body') != 'body' or (item['t'] == 'p' and roles.get(start) != 'body'):
            errors.append('Reading landmark must start at substantive body content: ' + start)
    return errors


def heading(entry):
    return ('<div class="reading-landmark" id="' + escape(landmark_id(entry['start']), quote=True)
            + '"><span>阅读分段 · 整理者添加</span><h3>' + escape(entry['title']) + '</h3></div>')


def navigation(data, records, guide):
    roles = {r['id']: r.get('role', 'body') for r in records}
    primary, auxiliary = [], []
    for sn, section in enumerate(data['sections']):
        if not section['items']: continue
        substantive = any(i['t'] != 'p' or roles.get(i['id'], 'body') == 'body' for i in section['items'])
        target = primary if section.get('kind', 'body') == 'body' and substantive else auxiliary
        target.append((sn, section))
    groups = {}
    owners = {item['id']: sn for sn, section in enumerate(data['sections']) for item in section['items']}
    for entry in guide.get('reading_outline', []):
        groups.setdefault(owners[entry['start']], []).append(entry)
    def link(target, label, number, depth=0, extra=''):
        return (f'<a href="#{escape(target, quote=True)}" class="toc-link {extra}" data-toc-depth="{depth}" '
                f'style="--toc-depth:{depth}"><span class="nav-num">{number}</span><span>{escape(label)}</span></a>')
    parts = ['<p class="toc-group-label">正文阅读</p>'] if primary else []
    # Source levels form a hierarchy without inventing omitted source headings.
    stack, counters = [], []
    for sn, section in primary:
        level = section.get('level', 1)
        while stack and stack[-1] >= level:
            stack.pop()
        depth = len(stack)
        if len(counters) <= depth: counters.append(0)
        counters = counters[:depth+1]; counters[depth] += 1
        number = '.'.join(f'{n:02d}' for n in counters)
        parts.append(link(f'f-{sn:02d}', section.get('display_name', section['name']), number, depth))
        for n, entry in enumerate(groups.get(sn, []), 1):
            parts.append(link(landmark_id(entry['start']), entry['title'], number + '.' + str(n), depth+1, 'toc-reading'))
        stack.append(level)
    if guide.get('further_reading'):
        parts.append(link('f-further-reading', '核心文献推荐', '读'))
    if auxiliary:
        parts.append('<p class="toc-group-label">出版信息与附录</p>')
        for n, (sn, section) in enumerate(auxiliary, 1):
            label = section.get('display_name', section['name'])
            if section['name'] == data['front']['title']: label = '题名与作者'
            parts.append(link(f'f-{sn:02d}', label, '附' + str(n), 0, 'toc-auxiliary'))
    return ''.join(parts)
