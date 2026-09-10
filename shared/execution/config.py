"""ScholarFlow Run Execution Configuration (R04 canonical data contract).

Two concepts were conflated before this module existed:

* ``ExecutionProfile`` -- an **immutable tier preset** (quick/standard/deep).
  It answers "what is the ceiling for this tier?".
* ``RunExecutionConfig`` -- a **confirmed configuration for one run**.
  It answers "what did this specific run get authorised to do, by whom,
  and for which stage of the pipeline?".

Keeping them apart fixes the R04 defects: a preset can no longer be saved as if
it were a confirmed run configuration, the serialisation round-trips exactly,
and what is written to ``runs/<run_id>/execution_profile.json`` validates
against ``schemas/execution_profile.schema.json``.

Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from shared.execution.profiles import ExecutionDepth, ExecutionProfile, get_profile
from shared.execution.selection import DepthSelectionSource, normalize_depth

#: Canonical version tags for the saved run configuration.
RUN_CONFIG_SCHEMA_VERSION = "1.0"
RUN_CONFIG_PROFILE_VERSION = "depth-v1"

#: Selection states a run configuration may carry. Only ``confirmed`` may unlock
#: substantive execution; the others are recorded for auditability only.
SELECTION_STATUSES = ("confirmed", "pending", "rejected")

#: Pipeline stages a configuration can authorise.
PIPELINE_STAGES = ("discovery", "extraction", "synthesis", "full_pipeline")


class StageScope(str, Enum):
    """How far a confirmed configuration reaches."""

    STAGE = "stage"            # a single skill's stage
    PIPELINE = "pipeline"      # the whole Discovery -> Extraction -> Synthesis run


@dataclass
class SelectionRecord:
    """Auditable record of how a run's depth was chosen (R04/R07)."""

    status: str = "pending"
    source: str = DepthSelectionSource.INTERACTIVE_CONFIRMED.value
    scope: str = StageScope.PIPELINE.value
    selected_value: Optional[str] = None
    confirmed_by: str = ""
    confirmed_at: Optional[str] = None
    intent: str = ""
    reason: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "scope": self.scope,
            "selected_value": self.selected_value,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "intent": self.intent,
            "reason": self.reason,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelectionRecord":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in allowed})

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed" and bool(self.selected_value)


@dataclass
class RunBudget:
    """The concrete budget envelope in force for one run."""

    max_search_candidates: int
    snowball_rounds: int = 0
    concept_expansion_rounds: int = 0
    extraction_unit_limit: int = 1
    max_active_seconds: int = 1200
    max_model_requests: int = 30
    max_token_ceiling: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_search_candidates": self.max_search_candidates,
            "snowball_rounds": self.snowball_rounds,
            "concept_expansion_rounds": self.concept_expansion_rounds,
            "extraction_unit_limit": self.extraction_unit_limit,
            "max_active_seconds": self.max_active_seconds,
            "max_model_requests": self.max_model_requests,
            "max_token_ceiling": self.max_token_ceiling,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunBudget":
        if not isinstance(data, dict):
            raise ValueError("budgets must be an object")
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in allowed}
        missing = [
            name
            for name in ("max_search_candidates",)
            if name not in filtered
        ]
        if missing:
            raise ValueError("budgets is missing required field(s): %s" % ", ".join(missing))
        return cls(**filtered)

    @classmethod
    def from_profile(cls, profile: ExecutionProfile) -> "RunBudget":
        return cls(
            max_search_candidates=profile.max_search_candidates,
            snowball_rounds=profile.snowball_rounds,
            concept_expansion_rounds=profile.concept_expansion_rounds,
            extraction_unit_limit=profile.extraction_unit_limit,
            max_active_seconds=profile.max_active_seconds,
            max_model_requests=profile.max_model_requests,
            max_token_ceiling=profile.max_token_ceiling,
        )


@dataclass
class RunCapabilities:
    """Methodological capability switches granted to a run."""

    ocr_scan_policy: str = "essential_tables_only"
    figure_table_verification: str = "sample_crosscheck"
    cross_validation_budget: int = 1
    spot_check_rate: float = 0.1
    devils_advocate_mode: str = "standard"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ocr_scan_policy": self.ocr_scan_policy,
            "figure_table_verification": self.figure_table_verification,
            "cross_validation_budget": self.cross_validation_budget,
            "spot_check_rate": self.spot_check_rate,
            "devils_advocate_mode": self.devils_advocate_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunCapabilities":
        if data is not None and not isinstance(data, dict):
            raise ValueError("capabilities must be an object")
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in allowed})

    @classmethod
    def from_profile(cls, profile: ExecutionProfile) -> "RunCapabilities":
        return cls(
            ocr_scan_policy=profile.ocr_scan_policy,
            figure_table_verification=profile.figure_table_verification,
            cross_validation_budget=profile.cross_validation_budget,
            spot_check_rate=profile.spot_check_rate,
            devils_advocate_mode=profile.devils_advocate_mode,
        )


