"""Evidence-first layouts and editable annotations. Standard library only."""
from pathlib import Path
import hashlib
import json
import math
import re
import xml.etree.ElementTree as E

NEW = {'L15', 'L16', 'L17', 'L18', 'L19', 'L20'}
VARIANTS = {
    'L3': ['default', 'swap_columns'], 'L9': ['default', 'swap_columns'],
    'L11': ['default', 'swap_rows'],
    'L15': ['default', 'figure_left'], 'L16': ['default', 'figure_right', 'full_width'],
    'L17': ['default', 'detail_left'], 'L18': ['default', 'map_right'],
    'L19': ['default', 'two_groups'], 'L20': ['default', 'table_full'],
}
for _layout in ['L2', 'L3', 'L4', 'L8', 'L9', 'L10', 'L11']:
    VARIANTS.setdefault(_layout, ['default']).append('original_figure')


def check(ok, message):
    if not ok:
        raise ValueError(message)


def path_of(filename, base):
    p = Path(filename)
    return p if p.is_absolute() else Path(base) / p


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def validate(document, base):
    """A declared relevant paper requires a verified, actually used original crop."""
    if document['demo']:
        return
    materials = document.get('materials')
    check(isinstance(materials, dict) and isinstance(materials.get('papers'), list),
          'Formal decks require materials.papers inventory; use [] only when no papers were supplied')
    papers = {}
    for p in materials['papers']:
        check(isinstance(p, dict) and p.get('id') and p['id'] not in papers, 'Paper IDs must be unique')
        check(p.get('figure_status') in ['relevant', 'none', 'unavailable'], 'Declare paper figure_status')
        check(p['figure_status'] != 'unavailable', 'Paper original unavailable: formal delivery blocked')
        if p['figure_status'] == 'none':
            check(bool(p.get('reason')), 'Explain why this paper has no relevant figures')
        else:
            check(bool(p.get('path')) and path_of(p['path'], base).is_file(), 'Relevant paper PDF is missing')
        papers[p['id']] = p
    used = set()
    for page in document['slides']:
        for fig in page.get('figures', []):
            check(isinstance(fig, dict), 'Each figure must be an object')
            if fig.get('kind') != 'paper_crop':
                continue
            prov = fig.get('provenance', {})
            pid = prov.get('paper_id')
            check(pid in papers and papers[pid]['figure_status'] == 'relevant', 'Unknown/rejected paper source')
            check(page['layout'] in NEW - {'L19', 'L20'} or page.get('variant') == 'original_figure',
                  'Paper crops must use a figure-bearing layout')
            check(fig.get('caption') and fig.get('source'), 'Paper crop needs visible caption and source')
            check(prov.get('verified_complete') is True and prov.get('page', 0) >= 1 and prov.get('figure'),
                  'Verify complete original figure, page and figure number')
            check(len(prov.get('crop_bbox', [])) == 4, 'Record PDF crop rectangle')
            check(prov.get('pdf_sha256') == digest(path_of(papers[pid]['path'], base)),
                  'Original PDF hash mismatch')
            check(prov.get('png_sha256') == digest(path_of(fig['path'], base)), 'Crop PNG hash mismatch')
            check(prov.get('render_method') == 'pdf_clip', 'Paper image must be a direct PDF crop')
            check(not page.get('duotone', document.get('duotone', False)), 'Paper crops must preserve original color')
            used.add(pid)
    missing = [pid for pid, p in papers.items() if p['figure_status'] == 'relevant' and pid not in used]
    check(not missing, 'Missing original paper figure crops: ' + ', '.join(missing))


