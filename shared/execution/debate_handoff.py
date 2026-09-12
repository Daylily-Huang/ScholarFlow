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


def prepare_dispatch(gap: Dict[str, Any]) -> Dict[str, Any]:
    """派发前的门禁：未确认不得执行；范围变更须先失效旧确认。

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

    if recorded_fp and recorded_fp != current_fp:
        return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False}

    if gap.get("scope_changed"):
        return {"dispatchable": False, "reason": "SCOPE_CHANGED_APPROVAL_STALE",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": True, "idempotent_replay": False}

    if gap.get("execution_status") == "COMPLETE":
        return {"dispatchable": False, "reason": "ALREADY_COMPLETE_IDEMPOTENT",
                "payload": None, "fingerprint": current_fp,
                "must_reconfirm": False, "idempotent_replay": True}

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
    if p in q or q in p:
        return True, "EXACT", 1.0
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


def to_evidence_link(record: Dict[str, Any], proposition: str,
                     relation: str = "CONTEXT",
                     variants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """把一条上游证据记录规范化为 `evidence_links` 条目。

    **硬规则**：
      - 只有 `relation == "SUPPORT"` 且引句在命题层面得到支持时，才可 `VERIFIED`；
      - `CONTEXT` / `BOUNDARY` / `CHALLENGE` 一律 `UNRESOLVED`（它们是背景、限定或削弱，
        不是支持）；
      - 缺 `verbatim_quote` 或 `location` → `UNRESOLVED`；
      - 必须带 `checked_scope`，否则视为无法区分"没找到"与"没查"；
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
    problems: List[str] = []

    if not evidence_id:
        problems.append("MISSING_EVIDENCE_ID")
    if not quote.strip():
        problems.append("MISSING_VERBATIM_QUOTE")
    if not location:
        problems.append("MISSING_LOCATION")

    # 引句评估与完整性检查相互独立：**所有**问题都要如实列出，
    # 不能因为缺定位就掩盖"引句本身不支持命题"这一条。
    verdict = {"supported": False, "how": "NOT_EVALUATED", "ratio": 0.0,
               "variant_ref": None, "variant_status": "NOT_APPLICABLE", "reason": ""}
    if relation == "SUPPORT" and quote.strip():
        verdict = align_against_proposition(quote, proposition, variants)
        if not verdict["supported"]:
            problems.append("QUOTE_DOES_NOT_SUPPORT_PROPOSITION")

    supported, how = verdict["supported"], verdict["how"]

    # 跨语言是「机制上无法判定」，与「判定为不支持」必须可区分（不改变 alignment）。
    # 只有当"确实没有任何同书写系统的已确认变体被命中"（即判定停在 KEYWORD_ONLY）
    # 时，跨语言才是不可判定的原因；若已命中待确认变体，`how` 已自带更具体的原因，
    # 不能被笼统的 LANGUAGE_MISMATCH 覆盖掉（那会丢掉"差用户确认一步"这个信息）。
    lang_mismatch = (bool(quote.strip())
                     and verdict["variant_status"] != "ALIGNED"
                     and how == "KEYWORD_ONLY"
                     and detect_language_mismatch(quote, proposition))
    if lang_mismatch:
        how = "LANGUAGE_MISMATCH"
        if "LANGUAGE_MISMATCH" not in problems:
            problems.append("LANGUAGE_MISMATCH")

    alignment = "VERIFIED" if (relation == "SUPPORT" and supported and not problems) else "UNRESOLVED"

    return {
        "artifact_ref": record.get("artifact_ref") or record.get("source_file") or "",
        "evidence_id": evidence_id or "",
        "relation": relation,
        "alignment": alignment,
        "reason": _reason(relation, alignment, how, problems, verdict),
        "checked_scope": record.get("checked_scope") or "",
        "quote_match": how,
        "proposition_match_ratio": round(verdict.get("ratio") or 0.0, 4),
        "variant_ref": verdict.get("variant_ref"),
        "variant_status": verdict["variant_status"],
        "language_mismatch": lang_mismatch,
        "problems": problems,
    }


def _reason(relation: str, alignment: str, how: str, problems: List[str],
            verdict: Optional[Dict[str, Any]] = None) -> str:
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
        link = to_evidence_link(rec, proposition, relation=rel, variants=variants)
        if artifact_ref and not link["artifact_ref"]:
            link["artifact_ref"] = artifact_ref
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
