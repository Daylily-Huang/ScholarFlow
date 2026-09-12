#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Controversy Analyzer (controversy_analyzer.py)
--------------------------------------------
Part of the `literature-synthesis` skill.

Analyzes normalized scientific claims and evidence matrices to:
1. Cluster claims by research question / scientific assertion.
2. Quantify stance distribution (SUPPORT, REFUTE, CONDITIONAL, NEUTRAL).
3. Compute evidence-weighted consensus scores (preventing paper-count voting).
4. Heuristically diagnose controversy types (Type A to Type I).
5. Generate structured synthesis reports and identify critical evidence gaps.

Usage:
    python controversy_analyzer.py --input claims.json --format markdown
    python controversy_analyzer.py --input claims.json --output controversy_report.json
    python controversy_analyzer.py --help
"""

import argparse
import json
import sys
import io
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from comparability import stratify_claims_by_comparability, ComparabilityStatus
except ImportError:
    import sys
    from pathlib import Path
    _cur_dir = str(Path(__file__).parent)
    if _cur_dir not in sys.path:
        sys.path.insert(0, _cur_dir)
    from comparability import stratify_claims_by_comparability, ComparabilityStatus

# Decoupled evidence strength weights (Synthesis Dimension)
EVIDENCE_STRENGTH_WEIGHTS = {
    "DIRECT_EMPIRICAL": 1.0,      # Direct experiment / raw sequencing / first-hand measurement
    "MODELED_EMPIRICAL": 0.8,     # Statistically modeled / peer-reviewed estimation
    "AUTHOR_INTERPRETATION": 0.4, # Discussion hypothesis / qualitative induction
    "SECONDARY_EVIDENCE": 0.2,    # Secondary review citations
    "EXPERT_OPINION": 0.1,        # Expert opinion / unsupported narrative
    "NOT_REPORTED": 0.0,          # Not reported in paper (strictly zero weight)
    "AMBIGUOUS_LEGACY_TIER": 0.0, # Legacy bare E4 without explicit semantic qualifier (P0-08)
    "UNKNOWN": 0.3
}

# Backward-compatibility alias map for legacy E1-E4 and extraction support_types
LEGACY_TIER_MAP = {
    "E1": "DIRECT_EMPIRICAL",
    "E1_EXPLICIT": "DIRECT_EMPIRICAL",
    "E2": "MODELED_EMPIRICAL",
    "E2_DERIVED": "MODELED_EMPIRICAL",
    "E3": "AUTHOR_INTERPRETATION",
    "E3_REFERENCED": "SECONDARY_EVIDENCE",
    "E4": "AMBIGUOUS_LEGACY_TIER",
    "E4_NR": "NOT_REPORTED",
    "NOT_REPORTED": "NOT_REPORTED",
    "NR": "NOT_REPORTED"
}

# Legacy alias for backward compatibility
EVIDENCE_WEIGHTS = {
    "E1": 1.0,
    "E2": 0.8,
    "E3": 0.4,
    "E4": 0.1,
    "UNKNOWN": 0.3
}

VALID_STANCES = {"SUPPORT", "REFUTE", "CONDITIONAL", "NEUTRAL"}

# The synthesis_coordinator role contract (role/synthesis_coordinator.md, 职责 2)
# mandates a SIX-value direction vocabulary. The canonical ClaimRecord schema
# (schemas/claim_record.schema.json) permits FOUR. A Claim Mapper agent that
# follows its own contract therefore emits values this analyzer does not know,
# and normalize_claim() used to coerce every unknown value to NEUTRAL -- so an
# OPPOSE claim silently stopped counting as opposition and 2 OPPOSE + 1 SUPPORT
# was scored as 3 claims leaning the same way. That is a silent inversion of the
# synthesis, produced purely by two roles disagreeing about a vocabulary.
#
# Direction-MAPPING (not direction-dropping): every contract value is translated
# into the canonical equivalent, and the original label is preserved on the claim
# so the translation is auditable. Mapping rationale:
#   OPPOSE  -> REFUTE     : direct negation is exactly what REFUTE means
#   NULL    -> NEUTRAL    : no detected effect is not evidence in either direction
#   MIXED   -> NEUTRAL    : non-monotonic / internally inconsistent claims cannot
#                           be assigned a single direction; they must not be
#                           counted as support for either side
#   NOT_TESTED -> NEUTRAL : the author did not test it, so it is not evidence
#   CONDITIONAL          : shared by both vocabularies, unchanged
CONTRACT_DIRECTION_MAP = {
    "OPPOSE": "REFUTE",
    "NULL": "NEUTRAL",
    "MIXED": "NEUTRAL",
    "NOT_TESTED": "NEUTRAL",
}



def parse_args():
    parser = argparse.ArgumentParser(
        description="Literature Controversy & Consensus Diagnostic Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example JSON input structure:
[
  {
    "topic": "Snow leopard density in Sanjiangyuan",
    "paper_id": "Zhang2015",
    "year": 2015,
    "claim": "Sanjiangyuan density is high (~3.2 ind/100km2)",
    "stance": "SUPPORT",
    "method": "Transect line scrape count",
    "metric_value": 3.2,
    "confidence_interval": [2.3, 4.1],
    "evidence_tier": "E2",
    "boundary": "Winter snow season only"
  },
  {
    "topic": "Snow leopard density in Sanjiangyuan",
    "paper_id": "Li2021",
    "year": 2021,
    "claim": "Sanjiangyuan density is moderate (~1.1 ind/100km2)",
    "stance": "REFUTE",
    "method": "SECR camera trap grid",
    "metric_value": 1.1,
    "confidence_interval": [0.8, 1.4],
    "evidence_tier": "E1",
    "boundary": "Year-round grid survey"
  }
]
        """
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to input JSON file containing extracted claims and evidence."
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path to save output report (default: stdout)."
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown", "summary"],
        default="markdown",
        help="Output format: json, markdown, or concise summary (default: markdown)."
    )
    parser.add_argument(
        "-t", "--topic",
        default=None,
        help="Filter analysis to a specific research topic substring."
    )
    return parser.parse_args()


def load_input_data(filepath: str) -> List[Dict[str, Any]]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if isinstance(data, dict) and "claims" in data:
        data = data["claims"]
    elif not isinstance(data, list):
        raise ValueError("Input JSON must be an array of claim objects or an object with a 'claims' array.")
        
    return data


#: RFC-017 裁定 2：**已核验反证参与加权**，但必须封顶，避免"反证多数决"。
#: 惩罚是"削弱"而不是"投票给对立立场"：它只从被挑战主张的权重里扣，绝不加到 REFUTE 上。
CHALLENGE_PENALTY = {"WEAKENS": 0.25, "REFUTES": 0.5}

#: 同一独立来源组的反证合计惩罚上限（与"单组支持权重封顶 1.0"同构）。
CHALLENGE_GROUP_PENALTY_CAP = 0.5


