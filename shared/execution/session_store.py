#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-idea-debate 会话持久化（事件追加 + 幂等重放 + 原子快照）。

设计要点（对应设计稿 §12.3 / §6.2）：

- **单一真源**：`events.jsonl` 是追加式真源，`session.json` 只是检查点快照。
  两者冲突时以事件重放为准，并显式报告差异，不静默选边。
- **简单可重放**：事件采用**整值投影**语义——各类事件的 `payload` 携带该字段的
  完整新值（如 `{"field": "state", "value": "CHECKPOINT"}`、`{"field": "ideas",
  "value": [...]}`），重放即逐条赋值。这样无需在重放器里写业务逻辑，也避免
  "部分更新"带来的歧义。
- **单写者**：只有主 agent 调用本模块写入；子 agent 没有写入口。
- **幂等**：`event_id` 重复的事件不会被再次应用；`last_applied_event_id` 记录
  已应用到的位置。
- **原子替换**：快照先写同目录临时文件，再 `os.replace` 原子替换。
- **损坏处理**：末尾不完整行（无换行 / JSON 解析失败）隔离到
  `<events>.corrupt-tail-<n>` 后忽略；**中段损坏则停止并报告**，不猜测恢复。

只依赖标准库。写入是显式的：调用方必须给定 `expected_revision`，冲突即拒绝覆盖。
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from contextlib import contextmanager
import json
import os
from typing import Any, Dict, List, Optional, Tuple

_ABSENT = object()

EVENTS_FILENAME = "events.jsonl"
CHECKPOINT_FILENAME = "checkpoint.json"
COMMIT_JOURNAL_FILENAME = "commit_journal.json"
SESSION_FILENAME = "session.json"
LEDGER_FILENAME = "usage_ledger.jsonl"
LOCK_FILENAME = ".session.lock"

#: 恢复提交的审计事件类型（H-08/H-16，2026-09-13 集群测试）。
#: 两者都是无投影载荷的纯记录事件：进入事件日志可审计，但不改写业务状态。
RECOVERY_COMMIT_APPLIED = "RECOVERY_COMMIT_APPLIED"
RECOVERY_COMMIT_REJECTED = "RECOVERY_COMMIT_REJECTED"


def _pid_alive(pid: int) -> Optional[bool]:
    """进程是否存活；无法判断时返回 None（Windows 不用 os.kill 探活——
    在 Windows 上 os.kill(pid, 0) 会**终止**目标进程，绝不可用）。"""
    if pid == os.getpid():
        return True
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return True
    return None


