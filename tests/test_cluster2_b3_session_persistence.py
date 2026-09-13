# -*- coding: utf-8 -*-
"""B3 批次（session 持久层族）回归：2026-09-13 第二轮集群测试决议 H-08/09②/10/13/15/16/45/101 + H-02 词表接入。

每条用例移植四个 REPORT 的实测夹具（夹具来源在 docstring 中标注）：

- **H-15/H-101**（INT-A-01 / DEB-V-08 / INT-R-01，05-integration runner+adversary、
  01-debate verifier）：5 进程 ×200 次自报成功 = 实落盘 1000 条零丢失（D:\\ NTFS
  本机路径跨进程实测）；usage_ledger 并发恒合法 JSONL；锁 pid 属主核对 / deadline
  全路径生效 / stale 锁 rename-aside 回收。
- **H-08/H-16**（INT-A-05 §一伪造 commit_journal 复活授权全链；DEB-R-01 / DEB-V-09 /
  DEB-V-10 / INT-R-09）：recover_commit 三守卫逐一拒绝伪造/陈旧 journal；.rejected
  归档 + RECOVERY_COMMIT_* 审计事件；恢复路径真实调用；CLI recover-commit 收敛
  INCOMPLETE_COMMIT。
- **H-10**（DEB-V-01）：applied 判定 `is not True`——"false"/0/字符串/未戳记日志事件
  不得放行；SessionStore.append_event 为落盘事件补写 applied=True（持久层不变式）。
- **H-13**（DEB-V-06）：复核记录缺 evidence_id 时绑定核对不得空放行。
- **H-45**（INT-A-06）：同一 gap_id 双重消费被拒；已推进缺口的重复派发被拒。
- **H-09②**（INT-A-16）：跨会话搬运 events.jsonl → prepare_dispatch 拒绝。
- **H-02**（DEB-V-05）：don't 类收缩词经共享词表（shared/text/polarity.py）进入否定判定。

单进程时序与 kill 恢复零回归：TestKillRecoveryHonesty 做 20 次 kill（封存窗口 10 次 +
持锁追加窗口 10 次）诚实恢复全绿。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

import helpers  # noqa: F401

from shared.execution.session_store import (  # noqa: E402
    SessionStore,
    RevisionConflict,
    CorruptEventLog,
    _SessionFileLock,
    EVENTS_FILENAME,
)
from shared.execution.debate_handoff import (  # noqa: E402
    prepare_dispatch,
    scope_fingerprint,
    to_evidence_link,
    detect_negation_mismatch,
    NEGATION_MARKERS,
)
from shared.text import polarity as shared_polarity  # noqa: E402

REPO_ROOT = str(helpers.REPO_ROOT)
CLI = os.path.join(REPO_ROOT, "skills", "research-idea-debate", "scripts",
                   "session_store_cli.py")

SESSION_ID = "sess-b3-001"
GAP_ID = "GAP-1"


# --------------------------------------------------------------------- 夹具
def _gap(session_id=SESSION_ID, gap_id=GAP_ID, status="CONFIRMED", fp=None, ver=1,
         execution_status="NOT_STARTED"):
    """与 05-integration/adversary a7_dispatch.py 的 make_gap 同构。"""
    gap = {
        "session_id": session_id, "gap_id": gap_id, "idea_id": "IDEA-1",
        "idea_version": ver, "gap_type": "SEARCH_GAP",
        "target_skill": "literature-discovery-acquisition",
        "question": "低氧条件下偏压钙钛矿电池的衰减机制是否已被系统研究",
        "scope": {"topic": "perovskite low-oxygen degradation", "time_range": "2020-2026"},
        "decision_impact": "Required to unblock proposition evaluation.",
        "approval": {"status": status, "confirmed_event_id": "E-CONF-001",
                     "scope_fingerprint": fp, "approved_idea_version": ver},
        "execution_status": execution_status,
        "result_refs": [],
    }
    gap["approval"]["scope_fingerprint"] = fp or scope_fingerprint(gap)
    return gap


def _confirm_event(store, fp, event_id="E-CONF-001", session_id=SESSION_ID,
                   gap_id=GAP_ID, applied=...):
    """写入用户确认事件；applied=... 表示不显式携带（由 store 戳记 applied=True）。"""
    event = {
        "schema_version": "0.1", "event_id": event_id, "session_id": session_id,
        "seq": 1, "type": "GAP_CONFIRMED", "actor": "user", "execution_kind": "USER",
        "payload": {"gap_id": gap_id, "idea_id": "IDEA-1", "idea_version": 1,
                    "scope_fingerprint": fp},
        "created_at": "2026-09-13T00:00:00Z",
    }
    if applied is not ...:
        event["applied"] = applied
    store.append_event(event)
    return event


def _authorized_store(folder, session_id=SESSION_ID, with_snapshot=True):
    """带确认事件（可选带快照声明身份）的会话存储。"""
    store = SessionStore(folder)
    if with_snapshot:
        store.save_snapshot({"schema_version": "0.1", "session_id": session_id,
                             "state": "WAITING_USER", "last_applied_event_id": None}, 0)
    fp = scope_fingerprint(_gap(session_id=session_id))
    _confirm_event(store, fp, session_id=session_id)
    return store, fp


def _log_events(folder):
    path = os.path.join(folder, EVENTS_FILENAME)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
    return out


def _interrupted_commit(folder):
    """制造真实中断提交：seal 在 commit_journal 落盘后、写两文件前"崩溃"。"""
    store = SessionStore(folder)
    store.save_snapshot({"schema_version": "0.1", "session_id": SESSION_ID,
                         "state": "WAITING_USER", "last_applied_event_id": None}, 0)
    store.append_event({"schema_version": "0.1", "event_id": "K1",
                        "session_id": SESSION_ID, "seq": 1, "type": "ROLE_RESPONSE",
                        "actor": "moderator", "execution_kind": "ROLE_SWITCH",
                        "payload": {"field": "state", "value": "DISCUSSING"},
                        "created_at": None})

    class _CrashAfterJournal(Exception):
        pass

    original = store._atomic_write_json

    def crash_after_journal(path, payload):
        original(path, payload)
        if os.path.basename(path) == "commit_journal.json":
            raise _CrashAfterJournal()

    store._atomic_write_json = crash_after_journal
    try:
        store.seal_checkpoint({"session_id": SESSION_ID, "state": "DISCUSSING",
                               "last_applied_event_id": "K1"}, 1)
    except _CrashAfterJournal:
        pass
    return store


def _run_cli(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT
    proc = subprocess.run([sys.executable, CLI, *args],
                          capture_output=True, text=True, env=env, cwd=REPO_ROOT)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"_raw": proc.stdout, "_err": proc.stderr}
    return proc.returncode, payload


# ----------------------------------------------------------------- H-15 并发
WORKER_SCRIPT = textwrap.dedent("""
    import json, os, sys
    sys.path.insert(0, sys.argv[1])
    from shared.execution.session_store import SessionStore
    folder, wid, count, mode = sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
    st = SessionStore(folder)
    ok = 0
    for i in range(count):
        if mode == "ledger":
            st.append_usage({"kind": "model_request", "count": 1, "worker": wid, "i": i})
        else:
            ev = {"schema_version": "0.1", "event_id": "CONC-%s-%04d" % (wid, i),
                  "session_id": "SESS-CONC", "seq": i, "type": "ROLE_RESPONSE",
                  "actor": "worker-%s" % wid, "execution_kind": "SYSTEM",
                  "payload": {}, "created_at": None}
            if not st.append_event(ev):
                sys.stderr.write("DUP %s %d\\n" % (wid, i))
                sys.exit(3)
        ok += 1
    print(json.dumps({"wid": wid, "claimed": ok}))
