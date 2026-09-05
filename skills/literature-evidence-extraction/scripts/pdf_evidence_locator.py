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
            sys.stderr.write(f"[WARN] PyPDF extraction error: {e}. Attempting basic stream scan.\n")

    # Basic fallback: read binary stream and scan uncompressed text blocks
    try:
        with open(pdf_path, "rb") as f:
            content = f.read().decode("latin-1", errors="ignore")
        # Find stream objects
        streams = re.findall(r"stream[\r\n]+(.*?)[\r\n]+endstream", content, re.DOTALL)
        combined_text = " ".join(streams)
        # Filter printable ASCII and symbols
        clean_text = re.sub(r"[^\x20-\x7E\r\n\t]", " ", combined_text)
        pages.append({"page": 1, "text": clean_text})
    except Exception as e:
        sys.stderr.write(f"[ERROR] Failed to extract text from {pdf_path}: {e}\n")
        pages.append({"page": 1, "text": ""})

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
