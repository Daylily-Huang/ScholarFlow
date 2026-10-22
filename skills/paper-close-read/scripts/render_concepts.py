"""Optional conceptual distinctions used in humanities and social-science reading."""
from html import escape as e

def validate_concepts(concepts,ids):
    errors=[];seen=set()
    if not isinstance(concepts,list):return ['concepts must be an array']
    for c in concepts:
        if not isinstance(c,dict):errors.append('Concept must be an object');continue
        cid=c.get('id','')
        if not cid.startswith('concept-') or cid in seen:errors.append('Concept needs a unique concept- ID')
        seen.add(cid)
        if any(not isinstance(c.get(k),str) or not c[k].strip() for k in ['term','meaning','distinction','example']):errors.append('Concept needs term/meaning/distinction/example')
        if not c.get('refs') or any(x not in ids for x in c['refs']):errors.append('Concept needs valid source refs')
    return errors

def render_concepts(concepts,selected=None,prefix=''):
    if selected is not None:concepts=[c for c in concepts if c['id'] in selected]
    if not concepts:return ''
    cards=[]
    for c in concepts:
        refs=' '.join(f'<a class="evidence" href="#{e(x)}">原文依据 {i+1}</a>' for i,x in enumerate(c['refs']))
        cards.append(f'<article class="concept-card" id="{prefix}{e(c["id"])}"><h3>{e(c["term"])}</h3><p>{e(c["meaning"])}</p><p><strong>分清这一步：</strong>{e(c["distinction"])}</p><p><strong>用例子想：</strong>{e(c["example"])}</p>{refs}</article>')
    return '<div class="concept-cards">'+''.join(cards)+'</div>'
