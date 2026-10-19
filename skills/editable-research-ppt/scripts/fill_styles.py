"""Native OOXML solid style, limited to the bundled L1-L14 geometry.

Preserves chart numbers, text content and relationships. Rebalances native
object geometry and typography for the larger, opaque presentation style.
"""
import copy
import xml.etree.ElementTree as E

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
def q(p,n):return '{'+NS[p]+'}'+n
EMU=9525

def box(sp):
    off=sp.find('p:spPr/a:xfrm/a:off',NS);ext=sp.find('p:spPr/a:xfrm/a:ext',NS)
    if off is None or ext is None:return None
    return tuple(int(el.get(k))/EMU for el,k in [(off,'x'),(off,'y'),(ext,'cx'),(ext,'cy')])

def inside(a,b,margin=1):
    return a[0]>=b[0]-margin and a[1]>=b[1]-margin and a[0]+a[2]<=b[0]+b[2]+margin and a[1]+a[3]<=b[1]+b[3]+margin

def center_inside(a,b):
    return b[0]<=a[0]+a[2]/2<=b[0]+b[2] and b[1]<=a[1]+a[3]/2<=b[1]+b[3]

def inkbox(sp):
    bounds=box(sp);path=sp.find('.//a:custGeom/a:pathLst/a:path',NS)
    if path is None:return bounds
    pts=path.findall('.//a:pt',NS)
    if not pts:return bounds
    xs=[int(p.get('x')) for p in pts];ys=[int(p.get('y')) for p in pts];pw=int(path.get('w'));ph=int(path.get('h'))
    return (bounds[0]+min(xs)/pw*bounds[2],bounds[1]+min(ys)/ph*bounds[3],(max(xs)-min(xs))/pw*bounds[2],(max(ys)-min(ys))/ph*bounds[3])

def fill(parent,color):
    old_indexes=[i for i,child in enumerate(parent) if child.tag in [q('a',x) for x in ['noFill','solidFill','gradFill','pattFill','blipFill','grpFill']]]
    for child in list(parent):
        if child.tag in [q('a',x) for x in ['noFill','solidFill','gradFill','pattFill','blipFill','grpFill']]:parent.remove(child)
    el=E.Element(q('a','solidFill'));E.SubElement(el,q('a','srgbClr'),val=color)
    # Shape fill follows geometry and precedes line/effect properties.
    before=old_indexes[0] if old_indexes else next((i for i,c in enumerate(parent) if c.tag in [q('a',x) for x in ['ln','effectLst','effectDag','scene3d','sp3d']]),len(parent))
    if parent.tag in [q('a',n) for n in ['rPr','defRPr','endParaRPr']]:before=1 if len(parent) and parent[0].tag==q('a','ln') else 0
    if parent.tag==q('a','ln'):before=0
    parent.insert(before,el)

def stroke(sp,color,width=1.5):
    props=sp.find('p:spPr',NS);line=props.find('a:ln',NS)
    if line is None:line=E.SubElement(props,q('a','ln'))
    line.set('w',str(round(width*EMU)));fill(line,color)

def text_color(sp,color):
    for props in sp.findall('.//a:rPr',NS)+sp.findall('.//a:defRPr',NS)+sp.findall('.//a:endParaRPr',NS):fill(props,color)

