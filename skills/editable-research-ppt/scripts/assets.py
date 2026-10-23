"""Search bundled illustrations and insert cached native groups into a PPTX.

Stdlib only, no downloads, Office automation, or changes to the source deck.
"""
from __future__ import annotations
import argparse,copy,hashlib,io,json,math,posixpath,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
LIBRARY=ROOT/'assets/media-library'
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','rel':'http://schemas.openxmlformats.org/package/2006/relationships'}
for prefix,uri in NS.items():E.register_namespace(prefix,uri)
q=lambda prefix,name:'{'+NS[prefix]+'}'+name
digest=lambda data:hashlib.sha256(data).hexdigest()


def library_file(root,name):
    root=Path(root).resolve();path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Asset path missing or outside library')
    return path


def load_catalog(root=LIBRARY):
    doc=json.loads(library_file(root,'catalog.json').read_text(encoding='utf-8'))
    if len({a['id'] for a in doc['assets']})!=len(doc['assets']):raise ValueError('Duplicate asset IDs')
    return doc


def search(query='',theme='',native_only=False,root=LIBRARY):
    terms=query.casefold().split();groups={g['id'] for g in json.loads(library_file(root,'themes.json').read_text(encoding='utf-8'))['groups']}
    if theme and theme not in groups and theme!='ecology-field-genetics':raise ValueError('Unknown asset theme')
    found=[]
    for item in load_catalog(root)['assets']:
        text=' '.join([item['id'],item['label_zh'],item['category'],*item.get('keywords',[])]).casefold()
        if not all(t in text for t in terms):continue
        if theme and not (item.get('themes') if theme=='ecology-field-genetics' else theme in item.get('themes',[])):continue
        if native_only and not item.get('native',{}).get('path'):continue
        found.append(item)
    return found


def xml(data):return E.tostring(data,encoding='utf-8',xml_declaration=True)


def checked_native(item,root):
    original=library_file(root,item['path']).read_bytes()
    if digest(original)!=item['sha256']:raise ValueError('Original SVG hash mismatch: '+item['id'])
    meta=item.get('native',{})
    if not meta.get('path'):raise ValueError('Native conversion unavailable for '+item['id']+': '+meta.get('reason','use original SVG / PNG fallback'))
    data=library_file(root,meta['path']).read_bytes()
    if digest(data)!=meta['sha256']:raise ValueError('Native cache hash mismatch: '+item['id'])
    root=E.fromstring(data)
    if root.tag!=q('p','grpSp') or root.findall('.//p:pic',NS) or root.findall('.//a:blip',NS):raise ValueError('Expected a native shape group without pictures')
    return root


def relationships(parts,part):
    folder,name=posixpath.split(part);rel=folder+'/_rels/'+name+'.rels'
    if rel not in parts:return {}
    return {node.get('Id'):(posixpath.normpath(posixpath.join(folder,node.get('Target'))) if not node.get('Target').startswith('/') else node.get('Target').lstrip('/')) for node in E.fromstring(parts[rel]) if node.get('TargetMode')!='External'}