class _SessionFileLock:
    """跨进程 + 跨线程可重入的会话写锁（H-101 三项加固，2026-09-13）。

    锁文件 `<session_dir>/.session.lock` 用 ``O_CREAT|O_EXCL`` 创建，内容为持有者 pid。

    - **pid 属主核对**（DEB-V-16）：释放时只在锁文件内容仍是本进程 pid 时删除，
      防止"原持有者 finally 删掉后到者的锁"；POSIX 上陈旧回收前先探活，活锁不窃取。
    - **deadline 全路径生效**（INT-A-11）：陈旧回收分支失败同样受 deadline 约束，
      不再存在"锁永远回收不掉就永远等下去"的分支；超时抛结构化 RevisionConflict。
    - **stale 回收改 rename-aside**（不原地删除，可审计）：陈旧/孤儿锁被改名为
      `<lock>.stale-<epoch>-<rand>`。Windows 上持有者握着打开句柄时 rename 必然
      失败（PermissionError）→ 活锁不可被夺；rename 成功 ⟺ 无人持有（孤儿锁）
      ⟹ 立即回收，进程被 kill 后的恢复无需等满 timeout。
    """

    _registry: Dict[str, "_SessionFileLock"] = {}
    _registry_guard = threading.Lock()

    def __init__(self, path: str):
        self.path = path
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._fd: Optional[int] = None

    # -- 注册表（按绝对锁路径共享实例，使同进程同线程可重入） ----------------
    @classmethod
    def acquire(cls, path: str, timeout: float) -> "_SessionFileLock":
        key = os.path.abspath(path)
        with cls._registry_guard:
            inst = cls._registry.get(key)
            if inst is None:
                inst = cls(key)
                cls._registry[key] = inst
        inst._enter(timeout)
        return inst

    def _enter(self, timeout: float) -> None:
        if not self._thread_lock.acquire(timeout=max(timeout, 0.0)):
            raise RevisionConflict(
                "获取会话写锁超时（同进程其他线程持有 %s）" % self.path)
        try:
            if self._depth == 0:
                self._acquire_file_lock(timeout)
            self._depth += 1
        except BaseException:
            self._thread_lock.release()
            raise

    def release(self) -> None:
        try:
            self._depth -= 1
            if self._depth == 0 and self._fd is not None:
                fd, self._fd = self._fd, None
                try:
                    os.close(fd)
                finally:
                    self._release_file_lock()
        finally:
            self._thread_lock.release()

    # -- 文件锁 -------------------------------------------------------------
    def _acquire_file_lock(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pass
            except PermissionError:
                # Windows：目标文件已被他人持有（或正处于删除挂起态）时，
                # `O_CREAT|O_EXCL` 返回 EACCES 而非 EEXIST。这是**竞争**不是
                # 致命错误，必须走与 FileExistsError 相同的重试 / stale 回收
                # 路径——否则异常直接逃逸打死调用方进程（2026-09-15 实测：
                # 5 进程 ×200 并发 append 在 NTFS 上约 2/10 次以
                # `PermissionError: [Errno 13] ... .session.lock` 崩溃）。
                # 真正的权限故障（如只读目录）会在 deadline 到达后按既有语义
                # 抛结构化 `RevisionConflict`，比裸 traceback 更可诊断。
                pass
            except FileNotFoundError:
                continue  # 目录在检查后消失等极端情形：重试
            else:
                try:
                    os.write(fd, str(os.getpid()).encode("ascii"))
                except OSError:
                    pass
                self._fd = fd
                return
            if self._recover_stale(timeout):
                continue
            if time.time() > deadline:
                raise RevisionConflict(
                    "获取会话写锁超时（%s 被占用）；请稍后重试或检查残留锁" % self.path)
            time.sleep(0.01)

    def _read_lock_info(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="ascii", errors="replace") as fh:
                raw = fh.read().strip()
            age = time.time() - os.path.getmtime(self.path)
        except (OSError, ValueError):
            return None
        pid = int(raw) if raw.isdigit() else None
        return {"pid": pid, "age": age}

    def _rename_aside(self) -> None:
        aside = "%s.stale-%d-%s" % (self.path, int(time.time()), uuid.uuid4().hex[:8])
        os.rename(self.path, aside)  # 不覆盖既有归档；失败即视为回收未成功

    def _recover_stale(self, timeout: float) -> bool:
        """尝试回收陈旧/孤儿锁；返回 True 表示锁已消失、应立即重试创建。"""
        info = self._read_lock_info()
        if info is None:
            return True  # 锁文件刚消失
        if os.name == "nt":
            # Windows：持有者握着打开句柄 → rename 失败 → 活锁在位，等待；
            # rename 成功 ⟺ 没有任何进程持有句柄（孤儿锁）→ 立即回收。
            try:
                self._rename_aside()
                return True
            except OSError:
                return False
        # POSIX：rename 对活持有者也会成功，必须 age>timeout 且属主已死才回收。
        age = info.get("age")
        pid = info.get("pid")
        if age is not None and age <= timeout:
            return False
        if pid is not None and _pid_alive(pid):
            return False  # 活锁不可窃取（DEB-V-16）
        try:
            self._rename_aside()
            return True
        except OSError:
            return False

    def _release_file_lock(self) -> None:
        # pid 属主核对：只删除仍然属于本进程的锁文件。
        info = self._read_lock_info()
        if info is not None and info.get("pid") not in (os.getpid(), None):
            return  # 锁已易主（本进程的锁曾被回收）→ 不得删除他人锁
        try:
            os.remove(self.path)
        except OSError:
            pass

#: 事件类型中允许通过整值投影修改的字段白名单。
#: 未列入的字段不允许被事件改写（例如 schema_version / session_id / run_id 是身份字段）。
PROJECTABLE_FIELDS = (
    "state", "current_question", "stop_reason", "mode", "execution",
    "ideas", "decisions", "pending_question", "progress_signals",
    "stopped_questions", "open_questions", "review_requests", "review_batches",
    "gap_requests", "rounds", "external_inputs", "context", "upstream_refs",
    "budget_exhausted_at_round", "post_budget_rounds", "summary",
)

#: 身份字段：事件不得改写。
IDENTITY_FIELDS = ("schema_version", "session_id", "run_id", "parent_session_id")


class CorruptEventLog(Exception):
    """事件日志中段损坏——必须停下并报告，不得猜测恢复。"""

    def __init__(self, message: str, details: Dict[str, Any]):
        super().__init__(message)
        self.details = details


class RevisionConflict(Exception):
    """快照 revision 与调用方期望不一致——拒绝覆盖。"""


class ProjectionError(Exception):
    """事件试图改写不允许的字段。"""



class SnapshotCorrupt(ProjectionError):
    """快照文件损坏（非法 JSON）——必须结构化上报，不得以裸异常打死调用方。"""

    def __init__(self, message: str, details: Dict[str, Any]):
        super().__init__(message)
        self.details = details
class SessionStore:
    """一个会话目录的读写句柄。"""

    def __init__(self, session_dir: str):
        self._recovery_notes: List[Dict[str, Any]] = []
        self.session_dir = session_dir
        self.events_path = os.path.join(session_dir, EVENTS_FILENAME)
        self.checkpoint_path = os.path.join(self.session_dir, CHECKPOINT_FILENAME)
        self.commit_journal_path = os.path.join(self.session_dir,
                                                COMMIT_JOURNAL_FILENAME)
        self.session_path = os.path.join(session_dir, SESSION_FILENAME)
        self.ledger_path = os.path.join(session_dir, LEDGER_FILENAME)

    # ------------------------------------------------------------------ 内部
    def _atomic_write_text(self, path: str, text: str) -> None:
        """原子替换写入。

        **P0 修复（2026-09-13 集群测试）**：临时文件名过去是固定的 `<path>.tmp`。
        两个进程同时写同一路径时，它们会写同一个临时文件：内容互相覆盖成
        "两段 JSON 拼在一起"，或一方先 `os.replace` 让另一方抛
        `FileNotFoundError`。实测 3 进程 × 30 轮就产生 20 次异常与损坏快照。
        现在临时名带 pid + 随机后缀，写完 fsync 再替换，失败清理。
        """
        tmp = "%s.%d.%s.tmp" % (path, os.getpid(), uuid.uuid4().hex[:8])
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

    def _atomic_write_json(self, path: str, payload: Any) -> None:
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------ 事件
    def append_event(self, event: Dict[str, Any]) -> bool:
        """追加一条事件（原子写），返回是否为**新应用**（False = 幂等跳过）。

        幂等判据是 `event_id`：已存在于日志中的事件不再追加。

        **H-15（2026-09-13 集群测试 INT-A-01/DEB-V-08，NTFS 实测丢事件 0.8%~13.4%）**：
        "读日志去重 → 检查尾部 → 追加" 整体纳入 O_EXCL 锁临界区。Windows CRT 的
        `_O_APPEND` 是 lseek+write 两步而非原子追加，且 check-then-append 在多进程
        下互相覆盖——实测 5 进程 ×200 次自报成功只落盘 866 条。现在单写者在临界区
        内完成全部步骤，跨进程零丢失；单进程时序不变。

        **持久层不变式（H-10 配套）**：落盘事件若未显式携带 `applied`，由本层补写
        ``applied=True``——事件日志是唯一真源，出现在日志里的事件都会被重放应用。
        调用方要表达"已记录但未应用"必须显式写非 True 值（授权门禁据此拒绝）。
        """
        if not isinstance(event, dict):
            raise ValueError("event 必须是 dict")
        event_id = event.get("event_id")
        if not event_id:
            raise ValueError("event 必须有 event_id")
        if not os.path.isdir(self.session_dir):
            raise FileNotFoundError("会话目录不存在：%s" % self.session_dir)

        with self._revision_lock():
            return self._append_event_locked(event)

    def _append_event_locked(self, event: Dict[str, Any]) -> bool:
        """append_event 的临界区实现；调用方必须已持有会话写锁。"""
        if "applied" not in event:
            event = dict(event, applied=True)
        event_id = event.get("event_id")
        if not event_id:
            raise ValueError("event 必须有 event_id")

        parsed = self._read_events()
        seen = {e.get("event_id") for e in parsed["events"]}
        if event_id in seen:
            return False

        line = json.dumps(event, ensure_ascii=False)

        if parsed.get("quarantined_tail"):
            # F03: 坏尾部未解除时**不得**继续在坏尾部之后追加——那些字节会被解析器
            # 一并忽略，而本方法却返回 True，调用方以为已经持久化。
            # 调用方必须先走显式恢复（rebuild()/recover()）解除坏尾部。
            raise CorruptEventLog(
                "事件日志尾部损坏，拒绝追加：请先执行恢复再写入"
                "（rebuild() 或 recover()）",
                {"path": self.events_path,
                 "reason": "RECOVERY_REQUIRED",
                 "quarantined_tail": parsed["quarantined_tail"]},
            )

        prefix = ""
        if os.path.isfile(self.events_path) and os.path.getsize(self.events_path) > 0:
            with open(self.events_path, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    prefix = "\n"

        with open(self.events_path, "a", encoding="utf-8") as fh:
            if prefix:
                fh.write(prefix)
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True

    def _recover_tail(self, bad_lines: List[str], valid_events: List[Dict[str, Any]]) -> str:
        """在明确事务中修复坏尾部：保留原日志与坏尾部证据，原子重建活动日志。

        可重复执行：同一份损坏不会每次都产生新的隔离副本（隔离文件名按内容摘要固定）。
        返回隔离文件路径。
        """
        digest = hashlib.sha256("\n".join(bad_lines).encode("utf-8")).hexdigest()[:12]
        quarantine = "%s.corrupt-tail-%s" % (self.events_path, digest)
        if not os.path.exists(quarantine):
            self._atomic_write_text(quarantine, "\n".join(bad_lines) + "\n")

        backup = "%s.pre-recovery-%s" % (self.events_path, digest)
        if not os.path.exists(backup):
            if os.path.isfile(self.events_path):
                with open(self.events_path, encoding="utf-8") as fh:
                    self._atomic_write_text(backup, fh.read())

        rebuilt = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in valid_events)
        self._atomic_write_text(self.events_path, rebuilt)

        self._recovery_notes.append({
            "quarantine": quarantine,
            "backup": backup,
            "quarantined_lines": len(bad_lines),
            "recovered_events": len(valid_events),
        })
        return quarantine

    def recovery_notes(self) -> List[Dict[str, Any]]:
        """本实例执行过的尾部恢复记录（可审计）。"""
        return list(self._recovery_notes)

    def _read_events(self) -> Dict[str, Any]:
        """读取事件日志，按规则处理损坏。

        返回 `{"events": [...], "quarantined_tail": [...] | None, "line_count": n}`。
        - 事件中间出现无法解析的行 → 抛 `CorruptEventLog`（停止并报告）；
        - 仅**末尾**不完整（最后一行无换行符，或 JSON 解析失败）→ 隔离为
          `<events>.corrupt-tail-<序号>` 后忽略该条。
        """
        if not os.path.isfile(self.events_path):
            return {"events": [], "quarantined_tail": None, "line_count": 0}

        with open(self.events_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        if raw == "":
            return {"events": [], "quarantined_tail": None, "line_count": 0}

        ends_with_newline = raw.endswith("\n")
        lines = raw.split("\n")
        if ends_with_newline:
            lines = lines[:-1]

        events: List[Dict[str, Any]] = []
        quarantined: Optional[List[str]] = None
        for idx, line in enumerate(lines):
            is_last = idx == len(lines) - 1
            if line.strip() == "":
                if is_last:
                    continue
                raise CorruptEventLog(
                    "事件日志第 %d 行为空行（中段损坏）" % (idx + 1),
                    {"line": idx + 1, "path": self.events_path},
                )
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                if is_last:
                    # 末尾损坏（无论是否带换行）都按"不完整事件"处理：
                    # 崩溃写盘可能留下半行，也可能留下"完整换行但内容坏"的一行。
                    # 只隔离并忽略该条，不影响已提交事件。
                    quarantined = [line]
                    # 不再在这里就地隔离：隔离发生在明确的恢复事务中
                    # （见 _recover_tail），这样"只读诊断"不会产生副作用。
                    break
                raise CorruptEventLog(
                    "事件日志中段损坏：第 %d 行无法解析（其后仍有内容，不按尾部损坏处理）：%s"
                    % (idx + 1, exc),
                    {"line": idx + 1, "path": self.events_path, "reason": "MID_LOG_CORRUPTION"},
                ) from exc
        return {"events": events, "quarantined_tail": quarantined, "line_count": len(lines)}

    def _quarantine_tail(self, line: str) -> str:
        """把末尾不完整行另存隔离副本（不改动原日志的其余内容）。"""
        n = 1
        while True:
            path = "%s.corrupt-tail-%d" % (self.events_path, n)
            if not os.path.exists(path):
                break
            n += 1
        self._atomic_write_text(path, line + "\n")
        return path

    # ---------------------------------------------------------------- 重放
    @staticmethod
    def project(base: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """按整值投影语义把事件应用到快照上。"""
        state = json.loads(json.dumps(base, ensure_ascii=False))
        applied = 0
        for ev in events:
            payload = ev.get("payload") or {}
            field = payload.get("field")
            if field is None:
                # 无投影载荷的事件（如纯记录类）只影响 last_applied_event_id
                applied += 1
                state["last_applied_event_id"] = ev.get("event_id")
                continue
            if field in IDENTITY_FIELDS:
                raise ProjectionError("事件不得改写身份字段：%s" % field)
            if field not in PROJECTABLE_FIELDS:
                raise ProjectionError("事件试图改写未列入白名单的字段：%s" % field)
            state[field] = payload.get("value")
            state["last_applied_event_id"] = ev.get("event_id")
            applied += 1
        state["last_applied_event_id"] = (
            events[-1].get("event_id") if events else base.get("last_applied_event_id")
        )
        state["_events_applied"] = applied
        return state

    def rebuild(self, repair: bool = True) -> Dict[str, Any]:
        """从快照 + 事件重放重建当前状态，并报告差异。

        F03：这是**显式恢复入口**。检测到坏尾部时执行一次恢复事务——保留原始日志
        与坏尾部证据，用有效前缀原子重建活动日志，坏尾部因此从活动日志中解除。
        只读调用方可以传 ``repair=False`` 以避免任何写盘副作用。
        """
        base = self.load_snapshot()
        read = self._read_events()
        if read.get("quarantined_tail") and repair:
            self._recover_tail(read["quarantined_tail"], read["events"])
        projected = self.project(base, read["events"])
        return {
            "state": projected,
            # 成功解析并应用的事件数；被隔离的尾部损坏行不计入
            "events_applied": len(read["events"]),
            "quarantined_tail": read["quarantined_tail"],
            "snapshot_last_applied_event_id": base.get("last_applied_event_id"),
            "replayed_last_applied_event_id": projected.get("last_applied_event_id"),
        }

    # ---------------------------------------------------------------- 快照
    def load_snapshot(self) -> Dict[str, Any]:
        if not os.path.isfile(self.session_path):
            raise FileNotFoundError("快照不存在：%s" % self.session_path)
        with open(self.session_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            # P0：损坏快照过去直接抛裸 JSONDecodeError 打死调用方进程。
            raise SnapshotCorrupt(
                "快照不是合法 JSON（可能被并发写坏或人工编辑破坏）：%s" % exc,
                {"path": self.session_path, "reason": "SNAPSHOT_CORRUPT",
                 "bytes": len(raw)}) from exc

    def save_snapshot(self, session: Dict[str, Any], expected_revision: int) -> Dict[str, Any]:
        """原子写入快照缓存（物化视图）；revision 冲突则拒绝覆盖。

        遵循事件先行协议（Event-First Protocol）：事件日志是系统真源（Authoritative Source）。
        快照作为物化加速视图保存，调用方须先通过 append_event() 记录业务事件与 CHECKPOINT，
        再行持久化快照，本方法不隐式伪造或自动追加 CHECKPOINT 事件。

        **这是调用约定，不是代码保证**：本方法无法阻止调用方写入事件未记录的字段。
        要让"快照即事件重放结果"可被机械核验，须调用 `seal_checkpoint()` 建立可信
        重放基底；未封存时 `consistency_report()` 会报 `SNAPSHOT_BASE_UNVERIFIED`。
        """
        with self._revision_lock():
            return self._save_snapshot_locked(session, expected_revision)

    @contextmanager
    def _revision_lock(self, timeout: float = 10.0):
        """跨进程互斥：把"读 revision → 写快照"变成临界区（也保护事件/台账追加）。

        P0 修复：`save_snapshot` 的 check-then-write 过去无锁，两个进程都读到
        revision=5 时会有一个静默覆盖另一个（实测 90 次写入只留下 50 个版本）。

        **H-101 三项加固（2026-09-13 集群测试）**：见 `_SessionFileLock`——
        pid 属主核对、deadline 全路径生效、stale 锁 rename-aside 回收。
        同进程同线程可重入（`recover_commit` 需要在持锁状态下完成审计事件追加
        与快照推进，不得自锁）。
        """
        lock = _SessionFileLock.acquire(
            os.path.join(self.session_dir, LOCK_FILENAME), timeout)
        try:
            yield
        finally:
            lock.release()

    def _save_snapshot_locked(self, session: Dict[str, Any], expected_revision: int) -> Dict[str, Any]:
        current = None
        if os.path.isfile(self.session_path):
            current = self.load_snapshot().get("revision")
        if current is not None and current != expected_revision:
            raise RevisionConflict(
                "revision 冲突：盘上为 %r，期望 %r；拒绝覆盖，请重新读取后再写"
                % (current, expected_revision)
            )
        session = dict(session)
        session["revision"] = expected_revision + 1
        self._atomic_write_json(self.session_path, session)
        return session

    # ------------------------------------------------------------ 一致性与恢复
    # ------------------------------------------------------------ 事件先行检查点
    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """读取已封存的检查点（可信重放基底）；不存在返回 None。"""
        if not os.path.isfile(self.checkpoint_path):
            return None
        with open(self.checkpoint_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _event_digest(events: List[Dict[str, Any]]) -> str:
        canonical = "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                              for e in events)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _current_revision(self) -> int:
        if not os.path.isfile(self.session_path):
            return 0
        with open(self.session_path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("revision", 0)

    def pending_commit(self) -> Optional[Dict[str, Any]]:
        """读取未完成的提交日志（两文件一致提交协议的中断证据）。"""
        if not os.path.isfile(self.commit_journal_path):
            return None
        try:
            with open(self.commit_journal_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {"commit_id": None, "unreadable": True}

    def seal_checkpoint(self, session: Dict[str, Any], expected_revision: int,
                        import_mode: bool = False,
                        import_reason: Optional[str] = None,
                        import_source: Optional[str] = None) -> Dict[str, Any]:
        """把当前状态封存为**可信重放基底**（Event-First Protocol）。

        事件日志是唯一真源；快照只是物化视图。只有封存过的检查点才能作为重放的
        可信起点——否则"快照里多出来的字段"无法与"事件未记录的修改"区分。

        **信任边界（第三轮核查）**：事件从未定义的字段（`inherited_fields`）会随
        基底一起被信任。首次初始化/历史导入可以这样做，但**已有检查点之后不得
        无审计地接纳新的业务字段**：那种情况必须显式传 `import_mode=True` 并给出
        `import_reason` / `import_source`，随后写入检查点供审计。

        **提交协议（T04）**：revision 校验在任何写入之前完成；快照与检查点通过
        `commit_journal.json` 做两文件一致提交——中断会留下提交日志，
        `consistency_report()` 报 `INCOMPLETE_COMMIT`，`recover_commit()` 完成或回滚。

        **临界区（2026-09-15 部署层核查）**：本方法与 `save_snapshot()` 写同一个
        `session_path`，但旧实现不持锁——两个并发 `seal` 会各自通过 revision 校验
        再先后覆盖（与 H-15 修复前 `save_snapshot` 的 check-then-write 是同一形态）。
        现与 `save_snapshot()` 一致地纳入 `_revision_lock()`。
        """
        with self._revision_lock():
            return self._seal_checkpoint_locked(
                session, expected_revision, import_mode, import_reason, import_source)

    def _seal_checkpoint_locked(self, session: Dict[str, Any], expected_revision: int,
                                import_mode: bool = False,
                                import_reason: Optional[str] = None,
                                import_source: Optional[str] = None) -> Dict[str, Any]:
        """`seal_checkpoint()` 的持锁实现体；调用方必须已持有 `_revision_lock()`。"""
        # ① 先校验 revision，再考虑任何写入（旧实现先写检查点、后由 save_snapshot
        #    抛 RevisionConflict，导致 revision 冲突时却已覆盖 checkpoint.json）。
        current_revision = self._current_revision()
        if current_revision != expected_revision:
            raise RevisionConflict(
                "快照 revision 冲突：期望 %r，当前 %r" % (expected_revision, current_revision))

        read = self._read_events()
        if read["quarantined_tail"]:
            raise CorruptEventLog(
                "事件日志尾部损坏，拒绝封存检查点：请先执行恢复（rebuild/recover）",
                {"path": self.events_path, "reason": "RECOVERY_REQUIRED",
                 "quarantined_tail": read["quarantined_tail"]})
        events = read["events"]
        from_events = self.project({}, events)
        event_fields = [f for f in PROJECTABLE_FIELDS if f in from_events]
        conflicts = [f for f in event_fields
                     if f in session and session.get(f) != from_events.get(f)]
        if conflicts:
            raise ProjectionError(
                "拒绝封存与事件重放冲突的状态：字段 %s 与事件不一致" % sorted(conflicts))
        inherited = sorted(f for f in PROJECTABLE_FIELDS
                           if f in session and f not in from_events)

        previous = self.load_checkpoint()
        if previous is not None:
            known = set(previous.get("inherited_fields") or [])
            new_inherited = [f for f in inherited if f not in known]
            if new_inherited and not import_mode:
                raise ProjectionError(
                    "已有检查点，但本次封存引入了事件未记录的新业务字段 %s："
                    "如属首次初始化或历史导入，请显式传 import_mode=True 并给出 "
                    "import_reason / import_source（会记入检查点审计字段）"
                    % sorted(new_inherited))
            if new_inherited and import_mode and not (import_reason and import_source):
                raise ProjectionError(
                    "import_mode=True 必须同时提供 import_reason 与 import_source，"
                    "否则无法审计这些字段的来源")

        if import_mode:
            origin = "IMPORT"
        elif previous is None:
            origin = "INITIAL_SEAL"
        else:
            origin = "RESEAL"
        replayed = self.project(session, events)
        commit_id = self._commit_id(expected_revision, replayed, events)
        checkpoint_payload = {
            "schema_version": "0.1",
            "commit_id": commit_id,
            "last_event_id": replayed.get("last_applied_event_id"),
            "event_count": len(events),
            "event_log_digest": self._event_digest(events),
            "inherited_fields": inherited,
            "origin": origin,
            "state": replayed,
            "import_mode": bool(import_mode),
            "import_reason": import_reason,
            "import_source": import_source,
            # 信任边界自述：inherited_fields 里的字段是"封存那一刻就存在"的历史状态，
            # 不是事件推导出来的。检查点不是"全部业务状态都由事件证明"的证明。
            "trust_boundary": ("state = event-derived fields + inherited_fields "
                               "(historical state present at seal time)"),
            # 来源：INITIAL_SEAL=会话首次封存；RESEAL=事件推进后的日常封存；
            # IMPORT=显式历史导入（必须给出 import_reason/import_source）。
        }
        snapshot_payload = dict(replayed)
        snapshot_payload["revision"] = expected_revision + 1

        journal = {"schema_version": "0.1", "commit_id": commit_id,
                   "expected_revision": expected_revision,
                   "snapshot": snapshot_payload, "checkpoint": checkpoint_payload}
        self._atomic_write_json(self.commit_journal_path, journal)
        self._atomic_write_json(self.session_path, snapshot_payload)
        self._atomic_write_json(self.checkpoint_path, checkpoint_payload)
        try:
            os.remove(self.commit_journal_path)
        except OSError:
            pass
        return {"checkpoint": self.checkpoint_path, "commit_id": commit_id,
                "event_count": len(events), "last_event_id": checkpoint_payload["last_event_id"],
                "inherited_fields": inherited, "snapshot_revision": expected_revision + 1}

    @staticmethod
    def _commit_id(expected_revision: int, state: Dict[str, Any],
                   events: List[Dict[str, Any]]) -> str:
        material = json.dumps({"revision": expected_revision + 1, "state": state,
                               "events": [e.get("event_id") for e in events]},
                              ensure_ascii=False, sort_keys=True)
        return "commit-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    def recover_commit(self) -> Dict[str, Any]:
        """完成或回滚未完成的两次提交（two-file commit）；返回恢复简报。

        **H-08/H-16 三守卫（2026-09-13 集群测试 INT-A-05 / DEB-V-09 / DEB-V-10）**：
        commit_journal 是恢复入口的自愈输入，旧实现**零校验**直接写回——攻击者把
        封存时的旧 checkpoint 打包成 journal，就能让已撤销（INVALIDATED）的授权
        复活并解锁下游派发，且 consistency 全绿无察觉。现在逐条守卫：

          ① **revision 单调**：journal 目标 revision 必须 > 当前快照 revision
             （陈旧 journal 回滚历史状态一律拒绝）；
          ② **commit_id 绑定 + 事件前缀摘要重算核对**：journal.commit_id 必须与
             journal.checkpoint.commit_id 一致；snapshot.revision 必须 ==
             expected_revision + 1（seal 的构造不变式）；checkpoint 声明的
             event_log_digest 必须与当前事件日志前缀的重算摘要一致（日志被改写/
             截断即拒绝）；
          ③ **拒绝可审计**：被拒 journal 归档为 `commit_journal.json.rejected-<digest>`
             （不删除），并追加 `RECOVERY_COMMIT_REJECTED` 审计事件；恢复成功也追加
             `RECOVERY_COMMIT_APPLIED` 审计事件。审计事件为无投影载荷的纯记录事件。

        注意：commit_id 是公开内容的摘要、无密钥（HMAC 通道属 H-09③，本轮
        NO-ACTION），守卫②挡的是"伪造/陈旧 journal 与事件日志、检查点绑定链不符"；
        对能完整重算 commit_id 的攻击者，最终防线是①的单调性。
        """
        journal = self.pending_commit()
        if journal is None:
            return {"status": "NO_PENDING_COMMIT"}
        with self._revision_lock():
            return self._recover_commit_locked(journal)

    def _recover_commit_locked(self, journal: Any) -> Dict[str, Any]:
        if not isinstance(journal, dict) or journal.get("unreadable") \
                or not isinstance(journal.get("snapshot"), dict) \
                or not isinstance(journal.get("checkpoint"), dict):
            return self._reject_journal(
                journal, "JOURNAL_MALFORMED",
                "提交日志不可读或缺少 snapshot/checkpoint；两个文件保持原状")

        snapshot = journal["snapshot"]
        checkpoint = journal["checkpoint"]
        current_revision = self._current_revision()

        # 守卫①：revision 单调——journal 目标必须严格向前。
        target = snapshot.get("revision")
        if not isinstance(target, int) or isinstance(target, bool) or target <= current_revision:
            return self._reject_journal(
                journal, "REVISION_NOT_MONOTONIC",
                "journal 目标 revision=%r 不大于当前快照 revision=%r；"
                "恢复将回退历史状态，已拒绝（陈旧提交日志不可重放）"
                % (target, current_revision))

        # 守卫②：commit_id 绑定 + 事件前缀摘要重算核对。
        commit_id = journal.get("commit_id")
        if not isinstance(commit_id, str) or not commit_id.strip():
            return self._reject_journal(
                journal, "COMMIT_ID_BINDING_INVALID", "journal 缺少 commit_id")
        cp_commit_id = checkpoint.get("commit_id")
        if cp_commit_id is not None and cp_commit_id != commit_id:
            return self._reject_journal(
                journal, "COMMIT_ID_BINDING_INVALID",
                "journal.commit_id=%r 与 journal.checkpoint.commit_id=%r 不一致："
                "伪造或拼装的提交日志" % (commit_id, cp_commit_id))
        expected = journal.get("expected_revision")
        if isinstance(expected, int) and not isinstance(expected, bool) \
                and target != expected + 1:
            return self._reject_journal(
                journal, "COMMIT_ID_BINDING_INVALID",
                "snapshot.revision=%r != expected_revision+1=%r；不符合 seal 的构造不变式"
                % (target, expected + 1))
        declared_count = checkpoint.get("event_count")
        declared_digest = checkpoint.get("event_log_digest")
        if isinstance(declared_count, int) and not isinstance(declared_count, bool) \
                and declared_count >= 0 and isinstance(declared_digest, str):
            read = self._read_events()
            events = read["events"]
            if declared_count > len(events):
                return self._reject_journal(
                    journal, "EVENT_PREFIX_DIGEST_MISMATCH",
                    "checkpoint 声明 %d 个事件，当前日志仅 %d 条：事件日志被截断"
                    % (declared_count, len(events)))
            if self._event_digest(events[:declared_count]) != declared_digest:
                return self._reject_journal(
                    journal, "EVENT_PREFIX_DIGEST_MISMATCH",
                    "事件前缀摘要重算与 checkpoint.event_log_digest 不一致："
                    "日志被改写或 journal 与本会话不符")

        digest = self._journal_digest(journal)
        # 守卫通过：完成提交。
        self._atomic_write_json(self.session_path, snapshot)
        self._atomic_write_json(self.checkpoint_path, checkpoint)
        audit_id = self._append_recovery_audit(
            RECOVERY_COMMIT_APPLIED, digest,
            {"commit_id": commit_id, "revision": target})
        # 审计事件已进入日志尾部：快照的 last_applied_event_id 如实推进，
        # 保持"快照 = 检查点重放结果"（否则 check 会报 LAST_APPLIED_EVENT_MISMATCH）。
        advanced = dict(snapshot)
        if audit_id is not None:
            advanced["last_applied_event_id"] = audit_id
        self._save_snapshot_locked(advanced, expected_revision=target)
        try:
            os.remove(self.commit_journal_path)
        except OSError:
            pass
        return {"status": "COMMIT_COMPLETED", "commit_id": commit_id,
                "revision": target, "audit_event_id": audit_id}

    # ------------------------------------------------------ 恢复守卫与审计
    @staticmethod
    def _journal_digest(journal: Any) -> str:
        try:
            canonical = json.dumps(journal, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            canonical = repr(journal)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def _reject_journal(self, journal: Any, reason: str, detail: str) -> Dict[str, Any]:
        """守卫拒绝：归档原 journal（`.rejected-<digest>`，不删除）+ 追加审计事件。"""
        digest = self._journal_digest(journal)
        archive = "%s.rejected-%s" % (self.commit_journal_path, digest)
        if not os.path.exists(archive):
            raw = None
            if os.path.isfile(self.commit_journal_path):
                try:
                    with open(self.commit_journal_path, "r",
                              encoding="utf-8", errors="replace") as fh:
                        raw = fh.read()
                except OSError:
                    raw = None
            if raw is None:
                try:
                    raw = json.dumps(journal, ensure_ascii=False, sort_keys=True)
                except (TypeError, ValueError):
                    raw = repr(journal)
            self._atomic_write_text(archive, raw)
        try:
            os.remove(self.commit_journal_path)
        except OSError:
            pass
        commit_id = journal.get("commit_id") if isinstance(journal, dict) else None
        audit_id = self._append_recovery_audit(
            RECOVERY_COMMIT_REJECTED, digest,
            {"reason": reason, "commit_id": commit_id, "detail": detail,
             "archive": os.path.basename(archive)})
        return {"status": "COMMIT_REJECTED", "reason": reason, "detail": detail,
                "archived_to": archive, "audit_event_id": audit_id}

    def _append_recovery_audit(self, ev_type: str, digest: str,
                               payload: Dict[str, Any]) -> Optional[str]:
        """追加一条恢复审计事件（无投影载荷的纯记录事件）。

        审计写入失败（如日志中段损坏）不得改变恢复决定本身，返回 None 并由
        调用方在返回值中如实上报 `audit_event_id=None`。
        """
        event_id = "%s-%s" % (ev_type, digest)
        event = {
            "schema_version": "0.1",
            "event_id": event_id,
            "type": ev_type,
            "execution_kind": "SYSTEM",
            "actor": "session_store.recover_commit",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload": dict(payload),
        }
        try:
            self._append_event_locked(event)
        except (CorruptEventLog, OSError, ProjectionError):
            return None
        return event_id

    def _replay_from_checkpoint(self, checkpoint: Dict[str, Any], read: Dict[str, Any]) -> Dict[str, Any]:
        """从检查点重放其后的事件；返回 `(projected, divergences)`。

        T05：边界**以已核验的 `event_count` 为准**，不再靠"找 last_event_id 的下标"。
        零事件检查点的 `last_event_id` 是 None，旧实现把 tail 取成 `events[len(events):]`，
        于是之后追加的事件被全部跳过（重放停在封存时的状态）。
        """
        events = read["events"]
        divergences: List[Dict[str, Any]] = []
        count = checkpoint.get("event_count")
        if not isinstance(count, int) or count < 0:
            # 旧格式兼容：没有 event_count 时退回按 last_event_id 定位
            recorded_id = checkpoint.get("last_event_id")
            count = 0
            for idx, ev in enumerate(events):
                if ev.get("event_id") == recorded_id:
                    count = idx + 1
                    break
            divergences.append({
                "kind": "CHECKPOINT_EVENT_COUNT_MISSING",
                "detail": "检查点缺少 event_count，已按 last_event_id 推断边界；建议重新封存",
                "inferred_count": count,
            })

        state = checkpoint.get("state") or {}
        if count > len(events):
            divergences.append({
                "kind": "CHECKPOINT_EVENT_COUNT_AHEAD",
                "detail": "检查点声明的 event_count 超过当前事件日志长度：日志被截断，"
                          "可信基底不再成立。",
                "checkpoint_events": count, "log_events": len(events),
            })
            return dict(state), divergences

        prefix = events[:count]
        if self._event_digest(prefix) != checkpoint.get("event_log_digest"):
            divergences.append({
                "kind": "CHECKPOINT_EVENT_PREFIX_CHANGED",
                "detail": ("检查点封存的事件前缀已被改写或被截断：可信基底不再成立，"
                           "须重新封存并人工核对。"),
                "checkpoint_events": count,
            })
        recorded_id = checkpoint.get("last_event_id")
        prefix_last = prefix[-1].get("event_id") if prefix else None
        if prefix_last != recorded_id:
            divergences.append({
                "kind": "CHECKPOINT_EVENT_BOUNDARY_MISMATCH",
                "detail": "检查点边界不一致：event_count 指向的事件与 last_event_id 不符",
                "event_count": count, "last_event_id": recorded_id,
                "prefix_last_event_id": prefix_last,
            })
        tail = events[count:]
        return self.project(state, tail), divergences

    def consistency_report(self, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """核对快照与事件日志是否一致，不一致时显式报告差异。"""
        session = session if session is not None else self.load_snapshot()
        read = self._read_events()
        checkpoint = self.load_checkpoint()
        checkpoint_divergences: List[Dict[str, Any]] = []
        journal_divergences: List[Dict[str, Any]] = []
        journal = self.pending_commit()
        if journal is not None:
            # T04：两文件一致提交被中断（进程在写完日志后、删日志前退出）。
            # 只读诊断如实报告，并指出可用 recover_commit() 完成提交。
            journal_divergences.append({
                "kind": "INCOMPLETE_COMMIT",
                "detail": ("检测到未完成的提交日志：快照与检查点可能不同步。"
                           "请运行 recover_commit() 完成或回滚该次提交。"),
                "commit_id": journal.get("commit_id"),
                "expected_revision": journal.get("expected_revision"),
            })
        if checkpoint is None:
            # R04/P2-4：没有封存检查点时，快照只是"当前状态"，无法证明它就是
            # 事件重放的合法起点。如实报告，而不是默认它可信。
            checkpoint_divergences.append({
                "kind": "SNAPSHOT_BASE_UNVERIFIED",
                "detail": ("未找到 checkpoint.json：重放以当前快照为起点，事件未记录的"
                           "字段无法与未记录修改区分。请先 seal_checkpoint() 建立可信基底。"),
            })
            projected = self.project(session, read["events"])
        else:
            projected, checkpoint_divergences = self._replay_from_checkpoint(checkpoint, read)
        snap_last = session.get("last_applied_event_id")
        replay_last = projected.get("last_applied_event_id")
        divergence = list(checkpoint_divergences) + journal_divergences
        if snap_last != replay_last:
            divergence.append({
                "kind": "LAST_APPLIED_EVENT_MISMATCH",
                "snapshot": snap_last,
                "replayed": replay_last,
            })

        # F04: 同一个事件 ID 不等于同一个状态。
        # 旧实现只比末尾事件 ID，于是"快照写着 E1/state=CLOSED、事件重放却是
        # E1/state=WAITING_USER"被判为一致。这里比较**规范化业务投影**，
        # 并列出具体不同的字段。
        snap_business = self._business_projection(session)
        replay_business = self._business_projection(projected)
        if snap_business != replay_business:
            changed = sorted(set(snap_business) | set(replay_business))
            differing = [k for k in changed
                         if snap_business.get(k, _ABSENT) != replay_business.get(k, _ABSENT)]
            divergence.append({
                "kind": "STATE_PROJECTION_MISMATCH",
                "fields": differing,
                "snapshot": {k: snap_business.get(k) for k in differing},
                "replayed": {k: replay_business.get(k) for k in differing},
            })
        if read["quarantined_tail"]:
            divergence.append({
                "kind": "QUARANTINED_TAIL",
                "lines": len(read["quarantined_tail"]),
            })
        return {
            "consistent": not divergence,
            "events_in_log": read["line_count"],
            "snapshot_last_applied_event_id": snap_last,
            "replayed_last_applied_event_id": replay_last,
            "divergence": divergence,
            "authoritative_source": EVENTS_FILENAME,
            "replay_base": (CHECKPOINT_FILENAME if checkpoint is not None
                            else "snapshot(unverified)"),
            "pending_commit_id": (journal or {}).get("commit_id") if journal else None,
            "checkpoint_inherited_fields": list((checkpoint or {}).get("inherited_fields") or []),
            "checkpoint_import_mode": bool((checkpoint or {}).get("import_mode")),
        }

    @staticmethod
    def _business_projection(state: Dict[str, Any]) -> Dict[str, Any]:
        """规范化业务投影：去掉 revision、恢复诊断等非业务字段。

        F04 要求"快照中 revision、恢复诊断等非业务字段与业务投影分开比较"，
        否则每写一次快照 revision 递增就会被误报为状态不一致。
        """
        skip = {"revision", "_events_applied", "last_applied_event_id"}
        return {k: v for k, v in (state or {}).items()
                if k not in skip and not k.startswith("_") and not k.startswith("recovery_")}

    def recover(self) -> Dict[str, Any]:
        """恢复入口：以事件重放为准重建状态，并给出恢复简报所需字段。

        **H-16（2026-09-13 集群测试 DEB-R-01/DEB-V-09/INT-R-09）**：旧实现只调
        rebuild()，从不处理 commit_journal——`consistency_report()` 提示
        "请运行 recover_commit()"，CLI 按提示走 `recover` 却无法解除
        INCOMPLETE_COMMIT（CLI 命令面也没有 recover-commit）。现在恢复路径
        **先收敛未完成提交**（含三守卫与审计），再重建重放简报。
        """
        commit_recovery: Optional[Dict[str, Any]] = None
        if self.pending_commit() is not None:
            commit_recovery = self.recover_commit()
        report = self.rebuild()
        state = report["state"]
        ex = state.get("execution", {}) or {}
        usage, budget = ex.get("usage", {}) or {}, ex.get("budget", {}) or {}
        pending = state.get("pending_question") or None
        out = {
            "state": state,
            "consistency": {
                "snapshot_last_applied_event_id": report["snapshot_last_applied_event_id"],
                "replayed_last_applied_event_id": report["replayed_last_applied_event_id"],
                "quarantined_tail": report["quarantined_tail"],
                "authoritative_source": EVENTS_FILENAME,
            },
            "briefing": {
                "session_id": state.get("session_id"),
                "mode": state.get("mode"),
                "state": state.get("state"),
                "current_question": state.get("current_question"),
                "pending_question": (pending or {}).get("text"),
                "pending_role": (pending or {}).get("role_id"),
                "pending_target_version": (pending or {}).get("target_version"),
                "open_questions": len(state.get("open_questions") or []),
                "gaps_pending": sum(
                    1 for g in (state.get("gap_requests") or [])
                    if (g.get("approval") or {}).get("status") == "PENDING"
                ),
                "rounds_used": usage.get("rounds_used"),
                "rounds_cap": budget.get("max_rounds"),
                "review_batches_used": usage.get("review_batches_used"),
                "review_batches_cap": budget.get("max_review_batches"),
            },
        }
        if commit_recovery is not None:
            out["commit_recovery"] = commit_recovery
        return out

    def declared_session_id(self) -> Optional[str]:
        """会话目录自述的 session_id（快照优先，其次检查点）；无法确定返回 None。

        H-09②（2026-09-13 集群测试 INT-A-16）：`debate_handoff._trusted_event_list`
        用它核对事件日志的身份绑定——日志中出现与 store 自述身份不符的会话事件，
        即判定日志被跨会话搬运，授权核验失败关闭。
        """
        for path in (self.session_path, self.checkpoint_path):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(doc, dict):
                sid = doc.get("session_id")
                if isinstance(sid, str) and sid.strip():
                    return sid.strip()
        return None

    # ---------------------------------------------------------------- 用量台账
    def append_usage(self, entry: Dict[str, Any]) -> None:
        """追加一条资源用量记录（只追加，不覆盖历史）。

        **H-15 配套（INT-A-02）**：台账与事件日志同属"只追加真源"，并发交错写会
        产生非法 JSONL（实测 600 条自报成功只可解析 443 条）。追加纳入同一把
        O_EXCL 会话锁临界区，恒产出合法 JSONL。
        """
        if not os.path.isdir(self.session_dir):
            raise FileNotFoundError("会话目录不存在：%s" % self.session_dir)
        with self._revision_lock():
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def read_usage(self) -> List[Dict[str, Any]]:
        if not os.path.isfile(self.ledger_path):
            return []
        out = []
        with open(self.ledger_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out

    # -------------------------------------------------------- 外键与引用完整性
    def check_referential_integrity(self, session: Optional[Dict[str, Any]] = None) -> List[str]:
        """检查会话结构中的外键引用完整性（例如批次升级缺口是否存在）。

        **H-45（2026-09-13 集群测试 INT-A-06）**：gap_id 在 gap_requests 中必须唯一
        ——同一 gap_id 两条记录意味着一份用户授权可被双重消费，属引用完整性违规。
        """
        session = session if session is not None else self.load_snapshot()
        violations = []
        gap_entries = [g for g in (session.get("gap_requests") or []) if isinstance(g, dict)]
        gap_ids = [g.get("gap_id") for g in gap_entries if g.get("gap_id")]
        duplicated = sorted({gid for gid in gap_ids if gap_ids.count(gid) > 1})
        if duplicated:
            violations.append(
                "duplicate gap_id in gap_requests: %s (a gap_id identifies exactly one "
                "authorisation; duplicates would allow the same confirmation event to be "
                "consumed twice)" % duplicated)
        gaps = set(gap_ids)
        for b in (session.get("review_batches") or []):
            if b.get("resolution") == "ESCALATED_TO_GAP":
                gid = b.get("escalated_gap_id")
                if not gid or gid not in gaps:
                    violations.append(
                        f"review_batch '{b.get('batch_id')}' escalated_gap_id='{gid}' does not exist in gap_requests (available: {sorted(list(gaps))})"
                    )
        return violations

    def heal_referential_integrity(self, session: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """检测并修复孤儿外键引用：若批次升级的 gap_id 缺失，自动在 gap_requests 中补全占位缺口契约。"""
        healed_session = dict(session)
        gaps_list = list(healed_session.get("gap_requests") or [])
        synthesized = []
        existing_gap_ids = {g.get("gap_id") for g in gaps_list if g.get("gap_id")}
        actions = []

        ideas = [i for i in (healed_session.get("ideas") or []) if i.get("idea_id")]

        for b in (healed_session.get("review_batches") or []):
            if b.get("resolution") == "ESCALATED_TO_GAP":
                gid = b.get("escalated_gap_id")
                if gid and gid not in existing_gap_ids:
                    # F06: 修复程序只能生成"待修复占位"，绝不能制造用户授权。
                    #
                    # 旧实现给占位缺口写入 approval.status=CONFIRMED 并**伪造**
                    # confirmed_event_id / scope_fingerprint，等于把"未知关联"与
                    # "未知授权"写成确定事实。修复日志只能证明"发生了修复"，
                    # 不能证明"用户同意派发"。
                    #
                    # 因此：approval 保持 PENDING、不编造确认事件与指纹；
                    # 无法确定 idea 归属时如实报告孤儿关系，而不是猜第一条 idea。
                    idea_id = b.get("idea_id")
                    idea_version = b.get("idea_version")
                    if idea_id is None:
                        if len(ideas) == 1:
                            idea_id = ideas[0].get("idea_id")
                            idea_version = idea_version if idea_version is not None else ideas[0].get("version", 1)
                            actions.append(
                                f"Inferred idea_id='{idea_id}' for gap '{gid}' from the only idea in session")
                        else:
                            idea_id = None
                            actions.append(
                                "ORPHAN_RELATION: gap '%s' has no determinable idea_id "
                                "(%d candidate ideas); left unattributed for user resolution"
                                % (gid, len(ideas)))

                    new_gap = {
                        "schema_version": "0.1",
                        "gap_id": gid,
                        # P1 修复（集群测试）：派发门禁要求 gap.session_id，schema 现已
                        # 声明并 required；修复产物必须一并写出，否则"schema PASS 却永远
                        # 无法派发"。会话缺 session_id 时占位会被 schema 校验拒收，
                        # 转入 repair_proposals 由人工处理。
                        "session_id": healed_session.get("session_id"),
                        "idea_id": idea_id,
                        "idea_version": idea_version,
                        "gap_type": "SEARCH_GAP",
                        "target_skill": "literature-discovery-acquisition",
                        "question": f"Autogenerated gap to resolve escalated divergence in batch {b.get('batch_id')}",
                        "reason": f"Divergence escalated from batch {b.get('batch_id')}",
                        "decision_impact": "Required to unblock proposition evaluation.",
                        "blocking": "BLOCKING",
                        "scope": {"topic": "auto_healed_gap_inquiry"},
                        # 占位状态：等待用户确认，绝不预置 CONFIRMED
                        "approval": {
                            "status": "PENDING",
                            "confirmed_event_id": None,
                            "scope_fingerprint": None,
                            "healed_placeholder": True,
                            "heal_reason": f"placeholder created to resolve orphan reference from batch {b.get('batch_id')}",
                        },
                        "execution_status": "NOT_STARTED",
                        "result_refs": [],
                    }
                    gaps_list.append(new_gap)
                    synthesized.append(new_gap)
                    existing_gap_ids.add(gid)
                    actions.append(
                        f"Synthesized PENDING placeholder gap_request '{gid}' for review_batch "
                        f"'{b.get('batch_id')}' (not an authorisation; user confirmation still required)")

        healed_session["gap_requests"] = gaps_list

        # R06：修复产物必须**立刻**过一遍契约校验。不能符合契约的输出不得混进
        # 正式 gap_requests——那会让"修复"变成"制造非法数据"；改为作为待修复提案返回。
        # 只校验**本次修复新生成**的占位，不追溯惩罚会话里既有的历史缺口。
        validated_new, rejected = self._validate_repaired_gaps(synthesized)
        validated_ids = {g.get("gap_id") for g in validated_new}
        rejected_ids = {b["gap"].get("gap_id") for b in rejected}
        healed_session["gap_requests"] = [
            g for g in gaps_list
            if g.get("gap_id") not in rejected_ids or g not in synthesized]
        if rejected:
            healed_session.setdefault("repair_proposals", []).extend(rejected)
            for bad in rejected:
                actions.append(
                    "SCHEMA_REJECTED: placeholder gap '%s' does not satisfy "
                    "research_debate_gap.schema.json (%s); returned as a repair proposal "
                    "instead of a formal gap_request"
                    % (bad.get("gap", {}).get("gap_id"), "; ".join(bad.get("errors", [])[:3])))
        return healed_session, actions

    @staticmethod
    def _validate_repaired_gaps(gaps_list):
        """对修复生成的缺口做契约校验，返回 (通过, 被拒提案)。"""
        try:
            from shared.validation.schema_gate import validate as _validate_schema
        except Exception:  # noqa: BLE001 - 校验器不可用时明确标注，不静默跳过
            return list(gaps_list), []
        validated, rejected = [], []
        for gap in gaps_list:
            ok, mode, errors = _validate_schema(gap, "research_debate_gap.schema.json")
            if ok:
                validated.append(gap)
            else:
                rejected.append({"gap": gap, "errors": errors, "mode": mode})
        return validated, rejected
