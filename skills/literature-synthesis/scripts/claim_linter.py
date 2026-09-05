#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_linter.py
---------------
ScholarFlow mechanical traceability linter for narrative reviews (literature-synthesis).

Enforces the "Claims first, narrative later" contract at the prose level:
every factual statement in a narrative review must carry a Claim ID reference
(e.g. [CLM-001]) that resolves to a claim in the Claim-Evidence Matrix
(assets/claim_evidence_matrix_schema.json). An assertion that cannot be traced
to any matrix claim is an "orphan claim" — the highest-risk hallucination
surface of the synthesis stage.

This linter is deliberately mechanical. It performs three checks:

1. UNRESOLVED_REFS   — Claim IDs cited in the narrative but absent from the matrix.
                       Hard failure (exit 1).
2. UNCITED_CLAIMS    — Matrix claims never referenced in the narrative.
                       Coverage warning; the synthesis may legitimately drop
                       claims, but the list makes the omission auditable.
3. FLAGGED_PARAGRAPHS — Paragraphs that look like factual assertions (contain
                       reporting verbs or quantitative values) yet carry no
                       Claim ID reference. Heuristic (documented limitation:
                       it cannot understand meaning), intended as a human-review
                       pointer, not a verdict. Only fails the gate under --strict.

It can also schema-lite-validate the matrix itself (--check-matrix): required
keys, stance/evidence_tier enums, duplicate claim IDs.

Standard Library Only (Zero third-party pip dependencies required).

Usage:
    python claim_linter.py -i narrative_review.md -m claim_matrix.json
    python claim_linter.py -i narrative_review.md -m claim_matrix.json --strict --check-matrix
Exit code: 0 = clean (or warnings only without --strict); 1 = gate failed; 2 = input error.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CLAIM_REF_RE = re.compile(r"\bCLM-\d{3,}\b", re.IGNORECASE)

# Heuristic cues for "this sentence asserts a fact": reporting verbs or quantities.
FACTUAL_CUE_RE = re.compile(
    r"(研究表明|结果显示|研究发现|据报道|有研究报道|证据表明|"
    r"demonstrat\w+|reported|showed that|found that|indicated that|suggest\w* that|"
    r"\d+(?:\.\d+)?\s*%)",
    re.IGNORECASE,
)

VALID_STANCES = {"SUPPORT", "REFUTE", "CONDITIONAL", "NEUTRAL"}
VALID_TIERS = {"E1", "E2", "E3", "E4"}
REQUIRED_CLAIM_KEYS = ["claim_id", "paper_id", "stance", "evidence_tier", "claim_text"]


def extract_claim_refs(narrative: str) -> List[str]:
    """Ordered, de-duplicated Claim IDs referenced in the narrative."""
    seen, ordered = set(), []
    for m in CLAIM_REF_RE.finditer(narrative):
        ref = m.group(0).upper()
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def _is_prose_paragraph(paragraph: str) -> bool:
    """Skip headings, table rows, blockquotes and list bullets — they are not narrative prose."""
    lines = [ln for ln in paragraph.strip().splitlines() if ln.strip()]
    if not lines:
        return False
    return not all(
        ln.lstrip().startswith(("#", "|", ">", "-", "*", "+"))
        or re.match(r"^\d+[.)]\s", ln.lstrip())
        for ln in lines
    )


