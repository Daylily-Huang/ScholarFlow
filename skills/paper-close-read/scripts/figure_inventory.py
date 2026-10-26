"""Source-first figure inventory; matching extracted text alone cannot certify a PDF."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def tag(node):
    return node.tag.rsplit('}', 1)[-1]


def jats_figures(path):
    """Enumerate every source figure/equation graphic, independent of the importer."""
    root = ET.parse(path).getroot()
    entries = []
    for node in root.iter():
        if tag(node) not in {'fig', 'disp-formula', 'inline-formula'}:
            continue
        graphics = [el for el in node.iter() if tag(el) in {'graphic', 'inline-graphic'}]
        if not graphics and tag(node) != 'fig':
            continue
        # Different formats in <alternatives> represent one picture, not extra panels.
        alternatives = {id(g): alt for alt in node.iter() if tag(alt) == 'alternatives'
                        for g in alt.iter() if tag(g) in {'graphic', 'inline-graphic'}}
        hrefs, used = [], set()
        for graphic in graphics:
            group = alternatives.get(id(graphic))
            key = id(group) if group is not None else id(graphic)
            if key in used:
                continue
            used.add(key)
            href = next((v for k, v in graphic.attrib.items() if k.rsplit('}', 1)[-1] == 'href'), '')
            hrefs.append(href)
        label = next((' '.join(el.itertext()).strip() for el in node if tag(el) == 'label'), '')
        entries.append({'id': node.get('id') or 'source-figure-' + str(len(entries) + 1),
                        'label': label or node.get('id') or '原图 ' + str(len(entries) + 1),
                        'kind': 'figure' if tag(node) == 'fig' else 'equation', 'hrefs': hrefs})
    return entries


def inventory_errors(data, guide, asset_root=None, require=False):
    errors, warnings = [], []
    items = {i['id']: i for s in data['sections'] for i in s['items']}
    images = {key: item for key, item in items.items() if item['t'] == 'figure'}
    displayed = set()
    for chapter in guide.get('story', {}).get('walkthrough', []):
        for figure in chapter.get('figures', []):
            ref = figure.get('ref')
            if ref not in images:
                errors.append('Walkthrough figure must reference an original image block: ' + str(ref))
            elif ref not in chapter.get('refs', []):
                errors.append('Walkthrough figure needs chapter evidence ref: ' + ref)
            if type(figure.get('after')) is not int or not 0 <= figure['after'] < len(chapter.get('paragraphs', [])):
                errors.append('Walkthrough figure after must name an existing paragraph index')
            if any(not str(figure.get(key, '')).strip() for key in ('focus', 'explanation')):
                errors.append('Walkthrough figure needs focus and explanation')
            if isinstance(ref, str): displayed.add(ref)
    audit = data.get('figure_inventory')
    summary = {'status': 'unverified', 'source_figures': None, 'verified_figures': 0, 'image_blocks': len(images)}
    if audit is None:
        (errors if require else warnings).append('未提供独立原文图清单，无法确认提取前是否漏图；不能宣称原图完整')
        return errors, warnings, summary
    if not isinstance(audit, dict) or not isinstance(audit.get('figures'), list) or not isinstance(audit.get('source'), dict):
        return ['figure_inventory needs source object and figures array'], warnings, summary
    source, entries = audit['source'], audit['figures']
    kind = source.get('kind')
    if kind not in {'pdf', 'jats'} or not isinstance(source.get('file'), str) or not source['file'] or not re.fullmatch('[a-f0-9]{64}', str(source.get('sha256', ''))):
        errors.append('Figure inventory source needs kind pdf/jats, file and SHA256')
    complete = audit.get('status') == 'verified'
    if asset_root is None:
        (errors if require else warnings).append('图清单来源与图片哈希尚未校验；完整核验需提供 asset_root')
    if audit.get('status') not in {'pending', 'verified'}:
        errors.append('Figure inventory status must be pending or verified')
    if complete and not str(audit.get('review_note', '')).strip():
        errors.append('Verified figure inventory needs a source review_note')
    source_path = None
    if asset_root is not None and isinstance(source.get('file'), str):
        root = Path(asset_root).resolve()
        source_path = (root / source['file']).resolve()
        if not source_path.is_relative_to(root) or not source_path.is_file():
            (errors if complete or require else warnings).append('Figure inventory source file missing or outside asset root')
            source_path = None
        elif hashlib.sha256(source_path.read_bytes()).hexdigest() != source.get('sha256'):
            errors.append('Figure inventory source SHA256 mismatch')
    if kind == 'pdf':
        count, checked = source.get('page_count'), audit.get('checked_pages')
        if type(count) is not int or count < 1 or not isinstance(checked, list) or any(type(n) is not int or n < 1 or n > count for n in checked):
            errors.append('PDF figure inventory needs page_count and valid checked_pages')
        elif complete and set(checked) != set(range(1, count + 1)):
            errors.append('PDF figure inventory cannot be verified before every page is reviewed')
    pdf_review = audit.get('pdf_review')
    if pdf_review is not None:
        if not isinstance(pdf_review, dict):
            errors.append('figure_inventory.pdf_review must be an object')
        else:
            count, checked = pdf_review.get('page_count'), pdf_review.get('checked_pages')
            if type(count) is not int or count < 1 or not isinstance(checked, list) or any(type(n) is not int or n < 1 or n > count for n in checked):
                errors.append('PDF review needs page_count and valid checked_pages')
            elif complete and set(checked) != set(range(1, count + 1)):
                errors.append('PDF review must cover every page before verification')
            if not isinstance(pdf_review.get('file'), str) or not pdf_review['file'] or not re.fullmatch('[a-f0-9]{64}', str(pdf_review.get('sha256', ''))):
                errors.append('PDF review needs source file and SHA256')
            elif asset_root is not None:
                root = Path(asset_root).resolve(); pdf = (root / pdf_review['file']).resolve()
                if not pdf.is_relative_to(root) or not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-') or hashlib.sha256(pdf.read_bytes()).hexdigest() != pdf_review['sha256']:
                    errors.append('PDF review source SHA256 mismatch, missing or not a PDF')
    if source_path is not None and kind == 'pdf' and not source_path.read_bytes().startswith(b'%PDF-'):
        errors.append('Figure inventory PDF source is not a PDF file')
    ids, covered, seen_blocks = set(), set(), set()
    key_results = set()
    for n, entry in enumerate(entries):
        at = 'figure_inventory.figures[' + str(n) + ']'
        if not isinstance(entry, dict):
            errors.append(at + ' must be an object'); continue
        identity, blocks = entry.get('id'), entry.get('blocks')
        if not isinstance(identity, str) or not identity or identity in ids:
            errors.append(at + ' needs a unique nonempty source id')
        else:
            ids.add(identity)
        if not isinstance(entry.get('label'), str) or not entry['label'].strip() or entry.get('kind') not in {'figure', 'equation'}:
            errors.append(at + ' needs label and kind figure/equation')
        if not isinstance(blocks, list) or any(not isinstance(b, str) or b not in images for b in blocks):
            errors.append(at + ' blocks must refer to existing source image blocks'); continue
        if len(blocks) != len(set(blocks)) or seen_blocks.intersection(blocks):
            errors.append(at + ' repeats source image blocks')
        seen_blocks.update(blocks); covered.update(blocks)
        panels, checked_panels = entry.get('panels', []), entry.get('checked_panels', [])
        if any(not isinstance(v, list) or any(not isinstance(p, str) or not p.strip() for p in v) or len(v) != len(set(v)) for v in (panels, checked_panels)):
            errors.append(at + ' panels and checked_panels must be unique text arrays'); continue
        if not set(checked_panels).issubset(panels):
            errors.append(at + ' checked_panels contains unknown panels')
        verified = entry.get('verified') is True
        if complete or verified:
            if not blocks or not verified or entry.get('caption_checked') is not True or not str(entry.get('verification_note', '')).strip() or set(panels) != set(checked_panels):
                errors.append(at + ' needs image, caption and every panel reviewed before verification')
            if kind == 'pdf' and (not isinstance(entry.get('pages'), list) or not entry['pages'] or any(type(p) is not int or p < 1 or (type(source.get('page_count')) is int and p > source['page_count']) for p in entry['pages'])):
                errors.append(at + ' needs actual PDF pages for verified figures')
        if verified:
            summary['verified_figures'] += 1
        if entry.get('key_result') is True:
            key_results.update(blocks)
    if complete and covered != set(images):
        errors.append('Verified figure inventory must account for every extracted source image block')
    if kind == 'jats' and source_path is not None:
        try:
            expected = jats_figures(source_path)
        except (ET.ParseError, OSError) as exc:
            errors.append('Cannot read JATS figure inventory: ' + str(exc)); expected = []
        expected_ids = {e['id'] for e in expected}
        if len(expected_ids) != len(expected):
            errors.append('JATS source figure IDs are not unique')
        # A source figure cannot disappear from the inventory, even while review is pending.
        if ids != expected_ids:
            errors.append('JATS figure inventory differs from source figure/equation IDs')
        by_id = {e['id']: e for e in entries if isinstance(e, dict) and isinstance(e.get('id'), str)}
        for original in expected:
            record = by_id.get(original['id'], {})
            blocks = record.get('blocks', [])
            if not isinstance(blocks, list): continue
            if len(blocks) != len(original['hrefs']):
                errors.append('JATS graphic count mismatch: ' + original['id'])
            actual = [Path(images[b]['src']).stem for b in blocks if isinstance(b, str) and b in images]
            if actual != [Path(href).stem for href in original['hrefs']]:
                errors.append('JATS graphics do not match mapped image files: ' + original['id'])
    hashes = audit.get('asset_sha256', {})
    if not isinstance(hashes, dict):
        errors.append('figure_inventory.asset_sha256 must be an object'); hashes = {}
    if complete and set(hashes) != covered:
        errors.append('Verified figure inventory needs SHA256 for every mapped image')
    if asset_root is not None:
        root = Path(asset_root).resolve()
        for block, digest in hashes.items():
            if block not in images:
                errors.append('Unknown inventory image hash: ' + str(block)); continue
            file = (root / images[block]['src']).resolve()
            if not file.is_relative_to(root) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                errors.append('Figure inventory image SHA256 mismatch or missing file: ' + block)
    if key_results - displayed:
        errors.append('Key result images must appear beside walkthrough explanation: ' + ', '.join(sorted(key_results - displayed)))
    if not complete:
        (errors if require else warnings).append('原图清单尚未核对完成，不能宣称原图完整')
    summary.update(status='verified' if complete and not errors else 'pending', source_figures=len(entries))
    return errors, warnings, summary


def draft_inventory(data, source_path, kind):
    source_path = Path(source_path)
    images = [i for s in data['sections'] for i in s['items'] if i['t'] == 'figure']
    result = {'source': {'kind': kind, 'file': source_path.name, 'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest()},
              'status': 'pending', 'review_note': '', 'figures': [], 'asset_sha256': {}}
    if kind == 'jats':
        assigned = set()
        for entry in jats_figures(source_path):
            blocks = []
            for href in entry.pop('hrefs'):
                match = next((i for i in images if Path(i['src']).stem == Path(href).stem and i['id'] not in assigned), None)
                if match: blocks.append(match['id']); assigned.add(match['id'])
            result['figures'].append({**entry, 'blocks': blocks, 'panels': [], 'checked_panels': [],
                                      'caption_checked': False, 'verified': False, 'verification_note': '', 'key_result': False})
    else:
        # No PDF parser can prove semantic figure/panel completeness from image-object counts.
        result['source']['page_count'] = None
        result['checked_pages'] = []
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--kind', choices=('pdf', 'jats'), required=True)
    args = parser.parse_args()
    try:
        if args.output.resolve() in {args.source.resolve(), args.data.resolve()} or args.output.exists():
            raise ValueError('清单输出须为新文件，不能覆盖原文、结构或已有核对记录')
        result = draft_inventory(json.loads(args.data.read_text(encoding='utf-8-sig')), args.source, args.kind)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (ValueError, OSError, ET.ParseError) as exc:
        parser.exit(2, str(exc) + '\n')
    print('已生成待核图清单；对照原文核查图号、子图、图注和映射后，填入 fulltext.figure_inventory。')


if __name__ == '__main__': main()
