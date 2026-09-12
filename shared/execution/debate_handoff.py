#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-idea-debate ↔ 上游技能交接适配层（RFC-016 / M3）。

两件事：

1. **出向**：把本技能的 `GapRequest` 映射为前三个技能可消费的任务包。
   - `SEARCH_GAP` → `literature-discovery-acquisition`
   - `EXTRACTION_GAP` → `literature-evidence-extraction`
   - `SYNTHESIS_REQUEST` → `literature-synthesis`
   **前提**：上游现有载荷只有 `gap_type / target_skill / reason / suggested_query /
   date_range / mode` 之类字段，**没有** `gap_id`、`approval`、范围指纹。因此这是
   **单向映射**：保留原始 `GapRequest` 与映射记录，不反向覆盖上游文件，也不假设
   上游会回传我们需要的字段。

2. **入向**：把上游回流产物规范化为 `evidence_links`，并执行设计稿 §11.4 的
   **对齐硬规则**：`alignment = VERIFIED` 仅当回流记录的原文引句与定位在**命题本身**
   层面直接支持该命题；实体/关键词共现一律 `UNRESOLVED`；`CONTEXT`/`BOUNDARY`/
   `CHALLENGE` 不得记 `VERIFIED`。

引句比对口径与仓库既有 `quote_audit.py` 保持一致（NFC + 可混淆字符映射 + 空白折叠 +
小写 + 连字符断行重接），避免两套技能对"同一句话"给出不同判断。

只依赖标准库。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

#: 缺口类型 → 目标技能
TARGET_SKILLS = {
    "SEARCH_GAP": "literature-discovery-acquisition",
    "EXTRACTION_GAP": "literature-evidence-extraction",
    "SYNTHESIS_REQUEST": "literature-synthesis",
}

ALLOWED_RELATIONS = ("SUPPORT", "CHALLENGE", "BOUNDARY", "CONTEXT")
ALIGNMENTS = ("VERIFIED", "UNRESOLVED")

#: 命题中被引句覆盖到的最低比例。低于此值只能算"命中若干词"，不得记为支持。
#: 单实体词（如 "roads"）对多词命题的覆盖率远低于门槛，因此不会被升级。
SUBSTANTIVE_COVERAGE_THRESHOLD = 0.5

#: 否定线索。命中即视为告警：词面相似不代表支持，否定句尤其不能升级。
#: 审查报告 F01 指出简单否定词过滤不能宣称解决全部语义问题，因此这里只做
#: **告警与阻断**，不据此判定命题真假——语义裁决仍交人工或带出处的结构化判断。
NEGATION_MARKERS = (
    "not ", "no ", "never", "cannot", "can not", "does not", "do not", "did not",
    "is not", "are not", "was not", "were not", "without", "fail to", "fails to",
    "failed to", "no evidence", "no significant", "no difference", "rather than",
    "不", "无", "未", "没有", "并非", "不是", "不能", "无法", "否认", "缺乏",
)

#: F09：命题方向（relation）与"核验状态"（alignment）是两个正交维度。
#:
#: `relation` 回答"这条材料对当前主张是什么关系"：support / challenge / boundary / context。
#: `alignment` 回答"这个关系是否已经核实"：VERIFIED / UNRESOLVED。
#:
#: 现行规则把 CHALLENGE / BOUNDARY 一律记为 UNRESOLVED，是**刻意的保守选择**：
#: 它们不构成支持，因此不得进入支持计数。但这会把"已核实的反证"与"尚未判断的
#: 材料"混在同一档里。消费方若需要区分，应读取调用方提供的核验记录，
#: 不要仅凭 alignment 推断该反证是否已经核实。
#:
#: 注意：**已核实的反证可进入反证栏，但不得进入支持计数。**

#: 上游审计状态中，表示"该记录已被判定为不可信"的取值。
UPSTREAM_FAILED_STATUSES = ("unsupported", "unverified", "contradictory", "failed")

#: 定位对象中可作为有效锚点的字段。
LOCATION_ANCHOR_KEYS = ("page", "pages", "section", "table", "figure", "paragraph",
                        "anchor", "quote_start", "offset", "coordinate", "bbox")

#: 与 quote_audit.py 一致的少量常见可混淆字符（避免复制整张表导致漂移）
CONFUSABLE_TABLE = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u3000": " ",
}


# --------------------------------------------------------------------- 文本口径
def normalize_text(text: str) -> str:
    """NFC + 可混淆字符映射 + 空白折叠 + 小写（与 quote_audit.py 同口径）。"""
    t = unicodedata.normalize("NFC", text or "")
    for src, dst in CONFUSABLE_TABLE.items():
        t = t.replace(src, dst)
    return re.sub(r"\s+", " ", t).strip().lower()


def join_hyphen_breaks(text: str) -> str:
    """重接连字符断行：'step- wise' → 'stepwise'。"""
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


