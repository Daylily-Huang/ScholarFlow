"""ScholarFlow Execution Budget & Concurrency Test Suite (RFC-014 / P2-02).

Validates acceptance cases T13, T14, and T15 as specified in
ScholarFlow_统一执行深度接入操作手册.md.
Zero external dependencies (pure Python standard library).
"""

import sys
import time
import threading
import unittest
from pathlib import Path

_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

import helpers  # noqa: F401 (sys.path bootstrap)

from shared.execution.budget import (
    ExecutionBudget,
    BudgetState,
    TokenMeasurementStatus,
    ExecutionReceipt,
)


class TestExecutionBudgetAcceptance(unittest.TestCase):
    """Rigorous acceptance tests matching Section 14 T13-T15."""

    # -------------------------------------------------------------------------
    # T13: 两个并行请求争夺余额 -> 不能同时预留同一份额度
    # -------------------------------------------------------------------------
    def test_T13_concurrent_budget_atomic_reservation(self):
        # Create budget with capacity for exactly 5 model requests
        budget = ExecutionBudget(
            run_id="run-t13-concurrent",
            requested_depth="standard",
            max_model_requests=5,
            max_active_seconds=100,
        )

        results = []
        threads = []

        def worker():
            # Try to reserve 1 request
            res_id = budget.reserve(requests=1)
            if res_id:
                results.append(res_id)
                # Simulate small work
                time.sleep(0.01)
                budget.settle(res_id, actual_requests=1)

        # Launch 10 concurrent threads competing for 5 requests (excluding 1 closing reserve = 4 available)
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Available capacity was 5 - 1 (closing reserve) = 4 requests
        self.assertLessEqual(len(results), 4, f"More tasks reserved than available: {len(results)} > 4")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(budget.requests_bucket.used, len(results))

    # -------------------------------------------------------------------------
    # T14: 预算不足／网络超时 -> partial＋已完成＋待办＋原因
    # -------------------------------------------------------------------------
    def test_T14_budget_exhaustion_generates_partial_receipt(self):
        # Create budget with very small active seconds limit (0s so it triggers immediately)
        budget = ExecutionBudget(
            run_id="run-t14-timeout",
            requested_depth="standard",
            max_active_seconds=0,
            max_model_requests=30,
        )

        budget.record_scope_progress("核心关键词检索 (Q01)")
        budget.record_scope_progress("首批论文元数据下载 (20篇)")
        budget.record_pending_work("双向引文滚雪球追溯")
        budget.record_pending_work("正文表格高危字段核验")

        # Check reservation when time exceeded
        res = budget.reserve(requests=1)
        self.assertIsNone(res)
        self.assertEqual(budget.state, BudgetState.EXHAUSTED)
        self.assertEqual(budget.stop_reason, "active_time_limit")

        receipt = budget.generate_receipt()
        self.assertIsInstance(receipt, ExecutionReceipt)
        self.assertEqual(receipt.status, "partial")
        self.assertEqual(receipt.stop_reason, "active_time_limit")
        self.assertIn("核心关键词检索 (Q01)", receipt.completed_scope)
        self.assertIn("双向引文滚雪球追溯", receipt.pending_scope)
        receipt_dict = receipt.to_dict()
        self.assertEqual(receipt_dict["status"], "partial")
        self.assertEqual(receipt_dict["stop_reason"], "active_time_limit")

    # -------------------------------------------------------------------------
    # T15: 无宿主 usage -> tokens=null，不伪造实测数字
    # -------------------------------------------------------------------------
    def test_T15_host_usage_unavailable_honest_reporting(self):
        budget = ExecutionBudget(
            run_id="run-t15-no-usage",
            requested_depth="standard",
            max_model_requests=10,
            max_active_seconds=300,
        )

        # Reserve and settle requests without providing actual_tokens (host didn't report them)
        res1 = budget.reserve(requests=1)
        self.assertIsNotNone(res1)
        budget.settle(res1, actual_requests=1, actual_tokens=None)

        receipt = budget.generate_receipt()
        self.assertIsNone(receipt.usage["tokens"], "Tokens must be None when host usage is unavailable")
        self.assertEqual(receipt.usage["token_measurement"], "unavailable")
        self.assertTrue(
            any("未提供可观测的模型Token用量" in lim for lim in receipt.limitations),
            "Must explicitly disclose limitation when tokens cannot be measured",
        )


if __name__ == "__main__":
    unittest.main()
