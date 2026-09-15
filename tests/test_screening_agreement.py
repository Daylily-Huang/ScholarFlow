# -*- coding: utf-8 -*-
"""Tests for calculate_screening_agreement.py (PRISMA 2020 Item 8 dual-reviewer kappa)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sys.path bootstrap)

import calculate_screening_agreement as csa  # type: ignore


def _make_map(pairs):
    """pairs: list of (record_id, status) -> reviewer decision map."""
    return {
        rid: {"id": rid, "title": f"Paper {rid}", "status": st,
              "reason_code": "", "reason_detail": "", "confidence_score": None}
        for rid, st in pairs
    }


class TestNormalizeStatus(unittest.TestCase):
    def test_include_variants(self):
        for v in ["Include", "included", "INC", "纳入", "yes", "1"]:
            self.assertEqual(csa.normalize_status(v), "Include")

    def test_exclude_variants(self):
        for v in ["Exclude", "EXCLUDED", "exc", "排除", "no", "0"]:
            self.assertEqual(csa.normalize_status(v), "Exclude")

    def test_explicit_uncertain_variants(self):
        for v in ["Uncertain", "maybe", "borderline", "待定", "存疑", "?"]:
            self.assertEqual(csa.normalize_status(v), "Uncertain")

    def test_unreadable_is_not_uncertain(self):
        """P1（2026-09-15 集群审查）：读不到 ≠ 两方都判待定。

        本条原先断言 `""` / `None` / `"banana"` 一律归一为 `"Uncertain"`——**那正是缺陷
        本身**：它让「一条裁决都没读进来」与「两评阅人都判待定」在产物里完全同形，
        于是逐条对立的两份初筛被判 κ=1.000「Almost Perfect（符合顶级发表标准）」且
        rc=0、零告警。该断言长期为绿，门禁长期为坏。
        """
        for v in ["", "   ", None, "banana", "MAYBE_LATER"]:
            self.assertIsNone(csa.normalize_status(v),
                              "%r 不可识别，必须返回 None 而不是 Uncertain" % (v,))


class TestCohensKappa(unittest.TestCase):
    def test_perfect_agreement(self):
        a = _make_map([("R1", "Include"), ("R2", "Exclude"), ("R3", "Uncertain")])
        b = _make_map([("R1", "Include"), ("R2", "Exclude"), ("R3", "Uncertain")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertEqual(res["sample_size"], 3)
        self.assertEqual(res["discrepancy_count"], 0)
        self.assertEqual(res["observed_agreement"], 1.0)
        self.assertEqual(res["cohens_kappa"], 1.0)
        self.assertEqual(res["gate_failed"] if "gate_failed" in res else False, False)

    def test_known_kappa_value(self):
        """Hand-computed 3-class kappa on a 4-record case.

        A: [Inc, Inc, Inc, Exc], B: [Inc, Inc, Exc, Exc]
        po = 3/4 = 0.75; pe = (3*2 + 1*2)/16 = 0.5; kappa = 0.5
        """
        a = _make_map([("R1", "Include"), ("R2", "Include"),
                       ("R3", "Include"), ("R4", "Exclude")])
        b = _make_map([("R1", "Include"), ("R2", "Include"),
                       ("R3", "Exclude"), ("R4", "Exclude")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertAlmostEqual(res["cohens_kappa"], 0.5, places=4)
        self.assertAlmostEqual(res["observed_agreement"], 0.75, places=4)
        self.assertAlmostEqual(res["expected_agreement"], 0.5, places=4)
        self.assertEqual(res["agreed_count"], 3)
        self.assertEqual(res["discrepancy_count"], 1)

    def test_discrepancy_entries_require_arbitration(self):
        a = _make_map([("R1", "Include"), ("R2", "Exclude")])
        b = _make_map([("R1", "Exclude"), ("R2", "Exclude")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertEqual(res["discrepancy_count"], 1)
        d = res["discrepancies"][0]
        self.assertTrue(d["arbitration_required"])
        self.assertEqual(d["id"], "R1")
        self.assertEqual(res["confusion_matrix"][0][1], 1)  # A=Include, B=Exclude cell

    def test_kappa_bounded(self):
        a = _make_map([("R1", "Include"), ("R2", "Uncertain"),
                       ("R3", "Exclude"), ("R4", "Include")])
        b = _make_map([("R1", "Exclude"), ("R2", "Include"),
                       ("R3", "Uncertain"), ("R4", "Exclude")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertGreaterEqual(res["cohens_kappa"], -1.0)
        self.assertLessEqual(res["cohens_kappa"], 1.0)

    def test_no_overlap_ids(self):
        a = _make_map([("A1", "Include")])
        b = _make_map([("B1", "Include")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertIn("error", res)


class TestLoadDecisions(unittest.TestCase):
    def test_load_json_list_format(self):
        data = [
            {"id": "R1", "title": "T1", "status": "included", "reason_code": ""},
            {"id": "R2", "title": "T2", "status": "排除"},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            recs = csa.load_decisions(p)
        self.assertEqual(recs["R1"]["status"], "Include")
        self.assertEqual(recs["R2"]["status"], "Exclude")

    def test_load_csv(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.csv"
            p.write_text("id,title,status,reason_code\nR1,Paper One,Include,EXC_TAXON\n"
                         "R2,Paper Two,Uncertain,\n", encoding="utf-8")
            recs = csa.load_decisions(p)
        self.assertEqual(recs["R1"]["status"], "Include")
        self.assertEqual(recs["R2"]["status"], "Uncertain")

    def test_load_unsupported_extension(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.xlsx"
            p.write_text("dummy", encoding="utf-8")
            with self.assertRaises(ValueError):
                csa.load_decisions(p)

    # ---- P1（2026-09-15）：canonical 键名必须可读 ----
    def test_loads_canonical_record_id_and_screening_status(self):
        """生产者只写 canonical 名（agent_search.py / ingest_external_records.py），
        加载器原先只认 `id|rec_id|doi|title` 与 `status|Status|decision`——两边错开，
        整份文件的裁决被读成空值。"""
        data = [
            {"record_id": "R1", "title": "T1", "screening_status": "Include"},
            {"record_id": "R2", "title": "T2", "screening_status": "Exclude"},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "canonical.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            recs = csa.load_decisions(p)
        self.assertEqual(recs["R1"]["status"], "Include")
        self.assertEqual(recs["R2"]["status"], "Exclude")
        self.assertEqual(csa.summarize_unreadable(recs), [])

    def test_unreadable_decisions_are_reported_not_washed(self):
        data = [{"record_id": "R1", "screening_decision": "Include"}]  # 键名对不上
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "badkey.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            recs = csa.load_decisions(p)
        self.assertIsNone(recs["R1"]["status"])
        self.assertEqual(csa.summarize_unreadable(recs), [("R1", None)])


class TestKappaRefusesUnreadableInput(unittest.TestCase):
    """P1（2026-09-15）：κ 不得在输入读不出时给出数值结论。

    旧实现 `cat_to_idx.get(stat, 2)` 把 `None` 静默落到 Uncertain 格——「读不到」
    变成「两方都判待定」，制造虚假一致。
    """

    def test_unreadable_status_is_refused(self):
        a = {"R1": {"status": None, "status_raw": None}}
        b = {"R1": {"status": "Include", "status_raw": "Include"}}
        res = csa.calculate_cohens_kappa(a, b)
        self.assertIn("error", res, "读不到裁决时不得产出 κ 数值")
        self.assertIn("UNREADABLE_DECISIONS", res["error"])

    def test_readable_input_still_computes(self):
        a = _make_map([("R1", "Include"), ("R2", "Exclude")])
        b = _make_map([("R1", "Include"), ("R2", "Exclude")])
        res = csa.calculate_cohens_kappa(a, b)
        self.assertNotIn("error", res)
        self.assertEqual(res["cohens_kappa"], 1.0)


class TestSelftest(unittest.TestCase):
    def test_builtin_selftest_passes(self):
        # The author's own selftest must keep passing — guards against regressions
        # in calculate_cohens_kappa even if this suite's fixtures drift.
        csa.run_selftest()


if __name__ == "__main__":
    unittest.main()
