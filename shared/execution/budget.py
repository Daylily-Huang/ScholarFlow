"""ScholarFlow Execution Budget & Ledger Engine (RFC-014 / P2-02).

Manages multi-resource tracking (active time, model requests, tokens, candidates),
atomic reservation for concurrent workflows, state-machine transitions,
honest token reporting, and partial completion receipts upon exhaustion.
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
    AVAILABLE = "available"          # Exact usage measured from host API response
    PARTIAL = "partial"              # Some requests lacked usage metrics
    UNAVAILABLE = "unavailable"      # Host environment does not report token metrics


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

    def can_allocate(self, amount: int) -> bool:
        if self.limit is None:
            return True
        return (self.used + self.reserved + self.closing_reserve + amount) <= self.limit


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
        self.enforcement = enforcement
        self.state = BudgetState.ACTIVE
        self.stop_reason: Optional[str] = None

        self._lock = threading.RLock()
        self._start_wall_time = time.time()
        self._total_user_wait_seconds = 0.0
        self._user_wait_start: Optional[float] = None

        # Resource buckets
        self.requests_bucket = ResourceBucket("requests", limit=max_model_requests, closing_reserve=1)
        self.tokens_bucket = ResourceBucket("tokens", limit=max_token_ceiling, closing_reserve=1000)

        # Active reservations: reservation_id -> (bucket_name, amount)
        self._reservations: Dict[str, Dict[str, int]] = {}

        # Usage ledger & scopes
        self.token_measurement: TokenMeasurementStatus = TokenMeasurementStatus.UNAVAILABLE
        self.measured_tokens: Optional[int] = None
        self.completed_scope: List[str] = []
        self.pending_scope: List[str] = []
        self.limitations: List[str] = []

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

    def check_active_time(self) -> bool:
        """Check if active seconds exceeded the budget limit."""
        if self.active_seconds >= self.max_active_seconds:
            with self._lock:
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = "active_time_limit"
            return False
        return True

    def reserve(self, requests: int = 1, estimated_tokens: int = 0) -> Optional[str]:
        """Atomically reserve resources prior to dispatching a task (T13).

        Returns:
            reservation_id string if successful, None if insufficient budget.
        """
        with self._lock:
            if not self.check_active_time():
                return None

            if not self.requests_bucket.can_allocate(requests):
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = "request_limit"
                return None

            if estimated_tokens > 0 and not self.tokens_bucket.can_allocate(estimated_tokens):
                self.state = BudgetState.EXHAUSTED
                self.stop_reason = "token_ceiling_reached"
                return None

            res_id = str(uuid.uuid4())
            self.requests_bucket.reserved += requests
            if estimated_tokens > 0:
                self.tokens_bucket.reserved += estimated_tokens

            self._reservations[res_id] = {
                "requests": requests,
                "tokens": estimated_tokens,
            }
            return res_id

    def settle(
        self,
        reservation_id: str,
        actual_requests: int = 1,
        actual_tokens: Optional[int] = None,
        is_success: bool = True,
    ) -> None:
        """Settle a prior reservation with actual measured resource consumption."""
        with self._lock:
            res = self._reservations.pop(reservation_id, None)
            if res:
                self.requests_bucket.reserved = max(0, self.requests_bucket.reserved - res.get("requests", 0))
                self.tokens_bucket.reserved = max(0, self.tokens_bucket.reserved - res.get("tokens", 0))

            # Record actual requests used (failed retries are also accounted for, per manual 9.2)
            self.requests_bucket.used += actual_requests

            # Record token usage honestly (T15)
            if actual_tokens is not None:
                self.tokens_bucket.used += actual_tokens
                if self.measured_tokens is None:
                    self.measured_tokens = 0
                self.measured_tokens += actual_tokens
                if self.token_measurement == TokenMeasurementStatus.UNAVAILABLE:
                    self.token_measurement = TokenMeasurementStatus.AVAILABLE
            else:
                if self.token_measurement == TokenMeasurementStatus.AVAILABLE:
                    self.token_measurement = TokenMeasurementStatus.PARTIAL

    def release(self, reservation_id: str) -> None:
        """Release an unused reservation."""
        with self._lock:
            res = self._reservations.pop(reservation_id, None)
            if res:
                self.requests_bucket.reserved = max(0, self.requests_bucket.reserved - res.get("requests", 0))
                self.tokens_bucket.reserved = max(0, self.tokens_bucket.reserved - res.get("tokens", 0))

    def record_scope_progress(self, completed_item: str) -> None:
        with self._lock:
            if completed_item not in self.completed_scope:
                self.completed_scope.append(completed_item)

    def record_pending_work(self, pending_item: str) -> None:
        with self._lock:
            if pending_item not in self.pending_scope:
                self.pending_scope.append(pending_item)

    def generate_receipt(self) -> ExecutionReceipt:
        """Generate final truthful execution receipt (T14, T15)."""
        with self._lock:
            act_sec = self.active_seconds
            status = "partial" if self.state in (BudgetState.EXHAUSTED, BudgetState.PARTIAL) else "completed"

            usage_dict = {
                "tokens": self.measured_tokens,
                "token_measurement": self.token_measurement.value,
                "active_seconds": act_sec,
                "wall_seconds": self.wall_seconds,
                "model_requests": self.requests_bucket.used,
            }

            limitations = list(self.limitations)
            if self.token_measurement == TokenMeasurementStatus.UNAVAILABLE:
                limitations.append("宿主环境未提供可观测的模型Token用量")
            elif self.token_measurement == TokenMeasurementStatus.PARTIAL:
                limitations.append("部分模型调用未返回精确Token用量")

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
