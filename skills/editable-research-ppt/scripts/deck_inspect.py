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


def contains_center(outer,inner):
    x,y,w,h=outer
    ix,iy,iw,ih=inner
    return x <= ix+iw/2 <= x+w and y <= iy+ih/2 <= y+h


def panel_count(rectangles,texts,canvas):
    """Count distinct text-bearing regions from visible shapes, regardless of their names."""
    candidates=[b for b in rectangles if .035*canvas<=b[2]*b[3]<=.35*canvas
                and any(contains_center(b,txt) for txt in texts)]
    independent=[]
    for box in sorted(candidates,key=lambda b:b[2]*b[3],reverse=True):
        if not any(contains_center(other,box) or contains_center(box,other) for other in independent):
            independent.append(box)
    return len(independent)


def matrix_grid(rectangles,texts):
    """Find two contiguous rows of aligned, text-bearing cells."""
    rows={}
    for box in rectangles:
        x,y,w,h=box
        if w>=40 and h>=25 and any(contains_center(box,txt) for txt in texts):
            rows.setdefault(round(y),[]).append((round(x),round(w),round(h)))
    signatures={}
    for y,cells in sorted(rows.items()):
        cells=sorted(set(cells))
        if len(cells)<4 or any(abs(x+w-nx)>2 for (x,w,_),(nx,_,_) in zip(cells,cells[1:])):
            continue
        columns=tuple((x,w) for x,w,_ in cells)
        if columns in signatures and abs(signatures[columns]-y)<=2:
            return True
        signatures[columns]=y+max(h for _,_,h in cells)
    return False


# Text anchors from the approved navigation layouts. A tolerance accommodates
# the two fills and their adaptive title frames, and small PowerPoint edits.
NAVIGATION_ANCHORS={
    'L5':((38,76,620,30),(40,184,616,193)),
    'L6':((30,80,190,90),(40,177,174,32),(300,125,48,48)),
    'L7':((36,60,275,150),(39,230,605,168)),
    'L14':((48,117,560,233),(48,432,568,71)),
}


def navigation_layout(texts,tables,charts):
    if tables or charts:
        return None
    for layout,anchors in NAVIGATION_ANCHORS.items():
        if all(any(all(abs(expected-actual)<=tol for expected,actual,tol in
                       zip(anchor,box,(24,24,55,18))) for box in texts) for anchor in anchors):
            return layout
    return None


def slide_metrics(index,root):
    shapes=[]
    tree=root.find('p:cSld/p:spTree',NS)
    collect(tree if tree is not None else root,(1.0,0.0,1.0,0.0),shapes)
    canvas=CANVAS[0]*CANVAS[1]
    pictures=[];tables=charts=0;texts=[]
    rectangles=[]; nodes=[]; arrows=0
    for node,affine in shapes:
        tag=node.tag.rsplit('}',1)[-1]
        box=box_of(node,affine)
        if box is not None:
            x,y,w,h = box
            visible = max(0,min(x+w,CANVAS[0])-max(x,0))*max(0,min(y+h,CANVAS[1])-max(y,0))
            if tag=='pic' and visible >= canvas*.025:
                pictures.append({'box':box,'area':round(visible,1)})
            geometry=node.find('p:spPr/a:prstGeom',NS)
            preset=geometry.get('prst','') if geometry is not None else ''
            if tag=='sp' and visible>0 and not has_text(node):
                if preset in {'rect','roundRect'} and node.find('p:spPr/a:solidFill',NS) is not None:
                    rectangles.append(box)
                elif preset=='ellipse' and 6<=w<=30 and 6<=h<=30:
                    nodes.append(box)
            if (80<=y<=640 and 0<=x<=1248 and max(w,h)>=12 and
                    (tag=='cxnSp' or 'arrow' in preset.lower())):
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
    lanes=sum(1 for box in rectangles if box[2]>=600 and box[3]>=45 and
              sum(contains_center(box,node) for node in nodes)>=2)
    rows=clusters([t[1]+t[3]/2 for t in placed])
    cols=clusters([t[0]+t[2]/2 for t in placed])
    font=min_font_px(root)
    return {'slide':index,'pictures':pictures,'picture_area':picture_area,'image_share':image_share,
            'largest_picture_share':largest,'tables':tables,'charts':charts,'text_boxes':len(texts),
            'text_rows':rows,'text_columns':cols,'min_font_px':font,
            'matrix_grid':matrix_grid(rectangles,placed),'process_geometry':arrows>=2 or lanes>=2,
            'connectors':arrows,'panels':panel_count(rectangles,placed,canvas),
            'navigation_layout':navigation_layout(placed,tables,charts),
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
        result.append(slide_metrics(index,E.fromstring(parts[part])))
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
