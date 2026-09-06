#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_alignment.py
------------------
Universal Claim-Evidence Alignment Gate & Deterministic Auditor for ScholarFlow.
Part of `literature-evidence-extraction` skill and cross-skill architecture.

Core Epistemic Principles:
- Mention != Relation
- Co-occurrence != Relation
- Contextual proximity != Relation
- Entity evidence != Claim evidence

Role Definition:
- AI/Agent Specialist: Evaluates semantic scientific relations and claims.
- claim_alignment.py: Deterministic Alignment Guard preventing cheating:
  1. Enforces strict entity binding (Subject + Object must be bound).
  2. Blocks cross-context and cohort-mismatched evidence assembly.
  3. Fails closed when source_role is UNKNOWN or unverified.
  4. Demotes cited previous literature (REFERENCED_WORK) and discussion speculations.
  5. Enforces directional table comparison (HIGHER_IS_BETTER vs LOWER_IS_BETTER).
  6. Rejects mere co-occurrence / co-measurement from being promoted to confirmed relations.
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
    UNKNOWN = "UNKNOWN"
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
    r"(是否|怎样|如何)?(影响|导致|促成|抑制|降低|提高|增加|诱发|调控|优于|胜过|超越|取食|捕食)",
    r"(相关|关联|相伴|协同|因果|机制|依赖|支持|反驳|证实|证伪|交互|作用于|控制)",
    r"(affect|cause|reduce|increase|inhibit|promote|regulate|outperform|surpass)",
    r"(correlat|associat|depend|interact|mediat|support|refut|impact|superior)",
    r"(feed|prey|compet|symbio|normative|jurisprudence|holding|reject)",
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


def _check_entity_presence(entity_str: str, text: str) -> bool:
    """Check if entity is present in text allowing minor case/spacing/punctuation variations."""
    if not entity_str:
        return True
    ent_lower = entity_str.strip().lower()
    text_lower = text.lower()
    if ent_lower in text_lower:
        return True
    # Normalize hyphens, underscores, and multiple spaces
    norm_ent = re.sub(r"[\s_\-]+", " ", ent_lower).strip()
    norm_text = re.sub(r"[\s_\-]+", " ", text_lower).strip()
    if norm_ent in norm_text:
        return True
    # Normalized punctuation check
    clean_ent = " ".join(re.sub(r"[^\w\s]", " ", ent_lower).split())
    clean_text = " ".join(re.sub(r"[^\w\s]", " ", text_lower).split())
    if clean_ent and clean_ent in clean_text:
        return True
    return False


def _check_predicate_grounding(predicate: str, text: str) -> bool:
    """Check if a relational predicate is grounded in evidence text across disciplines.
    
    Supports root matching for common relational terms without an exhaustive rigid enum.
    """
    if not predicate:
        return True
    pred_lower = predicate.strip().lower()
    text_lower = text.lower()

    if pred_lower in text_lower:
        return True

    # Root mapping for inflectional variations across disciplines
    # e.g., "feeds on" -> "feed", "regulates" -> "regulat", "reduced" -> "reduc"
    root_patterns = [
        (r"feed", r"\b(feeds?|feeding|fed)\b"),
        (r"regulat", r"\b(regulates?|regulating|regulated|regulation)\b"),
        (r"reduc", r"\b(reduces?|reducing|reduced|reduction)\b"),
        (r"increas", r"\b(increases?|increasing|increased)\b"),
        (r"outperform", r"\b(outperforms?|outperforming|outperformed)\b"),
        (r"surpass", r"\b(surpasses?|surpassing|surpassed)\b"),
        (r"caus", r"\b(causes?|causing|caused)\b"),
        (r"promot", r"\b(promotes?|promoting|promoted)\b"),
        (r"inhibit", r"\b(inhibits?|inhibiting|inhibited|inhibition)\b"),
        (r"suppress", r"\b(suppresses?|suppressing|suppressed)\b"),
        (r"associat", r"\b(associates?|associated|association)\b"),
        (r"correlat", r"\b(correlates?|correlated|correlation)\b"),
        (r"control", r"\b(controls?|controlling|controlled)\b"),
        (r"reject", r"\b(rejects?|rejecting|rejected|rejection)\b"),
        (r"support", r"\b(supports?|supporting|supported)\b"),
        (r"refut", r"\b(refutes?|refuting|refuted)\b"),
        (r"interact", r"\b(interacts?|interacting|interacted|interaction)\b"),
    ]

    for stem, pat in root_patterns:
        if stem in pred_lower:
            if re.search(pat, text_lower):
                return True

    # Check multi-word phrase components (e.g. "positively associated with")
    words = [w for w in re.split(r"\s+", pred_lower) if len(w) > 3 and w not in {"with", "that", "from"}]
    if words and all(w in text_lower for w in words):
        return True

    return False


