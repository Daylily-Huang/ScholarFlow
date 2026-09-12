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
from helpers import semantic_verification  # noqa: E402

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
        "artifact_ref": "synth_paper.json",
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
        """正例不得被反例修复误伤：覆盖完整 + 语义核验凭据齐备 → VERIFIED。"""
        quote = "roads reduce gene flow in fragmented landscapes"
        link = to_evidence_link(
            _evidence_record(quote, semantic_verification=semantic_verification(
                "EV-SYNTH-1", PROPOSITION)),
            PROPOSITION, "SUPPORT")
        self.assertEqual(link["alignment"], "VERIFIED")
        self.assertEqual(link["problems"], [])
        self.assertTrue(link["text_match"])

    def test_text_match_is_not_semantic_support(self):
        """`text_match=True` 只说明字面命中；缺语义凭据仍不得判为支持。

        这正是第二轮核查 P1-1 的核心：词面相似度不是语义验证。
        """
        record = _evidence_record("roads reduce gene flow in fragmented landscapes")
        link = to_evidence_link(record, PROPOSITION, "SUPPORT")
        self.assertTrue(link["text_match"])
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("SEMANTIC_VERIFICATION_REQUIRED", link["problems"])

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
    """F05/R05：审批必须绑定指纹、可信确认事件、会话、构想与版本。"""

    def _gap(self, approval, **overrides):
        gap = {
            "gap_id": "G-SYNTH-1",
            "session_id": "S-SYNTH-1",
            "idea_id": "I-SYNTH-1",
            "idea_version": 3,
            "gap_type": "SEARCH_GAP",
            "target_skill": "literature-discovery-acquisition",
            "question": "synthetic test question",
            "scope": {"population": "synthetic"},
            "approval": approval,
            "execution_status": "NOT_STARTED",
        }
        gap.update(overrides)
        return gap

    def _confirmed(self, **overrides):
        gap = self._gap({"status": "CONFIRMED", "approved_idea_version": 3,
                         "confirmed_event_id": "EV-CONFIRM-1"}, **overrides)
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        return gap

    def _store(self, gap, event_id="EV-CONFIRM-1", event_type="GAP_CONFIRMED",
               actor="user", execution_kind="USER", payload_over=None,
               session_id=None):
        folder = tempfile.mkdtemp(prefix="sf-f05-")
        store = SessionStore(folder)
        payload = {"gap_id": gap.get("gap_id"), "idea_id": gap.get("idea_id"),
                   "idea_version": gap.get("idea_version"),
                   "scope_fingerprint": scope_fingerprint(gap)}
        payload.update(payload_over or {})
        store.append_event({
            "schema_version": "0.1", "event_id": event_id,
            "session_id": session_id or gap.get("session_id"), "seq": 1,
            "type": event_type, "actor": actor, "execution_kind": execution_kind,
            "payload": payload, "created_at": "2026-09-13T00:00:00Z"})
        return store

    def test_bare_confirmed_string_is_not_dispatchable(self):
        """只有 status=CONFIRMED、无指纹 → APPROVAL_BINDING_MISSING 且须重新确认。"""
        result = prepare_dispatch(self._gap({"status": "CONFIRMED"}))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_BINDING_MISSING")
        self.assertTrue(result["must_reconfirm"])

    def test_fingerprint_without_confirmation_event_is_not_dispatchable(self):
        """有正确指纹但无可追溯的确认事件 → APPROVAL_CONFIRMATION_UNBOUND。"""
        gap = self._gap({"status": "CONFIRMED", "approved_idea_version": 3})
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        result = prepare_dispatch(gap)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_CONFIRMATION_UNBOUND")
        self.assertTrue(result["must_reconfirm"])

    def test_stale_fingerprint_is_not_dispatchable(self):
        """问题/范围变更后旧指纹失效 → SCOPE_CHANGED_APPROVAL_STALE。"""
        gap = self._confirmed()
        gap["approval"]["scope_fingerprint"] = "deadbeef"
        result = prepare_dispatch(gap)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "SCOPE_CHANGED_APPROVAL_STALE")

    def test_missing_trusted_context_is_not_dispatchable(self):
        """R05：没有可信事件上下文时失败关闭——指纹不是授权证明。"""
        result = prepare_dispatch(self._confirmed())
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_CONTEXT_MISSING")

    def test_gap_self_declared_events_are_not_trusted(self):
        """R05：gap 自带的 `_events` 属调用方自述，不得当作授权证据。"""
        gap = self._confirmed()
        gap["_events"] = [{"event_id": "EV-CONFIRM-1", "type": "GAP_CONFIRMED",
                           "actor": "user", "execution_kind": "USER",
                           "session_id": gap["session_id"], "payload": {
                               "gap_id": gap["gap_id"], "idea_id": gap["idea_id"],
                               "idea_version": gap["idea_version"],
                               "scope_fingerprint": scope_fingerprint(gap)}}]
        result = prepare_dispatch(gap)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_CONTEXT_MISSING")

    def test_missing_idea_version_binding_fails_closed(self):
        """缺 approved_idea_version 或 idea_version 任一侧即失败关闭。"""
        gap = self._confirmed()
        del gap["approval"]["approved_idea_version"]
        result = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_IDEA_VERSION_UNBOUND")

    def test_changed_idea_version_blocks_dispatch(self):
        """构想版本变化 → 旧确认失效。"""
        gap = self._confirmed()
        gap["idea_version"] = 4          # 批准的是 3，当前已改为 4
        result = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "SCOPE_CHANGED_APPROVAL_STALE")

    def test_nonexistent_event_is_refused(self):
        gap = self._confirmed()
        store = self._store(gap, event_id="EV-OTHER")
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_NOT_FOUND")

    def test_checkpoint_event_is_not_an_authorization(self):
        """R05 反例：同会话、同 ID，但事件是 CHECKPOINT → 不是用户授权。"""
        gap = self._confirmed()
        store = self._store(gap, event_type="CHECKPOINT", actor="moderator",
                            execution_kind="SYSTEM")
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_TYPE_INVALID")

    def test_assistant_emitted_confirmation_is_not_authorization(self):
        """R05 反例：类型正确但由助手/系统产生 → 不是用户授权。"""
        gap = self._confirmed()
        store = self._store(gap, actor="moderator", execution_kind="ROLE_SWITCH")
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_NOT_USER")

    def test_session_mismatch_is_refused(self):
        gap = self._confirmed()
        store = self._store(gap, session_id="S-OTHER")
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_SESSION_UNBOUND")

    def test_gap_mismatch_is_refused(self):
        """确认事件属于另一个缺口 → 不得为本次派发背书。"""
        gap = self._confirmed()
        store = self._store(gap, payload_over={"gap_id": "G-OTHER"})
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_GAP_MISMATCH")

    def test_event_scope_mismatch_is_refused(self):
        gap = self._confirmed()
        store = self._store(gap, payload_over={"scope_fingerprint": "deadbeef"})
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_SCOPE_MISMATCH")

    def test_event_without_scope_fingerprint_is_refused(self):
        gap = self._confirmed()
        store = self._store(gap, payload_over={"scope_fingerprint": None})
        result = prepare_dispatch(gap, session_store=store)
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "CONFIRMATION_EVENT_SCOPE_UNBOUND")

    def test_running_task_is_refused_as_in_flight(self):
        gap = self._confirmed(execution_status="RUNNING")
        result = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "ALREADY_RUNNING_IN_FLIGHT")
        self.assertTrue(result["idempotent_replay"])

    def test_fully_bound_approval_is_dispatchable(self):
        """正例：指纹 + 真实用户确认事件 + 版本一致 → 允许派发。"""
        gap = self._confirmed()
        result = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertTrue(result["dispatchable"], result)
        self.assertEqual(result["reason"], "OK")

    def test_unconfirmed_status_still_blocks(self):
        """非 CONFIRMED 状态仍按原契约阻断。"""
        result = prepare_dispatch(self._gap({"status": "PENDING"}))
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["reason"], "APPROVAL_NOT_CONFIRMED")


