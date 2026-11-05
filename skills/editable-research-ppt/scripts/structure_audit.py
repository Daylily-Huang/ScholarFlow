#!/usr/bin/env python3
"""Bind each declared content task and visual structure to the saved deck.

Declarations are checked twice: against layout capacity while authoring, and
against the written PPTX geometry afterwards. A slide planned as one structure
and drawn as another cannot pass by plan alone, and any later edit invalidates
the sealed receipt because it carries the package fingerprint.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PART='docProps/scholarflow-structure-review.json'
VERSION=2
NAVIGATION=('cover','agenda','section','closing')
STRUCTURES=('cover','agenda','section','image_led','comparison','process','cards','data','chart','statement','closing')
# Layouts whose meaning is fixed by the template rather than by the author.
FIXED={'L5':'cover','L6':'agenda','L7':'section','L14':'closing'}
COMPACT={('L21','sidebar'):'chart',('L21','journal'):'chart',('L22','fraction'):'data',
         ('L22','metrics'):'data',('L22','pipeline'):'data',('L23','lanes'):'process'}
COMPACT_DEFAULTS={'L21':'sidebar','L22':'fraction','L23':'lanes'}
ORIGINAL_FIGURE={'L2','L3','L4','L8','L9','L10','L11'}
ALLOWED={'L1':{'cards','comparison','process','statement'},'L2':{'comparison','process','cards'},
         'L3':{'chart','data'},'L4':{'data','comparison'},'L8':{'process','comparison','cards'},
         'L9':{'comparison','cards'},'L10':{'process','cards'},'L11':{'chart','data'},
         'L12':{'cards','comparison'},'L13':{'comparison','process','cards'},
         'L15':{'image_led','comparison','cards'},'L16':{'image_led','comparison','cards','process'},
         'L17':{'image_led','comparison'},'L18':{'image_led','comparison','cards'},
         'L19':{'process'},'L20':{'data'},'L21':{'chart'},'L22':{'data','chart'},'L23':{'process'}}
SCOPE=('Declared task/structure wording, layout capacity, three-in-a-row rhythm, and measured '
       'picture/table/chart/text geometry of the saved file. Does not judge whether the chosen '
       'structure serves the message, scientific correctness, or visual quality of renderings.')


def module(name):
    spec=importlib.util.spec_from_file_location('structure_'+name,ROOT/'scripts'/(name+'.py'))
    found=importlib.util.module_from_spec(spec);spec.loader.exec_module(found);return found


def text(value):return isinstance(value,str) and bool(value.strip())


def readzip(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('PPTX contains duplicate package part names')
        return {name:archive.read(name) for name in names}


def fingerprint(parts):
    return module('content_audit').fingerprint(parts)


def declared_structure(page):
    """Structure implied by the layout itself, used to sanity-check an author's declaration."""
    layout=page.get('layout');variant=page.get('variant','default')
    if layout in FIXED:return FIXED[layout]
    return COMPACT.get((layout,COMPACT_DEFAULTS.get(layout) if variant=='default' else variant))


def failures(declared,m):
    """Why the measured geometry cannot be the declared structure; empty when it can."""
    reasons=[]
    share=m['image_share'];big=m['largest_picture_share'];pictures=len(m['pictures'])
    if declared=='image_led' and big<0.25:
        reasons.append('declared image_led but the largest picture covers %.1f%% of the page (<25%%)'%(big*100))
    if declared=='comparison' and not ((pictures>=2 and share>=0.10) or (m['text_columns']>=2 and m['text_rows']>=2)):
        reasons.append('declared comparison but no two parallel groups were drawn (pictures=%d share=%.1f%% columns=%d rows=%d)'%(pictures,share*100,m['text_columns'],m['text_rows']))
    if declared=='data' and m['tables']<1 and m['charts']<1 and not m['matrix_grid']:
        reasons.append('declared data but the page has no table, chart or aligned matrix cells')
    if declared=='chart' and m['charts']<1:
        reasons.append('declared chart but the page has no native chart')
    if declared=='cards' and (m['structure']!='cards' and (m['panels']<3 or m['structure'] in {'image_led','data'})):
        reasons.append('declared cards but the measured page is %s with %d text blocks'%(m['structure'],m['text_boxes']))
    if declared=='process' and not m['process_geometry']:
        reasons.append('declared process but the page has no measured links or timeline lanes')
    if declared=='statement' and m['structure']!='statement':
        reasons.append('declared statement but the measured page is '+m['structure'])
    return reasons


