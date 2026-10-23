#!/usr/bin/env python3
"""Portable native PPTX template filling. Python 3.10+, standard library only.

The approved layout is the source of geometry. Supports both legacy demo mode
(byte-identical to v1.1 examples) and adaptive visual mode (default when demo=false),
which removes stiff duplicate icons/stock illustrations, adapts icons and native cards
to the user's materials, normalizes table typography, and supports per-slide figures.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, io, json, math, os, posixpath, re, tempfile, zipfile
from pathlib import Path
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parent.parent
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
EMU=9525
for prefix,uri in NS.items():E.register_namespace(prefix,uri)
def q(prefix,name):return '{'+NS[prefix]+'}'+name
def xml(root):
    if root.tag.endswith(('}Relationships','}Types')):E.register_namespace('',root.tag[1:].split('}')[0])
    return E.tostring(root,encoding='utf-8',xml_declaration=True)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise ValueError(message)
def get(obj,path):
    for key in path.split('.'):obj=obj[int(key)] if isinstance(obj,list) else obj[key]
    return obj
def relpart(part):return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels') if part else '_rels/.rels'
def resolve(owner,target):return posixpath.normpath(posixpath.join(posixpath.dirname(owner),target)).lstrip('/')
def readzip(path):
    with zipfile.ZipFile(path) as z:return {n:z.read(n) for n in z.namelist()}
def zipbytes(parts):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(parts.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    return output.getvalue()
def text_content(body):return '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in body.findall('a:p',NS))
def visual_len(text):return sum(2.0 if ord(c)>127 else 1.15 for c in str(text))
def set_text(body,value,emphasis=(),accent='AF3D3D'):
    value=str(value)
    paras=body.findall('a:p',NS);first=paras[0] if paras else E.Element(q('a','p'))
    props=first.find('a:pPr',NS);runprops=first.find('a:r/a:rPr',NS)
    if runprops is None:runprops=E.Element(q('a','rPr'))
    for p in paras:body.remove(p)
    terms=sorted(set(t for t in emphasis if isinstance(t,str) and t),key=len,reverse=True)
    pattern='('+'|'.join(re.escape(t) for t in terms)+')' if terms else None
    for line in value.split('\n'):
        para=E.SubElement(body,q('a','p'))
        if props is not None:para.append(copy.deepcopy(props))
        for piece in re.split(pattern,line) if pattern else [line]:
            if not piece:continue
            run=E.SubElement(para,q('a','r'));rp=copy.deepcopy(runprops)
            if piece in terms:
                for fill in rp.findall('a:solidFill',NS):rp.remove(fill)
                E.SubElement(E.SubElement(rp,q('a','solidFill')),q('a','srgbClr'),val=accent);rp.set('b','1')
            run.append(rp);E.SubElement(run,q('a','t')).text=piece
        E.SubElement(para,q('a','endParaRPr'))
def mix(a,b,t):
    def jsround(v):return math.floor(v+.5)
    return ''.join(f'{jsround(int(a[i:i+2],16)*(1-t)+int(b[i:i+2],16)*t):02X}' for i in (0,2,4))
def color_map(old,new):
    m={old[k].lstrip('#').upper():new[k].lstrip('#').upper() for k in ['primary','secondary','accent','tint']}
    for t in [.17,.34,.51,.83]:m[mix(old['primary'][1:],'FFFFFF',t)]=mix(new['primary'][1:],'FFFFFF',t)
    return m
def recolor(root,palette,system,*,allow_duotone=True):
    mapping=color_map(system['palettes']['P1'],palette)
    for el in root.iter(q('a','srgbClr')):
        if el.get('val','').upper() in mapping:el.set('val',mapping[el.get('val').upper()])
    bg=root.find('p:cSld/p:bg/p:bgPr/a:solidFill/a:srgbClr',NS)
    if bg is not None:bg.set('val',palette['paper'][1:])
    for blip in root.findall('.//p:pic/p:blipFill/a:blip',NS):
        for duo in blip.findall('a:duotone',NS):blip.remove(duo)
        if allow_duotone and palette['primary']!=system['palettes']['P1']['primary']:
            duo=E.SubElement(blip,q('a','duotone'));E.SubElement(duo,q('a','srgbClr'),val=palette['primary'][1:]);E.SubElement(duo,q('a','srgbClr'),val='FFFFFF')
def colname(index):
    out=''
    while index:index,n=divmod(index-1,26);out=chr(65+n)+out
    return out
def number(v):
    require(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v),'Chart values must be finite numbers')
    return format(v,'.15g')
def workbook(columns):
    root=E.Element(q('s','worksheet'));data=E.SubElement(root,q('s','sheetData'))
    for row in range(max(len(v) for _,v in columns)+1):
        el=E.SubElement(data,q('s','row'),r=str(row+1))
        for i,(name,values) in enumerate(columns,1):
            if row and row>len(values):continue
            value=name if row==0 else values[row-1];cell=E.SubElement(el,q('s','c'),r=f'{colname(i)}{row+1}')
            if isinstance(value,(int,float)) and not isinstance(value,bool):E.SubElement(cell,q('s','v')).text=number(value)
            else:cell.set('t','inlineStr');E.SubElement(E.SubElement(cell,q('s','is')),q('s','t')).text=str(value)
    parts={'[Content_Types].xml':f'<Types xmlns="{CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'.encode(),
    '_rels/.rels':f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{NS["r"]}/officeDocument" Target="xl/workbook.xml"/></Relationships>'.encode(),
    'xl/workbook.xml':f'<workbook xmlns="{NS["s"]}" xmlns:r="{NS["r"]}"><sheets><sheet name="Chart Data" sheetId="1" r:id="rId1"/></sheets></workbook>'.encode(),
    'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{NS["r"]}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'.encode(),
    'xl/worksheets/sheet1.xml':xml(root)}
    return zipbytes(parts)
def cache(parent,values,numeric,formula=None):
    parent.clear();ref=E.SubElement(parent,q('c','numRef' if numeric else 'strRef')) if formula else parent
    if formula:E.SubElement(ref,q('c','f')).text=formula
    content=E.SubElement(ref,q('c',('numCache' if numeric else 'strCache') if formula else ('numLit' if numeric else 'strLit')))
    if numeric:E.SubElement(content,q('c','formatCode')).text='General'
    E.SubElement(content,q('c','ptCount'),val=str(len(values)))
    for i,v in enumerate(values):E.SubElement(E.SubElement(content,q('c','pt'),idx=str(i)),q('c','v')).text=number(v) if numeric else str(v)
def quartile(values,p):
    ordered=sorted(values);index=(len(ordered)-1)*p;lo=int(index);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)
def patch_chart(root,chart,base,*,adaptive=False):
    kind=chart['type'];require(kind==base['type'],'Chart type is fixed by the selected layout; choose another layout to change chart type')
    series=chart['series'];require(len(series)==len(base['series']),'Series count exceeds this layout capacity')
    for s in series:
        require(s.get('values'),'Empty chart series');[number(v) for v in s['values']]
    cats=chart.get('categories',[]);spec=[]
    if kind in ['line','bar','interval']:
        require(cats and all(len(s['values'])==len(cats) for s in series),'Chart category/data lengths differ')
    if kind=='box':
        require(all(len(s['values'])>=2 for s in series),'Box groups need at least two observations')
        qs=[[quartile(s['values'],p) for s in series] for p in [.25,.5,.75]];cats=[s['name'] for s in series]
        spec=[('Q1',cats,qs[0]),('Median minus Q1',cats,[round(b-a,10) for a,b in zip(qs[0],qs[1])]),('Q3 minus median',cats,[round(b-a,10) for a,b in zip(qs[1],qs[2])])]
    elif kind=='interval':
        low=chart['lower'];high=chart['upper'];require(len(low)==len(high)==len(cats),'Interval lengths differ')
        require(all(0<=a<=m<=b for a,m,b in zip(low,series[0]['values'],high)),'Interval must be nonnegative and enclose the first series')
        spec=[('Lower bound',cats,low),('Band width',cats,[round(b-a,10) for a,b in zip(low,high)])]+[(s['name'],cats,s['values']) for s in series]
    elif kind=='effects':
        require(len(chart['labels'])==len(base['labels'])==len(series[0]['values']),'Effect label count is fixed by the layout')
        spec=[(s['name'],s['values'],list(range(len(s['values']),0,-1))) for s in series]
        require(len(chart['errors'][0]['lower'])==len(chart['errors'][0]['upper'])==len(chart['labels']),'Effect interval lengths differ')
        require(all(a<=v<=b for a,v,b in zip(chart['errors'][0]['lower'],series[0]['values'],chart['errors'][0]['upper'])),'Effect intervals must enclose their points')
    elif kind=='scatter':
        for s in series:require(len(s['xValues'])==len(s['values']),'Scatter x/y lengths differ');[number(v) for v in s['xValues']]
        spec=[(s['name'],s['xValues'],s['values']) for s in series]
    else:spec=[(s['name'],cats,s['values']) for s in series]
    native=root.findall('.//c:ser',NS);require(len(native)==len(spec),'Native chart series mismatch')
    columns=[]
    strip_trend=chart.get('trendline') is False or (adaptive and not chart.get('trendline',False))
    for i,(ser,(name,x,y)) in enumerate(zip(native,spec)):
        if strip_trend:
            for tl in list(ser.findall('c:trendline',NS)):ser.remove(tl)
        tx=ser.find('c:tx',NS)
        if tx is not None:tx.clear();E.SubElement(tx,q('c','v')).text=name
        for label,values,isnum in [('xVal' if kind in ['scatter','effects'] else 'cat',x,kind in ['scatter','effects']),('yVal' if kind in ['scatter','effects'] else 'val',y,True)]:
            holder=ser.find('c:'+label,NS);require(holder is not None,'Missing native series values')
            columns.append((name+' '+label,values));column=colname(len(columns));cache(holder,values,isnum,f"'Chart Data'!${column}$2:${column}${len(values)+1}")
        errors=ser.find('c:errBars',NS)
        if errors is not None:
            if kind=='effects':plus=[round(b-v,10) for v,b in zip(x,chart['errors'][0]['upper'])];minus=[round(v-a,10) for v,a in zip(x,chart['errors'][0]['lower'])]
            elif kind=='box':
                plus=[round(max(s['values'])-q3,10) for s,q3 in zip(series,qs[2])] if i==2 else [0]*len(series)
                minus=[round(q1-min(s['values']),10) for s,q1 in zip(series,qs[0])] if i==0 else [0]*len(series)
            else:continue
            for direction,values in [('plus',plus),('minus',minus)]:cache(errors.find('c:'+direction,NS),values,True)
    for axis in root.findall('.//c:valAx',NS):
        fmt=axis.find('c:numFmt',NS)
        if fmt is not None:fmt.set('sourceLinked','0')
        isx=axis.find('c:axPos',NS).get('val') in ['b','t'];scale=axis.find('c:scaling',NS)
        if kind=='effects' and not isx:limits=[0,len(chart['labels'])+1]
        else:limits=[chart.get('xMin' if isx else 'yMin'),chart.get('xMax' if isx else 'yMax')]
        for name,value in zip(['min','max'],limits):
            old=scale.find('c:'+name,NS)
            if value is not None:
                if old is None:old=E.SubElement(scale,q('c',name))
                old.set('val',number(value))
            elif old is not None:scale.remove(old)
        major=chart.get('xMajor' if isx else 'yMajor');el=axis.find('c:majorUnit',NS)
        if major is not None:
            require(major>0,'Axis major unit must be positive')
            if el is None:el=E.SubElement(axis,q('c','majorUnit'))
            el.set('val',number(major))
            # Avoid rounding quarter-step ticks (0.25) to misleading 0.3 labels.
            decimals=len(format(major,'.10f').rstrip('0').partition('.')[2])
            if fmt is not None and decimals>len(fmt.get('formatCode','').partition('.')[2]):fmt.set('formatCode','0.'+'0'*decimals)
        title=axis.find('c:title/c:tx/c:rich',NS)
        if title is not None:set_text(title,chart.get('xTitle' if isx else 'yTitle',''))
    # Reject clipping, including uncertainty bounds. Never silently discard points.
    observed_y=[v for s in series for v in s['values']] if kind!='effects' else []
    if kind=='interval':observed_y+=chart['lower']+chart['upper']
    observed_x=[v for s in series for v in s.get('xValues',[])]
    if kind=='effects':observed_x=series[0]['values']+chart['errors'][0]['lower']+chart['errors'][0]['upper']
    for label,vals in [('x',observed_x),('y',observed_y)]:
        lo,hi=chart.get(label+'Min'),chart.get(label+'Max')
        if lo is not None and hi is not None:require(lo<hi,'Axis minimum must be below maximum')
        if vals:require((lo is None or min(vals)>=lo) and (hi is None or max(vals)<=hi),'Axis limits clip '+label+' data or intervals')
    return workbook(columns)

def normalize_table_adaptive(frame, matrix, palette, emphasis=(), policy=None):
    """Normalize table cell font sizes, colors, padding, and auto-proportion column widths."""
    table = frame.find('.//a:tbl', NS)
    grid = table.find('a:tblGrid', NS)
    grid_cols = grid.findall('a:gridCol', NS)
    rows = table.findall('a:tr', NS)
    policy = policy or {}
    header_px = policy.get('table_header', 21)
    data_px = policy.get('table_data', 20)
    require(isinstance(matrix, list) and len(matrix) >= 2 and isinstance(matrix[0], list) and len(matrix[0]) > 0 and all(isinstance(r, list) and len(r) == len(matrix[0]) for r in matrix), 'Table matrix must have >= 2 rows of equal nonzero length')
    target_rows = len(matrix)
    target_cols = len(matrix[0])

    # Adjust column count if different from template seed
    total_w = sum(int(c.get('w')) for c in grid_cols)
    while len(grid_cols) < target_cols:
        grid.append(copy.deepcopy(grid_cols[-1]))
        grid_cols = grid.findall('a:gridCol', NS)
    while len(grid_cols) > target_cols:
        grid.remove(grid_cols[-1])
        grid_cols = grid.findall('a:gridCol', NS)
    for r in rows:
        cells = r.findall('a:tc', NS)
        while len(cells) < target_cols:
            r.append(copy.deepcopy(cells[-1]))
            cells = r.findall('a:tc', NS)
        while len(cells) > target_cols:
            r.remove(cells[-1])
            cells = r.findall('a:tc', NS)

    # Adjust row count if different from template seed
    total_h = int(frame.find('p:xfrm/a:ext', NS).get('cy'))
    while len(rows) < target_rows:
        table.append(copy.deepcopy(rows[-1]))
        rows = table.findall('a:tr', NS)
    while len(rows) > target_rows:
        table.remove(rows[-1])
        rows = table.findall('a:tr', NS)
    row_h = total_h // target_rows
    required_h = (header_px * 1.25 + 8) + (target_rows - 1) * (data_px * 1.25 + 8)
    require(total_h / EMU >= required_h, f'Table exceeds vertical capacity ({target_rows} rows); split the slide, do not shrink text')
    for r in rows:
        r.set('h', str(row_h))

    # Auto-proportion column widths based on content length so cells never wrap unexpectedly
    col_needs = []
    for j in range(target_cols):
        max_v = max(visual_len(matrix[i][j]) for i in range(target_rows))
        col_needs.append(max(4.5, max_v + 2.2))
    sum_needs = sum(col_needs)
    new_widths = [round(total_w * (n / sum_needs)) for n in col_needs]
    new_widths[-1] += total_w - sum(new_widths)
    for col_el, w_val in zip(grid_cols, new_widths):
        col_el.set('w', str(w_val))
    # Reserve real glyph width and padding, including the solid style margin transform.
    scale = (1280 - 2 * policy.get('content_side_margin', 32)) / 1232
    for j, width in enumerate(new_widths):
        for i, row in enumerate(matrix):
            txt = str(row[j])
            font_px = header_px if i == 0 else data_px
            needed = sum(1.03 if ord(c) > 127 else .58 for c in txt) * font_px + 16
            require('\n' not in txt and '\r' not in txt and needed <= width / EMU * scale,
                    f'Table cell ({i},{j}) exceeds column capacity; shorten the cell or split the slide')

    primary = palette['primary'][1:]
    secondary = palette['secondary'][1:]
    accent = palette['accent'][1:]
    status_map = {'●': primary, '△': accent, '○': secondary}

    for r_idx, (values, row) in enumerate(zip(matrix, rows)):
        cells = row.findall('a:tc', NS)
        for c_idx, (value, cell) in enumerate(zip(values, cells)):
            sval = str(value)
            require(len(sval) <= 42, 'Table cell exceeds capacity')
            body = cell.find('a:txBody', NS)
            tcPr = cell.find('a:tcPr', NS)
            if tcPr is not None:
                tcPr.set('anchor', 'ctr')
                tcPr.set('marL', '68580')
                tcPr.set('marR', '68580')
                tcPr.set('marT', '38100')
                tcPr.set('marB', '38100')
            set_text(body, sval, emphasis if r_idx > 0 else (), accent)
            is_status = sval.strip() in status_map
            for p in body.findall('a:p', NS):
                pPr = p.find('a:pPr', NS)
                if pPr is None:
                    pPr = E.Element(q('a', 'pPr'))
                    p.insert(0, pPr)
                pPr.set('algn', 'l' if c_idx == 0 else 'ctr')
            for rp in body.findall('.//a:rPr', NS) + body.findall('.//a:endParaRPr', NS):
                if r_idx == 0:
                    rp.set('sz', str(round(header_px * 75)))
                    rp.set('b', '1')
                    for fl in rp.findall('a:solidFill', NS):
                        rp.remove(fl)
                    sfill = E.Element(q('a', 'solidFill'))
                    E.SubElement(sfill, q('a', 'srgbClr'), val='FFFFFF')
                    rp.insert(0, sfill)
                elif is_status:
                    rp.set('sz', str(round(data_px * 75)))
                    rp.set('b', '1')
                    for fl in rp.findall('a:solidFill', NS):
                        rp.remove(fl)
                    sfill = E.Element(q('a', 'solidFill'))
                    E.SubElement(sfill, q('a', 'srgbClr'), val=status_map[sval.strip()])
                    rp.insert(0, sfill)
                else:
                    rp.set('sz', str(round(data_px * 75)))
                    has_accent = rp.find('a:solidFill/a:srgbClr', NS) is not None and rp.find('a:solidFill/a:srgbClr', NS).get('val', '').upper() == accent.upper() and sval in emphasis
                    if not has_accent:
                        rp.set('b', '1' if c_idx == 0 else '0')
                        for fl in rp.findall('a:solidFill', NS):
                            rp.remove(fl)
                        sfill = E.Element(q('a', 'solidFill'))
                        E.SubElement(sfill, q('a', 'srgbClr'), val='1C2733')
                        rp.insert(0, sfill)

def png_dimensions(data):
    require(data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24, 'Replacement images must be valid PNG files')
    w = int.from_bytes(data[16:20], 'big')
    h = int.from_bytes(data[20:24], 'big')
    return max(1, w), max(1, h)

def fit_pic_aspect(pic, data):
    w_px, h_px = png_dimensions(data)
    off = pic.find('p:spPr/a:xfrm/a:off', NS)
    ext = pic.find('p:spPr/a:xfrm/a:ext', NS)
    if off is None or ext is None:
        return
    bx, by, bw, bh = int(off.get('x')), int(off.get('y')), int(ext.get('cx')), int(ext.get('cy'))
    aspect = w_px / h_px
    box_aspect = bw / max(1, bh)
    if aspect > box_aspect:
        nw = bw
        nh = round(bw / aspect)
        nx = bx
        ny = by + (bh - nh) // 2
    else:
        nh = bh
        nw = round(bh * aspect)
        ny = by
        nx = bx + (bw - nw) // 2
    off.set('x', str(nx))
    off.set('y', str(ny))
    ext.set('cx', str(nw))
    ext.set('cy', str(nh))
    blipFill = pic.find('p:blipFill', NS)
    if blipFill is not None:
        for sr in list(blipFill.findall('a:srcRect', NS)):
            blipFill.remove(sr)

def generate(document,output,*,force=False,font_profile='portable',base_dir=None):
    require(isinstance(document,dict),'Input must be a JSON object')
    system=load(ROOT/'assets/template-system.json');bindings=load(ROOT/'assets/templates/bindings.json')
    require(document.get('scenario') in system['scenarios'],'Choose scenario: academic/coursework/progress')
    require(document.get('palette') in system['palettes'],'Choose palette P1 through P10')
    require(document.get('fill_style','light') in ['light','solid'],'Choose fill_style light or solid')
    require(type(document.get('demo')) is bool,'demo must be explicitly true or false')
    require(isinstance(document.get('slides'),list) and 1<=len(document['slides'])<=150 and all(isinstance(p,dict) for p in document['slides']),'Provide 1 to 150 slide objects')
    output=Path(output).resolve();require(output.suffix.lower()=='.pptx','Output must end in .pptx')
    require(force or not output.exists(),'Output exists; choose another file or pass --force')
    base_dir=Path(base_dir).resolve() if base_dir else Path.cwd()
    extension = None
    if not document['demo'] or any(p.get('layout') in {'L15','L16','L17','L18','L19','L20'} or p.get('variant','default')!='default' or p.get('components') for p in document['slides']):
        spec_ext=importlib.util.spec_from_file_location('research_ppt_evidence',ROOT/'scripts/evidence_layouts.py')
        extension=importlib.util.module_from_spec(spec_ext);spec_ext.loader.exec_module(extension)
        extension.validate(document,base_dir)
    original=readzip(ROOT/'assets/templates/library.pptx');parts=dict(original)
    types=E.fromstring(original['[Content_Types].xml']);overrides={n.get('PartName').lstrip('/'):n.get('ContentType') for n in types if n.tag.endswith('Override')}
    counters={'chart':0,'workbook':0,'image':0};newslides=[];styler=None;compact=None
    def get_styler():
        nonlocal styler
        if styler is None:
            spec_styler=importlib.util.spec_from_file_location('research_ppt_fill_styles',ROOT/'scripts/fill_styles.py')
            styler=importlib.util.module_from_spec(spec_styler);spec_styler.loader.exec_module(styler)
        return styler

    for index,page in enumerate(document['slides'],1):
        if page.get('layout') in {'L21','L22','L23'}:
            if compact is None:
                spec_compact=importlib.util.spec_from_file_location('research_ppt_compact',ROOT/'scripts/compact_layouts.py')
                compact=importlib.util.module_from_spec(spec_compact);spec_compact.loader.exec_module(compact)
            import types as types_api
            newslides.append(compact.append(page,document,index,parts,overrides,counters,system,types_api.SimpleNamespace(**globals())))
            continue
        require('experiment_scene' not in page,'Unsupported experiment_scene; migrate explicitly to composition to avoid silently discarding custom content')
        layout=page.get('layout');is_new=extension is not None and (layout in extension.NEW or page.get('variant')=='original_figure')
        if page.get('variant')=='original_figure':require(layout in extension.VARIANTS and 'original_figure' in extension.VARIANTS[layout], 'Unsupported original_figure variant')
        require(layout in bindings or is_new,f'Unknown layout on page {index}')
        binding=({'slide':bindings['L14']['slide'],'default':{},'fields':[],'tables':[],'charts':[],'fixed_labels':[]} if is_new else bindings[layout])
        base=binding['default'];palette_id=page.get('palette',document['palette'])
        require(palette_id in system['palettes'],'Unknown page palette')
        require(document.get('palette_showcase') or palette_id==document['palette'],'A normal deck must use one palette')
        fill_style=page.get('fill_style',document.get('fill_style','light'))
        require(fill_style in ['light','solid'],'Choose fill_style light or solid')
        require(document.get('style_showcase') or fill_style==document.get('fill_style','light'),'A normal deck must use one fill style')
        visual_mode=page.get('visual_mode',document.get('visual_mode','legacy' if document.get('demo') else 'adaptive'))
        require(visual_mode in ['legacy','adaptive','clean'],'Choose visual_mode: legacy, adaptive, or clean')
        is_adaptive=visual_mode in ['adaptive','clean']
        slot_spec = system.get('image_slots', {}).get(layout, {})
        require(not (page.get('image') and page.get('images')), 'Choose image or images, not both')
        requested_images = page.get('images', {})
        require(isinstance(requested_images, dict), 'images must map named slots to PNG paths')
        if page.get('image'):
            require(len(slot_spec) == 1, f'{layout} needs named images slots {list(slot_spec)}' if slot_spec else f'{layout} has no image slot; choose L2/L5/L7/L8/L14')
            requested_images = {next(iter(slot_spec)): page['image']}
        require(all(k in slot_spec and isinstance(v, str) and v.strip() for k, v in requested_images.items()),
                f'{layout}: unknown image slot or empty PNG path; available: {list(slot_spec)}')
        if 'highlights' in page:
            hs = page['highlights']
            require(isinstance(hs, list) and 1 <= len(hs) <= 4 and all(isinstance(x, dict) for x in hs), 'highlights requires 1 to 4 objects; split or select highlights explicitly')
        palette=system['solid_palettes' if fill_style=='solid' else 'palettes'][palette_id];sources=page.get('sources')
        require(isinstance(sources,list) and sources and all(isinstance(v,str) and v.strip() for v in sources),'Every page needs non-empty sources')
        require(len(page.get('emphasis',[]))<=4,'At most four emphasis terms per slide')
        require(isinstance(page.get('title'),str),'Title must be text')
        require('composition' not in page or is_adaptive,'composition requires adaptive visual_mode')
        require('composition' not in page or layout in {'L15','L16','L17','L18'},'composition requires a figure-capable L15-L18 layout')
        flexible_header=is_adaptive and layout not in {'L5','L7','L14'} and 'composition' not in page
        require(len(page['title'])<=(240 if flexible_header or 'composition' in page else 38),'Title exceeds capacity; split the slide')
        if 'title_translation' in page:
            require(flexible_header,'title_translation is for adaptive content pages; use subtitle or lines on cover/section/closing pages')
            require(isinstance(page['title_translation'],str) and page['title_translation'].strip() and '\n' not in page['title_translation'] and '\r' not in page['title_translation'],'title_translation must be a non-empty single line')
        if 'edges' in base:
            require(page.get('edges')==base['edges'],'This template has fixed edges; edit the native PPT or use another template')
        if 'active' in base:
            act=page.get('active',base['active'])
            if is_adaptive:
                require(isinstance(act,int) and 0<=act<len(base.get('chapters',[0,1,2,3])),'L7 active chapter index must be 0..3')
            else:
                require(act==base['active'],'This template has fixed active chapter in legacy mode; set demo=false or visual_mode=adaptive')
        if not is_adaptive:
            def check_icons(actual,seed):
                if isinstance(seed,dict):
                    for key,val in seed.items():
                        if key=='icon':require(actual.get(key,val)==val,'Icon geometry is fixed in legacy mode; set demo=false or visual_mode=adaptive')
                        elif key in actual:check_icons(actual[key],val)
                elif isinstance(seed,list) and isinstance(actual,list):
                    for a,b in zip(actual,seed):check_icons(a,b)
            check_icons(page,base)
        for key in ['stages','observations','steps','chapters','inputs','nodes','items','lanes','actions','issues','milestones','anchors','checks','branches','lines']:
            if key in base:require(isinstance(page.get(key),list) and len(page[key])==len(base[key]),f'{layout}.{key} requires {len(base[key])} items')
        mapping={};owner='ppt/slides/slide'+str(index)+'.xml'
        def clone(part):
            if part in mapping:return mapping[part]
            if part.startswith('ppt/slides/slide') and part.endswith('.xml'):dest=owner
            elif part.startswith('ppt/notesSlides/notesSlide'):dest=f'ppt/notesSlides/notesSlide{index}.xml'
            elif re.search(r'/charts/chart\d+\.xml$',part):counters['chart']+=1;dest=f'ppt/charts/chart{counters["chart"]}.xml'
            elif part.startswith('ppt/embeddings/'):counters['workbook']+=1;dest=f'ppt/embeddings/data{counters["workbook"]}.xlsx'
            else:return part
            mapping[part]=dest;parts[dest]=original[part]
            if part in overrides:overrides[dest]=overrides[part]
            rp=relpart(part)
            if rp in original:
                relations=E.fromstring(original[rp])
                for rel in relations:
                    require(rel.get('TargetMode')!='External','External template relationships are not supported')
                    rel.set('Target','/'+clone(resolve(part,rel.get('Target'))))
                parts[relpart(dest)]=xml(relations)
            return dest
        clone(binding['slide']);root=E.fromstring(parts[owner])
        allow_duo = bool(page.get('duotone', document.get('duotone', not is_adaptive)))
        recolor(root,palette,system,allow_duotone=allow_duo)
        shapes={sp.find('p:nvSpPr/p:cNvPr',NS).get('id'):sp for sp in root.findall('.//p:sp',NS)}
        overrides_text=page.get('labels',{})
        require(isinstance(overrides_text,dict),'labels must map exact original labels to replacement text')
        for old,new in overrides_text.items():
            allowed = old in binding['fixed_labels'] or (is_adaptive and any(text_content(sp.find('p:txBody',NS))==old for sp in shapes.values() if sp.find('p:txBody',NS) is not None))
            max_lbl = max(18, len(old)*2 + 6) if is_adaptive else max(8, len(old)+3)
            require(allowed and isinstance(new,str) and len(new)<=max_lbl,'Unknown or oversized fixed label replacement: '+old)
        for sp in shapes.values():
            body=sp.find('p:txBody',NS)
            if body is not None and text_content(body) in overrides_text:set_text(body,overrides_text[text_content(body)])
        if is_adaptive and layout=='L12':
            lbl_pairs=[('14','17'),('36','39'),('52','55'),('84','87'),('102','105'),('116','119')]
            for idx,(p_id,r_id) in enumerate(lbl_pairs):
                if idx<len(page.get('items',[])):
                    it=page['items'][idx]
                    if it.get('problem_label') and p_id in shapes:set_text(shapes[p_id].find('p:txBody',NS),it['problem_label'])
                    if it.get('response_label') and r_id in shapes:set_text(shapes[r_id].find('p:txBody',NS),it['response_label'])
        for field in binding['fields']:
            sp=shapes[field['shape']];body=sp.find('p:txBody',NS)
            if 'special' in field:
                special=field['special'];value=f'{index:02d}' if special=='page' else system['scenarios'][document['scenario']]['name']+'  ·  RESEARCH PRESENTATION' if special=='scenario' else ('科研模板 · 内容与数据均为示意' if document['demo'] else str(document.get('footer','')))
            else:
                try:value=get(page,field['path'])
                except (KeyError,IndexError,TypeError):raise ValueError(f'{layout}: missing {field["path"]}')
                if field.get('join'):value=field['join'].join(str(v) for v in value)
                value=field.get('prefix','')+str(value)
                expected=text_content(body)
                if is_adaptive:
                    limit=max(64,int(visual_len(expected)*2.5)+24)
                    require((flexible_header and field['path']=='title') or visual_len(value)<=limit,f'{layout}.{field["path"]} is too long for this template ({visual_len(value)/2:.1f}>{limit/2:.0f}); shorten or split the slide')
                else:
                    limit=max(12,int(len(expected)*1.3)+3)
                    require(len(value)<=limit,f'{layout}.{field["path"]} is too long for this template ({len(value)}>{limit}); shorten or split the slide')
                if field['path']=='subtitle' and len(value)>18:value=value.replace(' · ','\n')
            set_text(body,value,page.get('emphasis',[]),palette['accent'][1:])
        if layout=='L5':
            for sp in shapes.values():
                ext=sp.find('p:spPr/a:xfrm/a:ext',NS);off=sp.find('p:spPr/a:xfrm/a:off',NS)
                if ext is not None and off is not None and abs(int(ext.get('cx'))-90*9525)<2 and abs(int(ext.get('cy'))-5*9525)<2:off.set('y',str((510 if len(page['subtitle'])>18 and ' · ' in page['subtitle'] else 475)*9525))
        frames={sp.find('p:nvGraphicFramePr/p:cNvPr',NS).get('id'):sp for sp in root.findall('.//p:graphicFrame',NS)}
        for tb in binding['tables']:
            matrix=get(page,tb['path'])
            if is_adaptive:
                region = system['table_regions'][layout]
                frame = frames[tb['shape']]
                frame.find('p:xfrm/a:off', NS).set('y', str(round(region['y'] * EMU)))
                frame.find('p:xfrm/a:ext', NS).set('cy', str(round(region['height'] * EMU)))
                normalize_table_adaptive(frames[tb['shape']], matrix, palette, page.get('emphasis', []), system['solid_typography'])
            else:
                table=frames[tb['shape']].find('.//a:tbl',NS);rows=table.findall('a:tr',NS)
                require(len(matrix)==len(rows),'Table row count must match layout')
                for values,row in zip(matrix,rows):
                    cells=row.findall('a:tc',NS);require(len(values)==len(cells),'Table column count must match layout')
                    for value,cell in zip(values,cells):
                        require(len(str(value))<=32,'Table cell exceeds capacity');body=cell.find('a:txBody',NS);set_text(body,value)
                        status={'●':palette['primary'][1:],'△':palette['accent'][1:],'○':palette['secondary'][1:]}
                        if str(value) in status:
                            for rp in body.findall('.//a:rPr',NS):
                                for fill in rp.findall('a:solidFill',NS):rp.remove(fill)
                                E.SubElement(E.SubElement(rp,q('a','solidFill')),q('a','srgbClr'),val=status[str(value)])
        if not is_new and fill_style=='solid':
            get_styler().apply(root,layout,palette,adaptive=is_adaptive,page=page,document=document,policy=system['solid_typography'])
        elif not is_new and is_adaptive:
            get_styler().prepare_adaptive_geometry(root,layout,palette,page,document,'light')
            get_styler().apply_adaptive_icons(root,layout,palette,page,'light')
            for sp in root.findall('.//p:sp', NS):
                off = sp.find('p:spPr/a:xfrm/a:off', NS)
                floor = system['solid_typography']['footnote'] if off is not None and int(off.get('y')) / EMU >= 690 else system['solid_typography']['auxiliary_min']
                for rp in sp.findall('.//a:rPr', NS) + sp.findall('.//a:defRPr', NS):
                    if rp.get('sz'):
                        rp.set('sz', str(max(int(rp.get('sz')), round(floor * 75))))
        # Handle per-slide real material image if provided
        pics = {p.find('p:nvPicPr/p:cNvPr', NS).get('id'): p for p in root.findall('.//p:pic', NS)}
        if requested_images and is_adaptive:
            requested_ids = {slot_spec[k] for k in requested_images}
            tree = root.find('p:cSld/p:spTree', NS)
            for pid, pic in pics.items():
                if pid not in requested_ids and pic in list(tree):
                    tree.remove(pic)
        for slot, filename in requested_images.items():
            require(slot_spec[slot] in pics, f'{layout}: image slot {slot} is unavailable')
            img_path = Path(filename)
            if not img_path.is_absolute():
                img_path = (base_dir / img_path).resolve()
            img_bytes = img_path.read_bytes()
            png_dimensions(img_bytes)
            counters['image'] += 1
            media_name = f'ppt/media/custom_slide_{counters["image"]}.png'
            parts[media_name] = img_bytes
            srels = E.fromstring(parts[relpart(owner)])
            new_rid = f'rCustomImg{counters["image"]}'
            E.SubElement(srels, '{'+REL+'}Relationship', Id=new_rid, Type=NS['r']+'/image', Target='/'+media_name)
            parts[relpart(owner)] = xml(srels)
            pic = pics[slot_spec[slot]]
            blip = pic.find('p:blipFill/a:blip', NS)
            require(blip is not None, f'{layout}: image slot {slot} has no image relationship')
            blip.set(q('r', 'embed'), new_rid)
            for duo in list(blip.findall('a:duotone', NS)):
                blip.remove(duo)
            if allow_duo:
                duo = E.SubElement(blip, q('a', 'duotone'))
                E.SubElement(duo, q('a', 'srgbClr'), val=palette['primary'][1:])
                E.SubElement(duo, q('a', 'srgbClr'), val='FFFFFF')
            fit_pic_aspect(pic, img_bytes)
        if is_new:
            import types as types_api
            api=types_api.SimpleNamespace(NS=NS,REL=REL,q=q,EMU=EMU,png_dimensions=png_dimensions)
            srels=E.fromstring(parts[relpart(owner)])
            render_page=dict(page)
            if page.get('variant')=='original_figure':render_page.update(layout='L16',variant='full_width')
            extension.build(root,srels,parts,counters,render_page,document,palette,api,get_styler(),base_dir,index)
            parts[relpart(owner)]=xml(srels)
        elif extension is not None and page.get('variant','default')!='default':
            import types as types_api
            extension.apply_variant(root,page,types_api.SimpleNamespace(NS=NS,EMU=EMU))
        if page.get('components'):
            import types as types_api
            extension.components(root,page,palette,types_api.SimpleNamespace(NS=NS),get_styler())
        if flexible_header:
            title_field=next((f for f in binding['fields'] if f.get('path')=='title'),None)
            title_shape=(shapes.get(title_field['shape']) if title_field else next((sp for sp in root.findall('.//p:sp',NS) if sp.find('p:nvSpPr/p:cNvPr',NS).get('name','').startswith('title-')),None))
            require(title_shape is not None,'Content page title object is missing')
            fit_content_header(root,title_shape,page,palette,get_styler())
        parts[owner]=xml(root)
        relations={r.get('Id'):resolve(owner,r.get('Target')) for r in E.fromstring(parts[relpart(owner)])}
        chart_sources=[]
        for ch in binding['charts']:
            chart=get(page,ch['path']);require(chart.get('source'),'Every chart needs a source')
            require(isinstance(chart['source'],str) and chart['source'].strip(),'Chart source must be non-empty text')
            chart_sources.append(ch['path']+': '+chart['source'])
            if layout=='L3':require(len(chart.get('categories',[]))==len(get(base,ch['path']).get('categories',[])),'L3 category count is fixed because labels are independent editable text')
            chartpart=relations[ch['rid']];native=E.fromstring(parts[chartpart]);recolor(native,palette,system,allow_duotone=allow_duo)
            book=patch_chart(native,chart,get(base,ch['path']),adaptive=is_adaptive)
            if fill_style=='solid' or is_adaptive:get_styler().chart_typography(native,adaptive=is_adaptive,policy=system['solid_typography'],layout=layout)
            parts[chartpart]=xml(native)
            ext=native.find('c:externalData',NS).get(q('r','id'));chartrels={r.get('Id'):resolve(chartpart,r.get('Target')) for r in E.fromstring(parts[relpart(chartpart)])};parts[chartrels[ext]]=book
        notespart=f'ppt/notesSlides/notesSlide{index}.xml';notes=E.fromstring(parts[notespart])
        for sp in notes.findall('.//p:sp',NS):
            ph=sp.find('p:nvSpPr/p:nvPr/p:ph',NS)
            if ph is not None and ph.get('type')=='body':set_text(sp.find('p:txBody',NS),'\n'.join(sources)+('\nChart sources:\n'+'\n'.join(chart_sources) if chart_sources else '')+f'\nLayout: {layout}\nPalette: {palette_id}\nScenario: {document["scenario"]}\n'+('Fill style: solid\n' if fill_style=='solid' else '')+('SYNTHETIC DEMONSTRATION DATA\n' if document['demo'] else '')+str(page.get('notes','')) + ('\nEVIDENCE_MANIFEST: '+json.dumps({'materials':document.get('materials',{}),'figures':page.get('figures',[])},ensure_ascii=False) if not document['demo'] else ''))
        parts[notespart]=xml(notes);newslides.append(owner)
    pres=E.fromstring(parts['ppt/presentation.xml']);lst=pres.find('p:sldIdLst',NS);lst.clear();rels=E.fromstring(parts['ppt/_rels/presentation.xml.rels'])
    for r in list(rels):
        if r.get('Type','').endswith('/slide'):rels.remove(r)
    for i,part in enumerate(newslides,1):
        rid=f'researchSlide{i}';E.SubElement(rels,'{'+REL+'}Relationship',Id=rid,Type=NS['r']+'/slide',Target='/'+part);E.SubElement(lst,q('p','sldId'),{'id':str(255+i),q('r','id'):rid})
    parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(rels)
    # Traverse package relationships to remove every unused seed slide/chart/media.
    keep={'[Content_Types].xml'}
    def visit(part):
        if part in keep:return
        if part:require(part in parts,'Broken relationship: '+part);keep.add(part)
        rp=relpart(part)
        if rp not in parts:return
        keep.add(rp)
        for r in E.fromstring(parts[rp]):
            if r.get('TargetMode')!='External':visit(resolve(part,r.get('Target')))
    visit('');parts={n:b for n,b in parts.items() if n in keep}
    for el in list(types):
        if el.tag.endswith('Override'):types.remove(el)
    for name,kind in sorted(overrides.items()):
        if name in parts:E.SubElement(types,'{'+CT+'}Override',PartName='/'+name,ContentType=kind)
    parts['[Content_Types].xml']=xml(types)
    # Remove seed document-title vectors and replace identifying metadata.
    if 'docProps/app.xml' in parts:
        app=E.fromstring(parts['docProps/app.xml'])
        for node in list(app):
            local=node.tag.rsplit('}',1)[-1]
            if local in ['TitlesOfParts','HeadingPairs']:app.remove(node)
            elif local=='Slides':node.text=str(len(newslides))
        parts['docProps/app.xml']=xml(app)
    if font_profile=='office':
        for name,b in list(parts.items()):
            if name.endswith('.xml'):parts[name]=b.replace(b'Noto Sans CJK SC',b'Microsoft YaHei').replace(b'Noto Serif CJK SC',b'SimSun')
    # User pictures replace independent media objects; no layout text is rasterized.
    for role,filename in document.get('illustrations',{}).items():
        target={'forest':'ppt/media/image.png','landscape':'ppt/media/image2.png'}.get(role)
        require(target is not None,'Unknown illustration role')
        img_p = Path(filename)
        if not img_p.is_absolute():
            img_p = (base_dir / img_p).resolve()
        data=img_p.read_bytes()
        require(data.startswith(b'\x89PNG\r\n\x1a\n'),'Replacement illustrations must be PNG')
        if target in parts:parts[target]=data
    payload=zipbytes(parts)
    atomic_write(output,payload,force=force)
    return {'slides':len(newslides),'charts':counters['chart'],'sha256':hashlib.sha256(payload).hexdigest(),'font_profile':font_profile,'output':str(output)}

def fit_content_header(root,title_shape,page,palette,styler):
    """One full-size title line plus optional native bilingual kicker, no body squeeze."""
    bounds=styler.box(title_shape)
    props=title_shape.findall('.//a:rPr',NS)
    size=max((int(r.get('sz'))/75 for r in props if r.get('sz')),default=42)
    title=page['title']
    width=sum(size*(1.03 if ord(ch)>127 else .58) for ch in title)
    require('\n' not in title and '\r' not in title and width<=bounds[2]+6,
            'title exceeds its actual region at the approved font size; shorten the title, put detail in body/notes, or split the page')
    if 'title_translation' not in page:return
    require(bounds[0]>=24 and bounds[2]>=1000,'Bilingual header needs a full-width content title region')
    translation=page['title_translation'];small=17
    require(sum(small*(1.03 if ord(ch)>127 else .58) for ch in translation)<=bounds[2]+6,
            'title_translation exceeds one header line; shorten or explain in body/notes')
    xf=title_shape.find('p:spPr/a:xfrm',NS)
    xf.find('a:off',NS).set('y',str(round(26*EMU)))
    xf.find('a:ext',NS).set('cy',str(round(58*EMU)))
    tree=root.find('p:cSld/p:spTree',NS)
    # Older content templates put the rule at y=74; bilingual titles end at y=84.
    for sp in tree.findall('p:sp',NS):
        b=styler.box(sp)
        if b and b[2]>=1000 and 60<=b[1]<=90 and b[3]<=4:
            sp.find('p:spPr/a:xfrm/a:off',NS).set('y',str(86*EMU))
    ids=[int(n.get('id')) for n in root.findall('.//p:cNvPr',NS) if n.get('id','').isdigit()]
    tree.append(styler.make_text_shape(max(ids,default=0)+1,'title-translation',bounds[0],2,bounds[2],23,translation,sz_px=small,color=palette['primary'][1:]))


def atomic_write(output,payload,*,force=False):
    """Publish complete bytes only; failed replacement leaves the old file intact."""
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    staged=None
    try:
        # Same-directory staging keeps rename atomic, including mounted volumes.
        with tempfile.NamedTemporaryFile(prefix='.'+output.name+'.',suffix='.tmp',dir=output.parent,delete=False) as f:
            staged=Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if force:
            os.replace(staged,output)
        else:
            # A link is exclusive: a file created after validation is never clobbered.
            os.link(staged,output)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main():
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);parser.add_argument('--force',action='store_true');parser.add_argument('--font-profile',choices=['portable','office'],default='portable');args=parser.parse_args()
    try:
        in_path=Path(args.input).resolve()
        document=load(in_path)
        document['illustrations']={role:str((in_path.parent/filename).resolve()) for role,filename in document.get('illustrations',{}).items()}
        print(json.dumps(generate(document,args.output,force=args.force,font_profile=args.font_profile,base_dir=in_path.parent),ensure_ascii=False))
    except (ValueError,KeyError,IndexError,TypeError,OSError) as error:parser.exit(2,'Input/environment error: '+str(error)+'\n')
if __name__=='__main__':main()