class TestR07EventFirstReplayBase(unittest.TestCase):
    """P2-4（第二轮核查）：快照不得在未封存检查点时被默认为可信重放基底。"""

    def _store(self, folder):
        store = SessionStore(folder)
        store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": None,
                             "ideas": []}, 0)
        store.append_event({"event_id": "E1", "session_id": "S1", "seq": 1,
                            "type": "ROLE_RESPONSE", "actor": "moderator",
                            "execution_kind": "ROLE_SWITCH",
                            "payload": {"field": "state", "value": "WAITING_USER"}})
        return store

    def test_unsealed_snapshot_is_not_claimed_consistent(self):
        with tempfile.TemporaryDirectory(prefix="sf-r07-") as folder:
            store = self._store(folder)
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            self.assertIn("SNAPSHOT_BASE_UNVERIFIED",
                          [d["kind"] for d in report["divergence"]])
            self.assertEqual(report["replay_base"], "snapshot(unverified)")

    def test_unlogged_field_is_detected_after_sealing(self):
        """审查反例：E1 只记录 state，快照却多出未记录的 idea。"""
        with tempfile.TemporaryDirectory(prefix="sf-r07-") as folder:
            store = self._store(folder)
            snap = store.load_snapshot()
            snap["state"] = "WAITING_USER"
            snap["last_applied_event_id"] = "E1"
            store.seal_checkpoint(snap, expected_revision=1)
            tampered = store.load_snapshot()
            tampered["ideas"] = [{"idea_id": "UNLOGGED"}]
            store.save_snapshot(tampered, expected_revision=tampered["revision"])
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            kinds = [d["kind"] for d in report["divergence"]]
            self.assertIn("STATE_PROJECTION_MISMATCH", kinds)
            self.assertEqual(report["replay_base"], "checkpoint.json")

    def test_sealed_checkpoint_replay_matches_events(self):
        with tempfile.TemporaryDirectory(prefix="sf-r07-") as folder:
            store = self._store(folder)
            snap = store.load_snapshot()
            snap["state"] = "WAITING_USER"
            snap["last_applied_event_id"] = "E1"
            store.seal_checkpoint(snap, expected_revision=1)
            store.append_event({"event_id": "E2", "session_id": "S1", "seq": 2,
                                "type": "ROLE_RESPONSE", "actor": "moderator",
                                "execution_kind": "ROLE_SWITCH",
                                "payload": {"field": "state", "value": "CLOSED"}})
            state = store.rebuild()["state"]
            store.seal_checkpoint(state, expected_revision=state["revision"])
            report = store.consistency_report()
            self.assertTrue(report["consistent"], report)

    def test_checkpoint_prefix_rewrite_is_detected(self):
        """检查点封存的事件前缀被改写 → 可信基底失效并报告。"""
        with tempfile.TemporaryDirectory(prefix="sf-r07-") as folder:
            store = self._store(folder)
            snap = store.load_snapshot()
            snap["state"] = "WAITING_USER"
            snap["last_applied_event_id"] = "E1"
            store.seal_checkpoint(snap, expected_revision=1)
            with open(store.events_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"event_id": "E1", "session_id": "S1", "seq": 1,
                                     "type": "ROLE_RESPONSE", "actor": "moderator",
                                     "execution_kind": "ROLE_SWITCH",
                                     "payload": {"field": "state",
                                                 "value": "TAMPERED"}}) + "\n")
            report = store.consistency_report()
            self.assertFalse(report["consistent"])
            self.assertIn("CHECKPOINT_EVENT_PREFIX_CHANGED",
                          [d["kind"] for d in report["divergence"]])

    def test_sealing_state_that_contradicts_events_is_refused(self):
        from shared.execution.session_store import ProjectionError
        with tempfile.TemporaryDirectory(prefix="sf-r07-") as folder:
            store = self._store(folder)
            snap = store.load_snapshot()
            snap["state"] = "DISCUSSING"
            snap["last_applied_event_id"] = "E1"
            with self.assertRaises(ProjectionError):
                store.seal_checkpoint(snap, expected_revision=1)


