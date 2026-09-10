"""ScholarFlow Execution Subsystem (RFC-014 / P2-02).

Provides unified execution depth tiers (quick, standard, deep), budget tracking,
preflight validation, canonical run configuration, and truthful execution receipts.

Two objects matter here and they are deliberately distinct:

* :class:`ExecutionProfile` -- an immutable tier *preset* (a resource ceiling).
* :class:`RunExecutionConfig` -- the auditable configuration of one run.

Only a confirmed ``RunExecutionConfig`` may unlock substantive execution.
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
from shared.execution.config import (
    PIPELINE_STAGES,
    RUN_CONFIG_PROFILE_VERSION,
    RUN_CONFIG_SCHEMA_VERSION,
    SELECTION_STATUSES,
    RunBudget,
    RunCapabilities,
    RunExecutionConfig,
    SelectionRecord,
    StageScope,
)
from shared.execution.budget import (
    BudgetError,
    BudgetState,
    Reservation,
    ReservationState,
    TokenMeasurementStatus,
    ExecutionReceipt,
    ExecutionBudget,
)
from shared.execution.preflight import (
    PreflightError,
    preflight_check,
    preflight_run_config,
)
from shared.execution.context import (
    BudgetLimitError,
    RunContext,
    StageKind,
    StagePlan,
)
from shared.execution.artifacts import (
    RUN_BUNDLE_FILES,
    load_run_artifacts,
    load_run_profile,
    save_run_artifacts,
)

__all__ = [
    # Tier presets
    "ExecutionDepth",
    "ExecutionProfile",
    "QUICK_PROFILE",
    "STANDARD_PROFILE",
    "DEEP_PROFILE",
    "DEPTH_PROFILES",
    "get_profile",
    # Selection
    "DepthSelectionSource",
    "DEPTH_ALIAS_MAP",
    "normalize_depth",
    "validate_depth_conflict",
    # Canonical run configuration
    "RunExecutionConfig",
    "RunBudget",
    "RunCapabilities",
    "SelectionRecord",
    "StageScope",
    "SELECTION_STATUSES",
    "PIPELINE_STAGES",
    "RUN_CONFIG_SCHEMA_VERSION",
    "RUN_CONFIG_PROFILE_VERSION",
    # Budget
    "BudgetError",
    "BudgetState",
    "Reservation",
    "ReservationState",
    "TokenMeasurementStatus",
    "ExecutionReceipt",
    "ExecutionBudget",
    # Preflight
    "PreflightError",
    "preflight_check",
    "preflight_run_config",
    # Run context
    "RunContext",
    "StageKind",
    "StagePlan",
    "BudgetLimitError",
    # Artifacts
    "save_run_artifacts",
    "load_run_profile",
    "load_run_artifacts",
    "RUN_BUNDLE_FILES",
]
