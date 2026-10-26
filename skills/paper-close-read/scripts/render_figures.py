"""Reuse original image assets in place; teaching explanations remain clearly separate."""
from render_full import esc, embed_image


def original_figure(item, asset_root, label=''):
    caption = item.get('caption', '')
    heading = ('<strong>' + esc(label) + '</strong> ') if label and not caption.startswith(label) else ''
    return ('<figure class="source-figure"><img alt="' + esc(caption or label or '原文图片') + '" src="' + embed_image(item['src'], asset_root) + '">'
            '<figcaption>' + heading + esc(caption or '原文未提供图注') + '</figcaption></figure>')


def walkthrough_figure(reference, items, asset_root, identity, data=None):
    item = items[reference['ref']]
    from source_pdf import page_button
    return ('<figure class="guide-source-figure" id="' + esc(identity) + '" data-source-figure="' + esc(item['id']) + '">'
            '<span class="eyebrow">论文原图 · 与讲解一起看</span>' + page_button(item, data or {}) + '<p class="figure-focus"><strong>先看哪里：</strong>' + esc(reference['focus']) + '</p>'
            '<img alt="' + esc(item.get('caption') or '论文原图') + '" src="' + embed_image(item['src'], asset_root) + '">'
            '<figcaption><span class="original-caption">' + esc(item.get('caption') or '原文未提供图注') + '</span>'
            '<p class="figure-explanation"><strong>这张图说明什么：</strong>' + esc(reference['explanation']) + '</p>'
            '<a href="#' + esc(item['id']) + '">对照逐段精读中的原图与上下文</a></figcaption></figure>')


def inventory_html(data, report):
    verified = report['status'] == 'verified'
    inventory = data.get('figure_inventory', {})
    rows = []
    for entry in inventory.get('figures', []):
        links = ' / '.join('<a href="#' + esc(b) + '">原图' + (str(n + 1) if len(entry['blocks']) > 1 else '') + '</a>' for n, b in enumerate(entry.get('blocks', [])))
        panels = ' · 子图 ' + esc('、'.join(entry['panels'])) if entry.get('panels') else ''
        rows.append('<li>' + esc(entry['label']) + panels + ' · ' + ('已核对' if entry.get('verified') else '待核对') + ' ' + links + '</li>')
    status = ('原图清单核对完成：' + str(report['verified_figures']) + ' 项原图/图像公式，' + str(report['image_blocks']) + ' 个图片块。') if verified else '原图完整性待核对：已保留提取到的图片，尚不能确认原文是否有漏图。'
    source = inventory.get('source', {})
    basis = ('来源：' + esc(source.get('file', '')) + ' · ' + (('出版商 JATS 图清单核对；另有 PDF 逐页看图记录。' if inventory.get('pdf_review') else '出版商 JATS 图清单核对；PDF 裁切与清晰度需另外看原页。') if source.get('kind') == 'jats' else 'PDF 逐页核对记录。')) if source else ''
    return '<div class="figure-inventory"><h3>原图完整性</h3><p>' + status + '</p><p>' + basis + '</p>' + ('<ul>' + ''.join(rows) + '</ul>' if rows else '') + '</div>'
