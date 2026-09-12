#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-idea-debate 会话记录确定性校验器。

只做**结构性**校验：字段、枚举、映射、幂等、授权、预算、停止与未决保留。
**不裁决科学真伪**，也不判断对话质量（后者须人工评审，见 role/quality_gatekeeper.md）。

用法：
    python skills/research-idea-debate/scripts/validate_session.py <session.json> [--json]
    python skills/research-idea-debate/scripts/validate_session.py --self-check

退出码：0 无违规；1 有违规；2 输入错误（文件缺失、JSON 非法）。

实现约束：仅用标准库。若环境中存在 `jsonschema`，额外用 assets/*.schema.json 做一次
JSON Schema 校验；否则跳过并如实报告"未做 schema 校验"，不假装已校验。
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(SKILL_ROOT, "assets")


def _locate_schemas(start):
    """向上查找 canonical `schemas/` 目录。

    仓库布局：`<repo>/skills/<skill>/scripts/` -> `<repo>/schemas/`。
    安装布局：`<dest>/skills/<skill>/scripts/` 或 `<dest>/<skill>/scripts/`，安装脚本会把
    `schemas/` 复制到 `<dest>/schemas/`。逐级向上查找可同时兼容两种布局，避免因目录
    深度假设写死而在部署后失效。
    """
    cur = os.path.abspath(start)
    for _ in range(5):
        cand = os.path.join(cur, "schemas")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.join(os.path.dirname(SKILL_ROOT), "schemas")


SCHEMAS = _locate_schemas(HERE)

# ---- 文档声明的枚举（与 references/ 各规程一致）----
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
    "ROLE_QUESTION", "EXTERNAL_OPINION", "INDEPENDENT_REVIEW",
    "EVIDENCE", "CHECKPOINT", "USER_INITIATIVE",
}
REVIEW_STATUS = {"COMPLETE", "PARTIAL", "FAILED", "UNAVAILABLE"}
DISAGREEMENT = {"LOW_DIVERGENCE", "HIGH_DIVERGENCE", "NOT_APPLICABLE"}
SUBSTANTIVE_KINDS = {"SUBSTANTIVE", "EXTERNAL_INPUT", "REVIEW_SUBMISSION"}
DEVELOPMENT_QUOTA_TRIGGERS = {"P3"}
BANNED_IN_QUESTION = ("以及", "另外", "顺便")
COUNTEREXAMPLE_TYPES = {
    "MEASUREMENT_ARTIFACT", "SAMPLING_ARTIFACT", "ALTERNATIVE_MECHANISM",
    "CONFOUNDING", "SCOPE_LIMIT", "NONE_FOUND",
}
ROLE_ZH = {
    "concept_clarifier": "概念澄清者", "premise_evidence_examiner": "前提与证据审查者",
    "implication_validator": "推论与验证者", "alternative_explorer": "替代解释探索者",
    "reflection_facilitator": "观点修订引导者", "moderator": "主持人",
}
DECLARED_SIGNALS = {
    "INTUITION_FORMULATED", "QUESTION_SHARPENED", "PREMISE_SURFACED",
    "PREMISE_VERIFIED", "PREMISE_CONTRADICTED", "DISCRIMINATION_ADDED",
    "ALTERNATIVE_ADDED", "DISPOSITION_DECIDED", "DECISION_RECORDED",
    "GAP_CONFIRMED", "EVIDENCE_IMPORTED",
}
DEVELOPMENT_SIGNALS = {
    "INTUITION_FORMULATED", "QUESTION_SHARPENED",
    "PREMISE_SURFACED", "DISCRIMINATION_ADDED",
}


class Report(object):
    def __init__(self):
        self.violations = []
        self.checked = 0

    def add(self, rule, where, message):
        self.violations.append({"rule": rule, "where": where, "message": message})

    def ok(self, n=1):
        self.checked += n

    @property
    def failed(self):
        return bool(self.violations)


def _enum(rep, value, allowed, rule, where, field):
    rep.ok()
    if value not in allowed:
        rep.add(rule, where, "%s 取值非法：%r（允许：%s）" % (field, value, sorted(allowed)))


def check_session(rep, s):
    for f in ("schema_version", "session_id", "run_id", "mode", "state",
              "original_prompt", "current_question", "execution"):
        rep.ok()
        if f not in s:
            rep.add("S-FIELD", "session", "缺少必填字段 %s" % f)
    _enum(rep, s.get("mode"), MODES, "S-ENUM", "session", "mode")
    _enum(rep, s.get("state"), STATES, "S-ENUM", "session", "state")
    ex = s.get("execution", {})
    _enum(rep, ex.get("selection_status"), {"pending", "confirmed", "rejected"},
          "S-EXEC", "session.execution", "selection_status")
    budget, usage = ex.get("budget", {}), ex.get("usage", {})
    for key in ("max_rounds", "max_review_batches", "max_subtasks_per_batch",
                "max_active_seconds", "max_events"):
        rep.ok()
        if not isinstance(budget.get(key), int) or budget.get(key, 0) < 1:
            rep.add("BU1", "session.execution.budget.%s" % key, "硬约束缺失或非正整数")
    rep.ok()
    if "max_tokens" in budget:
        rep.add("BU1", "session.execution.budget", "token 不得作为硬约束（只能观测）")
    _enum(rep, usage.get("tokens_metering"),
          {"MEASURED", "ESTIMATED", "UNAVAILABLE", None},
          "BU2", "session.execution.usage", "tokens_metering")
    rep.ok()
    if usage.get("tokens_observed") is None and usage.get("tokens_metering") not in (None, "UNAVAILABLE"):
        rep.add("BU2", "session.execution.usage", "计量非 UNAVAILABLE 时 tokens_observed 不应为 null")
    if s.get("state") in ("CHECKPOINT", "CLOSED", "PAUSED"):
        _enum(rep, s.get("stop_reason"), STOP_REASONS, "ST1", "session", "stop_reason")


def check_ideas(rep, s):
    for idea in s.get("ideas", []):
        iid = idea.get("idea_id", "<no-id>")
        _enum(rep, idea.get("maturation"), MATURATION, "ID-MAT", iid, "maturation")
        seen = set()
        for v in idea.get("versions", []):
            where = "%s@v%s" % (iid, v.get("version"))
            for f in ("version", "proposition", "origin", "epistemic_status",
                      "disposition", "revision_reason"):
                rep.ok()
                if f not in v:
                    rep.add("ID-FIELD", where, "缺少字段 %s" % f)
            rep.ok()
            if v.get("version") in seen:
                rep.add("ID-VER", where, "版本号重复")
            seen.add(v.get("version"))
            _enum(rep, v.get("epistemic_status"), EPISTEMIC, "ID-ENUM", where, "epistemic_status")
            _enum(rep, v.get("disposition"), DISPOSITION, "ID-ENUM", where, "disposition")
            rep.ok()
            if v.get("version") != 1 and v.get("parent_version") not in (seen - {v.get("version")}):
                rep.add("ID-VER", where, "parent_version 未指向已存在的更早版本")
            for a in v.get("assumptions", []):
                _enum(rep, a.get("type"), ASSUMPTION_TYPES, "ID-ASM", where, "assumption.type")
                _enum(rep, a.get("verification_status"), ASSUMPTION_STATUS, "ID-ASM", where,
                      "assumption.verification_status")
                rep.ok()
                if a.get("type") == "VALUE" and not a.get("decided_by"):
                    rep.add("ID-VALUE", where, "价值取舍类前提必须记录 decided_by（用户决定）")
            rep.ok()
            if v.get("disposition") == "DEFERRED" and v.get("epistemic_status") == "EVIDENCE_CHALLENGED":
                rep.add("ID-INDEP", where, "DEFERRED 不得写成 EVIDENCE_CHALLENGED")
        hist = idea.get("maturity_history", [])
        order = {"RAW": 0, "DEVELOPING": 1, "TESTABLE": 2}
        if hist:
            rep.ok()
            if hist[0].get("from") != "RAW":
                rep.add("ID-MAT", iid, "成熟度历史必须从 RAW 开始")
            for h in hist:
                rep.ok()
                if order.get(h.get("to"), -1) - order.get(h.get("from"), -2) != 1:
                    rep.add("ID-MAT", iid, "成熟度不得跳级：%r -> %r" % (h.get("from"), h.get("to")))
            rep.ok()
            if idea.get("maturation") != hist[-1].get("to"):
                rep.add("ID-MAT", iid, "maturation 与 maturity_history 终点不一致")
        else:
            rep.ok()
            if idea.get("maturation") != "RAW":
                rep.add("ID-MAT", iid, "无成熟度历史却声明 maturation=%r" % idea.get("maturation"))
        for link in idea.get("evidence_links", []):
            _enum(rep, link.get("relation"), RELATION, "EV-ENUM", iid, "relation")
            _enum(rep, link.get("alignment"), ALIGNMENT, "EV-ENUM", iid, "alignment")
            rep.ok()
            if link.get("relation") in ("CONTEXT", "BOUNDARY", "CHALLENGE") \
                    and link.get("alignment") == "VERIFIED":
                rep.add("EV1", iid, "relation=%s 不得记为 alignment=VERIFIED" % link.get("relation"))
            rep.ok()
            if not link.get("checked_scope"):
                rep.add("EV2", iid, "缺少 checked_scope")


def check_rounds(rep, s):
    versions = {i.get("idea_id"): {v.get("version") for v in i.get("versions", [])}
                for i in s.get("ideas", [])}
    rounds = s.get("rounds", [])
    rep.ok()
    if not rounds:
        rep.add("RD-EMPTY", "rounds", "没有任何轮次记录")
        return
    seq = [r.get("round") for r in rounds]
    rep.ok()
    if seq != sorted(x for x in seq if x is not None) or len(set(seq)) != len(seq):
        rep.add("RD-SEQ", "rounds", "轮次序号必须唯一且递增：%s" % seq)
    for r in rounds:
        where = "R%s" % r.get("round")
        q = r.get("question", "")
        rep.ok()
        if q.count("？") + q.count("?") != 1:
            rep.add("RD1", where, "焦点问题必须恰好一个问号，实际 %d 个"
                    % (q.count("？") + q.count("?")))
        for b in BANNED_IN_QUESTION:
            rep.ok()
            if b in q:
                rep.add("RD1", where, "焦点问题含并列引导词 %r" % b)
        rep.ok()
        if not r.get("user_answer"):
            rep.add("RD2", where, "缺少用户回答（不得代答）")
        rep.ok()
        if not r.get("intent"):
            rep.add("RD3", where, "缺少 intent")
        role, qtype = r.get("role"), r.get("question_type")
        rep.ok()
        if role not in ROLE_QUESTION_TYPE:
            rep.add("RD4", where, "未知 role_id：%r" % role)
        elif ROLE_QUESTION_TYPE[role] != qtype:
            rep.add("RD4", where, "role_id=%s 必须配 question_type=%s，实际 %s"
                    % (role, ROLE_QUESTION_TYPE[role], qtype))
        if r.get("idea_id"):
            rep.ok()
            if r.get("target_version") not in versions.get(r["idea_id"], set()):
                rep.add("RD5", where, "target_version=%r 不是已存在版本" % r.get("target_version"))
        rep.ok()
        if r.get("kind") in SUBSTANTIVE_KINDS and not r.get("idea_id"):
            rep.add("RD6", where, "实质轮未绑定 idea_id")
        rep.ok()
        if qtype == "CONFIGURATION" and role != "moderator":
            rep.add("RD7", where, "CONFIGURATION 只能由主持人提出")
        rep.ok()
        if r.get("trigger") in {"P2", "P3", "P4"} and r.get("requires_user_held_evidence"):
            rep.add("RD8", where, "评估性提问要求用户提供其不具备的证据")
        for sig in r.get("signals", []):
            rep.ok()
            if sig not in DECLARED_SIGNALS:
                rep.add("RD9", where, "未声明的进展信号：%r" % sig)
        # RD10：一轮内出现的角色名不超过两个（合并标签算一项）
        label_text = r.get("labels_text") or r.get("question") or ""
        mentioned = [zh for zh in set(ROLE_ZH.values()) if zh in label_text]
        if len(mentioned) > 2:
            rep.add("RD10", where, "同一轮出现 %d 个角色名（上限 2）：%s"
                    % (len(mentioned), sorted(mentioned)))


def check_maturity_gate(rep, s):
    for idea in s.get("ideas", []):
        iid = idea.get("idea_id")
        if not any(h.get("from") == "RAW" for h in idea.get("maturity_history", [])):
            continue
        signals = 0
        for r in s.get("rounds", []):
            if r.get("idea_id") != iid:
                continue
            if r.get("trigger") in DEVELOPMENT_QUOTA_TRIGGERS:
                rep.ok()
                if signals < 2:
                    rep.add("MT1", "R%s" % r.get("round"),
                            "%s 从 RAW 起步，进入 %s 前只有 %d 个发展信号（需 ≥2）"
                            % (iid, r.get("trigger"), signals))
                break
            signals += sum(1 for x in r.get("signals", []) if x in DEVELOPMENT_SIGNALS)


def check_decisions(rep, s):
    decisions = []
    for idea in s.get("ideas", []):
        decisions.extend(idea.get("decisions", []))
    decisions.extend(s.get("decisions", []))
    for d in decisions:
        where = "decision %s" % d.get("id")
        for f in ("id", "action", "reason", "author", "triggered_by", "user_confirmation"):
            rep.ok()
            if f not in d:
                rep.add("DC-FIELD", where, "缺少字段 %s" % f)
        rep.ok()
        if d.get("triggered_by") == "EXTERNAL_OPINION" and d.get("author") == "EXTERNAL_OPINION":
            rep.add("DC1", where, "外部意见不得作为决定作者")
        _enum(rep, d.get("triggered_by"), DECISION_TRIGGERS, "DC2", where, "triggered_by")
        rep.ok()
        if d.get("author") == "AI建议" and not d.get("user_confirmation"):
            rep.add("DC3", where, "AI 建议未获用户确认即成为决定")


def check_gaps(rep, s):
    for g in s.get("gap_requests", []):
        where = "gap %s" % g.get("gap_id")
        for f in ("gap_id", "idea_id", "question", "reason", "decision_impact",
                  "scope", "approval", "execution_status", "blocking"):
            rep.ok()
            if f not in g:
                rep.add("GP-FIELD", where, "缺少字段 %s" % f)
        ap = g.get("approval", {})
        _enum(rep, ap.get("status"), APPROVAL_STATUS, "GP-ENUM", where, "approval.status")
        rep.ok()
        if not ap.get("scope_fingerprint"):
            rep.add("GP1", where, "缺少 scope_fingerprint")
        rep.ok()
        if ap.get("status") != "CONFIRMED" and g.get("execution_status") not in \
                ("NOT_STARTED", "REFUSED_BY_USER"):
            rep.add("GP2", where, "approval=%s 时 execution_status 不得为 %s（先确认后执行）"
                    % (ap.get("status"), g.get("execution_status")))
        rep.ok()
        if ap.get("status") == "CONFIRMED" and not ap.get("confirmed_event_id"):
            rep.add("GP3", where, "已确认但缺少 confirmed_event_id")
        rep.ok()
        if g.get("scope_changed") and ap.get("status") == "CONFIRMED":
            rep.add("GP4", where, "范围已变更但旧确认未失效")
        rep.ok()
        if ap.get("status") == "REJECTED" and not g.get("question"):
            rep.add("GP5", where, "拒绝查证后缺口须保留")


def check_reviews(rep, s):
    gaps = {g.get("gap_id") for g in s.get("gap_requests", [])}
    batches = {b.get("batch_id"): b.get("subtasks", []) for b in s.get("review_batches", [])}
    cap = s.get("execution", {}).get("budget", {}).get("max_subtasks_per_batch")
    for r in s.get("review_requests", []):
        where = "review %s" % r.get("request_id")
        excluded = " ".join(r.get("excluded", []))
        for must in ("其他评估者", "主持人"):
            rep.ok()
            if must not in excluded:
                rep.add("RV1", where, "输入未显式排除 %s 的倾向/结果" % must)
        rep.ok()
        if not r.get("submitted_separately"):
            rep.add("RV2", where, "评估结果未分别提交")
        rep.ok()
        if r.get("cross_talk_rounds", 0) > 1:
            rep.add("RV3", where, "交叉回应超过 1 轮")
        tasks = batches.get(r.get("batch_id"), [])
        rep.ok()
        if cap is not None and len(tasks) > cap:
            rep.add("RV4", where, "单批子任务超限")
        lenses = [t.get("lens") for t in tasks]
        rep.ok()
        if len(lenses) != len(set(lenses)):
            rep.add("RV5", where, "同批使用了重复视角")
        for t in tasks:
            rep.ok()
            if t.get("input_version") != r.get("input_version"):
                rep.add("RV6", where, "任务 %s 的 input_version 与请求不一致" % t.get("task_id"))
    for b in s.get("review_batches", []):
        where = "batch %s" % b.get("batch_id")
        subs = b.get("subtasks", [])
        done = [t for t in subs if t.get("status") == "COMPLETE"]
        ds = b.get("disagreement_signal")
        _enum(rep, ds, DISAGREEMENT, "RV7", where, "disagreement_signal")
        rep.ok()
        if ds in ("LOW_DIVERGENCE", "HIGH_DIVERGENCE") and b.get("computed_by") != "deterministic_program":
            rep.add("RV8", where, "分歧判定必须来自确定性程序")
        # RV15：判定须基于可枚举字段，不得用前提文本的字面重合
        if b.get("computed_by") == "deterministic_program":
            rep.ok()
            # 只在**实际给出了分歧判定**时要求反例类型标签；
            # NOT_APPLICABLE（评估者不足 2 个）本无分歧可标，不应据此报错。
            if ds in ("LOW_DIVERGENCE", "HIGH_DIVERGENCE") and not b.get("counterexample_types"):
                rep.add("RV15", where,
                        "分歧判定缺少反例类型标签；不得用承重前提的字面重合代替语义比较")
            for tv in (b.get("counterexample_types") or {}).values():
                rep.ok()
                if tv not in COUNTEREXAMPLE_TYPES:
                    rep.add("RV15", where, "未声明的反例类型标签：%r" % tv)
            # 结论相同 + 反例类型相同 时不应判为 HIGH
            if ds == "HIGH_DIVERGENCE":
                tv = list((b.get("counterexample_types") or {}).values())
                same_verdict = len({t.get("verdict") for t in done}) == 1 and len(done) >= 2
                if same_verdict and len(tv) == 2 and tv[0] == tv[1] and not b.get("mutual_denial"):
                    rep.add("RV15", where,
                            "verdict 与反例类型均相同且无相互否定，不应判 HIGH_DIVERGENCE")
        rep.ok()
        if len(done) < 2 and ds != "NOT_APPLICABLE":
            rep.add("RV10", where, "评估者不足 2 个时应为 NOT_APPLICABLE")
        rep.ok()
        if len(done) < 2 and ds == "LOW_DIVERGENCE":
            rep.add("RV9", where, "评估者不足 2 个不得判 LOW_DIVERGENCE")
        if b.get("degraded"):
            rep.ok()
            if b.get("execution_kind") != "SELF_CHECK":
                rep.add("RV11", where, "降级批次必须记 execution_kind=SELF_CHECK")
            rep.ok()
            if ds == "LOW_DIVERGENCE":
                rep.add("RV11", where, "降级批次不得给出 LOW_DIVERGENCE")
            rep.ok()
            if b.get("satisfies_convergence_precondition"):
                rep.add("RV11", where, "降级批次不得满足收敛前提")
        if ds == "HIGH_DIVERGENCE":
            rep.ok()
            if not b.get("resolution"):
                rep.add("RV12", where, "HIGH_DIVERGENCE 未记录处理方式")
            rep.ok()
            if b.get("resolution") in ("VOTE", "AVERAGE", "CONSENSUS"):
                rep.add("RV12", where, "分歧不得以投票/平均/共识消解")
            if b.get("resolution") == "ESCALATED_TO_GAP":
                rep.ok()
                gid = b.get("escalated_gap_id")
                if gid not in gaps:
                    rep.add("RV13", where, "升级到的缺口 %r 不存在（可用缺口：%s）" % (gid, sorted(list(gaps))))
        verdicts = b.get("verdicts") or {}
        done_ids = {t.get("task_id") for t in done}
        rep.ok()
        if set(verdicts) - done_ids:
            rep.add("RV14", where, "verdicts 含非 COMPLETE 任务的结果")
        rep.ok()
        if done_ids - set(verdicts):
            rep.add("RV14", where, "已完成的评估者缺少 verdict")


def check_stopping(rep, s):
    sub = [r for r in s.get("rounds", []) if r.get("kind") in SUBSTANTIVE_KINDS]
    streak, trigger = 0, None
    for r in sub:
        streak = streak + 1 if not r.get("signals") else 0
        if streak >= 2:
            trigger = r.get("round")
            break
    ended = s.get("state") in ("CHECKPOINT", "CLOSED", "PAUSED")
    rep.ok()
    if trigger is not None and not ended:
        rep.add("ST2", "session", "R%s 起连续两轮无进展信号，但会话未收尾" % trigger)
    if trigger is not None and ended:
        rep.ok()
        if not any(r.get("stop_reason") or r.get("kind") == "CHECKPOINT"
                   for r in s.get("rounds", []) if (r.get("round") or 0) >= trigger):
            rep.add("ST2", "session", "连续两轮无进展后未记录 CHECKPOINT 或 stop_reason")
    for r in s.get("rounds", []):
        if r.get("kind") == "CHECKPOINT":
            blob = "%s %s" % (r.get("question", ""), r.get("user_answer", ""))
            for bad in ("已解决", "已证实", "结论成立", "问题解决", "已经解决"):
                rep.ok()
                if bad in blob:
                    rep.add("ST3", "R%s" % r.get("round"), "CHECKPOINT 不得宣告问题解决")
    if any(g.get("approval", {}).get("status") == "REJECTED" for g in s.get("gap_requests", [])):
        rep.ok()
        if not s.get("open_questions"):
            rep.add("ST4", "session", "存在被拒绝的查证缺口，但未保留未决问题")
    for sq in s.get("stopped_questions", []):
        where = "stopped %s" % sq.get("question_id")
        _enum(rep, sq.get("stop_rule"), {"S1", "S2", "S3"}, "ST5", where, "stop_rule")
        rep.ok()
        if not sq.get("known"):
            rep.add("ST5", where, "停止的追问未保留已知信息")
    used = s.get("execution", {}).get("usage", {}).get("rounds_used")
    cap = s.get("execution", {}).get("budget", {}).get("max_rounds")
    rep.ok()
    if cap and used and used >= cap and not s.get("budget_exhausted_at_round"):
        rep.add("ST6", "session", "实质轮次已达上限但未记录预算耗尽位置与待办")
    if s.get("state") in ("CHECKPOINT", "CLOSED"):
        triggers = [r.get("trigger") for r in s.get("rounds", [])]
        if "P3" not in triggers:
            claims = s.get("summary", {}).get("claims_validation_plan") is True
            rep.ok()
            if claims:
                rep.add("ST7", "session", "收尾时未出现 P3，却声称已形成最小验证方案")
            else:
                rep.ok()
                if not s.get("summary", {}).get("proposition_left_developing"):
                    rep.add("ST7", "session", "收尾时未出现 P3（命题仍在 DEVELOPING），但未在 summary 中声明")


CHECKS = (check_session, check_ideas, check_rounds, check_maturity_gate,
          check_decisions, check_gaps, check_reviews, check_stopping)


def validate(session):
    rep = Report()
    for fn in CHECKS:
        fn(rep, session)
    return rep


def try_jsonschema(session):
    """存在 jsonschema 时做一次 schema 校验；否则如实报告未做。"""
    path = os.path.join(SCHEMAS, "research_debate_session.schema.json")
    if not os.path.isfile(path):
        return "SKIPPED", "未找到 schemas/research_debate_session.schema.json"
    try:
        import jsonschema  # noqa: WPS433
    except Exception:
        return "SKIPPED", "环境无 jsonschema，未做 JSON Schema 校验（不代表通过）"
    schema = json.load(open(path, encoding="utf-8"))
    try:
        jsonschema.validate(session, schema)
        return "PASS", "session.schema.json 校验通过"
    except Exception as exc:  # noqa: BLE001
        return "FAIL", "schema 校验失败：%s" % exc


def main(argv=None):
    ap = argparse.ArgumentParser(description="research-idea-debate 会话记录确定性校验")
    ap.add_argument("session", nargs="?", help="session.json 路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--self-check", action="store_true", help="自检：校验器可加载且模块文件齐全")
    args = ap.parse_args(argv)

    if args.self_check:
        required = [
            "SKILL.md",
            "role/moderator.md", "role/concept_clarifier.md", "role/premise_evidence_examiner.md",
            "role/implication_validator.md", "role/alternative_explorer.md",
            "role/reflection_facilitator.md", "role/quality_gatekeeper.md",
            "references/dialogue_protocol.md", "references/maturation_and_gates.md",
            "references/independent_review.md", "references/evidence_handoff.md",
            "references/convergence_and_recovery.md",
            "assets/session_summary_template.md", "assets/validation_plan_template.md",
            "examples/intuition_to_question.md", "examples/hypothesis_revision.md",
        ]
        # canonical schema 位于仓库根，单独核对
        canonical = [
            "research_debate_session.schema.json",
            "research_debate_event.schema.json",
            "research_debate_gap.schema.json",
        ]
        missing = [p for p in required if not os.path.isfile(os.path.join(SKILL_ROOT, p))]
        print("技能模块自检：%d/%d 存在" % (len(required) - len(missing), len(required)))
        for m in missing:
            print("  [FAIL] 缺失技能模块: %s" % m)

        absent = [n for n in canonical if not os.path.isfile(os.path.join(SCHEMAS, n))]
        if absent:
            print("  [WARN] 未找到 canonical schema（%s）：%s" % (SCHEMAS, ", ".join(absent)))
            print("         结构性校验仍可运行，但 JSON Schema 校验会被跳过（不会假装通过）。")
            print("         修法：在仓库内运行 `bash scripts/install.sh`，或把 `schemas/` 复制到部署根目录。")
        else:
            print("canonical schema：%d/%d 存在（%s）" % (len(canonical), len(canonical), SCHEMAS))

        # 技能模块缺失才算失败；schema 属部署环境问题，降级为警告
        return 1 if missing else 0

    if not args.session:
        ap.error("需要 session.json 路径，或使用 --self-check")
    if not os.path.isfile(args.session):
        print("输入错误：文件不存在 %s" % args.session, file=sys.stderr)
        return 2
    try:
        session = json.load(open(args.session, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("输入错误：JSON 无法解析 %s" % exc, file=sys.stderr)
        return 2

    rep = validate(session)
    schema_status, schema_note = try_jsonschema(session)
    result = {
        "session": args.session,
        "checks_run": rep.checked,
        "violations": rep.violations,
        "json_schema": {"status": schema_status, "note": schema_note},
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("会话：%s" % args.session)
        print("已检查项：%d" % rep.checked)
        print("JSON Schema：%s（%s）" % (schema_status, schema_note))
        if rep.violations:
            print("违规 %d 条：" % len(rep.violations))
            for v in rep.violations:
                print("  - [%s] %s: %s" % (v["rule"], v["where"], v["message"]))
        else:
            print("无结构性违规。注意：这不代表对话质量合格，也不判断科学真伪。")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
