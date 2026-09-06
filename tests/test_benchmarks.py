# -*- coding: utf-8 -*-
"""
test_benchmarks.py
------------------
Automated test confirming that ScholarFlow scientific benchmark suite passes.
"""

import unittest
from pathlib import Path

try:
    import helpers
except ImportError:
    from tests import helpers

import sys
REPO_ROOT = helpers.REPO_ROOT
sys.path.insert(0, str(REPO_ROOT / "benchmarks"))

from run_benchmarks import (
    run_all_benchmarks,
    evaluate_extraction_benchmark,
    evaluate_claim_verification_benchmark,
    evaluate_claim_relation_alignment_benchmark,
    evaluate_synthesis_benchmark,
)


class TestScholarFlowBenchmarks(unittest.TestCase):
    """Ensure benchmarks pass and scientific metrics meet thresholds."""

    def test_extraction_benchmark(self):
        res = evaluate_extraction_benchmark()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["nr_accuracy"], 1.0)
        self.assertGreaterEqual(res["field_precision"], 0.95)

    def test_claim_verification_benchmark(self):
        res = evaluate_claim_verification_benchmark()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["false_support_rate"], 0.0, "False-support rate must be 0.0%")
        self.assertGreaterEqual(res["accuracy"], 0.9)

    def test_claim_relation_alignment_benchmark(self):
        res = evaluate_claim_relation_alignment_benchmark()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["false_relation_rate"], 0.0, "False-relation rate must be 0.0%")
        self.assertEqual(res["unsupported_predicate_insertion_rate"], 0.0, "Predicate insertion rate must be 0.0%")

    def test_synthesis_benchmark(self):
        res = evaluate_synthesis_benchmark()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["calibration_rate"], 1.0)

    def test_run_all_benchmarks_exit_code(self):
        code = run_all_benchmarks(output_format="json")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
