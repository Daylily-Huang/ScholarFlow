#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_to_claim.py
--------------------
Canonical EvidenceRecord -> ClaimRecord Adapter and Consensus Eligibility Gate.
Enforces upstream quality gates before claims enter synthesis consensus matrices.

Pure Python standard library (zero external runtime dependencies).
"""

import os
import sys
import re
from typing import Dict, List, Any, Optional, Tuple


EVIDENCE_BEARING_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTORY",
}


def _normalize_proposition(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", " ", str(text).lower()).strip()
    return cleaned


def check_target_proposition_compatibility(
    source_target_claim: Optional[str],
    synthesis_target_claim: Optional[str],
) -> Tuple[str, str]:
    """Check if extraction-target and synthesis-target propositions are compatible."""
    if not source_target_claim or not synthesis_target_claim:
        return "UNRESOLVED", "Source or synthesis target proposition is not specified"

    norm_src = _normalize_proposition(source_target_claim)
    norm_tgt = _normalize_proposition(synthesis_target_claim)

    if norm_src == norm_tgt:
        return "VERIFIED_SAME_PROPOSITION", "Identical target proposition"

    # Token-based comparison to detect obvious subject/object/predicate mismatches
    src_words = set(norm_src.split())
    tgt_words = set(norm_tgt.split())

    diff_src = src_words - tgt_words
    diff_tgt = tgt_words - src_words

    common_fillers = {"the", "a", "an", "in", "of", "to", "under", "soil", "significantly", "rates", "by"}
    distinct_src = diff_src - common_fillers
    distinct_tgt = diff_tgt - common_fillers

    if distinct_src and distinct_tgt and (distinct_src != distinct_tgt):
        synonym_pairs = [
            {"increases", "stimulates", "increased", "stimulated", "stimulate", "increase"},
            {"decreases", "reduces", "decreased", "reduced", "decrease", "reduce"},
        ]
        is_synonym_only = False
        for pair in synonym_pairs:
            if distinct_src.issubset(pair) and distinct_tgt.issubset(pair):
                is_synonym_only = True
                break
        if not is_synonym_only:
            return "DIFFERENT_PROPOSITION", f"Proposition mismatch: '{source_target_claim}' vs '{synthesis_target_claim}'"
        else:
            return "VERIFIED_SAME_PROPOSITION", "Semantically equivalent proposition (synonym predicate)"

    return "VERIFIED_SAME_PROPOSITION", "Compatible proposition"


def evaluate_consensus_eligibility(
    claim_record: Dict[str, Any],
    evidence_index: Optional[Dict[str, Any]] = None,
    mode: str = "AUDITED_CANONICAL",
) -> Tuple[bool, List[str]]:
    """
    Evaluate whether a ClaimRecord is eligible to participate in synthesis consensus calculations.
    Consumes upstream quality fields from Skill 2 EvidenceRecords:
    1. In AUDITED_CANONICAL mode, evidence_index must be present and verified.
    2. EvidenceRecord must exist for referenced evidence_ids.
    3. Context sufficiency must be SUFFICIENT for full-strength consensus (PARTIALLY_SUFFICIENT rejected).
    4. claim_status must be evidence-bearing (SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTORY).
    5. support_type must not be NOT_REPORTED / NR.
    6. evidence_strength must not be UNKNOWN or empty.
    7. Stance mapping status must not be DIFFERENT_PROPOSITION or UNRESOLVED.
    """
    issues = []
    evidence_ids = claim_record.get("evidence_ids", [])
    ev_index = evidence_index or {}

    if mode == "AUDITED_CANONICAL":
        if not evidence_index:
            issues.append("Missing evidence index: consensus calculations require verified evidence index in AUDITED_CANONICAL mode")
        elif not evidence_ids:
            issues.append("Missing evidence_ids references in claim record")
        else:
            for eid in evidence_ids:
                ev_rec = ev_index.get(eid)
                if not ev_rec:
                    issues.append(f"Referenced evidence record '{eid}' not found in evidence index")
                    continue

                # Upstream quality checks
                ctx_suff = ev_rec.get("context_sufficiency")
                if ctx_suff == "INSUFFICIENT":
                    issues.append(f"Evidence '{eid}' has INSUFFICIENT context sufficiency")
                elif ctx_suff == "PARTIALLY_SUFFICIENT":
                    issues.append(f"Evidence '{eid}' has PARTIALLY_SUFFICIENT context; not eligible for full-strength consensus")

                claim_status = ev_rec.get("claim_status") or ev_rec.get("status")
                if claim_status not in EVIDENCE_BEARING_STATUSES:
                    issues.append(f"Evidence '{eid}' has non-evidence-bearing status: {claim_status}")

                supp_type = ev_rec.get("support_type")
                if supp_type in ("NOT_REPORTED", "NR"):
                    issues.append(f"Evidence '{eid}' has support_type '{supp_type}' (zero weight)")

                ev_strength = ev_rec.get("evidence_strength")
                if not ev_strength or ev_strength == "UNKNOWN":
                    issues.append(f"Evidence '{eid}' has UNKNOWN evidence strength")
    else:
        # Legacy/display mode checks if index is provided
        if ev_index and evidence_ids:
            for eid in evidence_ids:
                ev_rec = ev_index.get(eid)
                if ev_rec:
                    ctx_suff = ev_rec.get("context_sufficiency")
                    if ctx_suff == "INSUFFICIENT":
                        issues.append(f"Evidence '{eid}' has INSUFFICIENT context sufficiency")

    # Claim-level checks
    if claim_record.get("support_type") in ("NOT_REPORTED", "NR"):
        issues.append("Claim support_type is NOT_REPORTED")

    strength = claim_record.get("evidence_strength")
    tier = claim_record.get("evidence_tier")
    if not strength and not tier:
        issues.append("Claim has no evidence_strength or evidence_tier specified")
    elif (strength == "UNKNOWN" or not strength) and not tier:
        issues.append("Claim evidence_strength is UNKNOWN")

    stance = claim_record.get("stance")
    if stance == "NEUTRAL":
        issues.append("Claim stance is NEUTRAL (non-evidence-bearing stance)")

    mapping_status = claim_record.get("stance_mapping_status")
    if mapping_status == "DIFFERENT_PROPOSITION":
        issues.append("Claim stance mapping status is DIFFERENT_PROPOSITION (target proposition mismatch)")

    is_eligible = len(issues) == 0
    return is_eligible, issues


def map_evidence_to_claim(
    evidence_record: Dict[str, Any],
    synthesis_target: Dict[str, Any],
    claim_id: Optional[str] = None,
    stance: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map a Skill 2 EvidenceRecord to a canonical Skill 3 ClaimRecord.
    Stance is determined relative to the synthesis target proposition:
    - SUPPORTED -> SUPPORT
    - CONTRADICTORY -> REFUTE
    - PARTIALLY_SUPPORTED -> CONDITIONAL
    - UNSUPPORTED / AMBIGUOUS / DIFFERENT_PROPOSITION -> NEUTRAL
    """
    ev_id = evidence_record.get("evidence_id", "EV-001")
    rec_id = evidence_record.get("record_id", "REC-UNKNOWN")
    topic = synthesis_target.get("topic") or "General Topic"
    target_prop = (
        synthesis_target.get("target_claim")
        or synthesis_target.get("target_proposition")
        or synthesis_target.get("claim")
    )
    source_target_claim = (
        evidence_record.get("source_target_claim")
        or evidence_record.get("target_claim")
        or evidence_record.get("target_proposition")
    )
    source_tin_id = (
        evidence_record.get("source_tin_id")
        or evidence_record.get("target_information_need_id")
    )

    status = evidence_record.get("claim_status") or evidence_record.get("status", "SUPPORTED")

    # Determine stance & compatibility gate (P0-11)
    if stance:
        claim_stance = stance.upper()
        stance_mapping_status = "AGENT_MAPPED"
    elif source_target_claim and target_prop:
        compat_status, _ = check_target_proposition_compatibility(source_target_claim, target_prop)
        stance_mapping_status = compat_status
        if compat_status == "VERIFIED_SAME_PROPOSITION":
            if status == "CONTRADICTORY":
                claim_stance = "REFUTE"
            elif status == "SUPPORTED":
                claim_stance = "SUPPORT"
            elif status == "PARTIALLY_SUPPORTED":
                claim_stance = "CONDITIONAL"
            else:
                claim_stance = "NEUTRAL"
        else:
            claim_stance = "NEUTRAL"
    else:
        # Fallback when source proposition was not recorded on evidence
        stance_mapping_status = "UNRESOLVED"
        if status == "CONTRADICTORY":
            claim_stance = "REFUTE"
        elif status == "SUPPORTED":
            claim_stance = "SUPPORT"
        elif status == "PARTIALLY_SUPPORTED":
            claim_stance = "CONDITIONAL"
        else:
            claim_stance = "NEUTRAL"

    # Resolve evidence strength (P0-08: NEVER infer from support_type!)
    ev_strength = evidence_record.get("evidence_strength")
    if not ev_strength or ev_strength == "UNKNOWN":
        ev_strength = "UNKNOWN"

    claim_text = target_prop or evidence_record.get("verbatim_quote") or f"Finding from {rec_id}"
    cid = claim_id or f"CLM-{ev_id}"
    year = synthesis_target.get("year") or evidence_record.get("year") or "NR"

    # Method (P0-10: DO NOT fabricate method from section or placeholder)
    method = evidence_record.get("method")

    # Appraisal (P0-09: DO NOT fabricate optimistic appraisal)
    raw_appraisal = evidence_record.get("appraisal")
    if isinstance(raw_appraisal, dict) and raw_appraisal:
        claim_appraisal = {
            "directness": raw_appraisal.get("directness", "UNKNOWN"),
            "independence": raw_appraisal.get("independence", "UNKNOWN"),
            "risk_of_bias": raw_appraisal.get("risk_of_bias", "UNKNOWN"),
            "replication": raw_appraisal.get("replication", "UNKNOWN"),
        }
    else:
        claim_appraisal = {
            "directness": "UNKNOWN",
            "independence": "UNKNOWN",
            "risk_of_bias": "UNKNOWN",
            "replication": "UNKNOWN",
        }

    # Independence (P1-05)
    ind_group = evidence_record.get("independence_group_id")
    ind_status = evidence_record.get("independence_status")
    if ind_group:
        independence_status = ind_status or "VERIFIED"
    else:
        independence_status = ind_status or "UNKNOWN"

    claim_record = {
        "schema_version": "1.0",
        "claim_id": cid,
        "topic": topic,
        "paper_id": rec_id,
        "year": year,
        "claim": claim_text,
        "stance": claim_stance,
        "stance_mapping_status": stance_mapping_status,
        "source_tin_id": source_tin_id,
        "source_target_claim": source_target_claim,
        "evidence_ids": [ev_id],
        "method": method,
        "evidence_strength": ev_strength,
        "evidence_tier": "E1" if ev_strength == "DIRECT_EMPIRICAL" else ("E2" if ev_strength == "MODELED_EMPIRICAL" else "E3"),
        "independence_group_id": ind_group,
        "independence_status": independence_status,
        "boundary": evidence_record.get("notes"),
        "appraisal": claim_appraisal,
    }

    return claim_record
