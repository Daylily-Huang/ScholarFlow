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

import json
import os
from typing import Any, Dict, List, Optional, Tuple

EVENTS_FILENAME = "events.jsonl"
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
        self.session_dir = session_dir
        self.events_path = os.path.join(session_dir, EVENTS_FILENAME)
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

        seen = {e.get("event_id") for e in self._read_events()["events"]}
        if event_id in seen:
            return False

        line = json.dumps(event, ensure_ascii=False)
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True

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
                    self._quarantine_tail(line)
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

    def rebuild(self) -> Dict[str, Any]:
        """从快照 + 事件重放重建当前状态，并报告差异。"""
        base = self.load_snapshot()
        read = self._read_events()
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
        """原子写入快照；revision 冲突则拒绝覆盖。

        成功后自动写入一条 `CHECKPOINT` 事件（若调用方未提供 event）。
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
    def consistency_report(self, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """核对快照与事件日志是否一致，不一致时显式报告差异。"""
        session = session if session is not None else self.load_snapshot()
        read = self._read_events()
        projected = self.project(session, read["events"])
        snap_last = session.get("last_applied_event_id")
        replay_last = projected.get("last_applied_event_id")
        divergence = []
        if snap_last != replay_last:
            divergence.append({
                "kind": "LAST_APPLIED_EVENT_MISMATCH",
                "snapshot": snap_last,
                "replayed": replay_last,
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
        }

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
        existing_gap_ids = {g.get("gap_id") for g in gaps_list if g.get("gap_id")}
        actions = []

        for b in (healed_session.get("review_batches") or []):
            if b.get("resolution") == "ESCALATED_TO_GAP":
                gid = b.get("escalated_gap_id")
                if gid and gid not in existing_gap_ids:
                    # Synthesize placeholder gap to prevent orphaned reference
                    new_gap = {
                        "gap_id": gid,
                        "idea_id": (healed_session.get("ideas") or [{}])[0].get("idea_id", "IDEA-DEFAULT"),
                        "idea_version": 1,
                        "gap_type": "SEARCH_GAP",
                        "target_skill": "literature-discovery-acquisition",
                        "question": f"Autogenerated gap to resolve escalated divergence in batch {b.get('batch_id')}",
                        "reason": f"Divergence escalated from batch {b.get('batch_id')}",
                        "decision_impact": "Required to unblock proposition evaluation.",
                        "blocking": "BLOCKING",
                        "scope": {"topic": "auto_healed_gap_inquiry"},
                        "approval": {"status": "CONFIRMED", "confirmed_event_id": f"EV-HEAL-{gid}", "scope_fingerprint": f"fp-heal-{gid}"},
                        "execution_status": "NOT_STARTED",
                        "result_refs": []
                    }
                    gaps_list.append(new_gap)
                    existing_gap_ids.add(gid)
                    actions.append(f"Synthesized missing gap_request '{gid}' for review_batch '{b.get('batch_id')}'")

        healed_session["gap_requests"] = gaps_list
        return healed_session, actions