def audit_embedded(archive, ns):
    """Check that declared paper crops survive as unfiltered, uncropped PPT media."""
    import posixpath
    import re
    errors, required, used = [], set(), set()
    for name in archive.namelist():
        if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml',name):
            root=E.fromstring(archive.read(name))
            for el in root.findall('.//a:t',ns):
                if not (el.text or '').startswith('EVIDENCE_MANIFEST: '):continue
                data=json.loads(el.text.split(': ',1)[1])
                for p in data.get('materials',{}).get('papers',[]):
                    if p.get('figure_status')=='relevant':required.add(p['id'])
        if not re.fullmatch(r'ppt/slides/slide\d+\.xml',name):continue
        root=E.fromstring(archive.read(name))
        relname=posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
        rels={r.get('Id'):r.get('Target') for r in E.fromstring(archive.read(relname))}
        for pic in root.findall('.//p:pic',ns):
            nv=pic.find('p:nvPicPr/p:cNvPr',ns)
            desc=nv.get('descr','')
            if not desc.startswith('{'):continue
            data=json.loads(desc)
            if data.get('kind')!='paper_crop':continue
            # Zoom windows are supplementary; only the complete overview counts.
            if 'zoom-' in nv.get('name',''):continue
            blip=pic.find('p:blipFill/a:blip',ns)
            rid=blip.get('{'+ns['r']+'}embed')
            media=posixpath.normpath(posixpath.join(posixpath.dirname(name),rels[rid])).lstrip('/')
            prov=data['provenance']
            if hashlib.sha256(archive.read(media)).hexdigest()!=prov.get('png_sha256'):
                errors.append(name+': paper figure bytes differ from verified crop')
            elif pic.find('p:blipFill/a:srcRect',ns) is not None or len(blip):
                errors.append(name+': original figure has PPT cropping or color effects')
            else:used.add(prov.get('paper_id'))
    if required-used:errors.append('Missing embedded original figures: '+', '.join(sorted(required-used)))
    return errors


def apply_variant(root, page, g):
    """Move whole columns/rows without reflecting glyphs or changing data."""
    variant = page.get('variant', 'default')
    if variant == 'default':
        return
    layout = page['layout']
    check(variant in VARIANTS.get(layout, []), f'{layout}: unsupported variant {variant}')
    ns = g.NS
    tree = root.find('p:cSld/p:spTree', ns)
    for el in tree:
        xf = el.find('p:spPr/a:xfrm', ns)
        if xf is None:
            xf = el.find('p:xfrm', ns)
        if xf is None:
            continue
        off, ext = xf.find('a:off', ns), xf.find('a:ext', ns)
        if off is None or ext is None:
            continue
        x, y = int(off.get('x')) / g.EMU, int(off.get('y')) / g.EMU
        w, h = int(ext.get('cx')) / g.EMU, int(ext.get('cy')) / g.EMU
        if variant == 'swap_columns':
            left_end,right_start,delta,top,bottom = ((566,714,683,110,486) if layout=='L3' else (633,647,616,92,494))
            if y >= top and y+h <= bottom:
                if x+w <= left_end:off.set('x',str(round((x+delta)*g.EMU)))
                elif x >= right_start:off.set('x',str(round((x-delta)*g.EMU)))
        elif variant == 'swap_rows' and w <= 602:
            # Include header strips and the native chart frames as one panel.
            if y >= 92 and y+h <= 355:
                off.set('y', str(round((y + 274) * g.EMU)))
            elif y >= 366 and y+h <= 629:
                off.set('y', str(round((y - 274) * g.EMU)))
    if variant=='swap_columns':
        for table in root.findall('.//a:tbl',ns):
            for row in table.findall('a:tr',ns):
                cells=row.findall('a:tc',ns)
                if len(cells)!=3:continue
                order=[2,1,0] if layout=='L3' else [0,2,1]
                for cell in cells:row.remove(cell)
                for i in order:row.append(cells[i])


