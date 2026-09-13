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

from evidence_states import classify_non_evidence, resolve_non_evidence_class  # noqa: E402


EVIDENCE_BEARING_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTORY",
}

#: H-49：claim 级资格 issue 代码 → 共识排除计数（excluded_from_consensus）的理由键。
#: `NON_EVIDENCE:<class>` 与 `CLAIM_STATUS_<VALUE>` 直接以自身作排除键。
CLAIM_ISSUE_REASON_KEYS = {
    "NEUTRAL_STANCE": "NEUTRAL",
    "UNRESOLVED": "UNRESOLVED",
    "DIFFERENT_PROPOSITION": "DIFFERENT_PROPOSITION",
    "UNKNOWN_EVIDENCE_STRENGTH": "UNKNOWN",
    "NO_EVIDENCE_STRENGTH": "NO_EVIDENCE_STRENGTH",
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

    # H-53（词袋命题兼容）：词袋（token 集合）相等但归一化串不等 = 同一批词的不同
    # 顺序——最典型是主宾互换（"A increases B" vs "B increases A"）。词袋比较把语序
    # 信息全丢，曾把反向关系判成 VERIFIED_SAME_PROPOSITION（反向主张可冒充支持）。
    # 此时无法在词袋层面证明命题对齐，必须 fail-closed 交人工（UNRESOLVED），
    # 由资格门禁拒绝入共识；原语序（归一化串相等）仍走上方 VERIFIED 成对断言。
    if norm_src and norm_tgt and set(norm_src.split()) == set(norm_tgt.split()):
        return "UNRESOLVED", (
            "Proposition tokens match but word order differs (possible subject/object "
            "swap); manual adjudication required: '%s' vs '%s'"
            % (source_target_claim, synthesis_target_claim))

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


def claim_consensus_issues(claim_record: Dict[str, Any]) -> List[str]:
    """H-49：claim 级共识资格检查（无证据索引上下文的公共判定）。

    与 `evaluate_consensus_eligibility` 的 claim 级检查**同源共用**，并被生产路径
    `controversy_analyzer.compute_topic_consensus()` 直接消费——资格门禁从此有了
    生产调用点（known P1-7 收口）。返回结构化 issue 代码列表，代码 → 排除键映射见
    `CLAIM_ISSUE_REASON_KEYS`；`NON_EVIDENCE:<class>` / `CLAIM_STATUS_<VALUE>`
    直接以自身作排除键，保证每次拒绝在 `excluded_from_consensus` 里可读数（设施-1）。

    检查项：
    1. 该记录不得属于「非证据」语义（NOT_REPORTED / UNCHECKED / INACCESSIBLE /
       CITED_ONLY / UNPARSEABLE）——判定走 `evidence_states` 单一真源；
    2. evidence_strength 与 evidence_tier 不得同时缺失，或 strength 为 UNKNOWN；
    3. stance 不得是 NEUTRAL（非证据承载立场，H-91：出分母）；
    4. stance_mapping_status 不得是 DIFFERENT_PROPOSITION / UNRESOLVED；
    5. claim 显式声明的上游状态（`claim_status` / `claim_status_upstream` 键存在时）
       必须是证据承载值——缺 key 不发表意见（普通 CLI 主张不携带该字段），但声明了
       空值/非承载值即拒绝（fail-closed，H-49「缺 claim_status」半边）。
    """
    issues: List[str] = []
    non_evidence = resolve_non_evidence_class(claim_record)
    if non_evidence:
        issues.append("NON_EVIDENCE:%s" % non_evidence)

    strength = claim_record.get("evidence_strength")
    tier = claim_record.get("evidence_tier")
    if not strength and not tier:
        issues.append("NO_EVIDENCE_STRENGTH")
    elif (strength == "UNKNOWN" or not strength) and not tier:
        issues.append("UNKNOWN_EVIDENCE_STRENGTH")

    if str(claim_record.get("stance", "") or "").upper() == "NEUTRAL":
        issues.append("NEUTRAL_STANCE")

    mapping_status = claim_record.get("stance_mapping_status")
    if mapping_status == "DIFFERENT_PROPOSITION":
        issues.append("DIFFERENT_PROPOSITION")
    elif mapping_status == "UNRESOLVED":
        issues.append("UNRESOLVED")

    for status_key in ("claim_status", "claim_status_upstream"):
        if status_key in claim_record:
            declared = str(claim_record.get(status_key) or "").strip().upper()
            if declared not in EVIDENCE_BEARING_STATUSES:
                issues.append("CLAIM_STATUS_%s" % (declared or "MISSING"))
    return issues


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
    5. 该记录不得属于「非证据」语义（NOT_REPORTED / UNCHECKED / INACCESSIBLE / CITED_ONLY /
       UNPARSEABLE）——判定走 `evidence_states` 单一真源，写法差异（"NOT REPORTED"、
       "not checked"、显式空值）同样拦截。
    6. evidence_strength must not be UNKNOWN or empty.
    7. Stance mapping status must not be DIFFERENT_PROPOSITION or UNRESOLVED（H-49）。
       UNRESOLVED 的唯一豁免：AUDITED_CANONICAL 模式下证据索引存在且所有引用证据逐条
       核验通过——此时立场来自上游已核验的 claim_status，而非缺失的命题对齐。
    8. Claim-level checks are shared with the production path via
       `claim_consensus_issues()`（controversy_analyzer.compute_topic_consensus 同源消费）。
    """
    issues: List[str] = []
    evidence_ids = claim_record.get("evidence_ids", [])
    ev_index = evidence_index or {}
    audited_clean = False

    if mode == "AUDITED_CANONICAL":
        if not evidence_index:
            issues.append("Missing evidence index: consensus calculations require verified evidence index in AUDITED_CANONICAL mode")
        elif not evidence_ids:
            issues.append("Missing evidence_ids references in claim record")
        else:
            mark = len(issues)
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
                if classify_non_evidence(ev_rec):
                    issues.append("Evidence '%s' is non-evidence-bearing (%s)"
                                  % (eid, classify_non_evidence(ev_rec)))
                elif claim_status not in EVIDENCE_BEARING_STATUSES:
                    issues.append(f"Evidence '{eid}' has non-evidence-bearing status: {claim_status}")

                supp_type = ev_rec.get("support_type")
                if supp_type in ("NOT_REPORTED", "NR"):
                    issues.append(f"Evidence '{eid}' has support_type '{supp_type}' (zero weight)")

                ev_strength = ev_rec.get("evidence_strength")
                if not ev_strength or ev_strength == "UNKNOWN":
                    issues.append(f"Evidence '{eid}' has UNKNOWN evidence strength")
            # H-49：全部引用证据逐条核验通过（本段零新增 issue）才算"已审计"。
            audited_clean = (len(issues) == mark)
    else:
        # Legacy/display mode checks if index is provided
        if ev_index and evidence_ids:
            for eid in evidence_ids:
                ev_rec = ev_index.get(eid)
                if ev_rec:
                    ctx_suff = ev_rec.get("context_sufficiency")
                    if ctx_suff == "INSUFFICIENT":
                        issues.append(f"Evidence '{eid}' has INSUFFICIENT context sufficiency")

    # Claim-level checks（与生产路径 compute_topic_consensus 共用单一判定）
    issues.extend(claim_consensus_issues(claim_record))
    if audited_clean and "UNRESOLVED" in issues:
        issues = [i for i in issues if i != "UNRESOLVED"]

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

    status = evidence_record.get("claim_status") or evidence_record.get("status")
    if not status:
        # H-49：缺 claim_status 不得默认 SUPPORTED（fail-closed）。无状态即无方向，
        # 映射立场交由资格门禁拒绝；SYN-A-08 实测默认 SUPPORTED 曾让"没查状态"的
        # 证据盖 E1 章直通共识。
        status = "UNRESOLVED"

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
