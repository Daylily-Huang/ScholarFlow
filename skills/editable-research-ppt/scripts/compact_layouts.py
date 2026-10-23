"""Fill six user-approved compact native compositions. Standard library only."""
from __future__ import annotations
import copy
import json
import posixpath
from pathlib import Path
import xml.etree.ElementTree as E

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = {'L21', 'L22', 'L23'}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def definition(page):
    catalog = json.loads((ROOT / 'assets/templates/compact-bindings.json').read_text(encoding='utf-8'))
    layout = page.get('layout')
    variant = page.get('variant', 'default')
    if variant == 'default':
        variant = catalog['defaults'].get(layout)
    key = str(layout) + ':' + str(variant)
    check(key in catalog['templates'], f'{layout}: unsupported compact variant {variant}')
    return catalog['templates'][key]


def fit_text(shape, text, g, label):
    box = shape.find('p:spPr/a:xfrm', g.NS)
    if box is None:
        return
    ext = box.find('a:ext', g.NS)
    w, h = int(ext.get('cx')) / g.EMU, int(ext.get('cy')) / g.EMU
    size = max((int(r.get('sz')) / 75 for r in shape.findall('.//a:rPr', g.NS) if r.get('sz')), default=20)
    lines = str(text).split('\n')
    width = max(sum(size * (1.03 if ord(c) > 127 else .58) for c in line) for line in lines)
    check(width <= w + 6 and len(lines) * size * 1.1 <= h + 6,
          f'{label} exceeds the approved compact region; shorten, insert an explicit line break, or split the page; font size is not reduced')


