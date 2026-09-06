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
    "EXPLICIT": "DIRECT_EMPIRICAL",
    "DERIVED": "MODELED_EMPIRICAL",
    "REFERENCED": "SECONDARY_EVIDENCE",
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
        dir_val = str(appraisal.get("directness", "HIGH")).upper()
        if dir_val == "LOW":
            mult *= 0.6
            factors.append("indirect(-0.2)")
        elif dir_val == "MEDIUM":
            mult *= 0.85
            factors.append("indirect_medium(-0.1)")

        ind_val = str(appraisal.get("independence", "HIGH")).upper()
        if ind_val == "LOW":
            mult *= 0.6
            factors.append("dependent(-0.2)")
        elif ind_val == "MEDIUM":
            mult *= 0.85

        rob_val = str(appraisal.get("risk_of_bias", "LOW")).upper()
        if rob_val == "HIGH":
            mult *= 0.6
            factors.append("bias_high(-0.3)")
        elif rob_val == "MEDIUM":
            mult *= 0.85
            factors.append("bias_medium(-0.1)")

        rep_val = str(appraisal.get("replication", "MEDIUM")).upper()
        if rep_val == "HIGH":
            mult *= 1.1
            factors.append("replicated(+0.1)")
        elif rep_val == "LOW":
            mult *= 0.9
            factors.append("unreplicated(-0.1)")

    final_weight = round(base_weight * mult, 3)
    return final_weight, strength, factors


def normalize_claim(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure standard fields and sensible defaults with support_type / evidence_strength decoupling."""
    topic = raw.get("topic") or raw.get("target_question") or "General Research Theme"
    stance = str(raw.get("stance", "NEUTRAL")).upper().strip()
    if stance not in VALID_STANCES:
        stance = "NEUTRAL"
    
    support_type = str(raw.get("support_type", "")).upper().strip()
    appraisal = raw.get("appraisal", {})
    final_weight, strength, _ = resolve_evidence_weight(raw)
        
    return {
        "topic": topic.strip(),
        "paper_id": raw.get("paper_id") or raw.get("source_citation") or "Unknown",
        "year": raw.get("year"),
        "claim": raw.get("claim") or raw.get("statement") or raw.get("claim_text") or "",
        "stance": stance,
        "method": raw.get("method") or "Unspecified Method",
        "metric_value": raw.get("metric_value"),
        "confidence_interval": raw.get("confidence_interval"),
        "evidence_strength": strength,
        "evidence_tier": strength,  # Backward compatibility
        "support_type": support_type if support_type else None,
        "appraisal": appraisal if isinstance(appraisal, dict) and appraisal else None,
        "weight": final_weight,
        "boundary": raw.get("boundary") or "Unspecified Boundary"
    }



def diagnose_controversy_type(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Diagnose controversy type (Taxonomy Type A-I) based on heuristics."""
    stances = [c["stance"] for c in claims]
    has_support = "SUPPORT" in stances
    has_refute = "REFUTE" in stances
    methods = set(c["method"].lower() for c in claims if c.get("method"))
    boundaries = set(c["boundary"].lower() for c in claims if c.get("boundary"))
    
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
            "reason": "Unanimous stance across examined evidence."
        }
        
    # Check if methods completely bifurcate with stances
    support_methods = set(c["method"].lower() for c in claims if c["stance"] == "SUPPORT")
    refute_methods = set(c["method"].lower() for c in claims if c["stance"] == "REFUTE")
    
    if support_methods and refute_methods and not (support_methods & refute_methods):
        return {
            "type": "Type B (Methodological Artifact / Tool Artifact)",
            "confidence": "High",
            "reason": f"Disagreement aligns 100% with differing methodological paradigms: Support used ({', '.join(support_methods)}) vs Refute used ({', '.join(refute_methods)})."
        }
        
    # Check numeric CI overlap
    if len(numeric_claims) >= 2:
        support_nums = [c["metric_value"] for c in numeric_claims if c["stance"] == "SUPPORT"]
        refute_nums = [c["metric_value"] for c in numeric_claims if c["stance"] == "REFUTE"]
        if support_nums and refute_nums:
            sup_mean = sum(support_nums) / len(support_nums)
            ref_mean = sum(refute_nums) / len(refute_nums)
            ratio = max(sup_mean, ref_mean) / (min(sup_mean, ref_mean) + 1e-9)
            if ratio > 2.0:
                return {
                    "type": "Type A (Direct Empirical Contradiction / Discrepancy)",
                    "confidence": "High",
                    "reason": f"Discrepancy in reported metrics exceeds 2-fold ({sup_mean:.2f} vs {ref_mean:.2f})."
                }

    if len(boundaries) > 1 and any("season" in b or "region" in b or "scale" in b for b in boundaries):
        return {
            "type": "Type D (Scale/Space-Time Dependence)",
            "confidence": "Medium",
            "reason": "Studies differ across sampling scales, seasons, or distinct geographic regions."
        }

    return {
        "type": "Type A (Direct Empirical Contradiction)",
        "confidence": "Medium",
        "reason": "Direct opposing assertions detected across independent studies without clear single-factor explanation."
    }


