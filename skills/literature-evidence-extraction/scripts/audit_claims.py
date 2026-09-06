#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_claims.py
---------------
Candidate Evidence Locator & Surface-Consistency Checker
Part of `literature-evidence-extraction` skill.

Capabilities:
1. Locates candidate evidence snippets in academic full text (PDF or TXT) by evaluating
   keyword and numerical co-location within local context windows.
2. Reports document parsing status and flags low-confidence extraction (e.g. scanned image PDFs).
3. Evaluates 0-10 relevance gatekeeper scores to inform pruning vs. in-depth extraction.

NOTE: This tool is an automated candidate evidence locator and consistency screener, NOT
a substitute for expert peer review or deep causal/semantic truth verification.

Usage:
    python audit_claims.py -i <paper.pdf> -c <claims.json>
    python audit_claims.py -i <paper.pdf> --relevance-topic "fecal DNA microsatellite snow leopard"
    python audit_claims.py -i <paper.txt> --claim "PCR volume was 20 uL"
"""

import os
import sys
import re
import json
import argparse
from typing import List, Dict, Any, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


def load_full_text(file_path: str, allow_degraded_pdf: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load text and page numbers from PDF or text file, and audit parse quality.

    Fails closed (PARSER_REQUIRED) if a PDF document is audited without a reliable
    PDF parser, unless allow_degraded_pdf is explicitly passed (P1-17).
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    pages = []
    parser_used = "plain_text"
    warning = None
    is_pdf = file_path.lower().endswith(".pdf")

    if is_pdf:
        if PYPDF_AVAILABLE:
            parser_used = "pypdf"
            try:
                reader = pypdf.PdfReader(file_path)
                for idx, p in enumerate(reader.pages):
                    pages.append({"page": idx + 1, "text": p.extract_text() or ""})
            except Exception as e:
                if not allow_degraded_pdf:
                    raise RuntimeError(f"PARSER_REQUIRED: pypdf error reading PDF: {e}. Pass --allow-degraded-pdf for best-effort fallback.")
                parser_used = "plain_text_fallback"
                warning = f"[WARN] PyPDF error: {e}, fell back to raw text reading."
                sys.stderr.write(f"{warning}\n")
        else:
            if not allow_degraded_pdf:
                raise RuntimeError("PARSER_REQUIRED: pypdf is not installed. Evidence-grade verification on PDF documents requires a reliable PDF parser (pip install 'scholarflow[pdf]' or pip install pypdf). Pass --allow-degraded-pdf for best-effort fallback.")
            parser_used = "plain_text_fallback"
            warning = "[WARN] pypdf is not installed. PDF text extraction is degraded."
            sys.stderr.write(f"{warning}\n")

    if not pages:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Split by form-feed or page breaks
        chunks = content.split("\x0c")
        if len(chunks) > 1:
            for idx, chunk in enumerate(chunks):
                pages.append({"page": idx + 1, "text": chunk})
        else:
            pages.append({"page": 1, "text": content})

    # Assess text density and parse quality
    total_chars = sum(len(p.get("text", "")) for p in pages)
    avg_chars_per_page = total_chars / max(1, len(pages))

    if is_pdf and avg_chars_per_page < 100:
        quality = "LOW_OCR_SUSPECT"
        warning = "[WARN] Very low character density (<100 chars/page) in PDF. Document may be a scanned image requiring OCR. Evidence localization confidence: LOW."
    elif parser_used == "plain_text_fallback" and is_pdf:
        quality = "LOW_FALLBACK"
    else:
        quality = "HIGH"

    parse_status = {
        "file_path": file_path,
        "parser": parser_used,
        "total_pages": len(pages),
        "total_characters": total_chars,
        "avg_chars_per_page": round(avg_chars_per_page, 1),
        "extraction_quality": quality,
        "warning": warning
    }

    return pages, parse_status


def compute_relevance_score(topic: str, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute 0-10 relevance score and PRUNE/PROCEED verdict."""
    topic_words = [w.lower() for w in re.findall(r"[a-zA-Z\u4e00-\u9fa5]{2,}", topic)]
    if not topic_words:
        return {"score": 5, "decision": "PROCEED", "rationale": "Empty topic provided, proceeding by default."}

    full_text = " ".join([p["text"].lower() for p in pages])
    first_page_text = pages[0]["text"].lower() if pages else ""

    # Frequency analysis
    word_hits = {}
    for w in topic_words:
        count = len(re.findall(re.escape(w), full_text))
        word_hits[w] = count

    matched_words = sum(1 for w, c in word_hits.items() if c > 0)
    match_ratio = matched_words / len(topic_words)
    total_hits = sum(word_hits.values())

    # Check title / first page hits (high weight)
    first_page_hits = sum(1 for w in topic_words if w in first_page_text)
    first_page_ratio = first_page_hits / len(topic_words)

    # Score calculation (0 to 10)
    base_score = match_ratio * 6.0  # up to 6 pts for keyword coverage
    density_score = min(2.5, total_hits / 10.0)  # up to 2.5 pts for repetition/density
    prominence_score = first_page_ratio * 1.5  # up to 1.5 pts for front matter prominence

    raw_score = round(base_score + density_score + prominence_score)
    score = max(0, min(10, raw_score))

    decision = "PROCEED" if score >= 6 else "PRUNE"
    if decision == "PROCEED":
        rationale = f"Sufficient topic alignment: {matched_words}/{len(topic_words)} keywords detected ({total_hits} total occurrences across text)."
    else:
        rationale = f"Low relevance (score {score}/10 < 6 threshold): only {matched_words}/{len(topic_words)} keywords detected. Recommend pruning before deep extraction."

    return {
        "score": score,
        "decision": decision,
        "matched_keywords": f"{matched_words}/{len(topic_words)}",
        "total_hits": total_hits,
        "rationale": rationale
    }


