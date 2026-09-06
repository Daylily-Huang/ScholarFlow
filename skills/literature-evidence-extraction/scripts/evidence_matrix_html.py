#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_matrix_html.py
-----------------------
ScholarFlow 证据抽取结果全中文 HTML 报告渲染器 (literature-evidence-extraction)。

将符合 canonical `schemas/extraction_result.schema.json` 的证据 JSON 渲染为
自包含、零外部依赖、可直接双击阅读的全中文 HTML 报告。设计动机（2026-09-06
端到端测试用户反馈）：Markdown 矩阵适合归档与 diff，但"便于观看"需要 HTML——
色标徽章、字段分组与统计面板让证据结构一目了然，且全中文呈现消除双语阅读摩擦。

特性:
1. 全中文表头/徽章/统计面板（支撑类型、证据强度、状态均带中文释义与色标）；
2. 兼容新旧两代记录字段（优先 support_type，回退 evidence_level 映射）；
3. NOT_REPORTED（未报告）记录以灰色斜体显著区分，状态一律显示"存疑/未报告"，
   防止"未报告"被误读为"不支持"（NR 语义防护条款的可视化落地）；
4. 派生计算（DERIVED）记录的备注区高亮显示推导公式；
5. 自包含单文件 HTML（内联 CSS，无 CDN、无 JS 依赖），离线可看、可直接归档。

Standard Library Only (Zero third-party pip dependencies required).

用法:
    python evidence_matrix_html.py -i evidence.json -o evidence_report.html
退出码: 0 成功 | 2 输入错误
"""

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 全中文映射表 ────────────────────────────────────────────────────────────
SUPPORT_ZH = {
    "EXPLICIT": "明示（E1）",
    "DERIVED": "派生计算（E2）",
    "REFERENCED": "引自他文（E3）",
    "NOT_REPORTED": "未报告（E4）",
}
SUPPORT_CLS = {
    "EXPLICIT": "b-green", "DERIVED": "b-blue",
    "REFERENCED": "b-orange", "NOT_REPORTED": "b-gray",
}
STRENGTH_ZH = {
    "DIRECT_EMPIRICAL": "直接实证",
    "MODELED_EMPIRICAL": "模型实证",
    "AUTHOR_INTERPRETATION": "作者解读",
    "SECONDARY_EVIDENCE": "二手证据",
    "EXPERT_OPINION": "专家意见",
    "UNKNOWN": "未知",
}
STATUS_ZH = {
    "SUPPORTED": "支持",
    "PARTIALLY_SUPPORTED": "部分支持",
    "UNSUPPORTED": "不支持",
    "CONTRADICTORY": "相互矛盾",
    "AMBIGUOUS": "存疑/未判定",
    "OCR_UNCERTAIN": "OCR 不确定",
    "NOT_REPORTED": "未报告",
}
STATUS_CLS = {
    "SUPPORTED": "s-green", "PARTIALLY_SUPPORTED": "s-orange",
    "UNSUPPORTED": "s-red", "CONTRADICTORY": "s-red",
    "AMBIGUOUS": "s-gray", "OCR_UNCERTAIN": "s-gray",
    "NOT_REPORTED": "s-gray",
}
LEGACY_LEVEL_MAP = {
    "E1_EXPLICIT": "EXPLICIT", "E2_DERIVED": "DERIVED",
    "E3_REFERENCED": "REFERENCED", "E4_NR": "NOT_REPORTED",
    "E1 (EXPLICIT)": "EXPLICIT", "E2 (DERIVED)": "DERIVED",
    "E3 (REFERENCED)": "REFERENCED",
    "E4 (NR)": "NOT_REPORTED",
}


def _support_type(rec: Dict[str, Any]) -> str:
    st = rec.get("support_type")
    if st:
        return st
    legacy = rec.get("evidence_level", "")
    return LEGACY_LEVEL_MAP.get(legacy, legacy or "EXPLICIT")


def _strength_zh(rec: Dict[str, Any]) -> str:
    s = rec.get("evidence_strength")
    if not s:
        return "—"
    return STRENGTH_ZH.get(s, s)


def _claim_status(rec: Dict[str, Any]) -> str:
    st = rec.get("claim_status") or rec.get("status") or "AMBIGUOUS"
    if _support_type(rec) == "NOT_REPORTED" and st in ("SUPPORTED", "UNSUPPORTED"):
        # NR 语义防护：未报告不是论断，禁止显示为 支持/不支持
        st = "AMBIGUOUS"
    return st


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def render_report(data: Dict[str, Any]) -> str:
    """纯函数渲染核心：evidence JSON → 全中文 HTML 字符串（可单元测试）。"""
    pm = data.get("paper_metadata", {}) or {}
    recs: List[Dict[str, Any]] = data.get("evidence_records", []) or []
    verdict = data.get("auditor_verdict", {}) or {}

    n_nr = sum(1 for r in recs if _support_type(r) == "NOT_REPORTED")
    n_derived = sum(1 for r in recs if _support_type(r) == "DERIVED")
    sup_counter: Dict[str, int] = {}
    for r in recs:
        sup_counter[_support_type(r)] = sup_counter.get(_support_type(r), 0) + 1
    dist = " · ".join(f"{SUPPORT_ZH.get(k, k)}×{v}" for k, v in sup_counter.items())

    verdict_zh = {"PASS": "通过", "PASS_WITH_DOWNGRADES": "通过（含降级项）",
                  "REJECT": "驳回"}.get(verdict.get("verdict", ""), verdict.get("verdict", "—"))
    verdict_cls = "v-pass" if str(verdict.get("verdict", "")).startswith("PASS") else "v-reject"

    rows = []
    for i, r in enumerate(recs, 1):
        sup = _support_type(r)
        is_nr = sup == "NOT_REPORTED"
        row_cls = ' class="nr-row"' if is_nr else ""
        status = _claim_status(r)
        notes = r.get("notes") or ""
        extra = ('<div class="derive-tag">⚖ 派生记录：须附推导公式与输入出处</div>'
                 if sup == "DERIVED" and "公式" not in notes
                 else "")
        rows.append(f"""<tr{row_cls}>
