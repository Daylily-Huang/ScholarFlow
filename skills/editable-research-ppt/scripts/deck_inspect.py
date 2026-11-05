#!/usr/bin/env python3
"""Recover the visual structure each slide of a saved PPTX actually has, measurement only and read-only."""

from __future__ import annotations
import argparse, json, posixpath, zipfile
from pathlib import Path
import xml.etree.ElementTree as E

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
EMU=9525
CANVAS=(1280,720)
TOL=40
STRUCTURE_TYPES=('cover','section','agenda','image_led','comparison','process','cards','data','chart','statement','closing')


def q(prefix,name):
    return '{'+NS[prefix]+'}'+name


def relpart(part):
    return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')


def resolve(owner,target):
    target=target.split('#',1)[0]
    joined=target if target.startswith('/') else posixpath.join(posixpath.dirname(owner),target)
    return posixpath.normpath(joined).lstrip('/')


def readzip(path):
    with zipfile.ZipFile(path) as z:return {n:z.read(n) for n in z.namelist()}


def relations(parts,owner):
    part=relpart(owner)
    if part not in parts:return {}
    return {r.get('Id'):r.get('Target','') for r in E.fromstring(parts[part]) if r.get('TargetMode')!='External'}


def frame(node):
    """Local (x,y,cx,cy) in EMU from the shape's own transform, or None when it is inherited."""
    for path in ('p:spPr/a:xfrm','p:xfrm','p:grpSpPr/a:xfrm'):
        xfrm=node.find(path,NS)
        if xfrm is None:continue
        off,ext=xfrm.find('a:off',NS),xfrm.find('a:ext',NS)
        if off is None or ext is None:continue
        return int(off.get('x')),int(off.get('y')),int(ext.get('cx')),int(ext.get('cy'))
    return None


def collect(node,affine,out):
    """Flatten spTree into (shape,affine) pairs. Affine maps local EMU to page EMU as page=off+scale*local.

    A group child lives in the group's child coordinate space; it is mapped linearly onto the
    page using the group's a:off/a:ext against a:chOff/a:chExt (no rotation or flip handling).
    """
    sx,ox,sy,oy=affine
    for child in node:
        tag=child.tag.rsplit('}',1)[-1]
        if tag=='grpSp':
            xfrm=child.find('p:grpSpPr/a:xfrm',NS)
            chOff=xfrm.find('a:chOff',NS) if xfrm is not None else None
            chExt=xfrm.find('a:chExt',NS) if xfrm is not None else None
            if xfrm is not None and chOff is not None and chExt is not None and int(chExt.get('cx')) and int(chExt.get('cy')):
                off,ext=xfrm.find('a:off',NS),xfrm.find('a:ext',NS)
                gsx=int(ext.get('cx'))/int(chExt.get('cx'));gsy=int(ext.get('cy'))/int(chExt.get('cy'))
                cox=int(chOff.get('x'))*gsx;coy=int(chOff.get('y'))*gsy
                inner=(sx*gsx,ox+sx*(int(off.get('x'))-cox),sy*gsy,oy+sy*(int(off.get('y'))-coy))
                collect(child,inner,out)
            else:
                collect(child,affine,out)
        elif tag in ('sp','pic','graphicFrame','cxnSp'):
            out.append((child,affine))


def box_of(node,affine):
    """Page-space [x,y,w,h] in px on the 1280x720 canvas, or None if the shape has no explicit frame."""
    local=frame(node)
    if local is None:return None
    sx,ox,sy,oy=affine
    x,y,cx,cy=local
    return [round((ox+sx*x)/EMU,1),round((oy+sy*y)/EMU,1),round(sx*cx/EMU,1),round(sy*cy/EMU,1)]


def has_text(node):
    return any(t.text and t.text.strip() for t in node.findall('.//a:t',NS))


def clusters(values,tol=TOL):
    """Count 1-D clusters; values closer than tol are joined and the running centre follows them."""
    if not values:return 0
    values=sorted(values);count=1;centre=values[0];size=1
    for value in values[1:]:
        if abs(value-centre)<=tol:
            centre=(centre*size+value)/(size+1);size+=1
        else:
            count+=1;centre=value;size=1
    return count


def min_font_px(root):
    """Smallest explicit size on the page: sz is 1/100 pt, so px = sz/100*96/72 = sz/75."""
    sizes=[int(el.get('sz')) for el in root.iter()
           if el.get('sz') and el.tag.rsplit('}',1)[-1] in ('rPr','endParaRPr','defRPr') and el.get('sz').isdigit()]
    return round(min(sizes)/75,1) if sizes else 0.0


def signature(pictures,picture_area,image_share,largest_share,tables,charts,text_boxes,rows,cols,font):
    return 'pics=%d share=%.3f big=%.3f tables=%d charts=%d text=%d rows=%d cols=%d font=%.1f'%(
        len(pictures),image_share,largest_share,tables,charts,text_boxes,rows,cols,font)


def shape_name(node):
    return next((element.get('name', '') for element in node.iter()
                 if element.tag == q('p', 'cNvPr')), '')


def matrix_grid(cells):
    """Recognize aligned cell shapes, including a header and one body row."""
    rows = {}
    for x, y, w, h in cells:
        rows.setdefault(round(y), []).append((round(x), round(w)))
    columns = [tuple(sorted(set(row))) for row in rows.values()]
    return len(columns) >= 2 and len(columns[0]) >= 4 and len(set(columns)) == 1