def audit_single_claim(claim: str, pages: List[Dict[str, Any]], window_chars: int = 250) -> Dict[str, Any]:
    """
    Audit one claim against full text pages using context-aware co-location.
    Evaluates whether numbers and key terms co-occur in the same local window.
    """
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", claim)
    raw_words = re.findall(r"[a-zA-Z\u4e00-\u9fa5]{3,}", claim)
    common_stops = {
        "the", "and", "that", "this", "with", "from", "were", "been", "have", "then",
        "also", "than", "each", "both", "such", "into", "more", "most", "some", "what"
    }
    words = [w.lower() for w in raw_words if w.lower() not in common_stops]
    if not words:
        words = [w.lower() for w in raw_words]

    best_match_page = None
    best_match_snippet = ""
    best_overlap = 0
    best_window_has_numbers = False

    # Check if numbers exist anywhere in document
    numbers_in_doc = set()
    if numbers:
        for p in pages:
            for num in numbers:
                if num in p["text"]:
                    numbers_in_doc.add(num)

    for p in pages:
        p_text = p["text"]
        p_text_lower = p_text.lower()
        
        # Search match positions for each word
        word_positions = []
        for w in words:
            for m in re.finditer(re.escape(w), p_text_lower):
                word_positions.append(m.start())
                
        if not word_positions:
            continue
            
        # Scan candidate context windows centered around each match
        for pos in word_positions:
            start = max(0, pos - window_chars)
            end = min(len(p_text), pos + window_chars)
            window_text = p_text[start:end]
            window_lower = window_text.lower()
            
            # Count distinct keywords present in this window
            local_overlap = sum(1 for w in words if w in window_lower)
            local_has_num = any(num in window_text for num in numbers) if numbers else True
            
            # Prefer windows with higher keyword overlap, with tie-break favoring number co-location
            score = local_overlap + (1.5 if (numbers and local_has_num) else 0)
            best_score = best_overlap + (1.5 if (numbers and best_window_has_numbers) else 0)
            
            if score > best_score:
                best_overlap = local_overlap
                best_window_has_numbers = local_has_num
                best_match_page = p["page"]
                best_match_snippet = window_text.replace("\n", " ").strip()

    if best_overlap == 0:
        verdict = "NO_SURFACE_MATCH"
        note = "No matching topical keywords located within local text windows."
    elif numbers:
        if best_window_has_numbers:
            verdict = "LOCATED_CO_OCCURRING"
            note = f"Keywords ({best_overlap} matched) and claim numerical value co-occur within local context on Page {best_match_page}."
        elif numbers_in_doc:
            verdict = "NUMBER_DISLOCATED"
            note = f"Keywords located on Page {best_match_page}, but claim numbers {list(numbers_in_doc)} only appear in disconnected parts of document."
        else:
            verdict = "NUMERICAL_MISMATCH"
            note = f"Keywords located on Page {best_match_page}, but claim numerical value ({numbers}) is absent from entire document."
    else:
        verdict = "CANDIDATE_LOCATED"
        note = f"Candidate text located with {best_overlap} matching keywords on Page {best_match_page} (qualitative claim)."

    return {
        "claim": claim,
        "verdict": verdict,
        "best_match_page": best_match_page,
        "evidence_snippet": best_match_snippet,
        "notes": note,
        "co_located": best_window_has_numbers if numbers else True
    }


