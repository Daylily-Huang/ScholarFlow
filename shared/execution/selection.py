"""ScholarFlow Execution Depth Selection & Normalization (RFC-014 / P2-02).

Handles depth normalization, alias mapping (including Chinese terms and aliases),
selection source provenance, and conflict validation.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from shared.execution.profiles import ExecutionDepth


class DepthSelectionSource(str, Enum):
    EXPLICIT_ARG = "EXPLICIT_ARG"                    # Supplied via CLI flag (e.g. --execution-depth)
    INTERACTIVE_CONFIRMED = "INTERACTIVE_CONFIRMED"  # Confirmed via Stage 0 Grill-Me question
    RUN_PROFILE_INHERITED = "RUN_PROFILE_INHERITED"  # Inherited from shared runs/<run_id>/ profile
    CONTEXT_RESOLVED = "CONTEXT_RESOLVED"            # Resolved with high confidence from conversation context


# Alias mapping including Chinese terms as specified in Section 3 & 16 of the manual:
# "支持 quick/standard/deep，中文快速/标准/深度，中等为标准别名"
DEPTH_ALIAS_MAP = {
    "quick": ExecutionDepth.QUICK,
    "q": ExecutionDepth.QUICK,
    "快速": ExecutionDepth.QUICK,
    "快": ExecutionDepth.QUICK,
    "fast": ExecutionDepth.QUICK,

    "standard": ExecutionDepth.STANDARD,
    "std": ExecutionDepth.STANDARD,
    "标准": ExecutionDepth.STANDARD,
    "标": ExecutionDepth.STANDARD,
    "中等": ExecutionDepth.STANDARD,  # Explicitly required alias
    "中": ExecutionDepth.STANDARD,
    "medium": ExecutionDepth.STANDARD,

    "deep": ExecutionDepth.DEEP,
    "d": ExecutionDepth.DEEP,
    "深度": ExecutionDepth.DEEP,
    "深": ExecutionDepth.DEEP,
    "comprehensive": ExecutionDepth.DEEP,
}


def normalize_depth(val: Optional[str]) -> Optional[ExecutionDepth]:
    """Normalize input string to canonical ExecutionDepth enum or return None if invalid/empty."""
    if not val:
        return None
    cleaned = str(val).strip().lower()
    return DEPTH_ALIAS_MAP.get(cleaned)


def validate_depth_conflict(legacy_mode: Optional[str], execution_depth: Optional[str | ExecutionDepth]) -> Optional[ExecutionDepth]:
    """Validate and harmonize legacy --mode with --execution-depth (T10).

    Raises:
        ValueError: If legacy_mode and execution_depth are both provided and conflict.
    """
    depth_norm = execution_depth if isinstance(execution_depth, ExecutionDepth) else normalize_depth(execution_depth)
    legacy_norm = normalize_depth(legacy_mode)

    if legacy_norm is not None and depth_norm is not None:
        if legacy_norm != depth_norm:
            raise ValueError(
                f"Conflicting execution depth options provided: "
                f"--mode '{legacy_mode}' ({legacy_norm.value}) vs "
                f"--execution-depth '{execution_depth}' ({depth_norm.value}). "
                f"Please specify a single consistent depth tier."
            )
        return depth_norm

    if depth_norm is not None:
        return depth_norm

    if legacy_norm is not None:
        return legacy_norm

    return None