""")


class TestConcurrentAppendZeroLoss(unittest.TestCase):
    """H-15：5 进程 ×200 次自报成功 = 实落盘 1000 条，零丢失（NTFS 本机跨进程实测）。

    夹具移植 05-integration/adversary INT-A-01（a1_control.py：自报 1000、实落 866）
    与 01-debate/verifier DEB-V-08（750 自报实落 744）。会话目录落在仓库所在盘
    （D:\\ NTFS 本机路径），不再是第一轮的 /mnt 9p 挂载。
    """

    @classmethod
    def setUpClass(cls):
        # 仓库根在 D:\\（NTFS 本机路径）；显式落在本机数据盘而非系统临时目录。
        cls.base = tempfile.mkdtemp(prefix="b3_conc_", dir=REPO_ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def _spawn_workers(self, tags, count, mode="event"):
        script_path = os.path.join(self.base, "worker_b3.py")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(WORKER_SCRIPT)
        procs = [subprocess.Popen(
            [sys.executable, script_path, REPO_ROOT, self.folder, tag, str(count), mode],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for tag in tags]
        results = []
        for proc in procs:
            out, err = proc.communicate()
            self.assertEqual(proc.returncode, 0,
                             "worker 失败（append_event 返回 False 或异常）：%s" % err)
            results.append(json.loads(out.strip().splitlines()[-1]))
        return results

    def test_five_processes_200_events_each_zero_loss(self):
        self.folder = os.path.join(self.base, "sess_conc_events")
        os.makedirs(self.folder)
        results = self._spawn_workers(["P1", "P2", "P3", "P4", "P5"], 200)
        claimed = sum(r["claimed"] for r in results)
        self.assertEqual(claimed, 1000, "5 进程必须各自自报 200 次成功")

        # 终局回读：唯一真源 events.jsonl 必须一条不少、一条不重。
        events = _log_events(self.folder)
        on_disk_ids = [e.get("event_id") for e in events]
        self.assertEqual(len(events), 1000,
                         "自报成功 %d 条，实落盘 %d 条：并发丢事件未修复" % (claimed, len(events)))
        self.assertEqual(len(set(on_disk_ids)), 1000, "事件 id 必须无重复")
        for r in results:
            expected = {"CONC-%s-%04d" % (r["wid"], i) for i in range(200)}
            self.assertTrue(expected.issubset(set(on_disk_ids)),
                            "worker %s 的事件有丢失" % r["wid"])

    def test_concurrent_usage_ledger_is_always_valid_jsonl(self):
        """H-15 配套（INT-A-02）：台账并发追加恒为合法 JSONL，零丢失。"""
        self.folder = os.path.join(self.base, "sess_conc_ledger")
        os.makedirs(self.folder)
        results = self._spawn_workers(["L1", "L2", "L3"], 100, mode="ledger")
        claimed = sum(r["claimed"] for r in results)
        self.assertEqual(claimed, 300)
        store = SessionStore(self.folder)
        entries = store.read_usage()          # 任何非法行都会在此抛 JSONDecodeError
        self.assertEqual(len(entries), 300, "台账条目必须零丢失")
        workers = {e["worker"] for e in entries}
        self.assertEqual(workers, {"L1", "L2", "L3"})


# ------------------------------------------------------------ H-101 锁加固
class TestLockHardening(unittest.TestCase):
    """H-101 三项加固：pid 属主核对 / deadline 全路径生效 / rename-aside 回收。

    夹具来源：DEB-V-16（POSIX 活锁可被窃取 + 原持有者误删他人锁）、
    INT-A-11（持锁者存活时等待方越过 deadline 不抛超时）、A1.3 kill 现场。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_lock_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)
        self.lock_path = os.path.join(self.folder, ".session.lock")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_release_does_not_delete_foreign_owned_lock(self):
        """pid 属主核对：锁易主后，原持有者的 finally 不得删除他人的锁（DEB-V-16）。"""
        store = SessionStore(self.folder)
        with store._revision_lock(timeout=5.0):
            with open(self.lock_path, "w", encoding="ascii") as fh:
                fh.write("999999999")  # 模拟锁在本进程持锁期间被他人接管
        self.assertTrue(os.path.exists(self.lock_path),
                        "释放路径删除了 pid 不属于自己的锁")

    def test_deadline_is_honored_while_holder_alive(self):
        """deadline 补分支（INT-A-11）：活持有者在位时，等待方必须在 deadline 抛超时。"""
        holder_script = textwrap.dedent("""
            import os, sys, time
            sys.path.insert(0, sys.argv[1])
            from shared.execution.session_store import _SessionFileLock
            lock = _SessionFileLock.acquire(os.path.join(sys.argv[2], ".session.lock"), 5.0)
            time.sleep(3.0)          # 持锁 3 秒（存活持有者）
        """)
        script_path = os.path.join(self.tmp, "holder.py")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(holder_script)
        holder = subprocess.Popen([sys.executable, script_path, REPO_ROOT, self.folder],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline_hit = None
            store = SessionStore(self.folder)
            time.sleep(0.8)  # 等 holder 拿到锁
            start = time.time()
            with self.assertRaises(RevisionConflict):
                with store._revision_lock(timeout=1.0):
                    pass
            waited = time.time() - start
            deadline_hit = waited
            self.assertLess(deadline_hit, 2.5,
                            "越过 deadline 未抛超时（INT-A-11 复现）")
        finally:
            holder.communicate()
            holder.wait(timeout=10)

    def test_orphaned_lock_is_recovered_by_rename_aside(self):
        """孤儿锁（持有进程已死）回收改 rename-aside：立即恢复且留下可审计归档。"""
        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
        victim.wait(timeout=10)
        with open(self.lock_path, "w", encoding="ascii") as fh:
            fh.write(str(victim.pid))  # 已退出进程的 pid → 孤儿锁
        store = SessionStore(self.folder)
        start = time.time()
        with store._revision_lock(timeout=5.0):
            elapsed = time.time() - start
            self.assertLess(elapsed, 4.0, "孤儿锁未被立即回收（rename-aside 未生效）")
        asides = [f for f in os.listdir(self.folder) if ".session.lock.stale-" in f]
        self.assertEqual(len(asides), 1, "stale 回收必须留 rename-aside 归档（可审计）")

    def test_same_thread_reentrancy_does_not_deadlock(self):
        """recover_commit 需要在持锁状态下追加审计事件/推进快照：同线程必须可重入。"""
        store = SessionStore(self.folder)
        with store._revision_lock(timeout=2.0):
            with store._revision_lock(timeout=2.0):
                store.append_usage({"nested": True})
        self.assertEqual(len(store.read_usage()), 1)


# ------------------------------------------------- H-08/H-16 recover_commit
class TestRecoverCommitGuards(unittest.TestCase):
    """recover_commit 三守卫：合法恢复成功；伪造/陈旧 journal 逐一拒绝。

    夹具移植 INT-A-05（a7/a2 伪造 journal）、DEB-V-10（C6c doctored 快照）、
    T04（合法中断提交必须仍可恢复——守卫不得误伤诚实恢复）。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_rc_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- 合法恢复（守卫不得过严） ------------------------------------------
    def test_genuine_interrupted_commit_still_completes(self):
        store = _interrupted_commit(self.folder)
        self.assertIsNotNone(store.pending_commit())
        fresh = SessionStore(self.folder)     # 新实例 = 崩溃后重新打开会话
        result = fresh.recover_commit()
        self.assertEqual(result["status"], "COMMIT_COMPLETED")
        self.assertFalse(os.path.exists(fresh.commit_journal_path))
        report = fresh.consistency_report()
        self.assertTrue(report["consistent"], report["divergence"])
        # 恢复诚实：状态 = 封存时的状态，不增不减
        self.assertEqual(fresh.load_snapshot().get("state"), "DISCUSSING")

    def test_recover_path_calls_recover_commit_for_real(self):
        """H-16：SessionStore.recover() 必须真实收敛 INCOMPLETE_COMMIT（无调用点缺陷）。"""
        _interrupted_commit(self.folder)
        store = SessionStore(self.folder)
        self.assertIn("INCOMPLETE_COMMIT",
                      [d["kind"] for d in store.consistency_report()["divergence"]])
        result = store.recover()
        self.assertEqual(result["commit_recovery"]["status"], "COMMIT_COMPLETED")
        report = store.consistency_report()
        self.assertTrue(report["consistent"], report["divergence"])

    # -- 守卫① revision 单调 ------------------------------------------------
    def test_stale_journal_rejected_by_revision_monotonicity(self):
        """INT-A-05/A2.4 主守卫：目标 revision ≤ 当前快照 → 拒绝，不得回滚历史。"""
        store = SessionStore(self.folder)
        store.save_snapshot({"session_id": SESSION_ID, "state": "V1"}, 0)
        for r in range(1, 4):
            store.save_snapshot({"session_id": SESSION_ID, "state": "V%d" % (r + 1)}, r)
        stale_snapshot = {"session_id": SESSION_ID, "state": "V2", "revision": 2,
                          "last_applied_event_id": None}
        checkpoint = {"schema_version": "0.1", "commit_id": "commit-forgeddeadbeef",
                      "last_event_id": None, "event_count": 0,
                      "event_log_digest": store._event_digest([]),
                      "inherited_fields": [], "state": dict(stale_snapshot)}
        store._atomic_write_json(store.commit_journal_path, {
            "schema_version": "0.1", "commit_id": "commit-forgeddeadbeef",
            "expected_revision": 1, "snapshot": stale_snapshot,
            "checkpoint": checkpoint})
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        self.assertEqual(result["reason"], "REVISION_NOT_MONOTONIC")
        self.assertEqual(store.load_snapshot().get("state"), "V4",
                         "陈旧 journal 不得写回（历史状态被回滚）")

    # -- 守卫② commit_id 绑定 + 前缀摘要 ------------------------------------
    def _fresh_sealed(self, events=1):
        store = SessionStore(self.folder)
        store.save_snapshot({"session_id": SESSION_ID, "state": "WAITING_USER"}, 0)
        for i in range(events):
            store.append_event({"schema_version": "0.1", "event_id": "E%d" % (i + 1),
                                "session_id": SESSION_ID, "seq": i + 1,
                                "type": "ROLE_RESPONSE", "actor": "moderator",
                                "execution_kind": "ROLE_SWITCH",
                                "payload": {"field": "state", "value": "DISCUSSING"},
                                "created_at": None})
        state = store.rebuild()["state"]
        store.seal_checkpoint(state, expected_revision=state["revision"])
        # 正常封存后推进一次快照，制造"当前 revision > journal 目标"的中断态：
        # 手工把 journal 复原为中断现场（模拟崩溃在删 journal 之前）。
        return store

    def test_forged_commit_id_rejected_by_binding_check(self):
        """C6c 主守卫：journal.commit_id 与 checkpoint.commit_id 不一致 → 拒绝。"""
        store = self._fresh_sealed()
        current = store._current_revision()
        checkpoint = store.load_checkpoint()
        forged = {"schema_version": "0.1", "commit_id": "commit-STALE-JRNL",
                  "expected_revision": current,
                  "snapshot": dict(checkpoint["state"], revision=current + 1),
                  "checkpoint": dict(checkpoint, state=dict(checkpoint["state"]))}
        store._atomic_write_json(store.commit_journal_path, forged)
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        self.assertEqual(result["reason"], "COMMIT_ID_BINDING_INVALID")

    def test_revision_incoherent_snapshot_rejected(self):
        """seal 构造不变式：snapshot.revision 必须 == expected_revision + 1。"""
        store = self._fresh_sealed()
        current = store._current_revision()
        checkpoint = store.load_checkpoint()
        forged = {"schema_version": "0.1", "commit_id": "commit-aaaabbbbcccc",
                  "expected_revision": current - 1,
                  "snapshot": dict(checkpoint["state"], revision=current + 1),
                  "checkpoint": dict(checkpoint, commit_id="commit-aaaabbbbcccc")}
        store._atomic_write_json(store.commit_journal_path, forged)
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        self.assertEqual(result["reason"], "COMMIT_ID_BINDING_INVALID")

    def test_tampered_event_prefix_digest_rejected(self):
        """事件前缀摘要重算核对：checkpoint 声明的摘要与当前日志不符 → 拒绝。"""
        store = self._fresh_sealed(events=2)
        current = store._current_revision()
        checkpoint = store.load_checkpoint()
        bad_digest = "sha256:" + "0" * 64
        forged = {"schema_version": "0.1",
                  "commit_id": "commit-ddddeeeeffff",
                  "expected_revision": current,
                  "snapshot": dict(checkpoint["state"], revision=current + 1),
                  "checkpoint": dict(checkpoint, commit_id="commit-ddddeeeeffff",
                                     event_log_digest=bad_digest)}
        store._atomic_write_json(store.commit_journal_path, forged)
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        self.assertEqual(result["reason"], "EVENT_PREFIX_DIGEST_MISMATCH")

    def test_journal_claiming_more_events_than_log_rejected(self):
        """checkpoint 声明的 event_count 超过日志长度（日志被截断）→ 拒绝。"""
        store = self._fresh_sealed()
        current = store._current_revision()
        checkpoint = store.load_checkpoint()
        forged = {"schema_version": "0.1", "commit_id": "commit-111122223333",
                  "expected_revision": current,
                  "snapshot": dict(checkpoint["state"], revision=current + 1),
                  "checkpoint": dict(checkpoint, commit_id="commit-111122223333",
                                     event_count=99)}
        store._atomic_write_json(store.commit_journal_path, forged)
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        self.assertEqual(result["reason"], "EVENT_PREFIX_DIGEST_MISMATCH")

    # -- 守卫③ 拒绝可审计（.rejected 归档 + 审计事件） ----------------------
    def test_rejected_journal_is_archived_with_audit_event(self):
        store = self._fresh_sealed()
        current = store._current_revision()
        with open(store.session_path, encoding="utf-8") as fh:
            before_snapshot = json.load(fh)
        checkpoint = store.load_checkpoint()
        forged = {"schema_version": "0.1", "commit_id": "commit-replayauth001",
                  "expected_revision": current,
                  "snapshot": dict(checkpoint["state"], revision=current + 1),
                  "checkpoint": dict(checkpoint)}   # 真 checkpoint + 伪 commit_id
        store._atomic_write_json(store.commit_journal_path, forged)
        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        # 归档不删除
        self.assertFalse(os.path.exists(store.commit_journal_path))
        self.assertTrue(os.path.isfile(result["archived_to"]))
        self.assertIn(".rejected-", result["archived_to"])
        with open(result["archived_to"], encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["commit_id"], "commit-replayauth001")
        # 审计事件在日志中
        audit = [e for e in _log_events(self.folder)
                 if e.get("type") == "RECOVERY_COMMIT_REJECTED"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["payload"]["reason"], "COMMIT_ID_BINDING_INVALID")
        self.assertTrue(audit[0]["payload"]["archive"])
        # 两个数据文件保持原状
        with open(store.session_path, encoding="utf-8") as fh:
            after_snapshot = json.load(fh)
        self.assertEqual(after_snapshot, before_snapshot)


class TestForgedJournalAuthorizationResurrection(unittest.TestCase):
    """INT-A-05 §一全链移植：伪造 journal 复活已撤销授权 → 现在必须全链被拒。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_a05_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_revoked_authorization_stays_revoked(self):
        store, fp = _authorized_store(self.folder)
        gap = _gap()
        current = store._current_revision()
        store.seal_checkpoint({"session_id": SESSION_ID, "state": "DISPATCH_READY",
                               "gap_requests": [gap]}, current, import_mode=True,
                              import_reason="fixture", import_source="e2e-cluster2")
        # 用户撤销（新快照把授权置为 INVALIDATED）
        revoked = json.load(open(store.session_path, encoding="utf-8"))
        revoked["gap_requests"] = [dict(gap, approval=dict(gap["approval"],
                                                           status="INVALIDATED"))]
        store.save_snapshot(revoked, store._current_revision())

        # 攻击：封存时的旧 checkpoint + 陈旧 state 打包成 commit_journal
        cp = store.load_checkpoint()
        stale_state = dict(cp["state"])
        stale_state["revision"] = store._current_revision() - 1
        store._atomic_write_json(store.commit_journal_path,
                                 {"schema_version": "0.1",
                                  "commit_id": "commit-replayauth001",
                                  "expected_revision": stale_state["revision"],
                                  "snapshot": stale_state, "checkpoint": cp})

        result = store.recover_commit()
        self.assertEqual(result["status"], "COMMIT_REJECTED")
        # 授权没有复活
        restored = json.load(open(store.session_path, encoding="utf-8"))
        self.assertEqual(restored["gap_requests"][0]["approval"]["status"], "INVALIDATED")
        self.assertEqual(restored["revision"], store._current_revision())
        # 一致性不再全绿（撤销后的快照与检查点重放的分歧被如实报告）
        report = store.consistency_report()
        self.assertFalse(report["consistent"], "伪造 journal 被拒后分歧必须显式可见")
        # 下游派发不被解锁
        verdict = prepare_dispatch(restored["gap_requests"][0], store)
        self.assertFalse(verdict["dispatchable"], verdict)
        # 拒绝留痕
        self.assertTrue(any(e.get("type") == "RECOVERY_COMMIT_REJECTED"
                            for e in _log_events(self.folder)))


# --------------------------------------------------------------- CLI 断链
class TestCliRecoverCommit(unittest.TestCase):
    """DEB-R-01 / DEB-V-09 / INT-R-09：CLI 恢复路径收敛 INCOMPLETE_COMMIT。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_cli_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recover_commit_subcommand_converges_incomplete_commit(self):
        _interrupted_commit(self.folder)
        code, out = _run_cli("recover-commit", self.folder)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "COMMIT_COMPLETED")
        code, out = _run_cli("check", self.folder)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["consistent"], out.get("divergence"))

    def test_recover_command_now_resolves_incomplete_commit(self):
        """旧实现：CLI recover 只做 rebuild，journal 永久悬置（DEB-R-01）。"""
        _interrupted_commit(self.folder)
        code, out = _run_cli("recover", self.folder)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["commit_recovery"]["status"], "COMMIT_COMPLETED")
        code, out = _run_cli("check", self.folder)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["consistent"], out.get("divergence"))

    def test_recover_commit_rejects_forged_journal_with_nonzero_rc(self):
        """持久层违规（恢复拒绝）必须 rc≠0，并给出 .rejected 归档位置。"""
        store = SessionStore(self.folder)
        store.save_snapshot({"session_id": SESSION_ID, "state": "V1"}, 0)
        store.save_snapshot({"session_id": SESSION_ID, "state": "V2"}, 1)
        store._atomic_write_json(store.commit_journal_path, {
            "schema_version": "0.1", "commit_id": "commit-forgeddeadbeef",
            "expected_revision": 1,
            "snapshot": {"session_id": SESSION_ID, "state": "V1", "revision": 2},
            "checkpoint": {"schema_version": "0.1", "commit_id": "commit-other",
                           "event_count": 0, "state": {}}})
        code, out = _run_cli("recover-commit", self.folder)
        self.assertEqual(code, 1, out)
        self.assertEqual(out["status"], "COMMIT_REJECTED")
        self.assertTrue(os.path.isfile(out["archived_to"]))

    def test_no_pending_commit_reports_ok(self):
        code, out = _run_cli("recover-commit", self.folder)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "NO_PENDING_COMMIT")

    def test_cli_schema_and_argument_errors_are_nonzero(self):
        code, out = _run_cli("append", self.folder, "--event-json", "{oops")
        self.assertEqual(code, 2, out)
        self.assertEqual(out["status"], "INPUT_ERROR")
        code, out = _run_cli("seal", self.folder)
        self.assertEqual(code, 2, out)
        code, out = _run_cli("definitely-not-a-command", self.folder)
        self.assertEqual(code, 2, out)
        code, out = _run_cli("append", self.folder)  # 缺 --event-json
        self.assertEqual(code, 2, out)


# ------------------------------------------------------------------- H-10
class TestAppliedTypeConfusionMatrix(unittest.TestCase):
    """DEB-V-01：applied 判定改 `is not True`——false/"false"/0/未戳记事件不得放行。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_applied_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _verdict_for(self, applied):
        store = SessionStore(self.folder)
        fp = scope_fingerprint(_gap())
        _confirm_event(store, fp, applied=applied)   # applied=... → 由 store 戳记 True
        return prepare_dispatch(_gap(fp=fp), store)

    def test_applied_false_is_refused(self):
        r = self._verdict_for(False)
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "CONFIRMATION_EVENT_NOT_APPLIED")

    def test_applied_string_false_is_refused(self):
        r = self._verdict_for("false")
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "CONFIRMATION_EVENT_NOT_APPLIED")

    def test_applied_zero_is_refused(self):
        r = self._verdict_for(0)
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "CONFIRMATION_EVENT_NOT_APPLIED")

    def test_unstamped_event_in_handwritten_log_is_refused(self):
        """绕过 store 手写日志（无 applied 戳记）→ 严格判定拒绝（伪造日志不得放行）。"""
        store, fp = _authorized_store(self.folder, with_snapshot=False)
        gap = _gap(fp=fp)
        gap["approval"]["confirmed_event_id"] = "E-CONF-RAW"
        event = {
            "schema_version": "0.1", "event_id": "E-CONF-RAW", "session_id": SESSION_ID,
            "seq": 2, "type": "GAP_CONFIRMED", "actor": "user", "execution_kind": "USER",
            "payload": {"gap_id": GAP_ID, "idea_id": "IDEA-1", "idea_version": 1,
                        "scope_fingerprint": fp},
            "created_at": "2026-09-13T00:00:00Z",
        }
        with open(store.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        r = prepare_dispatch(gap, store)
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "CONFIRMATION_EVENT_NOT_APPLIED")

    def test_store_stamped_event_dispatches(self):
        """持久层不变式：经 append_event 落盘的事件由 store 戳记 applied=True。"""
        r = self._verdict_for(...)
        self.assertTrue(r["dispatchable"], r)
        store = SessionStore(self.folder)
        self.assertTrue(all(e.get("applied") is True for e in _log_events(self.folder)))

    def test_challenge_confirmation_unapplied_stays_pending(self):
        """挑战通道同口径：applied 非 True 的复核事件不得核验反证。"""
        from shared.execution.debate_handoff import _validate_challenge_human_confirmation
        store, fp = _authorized_store(self.folder, with_snapshot=False)
        _confirm_event(store, fp, event_id="E-HUMAN", applied=False)
        human = {"confirmed_by": "user", "confirmed_event_id": "E-HUMAN"}
        ok, problem_code, _ = _validate_challenge_human_confirmation(human, store,
                                                                     evidence_id="EV-1")
        self.assertFalse(ok)
        self.assertEqual(problem_code, "CHALLENGE_HUMAN_CONFIRMATION_UNVERIFIED")


