"""Render a short overview and a separate explanatory walkthrough."""
from html import escape as e

RESEARCH_STEPS = (
    ('background', '背景', '为什么关注这件事'),
    ('gap', '已有缺口', '以前还没讲清什么'),
    ('question', '核心问题', '这篇到底想弄清什么'),
    ('method', '怎么做', '用了什么材料和方法'),
    ('findings', '主要结果', '实际发现了什么'),
    ('conclusion', '结论与意义', '这些发现说明什么'),
)

def annotatable(text, identity, tag='p', css=''):
    return f'<{tag} id="{identity}" data-ann-id="{identity}"'+(f' class="{css}"' if css else '')+'>'+e(text)+f'</{tag}>'

def render_research_map(q):
    cards=[];sources=[]
    for n, (item, (_,label,prompt)) in enumerate(zip(q['research_map'], RESEARCH_STEPS),1):
        title=item.get('title') or label
        text=annotatable(item['text'],'guide-overview-'+item['step'])
        cards.append(f'<article class="research-step step-{e(item["step"])}"><div class="research-step-head"><span class="research-num">{n:02d}</span><div><h3>{e(title)}</h3><span class="research-prompt">{e(prompt)}</span></div></div>{text}</article>')
        sources.append(f'<a class="evidence" href="#{e(item["refs"][0])}" title="对照{e(label)}的原文">{e(label)} ↗</a>')
    rail='<div class="research-route" aria-label="整篇研究路线">'+''.join(f'<span>{e(label)}</span>' for _,label,_ in RESEARCH_STEPS)+'</div>'
    return '<section id="story-overview" class="story-overview research-overview"><span class="eyebrow">3分钟入门 · 这篇论文到底做了什么</span><h2>'+e(q['title'])+'</h2>'+annotatable(q['lead'],'guide-overview-lead',css='story-lead')+rail+'<div class="research-map">'+''.join(cards)+'</div><div class="story-takeaway"><strong>把整篇串起来：</strong>'+annotatable(q['takeaway'],'guide-overview-takeaway','span')+'</div><div class="research-sources"><span>对照原文</span>'+''.join(sources)+'</div></section>'

def links(refs):
    return '<div class="story-refs">'+ ' '.join(f'<a href="#{e(r)}">原文依据 {i+1}</a>' for i,r in enumerate(refs))+'</div>'

def render_story(story, mechanisms=None, concepts=None, extra_deep='', data=None, asset_root='.'):
    from render_concepts import render_concepts
    from render_mechanisms import render_mechanism
    library = {m['id']:m for m in mechanisms or []}
    q=story['overview']
    paras=lambda xs,prefix: ''.join(annotatable(x,prefix+'-'+str(i)) for i,x in enumerate(xs))
    if q.get('format')=='research-map':
        quick=render_research_map(q)
    else:
        chain='<ol class="story-chain">'+''.join('<li>'+e(x)+'</li>' for x in q['chain'])+'</ol>'
        metrics='<div class="story-metrics">'+''.join(f'<article><span>{e(m["label"])}</span><strong>{e(m["value"])}</strong><p>{e(m["meaning"])}</p></article>' for m in q.get('metrics',[]))+'</div>'
        quick=f'<section id="story-overview" class="story-overview"><span class="eyebrow">3分钟入门 · 先把整篇串起来</span><h2>{e(q["title"])}</h2>'+annotatable(q['lead'],'guide-overview-lead',css='story-lead')+paras(q['paragraphs'],'guide-overview-p')+chain+metrics+'<div class="story-takeaway">'+annotatable(q['takeaway'],'guide-overview-takeaway','span')+'</div>'+links(q['refs'])+'</section>'
    chapters=[]
    source_items = {i['id']:i for section in (data or {}).get('sections', []) for i in section['items']}
    for n,s in enumerate(story['walkthrough'],1):
        from render_figures import walkthrough_figure
        prose=[]
        for p,paragraph in enumerate(s['paragraphs']):
            prose.append(annotatable(paragraph,f'guide-chapter-{n}-p-{p}'))
            for f,reference in enumerate(s.get('figures', [])):
                if reference['after']==p:
                    prose.append(walkthrough_figure(reference,source_items,asset_root,f'guide-figure-{n}-{f}',data))
        players=[]
        for reference in s.get('motions',[]):
            original=library[reference['id']]
            instance={**original, 'id':f'guide-motion-{n}-{original["id"]}'}
            players.append(render_mechanism(instance))
        motion=''.join(players)
        concept_html=render_concepts(concepts or [], s.get('concepts', []), f'guide-concept-{n}-')
        table=''
        if s.get('table'):
            t=s['table'];table='<div class="story-table"><table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in t['head'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(c)+'</td>' for c in row)+'</tr>' for row in t['rows'])+'</tbody></table></div>'
        chapters.append(f'<section id="story-step-{n}" class="story-chapter"><span class="eyebrow">{n:02d} · {e(s["bridge"])}</span><h2>{e(s["title"])}</h2>'+''.join(prose)+table+concept_html+motion+annotatable(s['connection'],f'guide-chapter-{n}-connection',css='story-next')+links(s['refs'])+'</section>')
    return '<div class="story-reader">'+quick+'<div class="guide-deep" data-deep><p class="story-route-label">10分钟读懂 · 沿着问题往下推</p>'+''.join(chapters)+extra_deep+'</div></div>'
