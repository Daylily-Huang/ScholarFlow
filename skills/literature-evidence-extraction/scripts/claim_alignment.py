#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_alignment.py
------------------
Universal Claim-Evidence Alignment Gate & Auditor for ScholarFlow.
Part of `literature-evidence-extraction` skill and cross-skill architecture.

Core Epistemic Principles:
- Mention != Relation
- Co-occurrence != Relation
- Contextual proximity != Relation
- Entity evidence != Claim evidence

Capabilities:
1. Dynamic semantic bifurcation: ATTRIBUTE vs CLAIM_RELATION vs MIXED.
2. 5 Alignment Gates:
   - Gate 1: Target Claim Identity
   - Gate 2: Evidence Context Match
   - Gate 3: Proposition / Relation Support Test
   - Gate 4: Source Role Classification
   - Gate 5: Inference Boundary & Predicate Insertion Check
3. 10-Status Relation Taxonomy:
   SUPPORTED, PARTIALLY_SUPPORTED, DERIVED, AMBIGUOUS, CONTRADICTORY,
   BACKGROUND_ONLY, CONTEXT_ONLY, OTHER_ENTITY_CONTEXT, REFERENCED_ONLY, NOT_REPORTED.
4. Confirmed Output Gatekeeper: Only SUPPORTED, PARTIALLY_SUPPORTED, and DERIVED
   belonging to current study (CURRENT_STUDY_RESULT) may enter confirmed outputs.