# ------------------------------------------------------------------- H-13
class TestChallengeEvidenceBinding(unittest.TestCase):
    """DEB-V-06：复核记录缺 evidence_id 时，绑定核对不得空放行。"""

    PROP = "黑麂与小麂的共存主轴是空间与时间生态位分化。"
    QUOTE = ("冬季由于可利用的资源减少，竞争加剧，二者通过调整日活动节律，"
             "增加时间生态位分化程度，从而实现同域共存。")

    def _store(self, folder, bound_evidence="EV-OTHER"):
        store = SessionStore(folder)
        store.append_event({"schema_version": "0.1", "event_id": "EV-HUMAN",
                            "session_id": "S1", "seq": 1, "type": "EVIDENCE_IMPORTED",
                            "actor": "user", "execution_kind": "USER",
                            "payload": {"evidence_id": bound_evidence},
                            "created_at": None})
        return store

    def _credential(self):
        return {"status": "VERIFIED", "challenge_scope": "MECHANISM",
                "challenge_strength": "WEAKENS", "verifier": "host-agent",
                "verification_ref": "audit/report_challenge.json",
                "human_confirmation": {"confirmed_by": "user",
                                       "confirmed_event_id": "EV-HUMAN"}}

    def _record(self, **over):
        rec = {"evidence_id": "EV-CH", "artifact_ref": "hu_temporal_spatial.pdf",
               "verbatim_quote": self.QUOTE, "location": {"page": 9},
               "checked_scope": "全文 11 页"}
        rec["challenge_verification"] = self._credential()
        rec.update(over)
        return rec

    def test_record_without_evidence_id_cannot_ride_on_foreign_confirmation(self):
        """空放行堵死：记录无 evidence_id + 复核事件绑定他人证据 → UNBOUND，不升级。"""
        with tempfile.TemporaryDirectory(prefix="b3_h13_") as folder:
            store = self._store(folder, bound_evidence="EV-OTHER")
            record = self._record()
            record.pop("evidence_id")   # 被复核记录自身没有身份（DEB-V-06 夹具）
            link = to_evidence_link(record, self.PROP, "CHALLENGE", session_store=store)
            self.assertEqual(link["challenge_status"], "PENDING_HUMAN_CONFIRMATION")
            self.assertIn("CHALLENGE_HUMAN_CONFIRMATION_UNBOUND", link["challenge_reason"])

    def test_bound_record_with_matching_confirmation_still_verifies(self):
        """同构正例：记录有 evidence_id 且复核事件绑定同一证据 → 正常核验。"""
        with tempfile.TemporaryDirectory(prefix="b3_h13b_") as folder:
            store = self._store(folder, bound_evidence="EV-CH")
            link = to_evidence_link(self._record(), self.PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "VERIFIED_CHALLENGE")


