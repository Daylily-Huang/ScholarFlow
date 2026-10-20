#!/usr/bin/env python3
"""Audit PPTX package integrity, chart cache/workbook agreement, fonts, font sizes, and layout positions."""
from __future__ import annotations
import argparse, io, json, math, posixpath, re, zipfile
from pathlib import Path
import xml.etree.ElementTree as E

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
EMU = 9525
ALLOWED_FONTS = {
    'Noto Sans CJK SC', 'Noto Serif CJK SC',
    'Microsoft YaHei', 'SimSun', 'Arial', 'Calibri',
}


def target(owner, path):
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), path)).lstrip('/')


def relation_file(part):
    return posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')


def visual_width_px(text, sz_px):
    total = 0.0
    for ch in str(text):
        total += (1.03 if ord(ch) > 127 else 0.58) * sz_px
    return total


def shape_box(el, xfrm_path='p:spPr/a:xfrm'):
    xf = el.find(xfrm_path, NS)
    if xf is None:
        return None
    off = xf.find('a:off', NS)
    ext = xf.find('a:ext', NS)
    if off is None or ext is None:
        return None
    return (
        int(off.get('x')) / EMU,
        int(off.get('y')) / EMU,
        int(ext.get('cx')) / EMU,
        int(ext.get('cy')) / EMU,
    )


def para_lines_text(txBody):
    lines = []
    for p in txBody.findall('a:p', NS):
        cur = []
        for child in p:
            if child.tag == '{' + NS['a'] + '}r':
                t = child.find('a:t', NS)
                if t is not None and t.text:
                    cur.append(t.text)
            elif child.tag == '{' + NS['a'] + '}br':
                lines.append(''.join(cur))
                cur = []
        lines.append(''.join(cur))
    return [ln for ln in lines if ln != ''] or ['']


def overlap_rect(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x1 - x0), max(0.0, y1 - y0)


