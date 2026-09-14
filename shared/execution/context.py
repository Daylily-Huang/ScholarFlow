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
* resumption that reuses the persisted ledger instead of granting a fresh
  quota -- and since H-19 this is enforced at *construction* time: any
  ``RunContext`` built over a run bundle that already carries a usage ledger
  force-replays it (usage counted, ``run_resumed`` event persisted), an
  unreadable ledger fails explicitly instead of silently starting fresh, and a
  terminated bundle (completed / exhausted / aborted receipt) refuses new
  usage write-backs.

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


class LedgerReplayError(Exception):
    """A persisted usage ledger exists but cannot be replayed (H-19).

    Raised instead of silently starting from a fresh budget when the ledger is
    unreadable, malformed, or belongs to a different run. The exception carries
    structured fields so hosts can surface a machine-readable failure instead
    of a silent quota reset.
    """

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
        ledger_path: Optional[str] = None,
        line_no: Optional[int] = None,
        error_code: str = "LEDGER_REPLAY_FAILED",
    ):
        super().__init__(message)
        self.run_id = run_id
        self.ledger_path = ledger_path
        self.line_no = line_no
        self.error_code = error_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self),
            "error_code": self.error_code,
            "run_id": self.run_id,
            "ledger_path": self.ledger_path,
            "line_no": self.line_no,
        }


class RunTerminatedError(Exception):
    """New usage was offered to an already terminated run bundle (H-19).

    Writing usage back into a run whose receipt already closed it would create
    a mixed ledger/receipt snapshot (contract violation), so the write-back is
    refused with a structured error. Start a new run (new ``run_id``) instead.
    """

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
        terminal_status: Optional[str] = None,
    ):
        super().__init__(message)
        self.run_id = run_id
        self.terminal_status = terminal_status
        self.error_code = "RUN_TERMINATED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self),
            "error_code": self.error_code,
            "run_id": self.run_id,
            "terminal_status": self.terminal_status,
        }


#: Receipt statuses that terminate a run bundle (H-19). "partial" without an
#: exhaustion stop reason is deliberately *not* terminal: a run closed with
#: outstanding work is exactly what ``RunContext.resume`` continues.
_TERMINAL_RECEIPT_STATUSES = {
    "completed": "COMPLETED",
    "failed": "ABORTED",
}

#: Stop reasons that mark a budget-exhausted (therefore terminated) run even
#: when the receipt status is "partial".
_EXHAUSTION_STOP_REASONS = frozenset(
    {"request_limit", "active_time_limit", "token_ceiling_reached", "budget_exhausted"}
)

#: Ledger event kinds that carry quota semantics. A usage event from a foreign
#: run makes the bundle's budget ambiguous and is refused on replay; foreign
#: lifecycle bookkeeping (stage plans, seals, ...) is tolerated and skipped.
_USAGE_EVENT_KINDS = frozenset(
    {"model_request", "tokens", "database_request", "candidates_consumed"}
)


def terminal_reason_from_receipt(receipt: Dict[str, Any]) -> Optional[str]:
    """Map a persisted execution receipt to a terminal label (H-19).

    Returns ``"COMPLETED"``, ``"EXHAUSTED"`` or ``"ABORTED"`` when the receipt
    closes the run bundle, else ``None`` (still resumable / not finalised).
    """
    status = str(receipt.get("status") or "").strip().lower()
    if status in _TERMINAL_RECEIPT_STATUSES:
        return _TERMINAL_RECEIPT_STATUSES[status]
    stop_reason = receipt.get("stop_reason")
    if isinstance(stop_reason, str) and stop_reason.strip().lower() in _EXHAUSTION_STOP_REASONS:
        return "EXHAUSTED"
    return None