# ------------------------------------------------------------------- H-45
class TestGapIdUniqueness(unittest.TestCase):
    """INT-A-06：同一 gap_id 双重消费被拒；已推进缺口的重复派发被拒。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="b3_gap_")
        self.folder = os.path.join(self.tmp, "sess")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store_with_snapshot(self, gap_requests):
        store, fp = _authorized_store(self.folder)
        store.save_snapshot({"schema_version": "0.1", "session_id": SESSION_ID,
                             "state": "DISPATCH_READY", "last_applied_event_id": None,
                             "gap_requests": gap_requests},
                            store._current_revision())
        return store, fp

    def test_duplicate_gap_id_cannot_double_consume_authorization(self):
        gap = _gap()
        store, fp = self._store_with_snapshot([gap, dict(gap)])
        verdict = prepare_dispatch(gap, store)
        self.assertFalse(verdict["dispatchable"], verdict)
        self.assertEqual(verdict["reason"], "GAP_ID_NOT_UNIQUE")

    def test_check_referential_integrity_reports_duplicate_gap_id(self):
        store, _ = _authorized_store(self.folder)
        gap = _gap()
        violations = store.check_referential_integrity({"gap_requests": [gap, dict(gap)]})
        self.assertEqual(len(violations), 1)
        self.assertIn("duplicate gap_id", violations[0])

    def test_advanced_gap_in_snapshot_blocks_duplicate_dispatch(self):
        for status, expected in (("RUNNING", "ALREADY_RUNNING_IN_FLIGHT"),
                                 ("IN_PROGRESS", "ALREADY_RUNNING_IN_FLIGHT"),
                                 ("COMPLETE", "ALREADY_COMPLETE_IDEMPOTENT"),
                                 ("DISPATCH_QUEUED", "GAP_ALREADY_ADVANCED")):
            with self.subTest(status=status):
                shutil.rmtree(self.folder, ignore_errors=True)
                os.makedirs(self.folder)
                store, fp = self._store_with_snapshot(
                    [_gap(execution_status=status)])
                caller_copy = _gap(fp=fp)   # 调用方拿的是未推进的旧副本
                verdict = prepare_dispatch(caller_copy, store)
                self.assertFalse(verdict["dispatchable"], verdict)
                self.assertEqual(verdict["reason"], expected)

    def test_single_not_started_gap_still_dispatches(self):
        """同构正例：唯一且未推进的缺口照常派发（守卫不得过严）。"""
        gap = _gap()
        store, fp = self._store_with_snapshot([gap])
        verdict = prepare_dispatch(_gap(fp=fp), store)
        self.assertTrue(verdict["dispatchable"], verdict)


# ------------------------------------------------------------------ H-09②
class TestStoreIdentityBinding(unittest.TestCase):
    """INT-A-16：跨会话搬运 events.jsonl → prepare_dispatch 拒绝（store 身份绑定）。"""

    def test_copied_event_log_is_rejected_in_foreign_session(self):
        with tempfile.TemporaryDirectory(prefix="b3_h09a_") as folder_a, \
                tempfile.TemporaryDirectory(prefix="b3_h09b_") as folder_b:
            store_a, fp = _authorized_store(folder_a, session_id="sess-A")
            gap_a = _gap(session_id="sess-A", fp=fp)
            self.assertTrue(prepare_dispatch(gap_a, store_a)["dispatchable"],
                            "同会话正例必须可派发")

            # 攻击：把 A 会话的 events.jsonl 原样搬进 B 会话
            store_b = SessionStore(folder_b)
            store_b.save_snapshot({"schema_version": "0.1", "session_id": "sess-B",
                                   "state": "WAITING_USER"}, 0)
            shutil.copyfile(store_a.events_path, store_b.events_path)
            gap_b = _gap(session_id="sess-B", fp=fp)
            verdict = prepare_dispatch(gap_b, store_b)
            self.assertFalse(verdict["dispatchable"], verdict)
            self.assertEqual(verdict["reason"], "CONFIRMATION_EVENT_STORE_MISMATCH")

    def test_events_only_store_without_declared_identity_skips_binding(self):
        """身份无法自述的 events-only 存储：跳过绑定核对（既有授权流程不回归）。"""
        with tempfile.TemporaryDirectory(prefix="b3_h09b_") as folder:
            store, fp = _authorized_store(folder, with_snapshot=False)
            verdict = prepare_dispatch(_gap(fp=fp), store)
            self.assertTrue(verdict["dispatchable"], verdict)


# ------------------------------------------------------------------- H-02
class TestSharedNegationLexicon(unittest.TestCase):
    """DEB-V-05/H-02：NEGATION_MARKERS 换用 shared/text/polarity.py（单一真源）。"""

    PROP = "roads reduce gene flow in muntjac"

    def test_lexicon_is_the_shared_single_source(self):
        self.assertIs(NEGATION_MARKERS, shared_polarity.NEGATION_MARKERS,
                      "debate_handoff 必须复用共享词表，不得再持私有副本")

    def test_nt_contractions_enter_negation_detection(self):
        hit = detect_negation_mismatch(
            "Our telemetry shows roads don't reduce gene flow in muntjac.", self.PROP)
        self.assertIsNotNone(hit, "don't 收缩词必须进入否定判定（DEB-V-05）")
        link = to_evidence_link(
            {"evidence_id": "E1", "artifact_ref": "paper.pdf",
             "verbatim_quote": "Our telemetry shows roads don't reduce gene flow in muntjac.",
             "location": {"page": 3}, "checked_scope": "全文",
             "semantic_verification": helpers.semantic_verification("E1", self.PROP)},
            self.PROP, "SUPPORT")
        self.assertIn("NEGATION_MISMATCH", link["problems"])
        self.assertEqual(link["alignment"], "UNRESOLVED")

    def test_chinese_bu_tong_compound_is_not_a_negation(self):
        """H-82 行为兼容：中文"不同"等合成词不误报否定。"""
        self.assertIsNone(detect_negation_mismatch(
            "不同样地间的物种数均显著增加", "干扰移除使物种数增加"))

    def test_legacy_markers_remain_effective(self):
        self.assertIsNotNone(detect_negation_mismatch(
            "Species declined rather than increased.", "Species increased."))
        self.assertIsNotNone(detect_negation_mismatch(
            "The treatment did not change gene flow.", self.PROP))
        self.assertIsNone(detect_negation_mismatch(
            "Roads strongly reduce gene flow in muntjac.", self.PROP))


# ------------------------------------------------------- kill 中断诚实恢复
SEAL_CRASH_CHILD = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, sys.argv[1])
    from shared.execution.session_store import SessionStore
    st = SessionStore(sys.argv[2])
    st.save_snapshot({"schema_version": "0.1", "session_id": "SESS-KILL",
                      "state": "WAITING_USER", "last_applied_event_id": None}, 0)
    st.append_event({"schema_version": "0.1", "event_id": "K1", "session_id": "SESS-KILL",
                     "seq": 1, "type": "ROLE_RESPONSE", "actor": "moderator",
                     "execution_kind": "ROLE_SWITCH",
                     "payload": {"field": "state", "value": "DISCUSSING"},
                     "created_at": None})
    original = st._atomic_write_json
    def crash_after_journal(path, payload):
        original(path, payload)
        if os.path.basename(path) == "commit_journal.json":
            os._exit(137)          # 模拟 kill：journal 落盘后、两文件写入前死亡
        original(path, payload)
    st._atomic_write_json = crash_after_journal
    st.seal_checkpoint({"session_id": "SESS-KILL", "state": "DISCUSSING",
                        "last_applied_event_id": "K1"}, 1)
    print("NOT_REACHED")
""")