class TestR08GapSchemaStateConstraints(unittest.TestCase):
    """P2-5（第二轮核查）：非 CONFIRMED 的执行限制与空关联范围。"""

    def setUp(self):
        try:
            import jsonschema  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("jsonschema 不可用，无法执行契约校验")
        import jsonschema
        schema = json.loads((REPO_ROOT / "schemas" / "research_debate_gap.schema.json")
                            .read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft202012Validator(schema)

    def _placeholder(self):
        with tempfile.TemporaryDirectory(prefix="sf-r08-") as folder:
            store = SessionStore(folder)
            healed, _ = store.heal_referential_integrity({
                "ideas": [], "review_batches": [
                    {"batch_id": "B1", "resolution": "ESCALATED_TO_GAP",
                     "escalated_gap_id": "G1"}]})
            return healed["gap_requests"][0]

    def test_healed_placeholder_conforms(self):
        gap = self._placeholder()
        self.assertEqual([e.message for e in self.validator.iter_errors(gap)], [])
        self.assertTrue(gap["approval"]["healed_placeholder"])

    def test_placeholder_cannot_enter_execution(self):
        """审查反例：把占位改成 RUNNING 必须违反契约。"""
        gap = self._placeholder()
        gap["execution_status"] = "RUNNING"
        self.assertTrue([e for e in self.validator.iter_errors(gap)])

    def test_confirmed_requires_full_binding(self):
        gap = self._placeholder()
        gap["approval"] = dict(gap["approval"], status="CONFIRMED",
                               healed_placeholder=False)
        gap["execution_status"] = "NOT_STARTED"
        errors = [e.message for e in self.validator.iter_errors(gap)]
        self.assertTrue(errors, "CONFIRMED 且空关联必须被契约拒绝")

    def test_plain_pending_requires_fingerprint(self):
        """非占位的 PENDING 仍须给出可核对的指纹，null 放宽不得外溢。"""
        gap = self._placeholder()
        gap["approval"] = {"status": "PENDING", "scope_fingerprint": None,
                           "confirmed_event_id": None, "healed_placeholder": False}
        errors = [e.message for e in self.validator.iter_errors(gap)]
        self.assertTrue(errors, "普通 PENDING 缺指纹必须被拒绝")

    def test_rejected_gap_cannot_be_running(self):
        gap = self._placeholder()
        gap["approval"] = {"status": "REJECTED", "scope_fingerprint": None,
                           "confirmed_event_id": None, "healed_placeholder": False}
        gap["execution_status"] = "RUNNING"
        errors = [e.message for e in self.validator.iter_errors(gap)]
        self.assertTrue(errors, "被拒缺口不得处于 RUNNING")


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


class TestR01SemanticSupportGate(unittest.TestCase):
    """R01：设问、假说、转引等非实证引句不得被提升为 VERIFIED，必须绑定 artifact_ref。"""

    def test_research_question_is_not_verified(self):
        record = {
            "evidence_id": "E1",
            "artifact_ref": "paper.json",
            "verbatim_quote": "We tested whether roads reduce gene flow.",
            "location": {"page": 1},
            "checked_scope": "abstract",
            "claim_status": "supported",
        }
        link = to_evidence_link(record, "roads reduce gene flow", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("RESEARCH_QUESTION_NOT_RESULT", link["problems"])
        self.assertEqual(link["semantic_verification"]["semantic_role"], "RESEARCH_QUESTION")
        self.assertFalse(link["semantic_verification"]["is_empirical_result"])

    def test_hypothesis_is_not_verified(self):
        record = {
            "evidence_id": "E2",
            "artifact_ref": "paper.json",
            "verbatim_quote": "We hypothesized that roads reduce gene flow in amphibians.",
            "location": {"page": 1},
            "checked_scope": "abstract",
            "claim_status": "supported",
        }
        link = to_evidence_link(record, "roads reduce gene flow in amphibians", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertEqual(link["semantic_verification"]["semantic_role"], "HYPOTHESIS")

    def test_referenced_work_is_not_verified(self):
        record = {
            "evidence_id": "E3",
            "artifact_ref": "paper.json",
            "verbatim_quote": "Previous studies reported that roads reduce gene flow [12].",
            "location": {"page": 1},
            "checked_scope": "introduction",
            "claim_status": "supported",
        }
        link = to_evidence_link(record, "roads reduce gene flow", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertEqual(link["semantic_verification"]["semantic_role"], "REFERENCED_WORK")

    def test_empirical_result_is_verified(self):
        prop = "roads reduce gene flow by 40%"
        record = {
            "evidence_id": "E4",
            "artifact_ref": "paper.json",
            "verbatim_quote": "Our experimental results demonstrated that roads reduce gene flow by 40%.",
            "location": {"page": 3},
            "checked_scope": "results",
            "claim_status": "supported",
            "semantic_verification": semantic_verification("E4", prop),
        }
        link = to_evidence_link(record, prop, "SUPPORT")
        self.assertEqual(link["alignment"], "VERIFIED")
        self.assertEqual(link["semantic_verification"]["semantic_role"], "CURRENT_STUDY_RESULT")
        self.assertTrue(link["semantic_verification"]["is_empirical_result"])

    def test_review_counterexample_central_question_is_not_a_result(self):
        """第二轮核查反例 1：`Our central question is whether …` 不是实证结果。"""
        record = {
            "evidence_id": "E-Q1", "artifact_ref": "paper.json",
            "verbatim_quote": "Our central question is whether roads reduce gene flow.",
            "location": {"page": 1}, "checked_scope": "introduction",
        }
        link = to_evidence_link(record, "roads reduce gene flow", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("RESEARCH_QUESTION_NOT_RESULT", link["problems"])
        self.assertFalse(link["semantic_verification"]["is_empirical_result"])

    def test_review_counterexample_simulation_assumption_is_not_a_result(self):
        """第二轮核查反例 2：`For this simulation we assume …` 是模拟前提，不是发现。"""
        record = {
            "evidence_id": "E-S1", "artifact_ref": "paper.json",
            "verbatim_quote": "For this simulation we assume that roads reduce gene flow.",
            "location": {"page": 2}, "checked_scope": "methods",
        }
        link = to_evidence_link(record, "roads reduce gene flow", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("HYPOTHESIS_NOT_RESULT", link["problems"])
        self.assertFalse(link["semantic_verification"]["is_empirical_result"])

    def test_question_rewrite_variants_are_not_results(self):
        """问句改写族（不同措辞）必须同样被排除，而不是逐条加黑名单。"""
        props = "roads reduce gene flow"
        quotes = [
            "We investigated whether roads reduce gene flow.",
            "This study aimed to test whether roads reduce gene flow.",
            "It remains an open question whether roads reduce gene flow.",
            "道路是否降低基因流，是本研究旨在探究的问题。",
        ]
        for quote in quotes:
            record = {"evidence_id": "E-Q", "artifact_ref": "paper.json",
                      "verbatim_quote": quote, "location": {"page": 1},
                      "checked_scope": "introduction"}
            link = to_evidence_link(record, props, "SUPPORT")
            self.assertEqual(link["alignment"], "UNRESOLVED", quote)
            self.assertIn("RESEARCH_QUESTION_NOT_RESULT", link["problems"], quote)

    def test_unbound_semantic_credential_is_refused(self):
        """`status=VERIFIED` 但缺 evidence/proposition/verifier 绑定 → 不得升级。"""
        prop = "roads reduce gene flow"
        quote = "Our experimental results demonstrated that roads reduce gene flow."
        record = {"evidence_id": "E-U1", "artifact_ref": "paper.json",
                  "verbatim_quote": quote, "location": {"page": 3},
                  "checked_scope": "results",
                  "semantic_verification": {"status": "VERIFIED",
                                            "semantic_role": "CURRENT_STUDY_RESULT",
                                            "is_empirical_result": True}}
        link = to_evidence_link(record, prop, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("SEMANTIC_VERIFICATION_UNBOUND", link["problems"])

    def test_credential_for_another_proposition_is_refused(self):
        prop = "roads reduce gene flow"
        quote = "Our experimental results demonstrated that roads reduce gene flow."
        record = {"evidence_id": "E-U2", "artifact_ref": "paper.json",
                  "verbatim_quote": quote, "location": {"page": 3},
                  "checked_scope": "results",
                  "semantic_verification": semantic_verification("E-U2", "other proposition")}
        link = to_evidence_link(record, prop, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("SEMANTIC_VERIFICATION_PROPOSITION_MISMATCH", link["problems"])

    def test_stale_credential_after_proposition_version_change_is_refused(self):
        """命题版本变化 → 旧语义核验凭据失效。"""
        prop = "roads reduce gene flow"
        quote = "Our experimental results demonstrated that roads reduce gene flow."
        record = {"evidence_id": "E-U3", "artifact_ref": "paper.json",
                  "verbatim_quote": quote, "location": {"page": 3},
                  "checked_scope": "results", "idea_version": 5,
                  "semantic_verification": semantic_verification("E-U3", prop,
                                                                 idea_version=4)}
        link = to_evidence_link(record, prop, "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("SEMANTIC_VERIFICATION_STALE", link["problems"])

    def test_bound_credential_at_current_version_still_verifies(self):
        """正例：绑定了当前命题版本的真实实证结果仍应通过。"""
        prop = "roads reduce gene flow"
        quote = "Our experimental results demonstrated that roads reduce gene flow."
        record = {"evidence_id": "E-OK", "artifact_ref": "paper.json",
                  "verbatim_quote": quote, "location": {"page": 3},
                  "checked_scope": "results", "idea_version": 5,
                  "semantic_verification": semantic_verification("E-OK", prop,
                                                                 idea_version=5)}
        link = to_evidence_link(record, prop, "SUPPORT")
        self.assertEqual(link["alignment"], "VERIFIED", link)
        self.assertEqual(link["problems"], [])

    def test_missing_artifact_ref_fails_closed(self):
        record = {
            "evidence_id": "E5",
            "artifact_ref": "",
            "verbatim_quote": "Our results demonstrated that roads reduce gene flow.",
            "location": {"page": 1},
            "checked_scope": "results",
            "claim_status": "supported",
        }
        link = to_evidence_link(record, "roads reduce gene flow", "SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("MISSING_ARTIFACT_REF", link["problems"])


class TestR02UnitPreservationAndBareInteger(unittest.TestCase):
    """R02：单位保真（不退化为裸数）、支持合法单位别名与纯整数审计。"""

    def setUp(self):
        self.audit = _load_quote_audit()

    def test_unit_swap_fails_gate(self):
        source = "The reaction volume was 20 microliters for every sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "20 milliliters"}]},
            source,
        )
        self.assertTrue(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_not_found_in_source"], 1)

    def test_unit_alias_passes_gate(self):
        source = "The reaction volume was 20 microliters for every sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "20 µl"}]},
            source,
        )
        self.assertFalse(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_bare_integer_mismatch_fails_gate(self):
        source = "The study included 20 samples in the experiment."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": 999}]},
            source,
        )
        self.assertTrue(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_not_found_in_source"], 1)

    def test_bare_integer_match_passes_gate(self):
        source = "The study included 20 samples in the experiment."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": 20}]},
            source,
        )
        self.assertFalse(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    # --- 第二轮核查 P1-2 的五个反例 ---

    def test_decimal_unit_swap_fails_gate(self):
        """`2.5 microliters` ↛ `2.5 milliliters`（旧实现因丢单位而放行）。"""
        source = "The measured reaction volume was 2.5 microliters in each experiment."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source,
                                   "extracted_value": "2.5 milliliters"}]}, source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_decimal_suffix_truncation_fails_gate(self):
        """`15.4%` ↛ `4%`（旧实现把 `4%` 当作 15.4% 的子串命中）。"""
        source = "The observed proportion was 15.4% for this population."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "4%"}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_integer_truncation_fails_gate(self):
        """`20.5` ↛ 整数 `20`。"""
        source = "The measured quantity was 20.5 for this sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": 20}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_percent_never_matches_length(self):
        """量纲不同：`0.054 meters` ↛ `5.4%`。"""
        source = "The distance measured in this experiment was 0.054 meters."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_mismatched_unit_value_with_uppercase_symbol_fails_gate(self):
        """`20 mL` ↛ `999 mL`（旧实现抽不出 token，value_checked=0 直接放行）。"""
        source = "The reaction volume was 20 mL for each sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "999 mL"}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])
        self.assertEqual(rep["summary"]["value_checked"], 1)

    def test_case_sensitive_symbols_are_not_folded(self):
        """`ML`（兆升）不得被当作 `mL`（毫升）的同义词。"""
        source = "The reaction volume was 20 mL for each sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "20 ML"}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_declared_ratio_field_allows_percent_ratio_conversion(self):
        """字段显式声明为比例时，`0.054` ↔ `5.4%` 才允许互认。"""
        source = "The observed proportion was 5.4% in this population."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "0.054",
                                   "value_type": "proportion"}]}, source)
        self.assertFalse(self.audit.gate_failed(rep, strict=True), rep["summary"])
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_undeclared_ratio_conversion_is_refused(self):
        """未声明字段类型时，百分比与裸比例不得互认。"""
        source = "The observed proportion was 5.4% in this population."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "0.054"}]},
            source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])

    def test_legit_unit_conversion_within_dimension_passes(self):
        """同量纲的合法换算正例：`2.5 mL` == `2500 µL`。"""
        source = "Each tube received 2500 µL of buffer before incubation."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "2.5 mL"}]},
            source)
        self.assertFalse(self.audit.gate_failed(rep, strict=True), rep["summary"])
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_unparsable_numeric_value_is_flagged_not_passed(self):
        """含数字却解析不出数量 → 待核验并阻断，不得 value_checked=0 放行。"""
        source = "The reaction volume was 20 mL for each sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source,
                                   "extracted_value": "999 zorks"}]}, source)
        self.assertTrue(self.audit.gate_failed(rep, strict=True), rep["summary"])
        self.assertEqual(rep["summary"]["unverified"], 1)


