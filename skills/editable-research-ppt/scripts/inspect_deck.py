"""Read-only PPTX object inventory, offline dependencies and privacy indicators.

No note text or relationship target is copied into the report. This is not a
content, licence, rendering or full privacy review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
PRIVATE=[('local_path',re.compile(r'(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|/(?:Users|home|mnt)/)')),
         ('credential_like',re.compile(r'(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,})'))]


def relfile(owner):
    return posixpath.join(posixpath.dirname(owner),'_rels',posixpath.basename(owner)+'.rels')


def resolve(owner,target):
    target=target.split('#',1)[0]
    result=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(owner),target))
    if result.startswith('../') or result=='..' or '\\' in result:
        raise ValueError('Relationship escapes package')
    return result


def inspect(path):
    result={'ok':False,'pages':[],'errors':[],'external_relationships':[],
            'privacy_indicators':[],'metadata_fields':[],
            'scope':'Package relationships, display-order object counts, embedded chart workbooks and pattern-based privacy indicators. Native structure does not prove usable editing, complete privacy, scientific validity, licensing or visual quality.'}
    try:
        path=Path(path)
        result['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as z:
            names=set(z.namelist())
            if len(names)!=len(z.namelist()):raise ValueError('Duplicate ZIP member names')
            bad=z.testzip()
            if bad:raise ValueError('ZIP checksum failure')
            def relations(owner):
                part=relfile(owner)
                return {r.get('Id'):r for r in ET.fromstring(z.read(part))} if part in names else {}
            # All parts, not just visible slides: hidden notes or masters can link out.
            for part in sorted(names):
                if part.endswith('.rels'):
                    owner='' if part=='_rels/.rels' else posixpath.join(posixpath.dirname(posixpath.dirname(part)),posixpath.basename(part)[:-5])
                    for rel in ET.fromstring(z.read(part)):
                        kind=rel.get('Type','').rsplit('/',1)[-1]
                        if rel.get('TargetMode')=='External':
                            result['external_relationships'].append({'part':part,'id':rel.get('Id'),'kind':kind,'offline_dependency':kind!='hyperlink'})
                        elif resolve(owner,rel.get('Target','')) not in names:
                            result['errors'].append('Missing relationship target in '+part+' '+str(rel.get('Id')))
                if part.endswith(('.xml','.rels')):
                    raw=z.read(part).decode('utf-8')
                    # Scan both XML attributes and joined text (tokens may span runs).
                    root=ET.fromstring(raw)
                    texts=[raw,''.join(root.itertext())]
                    for code,pattern in PRIVATE:
                        if any(pattern.search(t) for t in texts):
                            result['privacy_indicators'].append({'part':part,'code':code})
                if part=='docProps/core.xml':
                    result['metadata_fields']=[el.tag.rsplit('}',1)[-1] for el in ET.fromstring(z.read(part)) if el.text and el.text.strip()]
            pres=ET.fromstring(z.read('ppt/presentation.xml'))
            size=pres.find('p:sldSz',NS)
            canvas=(int(size.get('cx')),int(size.get('cy'))) if size is not None else None
            order=pres.find('p:sldIdLst',NS)
            if order is None or not len(order):raise ValueError('Presentation has no slides')
            rels=relations('ppt/presentation.xml')
            for index,entry in enumerate(order,1):
                rel=rels[entry.get('{'+NS['r']+'}id')]
                if rel.get('TargetMode')=='External' or not rel.get('Type','').endswith('/slide'):
                    raise ValueError('Invalid slide relationship')
                part=resolve('ppt/presentation.xml',rel.get('Target',''))
                root=ET.fromstring(z.read(part));srels=relations(part)
                page={'page':index,'part':part,'text_objects':0,'native_shapes':0,'groups':0,
                      'connectors':0,'pictures':0,'native_charts':0,'tables':0,
                      'charts_with_embedded_workbooks':0,'video_relationships':0,'has_notes':False,
                      'possible_image_only_page':False,'fonts':[]}
                page['text_objects']=sum(bool(''.join(sp.itertext()).strip()) and bool(sp.findall('.//a:t',NS)) for sp in root.findall('.//p:sp',NS))
                page['native_shapes']=len(root.findall('.//p:sp',NS))
                page['groups']=len(root.findall('.//p:grpSp',NS))
                page['connectors']=len(root.findall('.//p:cxnSp',NS))
                page['pictures']=len(root.findall('.//p:pic',NS))
                page['tables']=len(root.findall('.//a:tbl',NS))
                page['fonts']=sorted({f.get('typeface') for tag in ['latin','ea','cs'] for f in root.findall('.//a:'+tag,NS) if f.get('typeface')})
                for ch in root.findall('.//c:chart',NS):
                    page['native_charts']+=1
                    crel=srels[ch.get('{'+NS['r']+'}id')]
                    if crel.get('TargetMode')=='External':continue
                    cpart=resolve(part,crel.get('Target',''));chart=ET.fromstring(z.read(cpart))
                    ext=chart.find('c:externalData',NS)
                    if ext is not None:
                        er=relations(cpart).get(ext.get('{'+NS['r']+'}id'))
                        if er is not None and er.get('TargetMode')!='External':
                            embedded=resolve(cpart,er.get('Target',''))
                            if embedded in names and embedded.lower().endswith('.xlsx'):
                                page['charts_with_embedded_workbooks']+=1
                for r in srels.values():
                    kind=r.get('Type','').rsplit('/',1)[-1]
                    if kind=='notesSlide':page['has_notes']=True
                    if kind=='video':page['video_relationships']+=1
                if not page['text_objects'] and not page['native_charts'] and not page['tables'] and page['pictures'] and canvas:
                    for pic in root.findall('.//p:pic',NS):
                        extent=pic.find('p:spPr/a:xfrm/a:ext',NS)
                        if extent is not None and int(extent.get('cx'))*int(extent.get('cy'))>=canvas[0]*canvas[1]*.9:
                            page['possible_image_only_page']=True
                result['pages'].append(page)
            fields=['text_objects','native_shapes','groups','connectors','pictures','native_charts','tables','charts_with_embedded_workbooks','video_relationships']
            result['totals']={k:sum(p[k] for p in result['pages']) for k in fields}
            result['offline_dependencies']=sum(r['offline_dependency'] for r in result['external_relationships'])
            result['ok']=not result['errors']
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,zipfile.BadZipFile,ET.ParseError) as exc:
        result['errors'].append(type(exc).__name__+': '+str(exc))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx',type=Path)
    parser.add_argument('--require-offline',action='store_true')
    args=parser.parse_args()
    report=inspect(args.pptx)
    if args.require_offline and report.get('offline_dependencies',0):
        report['ok']=False;report['errors'].append('External content dependencies require network or local source files')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
