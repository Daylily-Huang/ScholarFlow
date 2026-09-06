"""ScholarFlow Dynamic Context-Aware Recommendation Engine.

Resolves recommended options and rationales dynamically based on:
1. Explicit user preferences in context
2. Confirmed research goals and task mode (e.g. quick scan vs comprehensive survey)
3. Domain Lens methodological hints (e.g. Computer Science conference culture vs Biomedicine PubMed)
4. ScholarFlow epistemic anti-bias rules
5. Conservative static fallback (default_key)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shared.grill_me.response_parser import DimensionOption, GrillDimension


@dataclass
class RecommendationContext:
    skill_name: str
    research_goal: Optional[str] = None
    domain_lenses: List[str] = field(default_factory=list)
    resolved_values: Dict[str, Any] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    task_mode: Optional[str] = None


@dataclass
class Recommendation:
    dimension_id: str
    option_key: str
    confidence: str
    rationale: str
    source: str  # "user_preference", "task_goal", "domain_lens", "epistemic_rule", "static_fallback"


def recommend_option(
    dimension: GrillDimension,
    context: RecommendationContext,
) -> Recommendation:
    """Dynamically determine the recommended option for a given dimension."""
    dim_id = dimension.id
    lenses = [l.lower() for l in context.domain_lenses]
    goal = (context.research_goal or "").lower()
    mode = (context.task_mode or "").lower()
    prefs = context.user_preferences

    # 1. User Explicit Preferences
    if dim_id in prefs:
        val = prefs[dim_id]
        opt = dimension.get_option_by_key(str(val))
        if opt:
            return Recommendation(
                dimension_id=dim_id,
                option_key=opt.key,
                confidence="high",
                rationale=f"用户在上下文中显式指定了偏好选项: {opt.label}",
                source="user_preference",
            )

    # Specific preference aliases
    if dim_id == "D10" and prefs.get("language") in ["en", "en_only"]:
        opt_b = dimension.get_option_by_key("B")
        if opt_b:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="high",
                rationale="用户指定仅限英文文献",
                source="user_preference",
            )

    # 2. Task Mode & Research Goal
    is_quick_mode = any(k in mode for k in ["quick", "fast", "probe"]) or any(
        k in goal for k in ["快速", "探测", "benchmark", "quick", "fast"]
    )
    is_controversy_mode = any(k in goal for k in ["争议", "controversy", "争鸣", "对立"])
    is_protocol_mode = any(k in goal for k in ["方案", "协议", "protocol", "选型", "对比"])

    if dim_id == "D1":
        if is_controversy_mode:
            return Recommendation(
                dimension_id=dim_id,
                option_key="C",
                confidence="high",
                rationale="任务目标聚焦于对立学派争鸣与竞争假说事实核查",
                source="task_goal",
            )
        elif is_protocol_mode:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="high",
                rationale="任务目标聚焦于具体实验方案与评测参数对比选型",
                source="task_goal",
            )
        elif is_quick_mode:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="moderate",
                rationale="快速探测模式优先聚焦具体技术方案与代表性基准",
                source="task_goal",
            )

    if dim_id == "D8" and is_quick_mode:
        opt_b = dimension.get_option_by_key("B")
        if opt_b:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="moderate",
                rationale="快速前沿扫描聚焦近 3–5 年近期突破",
                source="task_goal",
            )

    if dim_id == "D13" and is_quick_mode:
        opt_b = dimension.get_option_by_key("B")
        if opt_b:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="moderate",
                rationale="快速粗查模式采用单层直接检索，严格控制调用成本",
                source="task_goal",
            )

    # 3. Domain Lens Methodological Hints
    is_cs = any(k in lenses for k in ["computer_science", "cs", "artificial_intelligence", "ai"])
    is_biomed = any(k in lenses for k in ["biomedical", "clinical", "medicine", "pharmacy"])

    if is_cs:
        if dim_id == "D9":
            opt_b = dimension.get_option_by_key("B")
            if opt_b:
                return Recommendation(
                    dimension_id=dim_id,
                    option_key="B",
                    confidence="high",
                    rationale="计算机科学中顶会论文（Conferences）与权威期刊同具最高学术影响力",
                    source="domain_lens",
                )
        elif dim_id == "D12":
            opt_a = dimension.get_option_by_key("A")
            if opt_a:
                return Recommendation(
                    dimension_id=dim_id,
                    option_key="A",
                    confidence="high",
                    rationale="计算机领域聚合 OpenAlex、arXiv 与开源多源检索，不设生物医学库默认依赖",
                    source="domain_lens",
                )
        elif dim_id == "D8":
            opt_b = dimension.get_option_by_key("B")
            if opt_b:
                return Recommendation(
                    dimension_id=dim_id,
                    option_key="B",
                    confidence="moderate",
                    rationale="计算机与 AI 领域技术迭代极快，优先聚焦近期前沿",
                    source="domain_lens",
                )

    if is_biomed:
        if dim_id == "D12":
            opt_a = dimension.get_option_by_key("A")
            if opt_a:
                return Recommendation(
                    dimension_id=dim_id,
                    option_key="A",
                    confidence="high",
                    rationale="生物医学领域推荐聚合 PubMed、Europe PMC 与 OpenAlex 权威实证源",
                    source="domain_lens",
                )

    # 4. Epistemic Rules (Extraction & Synthesis)
    if dim_id == "E1":
        if is_controversy_mode or "claim" in goal:
            return Recommendation(
                dimension_id=dim_id,
                option_key="B",
                confidence="high",
                rationale="对照文献审核既有结论真实性（Claim Audit 模式）",
                source="epistemic_rule",
            )
        elif is_protocol_mode:
            return Recommendation(
                dimension_id=dim_id,
                option_key="C",
                confidence="high",
                rationale="提炼各文献实验步骤、协议与关键参数对比",
                source="epistemic_rule",
            )

    # 5. Static Fallback
    fallback_key = dimension.default_key or (dimension.options[0].key if dimension.options else "A")
    fallback_opt = dimension.get_option_by_key(fallback_key)
    fallback_rationale = fallback_opt.rationale if fallback_opt and fallback_opt.rationale else "默认通用防错建议"
    fallback_confidence = fallback_opt.confidence if fallback_opt else "moderate"

    return Recommendation(
        dimension_id=dim_id,
        option_key=fallback_key,
        confidence=fallback_confidence,
        rationale=fallback_rationale,
        source="static_fallback",
    )


def apply_recommendations(
    dimensions: List[GrillDimension],
    context: RecommendationContext,
) -> List[GrillDimension]:
    """Decorate dimensions with context-aware recommendations."""
    resolved_dims = []
    for dim in dimensions:
        rec = recommend_option(dim, context)
        new_dim = copy.deepcopy(dim)
        for opt in new_dim.options:
            if opt.key.upper() == rec.option_key.upper():
                opt.is_recommended = True
                opt.rationale = rec.rationale
                opt.confidence = rec.confidence
            else:
                opt.is_recommended = False
        resolved_dims.append(new_dim)
    return resolved_dims