class TestR03BoundaryAndSignAudit(unittest.TestCase):
    """R03：行首/行尾数值匹配与正负号边界隔离。"""

    def setUp(self):
        self.audit = _load_quote_audit()

    def test_positive_value_at_sentence_start_passes(self):
        source = "5.4% was the observed proportion in the sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source,
        )
        self.assertFalse(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_positive_value_at_sentence_end_passes(self):
        source = "The observed proportion in the sample was 5.4%."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source,
        )
        self.assertFalse(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_value_enclosed_in_parentheses_passes(self):
        source = "We observed significant reduction (5.4%) in the sample."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source,
        )
        self.assertFalse(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_aligned"], 1)

    def test_sign_swap_fails_gate(self):
        source = "The estimated effect was -5.4% in the tested population."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source,
        )
        self.assertTrue(self.audit.gate_failed(rep, strict=True))
        self.assertEqual(rep["summary"]["value_not_found_in_source"], 1)

    def test_prefix_number_collision_fails_gate(self):
        source = "The estimated effect was 55.4% in the population."
        rep = self.audit.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": "5.4%"}]},
            source,
        )
        self.assertTrue(self.audit.gate_failed(rep, strict=True))


class TestR04NewlineBoundaryAppend(unittest.TestCase):
    """R04：事件日志追加时保护记录边界，防止无尾随换行导致行拼接损坏。"""

    def test_valid_json_no_newline_append_succeeds_and_both_readable(self):
        with tempfile.TemporaryDirectory(prefix="sf-r04-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "WAITING_USER", "last_applied_event_id": "E1"}, 0)
            with open(store.events_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"event_id": "E1", "payload": {"field": "state", "value": "WAITING_USER"}}))
            appended = store.append_event({"event_id": "E2", "payload": {"field": "state", "value": "CLOSED"}})
            self.assertTrue(appended)
            events = store._read_events()["events"]
            self.assertEqual([e["event_id"] for e in events], ["E1", "E2"])

    def test_invalid_half_line_refuses_append(self):
        with tempfile.TemporaryDirectory(prefix="sf-r04-") as folder:
            store = SessionStore(folder)
            with open(store.events_path, "w", encoding="utf-8") as fh:
                fh.write('{"event_id": "E1", "payload":')
            with self.assertRaises(CorruptEventLog) as ctx:
                store.append_event({"event_id": "E2", "payload": {"field": "state", "value": "CLOSED"}})
            self.assertEqual(ctx.exception.details.get("reason"), "RECOVERY_REQUIRED")