def typography(root,layout):
    """Larger type with a consistent 32px left/right safe area on content slides."""
    def split_line(sp,index):
        paragraph=sp.find('p:txBody/a:p',NS)
        if paragraph is None:return
        run=paragraph.find('a:r',NS)
        if run is None:return
        t=run.find('a:t',NS)
        if t is None or len(t.text or '')<=index:return
        tail=copy.deepcopy(run);tail.find('a:t',NS).text=t.text[index:];t.text=t.text[:index]
        idx=list(paragraph).index(run);paragraph.insert(idx+1,E.Element(q('a','br')));paragraph.insert(idx+2,tail)
    for sp in root.findall('.//p:sp',NS):
        b=box(sp)
        if not b or not sp.findall('.//a:t',NS):continue
        text=''.join(t.text or '' for t in sp.findall('.//a:t',NS));props=sp.findall('.//a:rPr',NS)+sp.findall('.//a:defRPr',NS)
        off=sp.find('p:spPr/a:xfrm/a:off',NS);ext=sp.find('p:spPr/a:xfrm/a:ext',NS)
        for rp in props:
            if not rp.get('sz'):continue
            old=int(rp.get('sz'))/75
            new=old if text=='!' else 14 if b[1]>=690 else 42 if b[1]<40 and old==36 else old+6 if 50<=old<=75 else old if old>75 else old+2 if old>=28 else max(17,old+3)
            rp.set('sz',str(round(new*75)))
        if b[1]<40 and b[3]>=40:off.set('y',str(10*EMU));ext.set('cy',str(58*EMU))
        if layout=='L1' and abs(b[2]-377)<1 and abs(b[3]-48)<1:ext.set('cy',str(58*EMU))
        if layout=='L1' and b[0]==42 and b[1]==153 and '，' in text:split_line(sp,text.index('，')+1)
        if layout=='L1' and abs(b[2]-130)<1:
            if 370<b[1]<400:
                split_line(sp,2);off.set('y',str(380*EMU));ext.set('cy',str(65*EMU))
            elif b[1]==530:off.set('y',str(515*EMU))
        if layout=='L2' and b[2]==22:
            off.set('x',str(27*EMU));ext.set('cx',str(30*EMU));off.set('y',str(round((b[1]-10)*EMU)));ext.set('cy',str(round((b[3]+20)*EMU)))
        if layout=='L2' and abs(b[1]-109)<1:off.set('x',str(round((b[0]-16)*EMU)));ext.set('cx',str(round((b[2]+16)*EMU)))
        if layout=='L2' and abs(b[1]-416)<1:off.set('x',str(round((b[0]+12)*EMU)));ext.set('cx',str(round((b[2]-24)*EMU)))
        if layout=='L8' and abs(b[1]-476)<1:off.set('y',str(466*EMU));ext.set('cy',str(44*EMU))
        if layout=='L8' and abs(b[1]-214)<1:
            off.set('y',str(207*EMU));ext.set('cy',str(48*EMU));off.set('x',str(round((b[0]-6)*EMU)));ext.set('cx',str(round((b[2]+12)*EMU)))
        if layout=='L3' and abs(b[1]-621)<1:off.set('y',str(617*EMU));ext.set('cy',str(31*EMU))
        if layout=='L10' and abs(b[0]-510)<1 and abs(b[1]-455)<1:off.set('y',str(450*EMU));ext.set('cy',str(61*EMU))
        if layout=='L13' and abs(b[2]-128)<1:off.set('y',str(round((b[1]-5)*EMU)));ext.set('cy',str(34*EMU))
        if layout=='L13' and abs(b[2]-132)<1:
            off.set('x',str(29*EMU));ext.set('cx',str(143*EMU));off.set('y',str(round((b[1]-11)*EMU)));ext.set('cy',str(47*EMU))
            for paragraph in sp.findall('p:txBody/a:p',NS):
                run=paragraph.find('a:r',NS)
                if run is not None:
                    t=run.find('a:t',NS)
                    if t is not None and (t.text or '').startswith('回答'):
                        tail=copy.deepcopy(run);tail.find('a:t',NS).text=t.text[2:];t.text=t.text[:2]
                        idx=list(paragraph).index(run);paragraph.insert(idx+1,E.Element(q('a','br')));paragraph.insert(idx+2,tail)
        if b[1]>=690:ext.set('cy',str(20*EMU))
    for table in root.findall('.//a:tbl',NS):
        for rp in table.findall('.//a:rPr',NS)+table.findall('.//a:defRPr',NS):
            if rp.get('sz'):
                old=int(rp.get('sz'))/75;rp.set('sz',str(round((old+2 if old>=18 else old+3)*75)))
    # Transform the entire content grid, including attached connector frames.
    # Cover/navigation/closing compositions retain their intentional full bleed.
    if layout not in ['L5','L6','L7','L14']:
        scale=1216/1232
        for xf in root.findall('.//p:spPr/a:xfrm',NS)+root.findall('.//p:xfrm',NS):
            off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
            if off is not None:off.set('x',str(round((32+(int(off.get('x'))/EMU-24)*scale)*EMU)))
            if ext is not None:ext.set('cx',str(round(int(ext.get('cx'))*scale)))
        for col in root.findall('.//a:tblGrid/a:gridCol',NS):col.set('w',str(round(int(col.get('w'))*scale)))