def rhythm(structures,explained=()):
    """Three or more consecutive slides with the same structure, unless a reason is declared."""
    runs=[];i=0
    while i<len(structures):
        j=i
        while j+1<len(structures) and structures[j+1]==structures[i]:j+=1
        length=j-i+1
        if length>=3 and structures[i] not in NAVIGATION:
            reasons=[explained[k] for k in range(i,j+1) if k in explained]
            run={'start':i+1,'end':j+1,'structure':structures[i],'length':length,
                 'reason':reasons[0] if reasons else None}
            runs.append(run)
        i=j+1
    return runs


def measure(parts):
    """Per-slide measured geometry and inferred structure, in presentation order."""
    deck=module('deck_inspect')
    metrics=deck.structure_from_parts(parts)
    return [dict(m,structure=deck.infer_actual(m)) for m in metrics]


def inspect(document,parts=None):
    """Authoring-side report: honest declarations, layout capacity, rhythm, and plan/actual match."""
    issues=[]
    def issue(level,path,code,message):issues.append(dict(level=level,path=path,code=code,message=message))
    pages=document.get('slides') if isinstance(document,dict) else None
    if not isinstance(pages,list) or not pages:
        return {'ok':False,'issues':[dict(level='error',path='slides',code='invalid_pages',message='Expected slides')],
                'status':'undeclared','structures':[],'runs':[],'scope':SCOPE}
    marks={i for i,p in enumerate(pages) if isinstance(p,dict) and ('structure' in p or 'task' in p)}
    formal=document.get('demo') is not True or 'content_plan' in document
    advisory=document.get('structure_check')=='advisory'
    if formal and advisory:
        issue('error','structure_check','advisory_formal','正式稿不能使用仅供合成示例的 advisory 模式。')
    if not marks:
        issue('error' if formal else 'warning','slides','structure_undeclared',
              '每页需要 task 与 structure；未声明的文件只可作为待审稿或合成样板。')
    elif len(marks)!=len(pages):
        missing=', '.join(str(i+1) for i in range(len(pages)) if i not in marks)
        issue('error','slides','structure_partial','未声明内容任务或视觉结构的页：'+missing)
    explained={}
    named=[]
    for i,page in enumerate(pages):
        label=page.get('structure') if isinstance(page,dict) else None
        named.append(label if text(label) and label in STRUCTURES else 'undeclared')
        if not isinstance(page,dict):
            issue('error',f'slides[{i}]','invalid_page','每页须为对象。')
            continue
        if i not in marks:continue
        if named[-1]=='undeclared':
            issue('error',f'slides[{i}].structure','invalid_structure','结构类型应为：'+', '.join(STRUCTURES))
        if not text(page.get('task')):
            issue('error',f'slides[{i}].task','task_required','每页需要一句话说明内容任务。')
        if 'rhythm_exception' in page:
            if text(page['rhythm_exception']):
                explained[i]=page['rhythm_exception'].strip()
            else:
                issue('error',f'slides[{i}].rhythm_exception','invalid_exception','请写明连排原因，或删除空字段。')
        layout=page.get('layout')
        variant=page.get('variant','default')
        if not isinstance(layout,str) or layout not in FIXED.keys()|ALLOWED.keys() or not isinstance(variant,str):
            issue('error',f'slides[{i}].layout','invalid_layout','需要有效的版式与变体。')
            continue
        fixed=declared_structure(page)
        allowed=ALLOWED.get(layout,set())
        if variant=='original_figure' and layout in ORIGINAL_FIGURE:
            allowed={'image_led','comparison'}
        if fixed and label!=fixed:
            issue('error',f'slides[{i}].structure','structure_layout_mismatch',f'{layout} / {variant} 只能声明 {fixed}。')
        elif not fixed and named[-1] not in allowed:
            issue('error',f'slides[{i}].structure','structure_capacity_mismatch',
                  f'{layout} 能画出的结构是：'+', '.join(sorted(allowed)))
    actual=measure(parts) if parts is not None else []
    series={'planned':named}
    if parts is not None and len(actual)!=len(pages):
        issue('error','slides','slide_count_mismatch','成品页数与声明页数不一致。')
    elif parts is not None and len(marks)==len(pages):
        series['measured']=[]
        for i,(page,label,m) in enumerate(zip(pages,named,actual)):
            at_expected_position=(label!='cover' or i==0) and (label!='closing' or i==len(pages)-1)
            is_navigation=(at_expected_position and label in NAVIGATION and isinstance(page,dict) and
                           m['navigation_layout']==page.get('layout') and FIXED.get(m['navigation_layout'])==label)
            series['measured'].append(label if is_navigation else m['structure'])
            reasons=failures(label,m)
            if label in NAVIGATION and not is_navigation:
                reasons.append('the saved page does not match the approved navigation geometry or position')
            for reason in reasons:
                issue('warning' if advisory and not formal else 'error',f'slides[{i}].structure',
                      'plan_actual_mismatch',f'第 {i+1} 页：{reason}')
    runs={}
    if len(marks)==len(pages):
        for origin,labels in series.items():
            for run in rhythm(labels,explained):
                key=(run['start'],run['end'],run['structure'])
                if key in runs:
                    runs[key]['checks'].append(origin)
                else:
                    runs[key]=dict(run,checks=[origin])
    for run in runs.values():
        prefix=f'第 {run["start"]} 到 {run["end"]} 页连续使用 {run["structure"]}（{"/".join(run["checks"])}）'
        where=f'slides[{run["start"]-1}]'
        if run['reason']:
            issue('warning',where,'explained_rhythm',prefix+'；正式交付需复核此连排理由。')
        else:
            issue('warning' if advisory and not formal else 'error',where,'repetitive_structure',
                  prefix+'；请调整布局，或写明具体连排理由并交复核。')
    ok=not any(item['level']=='error' for item in issues)
    if not ok:
        status='rejected'
    elif not marks:
        status='undeclared'
    elif advisory:
        status='demo'
    elif runs:
        status='review_required'
    else:
        status='confirmed'
    return {'ok':ok,'issues':issues,'status':status,'declared':named,'structures':named,
            'runs':list(runs.values()),'actual':actual,'scope':SCOPE}