def components(root, page, palette, g, styler):
    """Opt-in shared native components; coordinates are 1280x720 canvas pixels."""
    items = page.get('components', [])
    check(isinstance(items, list), 'components must be a list')
    c = Canvas.__new__(Canvas)
    c.tree = root.find('p:cSld/p:spTree', g.NS)
    c.i = max(int(el.get('id')) for el in root.findall('.//p:cNvPr', g.NS)) + 1
    c.s = styler
    c.p, c.a, c.tint = (palette[k].lstrip('#') for k in ['primary','accent','tint'])
    for item in items:
        kind, box = item.get('type'), item.get('box', [])
        check(len(box)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in box),
              'Component box must be [x,y,width,height]')
        x,y,w,h=box
        check(x>=0 and y>=0 and w>0 and h>0 and x+w<=1280 and y+h<=720,'Component outside canvas')
        if kind=='zoom_frame':
            c.rect('component-zoom-frame',*box,stroke=c.a)
        elif kind in {'figure_number','caption','source','number','navigation'}:
            size = 17 if kind=='source' else 20
            c.text('component-'+kind,item['text'],*box,size=size,
                   color=c.a if kind=='number' else c.p,bold=kind in {'figure_number','number','navigation'})
            if kind=='navigation' and item.get('active'):
                c.rect('component-nav-indicator',x,y+h-2,w,2,fill=c.a)
        else:
            raise ValueError('Unknown component type: '+str(kind))


class Canvas:
    def __init__(self, root, rels, parts, counters, palette, g, styler):
        self.g, self.s, self.parts, self.rels, self.counters = g, styler, parts, rels, counters
        self.tree = root.find('p:cSld/p:spTree', g.NS)
        for el in list(self.tree)[2:]:
            self.tree.remove(el)
        # Remove template content; keep the slide layout and notes relationships.
        for rel in list(rels):
            if not rel.get('Type', '').endswith(('/slideLayout', '/notesSlide')):
                rels.remove(rel)
        self.i = 10
        self.p, self.a, self.tint = (palette[k].lstrip('#') for k in ['primary', 'accent', 'tint'])
        self.rect('canvas', 0, 0, 1280, 720, fill='FFFFFF')

    def rect(self, name, x, y, w, h, fill=None, stroke=None, prst='rect'):
        self.i += 1
        sp = self.s.make_shape(self.i, name, x, y, w, h, fill_clr=fill, stroke_clr=stroke, prst=prst)
        self.tree.append(sp)
        return sp

    def text(self, name, text, x, y, w, h, size=22, color=None, bold=False, align='l'):
        check(isinstance(text, (str, int, float)), f'{name}: expected text')
        # Fail rather than shrinking or silently truncating content.
        lines = sum(max(1, math.ceil(sum(size * (1.03 if ord(c) > 127 else .58) for c in ln) / (w + 6)))
                    for ln in str(text).split('\n'))
        check(lines * size * 1.18 <= h + 6, f'{name}: text exceeds region; shorten or split page')
        self.i += 1
        sp = self.s.make_text_shape(self.i, name, x, y, w, h, text, sz_px=size, color=color or self.p,
                                   bold=bold, align=align, anchor='t')
        self.tree.append(sp)
        return sp

    def image(self, fig, box, base, slot, crop=None):
        g = self.g
        data = path_of(fig['path'], base).read_bytes()
        iw, ih = g.png_dimensions(data)
        x, y, w, h = box
        if crop:
            l, t, r, b = crop
            check(0 <= l < r <= 1 and 0 <= t < b <= 1, 'Zoom rectangle must be normalized [left,top,right,bottom]')
            iw, ih = iw * (r-l), ih * (b-t)
        ratio = min(w / iw, h / ih)
        actual = (x + (w-iw*ratio)/2, y + (h-ih*ratio)/2, iw*ratio, ih*ratio)
        self.counters['image'] += 1
        n = self.counters['image']
        media = f'ppt/media/evidence_{n}.png'
        self.parts[media] = data
        rid = f'evidenceImage{n}'
        E.SubElement(self.rels, '{'+g.REL+'}Relationship', Id=rid, Type=g.NS['r']+'/image', Target='/'+media)
        pic = E.SubElement(self.tree, g.q('p','pic'))
        nv = E.SubElement(pic, g.q('p','nvPicPr'))
        self.i += 1
        E.SubElement(nv, g.q('p','cNvPr'), id=str(self.i), name=f'evidence-{slot}',
                     descr=json.dumps({'kind':fig.get('kind','user_image'), 'provenance':fig.get('provenance',{}),
                                       'sha256':hashlib.sha256(data).hexdigest()}, ensure_ascii=False))
        locks = E.SubElement(nv, g.q('p','cNvPicPr'))
        E.SubElement(locks,g.q('a','picLocks'),noChangeAspect='1')
        E.SubElement(nv,g.q('p','nvPr'))
        bf = E.SubElement(pic,g.q('p','blipFill'))
        E.SubElement(bf,g.q('a','blip'),{g.q('r','embed'):rid})
        if crop:
            E.SubElement(bf,g.q('a','srcRect'),l=str(round(l*100000)),t=str(round(t*100000)),
                         r=str(round((1-r)*100000)),b=str(round((1-b)*100000)))
        E.SubElement(E.SubElement(bf,g.q('a','stretch')),g.q('a','fillRect'))
        pr = E.SubElement(pic,g.q('p','spPr'))
        xf = E.SubElement(pr,g.q('a','xfrm'))
        ax,ay,aw,ah = actual
        E.SubElement(xf,g.q('a','off'),x=str(round(ax*g.EMU)),y=str(round(ay*g.EMU)))
        E.SubElement(xf,g.q('a','ext'),cx=str(round(aw*g.EMU)),cy=str(round(ah*g.EMU)))
        E.SubElement(E.SubElement(pr,g.q('a','prstGeom'),prst='rect'),g.q('a','avLst'))
        return actual

    def figure(self, fig, box, base, slot):
        x,y,w,h = box
        actual = self.image(fig,(x,y,w,h-64),base,slot)
        # Caption/source are outside the original image and remain editable.
        ax,ay,aw,ah=actual
        self.text('figure-number-caption',fig['caption'],ax,ay+ah+8,aw,28,20,bold=True)
        self.text('figure-source',fig['source'],ax,ay+ah+38,aw,25,17,color='526475')
        self.rect('image-boundary',*actual,stroke='C3D2E0')
        return actual