<td class="c-idx">{i}</td>
<td><b>{esc(r.get('field') or r.get('field_name') or '')}</b>{('<div class="fid">' + esc(r.get('field_id')) + '</div>') if r.get('field_id') else ''}</td>
<td class="c-val">{esc(r.get('extracted_value') if r.get('extracted_value') not in (None, '') else 'NR（未报告）')}</td>
<td><span class="badge {SUPPORT_CLS.get(sup, 'b-gray')}">{SUPPORT_ZH.get(sup, esc(sup))}</span></td>
<td>{esc(_strength_zh(r))}</td>
<td class="c-quote">{('“' + esc(r.get('verbatim_quote')) + '”') if r.get('verbatim_quote') else '<span class="nr-note">— 全文未提及（程序化核查）—</span>'}</td>
<td class="c-loc">{('第 ' + esc(r['location']['page']) + ' 页') if r.get('location', {}).get('page') else '—'}{(('<div class="fid">' + esc(r['location'].get('section')) + '</div>') if r.get('location', {}).get('section') else '')}</td>
<td><span class="badge {STATUS_CLS.get(status, 's-gray')}">{STATUS_ZH.get(status, esc(status))}</span></td>
<td class="c-note">{esc(notes)}{extra}</td>
</tr>""")

    doi = pm.get("doi") or ""
    doi_html = (f'<a href="https://doi.org/{esc(doi)}">{esc(doi)}</a>' if doi else "—")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>证据抽取报告 — {esc(pm.get('title', ''))[:60]}</title>
<style>
 body {{ font-family: "Microsoft YaHei","PingFang SC",sans-serif; max-width: 1280px;
        margin: 0 auto; padding: 24px; background: #f6f8fa; color: #1a2b3c; line-height: 1.55; }}
 h1 {{ font-size: 22px; border-bottom: 3px solid #2f6fed; padding-bottom: 8px; }}
 h2 {{ font-size: 17px; margin: 28px 0 8px; color: #2f6fed; }}
 .meta {{ background: #fff; border: 1px solid #dde5ee; border-radius: 10px; padding: 14px 18px; }}
 .meta td {{ padding: 3px 10px 3px 0; vertical-align: top; }}
 .meta .k {{ color: #667; white-space: nowrap; font-size: 13px; }}
 .chips span {{ display: inline-block; background: #e8f0fe; border-radius: 12px;
               padding: 2px 12px; margin: 2px 6px 2px 0; font-size: 13px; }}
 table {{ border-collapse: collapse; width: 100%; background: #fff;
         border: 1px solid #dde5ee; border-radius: 10px; overflow: hidden; font-size: 13.5px; }}
 th {{ background: #2f6fed; color: #fff; padding: 8px 8px; text-align: left; white-space: nowrap; }}
 td {{ border-top: 1px solid #e8edf3; padding: 7px 8px; vertical-align: top; }}
 tr:nth-child(even) td {{ background: #fafbfd; }}
 .c-idx {{ color: #99a; font-size: 12px; }}
 .c-val {{ font-weight: 600; }}
 .c-quote {{ color: #456; font-style: italic; max-width: 340px; }}
 .c-note {{ color: #789; font-size: 12.5px; max-width: 200px; }}
 .fid {{ color: #9ab; font-size: 11px; font-family: Consolas, monospace; }}
 .badge {{ display: inline-block; padding: 1px 9px; border-radius: 10px; font-size: 12px; white-space: nowrap; }}
 .b-green {{ background: #e6f4ea; color: #137333; }} .b-blue {{ background: #e8f0fe; color: #1a56c4; }}
 .b-orange {{ background: #fff3e0; color: #a05a00; }} .b-gray {{ background: #eceff1; color: #546e7a; }}
 .s-green {{ background: #e6f4ea; color: #137333; }} .s-orange {{ background: #fff3e0; color: #a05a00; }}
 .s-red {{ background: #fde8e8; color: #b3261e; }} .s-gray {{ background: #eceff1; color: #546e7a; }}
 .nr-row td {{ color: #789; }} .nr-row .c-val {{ font-weight: 400; font-style: italic; }}
 .nr-note {{ color: #9ab; }}
 .derive-tag {{ color: #1a56c4; font-size: 12px; margin-top: 3px; }}
 .verdict {{ border-radius: 10px; padding: 12px 18px; margin: 14px 0; font-size: 15px; }}
 .v-pass {{ background: #e6f4ea; border-left: 5px solid #137333; }}
 .v-reject {{ background: #fde8e8; border-left: 5px solid #b3261e; }}
 .foot {{ color: #9ab; font-size: 12px; margin-top: 22px; }}
</style>
</head>
<body>
<h1>📑 证据抽取报告（全中文版）</h1>
<div class="meta"><table>
<tr><td class="k">文献标题</td><td><b>{esc(pm.get('title', ''))}</b></td></tr>
<tr><td class="k">作者</td><td>{esc('；'.join(pm.get('authors', [])) or '—')}</td></tr>
<tr><td class="k">年份 / 期刊</td><td>{esc(pm.get('year', ''))} ｜ {esc(pm.get('journal', '') or '—')}</td></tr>
<tr><td class="k">DOI</td><td>{doi_html}</td></tr>
<tr><td class="k">抽取模式</td><td>{esc((data.get('extraction_metadata', {}) or {}).get('mode', '—'))}
    ｜ Schema 类型：{esc((data.get('extraction_metadata', {}) or {}).get('schema_type', '—'))}</td></tr>
</table></div>

<h2>统计面板</h2>
<div class="chips">
 <span>证据记录共 <b>{len(recs)}</b> 条</span>
 <span>{dist or '—'}</span>
 <span>含派生计算（E2）<b>{n_derived}</b> 条</span>
 <span>未报告（E4）<b>{n_nr}</b> 条</span>
</div>

<h2>审计裁决</h2>
<div class="verdict {verdict_cls}">
 <b>{verdict_zh}</b>（核查清单通过：{'是' if verdict.get('checklist_passed') else '否'}）
 <div style="font-size:13px; margin-top:6px">{esc(verdict.get('auditor_notes') or '')}</div>
</div>

<h2>证据明细表（逐字引句绑定）</h2>
<table>
<tr><th>#</th><th>字段</th><th>抽取值</th><th>支撑类型</th><th>证据强度</th>
<th>逐字引句（最小充分）</th><th>位置</th><th>状态</th><th>备注</th></tr>
{''.join(rows)}
</table>

<div class="foot">
图例：支撑类型 = 该值如何锚定于本文原文（明示/派生/引自他文/未报告）；证据强度 = 该主张在更大综合中的科学分量；
状态 = 引句对抽取值的支撑关系。灰色斜体行 = 未报告（E4）记录——按 NR 语义防护条款，"未报告"不是"不支持"。
本报告由 evidence_matrix_html.py 自动生成（全中文、自包含、离线可读）。
</div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScholarFlow 证据抽取结果全中文 HTML 报告渲染器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="用法示例:\n  python evidence_matrix_html.py -i evidence.json -o evidence_report.html")
    parser.add_argument("-i", "--input", required=True,
                        help="证据 JSON（schemas/extraction_result.schema.json 契约）")
    parser.add_argument("-o", "--output", required=True, help="输出 HTML 报告路径")
    args = parser.parse_args()

    inp, out = Path(args.input), Path(args.output)
    if not inp.exists():
        print("[ERROR] 证据 JSON 不存在: %s" % inp, file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("[ERROR] 证据 JSON 无效: %s" % e, file=sys.stderr)
        sys.exit(2)

    html_text = render_report(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(f"[+] 全中文 HTML 报告已生成: {out}（{len(data.get('evidence_records', []))} 条证据记录）")


if __name__ == "__main__":
    main()
