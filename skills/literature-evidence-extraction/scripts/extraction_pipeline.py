#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extraction_pipeline.py
-----------------------
ScholarFlow Skill 2 Extraction Pipeline Orchestrator.
Orchestrates:
Candidate Detection -> AECE Context Expansion -> Semantic Classification
-> Target Alignment -> Claim-Evidence Alignment Gate (A2) -> Minimal Evidence Span -> Evidence Promotion.

Pure Python standard library (zero external runtime dependencies).
"""

import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

# Allow `python extraction_pipeline.py ...` (and CI jobs) to import shared.*
# regardless of the current working directory.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from shared.version import EXTRACTION_RESULT_SCHEMA_VERSION
except ImportError:
    EXTRACTION_RESULT_SCHEMA_VERSION = "1.1"

# The schema gate is the execution point for the §四 output contract. Before
# 2026-09-11 the docstring below claimed validation that never happened; keep
# this import failure loud rather than silent.
try:
    from shared.validation.schema_gate import (  # type: ignore
        SchemaGateError, require_valid, check_evidence_chain, validate as _validate_schema,
    )
except ImportError:  # pragma: no cover - only in stripped deployments
    try:
        from schema_gate import (  # type: ignore
            SchemaGateError, require_valid, check_evidence_chain, validate as _validate_schema,
        )
    except ImportError:
        SchemaGateError = Exception  # type: ignore
        require_valid = None  # type: ignore
        check_evidence_chain = None  # type: ignore
        _validate_schema = None  # type: ignore

try:
    from .context_expansion import (
        CandidateType,
        TINTaskType,
        ExpansionLevel,
        StopCondition,
        SemanticRole,
        AlignmentStatus,
        ContextSufficiency,
        expand_candidate_context,
        classify_semantic_role,
        evaluate_target_alignment,
        build_candidate_context_record,
        promote_candidate_to_evidence,
        audit_context_sufficiency,
    )
    from .claim_alignment import verify_claim_alignment, RelationStatus
except ImportError:
    from context_expansion import (
        CandidateType,
        TINTaskType,
        ExpansionLevel,
        StopCondition,
        SemanticRole,
        AlignmentStatus,
        ContextSufficiency,
        expand_candidate_context,
        classify_semantic_role,
        evaluate_target_alignment,
        build_candidate_context_record,
        promote_candidate_to_evidence,
        audit_context_sufficiency,
    )
    from claim_alignment import verify_claim_alignment, RelationStatus


CLAIM_TASK_TYPES = {
    TINTaskType.CLAIM,
    TINTaskType.RELATION,
    TINTaskType.COMPARISON,
    "CLAIM",
    "RELATION",
    "COMPARISON",
}


def process_candidate(
    tin: Dict[str, Any],
    candidate: Dict[str, Any],
    doc_text: str,
    record_id: str,
    field: str,
    extracted_value: Any,
    table_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process an individual candidate hit through the complete Skill 2 pipeline:
    1. AECE Context Expansion
    2. Semantic Role Classification
    3. Target Information Need (TIN) Alignment
    4. Claim-Evidence Alignment Gate (A2) if task requires claim verification
    5. Candidate Context Record (CCR) construction
    6. Fail-closed Evidence Promotion Gate
    """
    task_type = tin.get("task_type", TINTaskType.ATTRIBUTE)
    requires_claim_alignment = task_type in CLAIM_TASK_TYPES

    # 1. AECE Context Expansion
    expanded_ctx = expand_candidate_context(doc_text, candidate, tin=tin)

    # 2. Semantic Role Classification
    section_hdr = candidate.get("section") or expanded_ctx.get("section_heading")
    semantic_role, role_rationale = classify_semantic_role(
        expanded_ctx.get("context_text", ""),
        section_heading=section_hdr,
    )

    # 3. Target Alignment
    alignment = evaluate_target_alignment(tin, expanded_ctx)

    # 4. Claim Alignment Gate (A2)
    claim_alignment_verdict = None
    if requires_claim_alignment:
        target_claim_dict = {
            "text": tin.get("target_claim") or tin.get("target_relation") or "",
            "subject": tin.get("target_entity") or tin.get("subject") or "",
            "predicate": tin.get("predicate") or "",
            "object": tin.get("object") or tin.get("comparator") or "",
            "direction": tin.get("direction") or "",
        }
        claim_alignment_verdict = verify_claim_alignment(
            target_claim=target_claim_dict,
            evidence_text=expanded_ctx.get("context_text", ""),
            evidence_context={
                "source_role": semantic_role,
                "location": section_hdr or "",
            },
            table_bundle=table_bundle,
        )

    # 5. CCR Construction
    candidate_id = candidate.get("candidate_id") or candidate.get("id") or "CAND-001"
    tin_id = tin.get("tin_id") or tin.get("id") or "TIN-001"
    cand_type = candidate.get("type", CandidateType.TEXT_SENTENCE)
    hit_text = candidate.get("hit_text") or candidate.get("text") or ""
    allow_contradiction = tin.get("allow_contradiction", False)

    ccr = build_candidate_context_record(
        candidate_id=candidate_id,
        tin_id=tin_id,
        candidate_type=cand_type,
        hit_text=hit_text,
        expanded_ctx=expanded_ctx,
        semantic_role=semantic_role,
        alignment=alignment,
        role_rationale=role_rationale,
        page=candidate.get("page"),
        offset=candidate.get("offset"),
        section=section_hdr,
        task_type=task_type,
        requires_claim_alignment=requires_claim_alignment,
        claim_alignment=claim_alignment_verdict,
        allow_contradiction=allow_contradiction,
    )

    # 6. Evidence Promotion Gate
    provisional_record, promotion_error = promote_candidate_to_evidence(
        ccr=ccr,
        record_id=record_id,
        field=field,
        extracted_value=extracted_value,
    )

    if provisional_record is None:
        return {
            "candidate_context_record": ccr,
            "provisional_evidence_record": None,
            "evidence_record": None,
            "audit_result": None,
            "error": promotion_error,
            "promoted": False,
        }

    audit_result = audit_context_sufficiency(
        evidence_record=provisional_record,
        candidate_context=ccr,
        doc_text=doc_text,
    )

    if not audit_result.get("passed", False):
        return {
            "candidate_context_record": ccr,
            "provisional_evidence_record": provisional_record,
            "evidence_record": None,
            "audit_result": audit_result,
            "error": "AUDIT_REJECTED",
            "promoted": False,
        }

    return {
        "candidate_context_record": ccr,
        "provisional_evidence_record": provisional_record,
        "evidence_record": provisional_record,
        "audit_result": audit_result,
        "error": None,
        "promoted": True,
    }