def build_composition(c,page,base_dir,palette):
    """Native content-driven variation, with the same complete-figure evidence gate."""
    nodes=page['composition']
    check(isinstance(nodes,list) and 1<=len(nodes)<=500,'composition needs 1 to 500 native objects')
    check(page['layout'] in {'L15','L16','L17','L18'},'composition uses a figure-capable L15-L18 layout')
    texts=[];used=set();figures=page.get('figures',[])
    theme={k:palette[k].lstrip('#') for k in ['primary','secondary','accent','paper','tint']}
    color=lambda value:theme.get(value,value)
    check(isinstance(figures,list),'figures must be an array')
    for i,node in enumerate(nodes):
        check(isinstance(node,dict),f'composition[{i}] must be an object')
        kind=node.get('kind');box=node.get('box')
        check(isinstance(box,list) and len(box)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in box),f'composition[{i}].box needs four finite numbers')
        x,y,w,h=box
        check(x>=0 and y>=0 and w>0 and h>0 and x+w<=1280 and y+h<=720,f'composition[{i}] is outside the slide')
        common={'kind','name','box'}
        allowed=common|({'text','size','color','bold','align'} if kind=='text' else {'fill','stroke','prst'} if kind=='shape' else {'figure_index','slot'} if kind=='image' else set())
        check(kind in {'text','shape','image'} and not set(node)-allowed,f'composition[{i}] has unknown kind/fields')
        name=node.get('name',f'object-{i+1}')
        check(isinstance(name,str) and name.strip(),f'composition[{i}] needs a name')
        for key in ['fill','stroke','color']:
            value=node.get(key)
            check(value is None or isinstance(value,str) and (value in theme or re.fullmatch('[0-9A-Fa-f]{6}',value)),f'composition[{i}].{key} needs a six-digit RGB color, palette token or null')
        if kind=='text':
            size=node.get('size',22)
            check(type(size) in (int,float) and math.isfinite(size) and 13<=size<=80,'composition text size must be 13 to 80px; preserve approved hierarchy')
            check(isinstance(node.get('text'),str) and type(node.get('bold',False)) is bool and node.get('align','l') in {'l','ctr','r'},'Invalid composition text/bold/alignment')
            texts.append(node['text'])
            c.text(name,node['text'],*box,size=size,color=color(node.get('color')),bold=node.get('bold',False),align=node.get('align','l'))
        elif kind=='shape':
            prst=node.get('prst','rect')
            check(prst in {'rect','roundRect','ellipse','rightArrow','downArrow','upArrow','chevron','triangle','diamond','hexagon','parallelogram'},'Unsupported native shape preset')
            c.rect(name,*box,fill=color(node.get('fill')),stroke=color(node.get('stroke')),prst=prst)
        else:
            ix=node.get('figure_index')
            check(type(ix) is int and 0<=ix<len(figures),'composition image refers to missing figure index')
            fig=figures[ix]
            check(isinstance(fig,dict) and all(isinstance(fig.get(k),str) and fig[k].strip() for k in ['path','caption','source']),'Image requires path/caption/source')
            slot=node.get('slot',f'figure-{ix+1}')
            check(isinstance(slot,str) and slot.strip() and not slot.startswith('zoom-'),'composition uses complete original figures, not a crop substitute')
            c.image(fig,box,base_dir,slot);used.add(ix)
    check(page['title'] in texts,'composition must visibly include the page title as native text')
    check(used==set(range(len(figures))),'Every declared figure must actually appear in composition')
    for fig in figures:
        check(fig['caption'] in texts and fig['source'] in texts,'composition must include separate visible native caption and source for every image')


