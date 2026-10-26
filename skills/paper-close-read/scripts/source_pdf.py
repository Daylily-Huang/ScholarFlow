"""Validate and embed actual PDF-page facsimiles, never reconstructed paragraphs."""
import hashlib
from pathlib import Path
import re
from html import escape


def validate_source_pdf(data, asset_root=None):
    record = data.get('source_pdf')
    if record is None: return []
    errors = []
    if not isinstance(record, dict) or not isinstance(record.get('pages'), list):
        return ['source_pdf needs an object with a pages array']
    if type(record.get('page_count')) is not int or record['page_count'] < 1:
        return ['source_pdf.page_count must be a positive integer']
    if not isinstance(record.get('file'), str) or not record['file'] or not re.fullmatch('[a-f0-9]{64}', str(record.get('sha256', ''))):
        return ['source_pdf needs the original PDF file and SHA256']
    page_numbers = set()
    for page in record['pages']:
        if not isinstance(page, dict) or type(page.get('page')) is not int or not 1 <= page['page'] <= record['page_count'] or not isinstance(page.get('src'), str) or not page['src'] or not re.fullmatch('[a-f0-9]{64}', str(page.get('sha256', ''))):
            errors.append('source_pdf.pages needs actual page number, image path and SHA256'); continue
        if page['page'] in page_numbers: errors.append('Duplicate source PDF page number')
        page_numbers.add(page['page'])
    if not page_numbers: errors.append('source_pdf needs at least one prepared original page')
    if asset_root is not None:
        root = Path(asset_root).resolve();original = (root / record['file']).resolve()
        if not original.is_relative_to(root) or not original.is_file() or not original.read_bytes().startswith(b'%PDF-') or hashlib.sha256(original.read_bytes()).hexdigest() != record['sha256']:
            errors.append('source_pdf original PDF missing or SHA256 mismatch')
        for page in record['pages']:
            if not isinstance(page, dict) or not isinstance(page.get('src'), str): continue
            file = (root / page['src']).resolve()
            if not file.is_relative_to(root) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != page.get('sha256'):
                errors.append('Source PDF page image missing or SHA256 mismatch: ' + str(page.get('page')))
    inventory = data.get('figure_inventory', {})
    original_review = inventory.get('pdf_review', {}) if isinstance(inventory, dict) else {}
    inventory_source = inventory.get('source', {}) if isinstance(inventory, dict) else {}
    if isinstance(inventory_source, dict) and inventory_source.get('kind') == 'pdf':
        original_review = inventory_source
    if isinstance(original_review, dict) and original_review and original_review.get('sha256') != record['sha256']:
        errors.append('PDF page viewer and figure review must use the same source PDF')
    return errors


def config_pages(data, asset_root):
    from render_full import embed_image
    record = data.get('source_pdf')
    if not record: return None
    return {'file': record['file'], 'pageCount': record['page_count'],
            'pages': [{'page': p['page'], 'image': embed_image(p['src'], asset_root)} for p in sorted(record['pages'], key=lambda p: p['page'])]}


def page_button(item, data):
    record = data.get('source_pdf')
    if not record: return ''
    numbers = {p['page'] for p in record['pages']}
    page = item.get('source', {}).get('pdf_page')
    located = item.get('source', {}).get('status') == 'verified' and page in numbers
    for figure in data.get('figure_inventory', {}).get('figures', []):
        if item['id'] in figure.get('blocks', []) and figure.get('verified') and figure.get('pages'):
            candidate = figure['pages'][0]
            if candidate in numbers: page = candidate; located = True
    label = ('查看 PDF 原页' if located else '浏览 PDF 原文')
    return '<button type="button" data-open-pdf-page="' + (str(page) if located else '') + '" data-pdf-located="' + ('true' if located else 'false') + '" title="' + escape('打开对应 PDF 文件页' if located else '本段页码未核实，打开原PDF后可自行翻页对照') + '">' + label + '</button>'