def audit(path, *, strict=False, font_profile='auto'):
    errors = []
    warnings = []
    counts = dict(slides=0, text_shapes=0, charts=0, tables=0, connectors=0, pictures=0, cache_cells=0)
    fonts_used = set()
    font_size_summary = {}
    policy = json.loads((Path(__file__).resolve().parents[1] / 'assets/template-system.json').read_text(encoding='utf-8'))['solid_typography']

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        bad = z.testzip()
        if bad:
            errors.append('CRC: ' + bad)
        pres = E.fromstring(z.read('ppt/presentation.xml'))
        size = pres.find('p:sldSz', NS)
        canvas_w = int(size.get('cx')) / EMU if size is not None else 1280.0
        canvas_h = int(size.get('cy')) / EMU if size is not None else 720.0
        theme_fonts = {}
        if 'ppt/theme/theme1.xml' in names:
            theme = E.fromstring(z.read('ppt/theme/theme1.xml'))
            for key, family in [('mj', 'majorFont'), ('mn', 'minorFont')]:
                parent = theme.find('.//a:' + family, NS)
                if parent is not None:
                    for suffix, tag in [('lt', 'latin'), ('ea', 'ea'), ('cs', 'cs')]:
                        el = parent.find('a:' + tag, NS)
                        if el is not None and el.get('typeface'):
                            theme_fonts[f'+{key}-{suffix}'] = el.get('typeface')
        def resolve_font(tf):
            if tf.startswith('+'):
                if tf not in theme_fonts:
                    warnings.append(f'Unresolved theme font {tf!r}; explicit font required')
                return theme_fonts.get(tf, tf)
            return tf

        for name in sorted(names):
            if name.endswith('.rels'):
                owner = '' if name == '_rels/.rels' else name.replace('/_rels/', '/').removesuffix('.rels')
                for r in E.fromstring(z.read(name)):
                    if r.get('TargetMode') == 'External':
                        errors.append('External relationship: ' + name)
                    elif target(owner, r.get('Target')) not in names:
                        errors.append('Missing relationship target: ' + name)

            if re.fullmatch(r'ppt/slides/slide\d+\.xml', name):
                s_num = int(re.search(r'slide(\d+)\.xml$', name).group(1))
                s_tag = f'slide{s_num:02d}'
                root = E.fromstring(z.read(name))
                counts['slides'] += 1
                counts['text_shapes'] += len(root.findall('.//p:sp/p:txBody', NS))
                counts['tables'] += len(root.findall('.//a:tbl', NS))
                counts['connectors'] += len(root.findall('.//p:cxnSp', NS))
                counts['pictures'] += len(root.findall('.//p:pic', NS))

                # 1. Check fonts across slide
                for f_el in root.findall('.//a:latin', NS) + root.findall('.//a:ea', NS) + root.findall('.//a:cs', NS):
                    tf = resolve_font(f_el.get('typeface', ''))
                    if tf:
                        fonts_used.add(tf)
                        if tf not in ALLOWED_FONTS and not tf.startswith('+'):
                            warnings.append(f'{s_tag}: non-standard font typeface {tf!r}')

                # 2. Collect pictures, charts, tables, and text boxes for position/size/collision checks
                pic_boxes = []
                for pic in root.findall('.//p:pic', NS):
                    pb = shape_box(pic, 'p:spPr/a:xfrm')
                    if pb:
                        pic_boxes.append(pb)
                        if pb[2] >= canvas_w * 0.95 and pb[3] >= canvas_h * 0.95:
                            errors.append('Full-slide raster: ' + name)

                text_items = []
                slide_szs = set()
                for frame in root.findall('.//p:graphicFrame', NS):
                    bounds = shape_box(frame, 'p:xfrm')
                    if bounds and (bounds[0] < -2 or bounds[1] < -2 or bounds[0] + bounds[2] > canvas_w + 4 or bounds[1] + bounds[3] > canvas_h + 4):
                        warnings.append(f'{s_tag}: chart/table frame out of canvas bounds {bounds}')
                for sp in root.findall('.//p:sp', NS):
                    tb = sp.find('p:txBody', NS)
                    b = shape_box(sp, 'p:spPr/a:xfrm')
                    if tb is None or b is None:
                        continue
                    lines = para_lines_text(tb)
                    full_txt = '\n'.join(lines).strip()
                    if not full_txt:
                        continue
                    rprs = sp.findall('.//a:rPr', NS) + sp.findall('.//a:defRPr', NS)
                    szs = [round(int(rp.get('sz')) / 75.0, 2) for rp in rprs if rp.get('sz')]
                    sz_px = max(szs) if szs else 18.0
                    slide_szs.update(szs)
                    if sz_px < 13.0 and full_txt != '!':
                        warnings.append(f'{s_tag}: text font too small ({sz_px}px) in {full_txt[:16]!r}')
                    if b[0] < -2 or b[1] < -2 or b[0] + b[2] > canvas_w + 4 or b[1] + b[3] > canvas_h + 4:
                        warnings.append(f'{s_tag}: text box {b} out of canvas bounds for {full_txt[:16]!r}')

                    # Estimate ink width and wrapped line count
                    est_lines = 0
                    max_line_w = 0.0
                    for ln in lines:
                        lw = visual_width_px(ln, sz_px)
                        max_line_w = max(max_line_w, lw)
                        est_lines += max(1, math.ceil(lw / max(1.0, b[2] + 6.0)))
                    ink_w = min(b[2], max_line_w)
                    pPr = tb.find('a:p/a:pPr', NS)
                    if pPr is not None and pPr.get('algn') == 'ctr':
                        ink_x = b[0] + (b[2] - ink_w) / 2.0
                    else:
                        ink_x = b[0]
                    ink_h = min(b[3], est_lines * sz_px * 1.25)
                    ink_box = (ink_x, b[1], max(ink_w, 10.0), max(ink_h, 10.0))
                    text_items.append((sp.find('p:nvSpPr/p:cNvPr', NS).get('id', ''), full_txt, b, ink_box, sz_px, est_lines))

                    # Check text height overflow
                    if est_lines * sz_px * 1.18 > b[3] + 10.0:
                        warnings.append(f'{s_tag}: text wrap height ({est_lines} lines @ {sz_px}px) exceeds box h={round(b[3])}px in {full_txt[:18]!r}')

                    # Check text-to-picture collision (e.g. cover/section title overlapping right picture)
                    for pb in pic_boxes:
                        ow, oh = overlap_rect((b[0], b[1], max_line_w, ink_h), pb)
                        if ow > 16.0 and oh > 14.0:
                            msg = f'{s_tag}: text {full_txt[:18]!r} overlaps picture box {tuple(round(v) for v in pb)} by {round(ow)}x{round(oh)}px'
                            warnings.append(msg)
                            if strict:
                                errors.append(msg)

                font_size_summary[s_tag] = sorted(slide_szs)

                # 3. Check text-to-text collisions
                for i in range(len(text_items)):
                    for j in range(i + 1, len(text_items)):
                        id1, t1, b1, ink1, sz1, _ = text_items[i]
                        id2, t2, b2, ink2, sz2, _ = text_items[j]
                        ow, oh = overlap_rect(ink1, ink2)
                        if ow > 12.0 and oh > 10.0:
                            msg = f'{s_tag}: text collision between {t1[:12]!r} and {t2[:12]!r} ({round(ow)}x{round(oh)}px)'
                            warnings.append(msg)
                            if strict:
                                errors.append(msg)

                # 4. Check table font size uniformity & vertical wrap overflow
                for gf in root.findall('.//p:graphicFrame', NS):
                    tbl = gf.find('.//a:tbl', NS)
                    gb = shape_box(gf, 'p:xfrm')
                    if tbl is None or gb is None:
                        continue
                    col_ws = [int(c.get('w')) / EMU for c in tbl.findall('a:tblGrid/a:gridCol', NS)]
                    rows = tbl.findall('a:tr', NS)
                    data_szs = set()
                    est_tbl_h = 0.0
                    for r_idx, r in enumerate(rows):
                        cells = r.findall('a:tc', NS)
                        max_r_lines = 1
                        row_max_sz = 18.0
                        for c_idx, cell in enumerate(cells):
                            ctext = ''.join(t.text or '' for t in cell.findall('.//a:t', NS)).strip()
                            if not ctext:
                                continue
                            c_szs = [round(int(rp.get('sz')) / 75.0, 2) for rp in cell.findall('.//a:rPr', NS) if rp.get('sz')]
                            c_sz = max(c_szs) if c_szs else 18.0
                            row_max_sz = max(row_max_sz, c_sz)
                            if r_idx >= 1 and ctext not in {'●', '△', '○'}:
                                data_szs.add(c_sz)
                            cw = col_ws[c_idx] if c_idx < len(col_ws) else 100.0
                            avail_cw = max(20.0, cw - 16.0)
                            tw = visual_width_px(ctext, c_sz)
                            lines_c = max(1, math.ceil(tw / avail_cw))
                            max_r_lines = max(max_r_lines, lines_c)
                            if r_idx >= 1 and lines_c > 1 and len(rows) >= 5:
                                msg = f'{s_tag}: table cell ({r_idx},{c_idx}) {ctext!r} wraps to {lines_c} lines at {c_sz}px in {round(cw)}px column'
                                warnings.append(msg)
                                if strict:
                                    errors.append(msg)
                        row_def_h = int(r.get('h')) / EMU
                        required_h = max_r_lines * row_max_sz * 1.25 + 8.0
                        if row_def_h + 1 < required_h:
                            warnings.append(f'{s_tag}: table row {r_idx} height {row_def_h:.1f}px below text minimum {required_h:.1f}px')
                        est_tbl_h += max(row_def_h, required_h)
                    if len(data_szs) > 1 and (max(data_szs) - min(data_szs) > 2.5 or max(data_szs) > 25.0):
                        msg = f'{s_tag}: inconsistent table data cell font sizes {sorted(data_szs)}px'
                        warnings.append(msg)
                        if strict:
                            errors.append(msg)
                    # Check if expanded table collides with text below it
                    tbl_bottom = gb[1] + est_tbl_h
                    if gb[0] < -2 or gb[0] + gb[2] > canvas_w + 4 or gb[1] < -2 or tbl_bottom > canvas_h + 4:
                        warnings.append(f'{s_tag}: table out of canvas bounds (bottom={tbl_bottom:.1f}px)')
                    for _, t_txt, t_box, _, _, _ in text_items:
                        if t_box[1] >= gb[1] + gb[3] - 5 and t_box[1] < tbl_bottom - 2 and overlap_rect((gb[0], 0, gb[2], 10), (t_box[0], 0, t_box[2], 10))[0] > 20:
                            msg = f'{s_tag}: table vertical expansion (bottom={round(tbl_bottom)}px) collides with {t_txt[:18]!r} at y={round(t_box[1])}px'
                            warnings.append(msg)
                            if strict:
                                errors.append(msg)

            if not re.fullmatch(r'ppt/charts/chart\d+\.xml', name):
                continue
            counts['charts'] += 1
            root = E.fromstring(z.read(name))
            for font in root.findall('.//a:latin', NS) + root.findall('.//a:ea', NS) + root.findall('.//a:cs', NS):
                tf = resolve_font(font.get('typeface', ''))
                if tf:
                    fonts_used.add(tf)
                    if tf not in ALLOWED_FONTS and not tf.startswith('+'):
                        warnings.append(f'{name}: non-standard chart font {tf!r}')
            chart_sizes = {round(int(rp.get('sz')) / 75.0, 2)
                           for rp in root.findall('.//a:rPr', NS) + root.findall('.//a:defRPr', NS)
                           if rp.get('sz')}
            # Historical light examples remain readable legacy assets; strict delivery
            # enforces the current minimum without changing their original bytes.
            for sz in sorted(chart_sizes):
                if sz < policy['chart_min']:
                    warnings.append(f'{name}: chart font {sz}px below {policy["chart_min"]}px')
            ext = root.find('c:externalData', NS)
            if ext is None:
                errors.append('Missing workbook: ' + name)
                continue
            rels = {r.get('Id'): r.get('Target') for r in E.fromstring(z.read(relation_file(name)))}
            book = target(name, rels[ext.get('{' + NS['r'] + '}id')])
            with zipfile.ZipFile(io.BytesIO(z.read(book))) as wb:
                cells = {}
                for cell in E.fromstring(wb.read('xl/worksheets/sheet1.xml')).findall('.//s:c', NS):
                    cells[cell.get('r')] = ''.join(t.text or '' for t in cell.findall('.//s:t', NS)) if cell.get('t') == 'inlineStr' else cell.findtext('s:v', namespaces=NS)
            for ref in list(root.iter('{' + NS['c'] + '}numRef')) + list(root.iter('{' + NS['c'] + '}strRef')):
                formula = ref.findtext('c:f', namespaces=NS) or ''
                match = re.fullmatch(r"'Chart Data'!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)", formula)
                if not match or match[1] != match[3]:
                    errors.append('Unsupported reference: ' + formula)
                    continue
                numeric = ref.tag.endswith('}numRef')
                cache = ref.find('c:numCache' if numeric else 'c:strCache', NS)
                points = cache.findall('c:pt', NS)
                expected_count = int(match[4]) - int(match[2]) + 1
                if len(points) != expected_count or int(cache.find('c:ptCount', NS).get('val')) != expected_count:
                    errors.append('Point count mismatch: ' + name)
                if [int(p.get('idx')) for p in points] != list(range(expected_count)):
                    errors.append('Point indices mismatch: ' + name)
                for point in points:
                    key = match[1] + str(int(match[2]) + int(point.get('idx')))
                    actual = cells.get(key)
                    expected = point.findtext('c:v', namespaces=NS)
                    counts['cache_cells'] += 1
                    try:
                        equal = math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12) if numeric else actual == expected
                    except (ValueError, TypeError):
                        equal = False
                    if not equal:
                        errors.append(name + ' ' + key + ': cache/workbook mismatch')

        if any(b'EVIDENCE_MANIFEST' in z.read(n) for n in names if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')):
            import importlib.util
            spec=importlib.util.spec_from_file_location('evidence_audit',Path(__file__).resolve().parent/'evidence_layouts.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            errors.extend(mod.audit_embedded(z,NS))
        if len(pres.findall('p:sldIdLst/p:sldId', NS)) != counts['slides']:
            errors.append('Slide count mismatch')

    profiles = {'portable': {'Noto Sans CJK SC', 'Noto Serif CJK SC'}, 'office': {'Microsoft YaHei', 'SimSun'}}
    selected = font_profile if font_profile != 'auto' else ('office' if fonts_used and fonts_used <= profiles['office'] else 'portable')
    for tf in sorted(fonts_used - profiles[selected]):
        warnings.append(f'Font {tf!r} is outside the {selected} font profile')
    if strict:
        errors = list(dict.fromkeys(errors + warnings))
    return dict(
        ok=not errors,
        file=Path(path).name,
        counts=counts,
        fonts=sorted(fonts_used),
        font_sizes=font_size_summary,
        warning_count=len(warnings),
        warnings=warnings,
        errors=errors,
        scope='Structure, cached series/workbook agreement, font family, font size hierarchy, table cell uniformity, and bounding-box collision checks.',
    )


if __name__ == '__main__':
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pptx')
    p.add_argument('--strict', action='store_true', help='Fail on typography/layout warnings as well as structural errors')
    p.add_argument('--font-profile', choices=['auto', 'portable', 'office'], default='auto')
    args = p.parse_args()
    try:
        result = audit(args.pptx, strict=args.strict, font_profile=args.font_profile)
    except Exception as e:
        result = {'ok': False, 'errors': [str(e)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
