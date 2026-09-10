#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared/execution/context.py
----------------------------
Lightweight run context that carries one confirmed configuration through the
whole Discovery -> Extraction -> Synthesis pipeline (R05).

Before this module existed the budget classes were only ever constructed by
tests: a run could not actually be limited, and the execution-depth fields
(``extraction_unit_limit``, ``devils_advocate_mode``, ``snowball_rounds`` ...)
were declared but never consumed. ``RunContext`` closes that gap without
rewriting any of the underlying research algorithms:

* one confirmed :class:`RunExecutionConfig` and one shared budget per run;
* a phase plan derived from the configuration and consumed by each stage;
* separate counters for model requests and database/HTTP requests;
* a single finalisation path (normal end, error, timeout) that persists the
  usage ledger, receipt and outstanding work;
* resumption that reuses the persisted ledger instead of granting a fresh quota.

Pure Python standard library (zero external runtime dependencies).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .budget import BudgetState, ExecutionBudget, ExecutionReceipt
from .config import RunExecutionConfig
from .preflight import PreflightError, preflight_run_config


class BudgetLimitError(Exception):
    """Raised when the run budget cannot satisfy an additional unit of work."""

    def __init__(self, message: str, stop_reason: Optional[str] = None):
        super().__init__(message)
        self.stop_reason = stop_reason


class StageKind(str, Enum):
    DISCOVERY = "discovery"
    EXTRACTION = "extraction"
    SYNTHESIS = "synthesis"


#: Ledger A phase plan: how each stage is expected to spend the run budget.
_STAGE_PROFILE_FIELDS = {
    StageKind.DISCOVERY: (
        "max_search_candidates",
        "snowball_rounds",
        "concept_expansion_rounds",
        "max_active_seconds",
    ),
    StageKind.EXTRACTION: (
        "extraction_unit_limit",
        "cross_validation_budget",
        "spot_check_rate",
        "figure_table_verification",
        "ocr_scan_policy",
    ),
    StageKind.SYNTHESIS: (
        "cross_validation_budget",
        "devils_advocate_mode",
        "spot_check_rate",
    ),
}


@dataclass
class StagePlan:
    """Executable plan for one stage, derived from the run configuration."""

    stage: str
    settings: Dict[str, Any] = field(default_factory=dict)
    unsupported: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "settings": self.settings,
            "unsupported": list(self.unsupported),
        }


