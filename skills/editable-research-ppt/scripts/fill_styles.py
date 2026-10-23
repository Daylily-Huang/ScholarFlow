"""Native OOXML solid & adaptive visual styles for L1-L14 geometry.

Preserves chart numbers, text content, and relationships. Supports:
1. Legacy mode (`adaptive=False`): preserves exact v1.1 solid geometry for demo compatibility.
2. Adaptive mode (`adaptive=True`): removes stiff duplicate body icons and unrelated stock
   ecology bitmaps, expands text/table/chart areas, builds native editable summary/comparison
   cards when custom figures are not supplied, and renders clean domain-adaptive wireframe icons.
"""
from __future__ import annotations
import copy
import math
import xml.etree.ElementTree as E

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
def q(p, n): return '{' + NS[p] + '}' + n
EMU = 9525


def box(sp):
    off = sp.find('p:spPr/a:xfrm/a:off', NS)
    ext = sp.find('p:spPr/a:xfrm/a:ext', NS)
    if off is None or ext is None:
        return None
    return tuple(int(el.get(k)) / EMU for el, k in [(off, 'x'), (off, 'y'), (ext, 'cx'), (ext, 'cy')])


def set_box(el, x, y, w, h):
    xf = el.find('p:spPr/a:xfrm', NS)
    if xf is None:
        xf = el.find('p:xfrm', NS)
    if xf is None:
        return
    off = xf.find('a:off', NS)
    ext = xf.find('a:ext', NS)
    if off is not None:
        off.set('x', str(round(x * EMU)))
        off.set('y', str(round(y * EMU)))
    if ext is not None:
        ext.set('cx', str(round(w * EMU)))
        ext.set('cy', str(round(h * EMU)))


def inside(a, b, margin=1):
    return (
        a[0] >= b[0] - margin
        and a[1] >= b[1] - margin
        and a[0] + a[2] <= b[0] + b[2] + margin
        and a[1] + a[3] <= b[1] + b[3] + margin
    )


def center_inside(a, b):
    return b[0] <= a[0] + a[2] / 2 <= b[0] + b[2] and b[1] <= a[1] + a[3] / 2 <= b[1] + b[3]


def inkbox(sp):
    bounds = box(sp)
    path = sp.find('.//a:custGeom/a:pathLst/a:path', NS)
    if path is None:
        return bounds
    pts = path.findall('.//a:pt', NS)
    if not pts:
        return bounds
    xs = [int(p.get('x')) for p in pts]
    ys = [int(p.get('y')) for p in pts]
    pw = int(path.get('w'))
    ph = int(path.get('h'))
    return (
        bounds[0] + min(xs) / pw * bounds[2],
        bounds[1] + min(ys) / ph * bounds[3],
        (max(xs) - min(xs)) / pw * bounds[2],
        (max(ys) - min(ys)) / ph * bounds[3],
    )


def no_fill(parent):
    old_indexes = [
        i for i, child in enumerate(parent)
        if child.tag in [q('a', x) for x in ['noFill', 'solidFill', 'gradFill', 'pattFill', 'blipFill', 'grpFill']]
    ]
    for child in list(parent):
        if child.tag in [q('a', x) for x in ['noFill', 'solidFill', 'gradFill', 'pattFill', 'blipFill', 'grpFill']]:
            parent.remove(child)
    el = E.Element(q('a', 'noFill'))
    before = old_indexes[0] if old_indexes else next(
        (i for i, c in enumerate(parent) if c.tag in [q('a', x) for x in ['ln', 'effectLst', 'effectDag', 'scene3d', 'sp3d']]),
        len(parent),
    )
    parent.insert(before, el)


def fill(parent, color):
    old_indexes = [
        i for i, child in enumerate(parent)
        if child.tag in [q('a', x) for x in ['noFill', 'solidFill', 'gradFill', 'pattFill', 'blipFill', 'grpFill']]
    ]
    for child in list(parent):
        if child.tag in [q('a', x) for x in ['noFill', 'solidFill', 'gradFill', 'pattFill', 'blipFill', 'grpFill']]:
            parent.remove(child)
    el = E.Element(q('a', 'solidFill'))
    E.SubElement(el, q('a', 'srgbClr'), val=color)
    before = old_indexes[0] if old_indexes else next(
        (i for i, c in enumerate(parent) if c.tag in [q('a', x) for x in ['ln', 'effectLst', 'effectDag', 'scene3d', 'sp3d']]),
        len(parent),
    )
    if parent.tag in [q('a', n) for n in ['rPr', 'defRPr', 'endParaRPr']]:
        before = 1 if len(parent) and parent[0].tag == q('a', 'ln') else 0
    if parent.tag == q('a', 'ln'):
        before = 0
    parent.insert(before, el)


def stroke(sp, color, width=1.5):
    props = sp.find('p:spPr', NS)
    line = props.find('a:ln', NS)
    if line is None:
        line = E.SubElement(props, q('a', 'ln'))
    line.set('w', str(round(width * EMU)))
    line.set('cap', 'rnd')
    fill(line, color)


def no_stroke(sp):
    props = sp.find('p:spPr', NS)
    line = props.find('a:ln', NS)
    if line is not None:
        props.remove(line)


def text_color(sp, color):
    for props in sp.findall('.//a:rPr', NS) + sp.findall('.//a:defRPr', NS) + sp.findall('.//a:endParaRPr', NS):
        fill(props, color)


def set_vcenter(sp, anchor='ctr'):
    bodyPr = sp.find('p:txBody/a:bodyPr', NS)
    if bodyPr is not None:
        bodyPr.set('anchor', anchor)


def visual_char_len(text):
    total = 0.0
    for ch in str(text):
        total += 1.0 if ord(ch) > 127 else 0.56
    return total


def make_shape(nextid, name_str, x, y, w, h, *, prst='rect', fill_clr=None, stroke_clr=None, stroke_w=1.2, adj=None):
    sp = E.Element(q('p', 'sp'))
    nv = E.SubElement(sp, q('p', 'nvSpPr'))
    E.SubElement(nv, q('p', 'cNvPr'), id=str(nextid), name=f'{name_str}-{nextid}')
    E.SubElement(nv, q('p', 'cNvSpPr'))
    E.SubElement(nv, q('p', 'nvPr'))
    pr = E.SubElement(sp, q('p', 'spPr'))
    xf = E.SubElement(pr, q('a', 'xfrm'))
    E.SubElement(xf, q('a', 'off'), x=str(round(x * EMU)), y=str(round(y * EMU)))
    E.SubElement(xf, q('a', 'ext'), cx=str(round(w * EMU)), cy=str(round(h * EMU)))
    geom = E.SubElement(pr, q('a', 'prstGeom'), prst=prst)
    av = E.SubElement(geom, q('a', 'avLst'))
    if adj is not None:
        E.SubElement(av, q('a', 'gd'), name='adj', fmla=f'val {adj}')
    if fill_clr:
        fill(pr, fill_clr)
    else:
        no_fill(pr)
    if stroke_clr:
        stroke(sp, stroke_clr, stroke_w)
    return sp


def make_custom_path_shape(nextid, name_str, x, y, w, h, subpaths, *, stroke_clr, stroke_w=1.7, fill_clr=None):
    """Create a native OOXML custom geometry shape (`a:custGeom`) with clean vector paths.
    Each subpath in `subpaths` is a dict: {'pts': [(px, py), ...], 'close': bool} in 0..1000 coordinates.
    """
    sp = E.Element(q('p', 'sp'))
    nv = E.SubElement(sp, q('p', 'nvSpPr'))
    E.SubElement(nv, q('p', 'cNvPr'), id=str(nextid), name=f'{name_str}-{nextid}')
    E.SubElement(nv, q('p', 'cNvSpPr'))
    E.SubElement(nv, q('p', 'nvPr'))
    pr = E.SubElement(sp, q('p', 'spPr'))
    xf = E.SubElement(pr, q('a', 'xfrm'))
    E.SubElement(xf, q('a', 'off'), x=str(round(x * EMU)), y=str(round(y * EMU)))
    E.SubElement(xf, q('a', 'ext'), cx=str(round(w * EMU)), cy=str(round(h * EMU)))
    cg = E.SubElement(pr, q('a', 'custGeom'))
    E.SubElement(cg, q('a', 'avLst'))
    E.SubElement(cg, q('a', 'gdLst'))
    E.SubElement(cg, q('a', 'ahLst'))
    E.SubElement(cg, q('a', 'cxnLst'))
    E.SubElement(cg, q('a', 'rect'), l='0', t='0', r='r', b='b')
    pl = E.SubElement(cg, q('a', 'pathLst'))
    for sub in subpaths:
        p = E.SubElement(pl, q('a', 'path'), w='1000', h='1000')
        pts = sub['pts']
        mv = E.SubElement(p, q('a', 'moveTo'))
        E.SubElement(mv, q('a', 'pt'), x=str(round(pts[0][0])), y=str(round(pts[0][1])))
        for pt in pts[1:]:
            ln = E.SubElement(p, q('a', 'lnTo'))
            E.SubElement(ln, q('a', 'pt'), x=str(round(pt[0])), y=str(round(pt[1])))
        if sub.get('close'):
            E.SubElement(p, q('a', 'close'))
    if fill_clr:
        fill(pr, fill_clr)
    else:
        no_fill(pr)
    if stroke_clr:
        stroke(sp, stroke_clr, stroke_w)
    return sp