def lint_narrative(narrative: str, matrix: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure lint core: cross-check narrative prose against the claim matrix.
    Returns a report dict; file I/O stays in main() so this is unit-testable.
    """
    claims = matrix.get("claims", [])
    matrix_ids = {c.get("claim_id", "").upper() for c in claims}

    refs = extract_claim_refs(narrative)
    unresolved = [r for r in refs if r not in matrix_ids]
    uncited = sorted(matrix_ids - set(refs))

    flagged_paragraphs = []
    for para in re.split(r"\n\s*\n", narrative):
        if not _is_prose_paragraph(para):
            continue
        if FACTUAL_CUE_RE.search(para) and not CLAIM_REF_RE.search(para):
            snippet = re.sub(r"\s+", " ", para.strip())[:120]
            flagged_paragraphs.append(snippet)

    total_claims = len(matrix_ids)
    cited = total_claims - len(uncited)
    coverage = round(cited / total_claims, 4) if total_claims else 0.0

    return {
        "referenced_claim_ids": refs,
        "unresolved_refs": unresolved,
        "uncited_claims": uncited,
        "flagged_paragraphs": flagged_paragraphs,
        "stats": {
            "matrix_claim_count": total_claims,
            "referenced_count": len(refs),
            "unresolved_count": len(unresolved),
            "citation_coverage": coverage,
            "flagged_paragraph_count": len(flagged_paragraphs),
        },
        "notes": (
            "Flagged paragraphs are heuristic pointers (reporting verbs / quantities "
            "without a Claim ID), not proof of hallucination. Human review decides."
        ),
    }


def validate_matrix(matrix: Dict[str, Any]) -> List[str]:
    """Schema-lite validation of the Claim-Evidence Matrix (no jsonschema dependency)."""
    issues: List[str] = []
    claims = matrix.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["Matrix has no `claims` array."]
    seen_ids = set()
    for i, c in enumerate(claims):
        tag = f"claims[{i}]"
        for key in REQUIRED_CLAIM_KEYS:
            if key not in c or c.get(key) in (None, ""):
                issues.append(f"{tag}: missing required key `{key}`.")
        cid = str(c.get("claim_id", "")).upper()
        if cid:
            if cid in seen_ids:
                issues.append(f"{tag}: duplicate claim_id `{cid}`.")
            seen_ids.add(cid)
        if c.get("stance") and str(c["stance"]).upper() not in VALID_STANCES:
            issues.append(f"{tag}: invalid stance `{c['stance']}` (allowed: {sorted(VALID_STANCES)}).")
        if c.get("evidence_tier") and str(c["evidence_tier"]).upper() not in VALID_TIERS:
            issues.append(f"{tag}: invalid evidence_tier `{c['evidence_tier']}` (allowed: {sorted(VALID_TIERS)}).")
    return issues


def gate_failed(report: Dict[str, Any], strict: bool = False) -> bool:
    """Hard gate: unresolved refs always fail; flagged paragraphs fail only under --strict."""
    if report["unresolved_refs"]:
        return True
    if strict and report["flagged_paragraphs"]:
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScholarFlow narrative-review traceability linter (Claim ID gate)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python claim_linter.py -i narrative_review.md -m claim_matrix.json
  python claim_linter.py -i narrative_review.md -m claim_matrix.json --strict --check-matrix
Exit codes: 0 clean | 1 gate failed | 2 input error
        """)
    parser.add_argument("-i", "--input", required=True, help="Narrative review Markdown file")
    parser.add_argument("-m", "--matrix", required=True,
                        help="Claim-Evidence Matrix JSON (assets/claim_evidence_matrix_schema.json)")
    parser.add_argument("-o", "--output", help="Optional path to write the JSON lint report")
    parser.add_argument("--strict", action="store_true",
                        help="Also fail on paragraphs with factual cues but no Claim ID")
    parser.add_argument("--check-matrix", action="store_true",
                        help="Validate the matrix itself before linting")
    args = parser.parse_args()

    n_path, m_path = Path(args.input), Path(args.matrix)
    if not n_path.exists() or not m_path.exists():
        print("[ERROR] Narrative or matrix file not found.", file=sys.stderr)
        sys.exit(2)

    try:
        matrix = json.loads(m_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Matrix JSON invalid: {e}", file=sys.stderr)
        sys.exit(2)

    if args.check_matrix:
        issues = validate_matrix(matrix)
        if issues:
            print("[ERROR] Matrix validation failed:", file=sys.stderr)
            for it in issues:
                print(f"  - {it}", file=sys.stderr)
            sys.exit(1)

    narrative = n_path.read_text(encoding="utf-8", errors="replace")
    report = lint_narrative(narrative, matrix)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Lint report saved to: {out}")

    s = report["stats"]
    print("=" * 56)
    print(" ScholarFlow Claim Traceability Lint Report")
    print("=" * 56)
    print(f" Matrix claims               : {s['matrix_claim_count']}")
    print(f" Claim IDs cited in prose    : {s['referenced_count']}")
    print(f" Citation coverage           : {s['citation_coverage']:.1%}")
    print(f" UNRESOLVED refs (hard fail) : {s['unresolved_count']}")
    print(f" Uncited matrix claims       : {len(report['uncited_claims'])}")
    print(f" Flagged no-ID paragraphs    : {s['flagged_paragraph_count']}"
          + ("  [--strict: FAILED]" if args.strict and s["flagged_paragraph_count"] else ""))
    print("=" * 56)
    for r in report["unresolved_refs"]:
        print(f" [UNRESOLVED] {r}: cited in narrative but absent from matrix.")
    for cid in report["uncited_claims"]:
        print(f" [UNCITED]    {cid}: in matrix but never referenced.")
    for p in report["flagged_paragraphs"][:10]:
        print(f" [NO_CLAIM_ID] {p}...")

    sys.exit(1 if gate_failed(report, strict=args.strict) else 0)


if __name__ == "__main__":
    main()