def main():
    parser = argparse.ArgumentParser(
        description="Candidate Evidence Locator & Surface-Consistency Checker (audit_claims.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Note: This script performs surface text pattern matching and keyword/number co-location.
It assists researchers in locating candidate paragraphs and checking surface consistency,
but does NOT perform causal or semantic truth verification.
        """
    )
    parser.add_argument("-i", "--input", required=True, help="Path to input paper file (PDF or TXT)")
    parser.add_argument("-c", "--claims", default="", help="Path to JSON file containing list of claims")
    parser.add_argument("--claim", default="", help="A single claim string to audit")
    parser.add_argument("-r", "--relevance-topic", default="", help="Topic string to compute 0-10 relevance gatekeeper score")
    parser.add_argument("--allow-degraded-pdf", action="store_true", help="Allow degraded plain-text fallback if PDF parser is missing or fails (bypasses fail-closed gate)")
    parser.add_argument("-o", "--output", default="", help="Path to write output markdown or JSON")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    try:
        pages, parse_status = load_full_text(input_path, allow_degraded_pdf=args.allow_degraded_pdf)
    except RuntimeError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(2)

    md_lines = [
        f"# Candidate Evidence Locator & Surface Consistency Report: {os.path.basename(input_path)}\n",
        "> 💡 **定位说明**：本工具为候选证据定位器（Candidate Evidence Locator）与浅层字符串协同匹配器，旨在快速定位原文段落并检查数字-实体共现（Co-location）。本工具**不构成**端到端因果语义与方法学真实性判定，请结合上下文人工复核。\n",
        "## 📄 文档解析与抽取质量状态 (Document Parse Status)",
        f"- **解析引擎**：`{parse_status['parser']}`",
        f"- **文档页数**：`{parse_status['total_pages']}` (总字符数: {parse_status['total_characters']})",
        f"- **解析质量评级**：`[{parse_status['extraction_quality']}]`"
    ]

    if parse_status.get("warning"):
        md_lines.append(f"> ⚠️ **解析质量警告**：{parse_status['warning']}")

    md_lines.append("\n---")

    # 1. Relevance Gatekeeper Section (if topic provided)
    if args.relevance_topic:
        rel = compute_relevance_score(args.relevance_topic, pages)
        badge = "PROCEED" if rel["decision"] == "PROCEED" else "PRUNE"
        md_lines.extend([
            "## 🎯 相关性前置快速剪枝评估 (Relevance Gatekeeper)",
            f"- **评估主题**：`{args.relevance_topic}`",
            f"- **相关性评分 (0-10)**：`{rel['score']} / 10`",
            f"- **剪枝决议**：`[{badge}]` ({'继续深入抽取' if badge=='PROCEED' else '低于6分阈值，建议剪枝跳过'})",
            f"- **关键词覆盖**：{rel['matched_keywords']} (全篇命中频次: {rel['total_hits']})",
            f"- **判定依据**：{rel['rationale']}\n",
            "---"
        ])

    # 2. Claim Audit Section
    claim_list = []
    if args.claim:
        claim_list.append(args.claim)
    elif args.claims:
        claims_file = os.path.abspath(args.claims)
        if not os.path.isfile(claims_file):
            sys.stderr.write(f"Error: Claims file does not exist: {claims_file}\n")
            sys.exit(1)
        with open(claims_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        claim_list.append(item)
                    elif isinstance(item, dict) and "claim" in item:
                        claim_list.append(item["claim"])

    if claim_list:
        audit_results = [audit_single_claim(c, pages) for c in claim_list]
        md_lines.extend([
            "## 📊 候选证据定位与协同匹配表 (Candidate Evidence Localization)",
            "| Claim # | Claim Statement | Localization Status | Best Page | Co-Located Snippet | Diagnostic Notes |",
            "|:---:|---|:---:|:---:|---|---|"
        ])
        for idx, r in enumerate(audit_results):
            v = r["verdict"]
            badge = f"`{v}`"
            snippet = r["evidence_snippet"].replace("|", "\\|")
            note = r["notes"].replace("|", "\\|")
            c_text = r["claim"].replace("|", "\\|")
            md_lines.append(f"| C{idx+1} | {c_text} | {badge} | Page {r['best_match_page'] or '-'} | {snippet} | {note} |")

    report_content = "\n".join(md_lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Audit report saved to: {args.output}")
    else:
        print(report_content)


if __name__ == "__main__":
    main()