def make_text_shape(nextid, name_str, x, y, w, h, text, *, sz_px=20, color='1C2733', bold=False, align='l', anchor='ctr', typeface='Noto Sans CJK SC'):
    sp = E.Element(q('p', 'sp'))
    nv = E.SubElement(sp, q('p', 'nvSpPr'))
    E.SubElement(nv, q('p', 'cNvPr'), id=str(nextid), name=f'{name_str}-{nextid}')
    E.SubElement(nv, q('p', 'cNvSpPr'), txBox='1')
    E.SubElement(nv, q('p', 'nvPr'))
    pr = E.SubElement(sp, q('p', 'spPr'))
    xf = E.SubElement(pr, q('a', 'xfrm'))
    E.SubElement(xf, q('a', 'off'), x=str(round(x * EMU)), y=str(round(y * EMU)))
    E.SubElement(xf, q('a', 'ext'), cx=str(round(w * EMU)), cy=str(round(h * EMU)))
    geom = E.SubElement(pr, q('a', 'prstGeom'), prst='rect')
    E.SubElement(geom, q('a', 'avLst'))
    no_fill(pr)
    tb = E.SubElement(sp, q('p', 'txBody'))
    E.SubElement(tb, q('a', 'bodyPr'), wrap='square', lIns='0', tIns='0', rIns='0', bIns='0', anchor=anchor)
    E.SubElement(tb, q('a', 'lstStyle'))
    for line in str(text).split('\n'):
        p = E.SubElement(tb, q('a', 'p'))
        pPr = E.SubElement(p, q('a', 'pPr'), algn=align)
        spc = E.SubElement(pPr, q('a', 'lnSpc'))
        E.SubElement(spc, q('a', 'spcPct'), val='125000')
        r = E.SubElement(p, q('a', 'r'))
        rp = E.SubElement(r, q('a', 'rPr'), lang='zh-CN', sz=str(round(sz_px * 75)), b='1' if bold else '0', dirty='0')
        fill(rp, color)
        for tag in ['latin', 'ea', 'cs']:
            E.SubElement(rp, q('a', tag), typeface=typeface)
        E.SubElement(r, q('a', 't')).text = line
        E.SubElement(p, q('a', 'endParaRPr'), lang='zh-CN', sz=str(round(sz_px * 75)))
    return sp


def infer_semantic_icon(requested, text_hint='', used_icons=None):
    """Determine clean semantic icon type from requested icon name and nearby text context."""
    req = (requested or '').strip().lower()
    if req in {'none', 'blank', 'empty', 'off'}:
        return 'none'
    explicit_domain = {
        'dna', 'primer', 'gene', 'locus', 'pcr', 'lab', 'tube', 'gel', 'peak',
        'table', 'matrix', 'ledger', 'chart', 'bar', 'stats', 'scatter', 'trend',
        'filter', 'screen', 'check', 'verified', 'warning', 'alert', 'workflow',
        'process', 'layers', 'stack', 'comparison', 'location', 'site', 'document',
        'camera', 'tree', 'leaf', 'calendar', 'database', 'compass', 'search',
    }
    if req in explicit_domain:
        if used_icons is not None:
            used_icons.add(req)
        return req
    # Real-time material adaptation: match specific functional facets before broad domain words,
    # Prefer another relevant match when available; never change meaning just to deduplicate.
    txt = str(text_hint).casefold()
    candidates = []
    rules = [
        ('camera', ['相机', '红外监测', '影像', 'camera', 'photograph']),
        ('tree', ['植被', '森林结构', '乔木', 'vegetation', 'canopy']),
        ('leaf', ['叶片', '叶绿素', '光合作用', 'photosynthesis']),
        ('calendar', ['时间窗', '同期', '轮次', 'calendar']),
        ('database', ['数据库', '数据归档', 'database']),
        ('warning', ['问题', '冲突', '矛盾', '异常', '偏离', '缺失', '错误', '雷同', '不一致', '注意', '失衡', '淘汰', '失败']),
        ('filter', ['初筛', '筛选', '筛查', '过滤', '剔除', '排除', '入选']),
        ('pcr', ['PCR', '扩增', '退火', '体系', '上机', '电泳', '提取', '试剂', '粪便', '分池', '单管', '多重', '探针', '毛细管']),
        ('table', ['表 ', '表1', '表2', '台账', '矩阵', '分组', '清单', '汇总', '计数', '编号', '对照', 'Kit']),
        ('chart', ['均值', '分布', '完整率', '剖面', '相关', '统计', '效能', '功效', 'PID', '曲线', '散点', '趋势', 'HE', 'HO']),
        ('check', ['核对', '检验', '验证', '复核', '复算', '平衡', '判读', '定稿', '完成', '一致', 'HWE', '合规', '确认']),
        ('location', ['地点', '猎场', '阿尔卑斯', '保护区', '生境', '空间', '野外', '样地', '采样']),
        ('workflow', ['流程', '步骤', '阶段', '路径', '路线', '顺序', '闭环', '衔接', '决策', '模型']),
        ('dna', ['引物', '微卫星', '位点', '等位', '基因', '序列', '多态', '单态', '连锁', '杂合', 'DNA', 'SSR', 'SNP']),
    ]
    for icon_name, kw_list in rules:
        if any(k.casefold() in txt for k in kw_list) and icon_name not in candidates:
            candidates.append(icon_name)
    mapping = {
        'map': 'location',
        'grid': 'table',
        'clipboard': 'document',
        'database': 'layers',
        'network': 'workflow',
        'compass': 'compass',
        'search': 'search',
        'chart': 'chart',
        'check': 'check',
    }
    mapped = mapping.get(req, 'document')
    if not candidates or req in mapping:
        if mapped not in candidates:
            candidates.append(mapped)
    if used_icons is not None:
        for cand in candidates:
            if cand not in used_icons:
                used_icons.add(cand)
                return cand
    chosen = candidates[0]
    if used_icons is not None:
        used_icons.add(chosen)
    return chosen