@dataclass
class RunExecutionConfig:
    """Canonical, serialisable configuration for one authorised research run.

    This is the *only* object that may be persisted to
    ``runs/<run_id>/execution_profile.json``.
    """

    run_id: str
    depth: ExecutionDepth
    selection: SelectionRecord = field(default_factory=SelectionRecord)
    budgets: RunBudget = field(default_factory=lambda: RunBudget.from_profile(get_profile(ExecutionDepth.STANDARD)))
    capabilities: RunCapabilities = field(
        default_factory=lambda: RunCapabilities.from_profile(get_profile(ExecutionDepth.STANDARD))
    )
    stages: List[str] = field(default_factory=lambda: list(PIPELINE_STAGES))
    interaction_mode: str = "interactive"
    enforcement: str = "best_effort"
    schema_version: str = RUN_CONFIG_SCHEMA_VERSION
    profile_version: str = RUN_CONFIG_PROFILE_VERSION
    name_zh: str = ""
    created_at: str = ""
    updated_at: str = ""
    parent_run_id: Optional[str] = None
    limitations: List[str] = field(default_factory=list)

    # -- construction ------------------------------------------------------
    @classmethod
    def new_run_id(cls) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return "sf-run-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    @classmethod
    def from_profile(
        cls,
        profile: ExecutionProfile,
        run_id: Optional[str] = None,
        selection: Optional[SelectionRecord] = None,
        stages: Optional[List[str]] = None,
        interaction_mode: str = "interactive",
    ) -> "RunExecutionConfig":
        """Build a run configuration from a tier preset.

        Note that this still requires an explicit ``selection``: converting a
        preset into a run configuration does not itself confirm anything.
        """
        now = datetime.now(timezone.utc).isoformat()
        from shared.execution.selection import validate_depth_conflict

        depth = profile.depth
        record = selection or SelectionRecord(
            status="pending",
            source=DepthSelectionSource.INTERACTIVE_CONFIRMED.value,
            selected_value=depth.value,
        )
        return cls(
            run_id=run_id or cls.new_run_id(),
            depth=depth,
            selection=record,
            budgets=RunBudget.from_profile(profile),
            capabilities=RunCapabilities.from_profile(profile),
            stages=list(stages or PIPELINE_STAGES),
            interaction_mode=interaction_mode,
            enforcement=profile.enforcement if profile.enforcement in ("best_effort", "hard") else "best_effort",
            name_zh=profile.name_zh,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def confirmed(
        cls,
        depth: Any,
        source: str = DepthSelectionSource.INTERACTIVE_CONFIRMED.value,
        run_id: Optional[str] = None,
        confirmed_by: str = "user",
        scope: str = StageScope.PIPELINE.value,
        stages: Optional[List[str]] = None,
        intent: str = "DECISION",
        reason: str = "explicit_user_selection",
        interaction_mode: str = "interactive",
    ) -> "RunExecutionConfig":
        """Create a *confirmed* run configuration for a validated depth."""
        from shared.execution.selection import normalize_depth

        normalized = depth if isinstance(depth, ExecutionDepth) else normalize_depth(depth)
        if normalized is None:
            raise ValueError("Invalid execution depth: %r" % (depth,))
        profile = get_profile(normalized)
        now = datetime.now(timezone.utc).isoformat()
        record = SelectionRecord(
            status="confirmed",
            source=source,
            scope=scope,
            selected_value=normalized.value,
            confirmed_by=confirmed_by,
            confirmed_at=now,
            intent=intent,
            reason=reason,
        )
        config = cls.from_profile(
            profile,
            run_id=run_id,
            selection=record,
            stages=stages,
            interaction_mode=interaction_mode,
        )
        return config

    # -- validation --------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of contract violations; empty means the config is valid."""
        problems: List[str] = []
        if not self.run_id or not str(self.run_id).strip():
            problems.append("run_id is required")
        if not isinstance(self.depth, ExecutionDepth):
            problems.append("depth must be an ExecutionDepth")
        if self.selection.status not in SELECTION_STATUSES:
            problems.append("selection.status must be one of %s" % (SELECTION_STATUSES,))
        if self.selection.status == "confirmed" and not self.selection.selected_value:
            problems.append("a confirmed selection must record selected_value")
        if self.selection.selected_value:
            normalized = normalize_depth(self.selection.selected_value)
            if normalized is None:
                problems.append("selection.selected_value must be a valid depth")
            elif isinstance(self.depth, ExecutionDepth) and normalized != self.depth:
                problems.append("selection.selected_value must match depth")
        if self.enforcement not in ("best_effort", "hard"):
            problems.append("enforcement must be 'best_effort' or 'hard'")
        for stage in self.stages:
            if stage not in PIPELINE_STAGES:
                problems.append("unknown stage %r" % (stage,))
        if self.budgets.max_search_candidates < 1:
            problems.append("budgets.max_search_candidates must be >= 1")
        if self.budgets.extraction_unit_limit < 1:
            problems.append("budgets.extraction_unit_limit must be >= 1")
        if self.budgets.max_active_seconds < 1:
            problems.append("budgets.max_active_seconds must be >= 1")
        if self.budgets.max_model_requests < 1:
            problems.append("budgets.max_model_requests must be >= 1")
        if self.budgets.max_token_ceiling is not None and self.budgets.max_token_ceiling < 1:
            problems.append("budgets.max_token_ceiling must be null or >= 1")
        if not (0.0 <= self.capabilities.spot_check_rate <= 1.0):
            problems.append("capabilities.spot_check_rate must be within [0, 1]")
        return problems

    @property
    def is_confirmed(self) -> bool:
        return self.selection.is_confirmed

    def authorises_stage(self, stage: str) -> bool:
        """Whether this configuration authorises substantive work for ``stage``."""
        return self.is_confirmed and stage in self.stages

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_version": self.profile_version,
            "run_id": self.run_id,
            "depth": self.depth.value,
            "execution_depth": self.depth.value,
            "name_zh": self.name_zh,
            "selection_source": self.selection.source,
            "selection": self.selection.to_dict(),
            "interaction_mode": self.interaction_mode,
            "stages": list(self.stages),
            "budgets": self.budgets.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "enforcement": self.enforcement,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_run_id": self.parent_run_id,
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunExecutionConfig":
        """Rebuild a configuration from its canonical dictionary form.

        Raises:
            ValueError: when required keys are missing or unusable.
        """
        if not isinstance(data, dict):
            raise ValueError("RunExecutionConfig payload must be an object")

        depth_raw = data.get("depth", data.get("execution_depth"))
        depth = depth_raw if isinstance(depth_raw, ExecutionDepth) else normalize_depth(depth_raw)
        if depth is None:
            raise ValueError("execution profile payload has no valid depth")

        if not data.get("run_id"):
            raise ValueError("execution profile payload is missing run_id")
        if not data.get("selection_source"):
            raise ValueError("execution profile payload is missing selection_source")
        if not isinstance(data.get("selection"), dict):
            raise ValueError("execution profile payload is missing the selection record")

        selection = SelectionRecord.from_dict(data.get("selection") or {})
        if not selection.selected_value:
            selection.selected_value = depth.value
        if not selection.source:
            selection.source = data.get("selection_source") or DepthSelectionSource.INTERACTIVE_CONFIRMED.value

        budgets = RunBudget.from_dict(data.get("budgets") or {})
        capabilities = RunCapabilities.from_dict(data.get("capabilities") or {})

        config = cls(
            run_id=data.get("run_id") or "",
            depth=depth,
            selection=selection,
            budgets=budgets,
            capabilities=capabilities,
            stages=list(data.get("stages") or PIPELINE_STAGES),
            interaction_mode=data.get("interaction_mode") or "interactive",
            enforcement=data.get("enforcement") or "best_effort",
            schema_version=data.get("schema_version") or RUN_CONFIG_SCHEMA_VERSION,
            profile_version=data.get("profile_version") or RUN_CONFIG_PROFILE_VERSION,
            name_zh=data.get("name_zh") or get_profile(depth).name_zh,
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            parent_run_id=data.get("parent_run_id"),
            limitations=list(data.get("limitations") or []),
        )
        return config

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "RunExecutionConfig":
        return cls.from_dict(json.loads(text))

    # -- persistence -------------------------------------------------------
    def save(self, run_dir: str, validate: bool = True) -> str:
        """Persist to ``<run_dir>/execution_profile.json`` atomically.

        Validation happens *before* any byte is written, so an invalid
        configuration can never reach disk (R04).
        """
        problems = self.validate() if validate else []
        if problems:
            raise ValueError("Refusing to save an invalid run configuration: %s" % "; ".join(problems))

        os.makedirs(run_dir, exist_ok=True)
        target = os.path.join(run_dir, "execution_profile.json")
        tmp_path = target + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
        os.replace(tmp_path, target)
        return target

    @classmethod
    def load(cls, run_dir_or_file: str, validate: bool = True) -> "RunExecutionConfig":
        path = run_dir_or_file
        if os.path.isdir(path):
            path = os.path.join(path, "execution_profile.json")
        if not os.path.exists(path):
            raise FileNotFoundError("Execution profile not found: %s" % path)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        config = cls.from_dict(data)
        if validate:
            problems = config.validate()
            if problems:
                raise ValueError("Stored run configuration is invalid: %s" % "; ".join(problems))
        return config