# --------------------------------------------------------------------- 出向映射
def scope_fingerprint(gap: Dict[str, Any]) -> str:
    """授权指纹：覆盖 question / scope / target_skill / budget_ref 四项。

    任一改变即产生不同指纹 → 旧确认必须失效。归一化后哈希，故排版差异不影响。
    """
    scope = gap.get("scope") or {}
    approval = gap.get("approval") or {}
    material = {
        "question": normalize_text(gap.get("question") or ""),
        "scope": {k: (normalize_text(str(v)) if not isinstance(v, (list, dict)) else v)
                  for k, v in sorted(scope.items())},
        "target_skill": gap.get("target_skill") or TARGET_SKILLS.get(gap.get("gap_type") or "", ""),
        "budget_ref": approval.get("budget_ref"),
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return "fp-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def to_upstream_payload(gap: Dict[str, Any]) -> Dict[str, Any]:
    """把 GapRequest 单向映射为上游任务包。仅填相关字段。"""
    gap_type = gap.get("gap_type")
    if gap_type not in TARGET_SKILLS:
        raise ValueError("未知 gap_type：%r" % gap_type)
    scope = gap.get("scope") or {}
    payload: Dict[str, Any] = {
        "gap_type": gap_type,
        "target_skill": gap.get("target_skill") or TARGET_SKILLS[gap_type],
        "reason": gap.get("decision_impact") or gap.get("reason") or "",
    }
    if gap_type == "SEARCH_GAP":
        payload["suggested_query"] = gap.get("question") or scope.get("topic") or ""
        # 可直接喂给 headless 检索的版本（见 references/evidence_handoff.md §4）
        payload["executable_query"] = to_executable_query(gap)
        if scope.get("topic"):
            payload["topic"] = scope["topic"]
        if scope.get("time_range"):
            payload["date_range"] = scope["time_range"]
    elif gap_type == "EXTRACTION_GAP":
        if scope.get("target_papers"):
            payload["target_paper"] = scope["target_papers"][0]
            if len(scope["target_papers"]) > 1:
                payload["additional_target_papers"] = scope["target_papers"][1:]
        payload["required_fields"] = list(scope.get("required_fields") or [])
    else:  # SYNTHESIS_REQUEST
        if scope.get("evidence_refs"):
            payload["evidence_refs"] = list(scope["evidence_refs"])
        if scope.get("target_claim"):
            payload["target_claim"] = scope["target_claim"]
    return payload


def to_executable_query(gap: Dict[str, Any], max_terms: int = 12) -> str:
    """把缺口转成可执行检索式（供 headless Discovery 直接消费）。

    **只从缺口本身取词**：主题 + 问题中的实词，**不把对话原文写进检索式**
    （设计稿 §11.2 第 4 步的硬要求）。已停用词与重复词会被去掉。
    """
    stop = {
        "的", "与", "和", "及", "或", "在", "是", "有", "没有", "对", "为", "了",
        "请问", "是否", "哪些", "什么", "怎么", "如何", "以及", "the", "a", "an",
        "of", "and", "or", "for", "in", "on", "to", "is", "are", "does", "do",
    }
    scope = gap.get("scope") or {}
    question = gap.get("question") or ""
    # 疑问句式整体剥离：它们是提问形式，不是检索词
    for pat in ("是否已被系统研究", "是否存在系统差异", "是否存在", "是否影响", "是否",
                "有哪些", "哪些", "是什么", "什么", "如何", "怎么", "请问"):
        question = question.replace(pat, " ")
    parts = [scope.get("topic") or "", question]
    tokens: List[str] = []
    for part in parts:
        for tok in re.split(r"[\s,，。；;：:、/()（）]+", part):
            tok = tok.strip()
            if not tok or tok.lower() in stop or tok in tokens:
                continue
            tokens.append(tok)
    return " ".join(tokens[:max_terms])


#: 可作为用户授权的确认事件类型。CHECKPOINT / ROLE_RESPONSE 等一律不算授权。
CONFIRMATION_EVENT_TYPES = ("GAP_CONFIRMED", "GAP_APPROVED", "USER_CONFIRMATION")

#: 事件执行来源：只有 USER 才可能是用户授权。
NON_USER_EXECUTION_KINDS = ("SYSTEM", "ROLE_SWITCH", "INDEPENDENT_AGENT", "SELF_CHECK")

#: `execution_kind` 缺失时可接受的用户标识。
USER_ACTOR_NAMES = ("user", "human", "用户", "研究者", "学者", "researcher")


def _trusted_event_list(session_store: Optional[Any]) -> Optional[List[Dict[str, Any]]]:
    """从可信存储读取事件列表；无存储或不可读时返回 None（调用方须失败关闭）。

    R05：只接受外部存储对象（`SessionStore` / 任何带 `read_events()` 或
    `_read_events()` 的对象）。`gap` 自带的 `_events` / `_session_store` 是调用方
    自述内容，不构成授权证据，故不再支持。
    """
    if session_store is None:
        return None
    reader = getattr(session_store, "read_events", None)
    if callable(reader):
        try:
            parsed = reader()
        except Exception:
            return None
    else:
        reader = getattr(session_store, "_read_events", None)
        if not callable(reader):
            return None
        try:
            parsed = reader()
        except Exception:
            return None
    if isinstance(parsed, dict):
        events = parsed.get("events")
    else:
        events = parsed
    return events if isinstance(events, list) else None


def _validate_confirmation_event(event: Dict[str, Any], gap: Dict[str, Any],
                                 current_fp: str) -> Optional[Dict[str, Any]]:
    """核对确认事件本身是否构成对**本缺口**的用户授权；不通过时返回拒绝结果。"""
    ev_type = event.get("type") or event.get("event_type")
    if ev_type not in CONFIRMATION_EVENT_TYPES:
        return {"reason": "CONFIRMATION_EVENT_TYPE_INVALID",
                "details": ["event type %r is not a user confirmation event (accepted: %s)"
                            % (ev_type, ", ".join(CONFIRMATION_EVENT_TYPES))]}

    exec_kind = event.get("execution_kind")
    actor = str(event.get("actor") or "").strip().lower()
    if exec_kind in NON_USER_EXECUTION_KINDS:
        return {"reason": "CONFIRMATION_EVENT_NOT_USER",
                "details": ["execution_kind=%r means the event was not produced by the user"
                            % exec_kind]}
    if exec_kind != "USER" and actor not in USER_ACTOR_NAMES:
        return {"reason": "CONFIRMATION_EVENT_NOT_USER",
                "details": ["actor=%r, execution_kind=%r: a user-sourced event is required"
                            % (event.get("actor"), exec_kind)]}

    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

    ev_session = event.get("session_id") or payload.get("session_id")
    gap_session = gap.get("session_id")
    if not gap_session:
        return {"reason": "APPROVAL_SESSION_UNBOUND",
                "details": ["gap.session_id is absent; the approval cannot be tied to a session"]}
    if ev_session != gap_session:
        return {"reason": "APPROVAL_SESSION_UNBOUND",
                "details": ["Event session %r does not match gap session %r"
                            % (ev_session, gap_session)]}

    ev_gap = payload.get("gap_id") or event.get("gap_id")
    if ev_gap != gap.get("gap_id"):
        return {"reason": "CONFIRMATION_EVENT_GAP_MISMATCH",
                "details": ["Event gap_id %r does not match gap %r"
                            % (ev_gap, gap.get("gap_id"))]}

    ev_idea = payload.get("idea_id")
    if ev_idea != gap.get("idea_id"):
        return {"reason": "APPROVAL_IDEA_UNBOUND",
                "details": ["Event idea_id %r does not match gap idea_id %r"
                            % (ev_idea, gap.get("idea_id"))]}

    ev_ver = payload.get("idea_version")
    if ev_ver != gap.get("idea_version"):
        return {"reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "details": ["Event idea_version %r does not match current idea_version %r"
                            % (ev_ver, gap.get("idea_version"))]}

    ev_fp = payload.get("scope_fingerprint")
    if not ev_fp:
        return {"reason": "CONFIRMATION_EVENT_SCOPE_UNBOUND",
                "details": ["The confirmation event carries no scope_fingerprint; it cannot "
                            "prove which scope was approved."]}
    if ev_fp != current_fp:
        return {"reason": "CONFIRMATION_EVENT_SCOPE_MISMATCH",
                "details": ["Event scope_fingerprint %r does not match the current scope %r"
                            % (ev_fp, current_fp)]}
    return None