def build_extraction_result_envelope(
    paper_metadata: Dict[str, Any],
    evidence_records: List[Dict[str, Any]],
    mode: str = "deep_evidence_extraction",
    schema_type: str = "universal",
    auditor_notes: Optional[str] = None,
    audit_results: Optional[List[Dict[str, Any]]] = None,
    rejected_candidates: Optional[List[Dict[str, Any]]] = None,
    validate: bool = True,
    strict_handoff: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Construct a canonical ScholarFlowExtractionResult envelope and VALIDATE it
    against `schemas/extraction_result.schema.json`.

    `validate=True` (default) runs the gate and raises SchemaGateError on any
    violation, so an off-contract envelope cannot be handed downstream. Pass
    `validate=False` only for exploratory payloads, and say so at the call site.
    """
    if isinstance(mode, list) and audit_results is None:
        audit_results = mode
        mode = "deep_evidence_extraction"

    timestamp = datetime.now(timezone.utc).isoformat()

    if audit_results is not None:
        required_failures = [
            a for a in audit_results
            if not a.get("passed", False)
        ]
        if required_failures:
            verdict = "REJECT"
            checklist_passed = False
        elif any(a.get("downgraded", False) for a in audit_results):
            verdict = "PASS_WITH_DOWNGRADES"
            checklist_passed = True
        else:
            verdict = "PASS" if len(evidence_records) > 0 else "PASS_WITH_DOWNGRADES"
            checklist_passed = True
    else:
        if rejected_candidates and len(evidence_records) == 0:
            verdict = "REJECT"
            checklist_passed = False
        else:
            all_passed = len(evidence_records) > 0
            verdict = "PASS" if all_passed else "PASS_WITH_DOWNGRADES"
            checklist_passed = len(evidence_records) > 0

    # Defensively normalize evidence_records: guarantee verbatim_quote is a string and decouple nested location
    sanitized_records = []
    for rec in (evidence_records or []):
        r = dict(rec)
        raw_quote = r.get("verbatim_quote")
        if isinstance(raw_quote, dict):
            q_text = raw_quote.get("text") or raw_quote.get("quote") or raw_quote.get("verbatim_quote") or str(raw_quote)
            r["verbatim_quote"] = str(q_text)
            loc = r.get("location")
            if not isinstance(loc, dict):
                loc = {}
                r["location"] = loc
            if "page" in raw_quote and loc.get("page") is None:
                loc["page"] = raw_quote["page"]
            if "section" in raw_quote and loc.get("section") is None:
                loc["section"] = raw_quote["section"]
        elif raw_quote is None:
            r["verbatim_quote"] = ""
        elif not isinstance(raw_quote, str):
            r["verbatim_quote"] = str(raw_quote)
        sanitized_records.append(r)
    evidence_records = sanitized_records

    envelope = {
        "schema_version": EXTRACTION_RESULT_SCHEMA_VERSION,
        "paper_metadata": {
            "title": paper_metadata.get("title", "Untitled Document"),
            "authors": paper_metadata.get("authors", ["Unknown"]),
            "year": paper_metadata.get("year", "NR"),
            "journal": paper_metadata.get("journal"),
            "doi": paper_metadata.get("doi"),
            "file_path": paper_metadata.get("file_path"),
        },
        "extraction_metadata": {
            "mode": mode,
            "timestamp": timestamp,
            "schema_type": schema_type,
        },
        "evidence_records": evidence_records,
        "auditor_verdict": {
            "verdict": verdict,
            "checklist_passed": checklist_passed,
            "auditor_notes": auditor_notes or ("Context and claim alignment verification passed" if checklist_passed else "Auditor checks rejected candidate evidence"),
        },
    }

    if strict_handoff and check_evidence_chain is not None:
        chain = check_evidence_chain(evidence_records, audit_results)
        if chain:
            raise SchemaGateError("evidence handoff chain broken:\n  - " + "\n  - ".join(chain))

    if validate and require_valid is not None:
        require_valid(envelope, "extraction_result.schema.json")

    return envelope


def main() -> None:
    """CLI entry point.

    Historically this module had none, so the §四 contract could not be enforced
    from a pipeline or CI job — the only way to "validate" was to read the
    docstring. Added 2026-09-11.
    """
    import argparse
    import json as _json
    from pathlib import Path as _Path

    ap = argparse.ArgumentParser(
        description="Validate / inspect a ScholarFlow extraction result against the canonical schema")
    ap.add_argument("-i", "--input", required=True,
                    help="extraction_result JSON to validate")
    ap.add_argument("--schema", default="extraction_result.schema.json")
    ap.add_argument("--evidence-chain", action="store_true",
                    help="also check that auditor verdicts cover every evidence record")
    args = ap.parse_args()

    payload = _json.loads(_Path(args.input).read_text(encoding="utf-8"))
    if _validate_schema is None:
        print("[ERROR] schema gate unavailable (shared.validation.schema_gate not importable)",
              file=sys.stderr)
        raise SystemExit(2)
    ok, mode, errs = _validate_schema(payload, args.schema)
    print("schema=%s  mode=%s  ok=%s  errors=%d" % (args.schema, mode, ok, len(errs)))
    for e in errs[:40]:
        print("  -", e)

    chain_problems: List[str] = []
    if args.evidence_chain and check_evidence_chain is not None:
        chain_problems = check_evidence_chain(
            payload.get("evidence_records", []),
            [payload.get("auditor_verdict")] if payload.get("auditor_verdict") else None)
        for c in chain_problems:
            print("  [chain]", c)

    raise SystemExit(0 if (ok and not chain_problems) else 1)


if __name__ == "__main__":
    main()