class RunContext:
    """Carries the confirmed configuration, shared budget and artifacts for one run."""

    #: The plan adapter consumes these; anything declared but not honoured is
    #: reported as an explicit capability gap rather than silently ignored (R05).
    HONOURED_SETTINGS = {
        StageKind.DISCOVERY: {
            "max_search_candidates",
            "snowball_rounds",
            "concept_expansion_rounds",
            "max_active_seconds",
        },
        StageKind.EXTRACTION: {"extraction_unit_limit"},
        StageKind.SYNTHESIS: set(),
    }

    #: Capability switches that are recorded in the plan but not enforced by any
    #: code path in this repository -- they stay visible as host-dependent gaps.
    HOST_DEPENDENT_SETTINGS = {
        "cross_validation_budget",
        "spot_check_rate",
        "figure_table_verification",
        "ocr_scan_policy",
        "devils_advocate_mode",
    }

    def __init__(
        self,
        config: RunExecutionConfig,
        run_dir: Optional[str] = None,
        run_id: Optional[str] = None,
        stage: Optional[str] = None,
    ):
        if run_id is not None:
            passed, checked, message = preflight_run_config(
                config, run_id=run_id, stage=stage, allow_unconfirmed=False
            )
            if not passed or checked is None:
                raise PreflightError(message)
            config = checked

        problems = config.validate()
        if problems:
            raise PreflightError("Invalid run configuration: %s" % "; ".join(problems))

        self.config = config
        self.run_dir = run_dir
        self.budget = ExecutionBudget(
            run_id=config.run_id,
            requested_depth=config.depth.value,
            max_active_seconds=config.budgets.max_active_seconds,
            max_model_requests=config.budgets.max_model_requests,
            max_token_ceiling=config.budgets.max_token_ceiling,
            enforcement=config.enforcement,
        )
        #: Database/HTTP requests are counted separately from model requests so
        #: an OpenAlex call is never billed as a model call (R05).
        self.database_requests = 0
        self.events: List[Dict[str, Any]] = []
        self._stage_started: Dict[str, float] = {}
        self._resumed = False
        #: Run-level candidate ceiling consumption (per instance, never shared).
        self.candidates_processed = 0

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        depth: Any,
        run_dir: Optional[str] = None,
        run_id: Optional[str] = None,
        source: str = "INTERACTIVE_CONFIRMED",
        stages: Optional[List[str]] = None,
        interaction_mode: str = "interactive",
    ) -> "RunContext":
        """Create a context from an already-confirmed depth value."""
        config = RunExecutionConfig.confirmed(
            depth,
            source=source,
            run_id=run_id,
            stages=stages,
            interaction_mode=interaction_mode,
        )
        return cls(config, run_dir=run_dir)

    @classmethod
    def resume(cls, run_dir: str, run_id: Optional[str] = None) -> "RunContext":
        """Resume a persisted run without granting a fresh budget (R05).

        The remaining allowance is reconstructed from the persisted usage
        ledger, so restarting a run cannot reset consumption.
        """
        config = RunExecutionConfig.load(run_dir)
        if run_id is not None and run_id != config.run_id:
            raise PreflightError(
                "Cannot resume run %r from a bundle belonging to %r" % (run_id, config.run_id)
            )
        context = cls(config, run_dir=run_dir)
        context._replay_ledger()
        context._resumed = True
        context.record_event("run_resumed", {"run_id": config.run_id})
        return context

    def _ledger_path(self) -> Optional[str]:
        if not self.run_dir:
            return None
        return os.path.join(self.run_dir, "usage_ledger.jsonl")

    def _append_ledger(self, event: Dict[str, Any]) -> None:
        path = self._ledger_path()
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _replay_ledger(self) -> None:
        path = self._ledger_path()
        if not path or not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "model_request":
                    self.budget.requests_bucket.used += int(event.get("count", 1))
                elif kind == "tokens":
                    tokens = event.get("tokens")
                    if tokens is None:
                        self.budget._token_unobserved_calls += 1
                    else:
                        self.budget.tokens_bucket.used += int(tokens)
                        self.budget.measured_tokens = (self.budget.measured_tokens or 0) + int(tokens)
                        self.budget._token_observed_calls += 1
                elif kind == "database_request":
                    self.database_requests += int(event.get("count", 1))
                elif kind == "candidates_consumed":
                    self.candidates_processed += int(event.get("granted", 0))
                elif kind == "pending_work":
                    self.budget.record_pending_work(str(event.get("item")))
                elif kind == "scope_progress":
                    self.budget.record_scope_progress(str(event.get("item")))
        self.budget._refresh_state()

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------
    def record_event(self, event: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry = {
            "event": event,
            "run_id": self.config.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_active_seconds": self.budget.active_seconds,
        }
        if payload:
            entry.update(payload)
        self.events.append(entry)
        self._append_ledger(entry)
        return entry

    # ------------------------------------------------------------------
    # Resource accounting
    # ------------------------------------------------------------------
    def begin_model_request(self, estimated_tokens: int = 0) -> str:
        """Reserve one model request; raises when the budget is exhausted."""
        reservation = self.budget.reserve(requests=1, estimated_tokens=estimated_tokens)
        if reservation is None:
            raise BudgetLimitError(
                "Model request budget exhausted (%s)" % (self.budget.stop_reason or "budget_exhausted"),
                stop_reason=self.budget.stop_reason,
            )
        return reservation

    def end_model_request(
        self,
        reservation_id: str,
        actual_tokens: Optional[int] = None,
        is_success: bool = True,
    ) -> None:
        self.budget.settle(reservation_id, actual_requests=1, actual_tokens=actual_tokens, is_success=is_success)
        self.record_event(
            "model_request",
            {"count": 1, "tokens": actual_tokens, "is_success": is_success},
        )
        self.record_event("tokens", {"tokens": actual_tokens})

    def count_database_request(self, count: int = 1) -> int:
        """Record database/API requests separately from model requests (R05)."""
        self.database_requests += count
        self.record_event("database_request", {"count": count})
        return self.database_requests

    def check_active_time(self) -> None:
        if not self.budget.check_active_time():
            raise BudgetLimitError(
                "Active time budget exhausted (%ss)" % self.config.budgets.max_active_seconds,
                stop_reason="active_time_limit",
            )

    @property
    def remaining_candidates(self) -> int:
        return max(0, self.config.budgets.max_search_candidates - self.candidates_processed)

    def consume_candidates(self, count: int) -> int:
        """Consume up to ``count`` candidate slots from the run-level ceiling.

        Returns the number actually granted; the caller must not process more.
        """
        granted = max(0, min(count, self.remaining_candidates))
        self.candidates_processed += granted
        # The candidate ceiling is a *run-level total*, independent of the
        # per-query limit, so it is deducted here rather than from a bucket.
        self.record_event("candidates_consumed", {"granted": granted, "count": count})
        return granted

    # ------------------------------------------------------------------
    # Stage plans
    # ------------------------------------------------------------------
    def plan_for(self, stage: Any) -> StagePlan:
        """Build the executable plan for a stage from the confirmed configuration."""
        kind = stage if isinstance(stage, StageKind) else StageKind(str(stage))
        budgets = self.config.budgets.to_dict()
        capabilities = self.config.capabilities.to_dict()
        combined = dict(budgets)
        combined.update(capabilities)

        honoured = self.HONOURED_SETTINGS.get(kind, set())
        settings: Dict[str, Any] = {}
        unsupported: List[str] = []
        for name in _STAGE_PROFILE_FIELDS.get(kind, ()):
            if name not in combined:
                continue
            settings[name] = combined[name]
            if name in self.HOST_DEPENDENT_SETTINGS or name not in honoured:
                unsupported.append(name)

        plan = StagePlan(stage=kind.value, settings=settings, unsupported=unsupported)
        self.record_event("stage_plan", plan.to_dict())
        return plan

    def begin_stage(self, stage: Any) -> StagePlan:
        kind = stage if isinstance(stage, StageKind) else StageKind(str(stage))
        if not self.config.authorises_stage(kind.value):
            raise PreflightError(
                "This run configuration does not authorise stage %r (authorised: %s)"
                % (kind.value, ", ".join(self.config.stages))
            )
        self._stage_started[kind.value] = time.time()
        plan = self.plan_for(kind)
        self.record_event("stage_started", {"stage": kind.value})
        return plan

    def complete_stage(self, stage: Any, completed_items: Optional[List[str]] = None) -> None:
        kind = stage if isinstance(stage, StageKind) else StageKind(str(stage))
        started = self._stage_started.pop(kind.value, None)
        for item in completed_items or []:
            self.budget.record_scope_progress(item)
        self.record_event(
            "stage_completed",
            {
                "stage": kind.value,
                "duration_seconds": int(time.time() - started) if started else None,
            },
        )

    def defer_stage_work(self, stage: Any, items: List[str]) -> None:
        kind = stage if isinstance(stage, StageKind) else StageKind(str(stage))
        for item in items:
            self.budget.record_pending_work("%s:%s" % (kind.value, item))
            self.record_event("pending_work", {"item": "%s:%s" % (kind.value, item)})

    # ------------------------------------------------------------------
    # Phase plan for the host agent
    # ------------------------------------------------------------------
    def planned_call_trace(self) -> Dict[str, Any]:
        """A machine-checkable description of what each tier is expected to do.

        Different depths must produce different plans; this is what makes the
        tier settings observable rather than decorative (R05/R11).
        """
        return {
            "run_id": self.config.run_id,
            "depth": self.config.depth.value,
            "config": self.config.to_dict(),
            "stages": {kind.value: self.plan_for(kind).to_dict() for kind in StageKind},
        }

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------
    def finalize(
        self,
        status: Optional[str] = None,
        stop_reason: Optional[str] = None,
        error: Optional[str] = None,
    ) -> ExecutionReceipt:
        """Unified teardown for every outcome (normal, error, timeout).

        Persists the receipt and outstanding work, so a restart can see exactly
        what was and was not finished.
        """
        if error:
            self.record_event("run_failed", {"error": error})
            self.budget.mark_partial("error:" + error)
            self.budget.limitations.append("运行因错误提前结束：%s" % error)
        else:
            self.record_event("run_finalized", {"status": status, "stop_reason": stop_reason})

        if stop_reason:
            self.budget.stop_reason = self.budget.stop_reason or stop_reason

        receipt = self.budget.generate_receipt()
        if status and status != receipt.status:
            receipt.status = status

        if self.run_dir:
            os.makedirs(self.run_dir, exist_ok=True)
            self.config.save(self.run_dir)
            receipt_path = os.path.join(self.run_dir, "execution_receipt.json")
            tmp_path = receipt_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(receipt.to_dict(), handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, receipt_path)

            pending_items = [
                {"stage": self.config.depth.value, "item": item}
                for item in self.budget.pending_scope
            ]
            pending_path = os.path.join(self.run_dir, "pending_work.json")
            with open(pending_path, "w", encoding="utf-8") as handle:
                json.dump(pending_items, handle, indent=2, ensure_ascii=False)

        return receipt

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is BudgetLimitError:
            self.finalize(status="partial", stop_reason=getattr(exc, "stop_reason", None))
            return False
        if exc_type is not None:
            self.finalize(error="%s: %s" % (exc_type.__name__, exc))
            return False
        return False
