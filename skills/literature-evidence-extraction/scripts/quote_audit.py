#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quote_audit.py
--------------
ScholarFlow mechanical quote back-verification gate (literature-evidence-extraction).

For every `verbatim_quote` in an evidence JSON (schemas/extraction_result.schema.json),
verifies that the quoted text actually occurs in the source document (PDF or TXT).
A quote that cannot be located in the source is mechanically demoted to UNSUPPORTED:
no language model judgement is involved in this check.

Rationale: the E1-E4 evidence contract anchors every extracted value to a verbatim
quote. The quote itself is the anchor of anchors — and whether it exists in the
source is a string-matching problem, not a reasoning problem. This script turns
"the auditor re-read the paper" (same-model self-check) into a hard, reproducible gate.

Matching is robust to PDF extraction artifacts:
1. EXACT       — match after whitespace collapsing + confusable-character normalization
                 (curly quotes, µ/μ, unicode dashes, soft hyphens, NFC).
2. HYPHEN_JOIN — match after re-joining hyphenated line breaks ("step- wise" -> "stepwise").
3. FUZZY       — best sliding-window token containment >= threshold (default 0.95).
                 Reported as a warning, not a failure (unless --strict).
4. NOT_FOUND   — no acceptable match: gate failure.

Standard Library Only (pypdf optional, only needed for PDF sources).

Usage:
    python quote_audit.py -i evidence.json -s paper.pdf
    python quote_audit.py -i evidence.json -s paper.txt --strict -o audit_report.json
Exit code: 0 = all quotes verified; 1 = at least one NOT_FOUND (or FUZZY under --strict);
           2 = input error (file/schema missing, pypdf unavailable for PDF source).
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MIN_QUOTE_LEN = 15          # shorter quotes cannot be located reliably
FUZZY_THRESHOLD = 0.95      # token containment ratio for FUZZY match
FUZZY_WINDOW_CAP = 400      # max source tokens scanned for fuzzy windows per quote

CONFUSABLE_TABLE = {
    "\u2018": "'", "\u2019": "'", "\u201a": ",",          # single curly quotes
    "\u201c": '"', "\u201d": '"',                          # double curly quotes
    "\u00ab": '"', "\u00bb": '"',                          # guillemets
    "\u00b5": "\u03bc",                                    # MICRO SIGN -> GREEK MU
    "\u2013": "-", "\u2014": "-", "\u2212": "-",           # en/em/minus dash
    "\u2010": "-", "\u2011": "-", "\u00ad": "",            # hyphen variants, soft hyphen
    "\u00a0": " ", "\u2028": " ", "\u2029": " ",           # nbsp, line/para separators
    "\ufb01": "fi", "\ufb02": "fl",                        # ligatures
}


def normalize_text(text: str) -> str:
    """NFC + confusable-character mapping + whitespace collapse + lowercase."""
    t = unicodedata.normalize("NFC", text)
    for src, dst in CONFUSABLE_TABLE.items():
        t = t.replace(src, dst)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def join_hyphen_breaks(text: str) -> str:
    """Re-join words split by hyphenated line breaks: 'step- wise' -> 'stepwise'."""
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text, re.UNICODE)


def _best_fuzzy_window(needle_tokens: List[str], haystack_tokens: List[str]) -> float:
    """Max unique-token containment of the needle across sliding windows of the haystack.

    Both sides are reduced to unique token sets: duplicate words (e.g. "was ... was")
    would otherwise double-penalize containment for extraction-noise quotes.
    """
    needle_set = set(needle_tokens)
    m = len(needle_set)
    if m == 0 or not haystack_tokens:
        return 0.0
    best = 0.0
    end_limit = min(len(haystack_tokens), FUZZY_WINDOW_CAP)
    for start in range(0, max(1, len(haystack_tokens) - m + 1)):
        if start >= end_limit:
            break
        window = haystack_tokens[start:start + m]
        ratio = len(needle_set & set(window)) / m
        if ratio > best:
            best = ratio
            if best == 1.0:
                break
    return best