def challenge_penalty(challenges: List[Dict[str, Any]]) -> Tuple[float, List[str]]:
    """计算已核验反证对**被挑战主张**的权重惩罚；返回 `(penalty, factors)`。

    规则（RFC-017 裁定 2）：
      - 只有 `challenge_status == "VERIFIED_CHALLENGE"` 参与；未核验/待人工确认/被拒一律 0；
      - `WEAKENS` 扣 0.25、`REFUTES` 扣 0.5（以"一个独立组权重上限 1.0"为单位）；
      - 惩罚按**反证来源的独立组**合并，单组合计不超过 `CHALLENGE_GROUP_PENALTY_CAP`；
      - 惩罚只从被挑战主张的权重里扣，**不转移给对立立场**——因此再多反证也无法靠计数
        把结论翻成 REFUTE，只可能把支持权重压到 0（判为证据不足）。
    """
    by_group: Dict[str, float] = defaultdict(float)
    factors: List[str] = []
    for ch in challenges or []:
        if str(ch.get("challenge_status", "")).upper() != "VERIFIED_CHALLENGE":
            continue
        strength = str(ch.get("challenge_strength", "")).upper()
        amount = CHALLENGE_PENALTY.get(strength)
        if amount is None:
            continue
        grp = str(ch.get("independence_group_id") or ch.get("study_id")
                  or ch.get("paper_id") or "Unknown")
        by_group[grp] += amount
    penalty = 0.0
    for grp, raw_amount in sorted(by_group.items()):
        capped = min(raw_amount, CHALLENGE_GROUP_PENALTY_CAP)
        if capped < raw_amount:
            factors.append("challenge_group_capped(%s: %.2f->%.2f)"
                           % (grp, raw_amount, capped))
        penalty += capped
        factors.append("challenge(%s:-%.2f)" % (grp, capped))
    return penalty, factors


def apply_verified_challenges(weight: float, challenges: List[Dict[str, Any]]
                              ) -> Tuple[float, List[str]]:
    """把已核验反证折算为对被挑战主张权重的下调（不低于 0）。"""
    penalty, factors = challenge_penalty(challenges)
    if penalty <= 0.0:
        return float(weight), factors
    adjusted = max(0.0, float(weight) - penalty)
    if adjusted == 0.0 < float(weight):
        factors.append("challenge_zeroed_weight")
    return adjusted, factors


def resolve_evidence_weight(raw: Dict[str, Any]) -> Tuple[float, str, List[str]]:
    """
    Resolve base weight, resolved strength tier, and appraisal adjustment factors.
    Returns: (final_weight, resolved_strength, adjustment_factors)
    """
    support_type = str(raw.get("support_type", "")).upper().strip()
    extracted_val = str(raw.get("extracted_value", "")).upper().strip()
    factors = []

    # Strict isolation: NOT_REPORTED always yields 0.0 weight
    if support_type in ["NOT_REPORTED", "NR"] or extracted_val in ["NR", "NOT REPORTED"]:
        return 0.0, "NOT_REPORTED", ["not_reported(0.0)"]

    # Determine evidence strength: priority to evidence_strength, fallback to legacy evidence_tier / evidence_level
    raw_strength = raw.get("evidence_strength") or raw.get("evidence_tier") or raw.get("evidence_level") or "UNKNOWN"
    raw_str = str(raw_strength).upper().strip()
    if raw_str in EVIDENCE_STRENGTH_WEIGHTS:
        strength = raw_str
    elif raw_str in LEGACY_TIER_MAP:
        strength = LEGACY_TIER_MAP[raw_str]
    else:
        strength = "UNKNOWN"
    base_weight = EVIDENCE_STRENGTH_WEIGHTS.get(strength, 0.3)

    # Multi-dimensional Evidence Appraisal modifier
    appraisal = raw.get("appraisal", {})
    mult = 1.0
    if isinstance(appraisal, dict) and appraisal:
        has_incomplete = False

        raw_dir = appraisal.get("directness")
        dir_val = str(raw_dir).upper() if raw_dir else "UNKNOWN"
        if dir_val == "LOW":
            mult *= 0.6
            factors.append("indirect(-0.2)")
        elif dir_val == "MEDIUM":
            mult *= 0.85
            factors.append("indirect_medium(-0.1)")
        elif dir_val == "UNKNOWN":
            has_incomplete = True

        raw_ind = appraisal.get("independence")
        ind_val = str(raw_ind).upper() if raw_ind else "UNKNOWN"
        if ind_val == "LOW":
            mult *= 0.6
            factors.append("dependent(-0.2)")
        elif ind_val == "MEDIUM":
            mult *= 0.85
        elif ind_val == "UNKNOWN":
            has_incomplete = True

        raw_rob = appraisal.get("risk_of_bias")
        rob_val = str(raw_rob).upper() if raw_rob else "UNKNOWN"
        if rob_val == "HIGH":
            mult *= 0.6
            factors.append("bias_high(-0.3)")
        elif rob_val == "MEDIUM":
            mult *= 0.85
            factors.append("bias_medium(-0.1)")
        elif rob_val == "UNKNOWN":
            has_incomplete = True

        raw_rep = appraisal.get("replication")
        rep_val = str(raw_rep).upper() if raw_rep else "UNKNOWN"
        if rep_val == "HIGH":
            mult *= 1.1
            factors.append("replicated(+0.1)")
        elif rep_val == "LOW":
            mult *= 0.9
            factors.append("unreplicated(-0.1)")
        elif rep_val == "UNKNOWN":
            has_incomplete = True

        if has_incomplete:
            factors.append("appraisal_incomplete")

    final_weight = round(base_weight * mult, 3)
    return final_weight, strength, factors


