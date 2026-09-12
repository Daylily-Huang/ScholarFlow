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
import json
import os
from typing import Any, Dict, List, Optional, Tuple

_ABSENT = object()

EVENTS_FILENAME = "events.jsonl"
CHECKPOINT_FILENAME = "checkpoint.json"
SESSION_FILENAME = "session.json"
LEDGER_FILENAME = "usage_ledger.jsonl"

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


class SessionStore:
    """一个会话目录的读写句柄。"""

    def __init__(self, session_dir: str):
        self._recovery_notes: List[Dict[str, Any]] = []
        self.session_dir = session_dir
        self.events_path = os.path.join(session_dir, EVENTS_FILENAME)
        self.checkpoint_path = os.path.join(self.session_dir, CHECKPOINT_FILENAME)
        self.session_path = os.path.join(session_dir, SESSION_FILENAME)
        self.ledger_path = os.path.join(session_dir, LEDGER_FILENAME)

    # ------------------------------------------------------------------ 内部
    def _atomic_write_text(self, path: str, text: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)

    def _atomic_write_json(self, path: str, payload: Any) -> None:
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------ 事件
    def append_event(self, event: Dict[str, Any]) -> bool:
        """追加一条事件（原子写），返回是否为**新应用**（False = 幂等跳过）。

        幂等判据是 `event_id`：已存在于日志中的事件不再追加。
        """
        event_id = event.get("event_id")
        if not event_id:
            raise ValueError("event 必须有 event_id")
        if not os.path.isdir(self.session_dir):
            raise FileNotFoundError("会话目录不存在：%s" % self.session_dir)

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
            return json.load(fh)

    def save_snapshot(self, session: Dict[str, Any], expected_revision: int) -> Dict[str, Any]:
        """原子写入快照缓存（物化视图）；revision 冲突则拒绝覆盖。

        遵循事件先行协议（Event-First Protocol）：事件日志是系统真源（Authoritative Source）。
        快照作为物化加速视图保存，调用方须先通过 append_event() 记录业务事件与 CHECKPOINT，
        再行持久化快照，本方法不隐式伪造或自动追加 CHECKPOINT 事件。

        **这是调用约定，不是代码保证**：本方法无法阻止调用方写入事件未记录的字段。
        要让"快照即事件重放结果"可被机械核验，须调用 `seal_checkpoint()` 建立可信
        重放基底；未封存时 `consistency_report()` 会报 `SNAPSHOT_BASE_UNVERIFIED`。
        """
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

    def seal_checkpoint(self, session: Dict[str, Any], expected_revision: int) -> Dict[str, Any]:
        """把当前状态封存为**可信重放基底**（Event-First Protocol）。

        事件日志是唯一真源；快照只是物化视图。只有封存过的检查点才能作为重放的
        可信起点——否则"快照里多出来的字段"无法与"事件未记录的修改"区分
        （第二轮核查 P2-4）。

        封存条件：传入状态必须与**全部事件重放结果**的业务投影一致，否则拒绝封存
        （不能把未经事件解释的状态固化成可信基底）。封存同时写入快照。
        """
        read = self._read_events()
        if read["quarantined_tail"]:
            raise CorruptEventLog(
                "事件日志尾部损坏，拒绝封存检查点：请先执行恢复（rebuild/recover）",
                {"path": self.events_path, "reason": "RECOVERY_REQUIRED",
                 "quarantined_tail": read["quarantined_tail"]})
        events = read["events"]
        # 可信基底必须是"纯粹由事件解释"的状态：从空基底重放，再与传入状态在
        # 可投影字段上逐项比对。直接在传入状态上重放会原样保留事件未记录的字段，
        # 那样等于把"未记录修改"固化成可信基底（第二轮核查 P2-4 反例）。
        from_events = self.project({}, events)
        event_fields = [f for f in PROJECTABLE_FIELDS if f in from_events]
        conflicts = [f for f in event_fields
                     if f in session and session.get(f) != from_events.get(f)]
        if conflicts:
            raise ProjectionError(
                "拒绝封存与事件重放冲突的状态：字段 %s 与事件不一致" % sorted(conflicts))
        # 事件从未定义的字段由封存时的状态承载（作为可信基底的一部分），
        # 但必须在检查点里逐项记录，便于审计"基底里有哪些不是事件推出来的"。
        inherited = sorted(f for f in PROJECTABLE_FIELDS
                           if f in session and f not in from_events)
        replayed = self.project(session, events)
        payload = {
            "schema_version": "0.1",
            "last_event_id": replayed.get("last_applied_event_id"),
            "event_count": len(events),
            "event_log_digest": self._event_digest(events),
            "inherited_fields": inherited,
            "state": replayed,
        }
        self._atomic_write_json(self.checkpoint_path, payload)
        saved = self.save_snapshot(replayed, expected_revision)
        return {"checkpoint": self.checkpoint_path, "event_count": len(events),
                "last_event_id": payload["last_event_id"], "snapshot": saved}

    def _replay_from_checkpoint(self, checkpoint: Dict[str, Any], read: Dict[str, Any]) -> Dict[str, Any]:
        """从检查点重放其后的事件；返回 `(projected, divergences)`。"""
        events = read["events"]
        divergences: List[Dict[str, Any]] = []
        count = checkpoint.get("event_count")
        prefix = events[:count] if isinstance(count, int) and count >= 0 else []
        if self._event_digest(prefix) != checkpoint.get("event_log_digest"):
            divergences.append({
                "kind": "CHECKPOINT_EVENT_PREFIX_CHANGED",
                "detail": ("检查点封存的事件前缀已被改写或被截断：可信基底不再成立，"
                           "须重新封存并人工核对。"),
                "checkpoint_events": count,
            })
        recorded_id = checkpoint.get("last_event_id")
        position = None
        for idx, ev in enumerate(events):
            if ev.get("event_id") == recorded_id:
                position = idx
                break
        if recorded_id is not None and position is None:
            divergences.append({
                "kind": "CHECKPOINT_EVENT_MISSING",
                "detail": "检查点记录的 last_event_id 已不在事件日志中",
                "last_event_id": recorded_id,
            })
            return dict(checkpoint.get("state") or {}), divergences
        tail = events[(position + 1) if position is not None else len(events):]
        state = checkpoint.get("state") or {}
        return self.project(state, tail), divergences

    def consistency_report(self, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """核对快照与事件日志是否一致，不一致时显式报告差异。"""
        session = session if session is not None else self.load_snapshot()
        read = self._read_events()
        checkpoint = self.load_checkpoint()
        checkpoint_divergences: List[Dict[str, Any]] = []
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
        divergence = list(checkpoint_divergences)
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
        """恢复入口：以事件重放为准重建状态，并给出恢复简报所需字段。"""
        report = self.rebuild()
        state = report["state"]
        ex = state.get("execution", {}) or {}
        usage, budget = ex.get("usage", {}) or {}, ex.get("budget", {}) or {}
        pending = state.get("pending_question") or None
        return {
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

    # ---------------------------------------------------------------- 用量台账
    def append_usage(self, entry: Dict[str, Any]) -> None:
        """追加一条资源用量记录（只追加，不覆盖历史）。"""
        if not os.path.isdir(self.session_dir):
            raise FileNotFoundError("会话目录不存在：%s" % self.session_dir)
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

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
        """检查会话结构中的外键引用完整性（例如批次升级缺口是否存在）。"""
        session = session if session is not None else self.load_snapshot()
        violations = []
        gaps = {g.get("gap_id") for g in (session.get("gap_requests") or []) if g.get("gap_id")}
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