def prepare_dispatch(gap: Dict[str, Any], session_store: Optional[Any] = None) -> Dict[str, Any]:
    """派发前的门禁：未确认不得执行；范围变更须先失效旧确认。

    **R05（第二轮核查）授权核验契约**：范围指纹只是任务内容摘要，不是用户授权证明。
    因此本函数要求调用方提供**可信事件上下文**（`SessionStore` 或任何带
    `read_events()` / `_read_events()` 的存储对象，其事件来自会话目录而不是调用方
    自述），并核对确认事件本身：

      - 事件类型必须是用户确认类事件（`GAP_CONFIRMED` 等），`CHECKPOINT` /
        `ROLE_RESPONSE` 等一律不算授权；
      - `execution_kind` 必须是 `USER`（或缺失时 `actor` 为人类用户标识），
        `SYSTEM` / `ROLE_SWITCH` / `INDEPENDENT_AGENT` / `SELF_CHECK` 不算；
      - 事件必须绑定同一 `session_id`、`gap_id`、`idea_id`、`idea_version`，
        且其 `scope_fingerprint` 必须等于当前指纹。

    **不提供事件上下文即失败关闭**（`CONFIRMATION_CONTEXT_MISSING`）。不再接受
    `gap` 自带的 `_events` / `_session_store`：调用方自述的事件不构成授权证据。

    返回 `{"dispatchable": bool, "reason": str, "payload": {...} | None, "fingerprint": str,
    "must_reconfirm": bool, "idempotent_replay": bool}`。
    """
    approval = gap.get("approval") or {}
    status = approval.get("status")
    current_fp = scope_fingerprint(gap)
    recorded_fp = approval.get("scope_fingerprint")

    if status != "CONFIRMED":
        return {"dispatchable": False, "reason": "APPROVAL_NOT_CONFIRMED",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": status in ("PENDING", "INVALIDATED"),
                "idempotent_replay": False}

    # F05: 指纹缺失必须停止，而不是跳过比较。
    if not recorded_fp:
        return {"dispatchable": False, "reason": "APPROVAL_BINDING_MISSING",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["approval.scope_fingerprint is absent; a bare "
                            "status=CONFIRMED string is not a verifiable approval."]}

    if recorded_fp != current_fp:
        return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False}

    confirmed_event = approval.get("confirmed_event_id") or gap.get("confirmed_event_id")
    if not confirmed_event:
        return {"dispatchable": False, "reason": "APPROVAL_CONFIRMATION_UNBOUND",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["No confirmed_event_id: the approval cannot be traced back "
                            "to a user confirmation event."]}

    # R05: 版本必须双向可比较；缺任一侧即失败关闭（旧实现两侧缺一就跳过比较）。
    approved_ver = approval.get("approved_idea_version")
    actual_ver = gap.get("idea_version")
    if approved_ver is None or actual_ver is None:
        return {"dispatchable": False, "reason": "APPROVAL_IDEA_VERSION_UNBOUND",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["approved_idea_version=%r, gap.idea_version=%r: both sides are "
                            "required to prove the approval still covers the current idea."
                            % (approved_ver, actual_ver)]}
    if approved_ver != actual_ver:
        return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["idea_version changed: approved %r, current %r"
                            % (approved_ver, actual_ver)]}

    for field, reason in (("session_id", "APPROVAL_SESSION_UNBOUND"),
                          ("idea_id", "APPROVAL_IDEA_UNBOUND")):
        expected = approval.get(field)
        actual = gap.get(field)
        if expected is not None and actual is not None and expected != actual:
            return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                    "payload": None, "fingerprint": current_fp,
                    "must_reconfirm": True, "idempotent_replay": False,
                    "details": ["%s changed: approved %r, current %r"
                                % (field, expected, actual)]}

    if gap.get("scope_changed"):
        return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False}

    # R05: RUNNING 在途幂等拒绝
    exec_status = gap.get("execution_status")
    if exec_status in ("RUNNING", "IN_PROGRESS"):
        return {"dispatchable": False, "reason": "ALREADY_RUNNING_IN_FLIGHT",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": False, "idempotent_replay": True,
                "details": ["Task is currently in flight (execution_status=%r); duplicate dispatch blocked."
                            % exec_status]}

    if exec_status == "COMPLETE":
        return {"dispatchable": False, "reason": "ALREADY_COMPLETE_IDEMPOTENT",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": False, "idempotent_replay": True}

    # R05: 授权上下文必须是外部可信存储；调用方自述的 gap._events 不予采信。
    event_list = _trusted_event_list(session_store)
    if event_list is None:
        return {"dispatchable": False, "reason": "CONFIRMATION_CONTEXT_MISSING",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["A trusted SessionStore is required: a fingerprint is a summary "
                            "of the task, not proof that the user approved it."]}

    matching_event = next((e for e in event_list
                           if (e.get("event_id") or e.get("id")) == confirmed_event), None)
    if not matching_event:
        return {"dispatchable": False, "reason": "CONFIRMATION_EVENT_NOT_FOUND",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False,
                "details": ["confirmed_event_id %r not found in the trusted event store"
                            % confirmed_event]}

    refusal = _validate_confirmation_event(matching_event, gap, current_fp)
    if refusal is not None:
        refusal.update({"dispatchable": False, "payload": None,
                        "fingerprint": current_fp,
                        "must_reconfirm": True, "idempotent_replay": False})
        return refusal

    return {"dispatchable": True, "reason": "OK",
            "payload": to_upstream_payload(gap), "fingerprint": current_fp,
            "must_reconfirm": False, "idempotent_replay": False}


# --------------------------------------------------------------------- 入向回流
def _ngrams(text: str, n: int = 2) -> set:
    """字符 n-gram 集合。

    **为什么不能只用词元切分**：中文没有空格，按 ``re.findall(词类)`` 会把一整段
    汉字切成**一个** token，于是"引句包含命题"这种最明显的支持关系也算不出相似度，
    造成假阴性。因此词元与字符 n-gram 并用。
    """
    t = re.sub(r"\s+", "", text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _units(text: str) -> set:
    """混合比对单元：拉丁词元 + 字符 2-gram（对中英文都稳健）。"""
    words = set(re.findall(r"[a-z0-9]+", text, re.UNICODE))
    return words | _ngrams(text, 2)


def _compare(quote: str, reference: str) -> Tuple[bool, str, float]:
    """引句对某条参照文本（命题或已确认变体）的支持判定。

    口径（与设计稿 §11.4 一致，**宁可判 UNRESOLVED 也不升级**）：
      1. 归一化后一方包含另一方 → EXACT（最直接的支持）；
      2. 参照文本的比对单元被引句覆盖到 ≥ `QUOTE_OVERLAP_THRESHOLD` → OVERLAP
         （引句通常包含额外上下文，故看**参照侧覆盖率**而非对称相似度）；
      3. 其余 → 不支持（`KEYWORD_ONLY`）。
    """
    q = normalize_text(join_hyphen_breaks(quote))
    p = normalize_text(join_hyphen_breaks(reference))
    if not q or not p:
        return False, "EMPTY", 0.0
    if p in q:
        # 引句包含整个命题（通常还带额外上下文）→ 真正的字面命中。
        return True, "EXACT", 1.0
    if q in p:
        # 方向相反：引句只是命题的一个片段。**不支持方向与覆盖率都取决于此**，
        # 因此单列 FRAGMENT，交由调用方按实质覆盖率裁决，而不是直接判 1.0。
        frag_ratio = len(q) / max(1, len(p))
        return frag_ratio >= SUBSTANTIVE_COVERAGE_THRESHOLD, "FRAGMENT", frag_ratio
    pu, qu = _units(p), _units(q)
    if not pu:
        return False, "EMPTY", 0.0
    ratio = len(pu & qu) / len(pu)
    if ratio >= QUOTE_OVERLAP_THRESHOLD:
        return True, "OVERLAP", ratio
    return False, "KEYWORD_ONLY", ratio


def _quote_supported_by(quote: str, proposition: str) -> Tuple[bool, str]:
    """判断引句是否在**命题本身**层面提供支持。"""
    ok, how, _ = _compare(quote, proposition)
    return ok, how


def is_text_match(how: str) -> bool:
    """``how`` 是否属于"原文中出现了这段文字"层面。

    审查报告 F01 要求把 `_compare()` 的结论**降格为 text_match**：它只能回答
    "引句与命题在字面上重合了多少"，不能回答"引句是否支持该命题"。语义判定必须
    另走带出处的结构化检查。此函数是两者之间的显式分界。
    """
    return how in ("EXACT", "OVERLAP", "FRAGMENT")


def detect_negation_mismatch(quote: str, proposition: str) -> Optional[str]:
    """引句是否以否定形式谈论命题？返回命中的否定线索，无则 ``None``。

    F01 的反例是 ``It is not true that roads reduce gene flow.``——它**包含**命题
    字面，但语义相反。只要引句带否定线索而命题本身不带，就不能作为支持证据。
    """
    if not quote.strip() or not proposition.strip():
        return None
    q = normalize_text(quote)
    pr = normalize_text(proposition)
    if any(mark in pr for mark in NEGATION_MARKERS):
        return None  # 命题本身即否定式，不适用此规则
    for mark in NEGATION_MARKERS:
        if mark in q:
            return mark
    return None


def location_anchor(record: Dict[str, Any]) -> Tuple[bool, str]:
    """定位是否提供了可用于回查的实质锚点。

    ``{"page": null}``、``{}`` 这类"看着有 location 字段、实际无法回查"的情况必须
    判为无效。允许非 PDF 来源，因此段落/表格/偏移等锚点同样有效。
    """
    loc = record.get("location")
    if not isinstance(loc, dict) or not loc:
        return False, "MISSING_LOCATION"
    for key in LOCATION_ANCHOR_KEYS:
        val = loc.get(key)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        if isinstance(val, (list, tuple, dict)) and not val:
            continue
        return True, ""
    return False, "INVALID_LOCATION"


def upstream_audit_failed(record: Dict[str, Any]) -> Optional[str]:
    """上游是否已把该记录判为不可信？"""
    for key in ("audit_status", "claim_status", "verification_status",
                "fulltext_verification_status"):
        val = record.get(key)
        if isinstance(val, str) and val.strip().lower() in UPSTREAM_FAILED_STATUSES:
            return "%s=%s" % (key, val)
    return None


def _has_cjk(text: str) -> bool:
    """文本是否含 CJK 汉字。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _has_latin_word(text: str) -> bool:
    """文本是否含拉丁字母词（≥2 个字母，避免把单位符号误当语言）。"""
    return re.search(r"[A-Za-z]{2,}", text) is not None


def detect_language_mismatch(quote: str, proposition: str) -> bool:
    """引句与命题是否分属不同书写系统（中文命题 vs 英文引句，或反之）。

    **为什么必须单独标注**：`_quote_supported_by` 用「拉丁词元 + 字符 2-gram」比对，
    跨语言时 2-gram 交集恒为空，命题侧覆盖率恒为 0 → 永远 `KEYWORD_ONLY`。
    这在结果上与「查了、但文献确实不支持」完全一样；而「英文文献逐字支持中文命题」
    恰是本技能的常态场景（用户命题为中文，命中的多为英文文献）。

    因此本函数只做**知情标注**：把这种情况显式标出来，使下游能区分
    「机制上无法判定」与「判定为不支持」。它**不改变** `alignment`：
    跨语言引句仍然不得升级为 `VERIFIED`（要升级需要用户确认的目标语言命题变体，
    见设计稿 §11.4）。
    """
    q, p = normalize_text(quote), normalize_text(proposition)
    if not q or not p:
        return False
    return ((_has_cjk(p) and not _has_cjk(q)) or (_has_cjk(q) and not _has_cjk(p)))


#: 命题比对单元的覆盖率阈值；低于此视为"只命中关键词或落入其他上下文"，一律不升级为支持。
#: 取 0.85 偏严：宁可把措辞差异较大的引句判为 UNRESOLVED，也不误升级为支持。
QUOTE_OVERLAP_THRESHOLD = 0.85

#: 两条独立翻译之间至少要有这么高的互相覆盖率，才认为它们的含义一致。
#: 低于此说明翻译分歧过大，拿它当参照会把一种误译变成"证据"。
VARIANT_AGREEMENT_THRESHOLD = 0.85

#: 变体对齐状态
VARIANT_STATUS = ("ALIGNED", "PENDING_CONFIRMATION", "NOT_APPLICABLE")


def variant_fingerprint(variant: Dict[str, Any]) -> str:
    """变体指纹：覆盖该变体翻译的源命题文本（`source_text`）。"""
    payload = {"source_text": normalize_text(variant.get("source_text") or "")}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def proposition_fingerprint(proposition: str) -> str:
    """命题指纹，用于确认变体是否仍然翻译的是**当前**命题。"""
    return variant_fingerprint({"source_text": proposition})


def _script_of(text: str) -> str:
    """粗判书写系统：`CJK` / `LATIN` / `NONE`（足够用于选参照语言，不假装是语言识别）。"""
    if _has_cjk(text):
        return "CJK"
    if _has_latin_word(text):
        return "LATIN"
    return "NONE"


def _confirmed_variants(
        proposition: str,
        variants: Optional[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """分离已确认 / 未确认（或已失效）的变体。

    四条硬约束，任一不满足即视为**不可用于升级**：
      1. `approval.status == CONFIRMED`；
      2. `approval.confirmed_by == "user"` —— 禁止 AI 自我确认（否则等于自造命题）；
      3. `text` 非空；
      4. **翻译的正是当前命题**：`source_text` 必须与传入的 `proposition` 一致。
         实测教训（本层自带的真缺陷）：指纹若只与变体自身的 `source_text` 自比，
         它**恒等**，命题改了旧变体照样能升级。必须拿当前命题去比。
    """
    ready: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    current = proposition_fingerprint(proposition)
    for v in variants or []:
        approval = v.get("approval") or {}
        source = v.get("source_text")
        translated_current = source is not None and variant_fingerprint(v) == current
        fp = approval.get("scope_fingerprint")
        fp_ok = (not fp) or fp == current
        ok = (approval.get("status") == "CONFIRMED"
              and approval.get("confirmed_by") == "user"
              and bool((v.get("text") or "").strip())
              and translated_current
              and fp_ok)
        if ok:
            ready.append(v)
        else:
            blocked.append(dict(v, invalid_reason=(
                "SOURCE_TEXT_MISMATCH" if not translated_current else
                "FINGERPRINT_MISMATCH" if not fp_ok else
                "NOT_USER_CONFIRMED")))
    return ready, blocked


def _variants_agree(a: str, b: str) -> bool:
    """两条（已确认）翻译是否互相印证：双向覆盖率都不低于一致性阈值。"""
    ok_ab, _, ratio_ab = _compare(a, b)
    ok_ba, _, ratio_ba = _compare(b, a)
    if not (ok_ab and ok_ba):
        return False
    return min(ratio_ab, ratio_ba) >= VARIANT_AGREEMENT_THRESHOLD


def align_against_proposition(quote: str, proposition: str,
                              variants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """跨语言对齐判定：引句能否在**命题层面**获得支持。

    返回 `{"supported", "how", "ratio", "variant_ref", "variant_status", "reason"}`。

    判定链（按序，先命中先返回）：

    1. **直接命中底层命题**（EXACT / OVERLAP）→ 支持，`ALIGNED`；
    2. **命中 ≥ 2 条已确认且互相印证的同书写系统变体**（双向覆盖率 ≥
       `VARIANT_AGREEMENT_THRESHOLD`）→ 支持，`ALIGNED`。
       要求两条独立翻译互相印证，是为了拦住"把一种误译当成证据"；
    3. **只命中 1 条已确认变体**，或命中多条但互相不印证 → **不升级**，
       `PENDING_CONFIRMATION`，如实报告最高覆盖率，交由用户裁决；
    4. **只命中未确认 / 已失效变体** → 不升级，`PENDING_CONFIRMATION`。
       未确认变体是对比记录，不是命题本身；AI 也不得自我确认；
    5. 都不命中 → 不升级，`NOT_APPLICABLE`。
    """
    quote_script = _script_of(quote)
    ready, blocked = _confirmed_variants(proposition, variants)

    ok, how, ratio = _compare(quote, proposition)
    if ok:
        return {"supported": True, "how": how, "ratio": ratio, "variant_ref": None,
                "variant_status": "ALIGNED", "reason": "引句直接命中命题本身"}

    def same_script(v: Dict[str, Any]) -> bool:
        vt = v.get("text") or ""
        if quote_script == "NONE":
            return True
        return _script_of(vt) == quote_script

    ready_same = [v for v in ready if same_script(v)]
    scored = []
    for v in ready_same:
        vok, vhow, vratio = _compare(quote, v["text"])
        scored.append({"variant": v, "ok": vok, "how": vhow, "ratio": vratio})
    hits = [s for s in scored if s["ok"]]

    if len(hits) >= 2:
        best = max(hits, key=lambda s: s["ratio"])
        # 至少要有两条互相印证，否则退回"待确认"
        for i in range(len(hits)):
            for j in range(i + 1, len(hits)):
                if _variants_agree(hits[i]["variant"]["text"], hits[j]["variant"]["text"]):
                    return {"supported": True, "how": "VARIANT_AGREEMENT",
                            "ratio": best["ratio"],
                            "variant_ref": best["variant"].get("variant_ref"),
                            "variant_status": "ALIGNED",
                            "reason": "引句命中至少两条互相印证的已确认变体"}
        return {"supported": False, "how": "VARIANT_DISAGREEMENT",
                "ratio": best["ratio"],
                "variant_ref": best["variant"].get("variant_ref"),
                "variant_status": "PENDING_CONFIRMATION",
                "reason": "命中的多条已确认变体之间互相不印证，需用户裁决译法"}

    if len(hits) == 1:
        h = hits[0]
        return {"supported": False, "how": "VARIANT_NEEDS_SECOND_OPINION",
                "ratio": h["ratio"], "variant_ref": h["variant"].get("variant_ref"),
                "variant_status": "PENDING_CONFIRMATION",
                "reason": ("仅命中一条已确认变体，缺少第二条独立翻译互相印证；"
                           "按跨语言规则不升级，请用户补充或确认第二条译法")}

    blocked_same_script = [v for v in blocked if same_script(v)]

    # 未确认 / 已失效变体命中：只作报告，绝不升级
    for v in blocked_same_script:
        vok, _, vratio = _compare(quote, v.get("text") or "")
        if vok:
            return {"supported": False, "how": "VARIANT_UNCONFIRMED",
                    "ratio": vratio, "variant_ref": None,
                    "variant_status": "PENDING_CONFIRMATION",
                    "reason": ("引句只命中一条**未经用户确认或已失效**的变体（%s）；"
                               "AI 不得自我确认译法，故不升级"
                               % v.get("invalid_reason", "NOT_USER_CONFIRMED"))}

    # `PENDING_CONFIRMATION` 的语义是"差用户再确认一步"：只要确有同书写系统的变体记录
    # （已确认但未命中、未确认、或已失效），就不该退回"不适用"——
    # 那会把"补一条译法就能判"的待办事项，掩盖成"无事可做"。
    if blocked_same_script or scored:
        # 报告覆盖率时取"引句对命题或任一同书写系统变体"的最高值，
        # 否则会把"与变体已相当接近（如 0.59）"谎报成 0.0。
        best_ratio = max([s["ratio"] for s in scored] + [ratio])
        return {"supported": False, "how": "KEYWORD_ONLY", "ratio": best_ratio,
                "variant_ref": None, "variant_status": "PENDING_CONFIRMATION",
                "reason": ("存在同书写系统的命题变体，但尚不足以判定：引句既未命中它，"
                           "也缺第二条独立译法互相印证；请用户确认/补充译法后重判")}

    best_ratio = max([s["ratio"] for s in scored], default=ratio)
    return {"supported": False, "how": "KEYWORD_ONLY", "ratio": best_ratio,
            "variant_ref": None, "variant_status": "NOT_APPLICABLE",
            "reason": "未命中命题或任何变体"}


#: 允许升级为实证发现的语义角色。
EMPIRICAL_SEMANTIC_ROLES = ("CURRENT_STUDY_RESULT", "CURRENT_STUDY_OBSERVATION")

#: 显式语义核验凭据必须携带的绑定字段。
SEMANTIC_BINDING_FIELDS = ("evidence_id", "proposition_fingerprint",
                           "verifier", "verification_ref")


def verify_semantic_support(
    quote: str,
    proposition: str,
    record: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """结构化语义核验：引句是否为当前研究的实证发现，而非问题/假说/引文/条件/反驳。

    **R01（第二轮核查）判定契约**：

      - 模式规则**只用于排除**（研究问题、假说、引述、条件句、被反驳结论），命中即
        `UNRESOLVED` 并给出具体问题码；
      - **默认结果是 `UNRESOLVED`**。未命中任何排除规则**不等于**已证实——那只是
        "规则没有排除它"，不构成语义判断已经完成；
      - 只有携带**绑定完整**的显式语义核验凭据
        （`record["semantic_verification"]`，含 `evidence_id` / `proposition_fingerprint`
        / `verifier` / `verification_ref`，且命题版本未过期）时，才允许升级为
        `VERIFIED`。凭据由语义核验环节写出，不由本函数生成，也不靠字符串
        `status=VERIFIED` 自证。

    返回 `(semantic_record, problem_code)`；`problem_code` 非空时不得升级为支持。
    """
    explicit = record.get("semantic_verification")
    if isinstance(explicit, dict) and explicit.get("status"):
        return _validate_explicit_semantic_record(explicit, proposition, record)

    # 记录自带的角色标注：只用于排除。
    sem_role = record.get("semantic_role") or record.get("source_role")
    if sem_role in ("REFERENCED_WORK", "BACKGROUND"):
        return {
            "status": "UNRESOLVED",
            "semantic_role": sem_role,
            "epistemic_status": "EXTERNAL_CITATION",
            "is_empirical_result": False,
            "reasoning": "引句属已有文献或背景介绍，非当前论文实证发现",
        }, "REFERENCED_WORK_NOT_RESULT"
    if sem_role in ("DISCUSSION_INTERPRETATION", "LIMITATION"):
        return {
            "status": "UNRESOLVED",
            "semantic_role": sem_role,
            "epistemic_status": "INTERPRETATION_OR_SPECULATION",
            "is_empirical_result": False,
            "reasoning": "引句属讨论推测或研究局限，非确定性实证结果",
        }, "HYPOTHESIS_NOT_RESULT"

    excluded = _exclusion_semantic_role(quote)
    if excluded is not None:
        return excluded

    # 默认：没有任何已完成的语义判断凭据 → 保持未决，绝不默认放行。
    return {
        "status": "UNRESOLVED",
        "semantic_role": "UNVERIFIED",
        "epistemic_status": "UNVERIFIED",
        "is_empirical_result": False,
        "reasoning": ("未命中排除规则只说明规则没有排除它，不构成语义判断已完成；"
                      "缺少绑定完整的显式语义核验凭据（semantic_verification），"
                      "不得升级为支持"),
    }, "SEMANTIC_VERIFICATION_REQUIRED"


def _validate_explicit_semantic_record(explicit: Dict[str, Any], proposition: str,
                                       record: Dict[str, Any]
                                       ) -> Tuple[Dict[str, Any], Optional[str]]:
    """校验显式语义核验凭据的绑定完整性；不完整或过期一律不得升级。"""
    role = explicit.get("semantic_role") or "UNKNOWN"
    is_emp = bool(explicit.get("is_empirical_result", role in EMPIRICAL_SEMANTIC_ROLES))
    status = explicit.get("status")

    bound = {
        "status": status,
        "semantic_role": role,
        "epistemic_status": explicit.get("epistemic_status") or "UNVERIFIED",
        "is_empirical_result": bool(is_emp and status == "VERIFIED"),
        "reasoning": explicit.get("reasoning") or explicit.get("rationale") or "",
    }

    if status != "VERIFIED":
        code = ("SEMANTIC_VERIFICATION_FAILED" if status == "REJECTED"
                else "SEMANTIC_VERIFICATION_UNRESOLVED")
        return bound, code

    # status=VERIFIED 只是自述：必须逐项核对绑定，缺一项即失败关闭。
    evidence_id = record.get("evidence_id") or record.get("id")
    if str(explicit.get("evidence_id") or "") != str(evidence_id or ""):
        bound["reasoning"] = ("语义核验凭据未绑定本条证据：evidence_id=%r ≠ %r"
                              % (explicit.get("evidence_id"), evidence_id))
        return bound, "SEMANTIC_VERIFICATION_UNBOUND"
    expected_fp = proposition_fingerprint(proposition)
    if explicit.get("proposition_fingerprint") != expected_fp:
        bound["reasoning"] = ("语义核验凭据未绑定当前命题（指纹 %r ≠ %r）"
                              % (explicit.get("proposition_fingerprint"), expected_fp))
        return bound, "SEMANTIC_VERIFICATION_PROPOSITION_MISMATCH"
    for field in ("verifier", "verification_ref"):
        if not str(explicit.get(field) or "").strip():
            bound["reasoning"] = "语义核验凭据缺少 %s，无法追溯是谁在何时依据什么判定" % field
            return bound, "SEMANTIC_VERIFICATION_UNBOUND"
    if role not in EMPIRICAL_SEMANTIC_ROLES or not is_emp:
        bound["reasoning"] = ("语义角色 %r 不是当前研究的实证发现" % role)
        return bound, "SEMANTIC_ROLE_NOT_RESULT"

    # 命题版本过期检查：凭据声明版本与当前记录版本不一致即失效。
    claimed_ver = explicit.get("idea_version")
    current_ver = record.get("idea_version")
    if claimed_ver is not None and current_ver is not None and claimed_ver != current_ver:
        bound["reasoning"] = ("语义核验凭据针对 idea_version=%r，当前为 %r，须重新核验"
                              % (claimed_ver, current_ver))
        return bound, "SEMANTIC_VERIFICATION_STALE"

    bound["is_empirical_result"] = True
    bound["verified_at"] = explicit.get("verified_at")
    return bound, None


def _exclusion_semantic_role(quote: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """排除规则：命中即判为"非实证结果"，并给出具体语义角色与问题码。"""
    for code, role, epistemic, reasoning, patterns in _SEMANTIC_EXCLUSION_RULES:
        for pat in patterns:
            if re.search(pat, quote, re.IGNORECASE):
                return {
                    "status": "UNRESOLVED",
                    "semantic_role": role,
                    "epistemic_status": epistemic,
                    "is_empirical_result": False,
                    "reasoning": reasoning,
                }, code
    return None


#: (问题码, 语义角色, 认识论状态, 说明, 正则) 的排除规则表。
#: **只用于排除/告警**：命中即不得升级；未命中不代表可以升级（见 verify_semantic_support）。
_SEMANTIC_EXCLUSION_RULES = (
    (
        "RESEARCH_QUESTION_NOT_RESULT", "RESEARCH_QUESTION", "QUESTION_OR_HYPOTHESIS",
        "引句仅表述研究测试目的、检验意图或科学设问，非已实证结果",
        (
            r"\b(?:we\s+tested\s+(?:whether|if)|tested\s+(?:whether|if)|investigated\s+(?:whether|if)|investigate\s+(?:whether|if))\b",
            r"\b(?:examine[ds]?\s+(?:whether|if)|explor(?:ed|ing|es)?\s+(?:whether|if)|assess(?:ed|ing)?\s+(?:whether|if))\b",
            r"\b(?:to\s+(?:test|determine|investigate|assess|explore|examine)\s+(?:whether|if))\b",
            r"\b(?:aim(?:ed)?\s+to\s+(?:test|determine|investigate|assess)\s+(?:whether|if))\b",
            r"\b(?:whether\s+.*?\s+(?:remains|is\s+unclear|was\s+tested|was\s+examined|is\s+an\s+open\s+question))\b",
            r"\b(?:our\s+(?:central|main|research|key)\s+question\s+is)\b",
            r"\b(?:the\s+question\s+(?:is|was|remains)|open\s+question)\b",
            r"(?:是否已被|是否具有|是否存在|是否影响|是否降低|是否增加|是否显著)",
            r"(?:旨在(?:探究|研究|探讨|分析|确定|查明).*?是否|为(?:探究|验证|研究|探讨|检验).*?是否)",
            r"(?:检验.*?是否|测试.*?是否|探讨.*?是否|分析.*?是否)",
        ),
    ),
    (
        "HYPOTHESIS_NOT_RESULT", "HYPOTHESIS", "INTERPRETATION_OR_SPECULATION",
        "引句属于推测、假说、模拟假设或机制阐释，未达到实证结果确认标准",
        (
            r"\b(?:we\s+hypothesize|we\s+speculate|it\s+is\s+hypothesized|hypothesized\s+that)\b",
            r"\b(?:we\s+(?:assume|assumed)|assuming\s+that|for\s+this\s+simulation\s+we\s+assume)\b",
            r"\b(?:may\s+(?:suggest|indicate|reflect|be\s+due)|might\s+(?:suggest|indicate)|could\s+(?:indicate|explain))\b",
            r"\b(?:presumably|arguably|plausibly|future\s+work\s+is\s+needed)\b",
            r"(?:推测|推断|猜测|或许|假说|假设|假定|模拟设定|推测可能|提示潜在|尚待进一步证实|有待进一步)",
        ),
    ),
    (
        "REFERENCED_WORK_NOT_RESULT", "REFERENCED_WORK", "EXTERNAL_CITATION",
        "引句为前人或外部研究引述，非当前论文的第一手实证发现",
        (
            r"\b(?:et\s+al\.?|previously\s+reported|prior\s+(?:studies|research|work)|previous\s+(?:studies|work|findings))\b",
            r"\b(?:has\s+discussed|have\s+shown|earlier\s+work)\b",
            r"\(\s*[A-Z][a-z]+(?:\s+et\s+al\.)?,\s*\d{4}\s*\)",
            r"(?:转引|引自|参见|见文献|前人研究|以往研究|已有研究表明|文献报告)",
        ),
    ),
    (
        "CONDITIONAL_NOT_RESULT", "CONDITIONAL_STATEMENT", "HYPOTHETICAL_OR_CONDITIONAL",
        "引句为假设或未满足事实前提的条件性陈述，非实测确证事实",
        (
            r"\b(?:if\s+.*?\s+would\s+|under\s+hypothetical\s+conditions)\b",
            r"(?:如果.*?将|假定.*?则|在假设条件下)",
        ),
    ),
    (
        "REFUTED_CLAIM", "REFUTED_CLAIM", "CONTRADICTION_OR_REFUTATION",
        "引句明确否定、推翻或未检出该主张的证据",
        (
            r"\b(?:failed\s+to\s+(?:find|detect|support|confirm)|found\s+no\s+evidence|contrary\s+to\s+(?:our\s+)?expectations)\b",
            r"\b(?:refut(?:ed|es)|disprov(?:ed|es)|no\s+significant\s+(?:effect|difference|correlation))\b",
            r"(?:未发现.*?证据|未能支持|否定了|与预期相反|并不支持|未达显著水平)",
        ),
    ),
)


def to_evidence_link(record: Dict[str, Any], proposition: str,
                     relation: str = "CONTEXT",
                     variants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """把一条上游证据记录规范化为 `evidence_links` 条目。

    **硬规则**：
      - 只有 `relation == "SUPPORT"` 且引句在命题层面得到支持时，才可 `VERIFIED`；
      - `CONTEXT` / `BOUNDARY` / `CHALLENGE` 一律 `UNRESOLVED`（它们是背景、限定或削弱，
        不是支持）；
      - 缺 `artifact_ref`、`verbatim_quote` 或 `location` → `UNRESOLVED`；
      - 必须带 `checked_scope`，否则视为无法区分"没找到"与"没查"；
      - 必须经结构化语义核验（非研究问题/假说/引文/条件/反驳）；
      - **跨语言不得自动升级**：见 `align_against_proposition` 的判定链——
        仅命中一条已确认变体、或只命中未确认变体，一律不升级。

    `variants` 为可选的命题变体列表（不同语言的表述），`alignment` 只认其中
    `approval.status == CONFIRMED` 且 `confirmed_by == "user"` 的条目。
    """
    if relation not in ALLOWED_RELATIONS:
        raise ValueError("relation 非法：%r" % relation)

    quote = record.get("verbatim_quote") or ""
    location = record.get("location")
    evidence_id = record.get("evidence_id") or record.get("id")
    artifact_ref = record.get("artifact_ref") or record.get("source_file") or record.get("document_ref") or ""
    problems: List[str] = []

    if not evidence_id:
        problems.append("MISSING_EVIDENCE_ID")
    if not quote.strip():
        problems.append("MISSING_VERBATIM_QUOTE")

    # R01: 产物定位核验
    if not str(artifact_ref).strip():
        problems.append("MISSING_ARTIFACT_REF")

    # F01: 定位必须有实质锚点。{"page": null} 不能算"有定位"。
    loc_ok, loc_problem = location_anchor(record)
    if not loc_ok:
        problems.append(loc_problem)

    # F01: 记录入口必须强制检查范围与上游审计状态，而不是只写在文档里。
    if not str(record.get("checked_scope") or "").strip():
        problems.append("MISSING_CHECKED_SCOPE")
    failed_audit = upstream_audit_failed(record)
    if failed_audit:
        problems.append("UPSTREAM_AUDIT_%s" % failed_audit.split("=", 1)[0].upper())

    # R01: 结构化语义核验与事实判定
    sem_verdict, sem_problem = verify_semantic_support(quote, proposition, record)
    if sem_problem:
        problems.append(sem_problem)

    # 引句评估与完整性检查相互独立：**所有**问题都要如实列出，
    # 不能因为缺定位就掩盖"引句本身不支持命题"这一条。
    verdict = {"supported": False, "how": "NOT_EVALUATED", "ratio": 0.0,
               "variant_ref": None, "variant_status": "NOT_APPLICABLE", "reason": ""}
    if relation == "SUPPORT" and quote.strip():
        verdict = align_against_proposition(quote, proposition, variants)
        if not verdict["supported"]:
            problems.append("QUOTE_DOES_NOT_SUPPORT_PROPOSITION")
        elif verdict["how"] == "FRAGMENT":
            problems.append("INSUFFICIENT_PROPOSITION_COVERAGE")
        elif verdict["how"] == "OVERLAP" and verdict["ratio"] < SUBSTANTIVE_COVERAGE_THRESHOLD:
            problems.append("INSUFFICIENT_PROPOSITION_COVERAGE")
        # 词面命中不等于语义支持：否定句包含命题字面但方向相反。
        negation = detect_negation_mismatch(quote, proposition)
        if negation is not None:
            problems.append("NEGATION_MISMATCH")

    supported, how = verdict["supported"], verdict["how"]

    # 跨语言是「机制上无法判定」，与「判定为不支持」必须可区分（不改变 alignment）。
    lang_mismatch = (bool(quote.strip())
                     and verdict["variant_status"] != "ALIGNED"
                     and how == "KEYWORD_ONLY"
                     and detect_language_mismatch(quote, proposition))
    if lang_mismatch:
        how = "LANGUAGE_MISMATCH"
        if "LANGUAGE_MISMATCH" not in problems:
            problems.append("LANGUAGE_MISMATCH")

    # R01: VERIFIED 必须同时满足命题字面支持、实证语义核验通过，且无未决问题
    is_sem_verified = (sem_verdict.get("status") == "VERIFIED" and sem_verdict.get("is_empirical_result") is True)
    alignment = "VERIFIED" if (relation == "SUPPORT" and supported and is_sem_verified and not problems) else "UNRESOLVED"

    return {
        "artifact_ref": artifact_ref,
        "evidence_id": evidence_id or "",
        "relation": relation,
        "alignment": alignment,
        "reason": _reason(relation, alignment, how, problems, verdict, sem_verdict),
        "checked_scope": record.get("checked_scope") or "",
        "text_match": is_text_match(how),
        "quote_match": how,
        "proposition_match_ratio": round(verdict.get("ratio") or 0.0, 4),
        "variant_ref": verdict.get("variant_ref"),
        "variant_status": verdict["variant_status"],
        "language_mismatch": lang_mismatch,
        "semantic_verification": sem_verdict,
        "problems": problems,
    }


def _reason(relation: str, alignment: str, how: str, problems: List[str],
            verdict: Optional[Dict[str, Any]] = None,
            sem_verdict: Optional[Dict[str, Any]] = None) -> str:
    if alignment == "VERIFIED":
        if how == "VARIANT_AGREEMENT":
            return ("命题层面获得支持（引句匹配：%s；已确认变体 %s 且互相印证）"
                    % (how, (verdict or {}).get("variant_ref") or "—"))
        return "命题层面直接支持（引句匹配：%s）" % how
    if relation in ("CONTEXT", "BOUNDARY", "CHALLENGE"):
        return "relation=%s 属背景/限定/削弱，按规则不得升级为支持" % relation
    status = (verdict or {}).get("variant_status")
    if status == "PENDING_CONFIRMATION":
        return ("跨语言待确认：%s（当前覆盖率 %.3f；在用户确认第二条独立译法前不得升级）"
                % ((verdict or {}).get("reason") or "", (verdict or {}).get("ratio") or 0.0))
    if "LANGUAGE_MISMATCH" in problems:
        return ("引句与命题分属不同书写系统，且无可用的已确认目标语言变体："
                "覆盖率比对在跨语言下恒为 0，属「机制上无法判定」而非「判定为不支持」")
    if "QUOTE_DOES_NOT_SUPPORT_PROPOSITION" in problems:
        return "引句仅命中关键词或落入其他上下文，未在命题层面支持该命题"
    # 语义核验未完成是**兜底**原因：具体的方向/跨语言/覆盖问题优先呈现，
    # 否则调用方会以为"只差一道手续"，看不到真正没过的判定。
    if sem_verdict and sem_verdict.get("status") != "VERIFIED":
        return "语义核验未通过：%s" % sem_verdict.get("reasoning", "")
    return "缺少判定所需的引句、定位或标识：%s" % ",".join(problems)


def candidates_to_records(discovery_result: Dict[str, Any],
                          max_records: Optional[int] = None) -> List[Dict[str, Any]]:
    """把 Discovery 的 headless 产物转成**候选**证据记录。

    **关键限制（不得省略）**：题录与摘要**不是**证据。这里产出的记录一律
    不带 `verbatim_quote`（摘要 ≠ 原文引句），因此经 `to_evidence_link` 处理时
    必然落在 `UNRESOLVED`——这正是设计稿 §11.4 想要的行为：候选命中 ≠ 证据。
    若要升级为支持，必须先把全文交给 `literature-evidence-extraction` 抽取原文引句。
    """
    cands = (discovery_result.get("candidates")
             or discovery_result.get("records")
             or discovery_result.get("literature_records")
             or [])
    if max_records is not None:
        cands = cands[:max_records]
    out: List[Dict[str, Any]] = []
    for c in cands:
        out.append({
            "evidence_id": "CAND-%s" % (c.get("doi") or c.get("openalex_id") or c.get("id") or "?"),
            "artifact_ref": "discovery_result.json",
            "title": c.get("title"),
            "doi": c.get("doi"),
            "abstract": c.get("abstract"),
            # 摘要不作为原文引句 —— 留空是有意的
            "verbatim_quote": "",
            "location": None,
            "checked_scope": "仅题录与摘要（未获取全文）",
            "candidate_only": True,
        })
    return out


def ingest_returns(records: List[Dict[str, Any]], proposition: str,
                   relations: Optional[Dict[str, str]] = None,
                   artifact_ref: Optional[str] = None,
                   variants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """批量回流：规范化为 evidence_links，并给出可读的影响说明。

    `variants` 传给 `to_evidence_link`：只有 `approval.status == CONFIRMED` 且
    `confirmed_by == "user"` 的变体才参与对齐判定；跨语言且无第二条互相印证的
    已确认变体时**不升级**，并在 `pending_variants` 里列出待用户裁决的条目。
    """
    relations = relations or {}
    links: List[Dict[str, Any]] = []
    for rec in records:
        eid = rec.get("evidence_id") or rec.get("id") or ""
        rel = relations.get(eid, rec.get("relation", "CONTEXT"))
        if artifact_ref and not rec.get("artifact_ref") and not rec.get("source_file"):
            rec = dict(rec, artifact_ref=artifact_ref)
        link = to_evidence_link(rec, proposition, relation=rel, variants=variants)
        links.append(link)

    verified = [l for l in links if l["alignment"] == "VERIFIED"]
    unresolved = [l for l in links if l["alignment"] == "UNRESOLVED"]
    pending = [l["evidence_id"] for l in links
               if l["variant_status"] == "PENDING_CONFIRMATION"]
    impact = {
        "supports": [l["evidence_id"] for l in verified if l["relation"] == "SUPPORT"],
        "challenges": [l["evidence_id"] for l in links if l["relation"] == "CHALLENGE"],
        "boundaries": [l["evidence_id"] for l in links if l["relation"] == "BOUNDARY"],
        "context_only": [l["evidence_id"] for l in links if l["relation"] == "CONTEXT"],
        "unresolved": [l["evidence_id"] for l in unresolved],
        "pending_variants": pending,
    }
    if not links:
        note = "回流为空：检索失败不等于不存在研究；缺口应保留为未决。"
    elif not verified:
        note = "本批未产生可升级为支持的证据；命题状态不因本批而升级。"
        if pending:
            note += ("其中 %d 条因跨语言译法待确认而未升级（%s）："
                     "需用户确认第二条独立译法后才可判定。" % (len(pending), "、".join(pending)))
    else:
        note = "本批有 %d 条在命题层面获支持；仍不表示命题普遍正确。" % len(verified)
    return {"evidence_links": links, "impact": impact, "note": note,
            "counts": {"total": len(links), "verified": len(verified),
                        "unresolved": len(unresolved),
                        "pending_variant_confirmation": len(pending)}}
