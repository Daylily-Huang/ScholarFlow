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

# H-37（2026-09-13 第二轮集群测试）：ATTRIBUTE 数值核验复用 quote_audit 的
# 完整数量解析（数值 + 符号 + 指数 + 量纲），杜绝"任意数字 + 任意 >2 字符
# 字段 token 即 ALIGNED"的通道。导入失败必须显式可见（与本文件 schema gate
# 的导入失败同策略），不得静默退回任意数字对齐。
try:
    from .quote_audit import (  # type: ignore
        extract_quantities as _extract_quantities,
        numeric_view as _numeric_view,
        _present_in as _quantity_present_in,
    )
except ImportError:  # pragma: no cover - stripped deployment fallback
    try:
        from quote_audit import (  # type: ignore
            extract_quantities as _extract_quantities,
            numeric_view as _numeric_view,
            _present_in as _quantity_present_in,
        )
    except ImportError:
        _extract_quantities = None  # type: ignore
        _numeric_view = None  # type: ignore
        _quantity_present_in = None  # type: ignore


CLAIM_TASK_TYPES = {
    TINTaskType.CLAIM,
    TINTaskType.RELATION,
    TINTaskType.COMPARISON,
    "CLAIM",
    "RELATION",
    "COMPARISON",
}


def _verify_attribute_value_anchoring(extracted_value: Any,
                                      context_text: str) -> Optional[Dict[str, Any]]:
    """H-37（2026-09-13 第二轮集群测试）：ATTRIBUTE 数值核验。

    旧实现里 ATTRIBUTE 对齐 = "上下文出现任意数字 + 字段 token" → 伪造
    `25 uL`（上下文唯一数字是 1985）照样升级 SUPPORTED/EXPLICIT。现在复用
    quote_audit 的完整数量解析（`extract_quantities`：数值+符号+指数+量纲）
    与量纲比较（`_present_in`），抽取值中的每个数量都必须锚定在扩展上下文中。

    返回：
      - None                    —— quote_audit 不可用（导入失败已在他处显式报告）
      - {"anchored": True, ...}  —— 无数量可解析（纯文本值，交 quote_audit 门禁）
                                    或全部数量锚定成功
      - {"anchored": False, "detail": ...} —— 存在未锚定数量，不得判 ALIGNED
    """
    if _extract_quantities is None or _numeric_view is None or _quantity_present_in is None:
        return None
    quantities = _extract_quantities(str(extracted_value if extracted_value is not None else ""),
                                     strict_units=True)
    if not quantities:
        return {"anchored": True,
                "detail": "no parsable quantity in extracted_value; numeric anchoring not applicable"}
    ctx_fold = _numeric_view(context_text or "", fold_case=False)
    unanchored = []
    for q in quantities:
        if q.get("sign_ambiguous"):
            unanchored.append(q["raw"] + " (ambiguous sign)")
            continue
        if not _quantity_present_in(q, ctx_fold, {}):
            unanchored.append(q["raw"])
    if unanchored:
        return {
            "anchored": False,
            "detail": ("ATTRIBUTE value not anchored in expanded context: quantity token(s) "
                       "%s parse cleanly but do not appear in the evidence context "
                       "(value + dimension compared via quote_audit.extract_quantities); "
                       "refusing SUPPORTED/EXPLICIT promotion." % (unanchored,)),
            "quantities": [{"value": str(q["value"]), "unit": q["unit"],
                            "dimension": q["dimension"]} for q in quantities],
        }
    return {"anchored": True,
            "detail": "all quantities anchored in expanded context",
            "quantities": [{"value": str(q["value"]), "unit": q["unit"],
                            "dimension": q["dimension"]} for q in quantities]}


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

    # 3b. H-37: ATTRIBUTE 数值核验（复用 quote_audit.extract_quantities）
    # 伪造值（上下文唯一数字是 1985 的 "25 uL"）不得升级 SUPPORTED/EXPLICIT。
    value_anchoring = None
    if task_type not in CLAIM_TASK_TYPES and extracted_value is not None:
        value_anchoring = _verify_attribute_value_anchoring(
            extracted_value, expanded_ctx.get("context_text", ""))
        if value_anchoring is not None and not value_anchoring.get("anchored", True):
            alignment = {
                "status": AlignmentStatus.NOT_ALIGNED,
                "rationale": value_anchoring.get("detail",
                                                 "ATTRIBUTE value not anchored in context"),
                "value_anchoring": value_anchoring,
            }

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
