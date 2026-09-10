"""ScholarFlow Unified Execution Depth Profiles (RFC-014 / P2-02).

Defines the three orthogonal execution depth tiers (quick, standard, deep)
with concrete budget constraints, capability switches, and resource ceilings.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ExecutionDepth(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class ExecutionProfile:
    """Resource budget and methodological capability ceiling for a research execution run."""
    depth: ExecutionDepth
    name_zh: str
    description: str

    # Search & Discovery budgets
    max_search_candidates: int
    snowball_rounds: int
    concept_expansion_rounds: int

    # Extraction budgets
    extraction_unit_limit: int
    ocr_scan_policy: str                 # "text_only_skip_scans", "essential_tables_only", "full_multimodal_ocr"
    figure_table_verification: str       # "metadata_only", "sample_crosscheck", "exhaustive_audit"

    # Synthesis & Audit budgets
    cross_validation_budget: int
    spot_check_rate: float
    devils_advocate_mode: str            # "disabled", "standard", "adversarial_exhaustive"

    # Time & Model Call ceilings
    max_active_seconds: int             # Execution wall clock seconds (excluding user wait)
    max_model_requests: int
    max_token_ceiling: Optional[int]    # Soft/estimated Token ceiling; None if unconstrained
    enforcement: str = "best_effort"    # "best_effort" (default) or "hard"

    #: Aliases accepted on input and emitted on output for the depth field.
    _DEPTH_ALIASES = ("depth", "execution_depth")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the preset.

        The output round-trips exactly through :meth:`from_dict`, and the
        duplicate ``execution_depth`` alias is accepted on input (R04).
        """
        data = asdict(self)
        data["depth"] = self.depth.value
        data["execution_depth"] = self.depth.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExecutionProfile:
        """Rebuild a preset from its dictionary form.

        Unknown keys are rejected loudly rather than silently ignored, and a
        duplicate depth alias is tolerated as long as the values agree (R04).
        """
        d = dict(data)
        raw_depth = None
        for alias in cls._DEPTH_ALIASES:
            if alias in d:
                candidate = d.pop(alias)
                if raw_depth is None:
                    raw_depth = candidate
                elif candidate != raw_depth:
                    raise ValueError(
                        "Conflicting depth values in profile payload: %r vs %r"
                        % (raw_depth, candidate)
                    )
        if raw_depth is None:
            raise ValueError("Execution profile payload is missing a depth field")
        d["depth"] = raw_depth if isinstance(raw_depth, ExecutionDepth) else ExecutionDepth(str(raw_depth).lower().strip())

        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = sorted(set(d) - allowed)
        if unknown:
            raise ValueError("Unknown execution profile field(s): %s" % ", ".join(unknown))
        return cls(**d)


# Concrete definitions for the three tiers as specified in the manual:

QUICK_PROFILE = ExecutionProfile(
    depth=ExecutionDepth.QUICK,
    name_zh="快速档",
    description="聚焦核心代表性文献与快速验证，极速交付初步脉络（约5分钟预算）。",
    max_search_candidates=20,
    snowball_rounds=0,
    concept_expansion_rounds=0,
    extraction_unit_limit=5,
    ocr_scan_policy="text_only_skip_scans",
    figure_table_verification="metadata_only",
    cross_validation_budget=0,
    spot_check_rate=0.0,
    devils_advocate_mode="disabled",
    max_active_seconds=300,
    max_model_requests=10,
    max_token_ceiling=50000,
    enforcement="best_effort",
)

STANDARD_PROFILE = ExecutionProfile(
    depth=ExecutionDepth.STANDARD,
    name_zh="标准档 (推荐)",
    description="均衡查全率与论证严密性，覆盖核心文献、表格核验与双向追溯（约20分钟预算）。",
    max_search_candidates=50,
    snowball_rounds=1,
    concept_expansion_rounds=1,
    extraction_unit_limit=20,
    ocr_scan_policy="essential_tables_only",
    figure_table_verification="sample_crosscheck",
    cross_validation_budget=1,
    spot_check_rate=0.10,
    devils_advocate_mode="standard",
    max_active_seconds=1200,
    max_model_requests=30,
    max_token_ceiling=200000,
    enforcement="best_effort",
)

DEEP_PROFILE = ExecutionProfile(
    depth=ExecutionDepth.DEEP,
    name_zh="深度档",
    description="学术出版/系统综述级别高投入，饱和度滚雪球追踪、全图文OCR与对抗式异见审计（约60分钟预算）。",
    max_search_candidates=100,
    snowball_rounds=2,
    concept_expansion_rounds=2,
    extraction_unit_limit=50,
    ocr_scan_policy="full_multimodal_ocr",
    figure_table_verification="exhaustive_audit",
    cross_validation_budget=3,
    spot_check_rate=0.25,
    devils_advocate_mode="adversarial_exhaustive",
    max_active_seconds=3600,
    max_model_requests=100,
    max_token_ceiling=1000000,
    enforcement="best_effort",
)

DEPTH_PROFILES: Dict[ExecutionDepth, ExecutionProfile] = {
    ExecutionDepth.QUICK: QUICK_PROFILE,
    ExecutionDepth.STANDARD: STANDARD_PROFILE,
    ExecutionDepth.DEEP: DEEP_PROFILE,
}


def get_profile(depth: ExecutionDepth | str) -> ExecutionProfile:
    """Retrieve the standard ExecutionProfile for a given depth tier.

    Accepts an ``ExecutionDepth`` member, a canonical value, or any documented
    alias ("快速", "中等", ...). An unresolvable value raises ``ValueError``
    instead of a bare ``KeyError`` (R04).
    """
    if isinstance(depth, ExecutionDepth):
        return DEPTH_PROFILES[depth]
    if isinstance(depth, str):
        normalized = ExecutionDepth(depth.lower().strip()) if depth.strip().lower() in {
            member.value for member in ExecutionDepth
        } else None
        if normalized is None:
            from shared.execution.selection import normalize_depth

            normalized = normalize_depth(depth)
        if normalized is None:
            raise ValueError(
                "Invalid execution depth %r; allowed values are quick, standard, deep "
                "(aliases: 快速, 标准, 深度, 中等)" % (depth,)
            )
        return DEPTH_PROFILES[normalized]
    raise ValueError("Unsupported execution depth type: %r" % (type(depth).__name__,))
