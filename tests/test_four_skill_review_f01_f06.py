# -*- coding: utf-8 -*-
"""四技能审查（2026-09-12）F01–F06 反例的自动回归。

审查文档 §13/§14 要求："先把 F01–F06 的反例转成回归测试"。本文件把当时只在
一次性探针（`.planning/four-skill-review/probe.py`，已 gitignore）中验证的反例
固化为套件内可重复执行的用例，防止后续改动静默回退。

覆盖：

- **F01** 片段引句与否定引句不得被判为支持；
- **F02** 数值出现在全文但不在引句上下文中必须阻断交付；
- **F03** 坏尾部未恢复时不得追加事件，恢复事务必须可重复且留证；
- **F04** 末尾事件 ID 相同但状态不同必须报 `STATE_PROJECTION_MISMATCH`；
- **F05** 只有 `CONFIRMED` 字符串、无指纹/无确认事件的审批不得派发；
- **F06** 外键修复不得制造用户授权（不得伪造 `CONFIRMED` 与指纹）。

全部为离线合成数据，不读写任何真实会话。
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

import helpers  # noqa: F401

from shared.execution.debate_handoff import (  # noqa: E402
    prepare_dispatch,
    scope_fingerprint,
    to_evidence_link,
)
from shared.execution.session_store import CorruptEventLog, SessionStore  # noqa: E402

REPO_ROOT = helpers.REPO_ROOT


def _load_quote_audit():
    path = os.path.join(REPO_ROOT, "skills", "literature-evidence-extraction",
                        "scripts", "quote_audit.py")
    spec = importlib.util.spec_from_file_location("sf_quote_audit_f01_f06", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quote_audit = _load_quote_audit()

PROPOSITION = "roads reduce gene flow"


def _evidence_record(quote, **overrides):
    record = {
        "evidence_id": "EV-SYNTH-1",
        "verbatim_quote": quote,
        "location": {"page": 3},
        "checked_scope": "full text, Methods+Results",
        # 上游审计状态不是本组反例的自变量：用通过值，避免 UPSTREAM_AUDIT_* 混入。
        "claim_status": "verified",
    }
    record.update(overrides)
    return record


class TestF01QuoteAlignmentCounterexamples(unittest.TestCase):
    """F01：词面重合被误当语义支持。"""

    def test_fragment_quote_is_not_verified(self):
        """引句只是命题中的一个实体词 → 必须 UNRESOLVED 且标注覆盖不足。

        旧实现 `_compare` 在 `proposition in quote` 之外还接受反向子串，
        于是 "roads" 对 "roads reduce gene flow" 返回 EXACT/1.0，直接 VERIFIED。
        """
        link = to_evidence_link(_evidence_record("roads"), PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("QUOTE_DOES_NOT_SUPPORT_PROPOSITION", link["problems"])
        self.assertLess(link["proposition_match_ratio"], 0.5)
        self.assertFalse(link["text_match"])

    def test_negated_quote_is_not_verified(self):
        """否定句字面包含命题，但方向相反 → 必须 UNRESOLVED 且标注否定不匹配。"""
        quote = "It is not true that roads reduce gene flow."
        link = to_evidence_link(_evidence_record(quote), PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("NEGATION_MISMATCH", link["problems"])

    def test_full_coverage_support_still_verified(self):
        """正例不得被反例修复误伤：完整覆盖的引句仍应 VERIFIED。"""
        quote = "roads reduce gene flow in fragmented landscapes"
        link = to_evidence_link(_evidence_record(quote), PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "VERIFIED")
        self.assertEqual(link["problems"], [])
        self.assertTrue(link["text_match"])

    def test_quote_covering_whole_proposition_is_verified_flag_text_match(self):
        """片段引句与完整覆盖引句必须在 `text_match` 上可区分。"""
        fragment = to_evidence_link(_evidence_record("roads"), PROPOSITION, "SUPPORT")
        full = to_evidence_link(
            _evidence_record("roads reduce gene flow in fragmented landscapes"),
            PROPOSITION, "SUPPORT")
        self.assertFalse(fragment["text_match"])
        self.assertTrue(full["text_match"])
        self.assertEqual(fragment["alignment"], "UNRESOLVED")
        self.assertEqual(full["alignment"], "VERIFIED")

    def test_upstream_failed_audit_blocks_verification(self):
        """上游已判 unverified 的记录不得在本地被升级为 VERIFIED。"""
        link = to_evidence_link(
            _evidence_record("roads reduce gene flow in fragmented landscapes",
                             claim_status="unverified"),
            PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("UPSTREAM_AUDIT_CLAIM_STATUS", link["problems"])

    def test_missing_location_anchor_and_scope_are_reported(self):
        """F01：`{"page": null}` 不是定位；缺 checked_scope 必须显式记缺口。"""
        link = to_evidence_link(
            _evidence_record("roads reduce gene flow in fragmented landscapes",
                             location={"page": None}, checked_scope=""),
            PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("INVALID_LOCATION", link["problems"])
        self.assertIn("MISSING_CHECKED_SCOPE", link["problems"])


class TestF02ValueAnchoringCounterexamples(unittest.TestCase):
    """F02：数值未在引句上下文中锚定。"""

    def _audit(self, quote, value, source):
        return quote_audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": quote,
                                   "extracted_value": value}]},
            source)

    def test_percentage_substring_is_not_a_match(self):
        """`5.4%` 不得在 `55.4%` 内部命中（裸数字变体已移除 + 数字边界判定）。"""
        source = "The observed proportion was 55.4% in this sample."
        report = self._audit(source, "5.4%", source)
        self.assertTrue(quote_audit.gate_failed(report, strict=True),
                        report["summary"])

    def test_value_far_from_quote_blocks_delivery(self):
        """数值确实在全文，但远离引句 → 未锚定，必须阻断交付并计入 unverified。"""
        quote = "The method was evaluated using a controlled experiment."
        source = quote + " unrelated context " * 100 + "Another sample had 5.4%."
        report = self._audit(quote, "5.4%", source)
        self.assertEqual(report["summary"].get("value_not_in_quote_context"), 1)
        self.assertEqual(report["summary"].get("unverified"), 1)
        self.assertTrue(quote_audit.gate_failed(report, strict=False))
        self.assertTrue(quote_audit.gate_failed(report, strict=True))

    def test_unit_bearing_integer_is_checked(self):
        """带单位整数（`999 microliters`）必须被识别为可核对的数值锚点。"""
        source = "The reaction volume was 20 microliters for every sample."
        report = self._audit(source, "999 microliters", source)
        self.assertTrue(quote_audit.gate_failed(report, strict=True),
                        report["summary"])

    def test_aligned_value_still_passes(self):
        """正例：数值就在引句内 → 不得被新门禁误伤。"""
        source = "The observed proportion was 55.4% in this sample."
        report = self._audit(source, "55.4%", source)
        self.assertFalse(quote_audit.gate_failed(report, strict=True),
                         report["summary"])


class TestF03CorruptTailRecovery(unittest.TestCase):
    """F03：坏尾部必须走显式恢复，不得静默吞掉后续写入。"""

    def _store_with_corrupt_tail(self, folder):
        store = SessionStore(folder)
        store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None}, 0)
        store.append_event({"event_id": "E1",
                            "payload": {"field": "state", "value": "WAITING_USER"}})
        with open(store.events_path, "a", encoding="utf-8") as fh:
            fh.write('{"event_id":')
        return store

    def test_append_before_recovery_is_refused(self):
        """坏尾部未解除 → append_event 必须抛 RECOVERY_REQUIRED，而非返回成功。"""
        with tempfile.TemporaryDirectory(prefix="sf-f03-") as folder:
            store = self._store_with_corrupt_tail(folder)
            with self.assertRaises(CorruptEventLog) as ctx:
                store.append_event({"event_id": "E2",
                                    "payload": {"field": "state", "value": "CLOSED"}})
            self.assertEqual(ctx.exception.details.get("reason"), "RECOVERY_REQUIRED")

    def test_recovery_then_append_succeeds(self):
        """显式恢复后事件日志只保留有效事件，后续写入正常生效。"""
        with tempfile.TemporaryDirectory(prefix="sf-f03-") as folder:
            store = self._store_with_corrupt_tail(folder)
            with self.assertRaises(CorruptEventLog):
                store.append_event({"event_id": "E2",
                                    "payload": {"field": "state", "value": "CLOSED"}})
            store.rebuild()
            self.assertTrue(store.append_event(
                {"event_id": "E2", "payload": {"field": "state", "value": "CLOSED"}}))
            self.assertEqual([e["event_id"] for e in store._read_events()["events"]],
                             ["E1", "E2"])
            self.assertEqual(len(store.recovery_notes()), 1)

    def test_recovery_is_idempotent_and_keeps_evidence(self):
        """同一份损坏重复恢复不产生新隔离副本，且保留坏尾部与恢复前备份。"""
        with tempfile.TemporaryDirectory(prefix="sf-f03-") as folder:
            store = self._store_with_corrupt_tail(folder)
            store.rebuild()
            first = store.recovery_notes()[0]
            store.rebuild()
            notes = store.recovery_notes()
            quarantines = sorted({n["quarantine"] for n in notes})
            self.assertEqual(len(quarantines), 1)
            self.assertTrue(os.path.isfile(first["quarantine"]))
            self.assertTrue(os.path.isfile(first["backup"]))
            with open(first["quarantine"], encoding="utf-8") as fh:
                self.assertIn('{"event_id":', fh.read())

    def test_read_only_diagnosis_has_no_side_effects(self):
        """只读诊断（consistency_report）不得就地隔离或改写日志。"""
        with tempfile.TemporaryDirectory(prefix="sf-f03-") as folder:
            store = self._store_with_corrupt_tail(folder)
            with open(store.events_path, encoding="utf-8") as fh:
                before = fh.read()
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            self.assertIn("QUARANTINED_TAIL",
                          [d["kind"] for d in report["divergence"]])
            with open(store.events_path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before)
            self.assertFalse([f for f in os.listdir(folder) if ".corrupt-tail-" in f])


class TestF04StateProjectionDivergence(unittest.TestCase):
    """F04：末尾事件 ID 相同不代表状态相同。"""

    def test_same_last_event_but_different_state_is_divergent(self):
        with tempfile.TemporaryDirectory(prefix="sf-f04-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER",
                                 "last_applied_event_id": None}, 0)
            store.append_event({"event_id": "E1",
                                "payload": {"field": "state", "value": "WAITING_USER"}})
            store.save_snapshot({"state": "CLOSED", "last_applied_event_id": "E1"}, 1)

            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            kinds = [d["kind"] for d in report["divergence"]]
            self.assertIn("STATE_PROJECTION_MISMATCH", kinds)
            mismatch = [d for d in report["divergence"]
                        if d["kind"] == "STATE_PROJECTION_MISMATCH"][0]
            self.assertIn("state", mismatch["fields"])
            self.assertEqual(store.rebuild()["state"]["state"], "WAITING_USER")

    def test_revision_only_change_is_not_divergence(self):
        """revision 等非业务字段不得触发误报。"""
        with tempfile.TemporaryDirectory(prefix="sf-f04-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER",
                                 "last_applied_event_id": None}, 0)
            store.append_event({"event_id": "E1",
                                "payload": {"field": "state", "value": "WAITING_USER"}})
            state = store.rebuild()["state"]
            store.save_snapshot(state, state.get("revision", 0))
            report = store.consistency_report()
            self.assertNotIn("STATE_PROJECTION_MISMATCH",
                             [d["kind"] for d in report["divergence"]])


class TestF05ApprovalBindingGate(unittest.TestCase):
    """F05：审批必须绑定指纹、确认事件与范围/版本。"""

    def _gap(self, approval, **overrides):
        gap = {
            "gap_id": "G-SYNTH-1",
            "gap_type": "SEARCH_GAP",
            "target_skill": "literature-discovery-acquisition",
            "question": "synthetic test question",
            "scope": {"population": "synthetic"},
            "approval": approval,
        }
        gap.update(overrides)
        return gap

    def test_bare_confirmed_string_is_not_dispatchable(self):
        """只有 status=CONFIRMED、无指纹 → APPROVAL_BINDING_MISSING 且须重新确认。"""
        result = prepare_dispatch(self._gap({"status": "CONFIRMED"}))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_BINDING_MISSING")
        self.assertTrue(result["must_reconfirm"])

    def test_fingerprint_without_confirmation_event_is_not_dispatchable(self):
        """有正确指纹但无可追溯的确认事件 → APPROVAL_CONFIRMATION_UNBOUND。"""
        gap = self._gap({"status": "CONFIRMED"})
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        result = prepare_dispatch(gap)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_CONFIRMATION_UNBOUND")
        self.assertTrue(result["must_reconfirm"])

    def test_stale_fingerprint_is_not_dispatchable(self):
        """问题/范围变更后旧指纹失效 → SCOPE_CHANGED_APPROVAL_STALE。"""
        gap = self._gap({"status": "CONFIRMED",
                         "scope_fingerprint": "deadbeef",
                         "confirmed_event_id": "EV-CONFIRM-1"})
        result = prepare_dispatch(gap)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "SCOPE_CHANGED_APPROVAL_STALE")

    def test_fully_bound_approval_is_dispatchable(self):
        """正例：指纹 + 确认事件齐备 → 允许派发。"""
        gap = self._gap({"status": "CONFIRMED"})
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        gap["approval"]["confirmed_event_id"] = "EV-CONFIRM-1"
        result = prepare_dispatch(gap)
        self.assertTrue(result["dispatchable"], result)
        self.assertEqual(result["reason"], "OK")

    def test_unconfirmed_status_still_blocks(self):
        """非 CONFIRMED 状态仍按原契约阻断。"""
        result = prepare_dispatch(self._gap({"status": "PENDING"}))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_NOT_CONFIRMED")


class TestF06HealingMustNotGrantApproval(unittest.TestCase):
    """F06：外键修复只生成待确认占位，不得制造授权。"""

    def _session(self, **overrides):
        session = {
            "session_id": "S-SYNTH-1",
            "ideas": [{"idea_id": "IDEA-1", "version": 2}],
            "gap_requests": [],
            "review_batches": [{"batch_id": "B1", "resolution": "ESCALATED_TO_GAP",
                                "escalated_gap_id": "GAP-ORPHAN"}],
        }
        session.update(overrides)
        return session

    def test_placeholder_is_pending_not_confirmed(self):
        with tempfile.TemporaryDirectory(prefix="sf-f06-") as folder:
            store = SessionStore(folder)
            healed, actions = store.heal_referential_integrity(self._session())
            gaps = {g["gap_id"]: g for g in healed["gap_requests"]}
            self.assertIn("GAP-ORPHAN", gaps)
            placeholder = gaps["GAP-ORPHAN"]
            self.assertEqual(placeholder["approval"]["status"], "PENDING")
            self.assertIsNone(placeholder["approval"].get("confirmed_event_id"))
            self.assertIsNone(placeholder["approval"].get("scope_fingerprint"))
            self.assertTrue(placeholder["approval"].get("healed_placeholder"))
            self.assertTrue(actions)

    def test_healed_placeholder_is_not_dispatchable(self):
        """修复产物必须仍被派发门禁挡住（端到端闭合）。"""
        with tempfile.TemporaryDirectory(prefix="sf-f06-") as folder:
            store = SessionStore(folder)
            healed, _ = store.heal_referential_integrity(self._session())
            gap = healed["gap_requests"][0]
            result = prepare_dispatch(gap)
            self.assertFalse(result["dispatchable"])
            self.assertIn(result["reason"],
                          ("APPROVAL_NOT_CONFIRMED", "APPROVAL_BINDING_MISSING",
                           "APPROVAL_CONFIRMATION_UNBOUND"))

    def test_ambiguous_idea_reference_is_reported_not_guessed(self):
        """多个候选 idea 且批次未标明 → ORPHAN_RELATION，不得猜第一条。"""
        with tempfile.TemporaryDirectory(prefix="sf-f06-") as folder:
            store = SessionStore(folder)
            session = self._session(ideas=[{"idea_id": "IDEA-1", "version": 1},
                                           {"idea_id": "IDEA-2", "version": 3}])
            healed, actions = store.heal_referential_integrity(session)
            placeholder = healed["gap_requests"][0]
            self.assertIsNone(placeholder.get("idea_id"))
            self.assertTrue(any("ORPHAN_RELATION" in a for a in actions), actions)

    def test_single_idea_is_inferred_and_recorded(self):
        with tempfile.TemporaryDirectory(prefix="sf-f06-") as folder:
            store = SessionStore(folder)
            healed, actions = store.heal_referential_integrity(self._session())
            self.assertEqual(healed["gap_requests"][0].get("idea_id"), "IDEA-1")
            self.assertTrue(any("Inferred idea_id" in a for a in actions), actions)

    def test_consistent_session_needs_no_healing(self):
        with tempfile.TemporaryDirectory(prefix="sf-f06-") as folder:
            store = SessionStore(folder)
            session = self._session(gap_requests=[{"gap_id": "GAP-ORPHAN"}])
            self.assertEqual(store.check_referential_integrity(session), [])
            healed, actions = store.heal_referential_integrity(session)
            self.assertEqual(actions, [])
            self.assertEqual(len(healed["gap_requests"]), 1)


if __name__ == "__main__":
    unittest.main()
