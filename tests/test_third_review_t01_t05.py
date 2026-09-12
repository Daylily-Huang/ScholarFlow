# -*- coding: utf-8 -*-
"""第三次独立验收（2026-09-13）T01–T05 的自动回归。

对应文档：`docs/implementation/ScholarFlow_第三次修改独立验收与评分_2026-09-13.md`。
每条用例都来自该文档的独立实跑反例，另配对应的**正例**（换算/极小量/零值/
空会话首次追加），避免"只挡反例、误伤正例"。

- **T01** 相等判定改为十进制定点：`1 nL` 与 `2 nL` 不得判为相等；
- **T02** 单位倍率与千分比：`bp/kb/mb` 分列，`‰` 按 1000 折算；
- **T03** 未知单位（`Gy` / `Sv`）不得静默退化为无单位数字；
- **T04** 封存检查点在任何写入前校验 revision，两文件一致提交可识别中断；
- **T05** 零事件检查点的重放边界按已核验 `event_count`，后续事件不得被跳过。

全部为合成数据与临时目录，不触碰真实会话。
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

import helpers  # noqa: F401

from shared.execution.session_store import (  # noqa: E402
    SessionStore,
    ProjectionError,
    RevisionConflict,
)


def _load_quote_audit():
    path = os.path.join(helpers.REPO_ROOT, "skills", "literature-evidence-extraction",
                        "scripts", "quote_audit.py")
    spec = importlib.util.spec_from_file_location("sf_quote_audit_t01_t05", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quote_audit = _load_quote_audit()


def _audit(source, value, **extra):
    record = {"verbatim_quote": source, "extracted_value": value}
    record.update(extra)
    return quote_audit.audit_evidence({"evidence_records": [record]}, source)


def _verdict(report):
    return (report["entries"][0].get("value_alignment") or {}).get("verdict")


class TestT01DecimalEquality(unittest.TestCase):
    """T01：极小量的相等判定必须精确，不得用绝对容差掩盖真实差异。"""

    def test_nanolitre_mismatch_is_blocked(self):
        """核查反例：源文 1 nL、抽取 2 nL（换算后差 1e-9 L）不得放行。"""
        source = "The volume was 2 nL in the tube."
        report = _audit(source, "1 nL")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])
        self.assertNotEqual(_verdict(report), "ALIGNED")

    def test_nanolitre_match_passes(self):
        source = "The volume was 2 nL in the tube."
        report = _audit(source, "2 nL")
        self.assertFalse(quote_audit.gate_failed(report, strict=True), report["summary"])
        self.assertEqual(_verdict(report), "ALIGNED")

    def test_zero_is_not_equal_to_tiny_nonzero(self):
        source = "The volume was 1 nL in the tube."
        report = _audit(source, "0 L")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_nanogram_and_nanometre_mismatch_blocked(self):
        for source, value in (("The mass was 2 ng in the sample.", "1 ng"),
                              ("The length was 2 nm in the sample.", "1 nm")):
            report = _audit(source, value)
            self.assertTrue(quote_audit.gate_failed(report, strict=True), source)

    def test_cross_unit_conversions_pass(self):
        """正例：同一量纲内的正确换算仍要放行。"""
        cases = (
            ("The volume was 2000 nL in the tube.", "2 µL"),
            ("The volume was 2500 µL of buffer.", "2.5 mL"),
            ("The mass was 2000 ng in the sample.", "2 µg"),
            ("The length was 2000 nm in the sample.", "2 µm"),
        )
        for source, value in cases:
            report = _audit(source, value)
            self.assertFalse(quote_audit.gate_failed(report, strict=True),
                             "%s vs %s -> %s" % (source, value, report["summary"]))
            self.assertEqual(_verdict(report), "ALIGNED")


class TestT02UnitScales(unittest.TestCase):
    """T02：单位倍率与千分比换算。"""

    def test_basepair_kilobase_are_not_the_same_scale(self):
        """核查反例：源文 5 kb、抽取 5 bp 不得放行。"""
        source = "The fragment length was 5 kb."
        report = _audit(source, "5 bp")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_basepair_kilobase_conversion_passes(self):
        source = "The fragment length was 5 kb."
        report = _audit(source, "5000 bp")
        self.assertFalse(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_megabase_scale_is_distinct(self):
        source = "The genome size was 1 mb."
        report = _audit(source, "1 kb")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_permille_uses_one_thousandth(self):
        """核查反例：比例字段下 0.05 与 5‰ 不等；0.005 与 5‰ 相等。"""
        wrong = _audit("The proportion was 0.05 in the sample.", "5‰",
                       value_type="proportion")
        self.assertTrue(quote_audit.gate_failed(wrong, strict=True), wrong["summary"])
        right = _audit("The proportion was 0.005 in the sample.", "5‰",
                       value_type="proportion")
        self.assertFalse(quote_audit.gate_failed(right, strict=True), right["summary"])

    def test_percent_still_uses_one_hundredth(self):
        report = _audit("The proportion was 0.05 in the sample.", "5%",
                        value_type="proportion")
        self.assertFalse(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_percent_and_permille_cross_conversion(self):
        """`5%` == `50‰`（同一比例），但 `5%` ≠ `5‰`。"""
        ok = _audit("The proportion was 5% in the sample.", "50‰",
                    value_type="proportion")
        self.assertFalse(quote_audit.gate_failed(ok, strict=True), ok["summary"])
        bad = _audit("The proportion was 5% in the sample.", "5‰",
                     value_type="proportion")
        self.assertTrue(quote_audit.gate_failed(bad, strict=True), bad["summary"])

    def test_thousands_separator_and_decimal_comma(self):
        """`1,000 reads` 是千分位；`2,5 mL` 是欧洲小数逗号——两者都不能被误解析。"""
        thousands = _audit("The sample had 1,000 reads in total.", "1000 reads")
        self.assertFalse(quote_audit.gate_failed(thousands, strict=True),
                         thousands["summary"])
        decimal_comma = _audit("The value was 2,5 mL in the sample.", "2,5 mL")
        self.assertFalse(quote_audit.gate_failed(decimal_comma, strict=True),
                         decimal_comma["summary"])
        mismatch = _audit("The sample had 1,000 reads in total.", "1 reads")
        self.assertTrue(quote_audit.gate_failed(mismatch, strict=True), mismatch["summary"])


class TestT03UnknownUnits(unittest.TestCase):
    """T03：未知单位必须保留原文并阻断，不得退化为无单位数字。"""

    def test_unknown_unit_swap_is_blocked(self):
        """核查反例：源文 5 Gy、抽取 5 Sv 不得放行。"""
        source = "The dose was 5 Gy in the sample."
        report = _audit(source, "5 Sv")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])
        self.assertEqual(_verdict(report), "UNKNOWN_UNIT")

    def test_unknown_unit_is_not_compared_as_plain_number(self):
        tokens = quote_audit.extract_value_tokens("5 Sv")
        self.assertNotIn("5", tokens)
        quantity = quote_audit.extract_quantities("5 Sv")[0]
        self.assertEqual(quantity["dimension"], "unknown")
        self.assertEqual(quantity["unit"], "Sv")

    def test_same_unknown_unit_still_requires_review(self):
        """即使单位原文一致，本层不支持的量纲也标待核验（诚实阻断）。"""
        source = "The dose was 5 Gy in the sample."
        report = _audit(source, "5 Gy")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_declared_dimensionless_field_may_compare(self):
        """字段显式声明计数/无量纲时才允许按数值比较。"""
        source = "The count was 5 in the sample."
        report = _audit(source, "5 Gy", value_type="count")
        self.assertFalse(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_source_side_unknown_unit_blocks_unitless_extraction(self):
        """自检补漏：源文 `5 Gy`、抽取值写成无量纲 `5` —— 单位被悄悄丢掉也要阻断。"""
        source = "The dose was 5 Gy in the sample."
        report = _audit(source, "5")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_compound_units_are_blocked(self):
        """复合/带指数单位本层不做换算：`m/s`、`m2` 一律未知单位阻断。"""
        for source, value in (("The speed was 2 m/s in the test.", "2 m/s"),
                              ("The speed was 2 m/s in the test.", "2 m"),
                              ("The area was 5 m2 in the plot.", "5 m2")):
            report = _audit(source, value)
            self.assertTrue(quote_audit.gate_failed(report, strict=True),
                            "%s vs %s -> %s" % (source, value, report["summary"]))

    def test_unknown_unit_does_not_match_known_count_dimension(self):
        """声明 count 也不能让未知单位撞上计数单位。"""
        source = "The study included 20 samples."
        report = _audit(source, "20 Gy", value_type="count")
        self.assertTrue(quote_audit.gate_failed(report, strict=True), report["summary"])

    def test_plain_words_are_not_mistaken_for_units(self):
        """普通英文词（The/This/Table）不得被误判成单位。"""
        for source in ("The measured quantity was 20 for this sample.",
                       "The measured quantity was 20 This sample had more.",
                       "A total of 30 Table rows were inspected."):
            report = _audit(source, "20" if "20" in source else "30")
            self.assertFalse(quote_audit.gate_failed(report, strict=True), source)


class TestT04AtomicSealing(unittest.TestCase):
    """T04：封存前校验 revision，两文件一致提交且可识别中断。"""

    def _sealed_store(self, folder):
        store = SessionStore(folder)
        store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None}, 0)
        store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None},
                              expected_revision=1)
        return store

    def test_stale_revision_changes_neither_file(self):
        """核查反例：过期 revision 失败后，快照与检查点都必须保持原样。"""
        with tempfile.TemporaryDirectory(prefix="sf-t04-") as folder:
            store = self._sealed_store(folder)
            with open(store.session_path, encoding="utf-8") as fh:
                before_snapshot = fh.read()
            with open(store.checkpoint_path, encoding="utf-8") as fh:
                before_checkpoint = fh.read()
            with self.assertRaises(RevisionConflict):
                store.seal_checkpoint({"state": "CLOSED", "last_applied_event_id": None},
                                      expected_revision=1)
            with open(store.session_path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before_snapshot)
            with open(store.checkpoint_path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before_checkpoint)
            self.assertFalse(os.path.exists(store.commit_journal_path))

    def test_interrupted_commit_is_reported_and_recoverable(self):
        """模拟写入中断：留下提交日志 → 报告 INCOMPLETE_COMMIT，可完成提交。"""
        with tempfile.TemporaryDirectory(prefix="sf-t04-") as folder:
            store = self._sealed_store(folder)
            store._atomic_write_json(store.commit_journal_path, {
                "schema_version": "0.1", "commit_id": "commit-synthetic",
                "expected_revision": 2,
                "snapshot": {"state": "CLOSED", "last_applied_event_id": None,
                             "revision": 3},
                "checkpoint": {"schema_version": "0.1", "commit_id": "commit-synthetic",
                               "last_event_id": None, "event_count": 0,
                               "event_log_digest": store._event_digest([]),
                               "inherited_fields": [], "state": {"state": "CLOSED"}}})
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            self.assertIn("INCOMPLETE_COMMIT",
                          [d["kind"] for d in report["divergence"]])
            self.assertEqual(report["pending_commit_id"], "commit-synthetic")

            recovery = store.recover_commit()
            self.assertEqual(recovery["status"], "COMMIT_COMPLETED")
            self.assertFalse(os.path.exists(store.commit_journal_path))
            self.assertTrue(store.consistency_report()["consistent"])

    def test_successful_seal_leaves_no_journal(self):
        with tempfile.TemporaryDirectory(prefix="sf-t04-") as folder:
            store = self._sealed_store(folder)
            self.assertFalse(os.path.exists(store.commit_journal_path))
            self.assertIsNone(store.pending_commit())

    def test_new_inherited_fields_need_explicit_import(self):
        """检查点信任边界：已有检查点后不得无审计地接纳新业务字段。"""
        with tempfile.TemporaryDirectory(prefix="sf-t04-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None,
                                 "ideas": []}, 0)
            store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None,
                                   "ideas": []}, expected_revision=1)
            with self.assertRaises(ProjectionError):
                store.seal_checkpoint({"state": "WAITING_USER",
                                       "last_applied_event_id": None,
                                       "ideas": [], "decisions": ["UNLOGGED"]},
                                      expected_revision=2)

            sealed = store.seal_checkpoint(
                {"state": "WAITING_USER", "last_applied_event_id": None,
                 "ideas": [], "decisions": ["UNLOGGED"]},
                expected_revision=2, import_mode=True,
                import_reason="历史会话导入", import_source="legacy-session.json")
            self.assertIn("decisions", sealed["inherited_fields"])
            checkpoint = store.load_checkpoint()
            self.assertTrue(checkpoint["import_mode"])
            self.assertEqual(checkpoint["import_source"], "legacy-session.json")

    def test_import_mode_requires_reason_and_source(self):
        with tempfile.TemporaryDirectory(prefix="sf-t04-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None,
                                 "ideas": []}, 0)
            store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None,
                                   "ideas": []}, expected_revision=1)
            with self.assertRaises(ProjectionError):
                store.seal_checkpoint({"state": "WAITING_USER",
                                       "last_applied_event_id": None,
                                       "ideas": [], "decisions": ["X"]},
                                      expected_revision=2, import_mode=True)


class TestT05ZeroEventCheckpoint(unittest.TestCase):
    """T05：零事件检查点的重放边界。"""

    def test_events_after_empty_checkpoint_are_replayed(self):
        """核查反例：空日志封存后追加 E1，重放必须落在 E1 上。"""
        with tempfile.TemporaryDirectory(prefix="sf-t05-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None}, 0)
            store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None},
                                  expected_revision=1)
            store.append_event({"event_id": "E1", "session_id": "S1", "seq": 1,
                                "type": "ROLE_RESPONSE", "actor": "moderator",
                                "execution_kind": "ROLE_SWITCH",
                                "payload": {"field": "state", "value": "CLOSED"}})
            state = store.rebuild()["state"]
            store.seal_checkpoint(state, expected_revision=state["revision"])
            report = store.consistency_report()
            self.assertTrue(report["consistent"], report)
            self.assertEqual(report["replayed_last_applied_event_id"], "E1")

    def test_truncated_log_is_reported(self):
        """检查点声明的 event_count 超过日志长度 → 明确报截断。"""
        with tempfile.TemporaryDirectory(prefix="sf-t05-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None}, 0)
            store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None},
                                  expected_revision=1)
            store.append_event({"event_id": "E1", "session_id": "S1", "seq": 1,
                                "type": "ROLE_RESPONSE", "actor": "moderator",
                                "execution_kind": "ROLE_SWITCH",
                                "payload": {"field": "state", "value": "CLOSED"}})
            state = store.rebuild()["state"]
            store.seal_checkpoint(state, expected_revision=state["revision"])
            with open(store.events_path, "w", encoding="utf-8") as fh:
                fh.write("")
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            self.assertIn("CHECKPOINT_EVENT_COUNT_AHEAD",
                          [d["kind"] for d in report["divergence"]])

    def test_checkpoint_reports_trust_boundary(self):
        """检查点必须自述"哪些字段不是事件推出来的"，不得宣称全部由事件证明。"""
        with tempfile.TemporaryDirectory(prefix="sf-t05-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None,
                                 "ideas": []}, 0)
            store.seal_checkpoint({"state": "WAITING_USER", "last_applied_event_id": None,
                                   "ideas": []}, expected_revision=1)
            checkpoint = store.load_checkpoint()
            self.assertIn("ideas", checkpoint["inherited_fields"])
            self.assertIn("historical state", checkpoint["trust_boundary"])
            report = store.consistency_report()
            # 零事件日志下 state 也是"封存时已有"的值，一并如实列出
            self.assertIn("ideas", report["checkpoint_inherited_fields"])
            self.assertIn("state", report["checkpoint_inherited_fields"])
            self.assertFalse(report["checkpoint_import_mode"])

    def test_boundary_mismatch_is_reported(self):
        """event_count 指向的事件与 last_event_id 不符 → 明确报边界不一致。"""
        with tempfile.TemporaryDirectory(prefix="sf-t05-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None}, 0)
            store.append_event({"event_id": "E1", "session_id": "S1", "seq": 1,
                                "type": "ROLE_RESPONSE", "actor": "moderator",
                                "execution_kind": "ROLE_SWITCH",
                                "payload": {"field": "state", "value": "WAITING_USER"}})
            state = store.rebuild()["state"]
            store.seal_checkpoint(state, expected_revision=state["revision"])
            checkpoint = store.load_checkpoint()
            checkpoint["last_event_id"] = "E-OTHER"
            store._atomic_write_json(store.checkpoint_path, checkpoint)
            report = store.consistency_report()
            kinds = [d["kind"] for d in report["divergence"]]
            self.assertIn("CHECKPOINT_EVENT_BOUNDARY_MISMATCH", kinds)


if __name__ == "__main__":
    unittest.main()
