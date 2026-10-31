"""Cross-domain content-plan checks. Stdlib only; never certifies scientific truth.

Sources are local UTF-8 extracts/data, optionally bound to an original PDF or
workbook. The Agent/human supplies and verifies the evidence classification.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as E
import zipfile

KINDS={'observation','background','inference','projection','derivation','question'}
RELATIONS={'descriptive','association','causal','not_different','equivalent'}
FACT_FIELDS=('value','unit','population','comparison','timeframe')
PART='docProps/scholarflow-content-review.json'
SCOPE='Declared evidence, file/quote identity, claim bindings, contexts, coverage and exposition dependencies; source interpretation and completeness still require Agent/human review.'
VISIBLE={'title','subtitle','lines','intro','center','items','sections','left','right','table','texts','composition','highlights','takeaway','question','measurement','groups','times','anchors','anchor_details'}
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(data):return hashlib.sha256(data).hexdigest()
def slides_digest(document):return sha(canonical(document.get('slides')))
def clean(value):return ' '.join(value.split())
def text(value):return isinstance(value,str) and bool(value.strip())


def field(page,path):
    if not text(path) or path.split('.')[0] not in VISIBLE:raise ValueError('Target must be visible slide content')
    if any(k in {'sources','source','notes','path','icon','provenance'} for k in path.split('.')):raise ValueError('Hidden/source fields cannot establish a visible claim')
    node=page
    for key in path.split('.'):
        if isinstance(node,list) and key.isdecimal():node=node[int(key)]
        elif isinstance(node,dict):node=node[key]
        else:raise ValueError('Target field does not exist')
    if not isinstance(node,str):raise ValueError('Target must point to a text field')
    return node


def number(value):
    if isinstance(value,bool):raise ValueError('Boolean is not a numeric value')
    try:
        result=Decimal(str(value).replace('\u2212','-'))
        if not result.is_finite():raise ValueError('Non-finite number')
        return result
    except InvalidOperation as exc:raise ValueError('Expected finite numeric value') from exc


def numeric_tokens(value):
    normalized=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',value)
    return {number(x) for x in re.findall(r'(?<![A-Za-z0-9_.])[+\-\u2212]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?',normalized)}


def _inspect(document,base_dir=None):
    issues=[]
    def issue(level,path,code,message):issues.append(dict(level=level,path=path,code=code,message=message))
    def error(path,code,message):issue('error',path,code,message)
    def warning(path,code,message):issue('warning',path,code,message)
    def indexed(value,path):
        if not isinstance(value,list):error(path,'list_required','Expected an array');return {}
        out={}
        for i,item in enumerate(value):
            if not isinstance(item,dict) or not text(item.get('id')):error(f'{path}[{i}]','id_required','Each record needs a non-empty id');continue
            if item['id'] in out:error(path,'duplicate_id','Duplicate id: '+item['id'])
            out[item['id']]=item
        return out
    def refs(value,index,path,allow_empty=False):
        if not isinstance(value,list) or (not value and not allow_empty) or any(not text(x) for x in value):
            error(path,'references_required','Expected valid reference ids');return []
        missing=[x for x in value if x not in index]
        for x in missing:error(path,'unknown_reference','Unknown id: '+x)
        return [index[x] for x in value if x in index]
    def result():return dict(ok=not any(x['level']=='error' for x in issues),issues=issues,scope=SCOPE,
                             file_verification='performed' if base_dir is not None else 'not_run',
                             counts=dict(sources=len(sources),evidence=len(evidence),claims=len(claims),topics=len(topics)))
    sources={};evidence={};claims={};topics={}
    if not isinstance(document,dict):error('$','object_required','Expected document object');return result()
    plan=document.get('content_plan')
    if not isinstance(plan,dict):error('content_plan','content_plan_required','Formal content needs a reviewed content_plan; use an explicit draft for incomplete work');return result()
    if type(plan.get('version')) is not int or plan['version']!=1:error('content_plan.version','unsupported_version','Expected version 1')
    pages=document.get('slides')
    if not isinstance(pages,list) or not pages or not all(isinstance(p,dict) for p in pages):error('slides','slides_required','Expected slide objects');return result()
    review=plan.get('review',{})
    if not isinstance(review,dict):review={}
    if review.get('status')!='verified' or review.get('scope')!='all_visible_substantive_content' or not text(review.get('reviewer')) or not text(review.get('note')):
        error('content_plan.review','review_required','Record an actual Agent/human source review of all substantive visible content, including conditions and omitted topics')
    if review.get('slides_sha256')!=slides_digest(document):error('content_plan.review.slides_sha256','stale_review','Slide input changed after the declared review')
    sources=indexed(plan.get('sources'),'content_plan.sources')
    evidence=indexed(plan.get('evidence'),'content_plan.evidence')
    claims=indexed(plan.get('claims'),'content_plan.claims')
    topics=indexed(plan.get('coverage'),'content_plan.coverage')
    if not topics:error('content_plan.coverage','coverage_required','Declare the relevant core topics and their slide claims; no fixed discipline or chapter count is prescribed')
    extracts={}
    def bound_file(record,path,decode=False):
        if not isinstance(record,dict) or not text(record.get('path')) or not re.fullmatch('[0-9a-f]{64}',str(record.get('sha256',''))):
            error(path,'source_binding_required','A local path and SHA256 are required');return None
        if base_dir is None:return None
        p=Path(record['path']);p=p if p.is_absolute() else Path(base_dir)/p
        try:
            data=p.read_bytes()
            if sha(data)!=record['sha256']:error(path,'source_hash_mismatch','Source bytes changed');return None
            return data.decode('utf-8-sig') if decode else data
        except (OSError,UnicodeError) as exc:error(path,'source_unavailable',str(exc));return None
    for key,s in sources.items():
        loc='content_plan.sources.'+key
        raw=bound_file(s,loc,True)
        if raw is not None:extracts[key]=clean(raw)
        if 'origin' in s:bound_file(s['origin'],loc+'.origin')
    for key,e in evidence.items():
        loc='content_plan.evidence.'+key
        if e.get('source_id') not in sources:error(loc+'.source_id','unknown_source','Evidence needs a declared source')
        if e.get('kind') not in KINDS-{'question'}:error(loc+'.kind','evidence_kind_required','Classify observed/background/inferred/projected/derived evidence')
        if e.get('relation','descriptive') not in RELATIONS:error(loc+'.relation','unknown_relation','Invalid relation type')
        if e.get('status') not in {'verified','unverified','not_reported'}:error(loc+'.status','evidence_status_required','Declare verification status; never invent missing information')
        for name in ('locator','context'):
            if not text(e.get(name)):error(loc+'.'+name,'evidence_context_required','Record source location and study/analysis context')
        if e.get('status')=='verified':
            if not text(e.get('quote')):error(loc+'.quote','quote_required','Verified evidence needs an exact source excerpt')
            elif e.get('source_id') in extracts and clean(e['quote']) not in extracts[e['source_id']]:error(loc+'.quote','quote_mismatch','Excerpt not found in the bound UTF-8 source')
        facts=e.get('facts')
        if facts is not None:
            if not isinstance(facts,dict) or any(k not in facts for k in FACT_FIELDS):error(loc+'.facts','fact_context_required','Numeric evidence needs value, unit, population, comparison and timeframe')
            else:
                try:
                    n=number(facts['value'])
                    if text(e.get('quote')) and n not in numeric_tokens(e['quote']):error(loc+'.facts.value','numeric_evidence_mismatch','The recorded number is absent from its source excerpt; record a supported derivation separately')
                except ValueError as exc:error(loc+'.facts.value','invalid_number',str(exc))
                for k in FACT_FIELDS[1:]:
                    if not text(facts[k]):error(loc+'.facts.'+k,'fact_context_required','Use an explicit not_reported when unavailable')
    first={};placed={i:[] for i in range(1,len(pages)+1)}
    for key,c in claims.items():
        loc='content_plan.claims.'+key
        kind=c.get('kind');relation=c.get('relation','descriptive')
        if kind not in KINDS:error(loc+'.kind','claim_kind_required','Unknown claim kind')
        if relation not in RELATIONS:error(loc+'.relation','unknown_relation','Invalid relation type')
        if not text(c.get('text')):error(loc+'.text','claim_text_required','Record the exact claim as displayed')
        support=refs(c.get('evidence_ids'),evidence,loc+'.evidence_ids',kind=='question')
        if kind!='question':
            if any(e.get('status')!='verified' for e in support):error(loc,'unverified_support','Missing/unverified evidence cannot support an assertion; present an explicit question or omit the assertion')
            allowed={'observation':{'observation'},'background':{'background','observation'},'derivation':{'background','observation','derivation'}}.get(kind)
            if allowed and any(e.get('kind') not in allowed for e in support):error(loc,'evidence_kind_mismatch','Inference/projection must not be presented as an observed result')
            if kind=='projection' and not any(e.get('kind')=='projection' for e in support):error(loc,'projection_support_required','Projection needs projected evidence')
            if relation in {'causal','equivalent'} and not any(e.get('relation')==relation for e in support):error(loc,'relation_overstatement','Association/non-significance cannot establish causality/equivalence')
            contexts={e.get('context') for e in support}
            if kind in {'observation','background','derivation'} and (not text(c.get('context')) or contexts!={c.get('context')}):error(loc+'.context','context_mismatch','Do not combine study populations, methods or time windows into one observed scope')
        if kind in {'inference','projection'} and (not text(c.get('qualifier')) or not text(c.get('text')) or c['qualifier'] not in c['text']):
            error(loc+'.qualifier','visible_qualifier_required','The visible claim must carry its own appropriate uncertainty/attribution wording')
        if kind=='question' and text(c.get('text')) and not any(x in c['text'] for x in ('?','\uff1f')) and (not text(c.get('qualifier')) or c['qualifier'] not in c['text']):
            error(loc+'.qualifier','visible_question_required','Do not relabel an assertion as a question without visible question/unknown wording')
        facts=c.get('facts',[])
        if not isinstance(facts,list):error(loc+'.facts','list_required','Expected numeric fact references');facts=[]
        for j,f in enumerate(facts):
            floc=loc+f'.facts[{j}]'
            if not isinstance(f,dict) or f.get('evidence_id') not in c.get('evidence_ids',[]):error(floc,'numeric_support_required','Fact must reference the claim support');continue
            original=evidence.get(f['evidence_id'],{}).get('facts',{})
            if not isinstance(original,dict) or any(k not in original or k not in f for k in FACT_FIELDS):error(floc,'fact_context_required','A numeric fact needs the full original comparison tuple');continue
            try:equal=number(f['value'])==number(original['value'])
            except ValueError:equal=False
            if not equal or any(f[k]!=original[k] for k in FACT_FIELDS[1:]):error(floc,'numeric_context_mismatch','Value/unit/population/comparison/timeframe differs; a supported derivation must be recorded separately')
            elif text(c.get('text')) and number(f['value']) not in numeric_tokens(c['text']):error(floc,'numeric_display_mismatch','The declared fact is absent from the displayed claim')
        targets=c.get('targets')
        if not isinstance(targets,list) or not targets:error(loc+'.targets','targets_required','Bind each key claim to actual slide text');targets=[]
        for j,t in enumerate(targets):
            tloc=loc+f'.targets[{j}]'
            if not isinstance(t,dict) or type(t.get('slide')) is not int or not 1<=t['slide']<=len(pages):error(tloc,'invalid_slide','Slide numbers are 1-based');continue
            i=t['slide'];placed[i].append(key);first[key]=min(first.get(key,i),i)
            try:
                if field(pages[i-1],t.get('field'))!=c.get('text'):error(tloc,'claim_text_mismatch','Claim text differs from the visible input field')
            except (ValueError,KeyError,IndexError,TypeError):error(tloc,'invalid_target','Target must be an existing visible text field')
        refs(c.get('depends_on',[]),claims,loc+'.depends_on',True)
    page_plan=plan.get('pages');seen=set()
    if not isinstance(page_plan,list):error('content_plan.pages','page_plan_required','Plan the purpose and claims of every slide');page_plan=[]
    for j,p in enumerate(page_plan):
        loc=f'content_plan.pages[{j}]'
        if not isinstance(p,dict) or type(p.get('slide')) is not int or p['slide'] not in placed:error(loc,'invalid_slide','Expected each slide exactly once');continue
        i=p['slide']
        if i in seen:error(loc,'duplicate_page_plan','Duplicate planned slide')
        seen.add(i);role=p.get('role')
        if role not in {'cover','navigation','content','discussion'} or not text(p.get('message')):error(loc,'page_purpose_required','Declare slide role and core message')
        if (role=='cover' and pages[i-1].get('layout')!='L5') or (role=='navigation' and pages[i-1].get('layout') not in {'L6','L7'}):error(loc,'invalid_page_role','Do not relabel evidence pages as cover/navigation to skip claim checks')
        if role in {'content','discussion'} or pages[i-1].get('highlights'):
            if not placed[i]:error(loc,'uncovered_content_page','Content/discussion/highlight pages need an evidence-bound key claim')
    if seen!=set(placed):error('content_plan.pages','incomplete_page_plan','Every slide needs a declared purpose')
    for key,t in topics.items():
        loc='content_plan.coverage.'+key
        if not text(t.get('topic')) or type(t.get('required')) is not bool:error(loc,'topic_required','Declare relevant topic and required boolean')
        refs(t.get('claim_ids'),claims,loc+'.claim_ids',True)
        if not t.get('claim_ids') and (t.get('required') is True or not text(t.get('omission_reason'))):error(loc,'uncovered_topic','Required topics need slide claims; optional omissions need a reason')
    visiting=set();visited=set()
    def visit(key):
        if key in visited:return
        if key in visiting:error('content_plan.claims.'+key,'dependency_cycle','Exposition dependencies form a cycle');return
        visiting.add(key);c=claims[key]
        deps=c.get('depends_on',[])
        for dep in deps if isinstance(deps,list) else []:
            if dep not in claims:continue
            visit(dep)
            if key in first and dep in first and first[dep]>first[key]:
                if not text(c.get('forward_reference_reason')):error('content_plan.claims.'+key,'unexplained_forward_reference','Explain/introduce prerequisite content first, or record the reason for a deliberate preview')
                else:warning('content_plan.claims.'+key,'intentional_forward_reference','Check the declared preview against audience needs')
        visiting.remove(key);visited.add(key)
    for key in claims:visit(key)
    if not claims:error('content_plan.claims','claims_required','Formal content needs key claims, derivations or explicit discussion questions')
    return result()


def inspect(document,base_dir=None):
    try:return _inspect(document,base_dir)
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError) as exc:
        return dict(ok=False,issues=[dict(level='error',path='content_plan',code='invalid_content_plan',message=str(exc))],scope=SCOPE,file_verification='not_completed')


def fingerprint(parts):
    out={}
    for name,data in sorted(parts.items()):
        if re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
            node=E.fromstring(data)
            out[name]=sha(canonical([clean(''.join(t.text or '' for t in p.iter(A+'t'))) for p in node.iter(A+'p')]))
        elif name.startswith(('ppt/charts/','ppt/embeddings/','ppt/media/')) and not name.endswith('.rels'):out[name]=sha(data)
    return out


def attach(parts,document,report,draft=False):
    receipt=dict(version=1,status='draft' if draft else 'reviewed',slides_sha256=slides_digest(document),
                 counts=report.get('counts',{}),scope=SCOPE,review='Agent/human attestation; not independently established by this script',
                 content_fingerprint=fingerprint(parts))
    parts[PART]=canonical(receipt)
    ns='http://schemas.openxmlformats.org/package/2006/relationships'
    rel=E.fromstring(parts['_rels/.rels']);used={n.get('Id') for n in rel};rid='contentReview'
    while rid in used:rid+='x'
    E.SubElement(rel,'{'+ns+'}Relationship',Id=rid,Type='urn:scholarflow:content-review',Target=PART)
    parts['_rels/.rels']=E.tostring(rel,encoding='utf-8',xml_declaration=True)
    ct='http://schemas.openxmlformats.org/package/2006/content-types';types=E.fromstring(parts['[Content_Types].xml'])
    E.SubElement(types,'{'+ct+'}Override',PartName='/'+PART,ContentType='application/json')
    parts['[Content_Types].xml']=E.tostring(types,encoding='utf-8',xml_declaration=True)


def check_pptx(path):
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    if PART not in parts:raise ValueError('No content review binding; supply reviewed content input or explicitly prepare a draft')
    receipt=json.loads(parts[PART])
    if not isinstance(receipt,dict) or receipt.get('version')!=1 or receipt.get('status')!='reviewed':raise ValueError('Content is a draft or lacks a valid formal review record')
    if receipt.get('content_fingerprint')!=fingerprint(parts):raise ValueError('Content changed after review; review the actual edited deck again')
    return {k:receipt[k] for k in ('version','status','slides_sha256','counts','scope','review')}


def check_edited(document,base_dir,pptx):
    report=inspect(document,base_dir)
    if not report['ok']:raise ValueError('Content input failed: '+json.dumps(report['issues'],ensure_ascii=False))
    payload=Path(pptx).read_bytes()
    if document['content_plan']['review'].get('pptx_sha256')!=sha(payload):raise ValueError('Review the actual edited PPTX and bind its exact SHA256 in content_plan.review.pptx_sha256')
    with zipfile.ZipFile(pptx) as z:
        # Resolve actual page order, rather than trusting slide filenames.
        p='{http://schemas.openxmlformats.org/presentationml/2006/main}'
        r='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
        rel={x.get('Id'):x.get('Target') for x in E.fromstring(z.read('ppt/_rels/presentation.xml.rels'))}
        import posixpath
        pages=[]
        for item in E.fromstring(z.read('ppt/presentation.xml')).find(p+'sldIdLst'):
            target=rel[item.get(r+'id')];name=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('ppt',target))
            pages.append(clean(''.join(n.text or '' for n in E.fromstring(z.read(name)).iter(A+'t'))))
        if len(pages)!=len(document['slides']):raise ValueError('Edited deck slide count differs from reviewed input')
        for claim in document['content_plan']['claims']:
            for target in claim['targets']:
                if clean(claim['text']).replace(' ','') not in pages[target['slide']-1].replace(' ',''):raise ValueError('Reviewed claim missing from actual edited slide: '+claim['id'])
    return dict(version=1,status='reviewed',slides_sha256=slides_digest(document),counts=report['counts'],scope=SCOPE,
                review='Agent/human attestation bound to exact edited PPTX; not scientific certification')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--pptx',type=Path);a=p.parse_args()
    try:
        doc=json.loads(a.input.read_text(encoding='utf-8-sig'));result=inspect(doc,a.input.resolve().parent)
        if a.pptx and result['ok']:result['output_review']=check_edited(doc,a.input.resolve().parent,a.pptx)
    except (OSError,ValueError,KeyError,TypeError,E.ParseError,zipfile.BadZipFile) as exc:result=dict(ok=False,issues=[dict(level='error',path='$',code='read_or_output_error',message=str(exc))],scope=SCOPE)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 2


if __name__=='__main__':raise SystemExit(main())
