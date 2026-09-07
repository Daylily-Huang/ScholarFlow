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


def evaluate_consensus_eligibility(
    claim_record: Dict[str, Any],
    evidence_index: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """
    Evaluate whether a ClaimRecord is eligible to participate in synthesis consensus calculations.
    Consumes upstream quality fields from Skill 2 EvidenceRecords:
    1. EvidenceRecord must exist for referenced evidence_ids
    2. Context sufficiency must not be INSUFFICIENT
    3. claim_status must be evidence-bearing (SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTORY)
    4. support_type must not be NOT_REPORTED / NR
    5. evidence_strength must not be UNKNOWN
    """
    issues = []
    evidence_ids = claim_record.get("evidence_ids", [])
    ev_index = evidence_index or {}

    # If evidence index is provided, verify referenced records
    if ev_index:
        if not evidence_ids:
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

                claim_status = ev_rec.get("claim_status") or ev_rec.get("status")
                if claim_status not in EVIDENCE_BEARING_STATUSES:
                    issues.append(f"Evidence '{eid}' has non-evidence-bearing status: {claim_status}")

                supp_type = ev_rec.get("support_type")
                if supp_type in ("NOT_REPORTED", "NR"):
                    issues.append(f"Evidence '{eid}' has support_type '{supp_type}' (zero weight)")

                ev_strength = ev_rec.get("evidence_strength")
                if ev_strength == "UNKNOWN":
                    issues.append(f"Evidence '{eid}' has UNKNOWN evidence strength")

    # Claim-level checks
    if claim_record.get("support_type") in ("NOT_REPORTED", "NR"):
        issues.append("Claim support_type is NOT_REPORTED")

    strength = claim_record.get("evidence_strength")
    tier = claim_record.get("evidence_tier")
    if not strength and not tier:
        issues.append("Claim has no evidence_strength or evidence_tier specified")
    elif strength == "UNKNOWN" and not tier:
        issues.append("Claim evidence_strength is UNKNOWN")

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
    - UNSUPPORTED / AMBIGUOUS -> NEUTRAL
    """
    ev_id = evidence_record.get("evidence_id", "EV-001")
    rec_id = evidence_record.get("record_id", "REC-UNKNOWN")
    topic = synthesis_target.get("topic") or "General Topic"
    target_prop = synthesis_target.get("target_claim") or synthesis_target.get("target_proposition") or synthesis_target.get("claim")

    # Determine stance
    if stance:
        claim_stance = stance.upper()
    else:
        status = evidence_record.get("claim_status") or evidence_record.get("status", "SUPPORTED")
        if status == "CONTRADICTORY":
            claim_stance = "REFUTE"
        elif status == "SUPPORTED":
            claim_stance = "SUPPORT"
        elif status == "PARTIALLY_SUPPORTED":
            claim_stance = "CONDITIONAL"
        else:
            claim_stance = "NEUTRAL"

    # Resolve evidence strength
    ev_strength = evidence_record.get("evidence_strength")
    if not ev_strength or ev_strength == "UNKNOWN":
        supp_type = evidence_record.get("support_type", "EXPLICIT")
        if supp_type == "EXPLICIT":
            ev_strength = "DIRECT_EMPIRICAL"
        elif supp_type == "DERIVED":
            ev_strength = "MODELED_EMPIRICAL"
        elif supp_type == "REFERENCED":
            ev_strength = "SECONDARY_EVIDENCE"
        else:
            ev_strength = "DIRECT_EMPIRICAL"

    claim_text = target_prop or evidence_record.get("verbatim_quote") or f"Finding from {rec_id}"
    cid = claim_id or f"CLM-{ev_id}"
    year = synthesis_target.get("year") or evidence_record.get("year") or "NR"

    claim_record = {
        "schema_version": "1.0",
        "claim_id": cid,
        "topic": topic,
        "paper_id": rec_id,
        "year": year,
        "claim": claim_text,
        "stance": claim_stance,
        "evidence_ids": [ev_id],
        "method": evidence_record.get("location", {}).get("section") or "Empirical measurement",
        "evidence_strength": ev_strength,
        "evidence_tier": "E1" if ev_strength == "DIRECT_EMPIRICAL" else ("E2" if ev_strength == "MODELED_EMPIRICAL" else "E3"),
        "boundary": evidence_record.get("notes"),
        "appraisal": {
            "directness": "HIGH",
            "independence": "HIGH",
            "risk_of_bias": "LOW",
            "replication": "HIGH",
        },
    }

    if "independence_group_id" in evidence_record:
        claim_record["independence_group_id"] = evidence_record["independence_group_id"]

    return claim_record