def append(page, document, index, parts, overrides, counters, system, g):
    """Clone one selected seed graph into the shared package, preserving geometry."""
    seed = definition(page)
    allowed = {'layout','variant','title','texts','charts','table','sources','notes','palette','fill_style','visual_mode','emphasis'}
    check(not (set(page) - allowed), 'Compact layout: unsupported fields ' + ', '.join(sorted(set(page) - allowed)) + '; use L15-L18 for original figures/composition or bilingual layouts for title_translation')
    check(isinstance(page.get('title'), str) and page['title'].strip(), 'Compact title is required')
    check(isinstance(page.get('sources'), list) and page['sources'] and all(isinstance(s,str) and s.strip() for s in page['sources']), 'Every compact page needs nonempty sources')
    check(isinstance(page.get('texts'), dict), 'Compact texts must be an object; start with assets/examples/compact-approved.json')
    expected = {f['path'].split('.', 1)[1] for f in seed['fields'] if f['path'].startswith('texts.')}
    check(set(page['texts']) == expected, f'Compact texts keys differ: missing {sorted(expected - set(page["texts"]))}, unknown {sorted(set(page["texts"]) - expected)}')
    check(all(isinstance(t,str) and t.strip() for t in page['texts'].values()), 'Compact text values must be nonempty strings')
    palette_id = page.get('palette', document['palette'])
    check(palette_id in system['palettes'], 'Unknown compact palette')
    check(document.get('palette_showcase') or palette_id == document['palette'], 'A normal deck must use one palette')
    fill = page.get('fill_style', document.get('fill_style','light'))
    check(fill in {'light','solid'}, 'Choose fill_style light or solid')
    check(document.get('style_showcase') or fill == document.get('fill_style','light'), 'A normal deck must use one fill style')
    check(page.get('visual_mode', document.get('visual_mode', 'adaptive')) in {'legacy','adaptive','clean'}, 'Unknown visual_mode')
    emphasis = page.get('emphasis', [])
    check(isinstance(emphasis,list) and len(emphasis) <= 4 and all(isinstance(t,str) for t in emphasis), 'At most four emphasis terms')
    palette = system['solid_palettes' if fill == 'solid' else 'palettes'][palette_id]
    old = seed['seed_palette']
    mapping = {old[k].lstrip('#').upper(): palette.get(k, '#202C3A').lstrip('#').upper()
               for k in ['ink','paper','tint','primary','secondary','accent']}
    source = g.readzip(ROOT / 'assets/templates/compact-library.pptx')
    source_types = {n.get('PartName').lstrip('/'):n.get('ContentType') for n in E.fromstring(source['[Content_Types].xml']) if n.tag.endswith('Override')}
    mapped = {}
    owner = f'ppt/slides/slide{index}.xml'

    def clone(part):
        if part in mapped:
            return mapped[part]
        # The approved pages are fully explicit native objects on blank layouts.
        # Reuse the package's registered layout/notes master instead of creating
        # multiple competing master graphs from a second authoring application.
        if part.startswith('ppt/slideLayouts/'):
            return next(n for n in parts if n.startswith('ppt/slideLayouts/') and n.endswith('.xml'))
        if part.startswith('ppt/notesMasters/'):
            return next(n for n in parts if n.startswith('ppt/notesMasters/') and n.endswith('.xml'))
        if part == seed['slide']:
            dest = owner
        elif part.startswith('ppt/notesSlides/notesSlide') and part.endswith('.xml'):
            dest = f'ppt/notesSlides/notesSlide{index}.xml'
        elif part.startswith('ppt/charts/chart') and part.endswith('.xml'):
            counters['chart'] += 1
            dest = f'ppt/charts/chart{counters["chart"]}.xml'
        elif part.startswith('ppt/embeddings/'):
            counters['workbook'] += 1
            dest = f'ppt/embeddings/data{counters["workbook"]}.xlsx'
        else:
            dest = f'ppt/compact{index}/' + part.removeprefix('ppt/')
        check(part in source, 'Compact template dependency missing: ' + part)
        mapped[part] = dest
        parts[dest] = source[part]
        if part in source_types:
            overrides[dest] = source_types[part]
        rp = g.relpart(part)
        if rp in source:
            rels = E.fromstring(source[rp])
            for rel in rels:
                check(rel.get('TargetMode') != 'External', 'External compact template dependency')
                rel.set('Target', '/' + clone(g.resolve(part, rel.get('Target'))))
            parts[g.relpart(dest)] = g.xml(rels)
        return dest

    clone(seed['slide'])
    root = E.fromstring(parts[owner])
    for part in mapped.values():
        if part.endswith('.xml') and part != f'ppt/notesSlides/notesSlide{index}.xml':
            node = E.fromstring(parts[part])
            for color in node.iter(g.q('a','srgbClr')):
                if color.get('val','').upper() in mapping:
                    color.set('val', mapping[color.get('val').upper()])
            parts[part] = g.xml(node)
    root = E.fromstring(parts[owner])
    shapes = {s.find('p:nvSpPr/p:cNvPr',g.NS).get('id'):s for s in root.findall('.//p:sp',g.NS)}
    for field in seed['fields']:
        text = g.get(page, field['path'])
        fit_text(shapes[field['shape']], text, g, field['path'])
        g.set_text(shapes[field['shape']].find('p:txBody',g.NS), text, emphasis, palette['accent'][1:])
    for field in seed['special']:
        kind = field['kind']
        value = f'{index:02d}' if kind == 'page' else system['scenarios'][document['scenario']]['name'] if kind == 'scenario' else '合成数据，仅供版式演示' if document['demo'] else str(document.get('footer',''))
        fit_text(shapes[field['shape']], value, g, kind)
        g.set_text(shapes[field['shape']].find('p:txBody',g.NS),value)

    if fill == 'light':
        light_panels = []
        for shape in root.findall('.//p:sp',g.NS):
            fillcolor = shape.find('p:spPr/a:solidFill/a:srgbClr',g.NS)
            bounds = shape.find('p:spPr/a:xfrm',g.NS)
            geometry = shape.find('p:spPr/a:prstGeom',g.NS)
            container = geometry is not None and geometry.get('prst') in {'rect','roundRect'}
            if container and fillcolor is not None and bounds is not None and fillcolor.get('val') == palette['primary'][1:]:
                extent=bounds.find('a:ext',g.NS)
                if int(extent.get('cx'))*int(extent.get('cy')) < 4000*g.EMU*g.EMU:
                    continue
                fillcolor.set('val',palette['tint'][1:])
                off,ext = bounds.find('a:off',g.NS),bounds.find('a:ext',g.NS)
                light_panels.append(tuple(int(el.get(key)) for el,key in [(off,'x'),(off,'y'),(ext,'cx'),(ext,'cy')]))
        for shape in shapes.values():
            bounds=shape.find('p:spPr/a:xfrm',g.NS)
            if bounds is None:continue
            off,ext=bounds.find('a:off',g.NS),bounds.find('a:ext',g.NS)
            cx=int(off.get('x'))+int(ext.get('cx'))/2;cy=int(off.get('y'))+int(ext.get('cy'))/2
            if any(x<=cx<=x+w and y<=cy<=y+h for x,y,w,h in light_panels):
                for color in shape.findall('p:txBody//a:solidFill/a:srgbClr',g.NS):
                    if color.get('val')=='FFFFFF':color.set('val',palette['primary'][1:])
        for connector in root.findall('.//p:cxnSp',g.NS):
            bounds=connector.find('p:spPr/a:xfrm',g.NS)
            if bounds is None:continue
            off,ext=bounds.find('a:off',g.NS),bounds.find('a:ext',g.NS)
            cx=int(off.get('x'))+int(ext.get('cx'))/2;cy=int(off.get('y'))+int(ext.get('cy'))/2
            if any(x<=cx<=x+w and y<=cy<=y+h for x,y,w,h in light_panels):
                for color in connector.findall('p:spPr/a:ln/a:solidFill/a:srgbClr',g.NS):
                    if color.get('val')=='FFFFFF':color.set('val',palette['primary'][1:])

    table = seed['table']
    if table:
        matrix=page.get('table')
        check(isinstance(matrix,list) and len(matrix)==4 and all(isinstance(row,list) and len(row)==3 for row in matrix), 'Compact progress table needs 4 rows x 3 columns; split extra stages into another page')
        frame=next(f for f in root.findall('.//p:graphicFrame',g.NS) if f.find('p:nvGraphicFramePr/p:cNvPr',g.NS).get('id')==table['shape'])
        tbl=frame.find('.//a:tbl',g.NS)
        widths=[int(c.get('w'))/g.EMU for c in tbl.findall('a:tblGrid/a:gridCol',g.NS)]
        for ri,(values,row) in enumerate(zip(matrix,tbl.findall('a:tr',g.NS))):
            for ci,(value,cell) in enumerate(zip(values,row.findall('a:tc',g.NS))):
                check(isinstance(value,str) and value.strip(), 'Compact table values must be nonempty strings')
                check(sum((1.03 if ord(c)>127 else .58)*(21 if ri==0 else 20) for c in value)<=widths[ci]-12, 'Compact table cell exceeds column width; shorten or split')
                check('\n' not in value and '\r' not in value,'Compact table cells must be single line')
                g.set_text(cell.find('a:txBody',g.NS),value)
                if fill=='light' and ri==0:
                    cell.find('a:tcPr/a:solidFill/a:srgbClr',g.NS).set('val',palette['tint'][1:])
                    for color in cell.findall('.//a:rPr/a:solidFill/a:srgbClr',g.NS):color.set('val',palette['primary'][1:])
    else:
        check('table' not in page,'This compact variant has no table')
    charts=page.get('charts',[])
    check(isinstance(charts,list) and len(charts)==len(seed['charts']), 'Compact chart count differs from selected variant')
    rels={r.get('Id'):g.resolve(owner,r.get('Target')) for r in E.fromstring(parts[g.relpart(owner)])}
    for chart,binding in zip(charts,seed['charts']):
        check(isinstance(chart,dict) and isinstance(chart.get('source'),str) and chart['source'].strip(), 'Each chart needs a nonempty source')
        chartpart=rels[binding['rid']];native=E.fromstring(parts[chartpart])
        book=g.patch_chart(native,chart,binding['default'],adaptive=True)
        parts[chartpart]=g.xml(native)
        ext=native.find('c:externalData',g.NS).get(g.q('r','id'))
        bookrels={r.get('Id'):g.resolve(chartpart,r.get('Target')) for r in E.fromstring(parts[g.relpart(chartpart)])}
        parts[bookrels[ext]]=book
    parts[owner]=g.xml(root)
    notespart=f'ppt/notesSlides/notesSlide{index}.xml';notes=E.fromstring(parts[notespart])
    license_text=(ROOT/'assets/icons/lucide/LICENSE.txt').read_text(encoding='utf-8')
    note='\n'.join(page['sources'])+'\n'+'\n'.join(c['source'] for c in charts)+f'\nLayout: {page["layout"]}\nVariant: {page.get("variant","default")}\nPalette: {palette_id}\nScenario: {document["scenario"]}\nFill style: {fill}\nApproved reference page: {seed["source_page"]}\n'+('SYNTHETIC DEMONSTRATION DATA\n' if document['demo'] else '\nEVIDENCE_MANIFEST: '+json.dumps({'materials':document.get('materials',{}),'figures':[]},ensure_ascii=False)+'\n')+str(page.get('notes',''))+'\nLucide Icons and Contributors; https://lucide.dev/license\n'+license_text
    for shape in notes.findall('.//p:sp',g.NS):
        ph=shape.find('p:nvSpPr/p:nvPr/p:ph',g.NS)
        if ph is not None and ph.get('type')=='body':g.set_text(shape.find('p:txBody',g.NS),note)
    parts[notespart]=g.xml(notes)
    return owner