def build_vector_icon(nextid, icon_type, b, fg_color):
    """Build crisp, minimalist wireframe vector icon shapes inside bounding box `b = (x, y, w, h)`."""
    x, y, w, h = b
    s = min(w, h)
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = cx - s / 2, cy - s / 2
    sw = max(1.5, min(2.0, s * 0.058))
    shapes = []
    if icon_type == 'none':
        return shapes, nextid

    if icon_type == 'camera':
        paths=[{'pts':[(200,160),(800,160),(800,880),(200,880)],'close':True},
               {'pts':[(320,80),(680,80),(680,160),(320,160)],'close':False}]
        shapes.append(make_custom_path_shape(nextid,'icon-camera-body',x0,y0,s,s,paths,stroke_clr=fg_color,stroke_w=sw));nextid+=1
        for yy,diameter in [(300,.36),(680,.16)]:
            shapes.append(make_shape(nextid,'icon-camera-lens',cx-s*diameter/2,y0+s*yy/1000,s*diameter,s*diameter,prst='ellipse',stroke_clr=fg_color,stroke_w=sw));nextid+=1
    elif icon_type == 'tree':
        paths=[{'pts':[(500,80),(220,410),(350,410),(130,680),(440,680),(440,920),(560,920),(560,680),(870,680),(650,410),(780,410)],'close':True}]
        shapes.append(make_custom_path_shape(nextid,'icon-tree',x0,y0,s,s,paths,stroke_clr=fg_color,stroke_w=sw));nextid+=1
    elif icon_type == 'leaf':
        paths=[{'pts':[(200,760),(180,500),(280,280),(500,150),(850,100),(840,430),(700,650),(470,780),(200,760)],'close':True},
               {'pts':[(130,900),(730,250)],'close':False},
               {'pts':[(420,580),(390,340)],'close':False},
               {'pts':[(420,580),(650,570)],'close':False}]
        shapes.append(make_custom_path_shape(nextid,'icon-leaf',x0,y0,s,s,paths,stroke_clr=fg_color,stroke_w=sw));nextid+=1
    elif icon_type == 'calendar':
        paths=[{'pts':[(140,180),(860,180),(860,860),(140,860)],'close':True},
               {'pts':[(140,380),(860,380)],'close':False},
               {'pts':[(320,80),(320,280)],'close':False},
               {'pts':[(680,80),(680,280)],'close':False}]
        shapes.append(make_custom_path_shape(nextid,'icon-calendar',x0,y0,s,s,paths,stroke_clr=fg_color,stroke_w=sw));nextid+=1
        for xx in [.28,.48,.68]:
            for yy in [.49,.69]:
                shapes.append(make_shape(nextid,'icon-calendar-day',x0+s*xx,y0+s*yy,s*.08,s*.08,stroke_clr=fg_color,stroke_w=sw));nextid+=1
    elif icon_type == 'database':
        for yy in [.12,.38,.64]:
            shapes.append(make_shape(nextid,'icon-database-ring',x0+s*.16,y0+s*yy,s*.68,s*.22,prst='ellipse',stroke_clr=fg_color,stroke_w=sw));nextid+=1
        paths=[{'pts':[(160,230),(160,750)],'close':False},{'pts':[(840,230),(840,750)],'close':False}]
        shapes.append(make_custom_path_shape(nextid,'icon-database-sides',x0,y0,s,s,paths,stroke_clr=fg_color,stroke_w=sw));nextid+=1
    elif icon_type in {'dna', 'primer', 'gene', 'locus'}:
        # Crisp double-helix waves + base-pair rungs
        strand1 = [(180, 120), (350, 180), (650, 420), (820, 500), (650, 580), (350, 820), (180, 880)]
        strand2 = [(820, 120), (650, 180), (350, 420), (180, 500), (350, 580), (650, 820), (820, 880)]
        rungs = [
            {'pts': [(280, 220), (720, 220)], 'close': False},
            {'pts': [(360, 340), (640, 340)], 'close': False},
            {'pts': [(360, 660), (640, 660)], 'close': False},
            {'pts': [(280, 780), (720, 780)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(
            nextid, 'icon-dna', x0, y0, s, s,
            [{'pts': strand1, 'close': False}, {'pts': strand2, 'close': False}] + rungs,
            stroke_clr=fg_color, stroke_w=sw
        ))
        nextid += 1
    elif icon_type in {'pcr', 'lab', 'tube', 'gel', 'peak'}:
        # Clean laboratory tube / flask with cap and meniscus line
        subpaths = [
            {'pts': [(240, 140), (760, 140), (760, 250), (240, 250)], 'close': True},
            {'pts': [(310, 250), (310, 620), (500, 880), (690, 620), (690, 250)], 'close': False},
            {'pts': [(330, 520), (670, 520)], 'close': False},
            {'pts': [(380, 650), (620, 650)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-pcr', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'table', 'matrix', 'ledger', 'grid'}:
        # Clean 2x2 data table grid
        subpaths = [
            {'pts': [(140, 160), (860, 160), (860, 840), (140, 840)], 'close': True},
            {'pts': [(140, 380), (860, 380)], 'close': False},
            {'pts': [(140, 610), (860, 610)], 'close': False},
            {'pts': [(460, 160), (460, 840)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-table', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'chart', 'bar', 'stats', 'scatter', 'trend'}:
        # Clean 3-bar chart on axis
        subpaths = [
            {'pts': [(140, 840), (860, 840)], 'close': False},
            {'pts': [(220, 840), (220, 520), (350, 520), (350, 840)], 'close': False},
            {'pts': [(435, 840), (435, 340), (565, 340), (565, 840)], 'close': False},
            {'pts': [(650, 840), (650, 180), (780, 180), (780, 840)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-chart', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'filter', 'screen'}:
        # Clean funnel icon
        subpaths = [
            {'pts': [(140, 180), (860, 180), (580, 520), (580, 840), (420, 760), (420, 520)], 'close': True},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-filter', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'warning', 'alert'}:
        # Clean triangle + exclamation
        subpaths = [
            {'pts': [(500, 140), (880, 820), (120, 820)], 'close': True},
            {'pts': [(500, 380), (500, 600)], 'close': False},
            {'pts': [(485, 700), (515, 700), (515, 730), (485, 730)], 'close': True},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-warning', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'search', 'inspect'}:
        # Clean magnifier circle + handle (never a solid blob)
        shapes.append(make_shape(nextid, 'icon-search-ring', x0 + s * 0.14, y0 + s * 0.14, s * 0.54, s * 0.54, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_custom_path_shape(
            nextid, 'icon-search-handle', x0, y0, s, s,
            [{'pts': [(610, 610), (850, 850)], 'close': False}],
            stroke_clr=fg_color, stroke_w=sw * 1.15
        ))
        nextid += 1
    elif icon_type in {'location', 'site', 'map'}:
        # Clean map pin outline + center circle
        pin_pts = [(500, 860), (240, 520), (200, 380), (270, 220), (500, 140), (730, 220), (800, 380), (760, 520)]
        shapes.append(make_custom_path_shape(
            nextid, 'icon-location', x0, y0, s, s,
            [{'pts': pin_pts, 'close': True}],
            stroke_clr=fg_color, stroke_w=sw
        ))
        nextid += 1
        shapes.append(make_shape(nextid, 'icon-location-dot', cx - s * 0.12, y0 + s * 0.27, s * 0.24, s * 0.24, prst='ellipse', stroke_clr=fg_color, stroke_w=sw * 0.9))
        nextid += 1
    elif icon_type in {'layers', 'stack', 'database'}:
        # Clean 3-layer isometric stack
        subpaths = [
            {'pts': [(500, 160), (860, 320), (500, 480), (140, 320)], 'close': True},
            {'pts': [(140, 500), (500, 660), (860, 500)], 'close': False},
            {'pts': [(140, 680), (500, 840), (860, 680)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-layers', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'workflow', 'process', 'network', 'comparison'}:
        # Clean 3-node connected workflow graph
        shapes.append(make_shape(nextid, 'icon-wf-1', x0 + s * 0.12, y0 + s * 0.16, s * 0.26, s * 0.26, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_shape(nextid, 'icon-wf-2', x0 + s * 0.62, y0 + s * 0.16, s * 0.26, s * 0.26, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_shape(nextid, 'icon-wf-3', x0 + s * 0.37, y0 + s * 0.60, s * 0.26, s * 0.26, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_custom_path_shape(
            nextid, 'icon-wf-edges', x0, y0, s, s,
            [
                {'pts': [(380, 290), (620, 290)], 'close': False},
                {'pts': [(310, 400), (430, 620)], 'close': False},
                {'pts': [(690, 400), (570, 620)], 'close': False},
            ],
            stroke_clr=fg_color, stroke_w=sw * 0.9
        ))
        nextid += 1
    elif icon_type in {'document', 'clipboard'}:
        subpaths = [
            {'pts': [(200, 160), (800, 160), (800, 860), (200, 860)], 'close': True},
            {'pts': [(320, 360), (680, 360)], 'close': False},
            {'pts': [(320, 520), (680, 520)], 'close': False},
            {'pts': [(320, 680), (560, 680)], 'close': False},
        ]
        shapes.append(make_custom_path_shape(nextid, 'icon-doc', x0, y0, s, s, subpaths, stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
    elif icon_type in {'compass', 'direction'}:
        shapes.append(make_shape(nextid, 'icon-compass-ring', x0 + s * 0.12, y0 + s * 0.12, s * 0.76, s * 0.76, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_custom_path_shape(
            nextid, 'icon-compass-needle', x0, y0, s, s,
            [{'pts': [(500, 260), (630, 500), (500, 740), (370, 500)], 'close': True}],
            stroke_clr=fg_color, stroke_w=sw * 0.9
        ))
        nextid += 1
    else:
        # Default: crisp check badge (circle + checkmark)
        shapes.append(make_shape(nextid, 'icon-check-ring', x0 + s * 0.12, y0 + s * 0.12, s * 0.76, s * 0.76, prst='ellipse', stroke_clr=fg_color, stroke_w=sw))
        nextid += 1
        shapes.append(make_custom_path_shape(
            nextid, 'icon-check-mark', x0, y0, s, s,
            [{'pts': [(310, 520), (450, 660), (700, 360)], 'close': False}],
            stroke_clr=fg_color, stroke_w=sw * 1.15
        ))
        nextid += 1
    return shapes, nextid


def replace_icon_slot(tree, shapes_by_id, id_list, icon_type, fg_color, nextid, *, box_override=None):
    """Replace an existing cluster of icon shapes (`id_list`) with a clean vector icon."""
    existing = [shapes_by_id[i] for i in id_list if i in shapes_by_id and shapes_by_id[i] in list(tree)]
    if not existing and not box_override:
        return nextid
    if box_override:
        b = box_override
    else:
        boxes = [box(s) for s in existing if box(s)]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        b = (x0, y0, x1 - x0, y1 - y0)
    insert_idx = list(tree).index(existing[0]) if existing else len(tree)
    for s in existing:
        tree.remove(s)
    new_shapes, nextid = build_vector_icon(nextid, icon_type, b, fg_color)
    for offset, ns in enumerate(new_shapes):
        tree.insert(insert_idx + offset, ns)
    return nextid


def prepare_adaptive_geometry(root, layout, palette, page, document, fill_style):
    """Restructure slide geometry in adaptive mode before solid/light styling:
    - Remove stiff oversized body icons and unrelated stock ecology bitmaps.
    - Reclaim card space for natural text, tables, and charts.
    - Build native editable visual cards when custom images are not provided.
    """
    primary = palette['primary'][1:]
    secondary = palette['secondary'][1:]
    accent = palette['accent'][1:]
    tint = palette['tint'][1:]
    tree = root.find('p:cSld/p:spTree', NS)
    ids = [int(n.get('id')) for n in root.findall('.//p:cNvPr', NS) if (n.get('id') or '').isdigit()]
    nextid = max(ids, default=200) + 10

    shapes_by_id = {sp.find('p:nvSpPr/p:cNvPr', NS).get('id'): sp for sp in tree.findall('p:sp', NS)}
    pics_by_id = {p.find('p:nvPicPr/p:cNvPr', NS).get('id'): p for p in tree.findall('p:pic', NS)}
    gfs_by_id = {g.find('p:nvGraphicFramePr/p:cNvPr', NS).get('id'): g for g in tree.findall('p:graphicFrame', NS)}

    def remove_ids(id_set):
        for sid in id_set:
            sp = shapes_by_id.get(str(sid))
            if sp is not None and sp in list(tree):
                tree.remove(sp)

    def remove_pic(pid):
        p = pics_by_id.get(str(pid))
        if p is not None and p in list(tree):
            tree.remove(p)

    has_landscape = bool(page.get('image') or page.get('images') or (document.get('illustrations') or {}).get('landscape'))
    has_forest = bool(page.get('image') or page.get('images') or (document.get('illustrations') or {}).get('forest'))

    if layout == 'L1':
        # Remove giant duplicate body icons inside the 4 stage cards
        remove_ids({'11', '12', '13', '14', '15', '16', '17', '18'})
        remove_ids({'36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46', '47'})
        remove_ids({'58', '59', '60'})
        remove_ids({'82', '83', '84', '85', '86', '87', '88', '89', '90', '91', '92'})
        # Expand descriptions, table, chart, and bullet lists to full card width
        if '10' in shapes_by_id:
            set_box(shapes_by_id['10'], 42, 152, 378, 52)
        if '19' in gfs_by_id:
            set_box(gfs_by_id['19'], 40, 212, 380, 72)
        if '35' in shapes_by_id:
            set_box(shapes_by_id['35'], 862, 152, 378, 44)
        if '50' in shapes_by_id:
            set_box(shapes_by_id['50'], 862, 192, 150, 18)
        if '48' in gfs_by_id:
            set_box(gfs_by_id['48'], 860, 208, 382, 118)
        if '49' in shapes_by_id:
            set_box(shapes_by_id['49'], 980, 327, 170, 18)
        if '57' in shapes_by_id:
            set_box(shapes_by_id['57'], 862, 440, 378, 50)
        for idx, (dot_id, txt_id) in enumerate([('61', '62'), ('63', '64'), ('65', '66')]):
            yy = 504 + idx * 38
            if dot_id in shapes_by_id:
                set_box(shapes_by_id[dot_id], 866, yy + 11, 6, 6)
                fill(shapes_by_id[dot_id].find('p:spPr', NS), primary)
            if txt_id in shapes_by_id:
                set_box(shapes_by_id[txt_id], 882, yy, 356, 32)
        if '81' in shapes_by_id:
            set_box(shapes_by_id['81'], 42, 440, 378, 50)
        for idx, (dot_id, txt_id) in enumerate([('93', '94'), ('95', '96'), ('97', '98')]):
            yy = 504 + idx * 38
            if dot_id in shapes_by_id:
                set_box(shapes_by_id[dot_id], 46, yy + 11, 6, 6)
                fill(shapes_by_id[dot_id].find('p:spPr', NS), primary)
            if txt_id in shapes_by_id:
                set_box(shapes_by_id[txt_id], 62, yy, 356, 32)
        # Position 4 central ring labels cleanly inside ring quadrants
        ring_coords = {
            '104': (575, 240, 130, 30),
            '118': (755, 374, 48, 62),
            '123': (575, 520, 130, 30),
            '136': (477, 374, 48, 62),
        }
        for sid, (rx, ry, rw, rh) in ring_coords.items():
            if sid in shapes_by_id:
                set_box(shapes_by_id[sid], rx, ry, rw, rh)
                set_vcenter(shapes_by_id[sid], 'ctr')

    elif layout == 'L2':
        # Remove decorative filler icons and stock forest patch in top 3 observation cards
        remove_ids({'16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '42', '43', '44'})
        if not has_forest:
            remove_pic('34')
        for idx, (title_id, body_id) in enumerate([('14', '15'), ('32', '33'), ('40', '41')]):
            cx = 76 + idx * 397
            if title_id in shapes_by_id:
                set_box(shapes_by_id[title_id], cx + 64, 105, 304, 34)
            if body_id in shapes_by_id:
                set_box(shapes_by_id[body_id], cx + 24, 154, 344, 78)
                set_vcenter(shapes_by_id[body_id], 'ctr')
                bar = make_shape(nextid, 'obs-accent', cx + 12, 160, 4, 66, fill_clr=primary)
                nextid += 1
                tree.insert(list(tree).index(shapes_by_id[body_id]), bar)
        # Prevent bottom chart ticks from touching external X-axis titles
        if '86' in gfs_by_id:
            set_box(gfs_by_id['86'], 78, 452, 574, 168)
        if '93' in gfs_by_id:
            set_box(gfs_by_id['93'], 674, 452, 574, 168)
        if '91' in shapes_by_id:
            set_box(shapes_by_id['91'], 220, 622, 290, 20)
        if '94' in shapes_by_id:
            set_box(shapes_by_id['94'], 816, 622, 290, 20)

    elif layout == 'L4':
        # Keep clear gap between table (y=282..574) and caption id=39 (y=588)
        if '38' in gfs_by_id:
            set_box(gfs_by_id['38'], 38, 282, 757, 290)
        if '39' in shapes_by_id:
            set_box(shapes_by_id['39'], 42, 588, 740, 28)

    elif layout == 'L5':
        # Cover: prevent title from overlapping right panel/image
        if '3' in shapes_by_id:
            set_box(shapes_by_id['3'], 42, 174, 592, 196)
            max_line = max((visual_char_len(ln) for ln in page.get('lines', [page.get('title', '')])), default=8)
            target_px = 46 if max_line > 10.5 else 52 if max_line > 8.5 else 60
            for rp in shapes_by_id['3'].findall('.//a:rPr', NS) + shapes_by_id['3'].findall('.//a:defRPr', NS):
                rp.set('sz', str(round(target_px * 75)))
        if '4' in shapes_by_id:
            set_box(shapes_by_id['4'], 42, 396, 580, 78)
        if '5' in shapes_by_id:
            set_box(shapes_by_id['5'], 44, 486, 96, 5)
        if has_landscape:
            if '22' in pics_by_id:
                set_box(pics_by_id['22'], 664, 44, 576, 596)
        else:
            remove_pic('22')
            # Build a clean native editable Research Overview Card on the right
            card_x, card_y, card_w, card_h = 668, 68, 568, 576
            tree.append(make_shape(nextid, 'cover-card-bg', card_x, card_y, card_w, card_h, fill_clr='FFFFFF', stroke_clr=primary, stroke_w=1.4))
            nextid += 1
            tree.append(make_shape(nextid, 'cover-card-hdr', card_x, card_y, card_w, 50, fill_clr=primary))
            nextid += 1
            hdr_title = page.get('card_title', '核心信息速览  ·  KEY HIGHLIGHTS')
            tree.append(make_text_shape(nextid, 'cover-card-hdr-txt', card_x + 22, card_y + 8, card_w - 44, 34, hdr_title, sz_px=20, color='FFFFFF', bold=True))
            nextid += 1
            highlights = page.get('highlights')
            if not highlights:
                # Auto-derive highlights from the deck's outline (L6) or content slides
                highlights = []
                l6 = next((s for s in document.get('slides', []) if s.get('layout') == 'L6' and s.get('chapters')), None)
                if l6:
                    for ch in l6['chapters'][:4]:
                        highlights.append({
                            'label': ch.get('title', ''),
                            'value': ch.get('focus', ''),
                            'detail': ch.get('body', ''),
                        })
                else:
                    for s in document.get('slides', [])[1:5]:
                        highlights.append({
                            'label': s.get('title', ''),
                            'value': '',
                            'detail': '',
                        })
            n_items = max(1, min(4, len(highlights)))
            avail_h = card_h - 76
            row_h = avail_h // n_items
            for idx, item in enumerate(highlights[:n_items]):
                iy = card_y + 64 + idx * row_h
                ih = row_h - 12
                tree.append(make_shape(nextid, f'cover-hl-box-{idx}', card_x + 20, iy, card_w - 40, ih, fill_clr=tint, stroke_clr=secondary, stroke_w=0.8))
                nextid += 1
                bar_clr = accent if idx == n_items - 1 else primary
                tree.append(make_shape(nextid, f'cover-hl-bar-{idx}', card_x + 20, iy, 5, ih, fill_clr=bar_clr))
                nextid += 1
                badge_txt = f'0{idx+1}  {item.get("label", "")}'
                val_txt = item.get('value', '')
                det_txt = item.get('detail', '')
                heading = f'{badge_txt}  ·  {val_txt}' if val_txt else badge_txt
                if visual_char_len(heading) * 19 > card_w - 68:
                    raise ValueError(f'L5 highlight {idx+1} heading exceeds capacity; provide a shorter complete label/value')
                if det_txt and (math.ceil(visual_char_len(det_txt) * 17 / (card_w - 68)) * 17 * 1.25 > ih - 46):
                    raise ValueError(f'L5 highlight {idx+1} detail exceeds capacity; shorten or split explicitly')
                tree.append(make_text_shape(nextid, f'cover-hl-title-{idx}', card_x + 38, iy + 8, card_w - 68, 28, f'{badge_txt}  ·  {val_txt}' if val_txt else badge_txt, sz_px=19, color=primary, bold=True))
                nextid += 1
                if det_txt:
                    tree.append(make_text_shape(nextid, f'cover-hl-det-{idx}', card_x + 38, iy + 40, card_w - 68, ih - 46, det_txt, sz_px=17, color='1C2733', bold=False))
                    nextid += 1

    elif layout == 'L6':
        # Remove duplicate 66x66 left icons and 75x75 right icons in each TOC row
        remove_ids({
            '12', '13', '17', '18', '19', '20',
            '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35',
            '39', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '50',
            '54', '55', '56', '57', '58', '62', '63', '64', '65', '66',
            '70', '71', '72', '76', '77', '78',
        })
        rows_spec = [
            (98, '10', '11', '14', '15', '16'),
            (237, '22', '23', '36', '37', '38'),
            (376, '52', '53', '59', '60', '61'),
            (515, '68', '69', '73', '74', '75'),
        ]
        for idx, (ry, box_id, num_id, t_id, f_id, b_id) in enumerate(rows_spec):
            if box_id in shapes_by_id:
                set_box(shapes_by_id[box_id], 304, ry + 38, 52, 52)
            if num_id in shapes_by_id:
                set_box(shapes_by_id[num_id], 304, ry + 38, 52, 52)
                set_vcenter(shapes_by_id[num_id], 'ctr')
            bar = make_shape(nextid, f'toc-bar-{idx}', 374, ry + 20, 4, 88, fill_clr=primary)
            nextid += 1
            tree.append(bar)
            if t_id in shapes_by_id:
                set_box(shapes_by_id[t_id], 394, ry + 14, 816, 36)
            if f_id in shapes_by_id:
                set_box(shapes_by_id[f_id], 394, ry + 53, 816, 30)
            if b_id in shapes_by_id:
                set_box(shapes_by_id[b_id], 394, ry + 86, 816, 28)

    elif layout == 'L7':
        # Section divider: support dynamic active chapter (0..3) and clean right roadmap card
        active_idx = page.get('active', 2)
        remove_ids({
            '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17',
            '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30',
            '32', '33', '34', '35', '36', '39', '40', '41',
        })
        ch_ids = ['18', '31', '37', '42']
        for i, cid in enumerate(ch_ids):
            if cid in shapes_by_id:
                set_box(shapes_by_id[cid], 48 + i * 310, 646, 250, 32)
                is_act = (i == active_idx)
                text_color(shapes_by_id[cid], primary if is_act else '5A6B7C')
                for rp in shapes_by_id[cid].findall('.//a:rPr', NS):
                    rp.set('b', '1' if is_act else '0')
        if '38' in shapes_by_id:
            set_box(shapes_by_id['38'], 48 + active_idx * 310, 682, 205, 4)
        if '4' in shapes_by_id:
            set_box(shapes_by_id['4'], 40, 224, 580, 170)
            max_line = max((visual_char_len(ln) for ln in page.get('lines', [page.get('title', '')])), default=8)
            if max_line > 8.5:
                for rp in shapes_by_id['4'].findall('.//a:rPr', NS) + shapes_by_id['4'].findall('.//a:defRPr', NS):
                    rp.set('sz', str(round(48 * 75)))
        if '5' in shapes_by_id:
            set_box(shapes_by_id['5'], 40, 424, 580, 100)
        if has_landscape:
            if '45' in pics_by_id:
                set_box(pics_by_id['45'], 656, 72, 576, 536)
        else:
            remove_pic('45')
            rx, ry, rw, rh = 668, 76, 568, 516
            tree.append(make_shape(nextid, 'sec-card-bg', rx, ry, rw, rh, fill_clr='FFFFFF', stroke_clr=primary, stroke_w=1.4))
            nextid += 1
            tree.append(make_shape(nextid, 'sec-card-hdr', rx, ry, rw, 48, fill_clr=primary))
            nextid += 1
            tree.append(make_text_shape(nextid, 'sec-card-hdr-txt', rx + 22, ry + 7, rw - 44, 34, '章节导航  ·  SECTION ROADMAP', sz_px=20, color='FFFFFF', bold=True))
            nextid += 1
            chapters = page.get('chapters', [])
            for idx, ch_name in enumerate(chapters[:4]):
                cy = ry + 66 + idx * 108
                is_act = (idx == active_idx)
                bg_c = primary if is_act else tint
                fg_c = 'FFFFFF' if is_act else '1C2733'
                sub_c = 'FFFFFF' if is_act else primary
                tree.append(make_shape(nextid, f'sec-ch-box-{idx}', rx + 24, cy, rw - 48, 100, fill_clr=bg_c, stroke_clr=primary if is_act else secondary, stroke_w=1.2 if is_act else 0.8))
                nextid += 1
                if is_act:
                    tree.append(make_shape(nextid, f'sec-ch-accent-{idx}', rx + 24, cy, 8, 100, fill_clr=accent))
                    nextid += 1
                label_prefix = '当前章节' if is_act else f'第 0{idx+1} 章'
                tree.append(make_text_shape(nextid, f'sec-ch-txt-{idx}', rx + 46, cy + 14, rw - 88, 34, f'0{idx+1}  {ch_name}', sz_px=22, color=fg_c, bold=True))
                nextid += 1
                sub_txt = page.get('intro', '') if is_act else label_prefix
                tree.append(make_text_shape(nextid, f'sec-ch-sub-{idx}', rx + 46, cy + 45, rw - 88, 50, sub_txt, sz_px=17, color=sub_c, bold=False))
                nextid += 1

    elif layout == 'L8':
        # Remove stock forest cutout and duplicate icons in left column
        remove_ids({'27', '28', '29', '44', '45', '46', '47'})
        if not has_forest:
            remove_pic('37')
        for idx, (t_id, b_id) in enumerate([('25', '26'), ('35', '36'), ('42', '43')]):
            iy = 152 + idx * 160
            if t_id in shapes_by_id:
                set_box(shapes_by_id[t_id], 98, iy, 198, 34)
            if b_id in shapes_by_id:
                set_box(shapes_by_id[b_id], 40, iy + 40, 256, 76)

    elif layout == 'L9':
        if not has_forest:
            for pid in ['7', '9', '17', '19', '20', '21', '22']:
                remove_pic(pid)
            # Replace stock forest bitmaps with clean native editable comparison cards
            cards_spec = [
                ('10', 46, 222, 218, 126, tint, secondary),
                ('11', 358, 222, 246, 126, 'FFFFFF', primary),
                ('23', 670, 222, 218, 126, tint, secondary),
                ('24', 982, 222, 246, 126, 'FFFFFF', primary),
            ]
            for tid, cx, cy, cw, ch, fclr, sclr in cards_spec:
                if tid in shapes_by_id:
                    card = make_shape(nextid, f'l9-state-card-{tid}', cx, cy, cw, ch, fill_clr=fclr, stroke_clr=sclr, stroke_w=1.3)
                    nextid += 1
                    bar = make_shape(nextid, f'l9-state-bar-{tid}', cx, cy, cw, 6, fill_clr=sclr)
                    nextid += 1
                    idx_pos = list(tree).index(shapes_by_id[tid])
                    tree.insert(idx_pos, card)
                    tree.insert(idx_pos + 1, bar)
                    set_box(shapes_by_id[tid], cx + 14, cy + 18, cw - 28, ch - 30)
                    set_vcenter(shapes_by_id[tid], 'ctr')

    elif layout == 'L10':
        if '84' in shapes_by_id:
            set_box(shapes_by_id['84'], 1014.8, 360, 170, 24)

    elif layout == 'L12':
        # Remove the 6 giant 100x100 duplicate body icons and expand card text to full width
        remove_ids({
            '10', '11', '12', '13',
            '29', '30', '31', '32', '33', '34', '35',
            '48', '49', '50', '51',
            '72', '73', '74', '75', '76', '77', '78', '79', '80', '81', '82', '83',
            '97', '98', '99', '100', '101',
            '113', '114', '115',
        })
        cards_l12 = [
            (24, 94, '14', '15', '16', '17', '18'),
            (441, 94, '36', '37', '38', '39', '40'),
            (858, 94, '52', '53', '54', '55', '56'),
            (24, 368, '84', '85', '86', '87', '88'),
            (441, 368, '102', '103', '104', '105', '106'),
            (858, 368, '116', '117', '118', '119', '120'),
        ]
        for idx, (cx, cy, lbl1, txt1, line_id, lbl2, txt2) in enumerate(cards_l12):
            bar1 = make_shape(nextid, f'l12-bar1-{idx}', cx + 16, cy + 56, 4, 80, fill_clr=secondary)
            nextid += 1
            bar2 = make_shape(nextid, f'l12-bar2-{idx}', cx + 16, cy + 158, 4, 80, fill_clr=primary)
            nextid += 1
            tree.append(bar1)
            tree.append(bar2)
            if lbl1 in shapes_by_id:
                set_box(shapes_by_id[lbl1], cx + 28, cy + 52, 350, 26)
            if txt1 in shapes_by_id:
                set_box(shapes_by_id[txt1], cx + 28, cy + 80, 350, 56)
                set_vcenter(shapes_by_id[txt1], 'ctr')
            if line_id in shapes_by_id:
                set_box(shapes_by_id[line_id], cx + 20, cy + 146, 360, 0)
            if lbl2 in shapes_by_id:
                set_box(shapes_by_id[lbl2], cx + 28, cy + 154, 350, 26)
            if txt2 in shapes_by_id:
                set_box(shapes_by_id[txt2], cx + 28, cy + 182, 350, 56)
                set_vcenter(shapes_by_id[txt2], 'ctr')

    elif layout == 'L13':
        # Remove giant 72x72 before-icons and 78x78 after-icons, replace with clean native flow cards
        remove_ids({
            '8', '9', '10', '11', '16', '17', '18', '19', '20',
            '38', '39', '40', '41', '42', '47', '48', '49', '50', '51', '52', '53', '54', '55', '56', '57', '58',
            '69', '70', '75', '76', '77',
        })
        lanes_spec = [
            (100, '6', '7', '12', '13', '14', '15', '21'),
            (269, '36', '37', '43', '44', '45', '46', '59'),
            (438, '67', '68', '71', '72', '73', '74', '78'),
        ]
        for idx, (ly, lbl_id, q_id, bef_id, arr_id, act_id, det_id, aft_id) in enumerate(lanes_spec):
            if lbl_id in shapes_by_id:
                set_box(shapes_by_id[lbl_id], 28, ly + 66, 146, 36)
                set_vcenter(shapes_by_id[lbl_id], 'ctr')
            if q_id in shapes_by_id:
                question = shapes_by_id[q_id]
                set_box(question, 28, ly + 98, 146, 58)
                set_vcenter(question, 'ctr')
                # Keep the quoted question together instead of orphaning its closing quote.
                paragraph = question.find('p:txBody/a:p', NS)
                run = paragraph.find('a:r', NS) if paragraph is not None else None
                t = run.find('a:t', NS) if run is not None else None
                if t is not None and (t.text or '').startswith('回答“'):
                    tail = copy.deepcopy(run)
                    tail.find('a:t', NS).text = t.text[2:]
                    t.text = t.text[:2]
                    pos = list(paragraph).index(run)
                    paragraph.insert(pos + 1, E.Element(q('a', 'br')))
                    paragraph.insert(pos + 2, tail)
            if bef_id in shapes_by_id:
                bcard = make_shape(nextid, f'l13-before-card-{idx}', 196, ly + 20, 218, 115, fill_clr='FFFFFF', stroke_clr=secondary, stroke_w=1.2)
                nextid += 1
                bbar = make_shape(nextid, f'l13-before-bar-{idx}', 196, ly + 20, 5, 115, fill_clr=secondary)
                nextid += 1
                pos = list(tree).index(shapes_by_id[bef_id])
                tree.insert(pos, bcard)
                tree.insert(pos + 1, bbar)
                set_box(shapes_by_id[bef_id], 210, ly + 28, 194, 98)
                set_vcenter(shapes_by_id[bef_id], 'ctr')
            if arr_id in shapes_by_id:
                set_box(shapes_by_id[arr_id], 433, ly + 20, 426, 115)
            if act_id in shapes_by_id:
                set_box(shapes_by_id[act_id], 456, ly + 34, 366, 38)
            if det_id in shapes_by_id:
                set_box(shapes_by_id[det_id], 456, ly + 76, 366, 36)
            if aft_id in shapes_by_id:
                acard = make_shape(nextid, f'l13-after-card-{idx}', 878, ly + 20, 366, 115, fill_clr=tint, stroke_clr=primary, stroke_w=1.3)
                nextid += 1
                abar = make_shape(nextid, f'l13-after-bar-{idx}', 878, ly + 20, 5, 115, fill_clr=primary)
                nextid += 1
                pos = list(tree).index(shapes_by_id[aft_id])
                tree.insert(pos, acard)
                tree.insert(pos + 1, abar)
                set_box(shapes_by_id[aft_id], 894, ly + 28, 338, 98)
                set_vcenter(shapes_by_id[aft_id], 'ctr')

    elif layout == 'L14':
        # Always remove the 4 floating corner icons stamped over the right panel
        remove_ids({
            '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17',
            '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28',
        })
        if not has_landscape:
            remove_pic('5')
            rx, ry, rw, rh = 706, 52, 526, 466
            tree.append(make_shape(nextid, 'close-card-bg', rx, ry, rw, rh, fill_clr='FFFFFF', stroke_clr=primary, stroke_w=1.4))
            nextid += 1
            tree.append(make_shape(nextid, 'close-card-hdr', rx, ry, rw, 48, fill_clr=primary))
            nextid += 1
            tree.append(make_text_shape(nextid, 'close-card-hdr-txt', rx + 22, ry + 7, rw - 44, 34, '讨论焦点与下一步  ·  DISCUSSION', sz_px=20, color='FFFFFF', bold=True))
            nextid += 1
            anchors = page.get('anchors', [])
            details = list(page.get('anchor_details') or [])
            if not details and page.get('notes'):
                note_txt = str(page.get('notes', '')).strip().rstrip('。')
                if '：' in note_txt:
                    note_txt = note_txt.split('：', 1)[1]
                for sep in ['；', '、', '，', '。']:
                    parts = [p.strip() for p in note_txt.split(sep) if p.strip()]
                    if len(parts) >= len(anchors):
                        details = [p.lstrip('以及').lstrip('和').strip() for p in parts[:len(anchors)]]
                        break
            for idx, anc in enumerate(anchors[:3]):
                cy = ry + 68 + idx * 126
                tree.append(make_shape(nextid, f'close-anc-box-{idx}', rx + 22, cy, rw - 44, 108, fill_clr=tint, stroke_clr=secondary, stroke_w=0.9))
                nextid += 1
                tree.append(make_shape(nextid, f'close-anc-bar-{idx}', rx + 22, cy, 5, 108, fill_clr=accent if idx == 0 else primary))
                nextid += 1
                det = details[idx] if idx < len(details) else ''
                if det:
                    tree.append(make_text_shape(nextid, f'close-anc-title-{idx}', rx + 42, cy + 12, rw - 76, 32, f'0{idx+1}  {anc}', sz_px=21, color=primary, bold=True))
                    nextid += 1
                    tree.append(make_text_shape(nextid, f'close-anc-det-{idx}', rx + 42, cy + 48, rw - 76, 48, det, sz_px=17, color='1C2733', bold=False))
                    nextid += 1
                else:
                    tree.append(make_text_shape(nextid, f'close-anc-title-{idx}', rx + 42, cy + 28, rw - 76, 52, f'0{idx+1}   {anc}', sz_px=23, color=primary, bold=True))
                    nextid += 1


def apply_adaptive_icons(root, layout, palette, page, fill_style):
    """Replace header/node icons with crisp domain-appropriate vector icons in adaptive mode."""
    primary = palette['primary'][1:]
    tree = root.find('p:cSld/p:spTree', NS)
    shapes_by_id = {sp.find('p:nvSpPr/p:cNvPr', NS).get('id'): sp for sp in tree.findall('p:sp', NS)}
    ids = [int(n.get('id')) for n in root.findall('.//p:cNvPr', NS) if (n.get('id') or '').isdigit()]
    nextid = max(ids, default=300) + 10
    hdr_fg = 'FFFFFF' if fill_style == 'solid' else primary

    if layout == 'L1':
        stages = page.get('stages', [])
        slots = [
            (['5', '6', '7', '8'], ['100', '101', '102', '103'], (40, 111, 26, 26), (621, 206, 28, 28)),
            (['22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33'], ['106', '107', '108', '109', '110', '111', '112', '113', '114', '115', '116', '117'], (856, 111, 26, 26), (764, 344, 30, 30)),
            (['53', '54', '55'], ['120', '121', '122'], (856, 398, 26, 26), (625, 490, 30, 30)),
            (['69', '70', '71', '72', '73', '74', '75', '76', '77', '78', '79'], ['125', '126', '127', '128', '129', '130', '131', '132', '133', '134', '135'], (38, 398, 26, 26), (480, 352, 30, 30)),
        ]
        used = set()
        for idx, (hdr_ids, ring_ids, hdr_box, ring_box) in enumerate(slots):
            if idx < len(stages):
                st = stages[idx]
                ic = infer_semantic_icon(st.get('icon'), f"{st.get('title', '')} {st.get('body', '')}", used)
                nextid = replace_icon_slot(tree, shapes_by_id, hdr_ids, ic, hdr_fg, nextid, box_override=hdr_box)
                nextid = replace_icon_slot(tree, shapes_by_id, ring_ids, ic, 'FFFFFF', nextid, box_override=ring_box)

    elif layout == 'L2':
        obs = page.get('observations', [])
        slots = [
            (['10', '11', '12', '13'], (94, 106, 32, 32)),
            (['30', '31'], (491, 106, 32, 32)),
            (['36', '37', '38', '39'], (888, 106, 32, 32)),
        ]
        used_obs = set()
        for idx, (id_list, b_ovr) in enumerate(slots):
            if idx < len(obs):
                ob = obs[idx]
                ic = infer_semantic_icon(ob.get('icon'), f"{ob.get('title', '')} {ob.get('body', '')}", used_obs)
                nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, hdr_fg, nextid, box_override=b_ovr)
        steps = page.get('steps', [])
        step_slots = [
            (['46', '47', '48'], (92, 293, 40, 40)),
            (['51', '52', '53', '54', '55', '56', '57', '58', '59', '60'], (388, 293, 40, 40)),
            (['63', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74'], (684, 293, 40, 40)),
            (['77', '78', '79'], (980, 293, 40, 40)),
        ]
        used_steps = set()
        for idx, (id_list, b_ovr) in enumerate(step_slots):
            if idx < len(steps):
                ic = infer_semantic_icon('', str(steps[idx]), used_steps)
                nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, hdr_fg, nextid, box_override=b_ovr)

    elif layout == 'L4':
        ms = page.get('milestones', [])
        slots = [
            (['3', '4', '5', '6'], (50, 115, 44, 44)),
            (['10', '11', '12', '13'], (460, 115, 44, 44)),
            (['17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27'], (870, 115, 44, 44)),
        ]
        used_ms = set()
        for idx, (id_list, b_ovr) in enumerate(slots):
            if idx < len(ms):
                m = ms[idx]
                ic = infer_semantic_icon(m.get('icon'), f"{m.get('title', '')} {m.get('body', '')}", used_ms)
                nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, primary, nextid, box_override=b_ovr)
        nextid = replace_icon_slot(tree, shapes_by_id, ['32', '33', '34', '35', '36'], 'table', hdr_fg, nextid, box_override=(38, 239, 25, 25))
        nextid = replace_icon_slot(tree, shapes_by_id, ['42', '43'], 'warning', hdr_fg, nextid, box_override=(842, 239, 25, 25))
        nextid = replace_icon_slot(tree, shapes_by_id, ['49', '50', '51', '52', '53', '54', '55', '56', '57', '58'], 'check', hdr_fg, nextid, box_override=(842, 396, 25, 25))

    elif layout == 'L12':
        items = page.get('items', [])
        slots = [
            (['5', '6', '7', '8'], (38, 103, 25, 25)),
            (['21', '22', '23', '24', '25', '26', '27'], (455, 103, 25, 25)),
            (['43', '44', '45', '46'], (872, 103, 25, 25)),
            (['59', '60', '61', '62', '63', '64', '65', '66', '67', '68', '69', '70'], (38, 377, 25, 25)),
            (['91', '92', '93', '94', '95'], (455, 377, 25, 25)),
            (['109', '110', '111'], (872, 377, 25, 25)),
        ]
        used_items = set()
        for idx, (id_list, b_ovr) in enumerate(slots):
            if idx < len(items):
                it = items[idx]
                ic = infer_semantic_icon(it.get('icon'), f"{it.get('title', '')} {it.get('problem', '')} {it.get('response', '')}", used_items)
                nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, hdr_fg, nextid, box_override=b_ovr)

    elif layout == 'L13':
        lanes = page.get('lanes', [])
        slots = [
            (['4', '5'], (76, 114, 44, 44)),
            (['24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35'], (76, 283, 44, 44)),
            (['62', '63', '64', '65', '66'], (76, 452, 44, 44)),
        ]
        used_lanes = set()
        for idx, (id_list, b_ovr) in enumerate(slots):
            if idx < len(lanes):
                ln = lanes[idx]
                ic = infer_semantic_icon(ln.get('icon'), f"{ln.get('label', '')} {ln.get('question', '')} {ln.get('action', '')}", used_lanes)
                nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, hdr_fg, nextid, box_override=b_ovr)

    elif layout == 'L14':
        anchors = page.get('anchors', [])
        slots = [
            (['33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '43'], (465, 603, 38, 38)),
            (['45', '46'], (734, 603, 38, 38)),
            (['48', '49', '50'], (1003, 603, 38, 38)),
        ]
        used_anc = set()
        for idx, (id_list, b_ovr) in enumerate(slots):
            anc_txt = str(anchors[idx]) if idx < len(anchors) else ''
            ic = infer_semantic_icon('', anc_txt, used_anc)
            nextid = replace_icon_slot(tree, shapes_by_id, id_list, ic, primary, nextid, box_override=b_ovr)


def typography(root, layout, *, adaptive=False, policy=None):
    """Larger type with a consistent 32px left/right safe area on content slides."""
    def split_line(sp, index):
        paragraph = sp.find('p:txBody/a:p', NS)
        if paragraph is None:
            return
        run = paragraph.find('a:r', NS)
        if run is None:
            return
        t = run.find('a:t', NS)
        if t is None or len(t.text or '') <= index:
            return
        tail = copy.deepcopy(run)
        tail.find('a:t', NS).text = t.text[index:]
        t.text = t.text[:index]
        idx = list(paragraph).index(run)
        paragraph.insert(idx + 1, E.Element(q('a', 'br')))
        paragraph.insert(idx + 2, tail)

    policy = policy or {}
    for sp in root.findall('.//p:sp', NS):
        b = box(sp)
        if not b or not sp.findall('.//a:t', NS):
            continue
        sname = sp.find('p:nvSpPr/p:cNvPr', NS).get('name', '')
        if adaptive and sname.startswith(('cover-', 'sec-', 'close-')):
            continue
        text = ''.join(t.text or '' for t in sp.findall('.//a:t', NS))
        props = sp.findall('.//a:rPr', NS) + sp.findall('.//a:defRPr', NS)
        off = sp.find('p:spPr/a:xfrm/a:off', NS)
        ext = sp.find('p:spPr/a:xfrm/a:ext', NS)
        for rp in props:
            if not rp.get('sz'):
                continue
            old = int(rp.get('sz')) / 75
            if adaptive and layout in ['L5', 'L7'] and 44 <= old <= 62:
                new = old
            elif adaptive and layout == 'L1' and sp.find('p:nvSpPr/p:cNvPr', NS).get('id') in {'104', '118', '123', '136'}:
                new = 19
            elif adaptive and layout == 'L13' and b[0] >= 190 and b[1] < 600 and old >= 22:
                new = 22
            else:
                new = (
                    old if text == '!'
                    else policy.get('footnote', 14) if b[1] >= 690
                    else policy.get('title', 42) if b[1] < 40 and old == 36
                    else old + 6 if 50 <= old <= 75
                    else old if old > 75
                    else old + 2 if old >= 28
                    else max(policy.get('auxiliary_min', 17), old + 3)
                )
            rp.set('sz', str(round(new * 75)))
        if b[1] < 40 and b[3] >= 40:
            off.set('y', str(10 * EMU))
            ext.set('cy', str(58 * EMU))
        if not adaptive:
            if layout == 'L1' and abs(b[2] - 377) < 1 and abs(b[3] - 48) < 1:
                ext.set('cy', str(58 * EMU))
            if layout == 'L1' and b[0] == 42 and b[1] == 153 and '，' in text:
                split_line(sp, text.index('，') + 1)
            if layout == 'L1' and abs(b[2] - 130) < 1:
                if 370 < b[1] < 400:
                    split_line(sp, 2)
                    off.set('y', str(380 * EMU))
                    ext.set('cy', str(65 * EMU))
                elif b[1] == 530:
                    off.set('y', str(515 * EMU))
        if layout == 'L2' and b[2] == 22:
            off.set('x', str(27 * EMU))
            ext.set('cx', str(30 * EMU))
            off.set('y', str(round((b[1] - 10) * EMU)))
            ext.set('cy', str(round((b[3] + 20) * EMU)))
        if not adaptive and layout == 'L2' and abs(b[1] - 109) < 1:
            off.set('x', str(round((b[0] - 16) * EMU)))
            ext.set('cx', str(round((b[2] + 16) * EMU)))
        if layout == 'L2' and abs(b[1] - 416) < 1:
            off.set('x', str(round((b[0] + 12) * EMU)))
            ext.set('cx', str(round((b[2] - 24) * EMU)))
        if layout == 'L8' and abs(b[1] - 476) < 1:
            off.set('y', str(466 * EMU))
            ext.set('cy', str(44 * EMU))
        if layout == 'L8' and abs(b[1] - 214) < 1:
            off.set('y', str(207 * EMU))
            ext.set('cy', str(48 * EMU))
            off.set('x', str(round((b[0] - 6) * EMU)))
            ext.set('cx', str(round((b[2] + 12) * EMU)))
        if layout == 'L3' and abs(b[1] - 621) < 1:
            off.set('y', str(617 * EMU))
            ext.set('cy', str(31 * EMU))
        if layout == 'L10' and abs(b[0] - 510) < 1 and abs(b[1] - 455) < 1:
            off.set('y', str(450 * EMU))
            ext.set('cy', str(61 * EMU))
        if not adaptive and layout == 'L13' and abs(b[2] - 128) < 1:
            off.set('y', str(round((b[1] - 5) * EMU)))
            ext.set('cy', str(34 * EMU))
        if not adaptive and layout == 'L13' and abs(b[2] - 132) < 1:
            off.set('x', str(29 * EMU))
            ext.set('cx', str(143 * EMU))
            off.set('y', str(round((b[1] - 11) * EMU)))
            ext.set('cy', str(47 * EMU))
            for paragraph in sp.findall('p:txBody/a:p', NS):
                run = paragraph.find('a:r', NS)
                if run is not None:
                    t = run.find('a:t', NS)
                    if t is not None and (t.text or '').startswith('回答'):
                        tail = copy.deepcopy(run)
                        tail.find('a:t', NS).text = t.text[2:]
                        t.text = t.text[:2]
                        idx = list(paragraph).index(run)
                        paragraph.insert(idx + 1, E.Element(q('a', 'br')))
                        paragraph.insert(idx + 2, tail)
        if b[1] >= 690:
            ext.set('cy', str(20 * EMU))

    for table in root.findall('.//a:tbl', NS):
        for rp in table.findall('.//a:rPr', NS) + table.findall('.//a:defRPr', NS):
            if rp.get('sz'):
                old = int(rp.get('sz')) / 75
                if adaptive:
                    # generate.normalize_table_adaptive already applied the policy
                    # per row; preserve its distinct header/data sizes.
                    pass
                else:
                    rp.set('sz', str(round((old + 2 if old >= 18 else old + 3) * 75)))

    if layout not in ['L5', 'L6', 'L7', 'L14']:
        margin = policy.get('content_side_margin', 32)
        scale = (1280 - 2 * margin) / 1232
        for xf in root.findall('.//p:spPr/a:xfrm', NS) + root.findall('.//p:xfrm', NS):
            off = xf.find('a:off', NS)
            ext = xf.find('a:ext', NS)
            if off is not None:
                off.set('x', str(round((margin + (int(off.get('x')) / EMU - 24) * scale) * EMU)))
            if ext is not None:
                ext.set('cx', str(round(int(ext.get('cx')) * scale)))
        for col in root.findall('.//a:tblGrid/a:gridCol', NS):
            col.set('w', str(round(int(col.get('w')) * scale)))


def chart_typography(root, *, adaptive=False, policy=None, layout=None):
    min_sz = round((policy or {}).get('chart_min', 17) * 75)
    bump = 75 if adaptive else 150
    for rp in root.findall('.//a:rPr', NS) + root.findall('.//a:defRPr', NS):
        if rp.get('sz'):
            rp.set('sz', str(max(min_sz, int(rp.get('sz')) + bump)))
        for tag in ['latin', 'ea', 'cs']:
            font = rp.find('a:' + tag, NS)
            if font is not None:
                font.set('typeface', 'Noto Sans CJK SC')
    ns = {**NS, 'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    plot = root.find('.//c:plotArea/c:layout/c:manualLayout', ns)
    if plot is not None:
        height = plot.find('c:h', ns)
        if height is not None:
            height.set('val', str(round(float(height.get('val')) - (0.065 if adaptive else 0.055), 3)))
        if root.find('.//c:valAx/c:title', ns) is not None:
            x = plot.find('c:x', ns)
            w = plot.find('c:w', ns)
            if x is not None and w is not None:
                x.set('val', str(round(float(x.get('val')) + 0.03, 3)))
                w.set('val', str(round(float(w.get('val')) - 0.03, 3)))
                if adaptive and layout == 'L10':
                    # The narrow output column needs room for both Y title and ticks.
                    x.set('val', str(round(float(x.get('val')) + 0.07, 3)))
                    w.set('val', str(round(float(w.get('val')) - 0.07, 3)))


def apply(root, layout, palette, *, adaptive=False, page=None, document=None, policy=None):
    if adaptive and page is not None and document is not None:
        prepare_adaptive_geometry(root, layout, palette, page, document, 'solid')

    primary = palette['primary'][1:]
    secondary = palette['secondary'][1:]
    tint = palette['tint'][1:]
    tree = root.find('p:cSld/p:spTree', NS)
    shapes = list(tree.findall('p:sp', NS))
    dark = []
    ids = [int(n.get('id')) for n in root.findall('.//p:cNvPr', NS) if (n.get('id') or '').isdigit()]
    nextid = max(ids, default=1) + 1

    def dark_at(b):
        if any(center_inside(b, area) for area in dark):
            return True
        if layout == 'L1':
            d = ((b[0] + b[2] / 2 - 640) ** 2 + (b[1] + b[3] / 2 - 373) ** 2) ** 0.5
            return 106 < d < 202
        return False

    def name(sp):
        return sp.find('p:nvSpPr/p:cNvPr', NS).get('name', '')

    def hastext(sp):
        return bool(sp.findall('.//a:t', NS))

    def rectangle(anchor, x, y, w, h):
        nonlocal nextid
        sp = E.Element(q('p', 'sp'))
        nv = E.SubElement(sp, q('p', 'nvSpPr'))
        E.SubElement(nv, q('p', 'cNvPr'), id=str(nextid), name='solid-title-band-' + str(nextid))
        nextid += 1
        E.SubElement(nv, q('p', 'cNvSpPr'))
        E.SubElement(nv, q('p', 'nvPr'))
        pr = E.SubElement(sp, q('p', 'spPr'))
        xf = E.SubElement(pr, q('a', 'xfrm'))
        E.SubElement(xf, q('a', 'off'), x=str(round(x * EMU)), y=str(round(y * EMU)))
        E.SubElement(xf, q('a', 'ext'), cx=str(round(w * EMU)), cy=str(round(h * EMU)))
        geom = E.SubElement(pr, q('a', 'prstGeom'), prst='rect')
        E.SubElement(geom, q('a', 'avLst'))
        fill(pr, primary)
        region = (x, y, w, h)
        front = next((s for s in tree if s.tag == q('p', 'sp') and box(s) and center_inside(box(s), region) and box(s)[3] < 80), anchor)
        tree.insert(list(tree).index(front), sp)
        dark.append(region)
        return sp

    for sp in shapes:
        b = box(sp)
        if not b or hastext(sp):
            continue
        if adaptive and name(sp).startswith(('cover-', 'sec-', 'close-', 'l9-', 'l12-', 'l13-', 'obs-', 'toc-')):
            if sp.find('p:spPr/a:solidFill/a:srgbClr', NS) is not None and sp.find('p:spPr/a:solidFill/a:srgbClr', NS).get('val') == primary and b[2] * b[3] > 2000:
                dark.append(b)
            continue
        x, y, w, h = b
        pr = sp.find('p:spPr', NS)
        color = pr.find('a:solidFill/a:srgbClr', NS)
        c = color.get('val') if color is not None else None
        isbar = w > 200 and 28 <= h <= 46 and c == tint
        isnode = name(sp).startswith('node-')
        islane = layout == 'L13' and abs(w - 153) < 2 and abs(h - 155) < 2
        if isbar or isnode or islane:
            fill(pr, primary)
            stroke(sp, primary, 1.5)
            dark.append(b)
            geom = pr.find('a:prstGeom', NS)
            if geom is not None and not isnode:
                geom.set('prst', 'rect')
        elif w > 200 and h > 90 and c in ['FFFFFF', tint] and y > 80 and pr.find('a:prstGeom', NS) is not None and pr.find('a:prstGeom', NS).get('prst') in ['rect', 'roundRect']:
            fill(pr, 'FFFFFF')
            stroke(sp, primary, 1.2)
            geom = pr.find('a:prstGeom', NS)
            if geom is not None:
                geom.set('prst', 'rect')
        elif c == primary and w * h > 3000:
            geom = pr.find('a:prstGeom', NS)
            if geom is not None and geom.get('prst') in ['rect', 'roundRect']:
                dark.append(b)

    if layout == 'L2':
        for sp in shapes:
            b = box(sp)
            if b and hastext(sp) and abs(b[1] - (105 if adaptive else 109)) < 2 and abs(b[3] - 35) < 2:
                card_x = round((b[0] - (64 if adaptive else 83)))
                rectangle(sp, card_x, 96, 383, 48)
            if b and hastext(sp) and abs(b[1] - 416) < 1 and abs(b[3] - 30) < 1:
                rectangle(sp, b[0] - 2, 412, 574, 38)
        if not adaptive:
            for sp in shapes:
                b = box(sp)
                if not b or hastext(sp):
                    continue
                for i in range(3):
                    area = (91 + 397 * i, 109, 49, 49)
                    if inside(b, area, 0.1):
                        xf = sp.find('p:spPr/a:xfrm', NS)
                        off = xf.find('a:off', NS)
                        ext = xf.find('a:ext', NS)
                        off.set('x', str(round((area[0] + (b[0] - area[0]) * 32 / 49) * EMU)))
                        off.set('y', str(round((104 + (b[1] - area[1]) * 32 / 49) * EMU)))
                        ext.set('cx', str(round(b[2] * 32 / 49 * EMU)))
                        ext.set('cy', str(round(b[3] * 32 / 49 * EMU)))

    for sp in shapes:
        b = box(sp)
        if b and hastext(sp) and any(center_inside(b, area) for area in dark):
            text_color(sp, 'FFFFFF')

    if adaptive and page is not None:
        apply_adaptive_icons(root, layout, palette, page, 'solid')
        # Style any remaining template icons cleanly as wireframe strokes without turning them into solid blobs
        for sp in list(tree.findall('p:sp', NS)):
            b = box(sp)
            if not b or hastext(sp):
                continue
            nm = name(sp)
            if nm.startswith(('icon-', 'vector-')) and b[2] <= 110 and b[3] <= 110:
                if any( nm.startswith(p) for p in ['icon-camera', 'icon-tree', 'icon-leaf', 'icon-calendar', 'icon-database', 'icon-dna', 'icon-pcr', 'icon-table', 'icon-chart', 'icon-filter', 'icon-warning', 'icon-search', 'icon-location', 'icon-layers', 'icon-wf', 'icon-doc', 'icon-compass', 'icon-check']):
                    continue
                on_dark = dark_at(b)
                fg = 'FFFFFF' if on_dark else primary
                pr = sp.find('p:spPr', NS)
                if pr.find('a:solidFill', NS) is not None and b[2] * b[3] < 400:
                    fill(pr, fg)
                else:
                    no_fill(pr)
                    stroke(sp, fg, 1.7)
    else:
        icons = [sp for sp in shapes if box(sp) and (name(sp).startswith('icon-') or name(sp).startswith('vector-') and box(sp)[2] <= 110 and box(sp)[3] <= 110)]
        closed = []
        for sp in icons:
            geom = sp.find('p:spPr/a:prstGeom', NS)
            if geom is not None and geom.get('prst') not in ['line', 'arc'] or sp.find('.//a:custGeom/a:pathLst/a:path/a:close', NS) is not None:
                closed.append(sp)
        for sp in icons:
            b = inkbox(sp)
            on_dark = dark_at(b)
            fg = 'FFFFFF' if on_dark else primary
            containers = [outer for outer in closed if outer is not sp and inkbox(outer)[2] * inkbox(outer)[3] > b[2] * b[3] * 2 and inside(b, inkbox(outer), 0.1)]
            parent = min(containers, key=lambda s: inkbox(s)[2] * inkbox(s)[3]) if containers else None
            if parent is None:
                color = fg
            else:
                parent_fill = parent.find('p:spPr/a:solidFill/a:srgbClr', NS)
                color = primary if parent_fill is not None and parent_fill.get('val') == 'FFFFFF' else 'FFFFFF'
            if sp in closed:
                fill(sp.find('p:spPr', NS), color)
            stroke(sp, color, 2.1)
            path = sp.find('.//a:custGeom/a:pathLst/a:path', NS)
            if sp in closed and path is not None and len(path.findall('.//a:pt', NS)) == 4 and abs(box(sp)[3] / box(sp)[2] - 0.5) < 0.02:
                stroke(sp, primary if on_dark else 'FFFFFF', 1.3)
        for sp in shapes:
            b = box(sp)
            if not b or hastext(sp) or sp in icons:
                continue
            if name(sp).startswith(('vector-', 'line-')) and b[2] <= 110 and b[3] <= 110:
                pr = sp.find('p:spPr', NS)
                on_dark = any(inside(b, area) for area in dark)
                enclosing = next((outer for outer in closed if inside(b, box(outer), 0.1) and box(outer)[2] * box(outer)[3] > b[2] * b[3] * 2), None)
                color = (primary if on_dark else 'FFFFFF') if enclosing is not None else ('FFFFFF' if on_dark else primary)
                if on_dark or enclosing is not None:
                    if pr.find('a:solidFill', NS) is not None:
                        fill(pr, color)
                    if pr.find('a:ln/a:solidFill', NS) is not None:
                        stroke(sp, color, 2.1)

    for sp in tree.findall('p:cxnSp', NS):
        line = sp.find('p:spPr/a:ln', NS)
        if line is not None:
            line.set('w', str(round(2.6 * EMU)))
    typography(root, layout, adaptive=adaptive, policy=policy)