class TestR05AuthorizationTruth(unittest.TestCase):
    """R05（第二轮核查）：只有"用户确认过"才算授权，运行态重复请求要被挡。"""

    def _gap(self, **overrides):
        gap = {
            "gap_id": "G1", "session_id": "S1", "idea_id": "I1", "idea_version": 1,
            "gap_type": "SEARCH_GAP", "question": "synthetic question",
            "target_skill": "literature-discovery-acquisition",
            "approval": {"status": "CONFIRMED", "confirmed_event_id": "EV-1",
                         "approved_idea_version": 1},
            "execution_status": "NOT_STARTED",
        }
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        gap.update(overrides)
        return gap

    def _store(self, gap, **event_over):
        folder = tempfile.mkdtemp(prefix="sf-r05-")
        store = SessionStore(folder)
        event = {
            "schema_version": "0.1", "event_id": "EV-1", "session_id": gap["session_id"],
            "seq": 1, "type": "GAP_CONFIRMED", "actor": "user", "execution_kind": "USER",
            "payload": {"gap_id": gap["gap_id"], "idea_id": gap["idea_id"],
                        "idea_version": gap["idea_version"],
                        "scope_fingerprint": scope_fingerprint(gap)},
            "created_at": "2026-09-13T00:00:00Z",
        }
        event.update(event_over)
        store.append_event(event)
        return store

    def test_running_status_blocks_dispatch(self):
        gap = self._gap(execution_status="RUNNING")
        res = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertFalse(res["dispatchable"])
        self.assertEqual(res["reason"], "ALREADY_RUNNING_IN_FLIGHT")
        self.assertTrue(res["idempotent_replay"])

    def test_in_progress_status_blocks_dispatch(self):
        gap = self._gap(execution_status="IN_PROGRESS")
        res = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertFalse(res["dispatchable"])
        self.assertEqual(res["reason"], "ALREADY_RUNNING_IN_FLIGHT")

    def test_nonexistent_event_in_store_blocks_dispatch(self):
        gap = self._gap()
        store = self._store(gap, event_id="EV-OTHER")
        res = prepare_dispatch(gap, session_store=store)
        self.assertFalse(res["dispatchable"])
        self.assertEqual(res["reason"], "CONFIRMATION_EVENT_NOT_FOUND")

    def test_empty_payload_event_is_not_a_confirmation(self):
        """旧实现只要 ID 存在即放行；空载荷事件现在必须被拒。"""
        gap = self._gap()
        store = self._store(gap, payload={})
        res = prepare_dispatch(gap, session_store=store)
        self.assertFalse(res["dispatchable"])
        self.assertIn(res["reason"], ("CONFIRMATION_EVENT_GAP_MISMATCH",
                                      "APPROVAL_IDEA_UNBOUND"))

    def test_confirmed_event_present_in_store_allows_dispatch(self):
        gap = self._gap()
        res = prepare_dispatch(gap, session_store=self._store(gap))
        self.assertTrue(res["dispatchable"], res)
        self.assertEqual(res["reason"], "OK")


class TestR06HealedGapSchemaValidation(unittest.TestCase):
    """R06：孤儿引用修复产物完整符合 schemas/research_debate_gap.schema.json。"""

    def test_healed_placeholder_conforms_to_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")

        schema_path = os.path.join(REPO_ROOT, "schemas", "research_debate_gap.schema.json")
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
        validator = jsonschema.Draft202012Validator(schema)

        with tempfile.TemporaryDirectory(prefix="sf-r06-") as folder:
            store = SessionStore(folder)
            session = {
                "ideas": [{"idea_id": "I1"}, {"idea_id": "I2"}],
                "review_batches": [{"batch_id": "B1", "resolution": "ESCALATED_TO_GAP", "escalated_gap_id": "G1"}],
            }
            healed, actions = store.heal_referential_integrity(session)
            placeholder = healed["gap_requests"][0]
            errors = list(validator.iter_errors(placeholder))
            self.assertEqual([e.message for e in errors], [])
            self.assertEqual(placeholder["schema_version"], "0.1")
            self.assertEqual(placeholder["approval"]["status"], "PENDING")
            self.assertIsNone(placeholder["idea_id"])


if __name__ == "__main__":
    unittest.main()
