"""ScholarFlow Execution Subsystem (RFC-014 / P2-02).

Provides unified execution depth tiers (quick, standard, deep), budget tracking,
preflight validation, and truthful execution receipts.
"""

from shared.execution.profiles import (
    ExecutionDepth,
    ExecutionProfile,
    QUICK_PROFILE,
    STANDARD_PROFILE,
    DEEP_PROFILE,
    DEPTH_PROFILES,
    get_profile,
)
from shared.execution.selection import (
    DepthSelectionSource,
    DEPTH_ALIAS_MAP,
    normalize_depth,
    validate_depth_conflict,
)
from shared.execution.budget import (
    BudgetState,
    TokenMeasurementStatus,
    ExecutionReceipt,
    ExecutionBudget,
)
from shared.execution.preflight import (
    PreflightError,
    preflight_check,
)
from shared.execution.artifacts import (
    save_run_artifacts,
    load_run_profile,
)

__all__ = [
    "ExecutionDepth",
    "ExecutionProfile",
    "QUICK_PROFILE",
    "STANDARD_PROFILE",
    "DEEP_PROFILE",
    "DEPTH_PROFILES",
    "get_profile",
    "DepthSelectionSource",
    "DEPTH_ALIAS_MAP",
    "normalize_depth",
    "validate_depth_conflict",
    "BudgetState",
    "TokenMeasurementStatus",
    "ExecutionReceipt",
    "ExecutionBudget",
    "PreflightError",
    "preflight_check",
    "save_run_artifacts",
    "load_run_profile",
]
