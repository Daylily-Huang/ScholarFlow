"""Build a standalone offline reader from verified source structure and authored explanations."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_full import esc, embed_image, render_full
from validate_content import validate
from render_further import render_further

ROOT = Path(__file__).resolve().parent.parent
GENERATOR_VERSION = '1.5.0'


def refs_html(refs):
    return ' '.join(f'<a class="evidence" href="#{esc(ref)}">查看证据 {n + 1}</a>' for n, ref in enumerate(refs))


def render_guide(guide, asset_root, data=None):
    checks = []
    for n, check in enumerate(guide.get("checks", [])):
        checks.append(f'<article class="check"><h3>{esc(check.get("question", ""))}</h3>'
                      f'<label>先用自己的话想一想（不用提交）<textarea data-recall="{n}" rows="2"></textarea></label>'
                      f'<details open><summary>对照解释与证据</summary><p>{esc(check.get("answer", ""))}</p>{refs_html(check.get("refs", []))}</details></article>')
    if guide.get('story'):
        from render_story import render_story
        extra='<section class="story-practice"><h2>试着讲给别人听</h2>'+''.join(checks)+'</section>' if checks else ''
        return render_story(guide['story'], guide.get('mechanisms', []), guide.get('concepts', []),extra, data, asset_root)
    motion_links = ''.join(f'<p><a class="evidence" href="#{esc(m["id"])}">{esc(m["title"])}</a></p>' for m in guide.get('mechanisms', []))
    motion_links = '<section class="motion-guide-links"><h3>用动图跨过这些难点</h3>' + motion_links + '</section>' if motion_links else ''
    claims = []
    for n, claim in enumerate(guide.get("claims", [])):
        claims.append(f'<article class="claim" id="g-{n}"><span class="eyebrow">证据路线 {n + 1} · {esc(claim.get("kind", "作者论述"))}</span>'
                      f'<h3>{esc(claim.get("title", ""))}</h3><p data-ann-id="g-{n}-text">{esc(claim.get("text", ""))}</p>'
                      f'{refs_html(claim.get("refs", []))}</article>')
    glossary = ''.join(f'<details open><summary>{esc(t.get("term", ""))}</summary><p>{esc(t.get("meaning", ""))}</p></details>' for t in guide.get("glossary", []))
    limits = ''.join('<li>' + esc(s) + '</li>' for s in guide.get("limits", []))
    transfer = ''.join('<li>' + esc(s) + '</li>' for s in guide.get("transfer", []))
    animations = []
    for n, anim in enumerate(guide.get("animations", [])):
        frames = [embed_image(x, asset_root) for x in anim["frames"]]
        durations = anim["durations"]
        if not frames or len(frames) != len(durations) or any(not isinstance(x, (int, float)) or x <= 0 for x in durations):
            raise ValueError("Animation frames/durations must have equal nonzero length and positive durations")
        payload = esc(json.dumps({"frames": frames, "durations": durations}))
        animations.append(f'<figure class="anim" data-animation="{payload}"><h3>{esc(anim["title"])}</h3>'
                          f'<p>教学示意 · 非原文数值</p><img src="{frames[0]}" alt="{esc(anim.get("alt", anim["title"]))}">'
                          '<div class="controls"><button data-action="first" aria-label="第一帧">⏮</button><button data-action="prev" aria-label="上一帧">◀</button>'
                          '<button data-action="play">播放</button><button data-action="next" aria-label="下一帧">▶</button>'
                          f'<input aria-label="动画帧" type="range" min="0" max="{len(frames)-1}" value="0">'
                          '<span class="frame-count"></span><label>速度<select><option value="0.5">0.5×</option><option selected value="1">1×</option><option value="2">2×</option></select></label></div>'
                          f'<figcaption>{esc(anim.get("explanation", ""))}</figcaption></figure>')
    return (f'<section class="entry"><span class="eyebrow">先弄懂一个问题</span><h2>{esc(guide.get("question", "导读待补"))}</h2>'
            f'<p class="lead" data-ann-id="guide-answer">{esc(guide.get("answer", "回答待补"))}</p>'
            f'<p>{esc(guide.get("why", ""))}</p><p class="muted">路线名称表示阅读深度；用时因论文和基础而异。</p></section>'
            f'{motion_links}<section><h2>这篇论文的证据路线</h2>{"".join(claims)}</section>'
            f'<section><h2>适用条件与未解问题</h2><ul>{limits}</ul></section>'
            f'<div data-deep><section><h2>卡住时再看</h2>{glossary or "<p>暂无额外术语。</p>"}{"".join(animations)}</section>'
            f'<section><h2>用到其他研究时要准备什么</h2><ul>{transfer}</ul></section>'
            f'<section><h2>试着讲给别人听</h2>{"".join(checks)}</section></div>')


def build(data, records, guide, asset_root, source_text=None, allow_incomplete=False, require_figure_audit=False, require_visual_plan=False):
    report = validate(data, records, guide, source_text, allow_incomplete, asset_root, require_figure_audit, require_visual_plan)
    if report["errors"]:
        raise ValueError('\n'.join(report["errors"]))
    full, missing = render_full(data, {r["id"]: r for r in records}, asset_root, guide.get('mechanisms', []))
    if guide.get('concepts'):
        from render_concepts import render_concepts
        for concept in guide['concepts']:
            anchor = concept.get('anchor', concept['refs'][0])
            marker = 'id="' + anchor + '"'
            at = full.find(marker)
            end = full.find('</article>', at) if at >= 0 else -1
            if end >= 0:
                full = full[:end+10] + render_concepts([concept]) + full[end+10:]
    if guide.get('mechanisms'):
        full = '<div class="motion-index">' + ''.join(f'<a href="#{esc(m["id"])}">▶ {esc(m["title"])}</a>' for m in guide['mechanisms']) + '</div>' + full
    if guide.get('story'):
        full = ('<div class="entry-funnel"><span>不想从第一页硬啃原文？先花 3 分钟抓研究骨架，再按问题走通 10 分钟主线：</span>'
                '<div class="entry-funnel-actions"><button type="button" data-goto-route="quick">先看 3 分钟入门 →</button>'
                '<button type="button" class="ghost-btn" data-goto-route="deep">10 分钟读懂主线 →</button></div></div>') + full
    ordered = sorted(enumerate(data['sections']), key=lambda pair: pair[1].get('kind', 'body') != 'body')
    navigation = ''.join(f'<a href="#f-{i:02d}">{esc(s.get("display_name", s["name"]))}</a>' for i, s in ordered if s['items'])
    if guide.get('further_reading'):
        recommendation = render_further(guide['further_reading'])
        link = '<a href="#f-further-reading">核心文献推荐</a>'
        appendix = next((i for i,s in ordered if s['items'] and (s.get('kind', 'body') != 'body' or s['name'].strip().lower() in {'references', 'acknowledgments', 'acknowledgements', '参考文献', '致谢'})), None)
        marker = f'<section class="fsect" id="f-{appendix:02d}">' if appendix is not None else ''
        if marker and marker in full:
            full = full.replace(marker, recommendation + marker, 1)
            nav_marker = f'<a href="#f-{appendix:02d}">'
            navigation = navigation.replace(nav_marker, link + nav_marker, 1)
        else:
            full += recommendation
            navigation += link
    title = data["front"]["title"]
    config = {"paperId": data["paper_id"], "title": title,
              "revision": hashlib.sha256(json.dumps([data, records, guide], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]}
    config['generatorVersion']=GENERATOR_VERSION
    config['citation']=data['front'].get('citation','')
    config['sourceLanguage']=data['front'].get('language','en')
    from source_pdf import config_pages
    config['sourcePdf']=config_pages(data, asset_root)
    config['blocks']={i['id']:{'page':i.get('source',{}).get('pdf_page'),'verified':i.get('source',{}).get('status')=='verified','section':s.get('display_name',s['name'])} for s in data['sections'] for i in s['items']}
    config_json = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    warnings = ''.join('<li>' + esc(w) + '</li>' for w in report["warnings"])
    verified = sum(item.get("source", {}).get("status") == "verified" for section in data["sections"] for item in section["items"])
    scope = esc(guide.get("scope", "导读为精选；全文模式覆盖本次提供的 Markdown，不代表已核对 PDF 全文完整性。"))
    css = (ROOT / 'assets/reader.css').read_text(encoding='utf-8-sig') + '\n' + (ROOT / 'assets/editorial.css').read_text(encoding='utf-8-sig')
    css += '\n' + (ROOT / 'assets/pdf.css').read_text(encoding='utf-8-sig')
    pdf_export = (ROOT / 'assets/pdf-export.js').read_text(encoding='utf-8-sig')
    css += '\n' + (ROOT / 'assets/source-viewer.css').read_text(encoding='utf-8-sig')
    source_viewers = (ROOT / 'assets/floating-viewer.js').read_text(encoding='utf-8-sig') + '\n' + (ROOT / 'assets/source-pdf-viewer.js').read_text(encoding='utf-8-sig')
    persistence = (ROOT / 'assets/persistence.js').read_text(encoding='utf-8-sig')
    workspace = (ROOT / 'assets/workspace.js').read_text(encoding='utf-8-sig')
    navigation_js = (ROOT / 'assets/navigation.js').read_text(encoding='utf-8-sig')
    reader = (ROOT / 'assets/reader.js').read_text(encoding='utf-8-sig')
    annotation = (ROOT / 'scripts/annotate.js').read_text(encoding='utf-8-sig')
    enhancements = (ROOT / 'assets/editorial.js').read_text(encoding='utf-8-sig') + '\n' + (ROOT / 'assets/mechanisms.js').read_text(encoding='utf-8-sig')
    attribution = ''
    if guide.get('attribution'):
        a=guide['attribution']
        attribution='<div class="source-attribution"><h3>原文归属与改写</h3><p>'+esc(a['citation'])+'</p><p>'+esc(a['url'])+'</p><p>'+esc(a['license'])+'</p><p>'+esc(a['changes'])+'</p></div>'
    draft = '<p class="warning">待补稿：讲解或翻译不完整。</p>' if allow_incomplete else ''
    from render_figures import inventory_html
    figure_audit_html = inventory_html(data, report['figures'])
    result = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · 精读</title><style>{css}</style></head>
<body class="{'source-zh' if data['front'].get('language') == 'zh' else 'source-en'}"><a class="skip" href="#main">跳至正文</a><header><span class="eyebrow">文献慢读 · 从问题走到证据</span><h1>{esc(title)}</h1><p>{esc(data['front'].get('citation', ''))}</p>{draft}<a href="#source-notes">来源说明</a></header>
<div class="toolbar"><div class="seg" aria-label="阅读路线"><button data-route="full" aria-pressed="true">逐段精读</button><button data-route="quick" aria-pressed="false">3 分钟入门</button><button data-route="deep" aria-pressed="false">10 分钟读懂</button></div><label class="font-label" for="font-size">字号 <select id="font-size"><option value="16">16px</option><option value="18" selected>18px · 默认</option><option value="20">20px</option></select></label><button id="resume">继续上次</button><button id="export-reading">导出阅读笔记</button><button id="export-pdf">导出双语 PDF</button><span id="progress" aria-live="polite"></span></div>
<div class="layout"><aside><label for="search">检索原文与逐段讲解</label><input id="search" type="search" placeholder="输入术语、数值或问题"><p id="search-count" aria-live="polite"></p><nav aria-label="全文目录">{navigation}</nav></aside><main id="main"><div id="mode-guide" hidden>{render_guide(guide, asset_root, data)}</div><div id="mode-full">{full}</div><section id="source-notes"><h2>来源说明</h2><p>{scope}</p><p>{report['source_blocks']} 个来源块 · {report['paragraphs']} 段 · {report['translations']} 条译文{f" · {report['block_notes']} 处公式/表格拆解" if report.get('block_notes') else ''}；原页文字核对 {verified} 块。逐块状态见来源标签提示。</p><ul>{warnings}</ul><p>译文与讲解由 AI 辅助整理。</p>{figure_audit_html}{attribution}</section></main></div>
<p id="storage-status" role="status"></p><noscript>交互需要浏览器启用 JavaScript；原文如下。</noscript><style>noscript+style{{display:none}}</style><noscript><style>#mode-full[hidden]{{display:block!important}}</style></noscript>
<script id="reader-config" type="application/json">{config_json}</script><script>{persistence}</script><script>{reader}</script><script>{annotation}</script><script>{workspace}</script><script>{navigation_js}</script><script>{enhancements}</script><script>{source_viewers}</script><script>{pdf_export}</script></body></html>'''
    return result, report


def atomic_write(path, text):
    """Keep a previous valid reader intact if a new output cannot be completed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.reader-', suffix='.tmp', dir=str(path.parent), delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'translations', 'guide', 'output'):
        ap.add_argument(name, type=Path)
    ap.add_argument('--asset-root', type=Path, required=True)
    ap.add_argument('--source', type=Path)
    ap.add_argument('--allow-incomplete', action='store_true')
    ap.add_argument('--require-figure-audit', action='store_true', help='新完整稿要求独立来源图清单和全部图/子图核对完成')
    ap.add_argument('--require-visual-plan', action='store_true', help='新完整稿核对重难点及其就地解释覆盖')
    args = ap.parse_args()
    try:
        values = []
        for file in (args.data, args.translations, args.guide):
            try:
                values.append(json.loads(file.read_text(encoding='utf-8-sig')))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{file.name}: JSON第{exc.lineno}行第{exc.colno}列有误：{exc.msg}") from exc
        source = None
        if args.source:
            with args.source.open(encoding='utf-8-sig', newline='') as stream:
                source = stream.read()
        result, report = build(*values, args.asset_root, source, args.allow_incomplete, args.require_figure_audit, args.require_visual_plan)
        atomic_write(args.output, result)
    except (OSError, UnicodeError, ValueError) as exc:
        print('构建未完成：' + str(exc), file=sys.stderr)
        print('请修正输入或输出路径后重试；原有HTML未被替换。', file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