class StageKind(str, Enum):
    #: Ordered as the canonical pipeline; RESEARCH_DEBATE is the
    #: idea-development stage that sits beside (not after) the literature stages.
    DISCOVERY = "discovery"
    EXTRACTION = "extraction"
    SYNTHESIS = "synthesis"
    RESEARCH_DEBATE = "research-debate"


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
    #: research-debate 的阶段计划只用**既有** budget/capabilities 字段表述，
    #: 因此无需改动 `execution_profile.schema.json`（其 budgets/capabilities
    #: 都是 additionalProperties:false）。会话自身的轮次/评审批次/事件上限由
    #: session.execution.budget 单独承载（见 references/convergence_and_recovery.md §7）。
    #: 只列**本运行配置真正携带**且与会话相关的字段。会话自身的轮次/评审批次/事件上限
    #: 属于 `session.execution.budget`（见 references/convergence_and_recovery.md §7），
    #: 不在 run 级信封里，故此处不列——避免计划里出现永远不生效的装饰性字段。
    StageKind.RESEARCH_DEBATE: (
        "max_active_seconds",
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
        #: The debate session's own round / review-batch / event caps live in
        #: `session.execution.budget`; the run-level envelope only bounds active
        #: time, which the debate runtime does enforce.
        StageKind.RESEARCH_DEBATE: {"max_active_seconds"},
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
        # H-19: constructing over an existing run bundle must never hand out a
        # fresh budget. A fresh/empty directory behaves exactly as before; a
        # directory that already carries a usage ledger is always replayed and
        # marked resumed, and a terminated bundle refuses new usage write-backs.
        # ------------------------------------------------------------------
        self._replayed_from_ledger = False
        self._terminal_reason = self._detect_terminal_reason()
        if self._ledger_has_content():
            self._replay_ledger()
            self._replayed_from_ledger = True
            self._resumed = True
            self.record_event("run_resumed", {"run_id": self.config.run_id})

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
        ledger, so restarting a run cannot reset consumption. Since H-19 the
        constructor itself force-replays any existing ledger, so this method
        only keeps the explicit resume contract: the ``run_id`` is checked
        against the persisted bundle and the ``run_resumed`` event is recorded
        exactly once (also when the bundle had no ledger yet).
        """
        config = RunExecutionConfig.load(run_dir)
        if run_id is not None and run_id != config.run_id:
            raise PreflightError(
                "Cannot resume run %r from a bundle belonging to %r" % (run_id, config.run_id)
            )
        context = cls(config, run_dir=run_dir)
        context._resumed = True
        if not context._replayed_from_ledger:
            context.record_event("run_resumed", {"run_id": config.run_id})
        return context

    # ------------------------------------------------------------------
    # H-19: ledger replay / termination guards
    # ------------------------------------------------------------------
    @property
    def resumed(self) -> bool:
        """Whether this context replayed a persisted usage ledger (H-19)."""
        return self._resumed

    @property
    def terminal_reason(self) -> Optional[str]:
        """Terminal label (COMPLETED / EXHAUSTED / ABORTED) of the run bundle."""
        return self._terminal_reason

    def _ledger_has_content(self) -> bool:
        """Whether the run bundle already carries a non-empty usage ledger."""
        path = self._ledger_path()
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return any(line.strip() for line in handle)
        except (OSError, ValueError):
            # Unreadable ledger: route into the forced replay path, which
            # surfaces the failure as a structured LedgerReplayError instead of
            # silently continuing from a fresh budget (H-19).
            return True

    def _detect_terminal_reason(self) -> Optional[str]:
        """Detect from the persisted receipt whether the run bundle is closed."""
        if not self.run_dir:
            return None
        receipt_path = os.path.join(self.run_dir, "execution_receipt.json")
        if not os.path.exists(receipt_path):
            return None
        try:
            with open(receipt_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            # An unreadable receipt cannot close the bundle; ledger integrity
            # is enforced independently by the replay path.
            return None
        if not isinstance(payload, dict):
            return None
        return terminal_reason_from_receipt(payload)

    def _assert_run_accepts_usage(self) -> None:
        """Refuse new usage write-backs into a terminated run bundle (H-19)."""
        if self._terminal_reason:
            raise RunTerminatedError(
                "Run %r is already terminated (%s); new usage must not be written "
                "into its ledger. Start a new run with a fresh run_id instead."
                % (self.config.run_id, self._terminal_reason),
                run_id=self.config.run_id,
                terminal_status=self._terminal_reason,
            )

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
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError as exc:
                        raise LedgerReplayError(
                            "usage ledger %s line %d is not valid JSON; refusing to "
                            "silently start from a fresh budget (H-19)" % (path, line_no),
                            run_id=self.config.run_id,
                            ledger_path=path,
                            line_no=line_no,
                        ) from exc
                    if not isinstance(event, dict):
                        raise LedgerReplayError(
                            "usage ledger %s line %d is not a JSON object; refusing to "
                            "silently start from a fresh budget (H-19)" % (path, line_no),
                            run_id=self.config.run_id,
                            ledger_path=path,
                            line_no=line_no,
                        )
                    event_run_id = event.get("run_id")
                    if event_run_id and event_run_id != self.config.run_id:
                        if event.get("event") in _USAGE_EVENT_KINDS:
                            raise LedgerReplayError(
                                "usage ledger %s carries quota usage of run %r, not %r; "
                                "resource authorisation never transfers across runs (H-19)"
                                % (path, event_run_id, self.config.run_id),
                                run_id=self.config.run_id,
                                ledger_path=path,
                                line_no=line_no,
                                error_code="LEDGER_RUN_ID_MISMATCH",
                            )
                        # Foreign lifecycle bookkeeping: tolerated (bundles may
                        # legitimately share a directory timeline), never applied.
                        continue
                    try:
                        kind = event.get("event")
                        if kind == "model_request":
                            self.budget.requests_bucket.used += int(event.get("count", 1))
                        elif kind == "tokens":
                            tokens = event.get("tokens")
                            if tokens is None:
                                self.budget._token_unobserved_calls += 1
                            else:
                                self.budget.tokens_bucket.used += int(tokens)
                                self.budget.measured_tokens = (
                                    self.budget.measured_tokens or 0
                                ) + int(tokens)
                                self.budget._token_observed_calls += 1
                        elif kind == "database_request":
                            self.database_requests += int(event.get("count", 1))
                        elif kind == "candidates_consumed":
                            self.candidates_processed += int(event.get("granted", 0))
                        elif kind == "pending_work":
                            self.budget.record_pending_work(str(event.get("item")))
                        elif kind == "scope_progress":
                            self.budget.record_scope_progress(str(event.get("item")))
                    except (TypeError, ValueError) as exc:
                        raise LedgerReplayError(
                            "usage ledger %s line %d carries a non-integer usage "
                            "value; refusing to replay it (H-19)" % (path, line_no),
                            run_id=self.config.run_id,
                            ledger_path=path,
                            line_no=line_no,
                        ) from exc
        except (OSError, ValueError) as exc:
            # LedgerReplayError raised above is neither OSError nor ValueError
            # and propagates unchanged; this catch handles unreadable/undecodable
            # ledger files (H-19).
            raise LedgerReplayError(
                "usage ledger %s exists but cannot be read; refusing to silently "
                "start from a fresh budget (H-19): %s" % (path, exc),
                run_id=self.config.run_id,
                ledger_path=path,
            ) from exc
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
        self._assert_run_accepts_usage()
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
        self._assert_run_accepts_usage()
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
        self._assert_run_accepts_usage()
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
            # H-19: once this context has closed its own bundle, further usage
            # on the same instance must not be written back either.
            self._terminal_reason = (
                terminal_reason_from_receipt(receipt.to_dict()) or self._terminal_reason
            )

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