APPEND_CRASH_CHILD = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, sys.argv[1])
    from shared.execution.session_store import SessionStore, _SessionFileLock
    folder = sys.argv[2]
    st = SessionStore(folder)
    st.save_snapshot({"schema_version": "0.1", "session_id": "SESS-KILL",
                      "state": "WAITING_USER", "last_applied_event_id": None}, 0)
    lock = _SessionFileLock.acquire(os.path.join(folder, ".session.lock"), 5.0)
    for i in range(5):
        st.append_event({"schema_version": "0.1", "event_id": "A%d" % i,
                         "session_id": "SESS-KILL", "seq": i, "type": "ROLE_RESPONSE",
                         "actor": "moderator", "execution_kind": "ROLE_SWITCH",
                         "payload": {"field": "state", "value": "DISCUSSING"},
                         "created_at": None})
    os._exit(137)                  # 模拟 kill：死在持锁状态 → 孤儿锁 + 完整事件前缀
""")


class TestKillRecoveryHonesty(unittest.TestCase):
    """20 次 kill 中断恢复诚实全绿（A1.3 现场移植）。

    封存窗口 kill ×10：journal 残留 → 恢复完成提交、一致性绿、状态不增不减；
    持锁追加窗口 kill ×10：孤儿锁 + 完整事件前缀 → rename-aside 立即回收、
    事件零丢失、追加可继续。
    """

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="b3_kill_", dir=REPO_ROOT)
        cls.seal_child = os.path.join(cls.base, "seal_crash_child.py")
        cls.append_child = os.path.join(cls.base, "append_crash_child.py")
        with open(cls.seal_child, "w", encoding="utf-8") as fh:
            fh.write(SEAL_CRASH_CHILD)
        with open(cls.append_child, "w", encoding="utf-8") as fh:
            fh.write(APPEND_CRASH_CHILD)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def _run_child(self, script, folder):
        proc = subprocess.run([sys.executable, script, REPO_ROOT, folder],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 137,
                         "kill 夹具应止步于 os._exit(137)：%s%s" % (proc.stdout, proc.stderr))

    def test_twenty_kills_recover_honestly(self):
        for round_no in range(20):
            folder = os.path.join(self.base, "kill_%02d" % round_no)
            os.makedirs(folder)
            if round_no % 2 == 0:
                with self.subTest(round=round_no, mode="seal-crash"):
                    self._run_child(self.seal_child, folder)
                    store = SessionStore(folder)
                    self.assertIsNotNone(store.pending_commit(),
                                         "kill 后必须留下可识别的中断提交")
                    result = store.recover()
                    self.assertEqual(result["commit_recovery"]["status"],
                                     "COMMIT_COMPLETED")
                    self.assertTrue(store.consistency_report()["consistent"],
                                    "第 %d 轮：诚实恢复后一致性必须全绿" % round_no)
                    self.assertEqual(store.load_snapshot().get("state"), "DISCUSSING",
                                     "恢复状态必须等于封存状态（不增不减）")
                    self.assertFalse(os.path.exists(store.commit_journal_path))
                    self.assertTrue(any(e.get("type") == "RECOVERY_COMMIT_APPLIED"
                                        for e in _log_events(folder)))
            else:
                with self.subTest(round=round_no, mode="append-crash"):
                    self._run_child(self.append_child, folder)
                    store = SessionStore(folder)
                    events = _log_events(folder)
                    self.assertEqual([e.get("event_id") for e in events],
                                     ["A0", "A1", "A2", "A3", "A4"],
                                     "kill 后事件前缀必须完整无损")
                    # 孤儿锁 rename-aside 回收 + 追加立即可继续
                    store.append_event({"schema_version": "0.1", "event_id": "A5",
                                        "session_id": "SESS-KILL", "seq": 5,
                                        "type": "ROLE_RESPONSE", "actor": "moderator",
                                        "execution_kind": "ROLE_SWITCH",
                                        "payload": {"field": "state",
                                                    "value": "DISCUSSING"},
                                        "created_at": None})
                    self.assertEqual(len(_log_events(folder)), 6)
                    self.assertTrue([f for f in os.listdir(folder)
                                     if ".session.lock.stale-" in f],
                                    "孤儿锁必须留下 rename-aside 审计归档")


if __name__ == "__main__":
    unittest.main()