def compute_topic_consensus(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute evidence-weighted metrics and consensus level for a cluster of claims."""
    total_papers = len(claims)
    weights_by_stance = defaultdict(float)
    papers_by_stance = defaultdict(list)
    
    for c in claims:
        w = c["weight"]
        s = c["stance"]
        weights_by_stance[s] += w
        papers_by_stance[s].append(c["paper_id"])
        
    total_weight = sum(weights_by_stance.values())
    if total_weight == 0:
        total_weight = 1.0
        
    support_ratio = weights_by_stance["SUPPORT"] / total_weight
    refute_ratio = weights_by_stance["REFUTE"] / total_weight
    cond_ratio = weights_by_stance["CONDITIONAL"] / total_weight
    
    # Qualitative Consensus Classification (replacing mechanical majority voting)
    # Never claim "Universal Consensus"
    if total_weight < 1.0 or total_papers < 2:
        consensus_classification = "INSUFFICIENT_EVIDENCE"
        consensus_level = "Level 6 (Nascent / Insufficient Evidence Frontier)"
    elif (support_ratio >= 0.40 and refute_ratio >= 0.40) or (0.30 <= support_ratio <= 0.70 and 0.30 <= refute_ratio <= 0.70):
        consensus_classification = "ACTIVE_CONTROVERSY"
        consensus_level = "Level 5 (Explicit Paradigm / Scholarly Controversy)"
    elif cond_ratio >= 0.45:
        consensus_classification = "CONDITIONAL_CONSENSUS"
        consensus_level = "Level 3 (Context-Bounded Consensus / Conditional Agreement)"
    elif support_ratio >= 0.80 and len(papers_by_stance["SUPPORT"]) >= 2:
        consensus_classification = "STRONG_CONSENSUS"
        consensus_level = "Level 1 (Strong Prevailing Consensus - Replicated Evidence)"
    elif support_ratio >= 0.65:
        consensus_classification = "MODERATE_CONSENSUS"
        consensus_level = "Level 2 (Moderate Consensus with Minor Dissent)"
    else:
        consensus_classification = "CONDITIONAL_CONSENSUS"
        consensus_level = "Level 4 (Method-Dependent Convergence)"
        
    diagnosis = diagnose_controversy_type(claims)
    
    heuristic_balance = {
        "SUPPORT": round(support_ratio * 100, 1),
        "REFUTE": round(refute_ratio * 100, 1),
        "CONDITIONAL": round(cond_ratio * 100, 1),
        "NEUTRAL": round(weights_by_stance["NEUTRAL"] / total_weight * 100, 1)
    }

    return {
        "total_claims": total_papers,
        "total_evidence_weight": round(total_weight, 2),
        "stance_weights": {k: round(v, 2) for k, v in weights_by_stance.items()},
        "heuristic_balance_score": heuristic_balance,
        "stance_percentages": heuristic_balance,  # Backward compatibility
        "consensus_classification": consensus_classification,
        "consensus_level": consensus_level,
        "papers_by_stance": dict(papers_by_stance),
        "controversy_diagnosis": diagnosis
    }



def analyze(claims: List[Dict[str, Any]], topic_filter: Optional[str] = None) -> Dict[str, Any]:
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
        analysis = compute_topic_consensus(t_claims)
        analysis["claims"] = t_claims
        results[t] = analysis
        
    return results


# Alias for backward/contract compatibility
analyze_controversy = analyze


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
        lines.append(f"- **证据权重分布**：SUPPORT: {data['stance_percentages']['SUPPORT']}% | REFUTE: {data['stance_percentages']['REFUTE']}% | CONDITIONAL: {data['stance_percentages']['CONDITIONAL']}% (总权重: {data['total_evidence_weight']})")
        lines.append("")
        
        lines.append("### 证据链条明细对决表")
        lines.append("")
        lines.append("| 来源文献 | 立场 (Stance) | 证据等级 (Tier) | 核心主张 | 关键方法 | 适用边界 |")
        lines.append("|---|---|---|---|---|---|")
        for c in data["claims"]:
            lines.append(f"| {c['paper_id']} ({c.get('year', 'N/A')}) | `{c['stance']}` | `{c['evidence_tier']}` | {c['claim']} | {c['method']} | {c['boundary']} |")
        lines.append("")
        lines.append("### 🌐 学术论证拓扑图 (Argument Graph)")
        lines.append("")
        lines.append(generate_mermaid_argument_graph(topic, data["claims"]))
        lines.append("")

        # Red Team Warning if close tie
        sup = data['stance_percentages']['SUPPORT']
        ref = data['stance_percentages']['REFUTE']
        if 35.0 <= sup <= 65.0 and 35.0 <= ref <= 65.0:
            lines.append("> ⚠️ **Red-Team 警示**：当前议题存在高烈度学术对决，绝不可采信简单文献篇数多数决！请结合方法范式（如样线法 vs SECR、单管 PCR vs 多管 PCR）进行方法论溯源。")
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
        output_content = json.dumps(results, indent=2, ensure_ascii=False)
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
