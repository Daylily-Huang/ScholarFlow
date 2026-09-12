#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_evidence_locator.py

A command-line tool to inspect PDF and text documents, locate keyword evidence
with exact page/paragraph context, and detect OCR/character anomalies
(e.g., corrupted μL, ±, ambiguous primer bases).

Usage:
    python pdf_evidence_locator.py -i <paper.pdf> -q "annealing,PCR volume,BSA"
    python pdf_evidence_locator.py -i <paper.txt> --detect-ocr-anomalies
"""

import os
import sys
import re
import json
import argparse
from typing import List, Dict, Any, Optional

# Attempt to import PyPDF if available, otherwise use text fallback or pure parser
PYPDF_AVAILABLE = False
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    try:
        import PyPDF2 as pypdf
        PYPDF_AVAILABLE = True
    except ImportError:
        PYPDF_AVAILABLE = False


def extract_pages_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract text from PDF file page by page."""
    pages = []
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if PYPDF_AVAILABLE:
        try:
            reader = pypdf.PdfReader(pdf_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append({"page": idx + 1, "text": text})
            return pages
        except Exception as e:
            sys.stderr.write(f"[WARN] PyPDF extraction error: {e}. Attempting fallback extractor.\n")

    # 回退：纯标准库提取器（解压 FlateDecode 内容流 + 解析交叉引用流）。
    # 旧实现在此直接把整个 PDF 以 latin-1 解码后过滤可打印字符，
    # 对压缩内容流只能得到二进制噪声，却会报出很大的 total_character_count，
    # 把「没有提取到文本」伪装成「提取到了文本、只是关键词没命中」（见该模块 docstring）。
    try:
        try:
            from extract_pdf_text import extract_pdf_pages
        except ImportError:
            # 以文件路径直接执行时脚本目录不一定在 sys.path 上
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from extract_pdf_text import extract_pdf_pages
        result = extract_pdf_pages(pdf_path)
        warnings = result.get("warnings") or []
        if warnings:
            sys.stderr.write("[WARN] fallback extractor warnings: %s\n" % "; ".join(warnings))
        if result.get("pages"):
            pages = [
                {"page": p["page"], "text": p["text"],
                 "extraction_engine": result.get("engine"),
                 "degraded": result.get("degraded", True),
                 "warnings": list(warnings)}
                for p in result["pages"]
            ]
            # 「一个字符都没提取到」必须显式标注：否则调用方会把工具性失败
            # 当成「文献里没有这句话」（真实闭环中就是这么误判的）。
            if not any(p["text"] for p in pages):
                pages[0]["warnings"].append("TEXT_UNAVAILABLE")
                sys.stderr.write(
                    "[ERROR] 该 PDF 未提取到任何文本（疑似扫描版或 CID 编码）。"
                    "必须改用 OCR，不得把空文本当作「关键词未命中」。\n"
                )
            return pages
    except Exception as e:
        sys.stderr.write(f"[WARN] fallback extractor unavailable: {e}\n")

    # 最后兜底：解压失败时**显式标空**，并告知调用方文本不可用，
    # 不再返回二进制噪声冒充正文。
    sys.stderr.write(
        "[ERROR] 无法从该 PDF 提取文本（无 pypdf 且回退提取器失败）。"
        "若为扫描版请改用 OCR；不要把空文本当成「关键词未命中」。\n"
    )
    pages.append({"page": 1, "text": "", "extraction_engine": "none",
                  "degraded": True, "warnings": ["TEXT_UNAVAILABLE"]})
    return pages


def extract_pages_from_text(txt_path: str) -> List[Dict[str, Any]]:
    """Extract text from plain text file."""
    with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    # Split by common page markers if present, else return single block
    page_splits = re.split(r"(?:---+\s*Page\s*(\d+)\s*---+|\f)", content, flags=re.IGNORECASE)
    if len(page_splits) > 1:
        pages = []
        cur_p = 1
        for chunk in page_splits:
            if not chunk:
                continue
            if chunk.strip().isdigit():
                cur_p = int(chunk.strip())
            else:
                pages.append({"page": cur_p, "text": chunk})
                cur_p += 1
        return pages
    else:
        return [{"page": 1, "text": content}]


def detect_ocr_anomalies(text: str) -> List[Dict[str, Any]]:
    """Detect suspicious character anomalies in OCR extracted academic text."""
    anomalies = []
    
    # 1. μL anomalies: e.g. "?L", "uL", "ul", "mkL"
    for m in re.finditer(r"\b\d+(?:\.\d+)?\s*([?]L|uL|ul)\b", text):
        anomalies.append({
            "type": "unit_anomaly",
            "snippet": m.group(0),
            "issue": f"Possible corrupted μL unit: '{m.group(1)}'"
        })

    # 2. Temperature anomalies: e.g. "550C", "55·C", "55° C"
    for m in re.finditer(r"\b\d{2,3}(?:[0·]C|°\s*C)\b", text):
        anomalies.append({
            "type": "temp_anomaly",
            "snippet": m.group(0),
            "issue": "Possible corrupted degree Celsius symbol"
        })

    # 3. Plus-minus anomalies: missing ± or replaced by ?
    for m in re.finditer(r"\b\d+(?:\.\d+)?\s*[?]\s*\d+(?:\.\d+)?\b", text):
        anomalies.append({
            "type": "symbol_anomaly",
            "snippet": m.group(0),
            "issue": "Possible corrupted ± (plus-minus) sign"
        })

    # 4. Primer sequence corruptions: letters other than A,C,G,T,R,Y,S,W,K,M,B,D,H,V,N
    for m in re.finditer(r"5['’]?-([A-Z0-9?]{15,40})-3['’]?", text):
        seq = m.group(1)
        invalid_chars = set(seq) - set("ACGTRYWSKMDHVN")
        if invalid_chars:
            anomalies.append({
                "type": "primer_anomaly",
                "snippet": m.group(0),
                "issue": f"Invalid nucleotide characters in primer: {invalid_chars}"
            })

    return anomalies


def search_evidence_keywords(pages: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    """Search for keywords across pages and extract minimal context snippets."""
    results = []
    for kw in keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        kw_pattern = re.compile(re.escape(kw_clean), re.IGNORECASE)
        kw_matches = []
        for p in pages:
            text = p["text"]
            for match in kw_pattern.finditer(text):
                start = max(0, match.start() - 150)
                end = min(len(text), match.end() + 150)
                snippet = text[start:end].replace("\n", " ").strip()
                kw_matches.append({
                    "page": p["page"],
                    "offset": match.start(),
                    "snippet": f"...{snippet}..."
                })
        results.append({
            "keyword": kw_clean,
            "match_count": len(kw_matches),
            "occurrences": kw_matches[:10]  # Cap top 10 occurrences
        })
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Academic Literature Evidence & OCR Anomaly Locator for literature-evidence-extraction Skill"
    )
    parser.add_argument("-i", "--input", required=True, help="Path to PDF or plain text paper file")
    parser.add_argument("-q", "--queries", default="", help="Comma-separated keywords to search (e.g. 'annealing,PCR volume,BSA')")
    parser.add_argument("--detect-ocr-anomalies", action="store_true", help="Flag suspicious OCR glitches (units, degrees, primers)")
    parser.add_argument("-o", "--output", default="", help="Path to write JSON output (default: stdout)")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        sys.stderr.write(f"Error: Input file does not exist: {input_path}\n")
        sys.exit(1)

    # 1. Extract pages
    if input_path.lower().endswith(".pdf"):
        pages = extract_pages_from_pdf(input_path)
    else:
        pages = extract_pages_from_text(input_path)

    total_text = " ".join([p["text"] for p in pages])
    output_data = {
        "file": input_path,
        "total_pages": len(pages),
        "total_character_count": len(total_text),
        "queries": [],
        "ocr_anomalies": []
    }

    # 2. Search queries
    if args.queries:
        keywords = [k.strip() for k in args.queries.split(",") if k.strip()]
        output_data["queries"] = search_evidence_keywords(pages, keywords)

    # 3. Detect anomalies
    if args.detect_ocr_anomalies or not args.queries:
        output_data["ocr_anomalies"] = detect_ocr_anomalies(total_text)

    # 4. Output
    json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Evidence locator results written to: {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