def audit_evidence(evidence: Dict[str, Any], source_text: str,
                   min_quote_len: int = MIN_QUOTE_LEN,
                   fuzzy_threshold: float = FUZZY_THRESHOLD) -> Dict[str, Any]:
    """
    Pure audit core: verify every verbatim_quote in evidence records against source text.
    Returns a report dict; file I/O stays in main() so this is unit-testable.
    """
    norm_source = normalize_text(source_text)
    joined_source = join_hyphen_breaks(norm_source)
    source_tokens = tokenize(joined_source)

    entries: List[Dict[str, Any]] = []
    counts = {"exact_match": 0, "hyphen_join": 0, "fuzzy_match": 0,
              "not_found": 0, "skipped_no_quote": 0, "too_short": 0}

    for rec in evidence.get("evidence_records", []):
        quote = rec.get("verbatim_quote") or ""
        field_id = rec.get("field_id", "")
        field_name = rec.get("field_name", "")
        level = rec.get("evidence_level", "")
        base = {"field_id": field_id, "field_name": field_name,
                "evidence_level": level, "quote": quote}

        if not quote.strip():
            counts["skipped_no_quote"] += 1
            entries.append({**base, "match_type": "SKIPPED_NO_QUOTE",
                            "detail": "Empty quote (E4_NR or not yet filled)."})
            continue

        if len(quote.strip()) < min_quote_len:
            counts["too_short"] += 1
            entries.append({**base, "match_type": "TOO_SHORT",
                            "detail": f"Quote shorter than {min_quote_len} chars; cannot verify mechanically."})
            continue

        norm_quote = normalize_text(quote)
        if norm_quote in norm_source:
            counts["exact_match"] += 1
            entries.append({**base, "match_type": "EXACT",
                            "detail": "Found after confusable-char/whitespace normalization."})
            continue

        if join_hyphen_breaks(norm_quote) in joined_source:
            counts["hyphen_join"] += 1
            entries.append({**base, "match_type": "HYPHEN_JOIN",
                            "detail": "Found after re-joining hyphenated line breaks."})
            continue

        ratio = _best_fuzzy_window(tokenize(norm_quote), source_tokens)
        if ratio >= fuzzy_threshold:
            counts["fuzzy_match"] += 1
            entries.append({**base, "match_type": "FUZZY",
                            "detail": f"Token containment {ratio:.3f} >= {fuzzy_threshold}; "
                                      "likely extraction artifact, verify manually."})
            continue

        counts["not_found"] += 1
        entries.append({**base, "match_type": "NOT_FOUND",
                        "detail": "Quote not located in source document. "
                                  "Per the E1-E4 contract this record must be demoted "
                                  "(quote unverified -> treat as UNSUPPORTED until human-confirmed)."})

    total = len(entries)
    gate_failed = counts["not_found"] > 0
    return {
        "summary": {
            "total_records": total,
            **counts,
            "gate_failed": gate_failed,
        },
        "entries": entries,
    }


def gate_failed(report: Dict[str, Any], strict: bool = False) -> bool:
    """Hard gate: any NOT_FOUND fails; FUZZY counts as failure only under --strict."""
    s = report["summary"]
    if s["not_found"] > 0:
        return True
    if strict and s["fuzzy_match"] > 0:
        return True
    return False


def load_source_text(path: Path) -> str:
    """Read TXT directly; extract PDF text via pypdf/PyPDF2 if available."""
    if path.suffix.lower() == ".pdf":
        pypdf = None
        try:
            import pypdf as pypdf  # noqa: F811
        except ImportError:
            try:
                import PyPDF2 as pypdf  # type: ignore
            except ImportError:
                print("[ERROR] PDF source requires pypdf: pip install pypdf "
                      "(or provide a plain-text extraction instead).", file=sys.stderr)
                sys.exit(2)
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScholarFlow mechanical quote back-verification gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python quote_audit.py -i evidence.json -s paper.pdf
  python quote_audit.py -i evidence.json -s paper.txt --strict -o audit_report.json
Exit codes: 0 all verified | 1 gate failed | 2 input error
        """)
    parser.add_argument("-i", "--evidence", required=True,
                        help="Evidence JSON following schemas/extraction_result.schema.json")
    parser.add_argument("-s", "--source", required=True, help="Source document (.pdf or .txt)")
    parser.add_argument("-o", "--output", help="Optional path to write the JSON audit report")
    parser.add_argument("--strict", action="store_true",
                        help="Treat FUZZY matches as gate failures as well")
    parser.add_argument("--min-quote-len", type=int, default=MIN_QUOTE_LEN)
    args = parser.parse_args()

    ev_path, src_path = Path(args.evidence), Path(args.source)
    if not ev_path.exists() or not src_path.exists():
        print("[ERROR] Evidence or source file not found.", file=sys.stderr)
        sys.exit(2)

    try:
        evidence = json.loads(ev_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Evidence JSON invalid: {e}", file=sys.stderr)
        sys.exit(2)

    source_text = load_source_text(src_path)
    report = audit_evidence(evidence, source_text, min_quote_len=args.min_quote_len)
    report["summary"]["gate_failed"] = gate_failed(report, strict=args.strict)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Audit report saved to: {out}")

    s = report["summary"]
    print("=" * 56)
    print(" ScholarFlow Quote Back-Verification Report")
    print("=" * 56)
    print(f" Records in evidence JSON : {s['total_records']}")
    print(f" EXACT match              : {s['exact_match']}")
    print(f" HYPHEN_JOIN match        : {s['hyphen_join']}")
    print(f" FUZZY match (>=thr)      : {s['fuzzy_match']}" + ("  [--strict: FAILED]" if args.strict and s['fuzzy_match'] else ""))
    print(f" TOO_SHORT (unverifiable) : {s['too_short']}")
    print(f" SKIPPED (empty quote)    : {s['skipped_no_quote']}")
    print(f" NOT_FOUND                : {s['not_found']}")
    print("=" * 56)
    for e in report["entries"]:
        if e["match_type"] in ("NOT_FOUND", "TOO_SHORT", "FUZZY"):
            print(f" [{e['match_type']}] {e['field_id']} {e['field_name']}: {e['detail']}")

    sys.exit(1 if report["summary"]["gate_failed"] else 0)


if __name__ == "__main__":
    main()
