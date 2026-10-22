"""Paper-independent rendering; prose is text, not executable HTML."""
import base64
import html
import json
import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path


def esc(value):
    return html.escape(str(value), quote=True)


def load_trans(path):
    records = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    out = {}
    for record in records:
        if record["id"] in out:
            raise ValueError("Duplicate translation id: " + record["id"])
        out[record["id"]] = record
    return out


class TableFilter(HTMLParser):
    allowed = {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "sub", "sup", "em", "strong", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.allowed:
            safe = ''.join(f' {k}="{v}"' for k, v in attrs
                           if k in {"colspan", "rowspan"} and v and v.isdigit() and 0 < int(v) < 1000)
            self.parts.append(f"<{tag}{safe}>")

    def handle_endtag(self, tag):
        if tag in self.allowed:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(esc(data))


def safe_table(raw):
    parser = TableFilter()
    parser.feed(raw)
    return ''.join(parser.parts)


def math_html(tex, block=False):
    try:
        import latex2mathml.converter
        markup = latex2mathml.converter.convert(tex)
        if block:
            markup = markup.replace('display="inline"', 'display="block"')
        return markup
    except Exception:
        return '<code class="mathfail" title="公式转换未完成，保留 LaTeX">' + esc(tex) + '</code>'


def inline(raw):
    parts, pos = [], 0
    for match in re.finditer(r"(?<!\\)\$([^$\n]+)\$", raw):
        parts.extend([esc(raw[pos:match.start()]), math_html(match[1])])
        pos = match.end()
    parts.append(esc(raw[pos:]))
    return ''.join(parts)


def original_html(raw, source):
    runs=source.get('inline_runs')
    if not runs:return inline(raw.strip())
    parts=[]
    for run in runs:
        content=esc(run['text'])
        for tag in reversed(run.get('styles',[])):content=f'<{tag}>'+content+f'</{tag}>'
        if run.get('target'):content=f'<a class="source-xref" href="#{esc(run["target"])}">'+content+'</a>'
        parts.append(content)
    return ''.join(parts)

def embed_image(name, asset_root):
    root = Path(asset_root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing image or path outside asset root: " + str(name))
    mime = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp", ".gif":"image/gif"}.get(path.suffix.lower())
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise ValueError("Only local raster images may be embedded: " + str(name))
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def source_label(item, include_status=False):
    src = item.get("source", {})
    bits = []
    if src.get("pdf_page") is not None:
        bits.append("PDF 第 " + str(src["pdf_page"]) + " 页")
    if src.get("printed_page") is not None:
        bits.append("印刷页 " + str(src["printed_page"]))
    if src.get("line_start") is not None:
        bits.append(f"Markdown L{src['line_start']}–{src.get('line_end', src['line_start'])}")
    if include_status:
        bits.append("原页已核对" if src.get("status") == "verified" else "原页待核对")
    return " · ".join(bits)


def render_full(data, trans, asset_root=".", mechanisms=None):
    from render_mechanisms import render_mechanism
    planned = {}
    for mechanism in mechanisms or []:
        planned.setdefault(mechanism['anchor'], []).append(mechanism)
    sections, missing = [], []
    ordered = sorted(enumerate(data["sections"]), key=lambda pair: pair[1].get('kind', 'body') != 'body')
    for si, section in ordered:
        if not section['items']:
            continue
        body = []
        for item in section["items"]:
            pid = item["id"]
            label = '<p class="source" title="' + esc(source_label(item, include_status=True)) + '">' + esc(source_label(item)) + '</p>'
            src=item.get('source',{})
            if src.get('context')=='quote':label+='<p class="source-kind">原文引文'+(' · '+esc(src['quote_attribution']) if src.get('quote_attribution') else '')+'</p>'
            if src.get('footnote_label'):label+='<p class="source-kind">原文注 '+esc(src['footnote_label'])+'</p>'
            raw = item["raw"]
            display_raw = raw
            for correction in item.get('source', {}).get('corrections', []):
                display_raw = display_raw.replace(correction['old'], correction['new'], 1)
            if item["t"] == "p":
                rec = trans.get(pid, {})
                if not rec.get("zh"):
                    missing.append(pid)
                original = f'<div class="orig en" data-ann-id="{esc(pid)}-en">{original_html(display_raw,item.get("source",{}))}</div>'
                translated = f'<div class="zh" data-ann-id="{esc(pid)}-zh">{inline(rec.get("zh", "译文待补"))}</div>'
                note = f'<div class="note" data-ann-id="{esc(pid)}-note">{esc(rec.get("note", "白话待补"))}</div>'
                keys = ''.join('<li>' + esc(x) + '</li>' for x in rec.get("keys", []))
                trap = '<p class="trap">易错点：' + esc(rec["trap"]) + '</p>' if rec.get("trap") else ''
                terms = ' · '.join(esc(t.get("en", "")) + '：' + esc(t.get("zh", "")) for t in rec.get("terms", []))
                if rec.get("role", "body") != "body":
                    body.append(f'<article class="source-block compact-info" id="{esc(pid)}">{label}{original}{translated}</article>')
                else:
                    glossary = f'<p class="terms">{terms}</p>' if terms else ''
                    body.append(f'<article class="pcard {"quoted-source" if src.get("context")=="quote" else ""}" id="{esc(pid)}">{label}'
                                f'<details class="bilingual" open><summary>原文与译文</summary><div class="pgrid">{original}{translated}</div></details>'
                                f'<h4 class="plain-title">白话解释</h4>{note}'
                                f'<details class="logic" open><summary>逻辑要点</summary><ul>{keys}</ul></details>{trap}{glossary}'
                                f'<button class="read-toggle" data-read="{esc(pid)}" aria-pressed="false">标为已读</button></article>')
            else:
                if item["t"] == "eq":
                    content = math_html(item.get("latex", raw.strip().strip('$')), True)
                    content += '<details open><summary>公式原始 LaTeX</summary><pre>' + esc(raw) + '</pre></details>'
                elif item["t"] == "table":
                    content = '<div class="table-scroll">' + safe_table(raw) + '</div>'
                    if item.get('source', {}).get('facsimile'):
                        content += '<figure><img alt="原页表格，供核对转录排版" src="' + embed_image(item['source']['facsimile'], asset_root) + '"><figcaption>原页表格 · 核对表头与单元格</figcaption></figure>'
                elif item["t"] == "figure":
                    content = '<img alt="' + esc(item.get("caption", "原文图")) + '" src="' + embed_image(item["src"], asset_root) + '">'
                    content += '<p>' + esc(item.get("caption", "")) + '</p>'
                else:
                    content = '<pre>' + esc(raw) + '</pre>'
                body.append(f'<article class="source-block" id="{esc(pid)}">{label}{content}</article>')
            for mechanism in planned.get(pid, []):
                body.append(render_mechanism(mechanism))
        sections.append(f'<section class="fsect" id="f-{si:02d}"><h2>{esc(section.get("display_name", section["name"]))}</h2>{"".join(body)}</section>')
    return '\n'.join(sections), missing
