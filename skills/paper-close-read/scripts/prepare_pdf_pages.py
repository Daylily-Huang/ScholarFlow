"""Render true PDF pages for an offline, draggable reader window (optional PyMuPDF)."""
import argparse
import hashlib
import json
from pathlib import Path


def prepare(pdf, root, selection='all', dpi=140):
    try:
        import fitz
    except ImportError as exc:
        raise ValueError('PDF 原页准备需可选 PyMuPDF；也可用现有 PDF 渲染工具后按 source_pdf 契约提供原页图像。') from exc
    pdf, root = Path(pdf).resolve(), Path(root).resolve()
    if not pdf.is_relative_to(root):
        raise ValueError('请将获准保留的原 PDF 放在资料根目录内，避免写入不可移植的绝对路径')
    manifest = root / 'source-pdf-pages.json'
    if manifest.exists():
        raise ValueError('已有原页清单，不覆盖；请核对后选择新的资料目录或显式处理旧输出')
    if not 72 <= dpi <= 240:
        raise ValueError('原页 DPI 应在72–240之间')
    doc = fitz.open(pdf)
    pages = list(range(1, len(doc) + 1)) if selection == 'all' else [int(n.strip()) for n in selection.split(',')]
    if not pages or len(pages) != len(set(pages)) or any(p < 1 or p > len(doc) for p in pages):
        raise ValueError('原页选择必须是不重复、有效的 PDF 文件页码')
    if any((root / 'pdf-pages' / ('page-' + str(p).zfill(3) + '.jpg')).exists() for p in pages):
        raise ValueError('原页图像已存在，不覆盖已核对的页面')
    (root / 'pdf-pages').mkdir(parents=True, exist_ok=True)
    result = {'file': pdf.relative_to(root).as_posix(), 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
              'page_count': len(doc), 'dpi': dpi, 'pages': []}
    for number in pages:
        file = root / 'pdf-pages' / ('page-' + str(number).zfill(3) + '.jpg')
        doc[number-1].get_pixmap(dpi=dpi, alpha=False).save(file, jpg_quality=90)
        result['pages'].append({'page': number, 'src': file.relative_to(root).as_posix(),
                                'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('asset_root', type=Path)
    parser.add_argument('--pages', default='all', help='all 或以逗号分隔的PDF文件页码')
    parser.add_argument('--dpi', type=int, default=140)
    args = parser.parse_args()
    try:
        result = prepare(args.pdf, args.asset_root, args.pages, args.dpi)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, str(exc) + '\n')
    print('已准备 ' + str(len(result['pages'])) + ' 个 PDF 原页；将 source-pdf-pages.json 内容填入 fulltext.source_pdf 后重建。')


if __name__ == '__main__': main()