def slide_metrics(index,root):
    shapes=[]
    tree=root.find('p:cSld/p:spTree',NS)
    collect(tree if tree is not None else root,(1.0,0.0,1.0,0.0),shapes)
    canvas=CANVAS[0]*CANVAS[1]
    pictures=[];tables=charts=0;texts=[]
    cells=[]; arrows=lanes=nodes=panels=0
    for node,affine in shapes:
        tag=node.tag.rsplit('}',1)[-1]
        box=box_of(node,affine)
        if box is not None:
            name = shape_name(node)
            x,y,w,h = box
            visible = max(0,min(x+w,CANVAS[0])-max(x,0))*max(0,min(y+h,CANVAS[1])-max(y,0))
            if tag=='pic' and visible >= canvas*.025:
                pictures.append({'box':box,'area':round(visible,1)})
            if tag=='sp' and visible > 0:
                if name.startswith('matrix-cell-') and not has_text(node) and w>=40 and h>=25:
                    cells.append(box)
                if name.startswith('timeline-lane-') and w>=600 and h>=45:lanes+=1
                if name.startswith('time-node-'):nodes+=1
                if name.startswith('panel-') and 0.035*canvas<=visible<=0.35*canvas:panels+=1
            if 80<=y<=640 and 0<=x<=1248:
                geometry=node.find('p:spPr/a:prstGeom',NS)
                if (tag=='cxnSp' or (geometry is not None and 'arrow' in geometry.get('prst','').lower())) and max(w,h)>=12:
                    arrows+=1
        if tag=='graphicFrame' and box is not None and visible>=canvas*.01:
            if node.find('.//a:tbl',NS) is not None:tables+=1
            data=node.find('.//a:graphicData',NS)
            if data is not None and '/chart' in (data.get('uri') or ''):charts+=1
        if tag=='sp' and box is not None and visible>0 and has_text(node):
            texts.append(box)
    picture_area=round(sum(p['area'] for p in pictures),1)
    image_share=round(picture_area/canvas,3)
    largest=round(max([p['area'] for p in pictures] or [0.0])/canvas,3)
    placed=[t for t in texts if t is not None]
    rows=clusters([t[1]+t[3]/2 for t in placed])
    cols=clusters([t[0]+t[2]/2 for t in placed])
    font=min_font_px(root)
    return {'slide':index,'pictures':pictures,'picture_area':picture_area,'image_share':image_share,
            'largest_picture_share':largest,'tables':tables,'charts':charts,'text_boxes':len(texts),
            'text_rows':rows,'text_columns':cols,'min_font_px':font,
            'matrix_grid':matrix_grid(cells),'process_geometry':arrows>=2 or (lanes>=2 and nodes>=4),
            'connectors':arrows,'panels':panels,
            'signature':signature(pictures,picture_area,image_share,largest,tables,charts,len(texts),rows,cols,font)}


def structure_from_parts(parts):
    """Per-slide metrics in presentation order (p:sldIdLst, not filename order)."""
    if 'ppt/presentation.xml' not in parts:raise ValueError('Package has no presentation part')
    pres=E.fromstring(parts['ppt/presentation.xml'])
    rels=relations(parts,'ppt/presentation.xml')
    order=pres.find('p:sldIdLst',NS)
    if order is None:return []
    result=[]
    for index,entry in enumerate(order,1):
        target=rels.get(entry.get(q('r','id')))
        if target is None:raise ValueError('Slide '+str(index)+' has no internal slide relationship')
        part=resolve('ppt/presentation.xml',target)
        if part not in parts:raise ValueError('Missing slide part '+part)
        metrics=slide_metrics(index,E.fromstring(parts[part]))
        note_targets=[resolve(part,value) for value in relations(parts,part).values()]
        notes=next((parts[name] for name in note_targets if name.startswith('ppt/notesSlides/') and name in parts), None)
        metrics['generated_layout']=None
        if notes is not None:
            for paragraph in E.fromstring(notes).findall('.//a:p',NS):
                value=''.join(el.text or '' for el in paragraph.findall('.//a:t',NS))
                if value.startswith('Layout: '):
                    metrics['generated_layout']=value.removeprefix('Layout: ').strip()
                    break
        result.append(metrics)
    return result


def infer_actual(m):
    """Deterministic structure label from the measured metrics; see the ordered rules in the skill docs."""
    if m['matrix_grid']:return 'data'
    if m['largest_picture_share']>=0.25 or m['image_share']>=0.34:return 'image_led'
    if m['panels']>=3 and not m['charts'] and not m['tables']:return 'cards'
    if len(m['pictures'])>=2 and m['image_share']>=0.12:return 'comparison'
    if m['charts']>=1:return 'chart'
    if m['tables']>=1:return 'data'
    if m['process_geometry']:return 'process'
    if m['text_columns']>=3 and m['text_rows']>=3:return 'cards'
    if m['text_columns']>=2 and m['text_rows']>=2:return 'comparison'
    return 'statement'


def inspect_pptx(path):
    return structure_from_parts(readzip(path))


def summarize(metrics_list):
    structures=[infer_actual(m) for m in metrics_list]
    return {'slides':len(metrics_list),'structures':structures,
            'counts':{t:structures.count(t) for t in STRUCTURE_TYPES if t in structures}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx',type=Path)
    parser.add_argument('--per-slide',action='store_true',help='Include the full per-slide metrics.')
    args=parser.parse_args()
    try:
        metrics=inspect_pptx(args.pptx)
    except (OSError,KeyError,ValueError,zipfile.BadZipFile,E.ParseError) as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)},ensure_ascii=False,indent=2))
        return 1
    report={'ok':True,'pptx':args.pptx.name,'summary':summarize(metrics)}
    if args.per_slide:report['pages']=[dict(m,structure=infer_actual(m)) for m in metrics]
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