"""

import re
from typing import Dict, List, Any, Optional, Tuple, Set


class ExtractionSemantics:
    ATTRIBUTE = "ATTRIBUTE"
    CLAIM_RELATION = "CLAIM_RELATION"
    MIXED = "MIXED"


class RelationStatus:
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    DERIVED = "DERIVED"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTORY = "CONTRADICTORY"
    BACKGROUND_ONLY = "BACKGROUND_ONLY"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    OTHER_ENTITY_CONTEXT = "OTHER_ENTITY_CONTEXT"
    REFERENCED_ONLY = "REFERENCED_ONLY"
    NOT_REPORTED = "NOT_REPORTED"
    REJECTED = "REJECTED"


class SourceRole:
    CURRENT_STUDY_RESULT = "CURRENT_STUDY_RESULT"
    CURRENT_STUDY_METHOD = "CURRENT_STUDY_METHOD"
    BACKGROUND = "BACKGROUND"
    REFERENCED_WORK = "REFERENCED_WORK"
    DISCUSSION_INTERPRETATION = "DISCUSSION_INTERPRETATION"
    ENVIRONMENT_OR_CONTEXT = "ENVIRONMENT_OR_CONTEXT"
    OTHER_ENTITY_CONTEXT = "OTHER_ENTITY_CONTEXT"


# Eligible statuses for Confirmed Output
CONFIRMED_ELIGIBLE_STATUSES = {
    RelationStatus.SUPPORTED,
    RelationStatus.PARTIALLY_SUPPORTED,
    RelationStatus.DERIVED,
}

# Relation/claim intent markers across disciplines (used for semantic intent routing)
CLAIM_INTENT_PATTERNS = [
    r"(是否|怎样|如何)?(影响|导致|促成|抑制|降低|提高|增加|诱发|调控|优于|胜过|超越)",
    r"(相关|关联|相伴|协同|因果|机制|依赖|支持|反驳|证实|证伪|交互|作用于)",
    r"(affect|cause|reduce|increase|inhibit|promote|regulate|outperform|surpass)",
    r"(correlat|associat|depend|interact|mediat|support|refut|impact|superior)",
    r"(feed|prey|compet|symbio|normative|jurisprudence|holding)",
]

# Patterns that signal mere co-occurrence, co-measurement, or coexistence without relational predicate
CO_OCCURRENCE_ONLY_PATTERNS = [
    r"(were\s+both\s+(measured|evaluated|recorded|examined|expressed|observed|tested|analyzed))",
    r"(both\s+[a-zA-Z0-9_\-\s]+\s+and\s+[a-zA-Z0-9_\-\s]+\s+(were|are)\s+(measured|recorded|present|evaluated))",
    r"(simultaneously\s+(measured|recorded|surveyed|observed))",
    r"(both\s+showed\s+elevated\s+expression)",
    r"(survey\s+plots?\s+.*confirmed\s+the\s+presence\s+of\s+.*recorded\s+abundant)",
    r"(recording\s+both\s+.*and\s+.*)",
    r"(同时(测定|记录|观察|评估|调查|共存|出现))",
]

# Patterns that indicate cited previous literature rather than current study findings
REFERENCED_WORK_PATTERNS = [
    r"(\b(previous\s+(research|studies|work|findings|jurisprudence)|earlier\s+work)\b)",
    r"(\b(has\s+discussed|have\s+shown|cites?\s+principle|following\s+[A-Z][a-z]+)\b)",
    r"(\b(et\s+al\.\s*\(?\d{4}\)?|\(\s*[A-Z][a-z]+(?:\s+et\s+al\.)?,\s*\d{4}\s*\))\b)",
    r"(前人研究|以往研究|既有文献|文献报告|以往判例)",
]

# Patterns that signal discussion speculation or unverified hypotheses
DISCUSSION_SPECULATION_PATTERNS = [
    r"(\b(may\s+explain|might\s+suggest|could\s+indicate|hypothesized\s+that|we\s+speculate)\b)",
    r"(\b(is\s+plausible\s+that|potential\s+mechanism\s+remains\s+to\s+be)\b)",
    r"(可能解释|推测可能|提示潜在|或可归因于|尚待进一步证实)",
]


def detect_extraction_semantics(
    query: str = "",
    target_fields: Optional[List[str]] = None
) -> str:
    """Detect whether extraction task is ATTRIBUTE, CLAIM_RELATION, or MIXED."""
    text_to_check = (query or "") + " " + " ".join(target_fields or [])
    has_claim = False
    has_attribute = False

    for pat in CLAIM_INTENT_PATTERNS:
        if re.search(pat, text_to_check, re.IGNORECASE):
            has_claim = True
            break

    # Check for typical attribute indicators
    attr_patterns = [
        r"(样本量|温度|浓度|体积|周期|规模|坐标|时间|年份|参数|指标数值)",
        r"(sample\s*size|temperature|volume|concentration|duration|dataset\s*size|period|year|parameter|value)",
    ]
    for pat in attr_patterns:
        if re.search(pat, text_to_check, re.IGNORECASE):
            has_attribute = True
            break

    if has_claim and has_attribute:
        return ExtractionSemantics.MIXED
    elif has_claim:
        return ExtractionSemantics.CLAIM_RELATION
    return ExtractionSemantics.ATTRIBUTE


def verify_claim_alignment(
    target_claim: Dict[str, Any],
    evidence_text: str,
    evidence_context: Optional[Dict[str, Any]] = None,
    table_bundle: Optional[Dict[str, Any]] = None,
    is_cross_context: bool = False
) -> Dict[str, Any]:
    """Execute the 5 Claim-Evidence Alignment Gates on a target claim and its candidate evidence.

    Args:
        target_claim: Dict containing:
            - text: str (e.g. "Treatment A reduces Outcome B")
            - subject: Optional[str] (e.g. "Treatment A")
            - predicate: Optional[str] (e.g. "reduces")
            - object: Optional[str] (e.g. "Outcome B")
            - claim_type: str ("RELATION" | "PROPOSITION")
        evidence_text: Verbatim snippet or structured text.
        evidence_context: Dict containing:
            - context_id: str (e.g. "CTX01")
            - target_context_id: Optional[str]
            - source_role: str (SourceRole enum)
            - location: Optional[str] (Section/Page, e.g. "Discussion", "Results")
        table_bundle: Optional structured table bundle (TABLE_HEADER_ROW_BUNDLE).
        is_cross_context: True if evidence was assembled across mismatched contexts.

    Returns:
        Dict with status, is_confirmed_eligible, gate_results, violation_reasons, notes.
    """
    ctx = evidence_context or {}
    source_role = ctx.get("source_role", SourceRole.CURRENT_STUDY_RESULT)
    section = (ctx.get("location") or "").lower()
    claim_str = target_claim.get("text", "")
    predicate = target_claim.get("predicate", "").strip().lower()

    gate_results = {
        "gate1_identity": True,
        "gate2_context_match": True,
        "gate3_proposition_support": True,
        "gate4_source_role": True,
        "gate5_inference_boundary": True,
    }
    violations = []

    # ----------------------------------------------------
    # Gate 1: Target Claim Identity
    # ----------------------------------------------------
    if not claim_str.strip():
        gate_results["gate1_identity"] = False
        violations.append("Target claim string is empty.")

    # ----------------------------------------------------
    # Gate 2: Evidence Context Match
    # ----------------------------------------------------
    if is_cross_context:
        gate_results["gate2_context_match"] = False
        violations.append("Evidence assembled by cross-context concatenation across disjoint contexts.")
        return {
            "status": RelationStatus.REJECTED,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "REJECT",
            "notes": "Cross-context claim assembly violation."
        }

    ctx_id = ctx.get("context_id")
    target_ctx_id = ctx.get("target_context_id")
    if ctx_id and target_ctx_id and ctx_id != target_ctx_id:
        gate_results["gate2_context_match"] = False
        violations.append(f"Context mismatch: Evidence belongs to context {ctx_id}, but target claim requires {target_ctx_id}.")
        return {
            "status": RelationStatus.OTHER_ENTITY_CONTEXT,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "REJECT",
            "notes": "Evidence from other entity context / wrong cohort."
        }

    # ----------------------------------------------------
    # Gate 4: Source Role Classification
    # ----------------------------------------------------
    # Check if cited work
    if source_role == SourceRole.REFERENCED_WORK or any(re.search(p, evidence_text, re.IGNORECASE) for p in REFERENCED_WORK_PATTERNS):
        gate_results["gate4_source_role"] = False
        violations.append("Evidence is from cited/previous research, not current study empirical result.")
        return {
            "status": RelationStatus.REFERENCED_ONLY,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": SourceRole.REFERENCED_WORK,
            "audit_verdict": "DOWNGRADE_REFERENCED",
            "notes": "Referenced work only; cannot be promoted to current study confirmed output."
        }

    if source_role == SourceRole.BACKGROUND or "introduction" in section or "background" in section:
        # If it's pure background without empirical result
        if not table_bundle and not re.search(r"\b(we\s+found|our\s+results|we\s+demonstrate|here\s+we\s+show)\b", evidence_text, re.IGNORECASE):
            gate_results["gate4_source_role"] = False
            violations.append("Evidence is background introductory statement.")
            return {
                "status": RelationStatus.BACKGROUND_ONLY,
                "is_confirmed_eligible": False,
                "gate_results": gate_results,
                "violations": violations,
                "source_role": SourceRole.BACKGROUND,
                "audit_verdict": "DOWNGRADE_BACKGROUND",
                "notes": "Background description only."
            }

    if source_role == SourceRole.ENVIRONMENT_OR_CONTEXT:
        gate_results["gate4_source_role"] = False
        violations.append("Evidence is contextual or environmental co-occurrence.")
        return {
            "status": RelationStatus.CONTEXT_ONLY,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": SourceRole.ENVIRONMENT_OR_CONTEXT,
            "audit_verdict": "DOWNGRADE_CONTEXT",
            "notes": "Environmental or contextual observation only."
        }

    # Check discussion speculation
    if source_role == SourceRole.DISCUSSION_INTERPRETATION or "discussion" in section:
        for p in DISCUSSION_SPECULATION_PATTERNS:
            if re.search(p, evidence_text, re.IGNORECASE):
                gate_results["gate4_source_role"] = False
                violations.append("Discussion author speculation without empirical verification in Results.")
                return {
                    "status": RelationStatus.AMBIGUOUS,
                    "is_confirmed_eligible": False,
                    "gate_results": gate_results,
                    "violations": violations,
                    "source_role": SourceRole.DISCUSSION_INTERPRETATION,
                    "audit_verdict": "DOWNGRADE_SPECULATION",
                    "notes": "Discussion speculation; not an empirical result."
                }

    # ----------------------------------------------------
    # Gate 3: Proposition / Relation Support Test
    # ----------------------------------------------------
    # Structured table bundle support
    if table_bundle:
        bundle_type = table_bundle.get("type", "")
        if bundle_type == "TABLE_HEADER_ROW_BUNDLE":
            cell_vals = table_bundle.get("cell_values", {})
            target_val = float(cell_vals.get("target", 0))
            base_val = float(cell_vals.get("baseline", 0))
            metric = table_bundle.get("column_header", "")
            if target_val > base_val:
                return {
                    "status": RelationStatus.SUPPORTED,
                    "is_confirmed_eligible": True,
                    "gate_results": gate_results,
                    "violations": [],
                    "source_role": SourceRole.CURRENT_STUDY_RESULT,
                    "audit_verdict": "PASS",
                    "notes": f"Supported via structured table bundle ({metric}: {target_val} vs {base_val})."
                }

    # Check Co-occurrence Only pattern (Mention != Relation, Co-occurrence != Relation)
    is_co_occurrence_only = False
    for pat in CO_OCCURRENCE_ONLY_PATTERNS:
        if re.search(pat, evidence_text, re.IGNORECASE):
            is_co_occurrence_only = True
            break

    if is_co_occurrence_only:
        # Check whether text contains an explicit relational predicate linking them
        # If predicate is absent or only co-measurement words appear
        gate_results["gate3_proposition_support"] = False
        violations.append("Entities merely co-occur or were co-measured; no relation predicate supported.")
        return {
            "status": RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "REJECT_CO_OCCURRENCE",
            "notes": "Co-occurrence only != relation. Cannot confirm relation."
        }

    # ----------------------------------------------------
    # Gate 5: Inference Boundary & Predicate Insertion Check
    # ----------------------------------------------------
    # If the user targets a specific predicate (e.g. "reduces", "outperforms", "causes")
    # check if the text explicitly states the relation or direct effect
    direct_support_patterns = [
        r"\b(significantly\s+(reduced|increased|improved|decreased|outperformed)|demonstrated\s+a\s+significant)\b",
        r"\b(reduced|suppressed|inhibited|promoted|enhanced|caused|outperformed|surpassed)\b",
        r"(显著(降低|提高|减少|增加|促进|抑制|优于))",
        r"(直接(调控|导致|抑制|促进))",
    ]
    has_direct_support = any(re.search(p, evidence_text, re.IGNORECASE) for p in direct_support_patterns)

    if has_direct_support:
        return {
            "status": RelationStatus.SUPPORTED,
            "is_confirmed_eligible": True,
            "gate_results": gate_results,
            "violations": [],
            "source_role": SourceRole.CURRENT_STUDY_RESULT,
            "audit_verdict": "PASS",
            "notes": "Direct empirical claim support verified."
        }

    # If neither co-occurrence flagged nor direct support, check predicate presence
    if predicate and predicate not in evidence_text.lower():
        # Predicate insertion detected
        gate_results["gate5_inference_boundary"] = False
        violations.append(f"Unsupported predicate insertion: '{predicate}' does not appear in evidence text.")
        return {
            "status": RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "UNSUPPORTED_PREDICATE",
            "notes": f"Predicate '{predicate}' was inserted by model without text grounding."
        }

    # Fallback to AMBIGUOUS if claim cannot be verified as full SUPPORTED
    return {
        "status": RelationStatus.AMBIGUOUS,
        "is_confirmed_eligible": False,
        "gate_results": gate_results,
        "violations": ["Evidence context does not fully substantiate target relation."],
        "source_role": source_role,
        "audit_verdict": "AMBIGUOUS",
        "notes": "Ambiguous relation support."
    }


def calculate_alignment_metrics(evaluation_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate False Relation Rate and Unsupported Predicate Insertion Rate.

    Formulas:
    - False Relation Rate = (unsupported_relations_emitted / total_true_non_relations_tested)
    - Unsupported Predicate Insertion Rate = (unsupported_predicates_emitted / total_tested)
    Target for both: STRICTLY 0.0%.
    """
    total_non_relations = 0
    false_relations_emitted = 0
    total_predicate_tests = 0
    inserted_predicates = 0

    for rec in evaluation_records:
        is_true_non_relation = rec.get("is_true_non_relation", False)
        verdict = rec.get("verdict", {})
        is_emitted_confirmed = verdict.get("is_confirmed_eligible", False)

        if is_true_non_relation:
            total_non_relations += 1
            if is_emitted_confirmed:
                false_relations_emitted += 1

        if rec.get("tests_predicate_insertion", False):
            total_predicate_tests += 1
            if is_emitted_confirmed and not rec.get("predicate_grounded", False):
                inserted_predicates += 1

    false_relation_rate = (
        false_relations_emitted / max(1, total_non_relations)
        if total_non_relations > 0 else 0.0
    )
    predicate_insertion_rate = (
        inserted_predicates / max(1, total_predicate_tests)
        if total_predicate_tests > 0 else 0.0
    )

    return {
        "total_true_non_relations": total_non_relations,
        "false_relations_emitted": false_relations_emitted,
        "false_relation_rate": round(false_relation_rate, 4),
        "total_predicate_tests": total_predicate_tests,
        "inserted_predicates": inserted_predicates,
        "unsupported_predicate_insertion_rate": round(predicate_insertion_rate, 4),
        "meets_target": (false_relation_rate == 0.0 and predicate_insertion_rate == 0.0)
    }
