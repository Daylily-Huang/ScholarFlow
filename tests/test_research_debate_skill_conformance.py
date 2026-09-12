# -*- coding: utf-8 -*-
"""research-idea-debate 技能本体的一致性测试（M1 补齐）。

与 `test_research_debate_skill_assets.py` 的分工：
  - 后者检查"文件是否齐全、链接是否可解析、schema 是否合法"（模块级结构）；
  - 本模块检查"技能文档内部的规则是否互相一致、示例是否符合自家协议、
    校验器脚本是否真的能跑"（内容级一致性）。

**不验证**技能被平台加载后的对话表现——那需要真实会话验收（设计稿 §14 的 A01–A34）。
"""

import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "research-idea-debate"
VALIDATOR = SKILL / "scripts" / "validate_session.py"
SPECIMEN = REPO_ROOT / "tests" / "fixtures" / "specimen_session_debate.json"
LIVE_SESSION = REPO_ROOT / ".planning" / "research-idea-debate" / "live-run" / "session.json"

SKILL_MD = SKILL / "SKILL.md"
ROLE_FILES = {
    "moderator": SKILL / "role" / "moderator.md",
    "concept_clarifier": SKILL / "role" / "concept_clarifier.md",
    "premise_evidence_examiner": SKILL / "role" / "premise_evidence_examiner.md",
    "implication_validator": SKILL / "role" / "implication_validator.md",
    "alternative_explorer": SKILL / "role" / "alternative_explorer.md",
    "reflection_facilitator": SKILL / "role" / "reflection_facilitator.md",
    "quality_gatekeeper": SKILL / "role" / "quality_gatekeeper.md",
}
REFERENCE_FILES = {
    "dialogue_protocol": SKILL / "references" / "dialogue_protocol.md",
    "maturation_and_gates": SKILL / "references" / "maturation_and_gates.md",
    "independent_review": SKILL / "references" / "independent_review.md",
    "evidence_handoff": SKILL / "references" / "evidence_handoff.md",
    "convergence_and_recovery": SKILL / "references" / "convergence_and_recovery.md",
}
ROLE_QUESTION_TYPE = {
    "concept_clarifier": "CLARIFICATION",
    "premise_evidence_examiner": "PREMISE_EVIDENCE",
    "implication_validator": "IMPLICATION",
    "alternative_explorer": "COMPARISON",
    "reflection_facilitator": "REFLECTION",
    "moderator": "CONFIGURATION",
}
REQUIRED_SIGNALS = {
    "INTUITION_FORMULATED", "QUESTION_SHARPENED", "PREMISE_SURFACED", "PREMISE_VERIFIED",
    "PREMISE_CONTRADICTED", "DISCRIMINATION_ADDED", "ALTERNATIVE_ADDED",
    "DISPOSITION_DECIDED", "DECISION_RECORDED", "GAP_CONFIRMED", "EVIDENCE_IMPORTED",
}
STOP_REASONS = {
    "USER_CLOSED", "CHECKPOINT_REACHED", "NO_PROGRESS",
    "BUDGET_EXHAUSTED", "PAUSED", "USER_SWITCHED_MODE",
}
BANNED_IN_QUESTION = ("以及", "另外", "顺便")


def _read(p):
    return io.open(str(p), encoding="utf-8").read()


def _skill_md_text():
    return _read(SKILL_MD)


def _all_skill_text():
    parts = []
    for p in sorted(SKILL.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".json", ".py"):
            parts.append(_read(p))
    return "\n".join(parts)