def insert(source,output,config,library=LIBRARY):
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output:raise ValueError('Source and output must differ')
    if output.exists():raise FileExistsError('Output already exists; source is never overwritten')
    config=copy.deepcopy(config);placements=config.get('placements')
    if not isinstance(placements,list) or not placements:raise ValueError('placements must be a nonempty list')
    canvas=config.get('canvas',[1280,720])
    if not isinstance(canvas,list) or len(canvas)!=2 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0 for x in canvas):raise ValueError('Invalid canvas')
    catalog={a['id']:a for a in load_catalog(library)['assets']}
    source_bytes=source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
        if len(set(z.namelist()))!=len(z.namelist()):raise ValueError('Duplicate PPTX archive entries')
        parts={name:z.read(name) for name in z.namelist()}
    presentation=E.fromstring(parts['ppt/presentation.xml']);size=presentation.find('p:sldSz',NS)
    cx,cy=int(size.get('cx')),int(size.get('cy'))
    if abs(cx/cy-canvas[0]/canvas[1])>0.01:raise ValueError('Canvas ratio does not match PPT slide size')
    sx,sy=cx/canvas[0],cy/canvas[1]
    rels=relationships(parts,'ppt/presentation.xml')
    slideparts=[rels[s.get(q('r','id'))] for s in presentation.findall('p:sldIdLst/p:sldId',NS)]
    slides={};records=[];credits={}
    for index,place in enumerate(placements,1):
        num=place.get('slide')
        if isinstance(num,bool) or not isinstance(num,int) or not 1<=num<=len(slideparts):raise ValueError('Invalid slide number')
        aid=place.get('asset');item=catalog.get(aid)
        if item is None:raise ValueError('Unknown asset ID: '+str(aid))
        group=checked_native(item,library)
        part=slideparts[num-1];slide=slides.setdefault(part,E.fromstring(parts[part]));tree=slide.find('p:cSld/p:spTree',NS)
        box=place.get('box');target=place.get('target');old=None
        if target is not None:
            if box is not None:raise ValueError('Use target or box, not both')
            matching=[s for s in tree if any(n.get('name')==target for n in s.findall('.//p:cNvPr',NS))]
            if len(matching)!=1:raise ValueError('Target name must match one top-level object')
            old=matching[0];xf=old.find('p:spPr/a:xfrm',NS)
            if xf is None or xf.get('rot','0')!='0':raise ValueError('Target must be an unrotated ordinary shape')
            off,ext=xf.find('a:off',NS),xf.find('a:ext',NS)
            box=[int(off.get('x'))/sx,int(off.get('y'))/sy,int(ext.get('cx'))/sx,int(ext.get('cy'))/sy]
        if not isinstance(box,list) or len(box)!=4 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in box):raise ValueError('Invalid placement box')
        x,y,w,h=box
        if min(x,y)<0 or min(w,h)<=0 or x+w>canvas[0]+0.01 or y+h>canvas[1]+0.01:raise ValueError('Placement is outside the slide')
        width,height=item['native']['width'],item['native']['height'];ratio=min(w/width,h/height)
        fw,fh=width*ratio,height*ratio;x+=(w-fw)/2;y+=(h-fh)/2
        xf=group.find('p:grpSpPr/a:xfrm',NS);xf.find('a:off',NS).set('x',str(round(x*sx)));xf.find('a:off',NS).set('y',str(round(y*sy)))
        # DrawingML line widths use slide EMU, unlike path coordinates inside
        # chExt. Scale explicitly so SVG outline weight survives placement.
        line_scale=min(fw*sx/int(xf.find('a:chExt',NS).get('cx')),fh*sy/int(xf.find('a:chExt',NS).get('cy')))
        for line in group.findall('.//a:ln',NS):
            if line.get('w'):line.set('w',str(max(1,round(int(line.get('w'))*line_scale))))
        xf.find('a:ext',NS).set('cx',str(round(fw*sx)));xf.find('a:ext',NS).set('cy',str(round(fh*sy)))
        used_ids=[int(n.get('id')) for n in slide.findall('.//p:cNvPr',NS)];nextid=max(used_ids,default=0)+1
        used_names={n.get('name') for n in slide.findall('.//p:cNvPr',NS)}
        name=place.get('name','asset-'+str(index)+'-'+aid.replace('/','-'))
        if not isinstance(name,str) or not name or name in used_names:raise ValueError('Asset group name must be unique on the slide')
        for j,node in enumerate(group.findall('.//p:cNvPr',NS)):
            node.set('id',str(nextid+j));node.set('name',name if j==0 else name+'-part-'+str(j))
        color=place.get('color')
        if color is not None:
            if not isinstance(color,str) or not re.fullmatch('[0-9A-Fa-f]{6}',color):raise ValueError('color must be six hex digits')
            for clr in group.findall('.//a:srgbClr',NS):clr.set('val',color.upper())
        if old is not None:
            position=list(tree).index(old);tree.remove(old);tree.insert(position,group)
        else:
            extlist=tree.find('p:extLst',NS)
            tree.insert(list(tree).index(extlist),group) if extlist is not None else tree.append(group)
        credit=item['attribution']+' Source: '+item['source_url']+'; SVG SHA256: '+item['sha256']+'; native DrawingML derivative'+('; recolored '+color if color else '; original colors retained')
        group.find('p:nvGrpSpPr/p:cNvPr',NS).set('descr',credit)
        credits.setdefault(part,[]).append(credit)
        records.append({'slide':num,'asset':aid,'name':name,'native_parts':item['native']['native_parts'],'source_sha256':item['sha256'],'cache_sha256':item['native']['sha256'],'edit_probe':item['native'].get('edit_probe','pending'),'box':[x,y,fw,fh]})
    for part,slide in slides.items():
        parts[part]=xml(slide)
        for notes in relationships(parts,part).values():
            if notes.startswith('ppt/notesSlides/') and notes.endswith('.xml') and notes in parts:
                root=E.fromstring(parts[notes]);body=next((s.find('p:txBody',NS) for s in root.findall('.//p:sp',NS) if s.find('p:nvSpPr/p:nvPr/p:ph',NS) is not None and s.find('p:nvSpPr/p:nvPr/p:ph',NS).get('type')=='body'),None)
                if body is not None:
                    for credit in credits[part]:
                        p=E.SubElement(body,q('a','p'));r=E.SubElement(p,q('a','r'));E.SubElement(r,q('a','t')).text=credit
                    parts[notes]=xml(root)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(stream.getvalue())
    return {'ok':True,'source_sha256':digest(source_bytes),'output_sha256':digest(stream.getvalue()),'placements':records,'scope':'Native cached geometry. Actual rendering/editing depends on target software; source deck is unchanged.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('search');s.add_argument('query',nargs='?',default='');s.add_argument('--theme',default='');s.add_argument('--native-only',action='store_true');s.add_argument('--limit',type=int,default=30)
    i=sub.add_parser('insert');i.add_argument('--source',type=Path,required=True);i.add_argument('--output',type=Path,required=True);i.add_argument('--config',type=Path,required=True);i.add_argument('--report',type=Path)
    a=p.parse_args()
    try:
        if a.command=='search':
            items=search(a.query,a.theme,a.native_only)
            result={'total':len(items),'assets':[{k:x.get(k) for k in ('id','label_zh','style','path','license','source_url','native','themes')} for x in items[:max(0,a.limit)]]}
        else:
            if a.report and (a.report.exists() or a.report.resolve() in (a.source.resolve(),a.output.resolve())):raise FileExistsError('Report output must be new and separate')
            result=insert(a.source,a.output,json.loads(a.config.read_text(encoding='utf-8-sig')))
            if a.report:
                a.report.parent.mkdir(parents=True,exist_ok=True)
                with a.report.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,KeyError,E.ParseError,zipfile.BadZipFile) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
