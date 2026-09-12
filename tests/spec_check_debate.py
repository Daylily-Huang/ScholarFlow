# -*- coding: utf-8 -*-
"""RFC-016 规格检查器（spec check）。

用途：把一次讨论会话的**结构化记录**对照设计稿声明的规则逐条检查，返回违规列表。
它与 `tests/test_research_debate_example_contract.py` 分工不同：
  - 后者检查"设计稿的规则 ↔ 设计稿的示例"是否自洽（面向文档）；
  - 本模块检查"会话记录本身"是否合规（面向未来的实现与验收 fixture）。

本模块**不是** JSON Schema 验证的替代品，也**不**裁决科学真伪。它只检查文档明确写出的
结构性规则，例如：每轮是否只有一个焦点问题、`role_id` 与 `question_type` 是否按表对应、
查证是否先确认后执行、评估是否由确定性程序判分歧、成熟度门是否被遵守。

零第三方依赖，纯标准库。
"""

from typing import Any, Dict, List

# ---- 文档声明的枚举（见设计稿 5.1.3 / 6.2 / 7.3 / 8.1 / 10 / 11.3）----
ROLE_QUESTION_TYPE = {
    "concept_clarifier": "CLARIFICATION",
    "premise_evidence_examiner": "PREMISE_EVIDENCE",
    "implication_validator": "IMPLICATION",
    "alternative_explorer": "COMPARISON",
    "reflection_facilitator": "REFLECTION",
    "moderator": "CONFIGURATION",
}
MODES = {"explore", "examine"}
STATES = {
    "CONTEXT_RESOLUTION", "WAITING_DEPTH", "DISCUSSING", "WAITING_USER",
    "INDEPENDENT_REVIEW", "WAITING_GAP_CONFIRMATION", "WAITING_EVIDENCE",
    "CHECKPOINT", "PAUSED", "CLOSED",
}
MATURATION = {"RAW", "DEVELOPING", "TESTABLE"}
EPISTEMIC = {"INTUITION", "HYPOTHESIS", "EVIDENCE_SUPPORTED", "EVIDENCE_CHALLENGED", "UNRESOLVED"}
DISPOSITION = {"ACTIVE", "RETAINED", "REVISED", "REJECTED", "DEFERRED"}
ASSUMPTION_TYPES = {"EMPIRICAL", "DEFINITIONAL", "METHODOLOGICAL", "VALUE"}
ASSUMPTION_STATUS = {"UNVERIFIED", "VERIFIED", "CONTRADICTED"}
RELATION = {"SUPPORT", "CHALLENGE", "BOUNDARY", "CONTEXT"}
ALIGNMENT = {"VERIFIED", "UNRESOLVED"}
APPROVAL_STATUS = {"PENDING", "CONFIRMED", "REJECTED", "INVALIDATED"}
STOP_REASONS = {
    "USER_CLOSED", "CHECKPOINT_REACHED", "NO_PROGRESS",
    "BUDGET_EXHAUSTED", "PAUSED", "USER_SWITCHED_MODE",
}
DECISION_TRIGGERS = {
    "ROLE_QUESTION", "EXTERNAL_OPINION", "INDEPENDENT_REVIEW", "EVIDENCE", "CHECKPOINT", "USER_INITIATIVE",
}
REVIEW_STATUS = {"COMPLETE", "PARTIAL", "FAILED", "UNAVAILABLE"}
DISAGREEMENT = {"LOW_DIVERGENCE", "HIGH_DIVERGENCE", "NOT_APPLICABLE"}
SUBSTANTIVE_KINDS = {"SUBSTANTIVE", "EXTERNAL_INPUT", "REVIEW_SUBMISSION"}
# 第 8.2 节：RAW 阶段的允许动作含"澄清、给出候选表述、举对照例、增加一个可区分差异"，
# 也含前提审查与替代解释（两者都是生成性动作）。因此配额只约束 **P3**——
# 即首次要求命题给出可观察预测/可证伪形式的那一步：此时命题必须已经发展过。
DEVELOPMENT_QUOTA_TRIGGERS = {"P3"}
# 计入发展配额的信号（§6.1 中属"发展"性质的信号）：
#   命题成形（INTUITION_FORMULATED）、问题收窄（QUESTION_SHARPENED）、
#   隐含前提显式化（PREMISE_SURFACED）、新增可区分差异（DISCRIMINATION_ADDED）。
# 仅记录"补了一条替代解释"（ALTERNATIVE_ADDED）不计入：它不改变原命题本身的可检验性。
DEVELOPMENT_SIGNALS = {
    "INTUITION_FORMULATED", "QUESTION_SHARPENED",
    "PREMISE_SURFACED", "DISCRIMINATION_ADDED",
}
# 一轮内出现的角色名上限（§5.5：合并标签算一项）
ROLE_ZH = {
    "concept_clarifier": "概念澄清者", "premise_evidence_examiner": "前提与证据审查者",
    "implication_validator": "推论与验证者", "alternative_explorer": "替代解释探索者",
    "reflection_facilitator": "观点修订引导者", "moderator": "主持人",
}
# 反例类型标签（§7.3）：分歧判定只比较可枚举字段，不比前提文本重合
COUNTEREXAMPLE_TYPES = {
    "MEASUREMENT_ARTIFACT", "SAMPLING_ARTIFACT", "ALTERNATIVE_MECHANISM",
    "CONFOUNDING", "SCOPE_LIMIT", "NONE_FOUND",
}
REQUIRED_SIGNALS = {
    "INTUITION_FORMULATED", "QUESTION_SHARPENED", "PREMISE_SURFACED", "PREMISE_VERIFIED",
    "PREMISE_CONTRADICTED", "DISCRIMINATION_ADDED", "ALTERNATIVE_ADDED",
    "DISPOSITION_DECIDED", "DECISION_RECORDED", "GAP_CONFIRMED", "EVIDENCE_IMPORTED",
}
BANNED_IN_QUESTION = ("以及", "另外", "顺便")


