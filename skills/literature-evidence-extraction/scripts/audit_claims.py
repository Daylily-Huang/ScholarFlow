#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_claims.py
---------------
A command-line utility to:
1. Audit a list of academic claims/summaries against a paper's full text (PDF or TXT),
   helping the Evidence Auditor detect unsupported claims, contradictions, and missing citations.
2. Provide a 0-10 Relevance Gatekeeper score and PRUNE / PROCEED advice based on
   topic alignment (inspired by PaperQA2 benchmark filtering).

Usage:
    python audit_claims.py -i <paper.pdf> -c <claims.json>
    python audit_claims.py -i <paper.pdf> --relevance-topic "fecal DNA microsatellite black muntjac"
    python audit_claims.py -i <paper.txt> --claim "PCR volume was 20 uL"
"""

import os
import sys
import re
import json
import argparse
from typing import List, Dict, Any

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


def load_full_text(file_path: str) -> List[Dict[str, Any]]:
    """Load text and page numbers from PDF or text file."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    pages = []
    if file_path.lower().endswith(".pdf") and PYPDF_AVAILABLE:
        try:
            reader = pypdf.PdfReader(file_path)
            for idx, p in enumerate(reader.pages):
                pages.append({"page": idx + 1, "text": p.extract_text() or ""})
            return pages
        except Exception as e:
            sys.stderr.write(f"[WARN] PyPDF error: {e}, falling back to plain reading.\n")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Split by form-feed or page breaks
    chunks = content.split("\x0c")
    if len(chunks) > 1:
        for idx, chunk in enumerate(chunks):
            pages.append({"page": idx + 1, "text": chunk})
    else:
        pages.append({"page": 1, "text": content})

    return pages


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


def audit_single_claim(claim: str, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Audit one claim against full text pages."""
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", claim)
    words = [w.lower() for w in re.findall(r"[a-zA-Z\u4e00-\u9fa5]{3,}", claim)]

    best_match_page = None
    best_match_snippet = ""
    best_overlap = 0

    number_matched = False

    for p in pages:
        p_text = p["text"]
        p_text_lower = p_text.lower()
        overlap = sum(1 for w in words if w in p_text_lower)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match_page = p["page"]
            for w in words:
                idx = p_text_lower.find(w)
                if idx != -1:
                    start = max(0, idx - 100)
                    end = min(len(p_text), idx + 150)
                    best_match_snippet = p_text[start:end].replace("\n", " ").strip()
                    break

        if numbers:
            for num in numbers:
                if num in p_text:
                    number_matched = True

    if best_overlap == 0:
        verdict = "UNSUPPORTED"
        note = "No relevant text matching claim keywords found in document."
    elif numbers and not number_matched:
        verdict = "CONTRADICTORY"
        note = f"Keywords found on Page {best_match_page}, but specific claim numerical value ({numbers}) was not matched in the text."
    else:
        verdict = "SUPPORTED"
        note = f"Matched {best_overlap} keywords on Page {best_match_page}."

    return {
        "claim": claim,
        "verdict": verdict,
        "best_match_page": best_match_page,
        "evidence_snippet": best_match_snippet,
        "notes": note
    }


def main():
    parser = argparse.ArgumentParser(description="Audit academic claims and compute relevance score against paper text")
    parser.add_argument("-i", "--input", required=True, help="Path to input paper file (PDF or TXT)")
    parser.add_argument("-c", "--claims", default="", help="Path to JSON file containing list of claims")
    parser.add_argument("--claim", default="", help="A single claim string to audit")
    parser.add_argument("-r", "--relevance-topic", default="", help="Topic string to compute 0-10 relevance gatekeeper score")
    parser.add_argument("-o", "--output", default="", help="Path to write output markdown or JSON")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    pages = load_full_text(input_path)

    md_lines = [f"# Claim Audit & Relevance Report for: {os.path.basename(input_path)}\n"]

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
            "## 📊 声明与全文证据链比对表",
            "| Claim # | Claim Statement | Audit Verdict | Best Page | Evidence Snippet | Notes |",
            "|:---:|---|:---:|:---:|---|---|"
        ])
        for idx, r in enumerate(audit_results):
            v = r["verdict"]
            badge = f"**{v}**"
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