def plan(document):
    """The declaration side of the receipt: task, layout, variant and structure per slide."""
    pages=(document.get('slides') or []) if isinstance(document,dict) else []
    return [dict(slide=i+1,**{key:p[key] for key in ('layout','task','structure','rhythm_exception') if key in p},
                 variant=p.get('variant','default'))
            for i,p in enumerate(pages) if isinstance(p,dict)]


def describe(report,parts=None,document=None):
    """Expose the declaration, measured geometry and any pending exception."""
    actual=report.get('actual')
    if actual is None:
        actual=measure(parts) if parts is not None else []
    metrics=('slide','structure','image_share','largest_picture_share','tables','charts',
             'text_boxes','text_rows','text_columns','matrix_grid','process_geometry','navigation_layout')
    return {'version':VERSION,'status':report['status'],'plan':plan(document) if document is not None else [],
            'actual':[{key:m[key] for key in metrics} for m in actual],
            'issues':report['issues'],'runs':report['runs'],
            'exceptions':[r['reason'] for r in report['runs'] if r.get('reason')],'scope':SCOPE}


def attach(parts,document,report=None,draft=False):
    """Seal the report into the package; refuses to publish a lie about the file it just wrote."""
    report=report if report is not None else inspect(document)
    receipt=describe(report,parts,document)
    receipt['pptx_fingerprint']=fingerprint(parts)
    if draft:
        receipt['status']='draft'
    if not draft and receipt['status']=='rejected':
        raise ValueError('Structure check failed; fix the declarations or use --draft: '+
                         json.dumps(report.get('issues',[]),ensure_ascii=False))
    parts[PART]=json.dumps(receipt,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    rel='_rels/.rels';ns='http://schemas.openxmlformats.org/package/2006/relationships'
    root=E.fromstring(parts[rel]);used={n.get('Id') for n in root};rid='structureReview'
    while rid in used:rid+='x'
    E.SubElement(root,'{'+ns+'}Relationship',Id=rid,Type='urn:scholarflow:structure-review',Target=PART)
    parts[rel]=E.tostring(root,encoding='utf-8',xml_declaration=True)
    types=E.fromstring(parts['[Content_Types].xml']);ct='http://schemas.openxmlformats.org/package/2006/content-types'
    E.SubElement(types,'{'+ct+'}Override',PartName='/'+PART,ContentType='application/json')
    parts['[Content_Types].xml']=E.tostring(types,encoding='utf-8',xml_declaration=True)
    return receipt['status']


def has_receipt(path):
    """Whether the package already carries a structure report (used to order delivery checks)."""
    try:
        with zipfile.ZipFile(path) as z:return PART in z.namelist()
    except (OSError,zipfile.BadZipFile):
        return False


def pending(path):
    """Measure the current draft even if it has no receipt or its old report is stale."""
    parts=readzip(path)
    try:
        receipt=json.loads(parts.get(PART,b'{}'))
    except ValueError:
        receipt={}
    if not isinstance(receipt,dict):
        receipt={}
    pages=receipt.get('plan',[])
    if not isinstance(pages,list) or not pages:
        report={'status':'draft','issues':[],'runs':[],'actual':measure(parts)}
        return describe(report,parts)
    document={'demo':True,'slides':pages}
    report=inspect(document,parts)
    result=describe(report,parts,document)
    result['status']='draft'
    result['previous_plan_is_current']=receipt.get('pptx_fingerprint')==fingerprint(parts)
    return result


def check_edited(document,path):
    """A re-reviewed hand edit is measured afresh, never allowed to inherit an old pass."""
    if document.get('demo') is not False:
        raise ValueError('Formal re-review requires a non-demo input document')
    parts=readzip(path)
    report=inspect(document,parts)
    if not report['ok']:
        raise ValueError('Structure check failed for the edited deck: '+json.dumps(report['issues'],ensure_ascii=False))
    return describe(report,parts,document)


def check_pptx(path):
    """Reapply the plan and geometry checks to a sealed, unchanged presentation."""
    parts=readzip(path)
    if PART not in parts:
        raise ValueError('No structure review receipt; use a draft or re-review the actual PPTX')
    receipt=json.loads(parts[PART])
    if not isinstance(receipt,dict) or receipt.get('version')!=VERSION:
        raise ValueError('Unsupported structure receipt; re-review the actual PPTX with the current skill')
    if receipt.get('status') not in {'confirmed','review_required'}:
        raise ValueError('Structure check did not pass for this deck ('+str(receipt.get('status'))+')')
    if receipt.get('pptx_fingerprint')!=fingerprint(parts):
        raise ValueError('Structure report is stale: the deck changed after the check; re-review this PPTX')
    document={'demo':False,'slides':receipt.get('plan')}
    report=inspect(document,parts)
    fresh=describe(report,parts,document)
    if not report['ok'] or any(receipt.get(key)!=fresh[key] for key in ('status','actual','runs','plan')):
        raise ValueError('Structure report disagrees with the saved file; re-review this PPTX')
    return fresh


def accept_rhythm(report, review, digest):
    """Require a separate review decision for each run, tied to the final file."""
    runs=report['runs']
    if not runs:
        return report
    expected=[{key:run[key] for key in ('start','end','structure','reason')} for run in runs]
    if (not isinstance(review,dict) or review.get('pptx_sha256')!=digest or
            not text(review.get('reviewer')) or not text(review.get('note')) or review.get('accepted_runs')!=expected):
        raise ValueError('Repeated structures require a separate rhythm review matching this PPTX SHA256 and every flagged run')
    record={key:review[key] for key in ('pptx_sha256','reviewer','note','accepted_runs')}
    return dict(report,status='confirmed',rhythm_review=record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,help='Authoring JSON to check before generation')
    parser.add_argument('--pptx',type=Path,help='Saved deck to re-measure')
    args=parser.parse_args()
    if not args.input and not args.pptx:
        parser.error('supply --input and/or --pptx')
    try:
        if args.input:
            document=json.loads(args.input.read_text(encoding='utf-8-sig'))
            parts=readzip(args.pptx) if args.pptx else None
            report=inspect(document,parts)
            report=dict(describe(report,parts,document),ok=report['ok'])
        else:
            report=check_pptx(args.pptx);report['ok']=True
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,E.ParseError) as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)},ensure_ascii=False,indent=2));return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report.get('ok') else 2


if __name__=='__main__':raise SystemExit(main())