class TestRoleAndTypeConsistency(unittest.TestCase):
    """role_id ↔ question_type 的对应关系必须在 SKILL.md、角色文件与校验器三处一致。"""

    def test_every_role_has_a_file(self):
        for role in ROLE_QUESTION_TYPE:
            self.assertIn(role, ROLE_FILES, "缺少角色文件：%s" % role)
            self.assertTrue(ROLE_FILES[role].is_file(), "角色文件不存在：%s" % role)

    def test_skill_md_declares_all_roles_and_types(self):
        text = _skill_md_text()
        for role, qtype in ROLE_QUESTION_TYPE.items():
            self.assertIn("`%s`" % role, text, "SKILL.md 未声明 role_id %s" % role)
            self.assertIn(qtype, text, "SKILL.md 未声明 question_type %s" % qtype)

    def test_mapping_is_one_to_one(self):
        self.assertEqual(len(set(ROLE_QUESTION_TYPE.values())), len(ROLE_QUESTION_TYPE),
                         "question_type 必须与 role_id 一一对应")

    def test_validator_mapping_matches_docs(self):
        """校验器内置的映射必须与文档一致——否则脚本会放过契约违规。"""
        src = _read(VALIDATOR)
        for role, qtype in ROLE_QUESTION_TYPE.items():
            self.assertIn('"%s": "%s"' % (role, qtype), src,
                          "校验器映射与文档不一致：%s -> %s" % (role, qtype))

    def test_role_files_do_not_cross_assign_types(self):
        """每个角色文件只应出现自己的 question_type，不得出现别人的。"""
        offenders = []
        for role, path in ROLE_FILES.items():
            if role == "quality_gatekeeper":
                continue  # 审查职能不提问
            text = _read(path)
            for other_role, other_type in ROLE_QUESTION_TYPE.items():
                if other_role == role or other_role == "moderator":
                    continue
                if other_role in text and other_type in text.split("## 一、")[0]:
                    offenders.append("%s 头部出现他人类型 %s" % (role, other_type))
        self.assertEqual(offenders, [], offenders)


class TestLadderConsistency(unittest.TestCase):
    """P0–P6 阶梯必须在 SKILL.md 与 moderator.md 两处都完整出现。"""

    def test_skill_md_has_full_ladder(self):
        text = _skill_md_text()
        for i in range(7):
            self.assertIn("| P%d |" % i, text, "SKILL.md 阶梯缺少 P%d" % i)

    def test_moderator_has_full_ladder(self):
        text = _read(ROLE_FILES["moderator"])
        for i in range(7):
            self.assertIn("| P%d |" % i, text, "moderator.md 阶梯缺少 P%d" % i)

    def test_ladder_entries_map_to_declared_roles(self):
        text = _read(ROLE_FILES["moderator"])
        for role in ("concept_clarifier", "premise_evidence_examiner",
                     "implication_validator", "alternative_explorer",
                     "reflection_facilitator"):
            self.assertIn("`%s`" % role, text, "moderator.md 阶梯未引用 %s" % role)

    def test_p5_is_independent_review_not_a_role(self):
        text = _read(ROLE_FILES["moderator"])
        p5 = [l for l in text.splitlines() if l.startswith("| P5 |")]
        self.assertTrue(p5, "缺少 P5 行")
        self.assertIn("独立评估", p5[0], "P5 应指向独立评估")


class TestStopRulesConsistency(unittest.TestCase):
    def test_s1_to_s6_present_in_reference(self):
        text = _read(REFERENCE_FILES["convergence_and_recovery"])
        for i in range(1, 7):
            self.assertIn("| S%d |" % i, text, "缺少停止规则 S%d" % i)

    def test_stop_reasons_match_validator(self):
        text = _read(REFERENCE_FILES["convergence_and_recovery"])
        src = _read(VALIDATOR)
        for reason in STOP_REASONS:
            self.assertIn(reason, text, "规程缺少停止原因 %s" % reason)
            self.assertIn('"%s"' % reason, src, "校验器缺少停止原因 %s" % reason)

    def test_s1_criteria_documented(self):
        text = _read(REFERENCE_FILES["convergence_and_recovery"])
        self.assertIn("S1 判定口径", text)
        self.assertIn("实质轮次", text)


class TestProgressSignalsConsistency(unittest.TestCase):
    def test_all_signals_in_reference_and_validator(self):
        ref = _read(REFERENCE_FILES["convergence_and_recovery"])
        src = _read(VALIDATOR)
        for sig in REQUIRED_SIGNALS:
            self.assertIn(sig, ref, "规程缺少进展信号 %s" % sig)
            self.assertIn(sig, src, "校验器缺少进展信号 %s" % sig)

    def test_development_signal_set_is_four(self):
        ref = _read(REFERENCE_FILES["maturation_and_gates"])
        for sig in ("INTUITION_FORMULATED", "QUESTION_SHARPENED",
                    "PREMISE_SURFACED", "DISCRIMINATION_ADDED"):
            self.assertIn("`%s`" % sig, ref)
        self.assertIn("`ALTERNATIVE_ADDED`（补了一条替代解释）**不计入**", ref)

    def test_quota_scope_is_p3_only(self):
        ref = _read(REFERENCE_FILES["maturation_and_gates"])
        self.assertIn("才能进入 **P3**", ref)
        self.assertIn("P2 前提审查与 P4 替代解释属生成性动作", ref)