def build(root, rels, parts, counters, page, document, palette, g, styler, base_dir, index):
    c = Canvas(root,rels,parts,counters,palette,g,styler)
    if 'composition' in page:
        build_composition(c,page,base_dir,palette)
        return c
    layout, variant = page['layout'], page.get('variant','default')
    check(variant in VARIANTS[layout], f'{layout}: unknown variant')
    c.text('title',page['title'],32,20,1216,58,42,bold=True)
    c.rect('header-rule',32,86,1216,2,fill=c.p)
    c.text('takeaway',page.get('takeaway',''),48,642,1184,32,23,bold=True)
    c.rect('takeaway-rule',32,632,1216,2,fill=c.p)
    chapters = page.get('navigation',document.get('navigation',{}))
    if chapters:
        labels, active = chapters.get('labels',[]), chapters.get('active',page.get('chapter',0))
        check(1 <= len(labels) <= 6 and isinstance(active,int) and 0 <= active < len(labels), 'Invalid navigation')
        for j,label in enumerate(labels):
            x = 32 + j*168
            c.text('chapter-navigation',label,x,686,156,24,14,bold=j==active,color=c.p if j==active else '667788')
            if j==active:c.rect('chapter-indicator',x,681,100,3,fill=c.a)
    else:
        c.text('footer', '模板示意 · 非真实研究数据' if document['demo'] else document.get('footer',''),32,690,1120,22,14)
    c.text('page-number',f'{index:02}',1206,686,42,24,14,align='r')
    figures = page.get('figures',[])
    for fig in figures:
        check(isinstance(fig,dict) and all(fig.get(k) for k in ['path','caption','source']), 'Figure needs path/caption/source')

    def notes(items,x,y,w,step=142):
        check(1 <= len(items) <= 3,'Use one to three concise explanation sections')
        for j,item in enumerate(items):
            yy=y+j*step
            c.text('section-number',f'{j+1:02}',x,yy,42,30,22,color=c.a,bold=True)
            c.text('section-title',item['title'],x+52,yy,w-52,35,25,bold=True)
            c.text('section-body',item['body'],x+52,yy+45,w-52,step-53,21,color='263746')
            if j<len(items)-1:c.rect('section-rule',x,yy+step-15,w,1,fill='D5DFE8')

    if layout in {'L15','L16','L18'}:
        check(len(figures)==1, f'{layout} requires exactly one complete main figure')
        if layout=='L16' and variant=='full_width':
            c.figure(figures[0],(32,104,1216,510),base_dir,'main')
        else:
            figure_left = layout!='L15'
            if variant in {'figure_left','figure_right','map_right'}:figure_left=not figure_left
            fw = 830 if layout in {'L16','L18'} else 800
            fx, nx, nw = (32,32+fw+32,1216-fw-32) if figure_left else (32+1216-fw,32,1216-fw-32)
            c.figure(figures[0],(fx,108,fw,508),base_dir,'main')
            notes(page['sections'],nx,124,nw,156)
    elif layout=='L17':
        check(len(figures)==1,'L17 uses a single original image for overview AND all zooms')
        mainx, detailx = (470,32) if variant=='detail_left' else (32,870)
        actual=c.figure(figures[0],(mainx,110,778,506),base_dir,'overview')
        zooms=page.get('zooms',[])
        check(1<=len(zooms)<=2,'L17 supports one or two zoom windows')
        ax,ay,aw,ah=actual
        for j,z in enumerate(zooms):
            yy=110+j*254
            c.text('zoom-label',f'{j+1}  '+z['label'],detailx,yy,378,30,22,bold=True)
            detail=c.image(figures[0],(detailx,yy+40,378,196),base_dir,f'zoom-{j+1}',z['rect'])
            l,t,r,b=z['rect']
            check(detail[2] > (r-l)*aw, 'Zoom window must enlarge the selected region; narrow the selection or use a separate full-width page')
            c.rect('editable-zoom-frame',ax+l*aw,ay+t*ah,(r-l)*aw,(b-t)*ah,stroke=c.a)
            # Mark outside the image: no obscuring original labels.
            c.text('zoom-number',str(j+1),detailx,yy+213,28,23,17,color=c.a,bold=True)
    elif layout=='L19':
        check(not figures,'L19 does not accept figure images; use L16 or original_figure')
        groups, times=page.get('groups',[]),page.get('times',[])
        check(len(groups)==(2 if variant=='two_groups' else 3),'L19 group count does not match variant')
        check(2<=len(times)<=6,'Use two to six time points')
        x0,x1=282,1200
        for j,t in enumerate(times):
            x=x0+(x1-x0)*j/(len(times)-1)
            c.text('time-label',t,x-50,112,100,32,22,bold=True,align='ctr')
        rowh=380/len(groups)
        for i,group in enumerate(groups):
            y=163+i*rowh
            c.rect('timeline-lane',32,y,1216,rowh-14,fill=c.tint)
            c.rect('group-fill',32,y,198,rowh-14,fill=c.a if i==len(groups)-1 else c.p)
            c.text('group-label',group['name'],48,y+18,162,37,26,color='FFFFFF',bold=True)
            c.text('group-sample',group['sample'],48,y+62,162,32,21,color='FFFFFF')
            check(len(group['events'])==len(times),'Events must align with time points')
            c.rect('timeline-line',x0,y+30,x1-x0,2,fill=c.p)
            for j,event in enumerate(group['events']):
                x=x0+(x1-x0)*j/(len(times)-1)
                c.rect('time-node',x-5,y+26,10,10,fill=c.p,prst='ellipse')
                c.text('event-label',event,x-64,y+49,128,rowh-70,20,align='ctr')
        c.text('measurement',page['measurement'],32,566,1216,48,23)
    elif layout=='L20':
        check(not figures,'L20 does not accept figure images; use L16 or original_figure')
        matrix=page.get('matrix',[])
        check(2<=len(matrix)<=5 and all(len(row)==4 for row in matrix),'L20 needs header + 1..4 rows, four columns')
        w=1216 if variant=='table_full' else 890
        widths=[.17*w,.23*w,.32*w,.28*w]
        yy=112
        for ri,row in enumerate(matrix):
            x=32
            rh=64 if ri==0 else 104
            for col,txt in enumerate(row):
                c.rect('matrix-cell',x,yy,widths[col],rh,fill=c.p if ri==0 else (c.tint if col==0 else 'FFFFFF'),stroke='D4DFE9')
                c.text('matrix-cell-text',txt,x+12,yy+16,widths[col]-24,rh-24,21 if ri==0 else 20,
                       color='FFFFFF' if ri==0 else c.p,bold=ri==0 or col==0)
                x+=widths[col]
            yy+=rh
        if variant!='table_full':notes(page['sections'],958,130,290,156)
    return c
