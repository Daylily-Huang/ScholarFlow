"""Read-only authoring diagnostics. Structural readiness is not render approval."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect(document, base_dir=None):
    issues = []
    def issue(level, path, code, message):
        issues.append(dict(level=level, path=path, code=code, message=message))
    def error(path, code, message):
        issue('error', path, code, message)
    def warning(path, code, message):
        issue('warning', path, code, message)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def strings(value):
        return isinstance(value, list) and bool(value) and all(text(x) for x in value)
    system = json.loads((ROOT/'assets/template-system.json').read_text(encoding='utf-8'))
    bindings = json.loads((ROOT/'assets/templates/bindings.json').read_text(encoding='utf-8'))
    if not isinstance(document, dict):
        error('$', 'object_required', '输入应为JSON对象。')
        return dict(ok=False, issues=issues, scope='Input structure only; no file generated.')
    for key, choices in [('scenario', system['scenarios']), ('palette', system['palettes'])]:
        if not isinstance(document.get(key), str) or document[key] not in choices:
            error(key, 'invalid_choice', '请选择：'+', '.join(choices))
    if type(document.get('demo')) is not bool:
        error('demo', 'boolean_required', '请明确标记是否为示意样板。')
    if document.get('fill_style', 'light') not in ('light', 'solid'):
        error('fill_style', 'invalid_choice', '请选择light或solid。')
    pages = document.get('slides')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 150:
        error('slides', 'invalid_pages', '需要1到150页的数组。')
        pages = []
    if document.get('demo') is False:
        materials = document.get('materials')
        if not isinstance(materials, dict) or not isinstance(materials.get('papers'), list):
            error('materials.papers', 'paper_inventory_required', '正式稿需要论文清单；没有论文时使用空数组。')
        if not text(document.get('footer')):
            warning('footer', 'missing_footer', '建议填写项目/报告名，避免沿用模板页脚。')
    directories = []
    overviews = []
    layouts = []
    titles = collections.defaultdict(list)
    for i, page in enumerate(pages):
        prefix = f'slides[{i}]'
        if not isinstance(page, dict):
            error(prefix, 'page_object_required', '每页需要一个对象。')
            continue
        layout = page.get('layout')
        if not isinstance(layout, str) or layout not in system['layouts']:
            error(prefix+'.layout', 'unknown_layout', '版式应为L1到L23。')
            continue
        if layout in {'L21','L22','L23'}:
            import importlib.util
            spec=importlib.util.spec_from_file_location('compact_preflight',ROOT/'scripts/compact_layouts.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            try:
                definition=module.definition(page)
                expected={f['path'].split('.',1)[1] for f in definition['fields'] if f['path'].startswith('texts.')}
                if not isinstance(page.get('texts'),dict) or set(page['texts'])!=expected:
                    error(prefix+'.texts','compact_text_keys','请按compact-approved.json提供当前变体的完整texts字段。')
                if not isinstance(page.get('charts',[]),list) or len(page.get('charts',[]))!=len(definition['charts']):
                    error(prefix+'.charts','compact_chart_count','图表数量与当前紧凑变体不一致。')
            except ValueError as exc:
                error(prefix+'.variant','compact_variant',str(exc))
        if 'composition' not in page:layouts.append((i,layout))
        if 'composition' in page and layout not in ('L15','L16','L17','L18'):error(prefix+'.composition','unsupported_layout','原生排版变体需要L15–L18。')
        if 'experiment_scene' in page:error(prefix+'.experiment_scene','migration_required','实验排版需明确迁移为composition，不能静默忽略。')
        if not text(page.get('title')):
            error(prefix+'.title', 'title_required', '请写本页论点或主题。')
        else:
            titles[page['title'].strip()].append(i)
        if not strings(page.get('sources')):
            error(prefix+'.sources', 'sources_required', '每页需要非空来源数组，示意页注明示意。')
        if 'title_translation' in page:
            value=page['title_translation']
            if not text(value) or '\n' in value or '\r' in value:
                error(prefix+'.title_translation','single_line_required','双语副标题需要非空单行文本。')
            if layout in ('L5','L7','L14'):
                error(prefix+'.title_translation','content_header_only','封面用subtitle，章节/结束页用lines；此字段用于正文页。')
        if 'notes' in page and not isinstance(page['notes'], str):
            error(prefix+'.notes', 'text_required', '讲者备注需要文本。')
        if layout in bindings:
            for field in bindings[layout]['fields']:
                if 'path' not in field:
                    continue
                value = page
                try:
                    for key in field['path'].split('.'):
                        value = value[int(key)] if isinstance(value,list) else value[key]
                except (KeyError, IndexError, TypeError, ValueError):
                    error(prefix+'.'+field['path'], 'required_field', '所选版式缺少字段；请补充内容或换版式。')
        if layout == 'L6':
            chapters=page.get('chapters')
            if isinstance(chapters,list) and all(isinstance(c,dict) and text(c.get('title')) for c in chapters):
                directories.append((i,[c['title'] for c in chapters]))
        if layout == 'L7':
            overviews.append((i,page))
            active=page.get('active')
            if type(active) is not int or not 0 <= active <= 3:
                error(prefix+'.active', 'invalid_active', '章节高亮索引应为0到3的整数。')
        images = page.get('images', {})
        if not isinstance(images, dict):
            error(prefix+'.images', 'object_required', 'images应为插槽与路径的映射。')
            images={}
        paths=[(prefix+'.images.'+str(k),v) for k,v in images.items()]
        if page.get('image') is not None:
            paths.append((prefix+'.image',page['image']))
        for loc, value in paths:
            if not text(value):
                error(loc, 'path_required', '需要图片文件路径。')
            elif base_dir is not None:
                p=Path(value)
                p=p if p.is_absolute() else Path(base_dir)/p
                try:
                    with p.open('rb') as f:header=f.read(24)
                    if not header.startswith(b'\x89PNG\r\n\x1a\n') or len(header)<24:
                        error(loc, 'png_required', '当前静态生成器需要有效PNG；请先转换并核对。')
                except OSError:
                    error(loc, 'file_unavailable', '图片文件不可读取。')
    # Compare only declared chapter structures; absence of chapter pages is not an error.
    if directories:
        canonical=directories[0][1]
        for i, names in directories[1:]:
            if names != canonical:
                error(f'slides[{i}].chapters', 'chapter_mismatch', '目录章节与前一目录不一致。')
        for i,page in overviews:
            if page.get('chapters') != canonical:
                error(f'slides[{i}].chapters', 'chapter_mismatch', '章节导航应与目录标题同源、同序。')
            active=page.get('active')
            if type(active) is int and 0<=active<len(canonical) and page.get('section')!=f'{active+1:02d}':
                error(f'slides[{i}].section', 'section_mismatch', '章节编号与高亮索引不一致。')
            if type(active) is int and 0<=active<len(canonical) and isinstance(page.get('lines'),list) and page['lines'] and page['lines'][0]!=canonical[active]:
                error(f'slides[{i}].lines[0]', 'section_title_mismatch', '章节标题与高亮索引指向的目录不一致。')
    for j in range(2,len(layouts)):
        a,b,c=layouts[j-2:j+1]
        if a[0]+1==b[0] and b[0]+1==c[0] and a[1]==b[1]==c[1] and c[1] not in ('L5','L7'):
            warning(f'slides[{c[0]}].layout', 'repetitive_rhythm', '连续三页同版式，请检查是否需要大图/对照/推导等变体；合理重复可保留。')
    for title, indices in titles.items():
        if len(indices)>1:
            warning('slides', 'duplicate_title', '重复标题位于页：'+', '.join(str(i+1) for i in indices))
    return dict(ok=not any(x['level']=='error' for x in issues), issues=issues,
                scope='Authoring structure, selected required fields, chapter consistency and ordinary PNG paths only. Does not prove paper completeness, chart validity, licensing or rendered quality.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=inspect(json.loads(args.input.read_text(encoding='utf-8-sig')),args.input.resolve().parent)
    except (OSError,ValueError) as exc:
        result=dict(ok=False,issues=[dict(level='error',path='$',code='read_error',message=str(exc))])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['ok'] else 2


if __name__=='__main__':
    raise SystemExit(main())
