"""Render explicitly planned mechanism scenes beside their source paragraphs."""
import html
import json

SCENES = {'inference_regress', 'gene_pool', 'edna_capture', 'edna_decay', 'qpcr_probe', 'primer_specificity', 'spatial', 'hazard', 'augmentation', 'boundary', 'vessel', 'cholesterol', 'oxidative', 'molecular_sampling', 'pcr_slippage', 'replicate_consensus', 'argument_map', 'evidence_coding', 'repeated_measures', 'source_timeline', 'communication', 'text_focus'}

def validate_scene_data(m):
    d=m.get('visual',{});errors=[]
    if not isinstance(d,dict):return ['Scene visual must be an object']
    if m['scene']=='gene_pool':
        import math
        values=d.get('initial')
        if not isinstance(values,list) or len(values)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in values) or not math.isfinite(sum(values)) or sum(values)<=0:errors.append('Gene pool needs three finite nonnegative initial AA/Aa/aa weights with positive total')
    elif m['scene']=='edna_decay':
        import math
        def positive(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0
        if any(not positive(d.get(k)) for k in ['maximum','days','threshold']):errors.append('Decay needs positive finite maximum/days/threshold')
        curves=d.get('curves',[])
        if not isinstance(curves,list) or len(curves)!=2 or any(not isinstance(c,dict) or not c.get('label') or any(not positive(c.get(k)) for k in ['initial','rate']) for c in curves):errors.append('Decay needs two named positive model curves')
        if not errors and (d['threshold']>=d['maximum'] or any(c['initial']>d['maximum'] for c in curves)):errors.append('Decay plot maximum must cover curves and threshold')
    elif m['scene']=='source_timeline':
        layers=d.get('layers',[])
        if len(layers)!=3 or any(any(not isinstance(x.get(k),str) or not x[k].strip() for k in ['label','date','detail']) for x in layers):errors.append('Source timeline needs event/record/interpretation layers with explicit dates')
        if any(len(x.get('detail',''))>36 for x in layers):errors.append('Timeline detail too long')
    elif m['scene']=='communication':
        nodes=d.get('nodes',[]);names=[n.get('id') for n in nodes];steps=d.get('steps',[])
        if len(nodes)!=3 or len(set(names))!=3 or any(not n.get('label') or len(n['label'])>12 for n in nodes):errors.append('Communication scene needs three named participants')
        if len(steps)!=len(m.get('stages',[])):errors.append('Communication steps must match captions')
        for step in steps:
            if not isinstance(step.get('labels',{}),dict) or any(k not in names or not isinstance(v,str) or not v.strip() or len(v)>12 for k,v in step.get('labels',{}).items()):errors.append('Communication labels must name existing participants')
            if not step.get('message') or len(step['message'])>35 or not step.get('interpretation') or len(step['interpretation'])>35:errors.append('Communication step needs short message and interpretation')
            if any(x.get('from') not in names or x.get('to') not in names or x.get('mode') not in {'speaks','overhears','letter'} for x in step.get('channels',[])):errors.append('Communication needs valid named channels')
    elif m['scene']=='text_focus':
        if not d.get('quote') or len(d['quote'])>160 or not d.get('attribution'):errors.append('Text focus needs short exact quote and attribution')
        focuses=d.get('focuses',[])
        if len(focuses)!=len(m.get('stages',[])) or any(not f.get('text') or f['text'] not in d.get('quote','') or not f.get('meaning') or len(f['meaning'])>45 for f in focuses):errors.append('Text focus needs one exact focus and short meaning per stage')
    elif m['scene']=='repeated_measures':
        if any(not isinstance(d.get(k),str) or not d[k].strip() for k in ['before','interval','after','meaning']):errors.append('Repeated measures needs before/interval/after/meaning')
    else:
        nodes=d.get('nodes',[]);edges=d.get('edges',[]);names=[n.get('id') for n in nodes]
        if m['scene']=='evidence_coding':
            if len(nodes)!=3:errors.append('Coding scene needs exactly 3 nodes')
            elif [(x.get('from'),x.get('to'),x.get('relation')) for x in edges]!=[(names[0],names[1],'interprets'),(names[1],names[2],'interprets')]:errors.append('Coding edges must explicitly interpret material into focus and theme')
        if any(nodes[j].get('stage',0)>nodes[j+1].get('stage',0) for j in range(len(nodes)-1)):errors.append('Node stages must follow reading order')
        if len(nodes)<2 or len(nodes)>6 or len(names)!=len(set(names)) or any(not isinstance(x,str) or not x for x in names):errors.append('Diagram needs 2–6 unique named nodes')
        for n in nodes:
            if not n.get('label') or not isinstance(n.get('lines'),list) or not 1<=len(n['lines'])<=3 or any(not isinstance(x,str) or len(x)>20 for x in n.get('lines',[])):errors.append('Diagram needs readable label and 1–3 short text lines')
            if type(n.get('stage')) is not int or not 0<=n['stage']<len(m.get('stages',[])):errors.append('Node stage outside explanatory stages')
        for edge in edges:
            if edge.get('from') not in names or edge.get('to') not in names or edge.get('relation') not in {'supports','rebuts','defines','precedes','compares','causes','interprets'}:errors.append('Diagram needs valid endpoints and explicit relation')
    return errors

def render_mechanism(m):
    e = lambda value: html.escape(str(value), quote=True)
    config = e(json.dumps(m, ensure_ascii=False))
    refs = ' '.join(f'<a class="evidence" href="#{e(r)}">对应原文 {i+1}</a>' for i, r in enumerate(m['refs']))
    return (f'<figure class="mechanism" id="{e(m["id"])}" data-mechanism="{config}">'
            f'<div class="mechanism-head"><div><span class="motion-label">动起来，理解这一步</span><h3>{e(m["title"])}</h3><p>{e(m["question"])}</p></div><span class="motion-tag">{e(m.get("label", "机制示意"))}</span></div>'
            f'<div class="motion-stage"><canvas width="900" height="440" role="img" aria-label="{e(m["question"])}">{e("；".join(m["stages"]))}</canvas></div>'
            '<p class="motion-scroll-hint">宽图可左右滑动查看；也可拖动进度逐步读图。</p><div class="motion-controls"><button data-play aria-pressed="false">播放演示</button><button data-reset aria-label="重播到起点">重置</button><button data-prev>上一步</button><button data-next>下一步</button>'
            '<input data-scrub type="range" min="0" max="1000" value="0" aria-label="演示进度"><span data-step-label></span><select data-speed aria-label="演示速度"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></div>'
            f'<p class="motion-caption">{e(m["stages"][0])}</p><figcaption class="motion-evidence">{refs}<span>{e(m.get("note", ""))}</span></figcaption></figure>')