def chart_typography(root):
    for rp in root.findall('.//a:rPr',NS)+root.findall('.//a:defRPr',NS):
        if rp.get('sz'):rp.set('sz',str(max(1275,int(rp.get('sz'))+150)))
        for tag in ['latin','ea','cs']:
            font=rp.find('a:'+tag,NS)
            if font is not None:font.set('typeface','Noto Sans CJK SC')
    ns={**NS,'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    plot=root.find('.//c:plotArea/c:layout/c:manualLayout',ns)
    if plot is not None:
        height=plot.find('c:h',ns)
        if height is not None:height.set('val',str(round(float(height.get('val'))-.055,3)))
        # Reserve measured space for larger tick labels beside a vertical title.
        if root.find('.//c:valAx/c:title',ns) is not None:
            x=plot.find('c:x',ns);w=plot.find('c:w',ns)
            if x is not None and w is not None:
                x.set('val',str(round(float(x.get('val'))+.03,3)));w.set('val',str(round(float(w.get('val'))-.03,3)))

def apply(root,layout,palette):
    primary=palette['primary'][1:];secondary=palette['secondary'][1:];tint=palette['tint'][1:]
    tree=root.find('p:cSld/p:spTree',NS);shapes=list(tree.findall('p:sp',NS))
    dark=[];ids=[int(n.get('id')) for n in root.findall('.//p:cNvPr',NS)];nextid=max(ids,default=1)+1
    def dark_at(b):
        if any(center_inside(b,area) for area in dark):return True
        if layout=='L1':
            d=((b[0]+b[2]/2-640)**2+(b[1]+b[3]/2-373)**2)**.5
            return 106<d<202
        return False
    def name(sp):return sp.find('p:nvSpPr/p:cNvPr',NS).get('name','')
    def hastext(sp):return bool(sp.findall('.//a:t',NS))
    def rectangle(anchor,x,y,w,h):
        nonlocal nextid
        sp=E.Element(q('p','sp'));nv=E.SubElement(sp,q('p','nvSpPr'));E.SubElement(nv,q('p','cNvPr'),id=str(nextid),name='solid-title-band-'+str(nextid));nextid+=1
        E.SubElement(nv,q('p','cNvSpPr'));E.SubElement(nv,q('p','nvPr'));pr=E.SubElement(sp,q('p','spPr'));xf=E.SubElement(pr,q('a','xfrm'))
        E.SubElement(xf,q('a','off'),x=str(round(x*EMU)),y=str(round(y*EMU)));E.SubElement(xf,q('a','ext'),cx=str(round(w*EMU)),cy=str(round(h*EMU)))
        geom=E.SubElement(pr,q('a','prstGeom'),prst='rect');E.SubElement(geom,q('a','avLst'));fill(pr,primary)
        region=(x,y,w,h)
        front=next((s for s in tree if s.tag==q('p','sp') and box(s) and center_inside(box(s),region) and box(s)[3]<80),anchor)
        tree.insert(list(tree).index(front),sp);dark.append(region);return sp
    # Existing title strips, diagram nodes, and strong navigation areas.
    for sp in shapes:
        b=box(sp)
        if not b or hastext(sp):continue
        x,y,w,h=b;pr=sp.find('p:spPr',NS);color=pr.find('a:solidFill/a:srgbClr',NS);c=color.get('val') if color is not None else None
        isbar=w>200 and 28<=h<=46 and c==tint
        isnode=name(sp).startswith('node-')
        islane=layout=='L13' and abs(w-153)<2 and abs(h-155)<2
        if isbar or isnode or islane:
            fill(pr,primary);stroke(sp,primary,1.5);dark.append(b)
            geom=pr.find('a:prstGeom',NS)
            if geom is not None and not isnode:geom.set('prst','rect')
        elif w>200 and h>90 and c in ['FFFFFF',tint] and y>80 and pr.find('a:prstGeom',NS) is not None and pr.find('a:prstGeom',NS).get('prst') in ['rect','roundRect']:
            fill(pr,'FFFFFF');stroke(sp,primary,1.2)
            geom=pr.find('a:prstGeom',NS)
            if geom is not None:geom.set('prst','rect')
        elif c==primary and w*h>3000:
            geom=pr.find('a:prstGeom',NS)
            if geom is not None and geom.get('prst') in ['rect','roundRect']:dark.append(b)
    if layout=='L2':
        for sp in shapes:
            b=box(sp)
            if b and hastext(sp) and abs(b[1]-109)<1 and abs(b[3]-35)<1:
                rectangle(sp,b[0]-83,96,383,48)
            if b and hastext(sp) and abs(b[1]-416)<1 and abs(b[3]-30)<1:
                rectangle(sp,b[0]-2,412,574,38)
        # Heading icon clusters shrink to 32px; other icons stay unchanged.
        for sp in shapes:
            b=box(sp)
            if not b or hastext(sp):continue
            for i in range(3):
                area=(91+397*i,109,49,49)
                if inside(b,area,.1):
                    xf=sp.find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
                    off.set('x',str(round((area[0]+(b[0]-area[0])*32/49)*EMU)));off.set('y',str(round((104+(b[1]-area[1])*32/49)*EMU)))
                    ext.set('cx',str(round(b[2]*32/49*EMU)));ext.set('cy',str(round(b[3]*32/49*EMU)))
    # Identify existing white-on-primary zones, then make each label legible.
    for sp in shapes:
        b=box(sp)
        if b and hastext(sp) and any(center_inside(b,area) for area in dark):text_color(sp,'FFFFFF')
    # Opaque icon silhouettes. Nested primitives form contrasting cutouts.
    icons=[sp for sp in shapes if box(sp) and (name(sp).startswith('icon-') or name(sp).startswith('vector-') and box(sp)[2]<=110 and box(sp)[3]<=110)]
    closed=[]
    for sp in icons:
        geom=sp.find('p:spPr/a:prstGeom',NS)
        if geom is not None and geom.get('prst') not in ['line','arc'] or sp.find('.//a:custGeom/a:pathLst/a:path/a:close',NS) is not None:closed.append(sp)
    for sp in icons:
        b=inkbox(sp);on_dark=dark_at(b);fg='FFFFFF' if on_dark else primary
        containers=[outer for outer in closed if outer is not sp and inkbox(outer)[2]*inkbox(outer)[3]>b[2]*b[3]*2 and inside(b,inkbox(outer),.1)]
        parent=min(containers,key=lambda s:inkbox(s)[2]*inkbox(s)[3]) if containers else None
        color=primary if on_dark else 'FFFFFF' if parent is not None else fg
        if parent is None:color=fg
        else:
            parent_fill=parent.find('p:spPr/a:solidFill/a:srgbClr',NS)
            color=primary if parent_fill is not None and parent_fill.get('val')=='FFFFFF' else 'FFFFFF'
        if sp in closed:fill(sp.find('p:spPr',NS),color)
        stroke(sp,color,2.1)
        path=sp.find('.//a:custGeom/a:pathLst/a:path',NS)
        if sp in closed and path is not None and len(path.findall('.//a:pt',NS))==4 and abs(box(sp)[3]/box(sp)[2]-.5)<.02:stroke(sp,primary if on_dark else 'FFFFFF',1.3)
    # Other icon paths and lines inside dark nodes must also use white ink.
    for sp in shapes:
        b=box(sp)
        if not b or hastext(sp) or sp in icons:continue
        if name(sp).startswith(('vector-','line-')) and b[2]<=110 and b[3]<=110:
            pr=sp.find('p:spPr',NS)
            on_dark=any(inside(b,area) for area in dark)
            enclosing=next((outer for outer in closed if inside(b,box(outer),.1) and box(outer)[2]*box(outer)[3]>b[2]*b[3]*2),None)
            color=(primary if on_dark else 'FFFFFF') if enclosing is not None else ('FFFFFF' if on_dark else primary)
            if on_dark or enclosing is not None:
                if pr.find('a:solidFill',NS) is not None:fill(pr,color)
                if pr.find('a:ln/a:solidFill',NS) is not None:stroke(sp,color,2.1)
    for sp in tree.findall('p:cxnSp',NS):
        line=sp.find('p:spPr/a:ln',NS)
        if line is not None:line.set('w',str(round(2.6*EMU)))
    typography(root,layout)