class TestNegativePatternsConsistency(unittest.TestCase):
    def test_n1_to_n7_defined_once_and_referenced(self):
        gk = _read(ROLE_FILES["quality_gatekeeper"])
        for i in range(1, 8):
            self.assertIn("| N%d |" % i, gk, "质量审查缺少 N%d" % i)
        proto = _read(REFERENCE_FILES["dialogue_protocol"])
        self.assertIn("N1–N7", proto, "对话协议未引用负例清单")

    def test_bundled_question_counterexample_present(self):
        proto = _read(REFERENCE_FILES["dialogue_protocol"])
        self.assertIn("语义打包", proto)
        self.assertIn("✗", proto)
        self.assertIn("✓", proto)


class TestExamplesConformToOwnProtocol(unittest.TestCase):
    """示例必须遵守本技能自己的单轮协议——示例违规比没有示例更糟。"""

    def _examples(self):
        return {p.name: _read(p) for p in sorted((SKILL / "examples").glob("*.md"))}

    def test_every_focus_question_is_single(self):
        offenders = []
        for name, text in self._examples().items():
            for q in re.findall(r"^焦点问题：(.+)$", text, flags=re.M):
                marks = q.count("？") + q.count("?")
                if marks != 1:
                    offenders.append("%s: 问号 %d 个 -> %s" % (name, marks, q[:40]))
                for b in BANNED_IN_QUESTION:
                    if b in q:
                        offenders.append("%s: 含并列引导词 %r -> %s" % (name, b, q[:40]))
        self.assertEqual(offenders, [], "示例焦点问题违规：%s" % offenders)

    def test_each_round_has_contribution_and_question(self):
        offenders = []
        for name, text in self._examples().items():
            blocks = re.split(r"^## R\d+.*$", text, flags=re.M)[1:]
            for idx, b in enumerate(blocks, start=1):
                if "焦点问题：" not in b:
                    offenders.append("%s R%d 缺焦点问题" % (name, idx))
                if "贡献（" not in b:
                    offenders.append("%s R%d 缺实质贡献" % (name, idx))
        self.assertEqual(offenders, [], "示例轮次不完整：%s" % offenders)

    def test_examples_declare_fictional_status(self):
        for name, text in self._examples().items():
            self.assertIn("虚构", text.splitlines()[0] + text[:400],
                          "%s 未声明为虚构演示" % name)

    def test_examples_have_rule_landing_notes(self):
        for name, text in self._examples().items():
            self.assertGreaterEqual(text.count("规则落点"), 4,
                                    "%s 规则落点注释过少" % name)

    def test_examples_do_not_fabricate_numbers(self):
        """示例不得给出具体样本量/统计方法数值——未知一律待补。"""
        pattern = re.compile(r"(n\s*=\s*\d+|样地\s*\d+\s*块|\d+\s*个重复|p\s*[<=]\s*0\.\d+)")
        for name, text in self._examples().items():
            hits = pattern.findall(text)
            self.assertEqual(hits, [], "%s 出现疑似伪造数值：%s" % (name, hits))


