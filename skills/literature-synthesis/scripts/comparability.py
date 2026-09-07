#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparability Matrix & Stratification (comparability.py)
---------------------------------------------------------
Part of the `literature-synthesis` skill (ScholarFlow v0.6.5, RFC-013).

Evaluates whether scientific claims are genuinely comparable across:
- Subject / entity / population
- Intervention / methodology
- Comparator / baseline
- Outcome metric & units
- Environment / setting / boundary conditions

Prevents false controversy / false consensus caused by pooling incommensurable
or differently conditioned studies. Conforms to schemas/comparison_record.schema.json.
"""

import re
import hashlib
from typing import Dict, List, Any, Optional, Tuple


class ComparabilityStatus:
    DIRECTLY_COMPARABLE = "DIRECTLY_COMPARABLE"
    COMPARABLE_AFTER_TRANSFORM = "COMPARABLE_AFTER_TRANSFORM"
    STRATIFY_REQUIRED = "STRATIFY_REQUIRED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN = "UNKNOWN"


class DimensionStatus:
    MATCH = "MATCH"
    COMPATIBLE = "COMPATIBLE"
    HIERARCHICAL_SUBSET = "HIERARCHICAL_SUBSET"
    CONVERTIBLE = "CONVERTIBLE"
    DIFFERENT_STRATUM = "DIFFERENT_STRATUM"
    DISCREPANT = "DISCREPANT"
    INCOMPATIBLE = "INCOMPATIBLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return str(val).strip().lower()
    return str(val).strip().lower()


def evaluate_dimension_subject(claim_a: Dict[str, Any], claim_b: Dict[str, Any]) -> str:
    """Evaluate whether subject/target entity between claim A and B are comparable."""
    sub_a = _clean_str(claim_a.get("subject") or claim_a.get("entity") or claim_a.get("topic"))
    sub_b = _clean_str(claim_b.get("subject") or claim_b.get("entity") or claim_b.get("topic"))

    if not sub_a or not sub_b:
        return DimensionStatus.UNKNOWN

    if sub_a == sub_b:
        return DimensionStatus.MATCH

    words_a = set(re.findall(r"\w+", sub_a))
    words_b = set(re.findall(r"\w+", sub_b))
    common = words_a & words_b

    # Filter out generic words
    stopwords = {"study", "effect", "analysis", "in", "of", "the", "and", "on", "a", "an", "research"}
    informative_common = common - stopwords

    if informative_common:
        if words_a.issubset(words_b) or words_b.issubset(words_a):
            return DimensionStatus.HIERARCHICAL_SUBSET
        return DimensionStatus.COMPATIBLE

    return DimensionStatus.DISCREPANT


def evaluate_dimension_method(claim_a: Dict[str, Any], claim_b: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Evaluate methodological compatibility and determine if stratification is needed."""
    m_a = _clean_str(claim_a.get("method"))
    m_b = _clean_str(claim_b.get("method"))

    if not m_a or not m_b or m_a == "unspecified method" or m_b == "unspecified method":
        return DimensionStatus.UNKNOWN, None

    if m_a == m_b:
        return DimensionStatus.MATCH, None

    # Known method incompatibility patterns requiring stratification (e.g. in vitro vs in vivo, survey vs capture-recapture)
    incompatible_pairs = [
        ({"in vitro", "cell line", "assay"}, {"in vivo", "clinical", "patient", "population", "field"}),
        ({"transect", "direct count", "line transect"}, {"secr", "spatial capture", "camera trap"}),
        ({"simulation", "modeled", "synthetic"}, {"empirical", "field survey", "observation"}),
    ]

    for set1, set2 in incompatible_pairs:
        a_in_1 = any(term in m_a for term in set1)
        b_in_2 = any(term in m_b for term in set2)
        a_in_2 = any(term in m_a for term in set2)
        b_in_1 = any(term in m_b for term in set1)
        if (a_in_1 and b_in_2) or (a_in_2 and b_in_1):
            return DimensionStatus.INCOMPATIBLE, f"method_paradigm:{m_a}_vs_{m_b}"

    # Default to compatible if no fundamental conflict detected
    return DimensionStatus.COMPATIBLE, None