class SpecViolation(object):
    __slots__ = ("rule", "where", "message")

    def __init__(self, rule: str, where: str, message: str):
        self.rule = rule
        self.where = where
        self.message = message

    def __str__(self):
        return "[%s] %s: %s" % (self.rule, self.where, self.message)

    def __repr__(self):
        return "SpecViolation(%r, %r, %r)" % (self.rule, self.where, self.message)


def _v(out: List[SpecViolation], rule: str, where: str, message: str):
    out.append(SpecViolation(rule, where, message))


# ----------------------------------------------------------------------------
# 1. 会话级
# ----------------------------------------------------------------------------
def check_session(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    for field in ("schema_version", "session_id", "run_id", "mode", "state",
                  "original_prompt", "current_question", "execution"):
        if field not in session:
            _v(out, "S-FIELD", "session", "缺少必填字段 %s" % field)
    if session.get("mode") not in MODES:
        _v(out, "S-ENUM", "session.mode", "mode 非法：%r" % session.get("mode"))
    if session.get("state") not in STATES:
        _v(out, "S-ENUM", "session.state", "state 非法：%r" % session.get("state"))

    ex = session.get("execution", {})
    budget, usage = ex.get("budget", {}), ex.get("usage", {})
    if ex.get("selection_status") not in ("pending", "confirmed"):
        _v(out, "S-EXEC", "session.execution", "selection_status 非法")
    # BU1：硬约束必须是可测的正整数；token 只能作为观测字段
    for key in ("max_rounds", "max_review_batches", "max_subtasks_per_batch",
                "max_active_seconds", "max_events"):
        if not isinstance(budget.get(key), int) or budget.get(key, 0) < 1:
            _v(out, "BU1", "session.execution.budget.%s" % key, "硬约束缺失或非正整数")
    if "max_tokens" in budget:
        _v(out, "BU1", "session.execution.budget", "token 不得作为硬约束（只能观测）")
    if usage.get("tokens_metering") not in ("MEASURED", "ESTIMATED", "UNAVAILABLE", None):
        _v(out, "BU2", "session.execution.usage", "tokens_metering 取值非法")
    if usage.get("tokens_observed") is None and usage.get("tokens_metering") not in (None, "UNAVAILABLE"):
        _v(out, "BU2", "session.execution.usage", "计量非 UNAVAILABLE 时 tokens_observed 不应为 null")

    # 停止原因互斥且必填（会话已结束时）
    if session.get("state") in ("CHECKPOINT", "CLOSED", "PAUSED"):
        sr = session.get("stop_reason")
        if sr is None:
            _v(out, "ST1", "session.stop_reason", "会话进入 %s 但未记录 stop_reason" % session["state"])
        elif sr not in STOP_REASONS:
            _v(out, "ST1", "session.stop_reason", "stop_reason 非法：%r" % sr)
    return out


# ----------------------------------------------------------------------------
# 2. 想法版本与维度独立
# ----------------------------------------------------------------------------
def check_ideas(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    for idea in session.get("ideas", []):
        iid = idea.get("idea_id", "<no-id>")
        if idea.get("maturation") not in MATURATION:
            _v(out, "ID-MAT", iid, "maturation 非法：%r" % idea.get("maturation"))
        versions = idea.get("versions", [])
        if not versions:
            _v(out, "ID-VER", iid, "没有任何版本")
            continue
        seen = set()
        for ver in versions:
            w = "%s@v%s" % (iid, ver.get("version"))
            for f in ("version", "proposition", "origin", "epistemic_status", "disposition", "revision_reason"):
                if f not in ver:
                    _v(out, "ID-FIELD", w, "缺少字段 %s" % f)
            if ver.get("version") in seen:
                _v(out, "ID-VER", w, "版本号重复")
            seen.add(ver.get("version"))
            if ver.get("epistemic_status") not in EPISTEMIC:
                _v(out, "ID-ENUM", w, "epistemic_status 非法：%r" % ver.get("epistemic_status"))
            if ver.get("disposition") not in DISPOSITION:
                _v(out, "ID-ENUM", w, "disposition 非法：%r" % ver.get("disposition"))
            pv = ver.get("parent_version")
            if ver.get("version") != 1 and pv not in seen - {ver.get("version")}:
                _v(out, "ID-VER", w, "parent_version 未指向已存在的更早版本：%r" % pv)
            for a in ver.get("assumptions", []):
                if a.get("type") not in ASSUMPTION_TYPES:
                    _v(out, "ID-ASM", w, "assumption.type 非法：%r" % a.get("type"))
                if a.get("verification_status") not in ASSUMPTION_STATUS:
                    _v(out, "ID-ASM", w, "assumption.verification_status 非法：%r" % a.get("verification_status"))
                if a.get("type") == "VALUE" and not a.get("decided_by"):
                    _v(out, "ID-VALUE", w, "价值取舍类前提必须记录 decided_by（用户决定，不得由 AI 定）")

        # 处置与证据状态相互独立：搁置不得写成证据否定
        for ver in versions:
            if ver.get("disposition") == "DEFERRED" and ver.get("epistemic_status") == "EVIDENCE_CHALLENGED":
                _v(out, "ID-INDEP", "%s@v%s" % (iid, ver.get("version")),
                   "DEFERRED（不可行/搁置）不得自动写成 EVIDENCE_CHALLENGED（证据否定）")

        for link in idea.get("evidence_links", []):
            w = "%s/evidence_links" % iid
            if link.get("relation") not in RELATION:
                _v(out, "EV-ENUM", w, "relation 非法：%r" % link.get("relation"))
            if link.get("alignment") not in ALIGNMENT:
                _v(out, "EV-ENUM", w, "alignment 非法：%r" % link.get("alignment"))
            # EV1：CONTEXT/BOUNDARY/CHALLENGE 不得被当作支持
            if link.get("relation") in ("CONTEXT", "BOUNDARY", "CHALLENGE") and link.get("alignment") == "VERIFIED":
                _v(out, "EV1", w, "relation=%s 不得记为 alignment=VERIFIED（只有直接支持命题才可）"
                   % link.get("relation"))
            if not link.get("checked_scope"):
                _v(out, "EV2", w, "缺少 checked_scope，无法区分'没找到'与'没查'")

        # 成熟度：只升不降；历史必须从 RAW 起、逐级连续、终点等于当前 maturation
        hist = idea.get("maturity_history", [])
        order = {"RAW": 0, "DEVELOPING": 1, "TESTABLE": 2}
        if hist:
            if hist[0].get("from") != "RAW":
                _v(out, "ID-MAT", iid, "成熟度历史必须从 RAW 开始，实际起点 %r" % hist[0].get("from"))
            for h in hist:
                cur, nxt = h.get("from"), h.get("to")
                if order.get(nxt, -1) - order.get(cur, -2) != 1:
                    _v(out, "ID-MAT", iid, "成熟度不得跳级：%r -> %r" % (cur, nxt))
            for a, b in zip(hist, hist[1:]):
                if b.get("from") != a.get("to"):
                    _v(out, "ID-MAT", iid, "成熟度历史不连续：%r -> %r 后接 %r -> %r"
                       % (a.get("from"), a.get("to"), b.get("from"), b.get("to")))
                if order.get(b.get("to"), -1) < order.get(a.get("to"), -1) and not b.get("reason"):
                    _v(out, "ID-MAT", iid, "成熟度回落未记录理由")
            if idea.get("maturation") != hist[-1].get("to"):
                _v(out, "ID-MAT", iid, "maturation 与 maturity_history 终点不一致")
        elif idea.get("maturation") != "RAW":
            _v(out, "ID-MAT", iid, "无成熟度历史却声明 maturation=%r" % idea.get("maturation"))
    return out


# ----------------------------------------------------------------------------
# 3. 逐轮协议
# ----------------------------------------------------------------------------
def check_rounds(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    idea_versions = {}
    for idea in session.get("ideas", []):
        idea_versions[idea["idea_id"]] = {v["version"] for v in idea.get("versions", [])}

    rounds = session.get("rounds", [])
    if not rounds:
        _v(out, "RD-EMPTY", "rounds", "没有任何轮次记录")
        return out
    seq = [r.get("round") for r in rounds]
    if seq != sorted(seq) or len(set(seq)) != len(seq):
        _v(out, "RD-SEQ", "rounds", "轮次序号必须唯一且递增：%s" % seq)

    for r in rounds:
        where = "R%s" % r.get("round")
        q = r.get("question", "")
        # RD1：每轮恰好一个焦点问题（单一问号 + 无并列引导词）
        if q.count("？") != 1:
            _v(out, "RD1", where, "焦点问题必须恰好一个问号，实际 %d 个" % q.count("？"))
        for b in BANNED_IN_QUESTION:
            if b in q:
                _v(out, "RD1", where, "焦点问题含并列引导词 %r" % b)
        if not r.get("user_answer"):
            _v(out, "RD2", where, "缺少用户回答（不得由 AI 代答或跳过）")
        if not r.get("intent"):
            _v(out, "RD3", where, "缺少 intent（本轮要消除的障碍）")

        # RD4：role_id 与 question_type 必须按 5.1.3 表对应
        role, qtype = r.get("role"), r.get("question_type")
        if role not in ROLE_QUESTION_TYPE:
            _v(out, "RD4", where, "未知 role_id：%r" % role)
        elif ROLE_QUESTION_TYPE[role] != qtype:
            _v(out, "RD4", where, "role_id=%s 必须配 question_type=%s，实际 %s"
               % (role, ROLE_QUESTION_TYPE[role], qtype))

        # RD5：命题身份保持——引用某 idea@version，且版本存在
        if r.get("idea_id"):
            if r.get("target_version") not in idea_versions.get(r["idea_id"], set()):
                _v(out, "RD5", where, "target_version=%r 不是 %s 的已存在版本"
                   % (r.get("target_version"), r.get("idea_id")))
        # RD6：非配置轮必须绑定想法版本
        if r.get("kind") in SUBSTANTIVE_KINDS and not r.get("idea_id"):
            _v(out, "RD6", where, "实质轮未绑定 idea_id")

        # RD7：CONFIGURATION 只属主持人
        if qtype == "CONFIGURATION" and role != "moderator":
            _v(out, "RD7", where, "CONFIGURATION 问句只能由主持人提出")

        # RD8：评估性提问（P2/P3/P4）不得要求用户提供其不具备的文献或数据
        if r.get("trigger") in {"P2", "P3", "P4"}:
            if r.get("requires_user_held_evidence"):
                _v(out, "RD8", where, "评估性提问要求用户提供其不具备的证据")

        # RD8b：RAW 命题不得被直接裁决成立与否
        if r.get("verdict_on_proposition") in ("SUPPORTED", "CHALLENGED"):
            idea = next((i for i in session.get("ideas", []) if i.get("idea_id") == r.get("idea_id")), None)
            if idea and idea.get("maturation") == "RAW":
                _v(out, "RD8b", where, "对 maturation=RAW 的命题直接作出裁决")

        # RD9：进展信号必须取自声明的信号集
        for s in r.get("signals", []):
            if s not in REQUIRED_SIGNALS:
                _v(out, "RD9", where, "未声明的进展信号：%r" % s)

        # RD10：一轮内出现的角色名不超过两个（合并标签算一项）
        label_text = r.get("labels_text") or r.get("question") or ""
        mentioned = [zh for zh in set(ROLE_ZH.values()) if zh in label_text]
        if len(mentioned) > 2:
            _v(out, "RD10", where, "同一轮出现 %d 个角色名（上限 2）：%s"
               % (len(mentioned), sorted(mentioned)))
    return out


# ----------------------------------------------------------------------------
# 4. 成熟度门
# ----------------------------------------------------------------------------
def check_maturity_gate(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    for idea in session.get("ideas", []):
        iid = idea["idea_id"]
        started_raw = any(h.get("from") == "RAW" for h in idea.get("maturity_history", []))
        if not started_raw:
            continue
        signals = 0
        for r in session.get("rounds", []):
            if r.get("idea_id") != iid:
                continue
            if r.get("trigger") in DEVELOPMENT_QUOTA_TRIGGERS:
                if signals < 2:
                    _v(out, "MT1", "R%s" % r.get("round"),
                       "%s 从 RAW 起步，但进入评估性提问（%s）前只有 %d 个发展信号（需 ≥2）"
                       % (iid, r.get("trigger"), signals))
                break
            for s in r.get("signals", []):
                if s in DEVELOPMENT_SIGNALS:
                    signals += 1
    return out


# ----------------------------------------------------------------------------
# 5. 决定记录（含外部意见不得吞并用户决定）
# ----------------------------------------------------------------------------
def check_decisions(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    idea_versions = {}
    for idea in session.get("ideas", []):
        idea_versions[idea["idea_id"]] = {v["version"] for v in idea.get("versions", [])}
    ext_ids = {e.get("id") for e in session.get("external_inputs", [])}

    for d in session.get("ideas", []):
        pass
    decisions = []
    for idea in session.get("ideas", []):
        decisions.extend(idea.get("decisions", []))
    decisions.extend(session.get("decisions", []))

    for d in decisions:
        where = "decision %s" % d.get("id")
        for f in ("id", "action", "reason", "author", "triggered_by", "user_confirmation"):
            if f not in d:
                _v(out, "DC-FIELD", where, "缺少字段 %s" % f)
        # DC1：外部意见不得成为决定作者
        if d.get("triggered_by") == "EXTERNAL_OPINION" and d.get("author") == "EXTERNAL_OPINION":
            _v(out, "DC1", where, "外部意见不得作为决定的作者；决定须由用户作出")
        if d.get("triggered_by") not in DECISION_TRIGGERS:
            _v(out, "DC2", where, "triggered_by 非法或缺失：%r" % d.get("triggered_by"))
        if d.get("author") == "AI建议" and not d.get("user_confirmation"):
            _v(out, "DC3", where, "AI 建议未获用户确认即成为决定")
    return out


# ----------------------------------------------------------------------------
# 6. 查证：先确认后执行、指纹失效、拒绝不阻塞、幂等
# ----------------------------------------------------------------------------
def check_gaps(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    for g in session.get("gap_requests", []):
        where = "gap %s" % g.get("gap_id")
        for f in ("gap_id", "idea_id", "question", "reason", "decision_impact",
                  "scope", "approval", "execution_status", "blocking"):
            if f not in g:
                _v(out, "GP-FIELD", where, "缺少字段 %s" % f)
        ap = g.get("approval", {})
        status = ap.get("status")
        if status not in APPROVAL_STATUS:
            _v(out, "GP-ENUM", where, "approval.status 非法：%r" % status)
        if not ap.get("scope_fingerprint"):
            _v(out, "GP1", where, "缺少 scope_fingerprint，无法判定授权范围")
        # GP2：未确认不得执行
        if status != "CONFIRMED" and g.get("execution_status") not in ("NOT_STARTED", "REFUSED_BY_USER"):
            _v(out, "GP2", where, "approval=%s 时 execution_status 不得为 %s（先确认后执行）"
               % (status, g.get("execution_status")))
        if status == "CONFIRMED" and not ap.get("confirmed_event_id"):
            _v(out, "GP3", where, "已确认但缺少 confirmed_event_id")
        # GP4：范围改变须失效旧确认
        if g.get("execution_status") == "COMPLETE" and status != "CONFIRMED":
            _v(out, "GP4", where, "已完成的查证必须来自已确认的授权")
        if g.get("scope_changed") and status == "CONFIRMED":
            _v(out, "GP4", where, "范围已变更但旧确认未失效")
        # GP5：拒绝查证不得删除缺口
        if status == "REJECTED" and not g.get("question"):
            _v(out, "GP5", where, "拒绝查证后缺口须保留（含原问题）")
    return out


# ----------------------------------------------------------------------------
# 7. 独立评估：隔离、确定性判分歧、降级不得冒充独立
# ----------------------------------------------------------------------------
def check_reviews(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    gap_ids = {g.get("gap_id") for g in session.get("gap_requests", [])}
    batch_sub = {b.get("batch_id"): b.get("subtasks", []) for b in session.get("review_batches", [])}
    cap = session.get("execution", {}).get("budget", {}).get("max_subtasks_per_batch")

    for r in session.get("review_requests", []):
        where = "review %s" % r.get("request_id")
        # RV1：输入白名单必须显式排除主持人倾向与其他评估者结果
        excluded = " ".join(r.get("excluded", []))
        for must in ("其他评估者", "主持人"):
            if must not in excluded:
                _v(out, "RV1", where, "输入未显式排除 %s 的倾向/结果" % must)
        if not r.get("submitted_separately"):
            _v(out, "RV2", where, "评估结果未分别提交")
        if r.get("cross_talk_rounds", 0) > 1:
            _v(out, "RV3", where, "交叉回应超过 1 轮（当前 %s）" % r.get("cross_talk_rounds"))
        tasks = batch_sub.get(r.get("batch_id"), [])
        lenses = [t.get("lens") for t in tasks]
        if cap is not None and len(tasks) > cap:
            _v(out, "RV4", where, "单批子任务 %d 超过上限 %d" % (len(tasks), cap))
        if len(lenses) != len(set(lenses)):
            _v(out, "RV5", where, "同批使用了重复视角，无法形成最大分歧")
        for t in tasks:
            if t.get("input_version") != r.get("input_version"):
                _v(out, "RV6", where, "任务 %s 的 input_version 与请求不一致" % t.get("task_id"))

    for b in session.get("review_batches", []):
        where = "batch %s" % b.get("batch_id")
        subs = b.get("subtasks", [])
        done = [t for t in subs if t.get("status") == "COMPLETE"]
        ds = b.get("disagreement_signal")
        if ds not in DISAGREEMENT:
            _v(out, "RV7", where, "disagreement_signal 非法：%r" % ds)
        # RV8：分歧必须由确定性程序判定
        if ds in ("LOW_DIVERGENCE", "HIGH_DIVERGENCE") and b.get("computed_by") != "deterministic_program":
            _v(out, "RV8", where, "分歧判定必须来自确定性程序，实际 %r" % b.get("computed_by"))
        # RV9：缺任一评估者时不得推定 LOW
        if len(done) < 2 and ds == "LOW_DIVERGENCE":
            _v(out, "RV9", where, "仅 %d 个评估者完成，不得判为 LOW_DIVERGENCE" % len(done))
        if len(done) < 2 and ds != "NOT_APPLICABLE":
            _v(out, "RV10", where, "评估者不足 2 个时 disagreement_signal 应为 NOT_APPLICABLE")
        # RV11：降级批次不得冒充独立评估，不得满足收敛前提
        if b.get("degraded"):
            if b.get("execution_kind") != "SELF_CHECK":
                _v(out, "RV11", where, "降级批次必须记 execution_kind=SELF_CHECK")
            if ds == "LOW_DIVERGENCE":
                _v(out, "RV11", where, "降级批次不得给出 LOW_DIVERGENCE")
            if b.get("satisfies_convergence_precondition"):
                _v(out, "RV11", where, "降级批次不得满足'收敛前独立评估'前提")
        # RV12：HIGH_DIVERGENCE 必须交回用户，且不得有投票/调和式结论
        if ds == "HIGH_DIVERGENCE":
            if not b.get("resolution"):
                _v(out, "RV12", where, "HIGH_DIVERGENCE 未记录处理方式")
            if b.get("resolution") in ("VOTE", "AVERAGE", "CONSENSUS"):
                _v(out, "RV12", where, "分歧不得以投票/平均/共识方式消解")
            if b.get("resolution") == "ESCALATED_TO_GAP":
                gid = b.get("escalated_gap_id")
                if gid not in gap_ids:
                    _v(out, "RV13", where, "升级到的缺口 %r 不存在（可用缺口：%s）" % (gid, sorted(list(gap_ids))))
        # RV15：分歧判定须基于可枚举字段，不得用前提文本字面重合
        if b.get("computed_by") == "deterministic_program":
            # 只在**实际给出了分歧判定**时要求反例类型标签；
            # NOT_APPLICABLE（评估者不足 2 个）本无分歧可标，不应据此报错。
            if ds in ("LOW_DIVERGENCE", "HIGH_DIVERGENCE") and not b.get("counterexample_types"):
                _v(out, "RV15", where,
                   "分歧判定缺少反例类型标签；不得用承重前提的字面重合代替语义比较")
            for tv in (b.get("counterexample_types") or {}).values():
                if tv not in COUNTEREXAMPLE_TYPES:
                    _v(out, "RV15", where, "未声明的反例类型标签：%r" % tv)
            if ds == "HIGH_DIVERGENCE":
                tv = list((b.get("counterexample_types") or {}).values())
                same_verdict = len({t.get("verdict") for t in done}) == 1 and len(done) >= 2
                if same_verdict and len(tv) == 2 and tv[0] == tv[1] and not b.get("mutual_denial"):
                    _v(out, "RV15", where,
                       "verdict 与反例类型均相同且无相互否定，不应判 HIGH_DIVERGENCE")

        # RV14：verdicts 只应对已完成的评估者存在，且不得多、不得少
        verdicts = b.get("verdicts") or {}
        done_ids = {t.get("task_id") for t in done}
        if set(verdicts) - done_ids:
            _v(out, "RV14", where, "verdicts 含有非 COMPLETE 任务的结果：%s" % sorted(set(verdicts) - done_ids))
        if done_ids - set(verdicts):
            _v(out, "RV14", where, "已完成的评估者缺少 verdict：%s" % sorted(done_ids - set(verdicts)))
    return out


# ----------------------------------------------------------------------------
# 8. 停止规则与未决保留
# ----------------------------------------------------------------------------
def check_stopping(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    sub = [r for r in session.get("rounds", []) if r.get("kind") in SUBSTANTIVE_KINDS]
    sig = {r.get("round"): r.get("signals", []) for r in sub}

    # ST2：S1 —— 连续 2 轮无进展信号必须已处理（进入 CHECKPOINT 或记录停因）
    streak, trigger = 0, None
    for r in sub:
        streak = streak + 1 if not sig.get(r.get("round")) else 0
        if streak >= 2:
            trigger = r.get("round")
            break
    ended = session.get("state") in ("CHECKPOINT", "CLOSED", "PAUSED")
    if trigger is not None and not ended:
        _v(out, "ST2", "session", "第 %s 轮已连续两轮无进展信号，但会话未进入 CHECKPOINT/收尾" % trigger)
    if trigger is not None and ended:
        marked = any(r.get("stop_reason") or r.get("kind") == "CHECKPOINT"
                     for r in session.get("rounds", []) if r.get("round", 0) >= trigger)
        if not marked:
            _v(out, "ST2", "session", "连续两轮无进展后未记录 CHECKPOINT 或 stop_reason")

    # ST3：CHECKPOINT 不得宣告问题解决
    for r in session.get("rounds", []):
        if r.get("kind") == "CHECKPOINT":
            blob = "%s %s" % (r.get("question", ""), r.get("user_answer", ""))
            for bad in ("已解决", "已证实", "结论成立", "问题解决", "已经解决"):
                if bad in blob:
                    _v(out, "ST3", "R%s" % r.get("round"), "CHECKPOINT 不得宣告问题解决：%s" % bad)

    # ST4：未决问题必须保留（缺口被拒、障碍未消除时）
    open_q = session.get("open_questions", [])
    stopped = session.get("stopped_questions", [])
    if any(g.get("approval", {}).get("status") == "REJECTED" for g in session.get("gap_requests", [])):
        if not open_q:
            _v(out, "ST4", "session", "存在被拒绝的查证缺口，但未保留任何未决问题")
    for sq in stopped:
        if sq.get("stop_rule") not in ("S1", "S2", "S3"):
            _v(out, "ST5", "stopped %s" % sq.get("question_id"), "停止规则标记非法：%r" % sq.get("stop_rule"))
        if not sq.get("known"):
            _v(out, "ST5", "stopped %s" % sq.get("question_id"), "停止的追问未保留已知信息")
    # ST7：收尾前命题应至少一次进入 P3（可观察预测/改判条件），否则不得声称已形成验证方案
    if session.get("state") in ("CHECKPOINT", "CLOSED"):
        triggers = [r.get("trigger") for r in session.get("rounds", [])]
        if "P3" not in triggers:
            claims_plan = any(
                isinstance(r.get("delivered"), list) and any("验证方案" in d or "最小验证" in d for d in r["delivered"])
                for r in session.get("rounds", [])
            ) or session.get("summary", {}).get("claims_validation_plan") is True
            if claims_plan:
                _v(out, "ST7", "session", "会话收尾时未出现 P3，却声称已形成最小验证方案")
            elif not session.get("summary", {}).get("proposition_left_developing"):
                _v(out, "ST7", "session",
                   "会话收尾时未出现 P3（命题未进入可检验形式），但未在 summary 中声明命题仍停在 DEVELOPING")

    # ST6：预算耗尽需记录
    used = session.get("execution", {}).get("usage", {}).get("rounds_used")
    cap = session.get("execution", {}).get("budget", {}).get("max_rounds")
    if cap and used and used >= cap and not session.get("budget_exhausted_at_round"):
        _v(out, "ST6", "session", "实质轮次已达上限但未记录预算耗尽位置与待办")
    return out


# ----------------------------------------------------------------------------
# 9. 综合
# ----------------------------------------------------------------------------
def check_all(session: Dict[str, Any]) -> List[SpecViolation]:
    out: List[SpecViolation] = []
    for fn in (check_session, check_ideas, check_rounds, check_maturity_gate,
               check_decisions, check_gaps, check_reviews, check_stopping):
        out.extend(fn(session))
    return out


def format_violations(violations: List[SpecViolation]) -> str:
    if not violations:
        return "无违规"
    return "\n".join("  - %s" % v for v in violations)