class TestValidatorActuallyRuns(unittest.TestCase):
    """技能自带脚本必须可执行——文档写得再好，脚本跑不起来也不算交付。"""

    def _run(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)
        proc = subprocess.run([sys.executable, str(VALIDATOR), *args],
                              capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
        return proc.returncode, proc.stdout + proc.stderr

    def test_validator_compiles(self):
        proc = subprocess.run([sys.executable, "-m", "py_compile", str(VALIDATOR)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_self_check_reports_canonical_schemas(self):
        code, out = self._run("--self-check")
        self.assertEqual(code, 0, out)
        self.assertIn("canonical schema", out)

    def test_no_session_argument_is_usage_error(self):
        code, out = self._run()
        self.assertNotEqual(code, 0, out)

    def test_specimen_passes_and_live_fails_as_expected(self):
        if SPECIMEN.is_file():
            code, out = self._run(str(SPECIMEN))
            self.assertEqual(code, 0, out)
        if LIVE_SESSION.is_file():
            code, out = self._run(str(LIVE_SESSION))
            self.assertEqual(code, 1, out)
            self.assertIn("[RD1]", out)
            self.assertIn("[RV15]", out)


class TestHandoffBoundaryDeclarations(unittest.TestCase):
    """技能必须声明与前三个技能的边界，避免重复建设。"""

    def test_skill_md_declares_handoff_targets(self):
        text = _skill_md_text()
        for skill in ("literature-discovery-acquisition", "literature-evidence-extraction",
                      "literature-synthesis"):
            self.assertIn(skill, text, "SKILL.md 未声明与 %s 的关系" % skill)

    def test_does_not_redefine_upstream_capabilities(self):
        """技能必须显式声明不复制上游能力，否则会重复建设。"""
        text = _skill_md_text()
        self.assertIn("**不复制**已有能力", text)
        for capability in ("学术争议九分类", "共识分级", "Devil's Advocate", "研究空白十类识别"):
            self.assertIn(capability, text, "应显式声明不复制 %s" % capability)

    def test_declares_evidence_need_before_file_handoff(self):
        """查证必须"先确认后执行"，技能文档需写明该硬约束。"""
        text = _all_skill_text()
        self.assertIn("approval.status = CONFIRMED", text)
        self.assertIn("禁止调用检索", text)

    def test_gap_types_match_design(self):
        text = _all_skill_text()
        for gap_type in ("SEARCH_GAP", "EXTRACTION_GAP", "SYNTHESIS_REQUEST"):
            self.assertIn(gap_type, text, "缺少缺口类型 %s" % gap_type)


class TestSecondLiveRunFindings(unittest.TestCase):
    """第二轮实跑（装好后真实使用）暴露的 5 个缺口必须已被修复，且不得回退。"""

    def test_gap1_user_delegated_choice_branch_exists(self):
        """用户答"你定吧"时必须有分支规定，且不得记成用户自选。"""
        text = _skill_md_text()
        self.assertIn("用户拒选／授权代选的分支", text)
        self.assertIn("user_delegated_choice_documented", text)
        self.assertIn("不得", text)

    def test_gap2_signal_round_attribution_is_specified(self):
        text = _read(REFERENCE_FILES["convergence_and_recovery"])
        self.assertIn("信号归属哪一轮", text)
        self.assertIn("backdated_to_round", text)

    def test_gap3_state_must_come_from_structured_records(self):
        """状态查询规则：不得凭叙述判断会话状态。"""
        text = _read(REFERENCE_FILES["convergence_and_recovery"])
        self.assertIn("状态查询规则", text)
        self.assertIn("结构化记录", text)
        self.assertIn("未核实", text)

    def test_gap4_divergence_uses_enumerable_fields_only(self):
        """分歧判定只比较可枚举字段；明令禁用前提文本字面重合。"""
        text = _read(REFERENCE_FILES["independent_review"])
        self.assertIn("不得用字面集合重合代替语义比较", text)
        for label in ("MEASUREMENT_ARTIFACT", "SAMPLING_ARTIFACT",
                      "ALTERNATIVE_MECHANISM", "CONFOUNDING", "SCOPE_LIMIT", "NONE_FOUND"):
            self.assertIn(label, text, "缺少反例类型标签 %s" % label)
        self.assertIn("不比较", text)

    def test_gap5_two_role_names_per_round(self):
        text = _read(REFERENCE_FILES["dialogue_protocol"])
        self.assertIn("一轮内出现的角色名不超过两个", text)
        self.assertIn("合并轮的焦点问题只能归属", text)

    def test_validator_enforces_new_rules(self):
        src = _read(VALIDATOR)
        self.assertIn('"RD10"', src)
        self.assertIn('"RV15"', src)
        self.assertIn("COUNTEREXAMPLE_TYPES", src)

    def test_new_rules_are_indexed_in_design_doc(self):
        doc = _read(REPO_ROOT / "docs" / "rfcs" / "research-idea-debate-design.md")
        for rule in ("`RD10`", "`RV15`"):
            self.assertIn(rule, doc, "设计稿规则索引缺少 %s" % rule)

    def test_second_run_artifacts_recorded(self):
        text = _read(REPO_ROOT / "docs" / "rfcs" / "research-idea-debate-design.md")
        self.assertIn("### 14.9 安装后真实运行实测", text, "缺少第二轮实跑章节")
        self.assertIn("HIGH_DIVERGENCE", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
