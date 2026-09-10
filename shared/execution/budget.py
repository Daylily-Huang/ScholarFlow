"""ScholarFlow Execution Budget & Ledger Engine (RFC-014 / P2-02).

Manages multi-resource tracking (active time, model requests, tokens, candidates),
atomic reservation for concurrent workflows, lifecycle-safe settlement, honest
token reporting, and partial completion receipts upon exhaustion.

Design notes for the review defects this module now closes:

* **R09** -- token-completeness state is derived from *counts* of observed and
  unobserved calls, never from whichever enum value happened to be set last.
* **R10** -- reservations have a ``pending -> settled/released`` lifecycle, so a
  repeated settlement is idempotent, an unknown id is rejected, settling after a
  ceiling breach is detected immediately, and a receipt with outstanding work is
  never reported as ``completed``.

Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

import time
import uuid
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BudgetState(str, Enum):
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"          # >= 80% used
    EXHAUSTED = "EXHAUSTED"      # Reached ceiling, no new substantive batches allowed
    PARTIAL = "PARTIAL"          # Gracefully finished with partial output


class TokenMeasurementStatus(str, Enum):
    AVAILABLE = "available"      # Exact usage measured for every executed call
    PARTIAL = "partial"          # Some executed calls lacked usage metrics
    UNAVAILABLE = "unavailable"  # Host environment does not report token metrics


class ReservationState(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"
    RELEASED = "released"


class BudgetError(Exception):
    """Raised when the budget ledger is used incorrectly (R10)."""


@dataclass
class ResourceBucket:
    name: str
    limit: Optional[int]
    used: int = 0
    reserved: int = 0
    closing_reserve: int = 0         # Reserved specifically for clean shutdown/receipt generation

    @property
    def remaining(self) -> Optional[int]:
        if self.limit is None:
            return None
        return max(0, self.limit - self.used - self.reserved - self.closing_reserve)

    @property
    def is_over_limit(self) -> bool:
        """Whether recorded usage already exceeds the ceiling (R10)."""
        if self.limit is None:
            return False
        return (self.used + self.reserved) > self.limit

    def can_allocate(self, amount: int) -> bool:
        if self.limit is None:
            return True
        if self.is_over_limit:
            # Once the ceiling is breached, no further allocation is possible --
            # not even a zero-estimate one (R10).
            return False
        return (self.used + self.reserved + self.closing_reserve + amount) <= self.limit


@dataclass
class Reservation:
    reservation_id: str
    requests: int
    tokens: int
    closing: bool = False
    state: ReservationState = ReservationState.PENDING
    #: Actual settled values, kept separate from the original estimate so a
    #: replay of the same settlement is recognised as idempotent (R10).
    settled_requests: Optional[int] = None
    settled_tokens: Optional[int] = None


@dataclass
class ExecutionReceipt:
    run_id: str
    requested_depth: str
    status: str                                  # "completed", "partial", "failed"
    stop_reason: Optional[str] = None            # None, "active_time_limit", "request_limit", "budget_exhausted"
    usage: Dict[str, Any] = field(default_factory=dict)
    completed_scope: List[str] = field(default_factory=list)
    pending_scope: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "requested_depth": self.requested_depth,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "usage": self.usage,
            "completed_scope": self.completed_scope,
            "pending_scope": self.pending_scope,
            "limitations": self.limitations,
        }


class ExecutionBudget:
    """Thread-safe budget manager coordinating resource consumption and exhaustion handling."""

    def __init__(
        self,
        run_id: str,
        requested_depth: str,
        max_active_seconds: int = 1200,
        max_model_requests: int = 30,
        max_token_ceiling: Optional[int] = None,
        enforcement: str = "best_effort",
    ):
        self.run_id = run_id
        self.requested_depth = requested_depth
        self.max_active_seconds = max_active_seconds
        # Without a hard pre-emption mechanism the only truthful mode is
        # best_effort (R10).
        self.enforcement = "hard" if enforcement == "hard" and self.HARD_ENFORCEMENT_SUPPORTED else "best_effort"
        self.requested_enforcement = enforcement
        self._enforcement_downgraded = self.requested_enforcement != self.enforcement
        self.state = BudgetState.ACTIVE
        self.stop_reason: Optional[str] = None

        self._lock = threading.RLock()
        self._start_wall_time = time.time()
        self._total_user_wait_seconds = 0.0
        self._user_wait_start: Optional[float] = None

        # Resource buckets. The closing reserve keeps enough headroom to write a
        # coherent receipt; it scales with the ceiling so a small budget is not
        # swallowed whole by a fixed constant (R10).
        self.requests_bucket = ResourceBucket(
            "requests",
            limit=max_model_requests,
            closing_reserve=self._closing_reserve_for(max_model_requests),
        )
        self.tokens_bucket = ResourceBucket(
            "tokens",
            limit=max_token_ceiling,
            closing_reserve=self._closing_reserve_for(max_token_ceiling),
        )

        # Reservation lifecycle: reservation_id -> Reservation
        self._reservations: Dict[str, Reservation] = {}

        # Honest token accounting (R09): counts, not last-writer-wins state.
        self._token_observed_calls = 0
        self._token_unobserved_calls = 0
        self.measured_tokens: Optional[int] = None

        self.completed_scope: List[str] = []
        self.pending_scope: List[str] = []
        self.limitations: List[str] = []
        self._closing_reserve_spent = False

    #: The module does not implement pre-emptive cancellation of in-flight work,
    #: so a "hard" ceiling cannot be honoured and is downgraded explicitly (R10).
    HARD_ENFORCEMENT_SUPPORTED = False

    #: Fraction of a ceiling held back so a run can always finalise cleanly.
    CLOSING_RESERVE_FRACTION = 0.1

    @classmethod
    def _closing_reserve_for(cls, limit: Optional[int]) -> int:
        if limit is None or limit <= 0:
            return 0
        # Never hold back so much that no substantive work can start.
        return max(1, min(int(limit * cls.CLOSING_RESERVE_FRACTION), max(0, limit - 1)))

    # -- user-wait accounting ---------------------------------------------
    def pause_for_user_input(self) -> None:
        """Mark start of interactive user wait (excluded from active_seconds)."""
        with self._lock:
            if self._user_wait_start is None:
                self._user_wait_start = time.time()

    def resume_from_user_input(self) -> None:
        """Mark resumption after interactive user wait."""
        with self._lock:
            if self._user_wait_start is not None:
                waited = time.time() - self._user_wait_start
                self._total_user_wait_seconds += waited
                self._user_wait_start = None

    @property
    def wall_seconds(self) -> int:
        return int(time.time() - self._start_wall_time)

    @property
    def active_seconds(self) -> int:
        with self._lock:
            current_pause = (time.time() - self._user_wait_start) if self._user_wait_start else 0.0
            total_pause = self._total_user_wait_seconds + current_pause
            return max(0, int(self.wall_seconds - total_pause))

    # -- state ------------------------------------------------------------
    def _refresh_state(self) -> None:
        """Recompute derived state from actual usage. Caller holds the lock."""
        if self.state in (BudgetState.EXHAUSTED, BudgetState.PARTIAL):
            return
        if self.requests_bucket.is_over_limit or self.tokens_bucket.is_over_limit:
            self.state = BudgetState.EXHAUSTED
            if self.stop_reason is None:
                self.stop_reason = (
                    "request_limit" if self.requests_bucket.is_over_limit else "token_ceiling_reached"
                )
            return
        used_fraction = 0.0
        for bucket in (self.requests_bucket, self.tokens_bucket):
            if bucket.limit:
                used_fraction = max(used_fraction, (bucket.used + bucket.reserved) / float(bucket.limit))
        if used_fraction >= 0.8:
            self.state = BudgetState.WARNING

    def check_active_time(self) -> bool:
        """Check if active seconds exceeded the budget limit."""
        if self.active_seconds >= self.max_active_seconds:
            with self._lock:
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = "active_time_limit"
            return False
        return True

    @property
    def is_exhausted(self) -> bool:
        return self.state in (BudgetState.EXHAUSTED, BudgetState.PARTIAL)

    # -- reservations -----------------------------------------------------
    def reserve(
        self,
        requests: int = 1,
        estimated_tokens: int = 0,
        closing: bool = False,
    ) -> Optional[str]:
        """Atomically reserve resources prior to dispatching a task.

        Args:
            requests: number of model requests this task will consume.
            estimated_tokens: soft token estimate; ``0`` still respects an
                already-breached ceiling (R10).
            closing: reserve from the dedicated closing allowance instead of the
                ordinary research quota.

        Returns:
            A reservation id, or ``None`` when the budget cannot satisfy it.
        """
        if requests < 0 or estimated_tokens < 0:
            raise BudgetError("Reservation amounts must be non-negative")

        with self._lock:
            if not self.check_active_time():
                return None
            if self.is_exhausted:
                return None

            amount = requests
            if closing:
                if self._closing_reserve_spent:
                    return None
                amount = max(amount, self.requests_bucket.closing_reserve)
            if not self.requests_bucket.can_allocate(amount):
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = self.stop_reason or "request_limit"
                return None
            if estimated_tokens > 0 and not self.tokens_bucket.can_allocate(estimated_tokens):
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = self.stop_reason or "token_ceiling_reached"
                return None

            res_id = str(uuid.uuid4())
            reservation = Reservation(
                reservation_id=res_id,
                requests=amount,
                tokens=estimated_tokens,
                closing=closing,
            )
            self._reservations[res_id] = reservation
            self.requests_bucket.reserved += amount
            if estimated_tokens > 0:
                self.tokens_bucket.reserved += estimated_tokens
            if closing:
                self._closing_reserve_spent = True
            return res_id

    def settle(
        self,
        reservation_id: str,
        actual_requests: Optional[int] = None,
        actual_tokens: Optional[int] = None,
        is_success: bool = True,
    ) -> None:
        """Settle a reservation with actual measured consumption.

        Repeated settlement of the same reservation is idempotent; a conflicting
        second settlement and an unknown id both raise (R10).
        """
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise BudgetError("Unknown reservation id: %s" % reservation_id)

            requests = reservation.requests if actual_requests is None else actual_requests
            if requests < 0 or (actual_tokens is not None and actual_tokens < 0):
                raise BudgetError("Settlement amounts must be non-negative")

            if reservation.state == ReservationState.SETTLED:
                if (
                    reservation.settled_requests == requests
                    and reservation.settled_tokens == actual_tokens
                ):
                    return  # idempotent replay of the same settlement
                raise BudgetError(
                    "Reservation %s was already settled with different values" % reservation_id
                )
            if reservation.state == ReservationState.RELEASED:
                raise BudgetError("Reservation %s was released and cannot be settled" % reservation_id)

            # Release the hold, then record actual usage.
            self.requests_bucket.reserved = max(0, self.requests_bucket.reserved - reservation.requests)
            self.tokens_bucket.reserved = max(0, self.tokens_bucket.reserved - reservation.tokens)

            self.requests_bucket.used += requests

            if actual_tokens is not None:
                self.tokens_bucket.used += actual_tokens
                self.measured_tokens = (self.measured_tokens or 0) + actual_tokens
                self._token_observed_calls += 1
            else:
                # An executed call whose usage was not reported still counts as
                # unobserved; this is what makes the completeness flag stable
                # regardless of call order (R09).
                self._token_unobserved_calls += 1

            reservation.settled_requests = requests
            reservation.settled_tokens = actual_tokens
            reservation.state = ReservationState.SETTLED
            self._refresh_state()

    def release(self, reservation_id: str) -> None:
        """Release an unused reservation."""
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise BudgetError("Unknown reservation id: %s" % reservation_id)
            if reservation.state == ReservationState.SETTLED:
                raise BudgetError("Reservation %s was already settled" % reservation_id)
            if reservation.state == ReservationState.RELEASED:
                return
            self.requests_bucket.reserved = max(0, self.requests_bucket.reserved - reservation.requests)
            self.tokens_bucket.reserved = max(0, self.tokens_bucket.reserved - reservation.tokens)
            reservation.state = ReservationState.RELEASED

    # -- scope tracking ---------------------------------------------------
    def record_scope_progress(self, completed_item: str) -> None:
        with self._lock:
            if completed_item not in self.completed_scope:
                self.completed_scope.append(completed_item)

    def record_pending_work(self, pending_item: str) -> None:
        with self._lock:
            if pending_item not in self.pending_scope:
                self.pending_scope.append(pending_item)

    def clear_pending_work(self, pending_item: str) -> None:
        with self._lock:
            if pending_item in self.pending_scope:
                self.pending_scope.remove(pending_item)

    # -- accounting views -------------------------------------------------
    @property
    def token_measurement(self) -> TokenMeasurementStatus:
        """Completeness of token accounting, derived from observed/unobserved counts (R09)."""
        if self._token_observed_calls == 0 and self._token_unobserved_calls == 0:
            return TokenMeasurementStatus.UNAVAILABLE
        if self._token_unobserved_calls == 0:
            return TokenMeasurementStatus.AVAILABLE
        if self._token_observed_calls == 0:
            return TokenMeasurementStatus.UNAVAILABLE
        return TokenMeasurementStatus.PARTIAL

    @property
    def observed_call_count(self) -> int:
        return self._token_observed_calls

    @property
    def unobserved_call_count(self) -> int:
        return self._token_unobserved_calls

    @property
    def has_outstanding_reservations(self) -> bool:
        return any(r.state == ReservationState.PENDING for r in self._reservations.values())

    # -- receipt ----------------------------------------------------------
    def mark_partial(self, reason: str = "budget_exhausted") -> None:
        """Explicitly declare that the run finished with partial output."""
        with self._lock:
            self.state = BudgetState.PARTIAL
            self.stop_reason = self.stop_reason or reason

    def generate_receipt(self) -> ExecutionReceipt:
        """Generate the final truthful execution receipt (T14, T15 / R09, R10)."""
        with self._lock:
            act_sec = self.active_seconds

            # Completion is a scheduling fact, not an inference from "we did not
            # run out of budget" (R10).
            outstanding = self.has_outstanding_reservations
            if self.state == BudgetState.EXHAUSTED or outstanding or self.pending_scope:
                status = "partial"
            else:
                status = "completed"

            measurement = self.token_measurement
            usage_dict = {
                "tokens": self.measured_tokens,
                "token_measurement": measurement.value,
                "observed_model_calls": self._token_observed_calls,
                "unobserved_model_calls": self._token_unobserved_calls,
                "active_seconds": act_sec,
                "wall_seconds": self.wall_seconds,
                "model_requests": self.requests_bucket.used,
                "outstanding_reservations": sum(
                    1 for r in self._reservations.values() if r.state == ReservationState.PENDING
                ),
            }

            limitations = list(self.limitations)
            if measurement == TokenMeasurementStatus.UNAVAILABLE:
                limitations.append("宿主环境未提供可观测的模型Token用量")
            elif measurement == TokenMeasurementStatus.PARTIAL:
                limitations.append(
                    "部分模型调用未返回精确Token用量（已观测 %d 次 / 未观测 %d 次）；"
                    "报告的 Token 数为已观测下界，不等于整次运行总量"
                    % (self._token_observed_calls, self._token_unobserved_calls)
                )
            if self.measured_tokens is not None and measurement != TokenMeasurementStatus.AVAILABLE:
                limitations.append("Token 合计为已观测调用的下界，不得作为整次运行总量使用")
            if self._enforcement_downgraded:
                limitations.append(
                    "请求的 hard 预算约束不受支持，已降级为 best_effort 并在回执中说明"
                )
            if outstanding:
                limitations.append("存在未结算的预算预留，本回执按部分完成处理")
            for item in self.pending_scope:
                limitations.append("仍有未完成工作：%s" % item)

            return ExecutionReceipt(
                run_id=self.run_id,
                requested_depth=self.requested_depth,
                status=status,
                stop_reason=self.stop_reason,
                usage=usage_dict,
                completed_scope=list(self.completed_scope),
                pending_scope=list(self.pending_scope),
                limitations=limitations,
            )
