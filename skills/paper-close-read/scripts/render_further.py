"""Render an authored, source-linked reading sequence."""
from html import escape
from urllib.parse import urlsplit

def validate_further(entries, ids):
    errors = []
    for entry in entries:
        for field in ('citation', 'role', 'priority', 'reason', 'focus'):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append('Further reading missing: ' + field)
        if not entry.get('refs') or any(ref not in ids for ref in entry['refs']):
            errors.append('Further reading needs valid source refs')
        url = urlsplit(entry.get('url', ''))
        if url.scheme != 'https' or not url.netloc:
            errors.append('Further reading needs verified HTTPS publication URL')
    return errors

def render_further(entries):
    if not entries:
        return ''
    cards = []
    for n, e in enumerate(entries, 1):
        refs = ' '.join(f'<a href="#{escape(r, quote=True)}">本文引用位置 {i+1}</a>' for i,r in enumerate(e['refs']))
        cards.append(f'<article class="further-card"><div class="further-head"><span class="further-num">{n}</span>'
                     f'<div><h3>{escape(e["citation"])}</h3><p class="further-role">{escape(e["role"])}</p></div>'
                     f'<span class="further-priority">{escape(e["priority"])}</span></div>'
                     f'<p class="further-reason">{escape(e["reason"])}</p>'
                     f'<p><strong>重点读什么：</strong>{escape(e["focus"])}</p>'
                     f'<div class="further-links"><a href="{escape(e["url"], quote=True)}" target="_blank" rel="noopener noreferrer">文献入口 ↗</a> {refs}</div></article>')
    return '<section class="fsect further-reading" id="f-further-reading"><h2>核心文献推荐 / Further reading</h2><p class="further-intro">按下面的顺序接着读；也可以直接选择你当前卡住的问题。推荐理由为本页带读建议。</p>' + ''.join(cards) + '</section>'
