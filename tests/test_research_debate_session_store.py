# -*- coding: utf-8 -*-
"""M2：research-idea-debate 会话持久化的行为测试。

覆盖设计稿 §6.2 / §12.3 要求的行为，且**逐条针对真实故障**：

- 事件先落盘、快照后原子替换；
- `event_id` 幂等（重复事件不得再次应用）；
- 快照与事件日志冲突时以事件为准，并**显式报告差异**；
- 末尾不完整事件隔离后忽略；**中段损坏则停止并报告**；
- 并发 `revision` 冲突拒绝覆盖；
- 恢复简报字段齐全且不重问已知信息；
- 单写者语义：身份字段不可被事件改写。

配套 CLI：`skills/research-idea-debate/scripts/session_store_cli.py`。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401

from shared.execution import (  # noqa: E402
    SessionStore, CorruptEventLog, RevisionConflict, ProjectionError,
    EVENTS_FILENAME, SESSION_FILENAME,
)

REPO_ROOT = helpers.REPO_ROOT
CLI = REPO_ROOT / "skills" / "research-idea-debate" / "scripts" / "session_store_cli.py"


def _base_session():
    return {
        "schema_version": "0.1",
        "session_id": "SESS-M2-TEST",
        "run_id": "RUN-M2-TEST",
        "revision": 1,
        "mode": "explore",
        "state": "DISCUSSING",
        "original_prompt": "起不来可能不只是郁闭度的事",
        "current_question": "更新不良指什么",
        "execution": {
            "depth": "standard",
            "selection_status": "confirmed",
            "budget": {"max_rounds": 8, "max_review_batches": 2, "max_subtasks_per_batch": 2,
                        "max_active_seconds": 1800, "max_events": 400},
            "usage": {"rounds_used": 0, "review_batches_used": 0, "events_written": 0,
                       "tokens_observed": None, "tokens_metering": "UNAVAILABLE"},
        },
        "ideas": [{"idea_id": "I1", "maturation": "RAW", "versions": [
            {"version": 1, "parent_version": None, "proposition": "p", "origin": "USER",
             "epistemic_status": "INTUITION", "disposition": "ACTIVE", "revision_reason": "r"}]}],
        "pending_question": {"question_id": "Q1", "role_id": "concept_clarifier",
                              "question_type": "CLARIFICATION", "text": "更新不良指什么",
                              "target_version": 1},
        "open_questions": ["基准未定"],
        "gap_requests": [],
        "rounds": [],
        "last_applied_event_id": None,
    }


class _TmpStoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rid-m2-")
        self.dir = os.path.join(self.tmp, "sessions", "SESS-M2-TEST")
        os.makedirs(self.dir)
        self.store = SessionStore(self.dir)
        self.session = _base_session()
        self.store.save_snapshot(self.session, expected_revision=0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _event(self, eid, field, value, etype="ROLE_RESPONSE"):
        return {"schema_version": "0.1", "event_id": eid, "session_id": "SESS-M2-TEST",
                "seq": 1, "type": etype, "actor": "moderator", "execution_kind": "ROLE_SWITCH",
                "payload": {"field": field, "value": value}, "created_at": None}


class TestAppendAndReplay(_TmpStoreCase):
    def test_events_persist_before_snapshot(self):
        """事件先落盘：追加后立刻可从日志读到，无需写快照。"""
        self.assertTrue(self.store.append_event(self._event("E1", "state", "WAITING_USER")))
        with open(os.path.join(self.dir, EVENTS_FILENAME), encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 1)
        # 快照仍是旧值——说明事件是独立先落盘的
        self.assertEqual(self.store.load_snapshot()["state"], "DISCUSSING")

    def test_replay_applies_events_in_order(self):
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        self.store.append_event(self._event("E2", "current_question", "新的焦点问题"))
        rebuilt = self.store.rebuild()
        self.assertEqual(rebuilt["state"]["state"], "WAITING_USER")
        self.assertEqual(rebuilt["state"]["current_question"], "新的焦点问题")
        self.assertEqual(rebuilt["state"]["last_applied_event_id"], "E2")

    def test_event_id_is_idempotent(self):
        ev = self._event("E1", "state", "WAITING_USER")
        self.assertTrue(self.store.append_event(ev))
        self.assertFalse(self.store.append_event(ev), "重复 event_id 必须幂等跳过")
        with open(os.path.join(self.dir, EVENTS_FILENAME), encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 1, "重复事件不得被追加两次")

    def test_identity_fields_cannot_be_rewritten(self):
        self.store.append_event(self._event("E1", "session_id", "HACKED"))
        with self.assertRaises(ProjectionError):
            self.store.rebuild()

    def test_unlisted_field_cannot_be_rewritten(self):
        self.store.append_event(self._event("E1", "run_id", "HACKED"))
        with self.assertRaises(ProjectionError):
            self.store.rebuild()

    def test_idea_projection_replaces_wholesale(self):
        """整值投影：ideas 的 payload 是该字段的完整新值。"""
        new_ideas = [{"idea_id": "I1", "maturation": "DEVELOPING", "versions": [
            {"version": 1, "parent_version": None, "proposition": "p", "origin": "USER",
             "epistemic_status": "HYPOTHESIS", "disposition": "REVISED", "revision_reason": "r"},
            {"version": 2, "parent_version": 1, "proposition": "p2", "origin": "USER",
             "epistemic_status": "HYPOTHESIS", "disposition": "ACTIVE", "revision_reason": "r2"}]}]
        self.store.append_event(self._event("E1", "ideas", new_ideas, etype="IDEA_REVISED"))
        rebuilt = self.store.rebuild()
        self.assertEqual(rebuilt["state"]["ideas"][0]["maturation"], "DEVELOPING")
        self.assertEqual(len(rebuilt["state"]["ideas"][0]["versions"]), 2)


class TestConsistency(_TmpStoreCase):
    def test_consistent_when_snapshot_matches_sealed_checkpoint(self):
        """快照与"检查点 + 其后事件"的重放一致时才算一致。

        2026-09-13 第二轮核查 P2-4：未封存检查点的会话不再默认判为一致——
        任意当前快照都可能含事件未记录的修改。
        """
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        snap = self.store.load_snapshot()
        snap["state"] = "WAITING_USER"
        snap["last_applied_event_id"] = "E1"
        self.store.seal_checkpoint(snap, expected_revision=1)
        report = self.store.consistency_report()
        self.assertTrue(report["consistent"], report)
        self.assertEqual(report["authoritative_source"], EVENTS_FILENAME)
        self.assertEqual(report["replay_base"], "checkpoint.json")

    def test_unsealed_session_is_not_claimed_consistent(self):
        """没有检查点时必须如实报告基底未验证，而不是默认快照可信。"""
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        snap = self.store.load_snapshot()
        snap["state"] = "WAITING_USER"
        snap["last_applied_event_id"] = "E1"
        self.store.save_snapshot(snap, expected_revision=1)
        report = self.store.consistency_report()
        self.assertFalse(report["consistent"])
        self.assertIn("SNAPSHOT_BASE_UNVERIFIED",
                      [d["kind"] for d in report["divergence"]])

    def test_unlogged_snapshot_field_is_detected_after_sealing(self):
        """R04 反例：封存后往快照里塞事件未记录的 idea → 必须报差异。"""
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        snap = self.store.load_snapshot()
        snap["state"] = "WAITING_USER"
        snap["last_applied_event_id"] = "E1"
        self.store.seal_checkpoint(snap, expected_revision=1)
        unlogged = self.store.load_snapshot()
        unlogged["ideas"] = [{"idea_id": "UNLOGGED"}]
        self.store.save_snapshot(unlogged, expected_revision=unlogged["revision"])
        report = self.store.consistency_report()
        self.assertFalse(report["consistent"])
        kinds = [d["kind"] for d in report["divergence"]]
        self.assertIn("STATE_PROJECTION_MISMATCH", kinds)
        mismatch = [d for d in report["divergence"]
                    if d["kind"] == "STATE_PROJECTION_MISMATCH"][0]
        self.assertIn("ideas", mismatch["fields"])

    def test_sealing_state_that_contradicts_events_is_refused(self):
        """封存的状态与事件冲突时拒绝——可信基底不能与真源矛盾。"""
        from shared.execution import ProjectionError
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        snap = self.store.load_snapshot()
        snap["state"] = "DISCUSSING"          # 事件说 WAITING_USER
        snap["last_applied_event_id"] = "E1"
        with self.assertRaises(ProjectionError):
            self.store.seal_checkpoint(snap, expected_revision=1)

    def test_checkpoint_records_fields_not_derived_from_events(self):
        """基底里"不是事件推出来的"字段必须逐项记录，便于审计。"""
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        snap = self.store.load_snapshot()
        snap["state"] = "WAITING_USER"
        snap["last_applied_event_id"] = "E1"
        self.store.seal_checkpoint(snap, expected_revision=1)
        checkpoint = self.store.load_checkpoint()
        self.assertIn("ideas", checkpoint["inherited_fields"])
        self.assertNotIn("state", checkpoint["inherited_fields"])

    def test_mismatch_is_reported_not_silently_resolved(self):
        """快照与事件不一致时必须报告差异，且指明以事件为准。"""
        self.store.append_event(self._event("E1", "state", "WAITING_USER"))
        report = self.store.consistency_report()
        self.assertFalse(report["consistent"])
        kinds = [d["kind"] for d in report["divergence"]]
        self.assertIn("LAST_APPLIED_EVENT_MISMATCH", kinds)
        self.assertEqual(report["authoritative_source"], EVENTS_FILENAME)
        # 重放值才是权威
        self.assertEqual(report["replayed_last_applied_event_id"], "E1")
        self.assertIsNone(report["snapshot_last_applied_event_id"])


class TestCorruptionHandling(_TmpStoreCase):
    def _write_events(self, lines):
        with open(os.path.join(self.dir, EVENTS_FILENAME), "w", encoding="utf-8") as fh:
            fh.write("".join(lines))

    def test_incomplete_tail_is_quarantined_and_ignored(self):
        good = json.dumps(self._event("E1", "state", "WAITING_USER"), ensure_ascii=False) + "\n"
        self._write_events([good, '{"event_id": "E2", "payload": {"field": '])  # 末尾截断
        rebuilt = self.store.rebuild()
        self.assertEqual(rebuilt["events_applied"], 1)
        self.assertIsNotNone(rebuilt["quarantined_tail"])
        quarantined = [f for f in os.listdir(self.dir) if "corrupt-tail" in f]
        self.assertEqual(len(quarantined), 1, "末尾损坏行必须留隔离副本")

    def test_mid_log_corruption_stops_and_reports(self):
        """坏行位于中段——其后仍有有效行——必须停止并报告，不得当尾部忽略。"""
        good = json.dumps(self._event("E1", "state", "WAITING_USER"), ensure_ascii=False) + "\n"
        good2 = json.dumps(self._event("E3", "state", "CHECKPOINT"), ensure_ascii=False) + "\n"
        self._write_events([good, "{ this is not json }\n", good2])
        with self.assertRaises(CorruptEventLog) as ctx:
            self.store.rebuild()
        self.assertEqual(ctx.exception.details["line"], 2)
        self.assertIn("中段损坏", str(ctx.exception))
        # 中段损坏不得留下隔离副本（隔离只用于尾部）
        self.assertEqual([f for f in os.listdir(self.dir) if "corrupt-tail" in f], [])


class TestRevisionConflict(_TmpStoreCase):
    def test_stale_revision_refuses_to_overwrite(self):
        with self.assertRaises(RevisionConflict):
            self.store.save_snapshot(self.session, expected_revision=99)

    def test_snapshot_write_increments_revision_atomically(self):
        saved = self.store.save_snapshot(self.session, expected_revision=1)
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(self.store.load_snapshot()["revision"], 2)
        # 临时文件不得残留
        leftovers = [f for f in os.listdir(self.dir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestRecoveryBriefing(_TmpStoreCase):
    def test_briefing_has_all_required_fields(self):
        self.store.append_event(self._event("E1", "state", "CHECKPOINT"))
        rec = self.store.recover()
        b = rec["briefing"]
        for key in ("session_id", "mode", "state", "current_question", "pending_question",
                    "pending_role", "open_questions", "gaps_pending",
                    "rounds_used", "rounds_cap"):
            self.assertIn(key, b, "恢复简报缺少字段 %s" % key)
        self.assertEqual(b["state"], "CHECKPOINT")
        self.assertEqual(b["pending_role"], "concept_clarifier")
        self.assertEqual(b["open_questions"], 1)

    def test_recovery_does_not_grant_new_authorisation(self):
        """恢复不改变预算：上限沿用原值。"""
        rec = self.store.recover()
        self.assertEqual(rec["briefing"]["rounds_cap"], 8)
        self.assertEqual(rec["briefing"]["rounds_used"], 0)

    def test_usage_ledger_appends_without_overwrite(self):
        self.store.append_usage({"round": 1, "active_seconds": 30})
        self.store.append_usage({"round": 2, "active_seconds": 25})
        self.assertEqual(len(self.store.read_usage()), 2)


class TestCliSurface(unittest.TestCase):
    """CLI 必须可执行且失败时给出结构化状态码。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rid-m2-cli-")
        self.dir = os.path.join(self.tmp, "s")
        os.makedirs(self.dir)
        store = SessionStore(self.dir)
        store.save_snapshot(_base_session(), expected_revision=0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)
        proc = subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout, "_err": proc.stderr}
        return proc.returncode, payload

    def test_append_rebuild_recover_roundtrip(self):
        ev = json.dumps({"schema_version": "0.1", "event_id": "E1", "session_id": "S",
                         "seq": 1, "type": "ROLE_RESPONSE", "actor": "moderator",
                         "execution_kind": "ROLE_SWITCH",
                         "payload": {"field": "state", "value": "WAITING_USER"},
                         "created_at": None}, ensure_ascii=False)
        code, out = self._run("append", self.dir, "--event-json", ev)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["applied"])

        code, out = self._run("rebuild", self.dir)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["state"]["state"], "WAITING_USER")

        code, out = self._run("recover", self.dir)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["briefing"]["state"], "WAITING_USER")

    def test_check_reports_inconsistency_with_exit_1(self):
        ev = json.dumps({"schema_version": "0.1", "event_id": "E1", "session_id": "S",
                         "seq": 1, "type": "ROLE_RESPONSE", "actor": "moderator",
                         "execution_kind": "ROLE_SWITCH",
                         "payload": {"field": "state", "value": "WAITING_USER"},
                         "created_at": None}, ensure_ascii=False)
        self._run("append", self.dir, "--event-json", ev)
        code, out = self._run("check", self.dir)
        self.assertEqual(code, 1, out)
        self.assertEqual(out["status"], "INCONSISTENT")

    def test_revision_conflict_exit_1(self):
        code, out = self._run("snapshot", self.dir, "--expected-revision", "99")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["status"], "REVISION_CONFLICT")

    def test_bad_json_exit_2(self):
        code, out = self._run("append", self.dir, "--event-json", "{oops")
        self.assertEqual(code, 2, out)
        self.assertEqual(out["status"], "INPUT_ERROR")

    def test_missing_argument_exit_2(self):
        code, out = self._run("append", self.dir)
        self.assertEqual(code, 2, out)

    def test_self_test_via_helpers_is_importable(self):
        proc = subprocess.run([sys.executable, "-m", "py_compile", str(CLI)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