def verify_claim_alignment(
    target_claim: Dict[str, Any],
    evidence_text: str,
    evidence_context: Optional[Dict[str, Any]] = None,
    table_bundle: Optional[Dict[str, Any]] = None,
    is_cross_context: bool = False
) -> Dict[str, Any]:
    """Execute the 5 Claim-Evidence Alignment Gates on a target claim and its candidate evidence.

    Deterministic Alignment Guard Principles:
    - Subject + Object must be bound to target entities.
    - source_role defaults to UNKNOWN and fails closed.
    - Directional table comparisons require explicit or inferable metric_direction.
    - Mere co-occurrence or co-measurement is prevented from entering confirmed output.
    """
    ctx = evidence_context or {}
    # P1: Fail-closed default on source_role
    source_role = ctx.get("source_role", SourceRole.UNKNOWN)
    section = (ctx.get("location") or "").lower()
    claim_str = target_claim.get("text", "")
    subject = target_claim.get("subject", "").strip()
    predicate = target_claim.get("predicate", "").strip()
    obj = target_claim.get("object", "").strip()
    semantic_verdict = target_claim.get("semantic_verdict")

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
    if not claim_str.strip() and not (subject and predicate and obj):
        gate_results["gate1_identity"] = False
        violations.append("Target claim string and components are empty.")
        return {
            "status": RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "REJECT_EMPTY_CLAIM",
            "notes": "Empty target claim."
        }

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
    # Gate 4: Source Role Classification (Fail-Closed)
    # ----------------------------------------------------
    # Fail-closed if source_role is UNKNOWN
    if source_role == SourceRole.UNKNOWN:
        gate_results["gate4_source_role"] = False
        violations.append("Source role is UNKNOWN; evidence cannot be confirmed without explicit origin attribution.")
        return {
            "status": RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": SourceRole.UNKNOWN,
            "audit_verdict": "FAIL_CLOSED_UNKNOWN_ROLE",
            "notes": "Fail-closed: unverified source role cannot enter confirmed output."
        }

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
    # Gate 1 & 3: Entity Binding Check (Subject + Object)
    # ----------------------------------------------------
    search_corpus = evidence_text
    if table_bundle:
        search_corpus += " " + str(table_bundle.get("table_title", "")) + " " + str(table_bundle.get("column_header", "")) + " " + str(table_bundle.get("row_identifier", "")) + " " + str(table_bundle.get("baseline_row_identifier", ""))

    if table_bundle and table_bundle.get("type") == "TABLE_HEADER_ROW_BUNDLE":
        cell_vals = table_bundle.get("cell_values", {})
        row_id = table_bundle.get("row_identifier")
        if row_id:
            subject_bound = _check_entity_presence(subject, row_id) or _check_entity_presence(subject, search_corpus)
        else:
            subject_bound = ("target" in cell_vals) or _check_entity_presence(subject, search_corpus)

        base_row_id = table_bundle.get("baseline_row_identifier")
        if base_row_id:
            object_bound = _check_entity_presence(obj, base_row_id) or _check_entity_presence(obj, search_corpus)
        else:
            object_bound = ("baseline" in cell_vals) or _check_entity_presence(obj, search_corpus)
    else:
        subject_bound = _check_entity_presence(subject, search_corpus)
        object_bound = _check_entity_presence(obj, search_corpus)

    if not subject_bound or not object_bound:
        gate_results["gate1_identity"] = False
        violations.append(
            f"Entity binding failed for target claim: subject '{subject}' bound={subject_bound}, object '{obj}' bound={object_bound}."
        )
        return {
            "status": RelationStatus.OTHER_ENTITY_CONTEXT if (not subject_bound and subject) else RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "UNBOUND_ENTITIES",
            "notes": "Target claim subject or object not bound in evidence."
        }

    # ----------------------------------------------------
    # Gate 3: Proposition / Relation Support Test
    # ----------------------------------------------------
    # Structured table bundle support (with metric_direction support)
    if table_bundle:
        bundle_type = table_bundle.get("type", "")
        if bundle_type == "TABLE_HEADER_ROW_BUNDLE":
            cell_vals = table_bundle.get("cell_values", {})
            target_val = float(cell_vals.get("target", 0))
            base_val = float(cell_vals.get("baseline", 0))
            metric = table_bundle.get("column_header", "")

            # Direction of comparison: HIGHER_IS_BETTER vs LOWER_IS_BETTER vs UNKNOWN
            metric_direction = table_bundle.get("metric_direction")
            if not metric_direction:
                m_lower = metric.lower()
                if any(k in m_lower for k in ["accuracy", "f1", "precision", "recall", "bleu", "rouge", "auc", "yield", "survival", "score", "rate"]):
                    if not any(k in m_lower for k in ["error", "loss", "mortality", "failure"]):
                        metric_direction = "HIGHER_IS_BETTER"
                if not metric_direction and any(k in m_lower for k in ["loss", "error", "rmse", "mae", "mortality", "toxicity", "latency", "delay", "cost"]):
                    metric_direction = "LOWER_IS_BETTER"

            if metric_direction == "HIGHER_IS_BETTER":
                outperforms = (target_val > base_val)
            elif metric_direction == "LOWER_IS_BETTER":
                outperforms = (target_val < base_val)
            else:
                gate_results["gate5_inference_boundary"] = False
                violations.append(f"Metric direction for '{metric}' is UNKNOWN; cannot infer outperformance.")
                return {
                    "status": RelationStatus.AMBIGUOUS,
                    "is_confirmed_eligible": False,
                    "gate_results": gate_results,
                    "violations": violations,
                    "source_role": source_role,
                    "audit_verdict": "UNKNOWN_METRIC_DIRECTION",
                    "notes": "Table comparison has unknown metric optimization direction."
                }

            if outperforms:
                return {
                    "status": RelationStatus.SUPPORTED,
                    "is_confirmed_eligible": True,
                    "gate_results": gate_results,
                    "violations": [],
                    "source_role": source_role,
                    "audit_verdict": "PASS",
                    "notes": f"Supported via structured table bundle ({metric}: {target_val} vs {base_val}, direction={metric_direction})."
                }
            else:
                return {
                    "status": RelationStatus.CONTRADICTORY,
                    "is_confirmed_eligible": False,
                    "gate_results": gate_results,
                    "violations": [f"Target value ({target_val}) did not outperform baseline ({base_val}) for metric {metric} ({metric_direction})."],
                    "source_role": source_role,
                    "audit_verdict": "REJECT_CONTRADICTORY",
                    "notes": "Baseline achieved superior or equal metric value."
                }

    # Check Co-occurrence Only pattern (Mention != Relation, Co-occurrence != Relation)
    is_co_occurrence_only = False
    for pat in CO_OCCURRENCE_ONLY_PATTERNS:
        if re.search(pat, evidence_text, re.IGNORECASE):
            is_co_occurrence_only = True
            break

    predicate_grounded = _check_predicate_grounding(predicate, evidence_text)

    # If evidence is a pure co-occurrence statement without explicit relational predicate
    if is_co_occurrence_only and not predicate_grounded:
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
    # If upstream model/agent provided semantic confirmation
    if semantic_verdict == "SUPPORTED" and predicate_grounded:
        return {
            "status": RelationStatus.SUPPORTED,
            "is_confirmed_eligible": True,
            "gate_results": gate_results,
            "violations": [],
            "source_role": source_role,
            "audit_verdict": "PASS",
            "notes": "Target claim confirmed by semantic evaluation with entity and context alignment."
        }

    # If predicate is grounded in evidence text with bound entities and current study result
    if predicate_grounded and source_role == SourceRole.CURRENT_STUDY_RESULT:
        # Check that it's not co-occurrence
        if not is_co_occurrence_only:
            return {
                "status": RelationStatus.SUPPORTED,
                "is_confirmed_eligible": True,
                "gate_results": gate_results,
                "violations": [],
                "source_role": source_role,
                "audit_verdict": "PASS",
                "notes": f"Claim relation grounded in empirical evidence text (predicate '{predicate}' bound)."
            }

    # If predicate is completely absent from text and not semantic confirmed -> Predicate Insertion
    if predicate and not predicate_grounded:
        gate_results["gate5_inference_boundary"] = False
        violations.append(f"Unsupported predicate insertion: predicate '{predicate}' not grounded in evidence.")
        return {
            "status": RelationStatus.AMBIGUOUS,
            "is_confirmed_eligible": False,
            "gate_results": gate_results,
            "violations": violations,
            "source_role": source_role,
            "audit_verdict": "UNSUPPORTED_PREDICATE",
            "notes": f"Predicate '{predicate}' was not grounded in source text."
        }

    # Fallback to AMBIGUOUS
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
