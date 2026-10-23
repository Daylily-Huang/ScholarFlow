"""Optional SVG -> DrawingML cache compiler (svgelements==1.9.6 required).

Normal asset search/insertion needs only Python stdlib. Unsupported SVG features
are rejected rather than silently rasterized or flattened incorrectly.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, re
from pathlib import Path
import xml.etree.ElementTree as E

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
for prefix,uri in NS.items():E.register_namespace(prefix,uri)
SVG='http://www.w3.org/2000/svg'
q=lambda prefix,name:'{'+NS[prefix]+'}'+name


def precheck(data):
    if len(data)>4_000_000 or re.search(br'<!DOCTYPE|<!ENTITY',data,re.I):
        raise ValueError('DTD/entities or oversized SVG are unsupported')
    root=E.fromstring(data)
    if root.tag!='{'+SVG+'}svg':raise ValueError('Expected SVG root')
    allowed={'svg','g','path','rect','circle','ellipse','polygon','polyline','line','defs','title','desc','metadata'}
    for node in root.iter():
        if node.tag.startswith('{') and not node.tag.startswith('{'+SVG+'}'):continue
        tag=node.tag.rsplit('}',1)[-1]
        if tag not in allowed:raise ValueError('Unsupported SVG feature: '+tag)
        for key,value in node.attrib.items():
            key=key.rsplit('}',1)[-1]
            if key.lower().startswith('on') or key in {'href','clip-path','mask','filter','vector-effect'} or 'url(' in value:
                raise ValueError('Unsupported SVG attribute/resource: '+key)
            if key=='fill-rule' and value=='evenodd':raise ValueError('evenodd fill requires image fallback')
        style=node.get('style','')
        if re.search(r'fill-rule\s*:\s*evenodd|mix-blend|isolation',style):raise ValueError('Unsupported fill/blending rule')
        if tag in {'g','svg'}:
            opacity=node.get('opacity')
            match=re.search(r'(?:^|;)\s*opacity\s*:\s*([^;]+)',style)
            if opacity is not None and float(opacity)!=1 or match and float(match[1])!=1:
                raise ValueError('Group opacity requires image fallback')
    return root


def compile_svg(data,asset_id='asset'):
    precheck(data)
    try:
        from svgelements import SVG as Parser,Shape,Path as SvgPath,Move,Line,Close,CubicBezier,QuadraticBezier
    except ImportError as exc:
        raise RuntimeError('Compilation only: install svgelements==1.9.6 in a separate build environment') from exc
    parsed=Parser.parse(io.BytesIO(data),reify=True)
    width,height=float(parsed.width),float(parsed.height)
    if not all(math.isfinite(v) and 0<v<1e7 for v in (width,height)):raise ValueError('Invalid SVG dimensions')
    scale=10000
    unit=lambda v:str(round(float(v)*scale))
    group=E.Element(q('p','grpSp'))
    nv=E.SubElement(group,q('p','nvGrpSpPr'))
    E.SubElement(nv,q('p','cNvPr'),id='1',name='asset:'+asset_id,descr=json.dumps({'asset_id':asset_id,'source_sha256':hashlib.sha256(data).hexdigest()}))
    E.SubElement(nv,q('p','cNvGrpSpPr'));E.SubElement(nv,q('p','nvPr'))
    gp=E.SubElement(group,q('p','grpSpPr'));xf=E.SubElement(gp,q('a','xfrm'))
    for tag,attrs in [('off',{'x':'0','y':'0'}),('ext',{'cx':unit(width),'cy':unit(height)}),('chOff',{'x':'0','y':'0'}),('chExt',{'cx':unit(width),'cy':unit(height)})]:E.SubElement(xf,q('a',tag),attrs)
    count=0
    for element in parsed.elements():
        if not isinstance(element,Shape):continue
        values=element.values
        if values.get('visibility')=='hidden' or values.get('display')=='none':continue
        if values.get('fill-rule')=='evenodd':raise ValueError('evenodd fill requires image fallback')
        path=SvgPath(element);path.reify();path.approximate_arcs_with_cubics(error=0.01)
        if not path:continue
        coords=path.bbox()
        if coords is None:continue
        x,y,x2,y2=coords;w=max(x2-x,0.001);h=max(y2-y,0.001)
        if not all(math.isfinite(v) for v in (*coords,w,h)):raise ValueError('Non-finite geometry')
        # Clip/mask support is intentionally absent. Reject geometry outside viewport.
        if min(x,y)<-0.02 or x2>width+0.02 or y2>height+0.02:raise ValueError('Geometry extends outside SVG viewport')
        fill,stroke=element.fill,element.stroke
        if (fill is None or fill.value is None) and (stroke is None or stroke.value is None):continue
        count+=1
        if count>1500:raise ValueError('Too many native components')
        shape=E.SubElement(group,q('p','sp'));nv=E.SubElement(shape,q('p','nvSpPr'))
        E.SubElement(nv,q('p','cNvPr'),id=str(count+1),name=asset_id+':part:'+str(count))
        E.SubElement(nv,q('p','cNvSpPr'));E.SubElement(nv,q('p','nvPr'))
        props=E.SubElement(shape,q('p','spPr'));xf=E.SubElement(props,q('a','xfrm'))
        E.SubElement(xf,q('a','off'),x=unit(x),y=unit(y));E.SubElement(xf,q('a','ext'),cx=unit(w),cy=unit(h))
        geom=E.SubElement(props,q('a','custGeom'))
        for name in ('avLst','gdLst','ahLst','cxnLst'):E.SubElement(geom,q('a',name))
        E.SubElement(geom,q('a','rect'),l='0',t='0',r='r',b='b')
        paths=E.SubElement(geom,q('a','pathLst'));target=E.SubElement(paths,q('a','path'),w=unit(w),h=unit(h))
        def point(parent,p):E.SubElement(parent,q('a','pt'),x=unit(p.x-x),y=unit(p.y-y))
        for segment in path:
            if isinstance(segment,Move):point(E.SubElement(target,q('a','moveTo')),segment.end)
            elif isinstance(segment,Close):E.SubElement(target,q('a','close'))
            elif isinstance(segment,Line):point(E.SubElement(target,q('a','lnTo')),segment.end)
            elif isinstance(segment,CubicBezier):
                node=E.SubElement(target,q('a','cubicBezTo'))
                for p in (segment.control1,segment.control2,segment.end):point(node,p)
            elif isinstance(segment,QuadraticBezier):
                node=E.SubElement(target,q('a','quadBezTo'));point(node,segment.control);point(node,segment.end)
            else:raise ValueError('Unsupported path segment '+type(segment).__name__)
        opacity=float(values.get('opacity',1))
        def paint(parent,color,paint_opacity=1):
            if color is None or color.value is None:E.SubElement(parent,q('a','noFill'));return
            solid=E.SubElement(parent,q('a','solidFill'))
            clr=E.SubElement(solid,q('a','srgbClr'),val=f'{color.red:02X}{color.green:02X}{color.blue:02X}')
            alpha=float(color.alpha)/255*opacity*float(paint_opacity)
            if alpha<1:E.SubElement(clr,q('a','alpha'),val=str(round(max(0,min(1,alpha))*100000)))
        paint(props,fill,values.get('fill-opacity',1))
        stroke_width=float(element.stroke_width)*scale
        line=E.SubElement(props,q('a','ln'),w=str(max(1,round(stroke_width))),cap={'round':'rnd','square':'sq'}.get(values.get('stroke-linecap'),'flat'))
        paint(line,stroke,values.get('stroke-opacity',1))
        dash=values.get('stroke-dasharray')
        if dash and dash!='none':raise ValueError('Dashed strokes require image fallback')
        E.SubElement(line,q('a','prstDash'),val='solid')
        join=values.get('stroke-linejoin','miter')
        E.SubElement(line,q('a',{'round':'round','bevel':'bevel'}.get(join,'miter')))
    if not count:raise ValueError('No visible geometry')
    return E.tostring(group,encoding='utf-8',xml_declaration=True),{'width':width,'height':height,'native_parts':count,'compiler':'svgelements-1.9.6 + DrawingML; arc approximation error=0.01 SVG unit'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--id',default='asset');a=p.parse_args()
    if a.output.exists():raise FileExistsError('Refusing to replace output')
    data,meta=compile_svg(a.source.read_bytes(),a.id)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data)
    print(json.dumps(meta))


if __name__=='__main__':main()