def evaluate_dimension_metric(claim_a: Dict[str, Any], claim_b: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Evaluate whether outcome metric and measurement unit are directly comparable or convertible."""
    m_a = _clean_str(claim_a.get("metric") or claim_a.get("metric_name") or claim_a.get("outcome"))
    m_b = _clean_str(claim_b.get("metric") or claim_b.get("metric_name") or claim_b.get("outcome"))

    unit_a = _clean_str(claim_a.get("unit"))
    unit_b = _clean_str(claim_b.get("unit"))

    # If neither specifies unit/metric, check claim text for density / rate cues
    if not m_a and not m_b and not unit_a and not unit_b:
        return DimensionStatus.MATCH, None

    if unit_a and unit_b and unit_a != unit_b:
        # Detect standard convertible units
        if (unit_a in {"ind/km2", "individuals/km2"} and unit_b in {"ind/100km2", "individuals/100km2"}):
            return DimensionStatus.CONVERTIBLE, {"factor": 0.01, "from": unit_b, "to": unit_a}
        if (unit_b in {"ind/km2", "individuals/km2"} and unit_a in {"ind/100km2", "individuals/100km2"}):
            return DimensionStatus.CONVERTIBLE, {"factor": 100.0, "from": unit_a, "to": unit_b}
        if (unit_a in {"mg/l", "ppm"} and unit_b in {"ug/l", "ppb"}):
            return DimensionStatus.CONVERTIBLE, {"factor": 1000.0, "from": unit_a, "to": unit_b}
        return DimensionStatus.INCOMPATIBLE, None

    if m_a and m_b and m_a != m_b:
        return DimensionStatus.INCOMPATIBLE, None

    return DimensionStatus.MATCH, None


def evaluate_dimension_boundary(claim_a: Dict[str, Any], claim_b: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Evaluate boundary / environmental conditions for required stratification."""
    b_a = _clean_str(claim_a.get("boundary"))
    b_b = _clean_str(claim_b.get("boundary"))

    if not b_a or not b_b or b_a == "unspecified boundary" or b_b == "unspecified boundary":
        return DimensionStatus.MATCH, None

    if b_a == b_b:
        return DimensionStatus.MATCH, None

    # Opposing environmental / seasonal conditions requiring stratification
    stratify_pairs = [
        ({"winter", "snow", "cold"}, {"summer", "dry", "warm"}),
        ({"wild", "field", "natural"}, {"captive", "laboratory", "enclosure"}),
        ({"high dose", "high concentration"}, {"low dose", "low concentration"}),
        ({"sterile", "in vitro"}, {"non-sterile", "complex field"}),
    ]

    for set1, set2 in stratify_pairs:
        a_in_1 = any(term in b_a for term in set1)
        b_in_2 = any(term in b_b for term in set2)
        a_in_2 = any(term in b_a for term in set2)
        b_in_1 = any(term in b_b for term in set1)
        if (a_in_1 and b_in_2) or (a_in_2 and b_in_1):
            return DimensionStatus.DIFFERENT_STRATUM, f"boundary:{b_a}_vs_{b_b}"

    return DimensionStatus.MATCH, None


def evaluate_claim_comparability(
    claim_a: Dict[str, Any],
    claim_b: Dict[str, Any],
    target: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pairwise comparability evaluation conforming to schemas/comparison_record.schema.json.
    """
    id_a = str(claim_a.get("claim_id") or claim_a.get("id") or "CLM-A")
    id_b = str(claim_b.get("claim_id") or claim_b.get("id") or "CLM-B")

    # Order IDs stably
    if id_a > id_b:
        id_a, id_b = id_b, id_a
        claim_a, claim_b = claim_b, claim_a

    h = hashlib.sha256(f"{id_a}:{id_b}".encode("utf-8")).hexdigest()[:8]
    comp_id = f"CMP-{h}"

    subj_eval = evaluate_dimension_subject(claim_a, claim_b)
    meth_eval, meth_stratum = evaluate_dimension_method(claim_a, claim_b)
    metric_eval, transform_rule = evaluate_dimension_metric(claim_a, claim_b)
    bnd_eval, bnd_stratum = evaluate_dimension_boundary(claim_a, claim_b)

    dims = {
        "subject": subj_eval,
        "intervention_or_method": meth_eval,
        "comparator": DimensionStatus.MATCH,
        "outcome_metric": metric_eval,
        "time_scale": DimensionStatus.MATCH,
        "environment_or_setting": bnd_eval,
    }

    # Synthesize overall comparability status
    strat_key = bnd_stratum or meth_stratum
    if subj_eval == DimensionStatus.DISCREPANT or metric_eval == DimensionStatus.INCOMPATIBLE:
        status = ComparabilityStatus.NOT_COMPARABLE
        rationale = f"Claims evaluate fundamentally disparate entities or metrics ({subj_eval}, {metric_eval})."
    elif bnd_eval == DimensionStatus.DIFFERENT_STRATUM or meth_eval == DimensionStatus.INCOMPATIBLE:
        status = ComparabilityStatus.STRATIFY_REQUIRED
        rationale = f"Conditions or methodology require stratification ({strat_key}). Cannot pool directly."
    elif metric_eval == DimensionStatus.CONVERTIBLE:
        status = ComparabilityStatus.COMPARABLE_AFTER_TRANSFORM
        rationale = f"Metrics are convertible with transformation rule: {transform_rule}."
    elif subj_eval in (DimensionStatus.MATCH, DimensionStatus.HIERARCHICAL_SUBSET, DimensionStatus.COMPATIBLE) and \
         meth_eval in (DimensionStatus.MATCH, DimensionStatus.COMPATIBLE) and \
         metric_eval == DimensionStatus.MATCH:
        status = ComparabilityStatus.DIRECTLY_COMPARABLE
        rationale = "Subject, methodology, and outcome metrics are fully commensurable."
    else:
        status = ComparabilityStatus.UNKNOWN
        rationale = "Insufficient metadata to confirm comparability."

    target_id = target.get("target_id") if isinstance(target, dict) else None

    return {
        "schema_version": "1.0",
        "comparison_id": comp_id,
        "claim_id_a": id_a,
        "claim_id_b": id_b,
        "target_id": target_id,
        "status": status,
        "dimension_evaluations": dims,
        "stratification_key": strat_key,
        "transform_rule": transform_rule,
        "rationale": rationale,
        "evaluated_by": "RULE_BASED",
    }


def stratify_claims_by_comparability(
    claims: List[Dict[str, Any]],
    target: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Stratifies a collection of claims under a topic into commensurable clusters.
    
    Returns:
        {
            "strata": {
                "default": [claims...],
                "boundary:winter_vs_summer": [claims...]
            },
            "uncomparable_claims": [claims...],
            "pairwise_comparisons": [ComparisonRecord...]
        }
    """
    if not claims:
        return {
            "strata": {},
            "uncomparable_claims": [],
            "pairwise_comparisons": [],
        }

    if len(claims) == 1:
        return {
            "strata": {"default_stratum": claims},
            "uncomparable_claims": [],
            "pairwise_comparisons": [],
        }

    # Reference claim is the first claim or highest-strength claim
    ref_claim = claims[0]
    comparisons = []
    strata: Dict[str, List[Dict[str, Any]]] = {}
    uncomparable: List[Dict[str, Any]] = []

    # Assign reference claim to default
    default_key = "core_stratum"
    strata[default_key] = [ref_claim]

    for c in claims[1:]:
        comp = evaluate_claim_comparability(ref_claim, c, target=target)
        comparisons.append(comp)

        st = comp["status"]
        if st in (ComparabilityStatus.DIRECTLY_COMPARABLE, ComparabilityStatus.COMPARABLE_AFTER_TRANSFORM):
            strata[default_key].append(c)
        elif st == ComparabilityStatus.STRATIFY_REQUIRED:
            s_key = comp.get("stratification_key") or "stratified_subgroup"
            if s_key not in strata:
                strata[s_key] = []
            strata[s_key].append(c)
        elif st == ComparabilityStatus.NOT_COMPARABLE:
            uncomparable.append(c)
        else:
            # UNKNOWN: place in separate unverified stratum
            unk_key = "unverified_stratum"
            if unk_key not in strata:
                strata[unk_key] = []
            strata[unk_key].append(c)

    return {
        "strata": strata,
        "uncomparable_claims": uncomparable,
        "pairwise_comparisons": comparisons,
    }