def normalize_claim(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure standard fields and sensible defaults with support_type / evidence_strength decoupling."""
    topic = raw.get("topic") or raw.get("target_question") or "General Research Theme"
    raw_stance = str(raw.get("stance", "NEUTRAL")).upper().strip()
    # Translate the coordinator contract's six-value vocabulary into the canonical
    # four-value one instead of discarding the direction (see CONTRACT_DIRECTION_MAP).
    stance = CONTRACT_DIRECTION_MAP.get(raw_stance, raw_stance)
    direction_was_mapped = stance != raw_stance
    if stance not in VALID_STANCES:
        stance = "NEUTRAL"
    
    support_type = str(raw.get("support_type", "")).upper().strip()
    appraisal = raw.get("appraisal", {})
    final_weight, strength, _ = resolve_evidence_weight(raw)

    is_eligible = (
        strength not in {"UNKNOWN", "NOT_REPORTED", "AMBIGUOUS_LEGACY_TIER"}
        and support_type not in {"NOT_REPORTED", "NR"}
        and final_weight > 0.0
    )
        
    return {
        "topic": topic.strip(),
        "paper_id": raw.get("paper_id") or raw.get("source_citation") or "Unknown",
        # Carry the entity and the outcome metric through normalization: the
        # comparability layer needs them, and dropping them here made every claim
        # fall back to the shared topic string, so a cross-species claim looked
        # like the same subject as the target species.
        "subject": raw.get("subject") or raw.get("entity"),
        "metric": raw.get("metric") or raw.get("metric_name") or raw.get("outcome"),
        "unit": raw.get("unit"),
        "year": raw.get("year"),
        "claim": raw.get("claim") or raw.get("statement") or raw.get("claim_text") or "",
        "stance": stance,
        "stance_original": raw_stance,
        "stance_was_mapped": direction_was_mapped,
        "direction_provenance": ("mapped from contract vocabulary" if direction_was_mapped
                                 else "canonical"),
        "method": raw.get("method") or "Unspecified Method",
        "metric_value": raw.get("metric_value"),
        "confidence_interval": raw.get("confidence_interval"),
        "evidence_strength": strength,
        "evidence_tier": strength,  # Backward compatibility
        "support_type": support_type if support_type else None,
        "appraisal": appraisal if isinstance(appraisal, dict) and appraisal else None,
        "weight": final_weight,
        "consensus_eligible": is_eligible,
        "boundary": raw.get("boundary") or "Unspecified Boundary",
        "independence_group_id": raw.get("independence_group_id"),
        "independence_status": raw.get("independence_status"),
        "claim_id": raw.get("claim_id"),
        "evidence_ids": raw.get("evidence_ids", []),
    }



# Consensus levels defined by references/consensus_levels_and_boundaries.md that
# this script can never assign. `EMERGING_VIEW` requires a judgement about whether
# recent frontier work is CONVERGING on a new answer -- claim counts and weights
# cannot express convergence, and the schema's enum does not carry the level, so
# assigning it by rule would be a category error. It stays an explicit human /
# agent-analyst decision rather than being silently unreachable.
CONSENSUS_LEVELS_REQUIRING_HUMAN_ASSIGNMENT = ["EMERGING_VIEW"]

# Translation from this script's internal diagnosis labels to the 9-Type taxonomy
# in references/controversy_taxonomy_9types.md.
#
# The script used to emit "Type D" for scale/context/space-time discrepancies, but
# the taxonomy defines Type D as Taxon/System dependency (分类群与生境依赖型分歧)
# and assigns scale/space-time dependency to Type C. Same letter, different
# concept -- so a Controversy Analyst role that read this label and wrote it into
# a Controversy Map mislabelled every scale-driven finding. Labels are now
# translated explicitly and the taxonomy letter is carried separately.
TAXONOMY_TYPE_TRANSLATION = {
    "Type D (Scale/Context Discrepancy)":
        ("Type C", "尺度/情境依赖型分歧，对应争议分类体系 Type C"),
    "Type D (Scale/Space-Time Dependence)":
        ("Type C", "时空尺度依赖型分歧，对应争议分类体系 Type C"),
    "Type B Candidate (Method-associated disagreement)":
        ("Type B", "方法/模型依赖型分歧（本脚本只能给出候选，需人工确认）"),
    "Candidate Type A (Large metric discrepancy)":
        ("Type A", "指标差异超过 2 倍（候选，尚未确认测量可比性）"),
    "Candidate Type A (Direct claim disagreement)":
        ("Type A", "直接主张对立（候选，分歧来源未裁定）"),
}

# Types the script can never conclude on its own -- they require the human/agent
# analyst working from the taxonomy document.
TAXONOMY_TYPES_NOT_CODE_DETECTABLE = [
    "Type E (响应指标依赖型分歧)",
    "Type F (概念基础定义分歧)",
    "Type G (统计范式分歧)",
    "Type H (历史技术代际更替分歧)",
    "Type I (表面矛盾实则互补/伪争议)",
]


def annotate_taxonomy_type(diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the taxonomy type letter and an explicit ambiguity note."""
    label = str(diagnosis.get("type", ""))
    if label in TAXONOMY_TYPE_TRANSLATION:
        letter, note = TAXONOMY_TYPE_TRANSLATION[label]
        diagnosis["taxonomy_type"] = letter
        diagnosis["taxonomy_note"] = note
    elif label == "No Active Disagreement":
        diagnosis["taxonomy_note"] = (
            "脚本判定本证据集内无对立方向；但这不等于不存在分歧 —— "
            "分歧可能因证据无资格、方向词表不一致或分层而被隐藏，需人工复核。"
        )
    diagnosis["taxonomy_types_requiring_human_review"] = TAXONOMY_TYPES_NOT_CODE_DETECTABLE
    return diagnosis


def diagnose_controversy_type(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Diagnose controversy type (Taxonomy Type A-I) based on heuristics."""
    stances = [c.get("stance", "NEUTRAL") for c in claims]
    has_support = "SUPPORT" in stances
    has_refute = "REFUTE" in stances
    methods = set((c.get("method") or "").lower() for c in claims if c.get("method"))
    boundaries = set((c.get("boundary") or "").lower() for c in claims if c.get("boundary"))
    
    # Numeric analysis
    numeric_claims = [c for c in claims if c.get("metric_value") is not None]
    
    if not has_support or not has_refute:
        if any("conditional" == s.lower() for s in stances):
            return {
                "type": "Type D (Scale/Context Discrepancy)",
                "confidence": "Medium",
                "reason": "Claims differ based on conditional parameters or context boundaries rather than direct empirical negation."
            }
        return {
            "type": "No Active Disagreement",
            "confidence": "High",
            "reason": "No active disagreement detected within the supplied evidence set.",
            "scoped_to_evidence": True
        }
        
    # Check if methods completely bifurcate with stances
    support_methods = set((c.get("method") or "").lower() for c in claims if c.get("stance") == "SUPPORT" and c.get("method"))
    refute_methods = set((c.get("method") or "").lower() for c in claims if c.get("stance") == "REFUTE" and c.get("method"))
    
    if support_methods and refute_methods and not (support_methods & refute_methods):
        return {
            "type": "Type B Candidate (Method-associated disagreement)",
            "confidence": "Medium",
            "causal_status": "NOT_ESTABLISHED",
            "observed_pattern": "Opposing study groups use non-overlapping methods",
            "candidate_type": "METHOD_ASSOCIATED_DISAGREEMENT",
            "reason": (
                f"Opposing study groups use non-overlapping methods: Support used ({', '.join(sorted(support_methods))}) vs Refute used ({', '.join(sorted(refute_methods))}). "
                "This indicates a method-associated pattern, but does not establish that methodology caused the disagreement."
            ),
            "requires_review": [
                "measurement equivalence",
                "population comparability",
                "scale comparability",
                "sampling period",
                "model assumptions"
            ]
        }
        
    # Check numeric CI overlap
    if len(numeric_claims) >= 2:
        support_nums = [c.get("metric_value") for c in numeric_claims if c.get("stance") == "SUPPORT" and c.get("metric_value") is not None]
        refute_nums = [c.get("metric_value") for c in numeric_claims if c.get("stance") == "REFUTE" and c.get("metric_value") is not None]

        if support_nums and refute_nums:
            sup_mean = sum(support_nums) / len(support_nums)
            ref_mean = sum(refute_nums) / len(refute_nums)
            ratio = max(sup_mean, ref_mean) / (min(sup_mean, ref_mean) + 1e-9)
            if ratio > 2.0:
                return {
                    "type": "Candidate Type A (Large metric discrepancy)",
                    "confidence": "Medium",
                    "causal_status": "NOT_ESTABLISHED",
                    "observed_pattern": f"Discrepancy in reported metrics exceeds 2-fold ({sup_mean:.2f} vs {ref_mean:.2f})",
                    "candidate_type": "METRIC_DISCREPANCY_UNVERIFIED_COMPARABILITY",
                    "reason": (
                        f"Discrepancy in reported metrics exceeds 2-fold ({sup_mean:.2f} vs {ref_mean:.2f}). "
                        "Direct empirical contradiction is not established until outcome definition and measurement comparability are confirmed."
                    ),
                    "requires_review": [
                        "same outcome definition",
                        "same unit and denominator",
                        "same target population",
                        "spatial and temporal scale comparability"
                    ]
                }

    if len(boundaries) > 1 and any("season" in b or "region" in b or "scale" in b for b in boundaries):
        return {
            "type": "Type D (Scale/Space-Time Dependence)",
            "confidence": "Medium",
            "reason": "Studies differ across sampling scales, seasons, or distinct geographic regions."
        }

    return {
        "type": "Candidate Type A (Direct claim disagreement)",
        "confidence": "Low",
        "causal_status": "NOT_ESTABLISHED",
        "reason": (
            "Opposing claims are present in the supplied evidence set, "
            "but the source of disagreement has not been adjudicated."
        ),
        "requires_review": [
            "outcome definition",
            "population/entity comparability",
            "measurement comparability",
            "study design",
            "context boundary"
        ]
    }


def compute_topic_consensus(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute evidence-weighted metrics and consensus level for a cluster of claims."""
    # This function is reachable directly with RAW claims (it is part of the
    # module's public surface and is called that way by tests and by downstream
    # roles), so it must apply the same contract-vocabulary translation that
    # normalize_claim() does. Doing the mapping only in normalize_claim() left a
    # second, quieter path on which OPPOSE silently scored as zero.
    claims = [
        (dict(c, stance=CONTRACT_DIRECTION_MAP.get(
            str(c.get("stance", "")).upper().strip(), c.get("stance")))
         if str(c.get("stance", "")).upper().strip() in CONTRACT_DIRECTION_MAP else c)
        for c in claims
    ]
    total_claims = len(claims)
    
    # Determine consensus eligibility for each claim
    eligible_claims = []
    excluded_counts = defaultdict(int)
    all_papers_by_stance = defaultdict(list)
    
    for c in claims:
        s = c.get("stance", "NEUTRAL")
        all_papers_by_stance[s].append(c.get("paper_id", "Unknown"))

        # RFC-017：反证记录是"对被挑战主张的削弱"，不是一条独立立场证据。
        # 若把它当普通 REFUTE 计入，5 条反证就能靠计数压过 2 条支持——那正是
        # "反证多数决"，与项目的非多数决原则冲突。它只通过 apply_verified_challenges 生效。
        if str(c.get("relation", "")).upper() == "CHALLENGE" or "challenge_status" in c:
            excluded_counts["CHALLENGE_EVIDENCE"] += 1
            continue

        # Check eligibility. resolve_evidence_weight() is the single source of
        # truth, so a raw claim carrying only evidence_strength is weighted
        # exactly like a normalized one. Reading a missing "weight" as 0.0
        # silently discarded every such claim.
        styp = str(c.get("support_type", "")).upper().strip()
        resolved_weight, resolved_strength, _ = resolve_evidence_weight(c)
        if "weight" in c and c.get("weight") is not None:
            wt = float(c.get("weight", 0.0))
        else:
            wt = resolved_weight
        strn = c.get("evidence_strength") or c.get("evidence_tier") or c.get("evidence_level") or resolved_strength

        if "consensus_eligible" in c:
            eligible = bool(c["consensus_eligible"])
        else:
            eligible = (
                strn not in {"UNKNOWN", "NOT_REPORTED", "AMBIGUOUS_LEGACY_TIER"}
                and styp not in {"NOT_REPORTED", "NR"}
                and wt > 0.0
            )
        
        if eligible:
            # Pin the resolved weight so the per-group capping loop below cannot
            # fall back to a missing "weight" field.
            if "weight" not in c or c.get("weight") is None:
                c = dict(c)
                c["weight"] = wt
            eligible_claims.append(c)
        else:
            reason_key = c.get("evidence_strength") or c.get("support_type") or "UNKNOWN"
            if reason_key in {"NOT_REPORTED", "NR"}:
                excluded_counts["NOT_REPORTED"] += 1
            elif reason_key == "AMBIGUOUS_LEGACY_TIER":
                excluded_counts["AMBIGUOUS_LEGACY_TIER"] += 1
            elif reason_key == "UNKNOWN":
                excluded_counts["UNKNOWN"] += 1
            elif wt <= 0.0:
                excluded_counts["ZERO_WEIGHT"] += 1
            else:
                excluded_counts[str(reason_key)] += 1

    total_eligible_claims = len(eligible_claims)

    # RFC-017 裁定 2：反证参与加权（有上限，且不转移给对立立场）。
    # 反证记录以 target_claim_id 指向被挑战主张；未核验的反证不参与。
    challenges_by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    challenge_factors: List[str] = []
    for ch in claims:
        if str(ch.get("challenge_status", "")).upper() != "VERIFIED_CHALLENGE":
            continue
        target = ch.get("target_claim_id") or ch.get("target_claim") or ch.get("claim_id")
        if target:
            challenges_by_target[str(target)].append(ch)
    if challenges_by_target:
        adjusted_claims = []
        for c in eligible_claims:
            hits = challenges_by_target.get(str(c.get("claim_id")), [])
            if not hits:
                adjusted_claims.append(c)
                continue
            new_weight, factors = apply_verified_challenges(float(c.get("weight", 0.0)), hits)
            c = dict(c, weight=new_weight,
                     challenge_adjustment={"applied": True, "factors": factors,
                                           "challenges": len(hits)})
            challenge_factors.extend(factors)
            if new_weight > 0.0:
                adjusted_claims.append(c)
            else:
                excluded_counts["CHALLENGE_ZEROED"] += 1
        eligible_claims = adjusted_claims
        total_eligible_claims = len(eligible_claims)

    weights_by_stance = defaultdict(float)
    papers_by_stance = defaultdict(list)
    
    # Group claims by independence group / study / paper to prevent multi-claim inflation
    group_claims = defaultdict(list)
    for c in eligible_claims:
        grp_key = c.get("independence_group_id") or c.get("study_id") or c.get("paper_id", "Unknown")
        group_claims[grp_key].append(c)

    # Calculate stance weights with independence group weight capping (max 1.0 per group)
    for grp_key, grp_items in group_claims.items():
        grp_raw_weights = defaultdict(float)
        for item in grp_items:
            grp_raw_weights[item.get("stance", "NEUTRAL")] += float(item.get("weight", 0.0))
        grp_sum = sum(grp_raw_weights.values())
        scaling = (min(1.0, grp_sum) / grp_sum) if grp_sum > 1.0 else 1.0
        for s, w in grp_raw_weights.items():
            weights_by_stance[s] += w * scaling
        for item in grp_items:
            papers_by_stance[item.get("stance", "NEUTRAL")].append(item.get("paper_id", "Unknown"))

    total_weight = sum(weights_by_stance.values())

    # Counted before the early return so that INSUFFICIENT_EVIDENCE is auditable:
    # a caller must be able to tell "no eligible evidence" apart from
    # "one study only", which are different limitations.
    distinct_independence_groups = {
        c.get("independence_group_id") or c.get("study_id") or c.get("paper_id", "Unknown")
        for c in eligible_claims
    }

    # Zero weight or zero eligible claims strictly yields INSUFFICIENT_EVIDENCE
    if total_weight <= 0.0 or total_eligible_claims == 0:
        return {
            "total_claims": total_claims,
            "consensus_eligible_claims": 0,
            "excluded_from_consensus": dict(excluded_counts),
            "total_evidence_weight": 0.0,
            "distinct_independence_group_count": len(distinct_independence_groups),
            "stance_weights": {k: round(v, 2) for k, v in weights_by_stance.items()},
            "heuristic_balance_score": {
                "SUPPORT": 0.0,
                "REFUTE": 0.0,
                "CONDITIONAL": 0.0,
                "NEUTRAL": 0.0,
            },
            "stance_percentages": {
                "SUPPORT": 0.0,
                "REFUTE": 0.0,
                "CONDITIONAL": 0.0,
                "NEUTRAL": 0.0,
            },
            "consensus_classification": "INSUFFICIENT_EVIDENCE",
            "consensus_level": "Level 6 (Nascent / Insufficient Evidence Frontier)",
            "classification_scope": "CURRENT_EVIDENCE_SET_ONLY",
            "external_consensus_claim": False,
            "papers_by_stance": dict(all_papers_by_stance),
            "challenge_adjustment": {"factors": challenge_factors,
                                      "targets": sorted(challenges_by_target)},
            "controversy_diagnosis": {
                "type": "NO_ELIGIBLE_EVIDENCE",
                "confidence": "High",
                "reason": "No consensus-eligible evidence is available in the supplied evidence set."
            }
        }
        
    support_ratio = weights_by_stance["SUPPORT"] / total_weight
    refute_ratio = weights_by_stance["REFUTE"] / total_weight
    cond_ratio = weights_by_stance["CONDITIONAL"] / total_weight
    
    # Independent evidence groups and empirical support check (P1 17.1 & 17.2)
    support_claims = [c for c in eligible_claims if c.get("stance") == "SUPPORT"]
    support_groups = {
        c.get("independence_group_id") or c.get("paper_id", "Unknown")
        for c in support_claims
    }
    verified_support_groups = {
        c["independence_group_id"]
        for c in support_claims
        if c.get("independence_group_id") and c.get("independence_status") != "UNKNOWN"
    }
    has_empirical_support = any(
        c.get("evidence_strength") in ("DIRECT_EMPIRICAL", "MODELED_EMPIRICAL")
        or c.get("evidence_tier") in ("E1", "E2")
        for c in support_claims
    )

    # Replication requires distinct independence groups, not distinct claims.
    # N claims from ONE study are one measurement: they cannot establish a
    # consensus on their own. Without this guard a single group splitting its
    # result into several claim rows reached STRONG/MODERATE_CONSENSUS
    # (Level 1/2), which reads as replicated evidence when nothing was replicated.
    single_independence_group = len(distinct_independence_groups) < 2

    # Qualitative Consensus Classification (replacing mechanical majority voting)
    # Never claim "Universal Consensus"
    if total_weight < 1.0 or total_eligible_claims < 2 or single_independence_group:
        consensus_classification = "INSUFFICIENT_EVIDENCE"
        consensus_level = "Level 6 (Nascent / Insufficient Evidence Frontier)"
    elif (support_ratio >= 0.40 and refute_ratio >= 0.40) or (0.30 <= support_ratio <= 0.70 and 0.30 <= refute_ratio <= 0.70):
        consensus_classification = "ACTIVE_CONTROVERSY"
        consensus_level = "Level 5 (Explicit Paradigm / Scholarly Controversy)"
    elif cond_ratio >= 0.45:
        consensus_classification = "CONDITIONAL_CONSENSUS"
        consensus_level = "Level 3 (Context-Bounded Consensus / Conditional Agreement)"
    elif support_ratio >= 0.80 and len(verified_support_groups) >= 2 and has_empirical_support:
        consensus_classification = "STRONG_CONSENSUS"
        consensus_level = "Level 1 (Strong Prevailing Consensus - Replicated Evidence)"
    elif support_ratio >= 0.65 or (support_ratio >= 0.80 and len(support_groups) >= 2 and has_empirical_support):
        consensus_classification = "MODERATE_CONSENSUS"
        consensus_level = "Level 2 (Moderate Consensus with Minor Dissent)"
    else:
        consensus_classification = "CONDITIONAL_CONSENSUS"
        consensus_level = "Level 4 (Method-Dependent Convergence)"
        
    diagnosis = annotate_taxonomy_type(
        diagnose_controversy_type(eligible_claims if eligible_claims else claims))
    
    heuristic_balance = {
        "SUPPORT": round(support_ratio * 100, 1),
        "REFUTE": round(refute_ratio * 100, 1),
        "CONDITIONAL": round(cond_ratio * 100, 1),
        "NEUTRAL": round(weights_by_stance["NEUTRAL"] / total_weight * 100, 1)
    }

    return {
        "total_claims": total_claims,
        "consensus_eligible_claims": total_eligible_claims,
        "excluded_from_consensus": dict(excluded_counts),
        "total_evidence_weight": round(total_weight, 2),
        "distinct_independence_group_count": len(distinct_independence_groups),
        "single_independence_group": single_independence_group,
        "stance_weights": {k: round(v, 2) for k, v in weights_by_stance.items()},
        "heuristic_balance_score": heuristic_balance,
        "stance_percentages": heuristic_balance,  # Backward compatibility
        "consensus_classification": consensus_classification,
        "consensus_level": consensus_level,
        "classification_scope": "CURRENT_EVIDENCE_SET_ONLY",
        "external_consensus_claim": False,
        "papers_by_stance": dict(all_papers_by_stance),
        "challenge_adjustment": {"factors": challenge_factors,
                                 "targets": sorted(challenges_by_target),
                                 "applied": bool(challenges_by_target)},
        "controversy_diagnosis": diagnosis
    }



def analyze(claims: List[Dict[str, Any]], topic_filter: Optional[str] = None, target: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized = [normalize_claim(c) for c in claims]
    
    # Group by topic
    topics = defaultdict(list)
    for c in normalized:
        t = c["topic"]
        if topic_filter and topic_filter.lower() not in t.lower():
            continue
        topics[t].append(c)
        
    results = {}
    for t, t_claims in topics.items():
        # Pre-synthesis stratification (M3)
        strat_res = stratify_claims_by_comparability(t_claims, target=target)
        strata = strat_res.get("strata", {})
        uncomp = strat_res.get("uncomparable_claims", [])

        # Analyze each stratum independently
        strata_analysis = {}
        for s_key, s_claims in strata.items():
            s_res = compute_topic_consensus(s_claims)
            s_res["claims"] = s_claims
            strata_analysis[s_key] = s_res

        # Headline consensus is computed over the WHOLE claim set. A single
        # stratum must never stand in for the topic, or a method-level split
        # would be reported as "no disagreement" (review follow-up).
        overall_analysis = compute_topic_consensus(t_claims)

        # Best-evidenced stratum is still reported, but as a labelled stratum,
        # not as the topic-level verdict.
        primary_key = None
        if strata_analysis:
            if "core_stratum" in strata_analysis and strata_analysis["core_stratum"].get("claims"):
                primary_key = "core_stratum"
            else:
                primary_key = max(
                    strata_analysis.keys(),
                    key=lambda k: len(strata_analysis[k].get("claims", [])),
                )
        primary_analysis = (
            dict(strata_analysis[primary_key]) if primary_key else compute_topic_consensus(t_claims)
        )

        # Cross-stratum disagreement must be surfaced explicitly. Two strata
        # pointing opposite ways is a finding, not an absence of one.
        per_stratum_directions = {}
        for s_key, s_res in strata_analysis.items():
            hbs = s_res.get("heuristic_balance_score", {}) or {}
            support = float(hbs.get("SUPPORT", hbs.get("support_pct", 0.0)) or 0.0)
            refute = float(hbs.get("REFUTE", hbs.get("refute_pct", 0.0)) or 0.0)
            if support > refute:
                direction = "SUPPORT_LEANING"
            elif refute > support:
                direction = "REFUTE_LEANING"
            else:
                direction = "BALANCED"
            per_stratum_directions[s_key] = {
                "direction": direction,
                "claim_count": len(s_res.get("claims", [])),
                "consensus_classification": s_res.get("consensus_classification"),
            }

        distinct_directions = {v["direction"] for v in per_stratum_directions.values()} - {"BALANCED"}
        cross_stratum = {
            "stratum_count": len(strata_analysis),
            "per_stratum": per_stratum_directions,
            "uncomparable_claim_count": len(uncomp),
            "has_cross_stratum_difference": len(distinct_directions) > 1,
        }
        if cross_stratum["has_cross_stratum_difference"]:
            cross_stratum["disclosure"] = (
                "Different strata lean in different directions (%s). This is a method/context-level "
                "difference, not evidence that the topic is settled; it must be reported alongside "
                "the within-stratum verdict." % ", ".join(sorted(distinct_directions))
            )
        elif len(strata_analysis) > 1:
            cross_stratum["disclosure"] = (
                "Topic splits into %d strata that lean the same way; the within-stratum verdict "
                "is reported and the split itself remains a comparability finding."
                % len(strata_analysis)
            )
            if all(s.get("consensus_classification") == "INSUFFICIENT_EVIDENCE"
                   for s in strata_analysis.values()):
                cross_stratum["disclosure"] += (
                    " No stratum reaches a determinate verdict on its own, so the strata must "
                    "not be pooled and no topic-level verdict is issued."
                )

        headline_analysis = dict(overall_analysis)
        headline_analysis["claims"] = t_claims
        headline_analysis["strata"] = strata_analysis
        headline_analysis["primary_stratum"] = primary_key
        headline_analysis["within_stratum_analysis"] = primary_analysis
        headline_analysis["within_stratum_key"] = primary_key
        headline_analysis["cross_stratum_analysis"] = cross_stratum
        headline_analysis["uncomparable_claims"] = uncomp
        headline_analysis["comparability_records"] = strat_res.get("pairwise_comparisons", [])

        # ------------------------------------------------------------------
        # The headline must not outrank the strata it is built from.
        # compute_topic_consensus() over the pooled set cannot see the
        # stratification: it re-pools claims that were split precisely because
        # they are not commensurable, then reads the number of independence
        # groups as replication. That produced "STRONG_CONSENSUS / Level 1
        # (Replicated Evidence)" across two methodologically incompatible
        # one-study strata -- a pooled number standing in for a topic it does
        # not describe.
        #
        # The headline is withheld only when it would describe something the
        # evidence does not contain:
        #   (a) the strata lean the same way AND no stratum reaches a determinate
        #       verdict, so any pooled number was manufactured by pooling; or
        #   (b) the strata lean the same way but at least one stratum is
        #       internally BALANCED, i.e. the "replication" is a between-stratum
        #       vote rather than a repeated measurement.
        # A genuine directional disagreement between incomparable strata is NOT
        # withheld: that disagreement is itself the reported finding (and the
        # caveat that it may be method-associated is disclosed alongside it).
        # Withholding it would have replaced "no disagreement" with "no verdict"
        # and hidden a real split either way.
        if len(strata_analysis) > 1:
            determinate_strata = [
                k for k, s in strata_analysis.items()
                if s.get("consensus_classification") != "INSUFFICIENT_EVIDENCE"
            ]
            no_determinate = not determinate_strata
            manufactured_replication = (
                any(v["direction"] == "BALANCED"
                    for v in per_stratum_directions.values())
            )
            if (not cross_stratum["has_cross_stratum_difference"]
                    and (no_determinate or manufactured_replication)):
                pooled_level = headline_analysis.get("consensus_level")
                pooled_class = headline_analysis.get("consensus_classification")
                headline_analysis["pooled_consensus_classification"] = pooled_class
                headline_analysis["consensus_classification"] = "INSUFFICIENT_EVIDENCE"
                headline_analysis["consensus_level"] = \
                    "Level 6 (Nascent / Insufficient Evidence Frontier)"
                headline_analysis["headline_withheld_reason"] = (
                    "claims split into %d methodologically non-comparable strata that "
                    "lean the same way; %s. The pooled figure (%s / %s) must not be "
                    "reported as the topic-level consensus -- a between-stratum vote is "
                    "not a replication of the same measurement."
                    % (len(strata_analysis),
                       "no single stratum reaches a determinate verdict on its own"
                       if no_determinate else
                       "at least one stratum is internally balanced, so pooling "
                       "manufactures the appearance of replication",
                       pooled_class, pooled_level)
                )
                headline_analysis["controversy_diagnosis"] = {
                    "type": "NO_POOLABLE_VERDICT_ACROSS_STRATA",
                    "confidence": "High",
                    "reason": (
                        "Comparability stratification separated the claims into %d strata "
                        "that cannot be pooled. %s A within-stratum verdict is required; "
                        "the per-stratum results are reported in `strata`."
                        % (len(strata_analysis),
                           "No stratum reaches a determinate verdict on its own."
                           if no_determinate else
                           "Each stratum is internally balanced and therefore carries "
                           "no determinate verdict of its own.")
                    ),
                    "strata_checked": len(strata_analysis),
                    "determinate_strata": determinate_strata,
                }
            elif no_determinate:
                # Headline kept because the strata point opposite ways -- but the
                # reader must still be told that no stratum can carry it alone.
                headline_analysis["headline_caveat"] = (
                    "headline kept because the strata disagree in direction; note that no "
                    "single stratum reaches a determinate verdict on its own, so the "
                    "disagreement is between incomparable strata and is NOT established "
                    "as a substantive scientific contradiction."
                )

        results[t] = headline_analysis
        
    return results


# Alias for backward/contract compatibility
analyze_controversy = analyze


def to_canonical_synthesis_records(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform analyze() results into a list of canonical SynthesisRecords validating
    against `schemas/synthesis_record.schema.json`.
    """
    records = []
    for topic, data in results.items():
        hbs = data.get("heuristic_balance_score", {})
        canonical_hbs = {
            "support_pct": float(hbs.get("SUPPORT", hbs.get("support_pct", 0.0))),
            "refute_pct": float(hbs.get("REFUTE", hbs.get("refute_pct", 0.0))),
            "conditional_pct": float(hbs.get("CONDITIONAL", hbs.get("conditional_pct", 0.0))),
            "neutral_pct": float(hbs.get("NEUTRAL", hbs.get("neutral_pct", 0.0))),
        }

        diag = data.get("controversy_diagnosis", {})
        canonical_diag = {
            "type": str(diag.get("type", "No Active Disagreement")),
            "confidence": str(diag.get("confidence", "Medium")),
            "reason": str(diag.get("reason", "No detailed rationale provided")),
        }

        rec = {
            "schema_version": "1.0",
            "topic": topic,
            "total_claims": int(data.get("total_claims", 0)),
            "consensus_classification": data.get("consensus_classification", "INSUFFICIENT_EVIDENCE"),
            "heuristic_balance_score": canonical_hbs,
            "controversy_diagnosis": canonical_diag,
        }
        records.append(rec)
    return records


def generate_mermaid_argument_graph(topic: str, claims: List[Dict[str, Any]]) -> str:
    """Generate a Mermaid flowchart visualizing the argument structure (Supporting vs Refuting)."""
    lines = ["```mermaid", "graph TD"]
    
    # Safe id
    safe_topic = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '_', topic)[:30]
    center_id = f"TOPIC_{safe_topic}"
    clean_topic = topic.replace('"', "'")
    lines.append(f'    {center_id}["核心命题: {clean_topic}"]:::topicNode')
    
    support_claims = [c for c in claims if c["stance"] == "SUPPORT"]
    refute_claims = [c for c in claims if c["stance"] == "REFUTE"]
    cond_claims = [c for c in claims if c["stance"] == "CONDITIONAL"]
    
    if support_claims:
        camp_sup_id = f"CAMP_SUP_{safe_topic}"
        lines.append(f'    {camp_sup_id}["支持阵营 (SUPPORT)"]:::supCamp')
        lines.append(f'    {camp_sup_id} ==>|支持主张| {center_id}')
        for idx, c in enumerate(support_claims[:4]):
            c_id = f"EV_S_{safe_topic}_{idx}"
            tier = c["evidence_tier"]
            pid = c["paper_id"]
            method = c["method"].replace('"', "'")[:25]
            lines.append(f'    {c_id}["[{tier}] {pid}<br/>方法: {method}"]:::supNode --> {camp_sup_id}')
            
    if refute_claims:
        camp_ref_id = f"CAMP_REF_{safe_topic}"
        lines.append(f'    {camp_ref_id}["反对/竞争阵营 (REFUTE)"]:::refCamp')
        lines.append(f'    {camp_ref_id} ==>|反驳/竞争| {center_id}')
        for idx, c in enumerate(refute_claims[:4]):
            c_id = f"EV_R_{safe_topic}_{idx}"
            tier = c["evidence_tier"]
            pid = c["paper_id"]
            method = c["method"].replace('"', "'")[:25]
            lines.append(f'    {c_id}["[{tier}] {pid}<br/>方法: {method}"]:::refNode --> {camp_ref_id}')
            
    if cond_claims:
        camp_cnd_id = f"CAMP_CND_{safe_topic}"
        lines.append(f'    {camp_cnd_id}["条件限定/调和视角 (CONDITIONAL)"]:::cndCamp')
        lines.append(f'    {camp_cnd_id} -.->|情境边界约束| {center_id}')
        for idx, c in enumerate(cond_claims[:3]):
            c_id = f"EV_C_{safe_topic}_{idx}"
            pid = c["paper_id"]
            bnd = c["boundary"].replace('"', "'")[:25]
            lines.append(f'    {c_id}["{pid}<br/>边界: {bnd}"]:::cndNode --> {camp_cnd_id}')
            
    # Class definitions for styling
    lines.append("    classDef topicNode fill:#f9f0ff,stroke:#6b21a8,stroke-width:2px,color:#000;")
    lines.append("    classDef supCamp fill:#e6ffed,stroke:#16a34a,stroke-width:2px,color:#000;")
    lines.append("    classDef refCamp fill:#fff1f0,stroke:#dc2626,stroke-width:2px,color:#000;")
    lines.append("    classDef cndCamp fill:#f0f7ff,stroke:#2563eb,stroke-width:2px,color:#000;")
    lines.append("    classDef supNode fill:#f6ffed,stroke:#52c41a,color:#333;")
    lines.append("    classDef refNode fill:#fff2e8,stroke:#fa541c,color:#333;")
    lines.append("    classDef cndNode fill:#f0f5ff,stroke:#2f54eb,color:#333;")
    lines.append("```")
    return "\n".join(lines)


def format_markdown_report(results: Dict[str, Any]) -> str:
    lines = []
    lines.append("# 学术争议与共识综合分析报告 (Literature Controversy & Consensus Diagnostic Report)")
    lines.append("")
    lines.append(f"> **生成模块**：`controversy_analyzer.py` | **分析主题数**：{len(results)}")
    lines.append("")
    
    for topic, data in results.items():
        lines.append(f"## 主题：{topic}")
        lines.append("")
        lines.append(f"- **共识层级**：`{data['consensus_level']}`")
        lines.append(f"- **争议诊断**：`{data['controversy_diagnosis']['type']}` (置信度: {data['controversy_diagnosis']['confidence']})")
        lines.append(f"- **诊断溯源**：{data['controversy_diagnosis']['reason']}")
        # A withheld headline is a finding, not a blank: say so where the reader
        # looks first, and say what the pooled number would have been.
        if data.get("headline_withheld_reason"):
            lines.append(
                "- 🚫 **头条结论已撤回（分层不可合并）**：%s"
                % data["headline_withheld_reason"]
            )
            if data.get("pooled_consensus_classification"):
                lines.append(
                    "- （未撤回时按全量合并会得到 `%s`，该数字不代表本议题，仅留作审计）"
                    % data["pooled_consensus_classification"]
                )
        elif data.get("headline_caveat"):
            lines.append("- ⚠️ **头条结论保留但受限**：%s" % data["headline_caveat"])
        lines.append(f"- **证据权重分布**：SUPPORT: {data['stance_percentages']['SUPPORT']}% | REFUTE: {data['stance_percentages']['REFUTE']}% | CONDITIONAL: {data['stance_percentages']['CONDITIONAL']}% (总权重: {data['total_evidence_weight']})")
        # Replication must be auditable in the rendered report: a Level-6 verdict
        # caused by "one study only" looks identical to "no usable evidence"
        # unless the group count is printed.
        grp_count = data.get("distinct_independence_group_count")
        if grp_count is not None:
            lines.append(f"- **独立证据单元数**（independence_group 去重后）：{grp_count}")
        if data.get("single_independence_group"):
            lines.append(
                "- ⚠️ **只有一个独立研究组**：多条主张来自同一研究单元，"
                "不构成重复验证，已按证据不足处理（INSUFFICIENT_EVIDENCE）。"
            )
        lines.append("")
        
        # Comparability disclosure: a method-level split must be visible in the
        # rendered report, not only in the JSON payload. Omitting it here was
        # what let a stratified disagreement read as "no disagreement".
        cross = data.get("cross_stratum_analysis")
        if cross and cross.get("stratum_count", 0) > 1:
            lines.append("### ⚖️ 可比性分层与跨层差异 (Comparability Strata)")
            lines.append("")
            lines.append(
                "- **分层数**：%d | **无法归入任何层**：%d 条"
                % (cross["stratum_count"], cross.get("uncomparable_claim_count", 0))
            )
            primary = data.get("primary_stratum")
            if primary:
                lines.append(
                    "- **本次比较的基准层**：`%s`（由元数据完备度与方法学表征最高的基准主张决定基准层，"
                    "不代表该层证据最强；其余层结论见下表，**不可用以代表整体**）" % primary
                )
            lines.append("")
            lines.append("| 分层 | 主张数 | 倾向 | 层内共识 |")
            lines.append("|---|---:|---|---|")
            for key, info in sorted(cross.get("per_stratum", {}).items()):
                lines.append(
                    "| `%s` | %s | `%s` | `%s` |"
                    % (key, info.get("claim_count"), info.get("direction"),
                       info.get("consensus_classification"))
                )
            lines.append("")
            if cross.get("disclosure"):
                tag = "⚠️ **分层间方向不一致**" if cross.get("has_cross_stratum_difference") else "ℹ️ 分层说明"
                lines.append("%s：%s" % (tag, cross["disclosure"]))
                lines.append("")
            lines.append(
                "> 方法学差异只能提示「差异与方法相关」，**不能证明差异由方法造成**。"
                "跨层比较需在方法可比的层内进行。"
            )
            lines.append("")

        within = data.get("within_stratum_analysis")
        if within is not None and data.get("primary_stratum"):
            lines.append(
                "### 层内结论（仅限 `%s`）" % data["primary_stratum"]
            )
            lines.append("")
            lines.append(
                "- 层内共识层级：`%s` | 层内主张数：%s"
                % (within.get("consensus_classification", "N/A"), len(within.get("claims", [])))
            )
            lines.append("")

        lines.append("### 证据链条明细对决表（已纳入综合）")
        lines.append("")
        # The study organism is printed per row: without it a cross-species claim
        # (e.g. sika deer) sitting in the same topic block is indistinguishable
        # from a target-species fact when the report is read on its own.
        has_subject = any((c.get("subject") or "") not in ("", c.get("topic"))
                          for c in data["claims"])
        uncomparable_ids = {id(c) for c in (data.get("uncomparable_claims") or [])}
        comparable = [c for c in data["claims"] if id(c) not in uncomparable_ids]
        if has_subject:
            lines.append("| 来源文献 | 研究对象 | 立场 (Stance) | 证据等级 (Tier) | 核心主张 | 关键方法 | 适用边界 |")
            lines.append("|---|---|---|---|---|---|---|")
            for c in comparable:
                lines.append(
                    f"| {c['paper_id']} ({c.get('year', 'N/A')}) | {c.get('subject') or '未声明'} "
                    f"| `{c['stance']}` | `{c['evidence_tier']}` | {c['claim']} | {c['method']} | {c['boundary']} |"
                )
        else:
            lines.append("| 来源文献 | 立场 (Stance) | 证据等级 (Tier) | 核心主张 | 关键方法 | 适用边界 |")
            lines.append("|---|---|---|---|---|---|")
            for c in comparable:
                lines.append(f"| {c['paper_id']} ({c.get('year', 'N/A')}) | `{c['stance']}` | `{c['evidence_tier']}` | {c['claim']} | {c['method']} | {c['boundary']} |")
        lines.append("")

        # Uncomparable claims are listed separately and explicitly: a subject or
        # metric mismatch means they are NOT evidence about this topic, and
        # printing them inside the main table let them be read as if they were.
        uncomparable = data.get("uncomparable_claims") or []
        if uncomparable:
            lines.append("### 🚫 不可比主张（已排除出综合，不得作为本命题证据）")
            lines.append("")
            lines.append("| 来源文献 | 研究对象 | 立场 | 证据等级 | 主张 | 排除理由 |")
            lines.append("|---|---|---|---|---|---|")
            for c in uncomparable:
                reason = ""
                for rec in data.get("comparability_records", []):
                    if rec.get("claim_id_b") == c.get("claim_id") or rec.get("claim_id_a") == c.get("claim_id"):
                        reason = "%s (%s)" % (rec.get("status"), rec.get("rationale", "")[:60])
                        break
                lines.append(
                    f"| {c['paper_id']} ({c.get('year', 'N/A')}) | {c.get('subject') or '未声明'} "
                    f"| `{c['stance']}` | `{c['evidence_tier']}` | {c['claim']} | {reason} |"
                )
            lines.append("")
        lines.append("### 🌐 学术论证拓扑图 (Argument Graph)")
        lines.append("")
        lines.append(generate_mermaid_argument_graph(topic, data["claims"]))
        lines.append("")

        # Red Team Warning if close tie
        sup = data['stance_percentages']['SUPPORT']
        ref = data['stance_percentages']['REFUTE']
        if 35.0 <= sup <= 65.0 and 35.0 <= ref <= 65.0:
            lines.append("> ⚠️ **Red-Team 警示**：当前议题存在高烈度学术对决，绝不可采信简单文献篇数多数决！请进一步检查测量定义、研究对象、采样设计、比较边界、分析模型、数据独立性及时间/空间尺度是否可比。")
            lines.append("")
            
        lines.append("---")
        lines.append("")
        
    return "\n".join(lines)


def format_summary_report(results: Dict[str, Any]) -> str:
    lines = []
    lines.append("=== LITERATURE SYNTHESIS SUMMARY ===")
    for topic, data in results.items():
        lines.append(f"Topic: {topic}")
        lines.append(f"  Consensus: {data['consensus_level']}")
        lines.append(f"  Controversy: {data['controversy_diagnosis']['type']}")
        lines.append(f"  Stance Split: Support={data['stance_percentages']['SUPPORT']}%, Refute={data['stance_percentages']['REFUTE']}%")
        lines.append(f"  Claims count: {data['total_claims']}")
    return "\n".join(lines)


def main():
    args = parse_args()
    try:
        raw_claims = load_input_data(args.input)
    except Exception as e:
        sys.stderr.write(f"Error loading input file: {e}\n")
        sys.exit(1)
        
    results = analyze(raw_claims, topic_filter=args.topic)
    
    if args.format == "json":
        canonical_records = to_canonical_synthesis_records(results)
        output_content = json.dumps(canonical_records, indent=2, ensure_ascii=False)
    elif args.format == "summary":
        output_content = format_summary_report(results)
    else:
        output_content = format_markdown_report(results)
        
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_content)
        print(f"[SUCCESS] Analysis written to {args.output}")
    else:
        print(output_content)


if __name__ == "__main__":
    main()
