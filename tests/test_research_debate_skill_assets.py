# -*- coding: utf-8 -*-
"""research-idea-debate 技能本体（M1）的结构与行为契约测试。

检查对象：`skills/research-idea-debate/`。
本测试只验证**技能文件自身**（模块齐全、链接可解析、校验器行为正确），
不验证技能被平台加载后的对话表现——那需要真实会话验收（见设计稿 §14）。
"""

import json
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

REQUIRED_FILES = [
    "SKILL.md",
    "role/moderator.md",
    "role/concept_clarifier.md",
    "role/premise_evidence_examiner.md",
    "role/implication_validator.md",
    "role/alternative_explorer.md",
    "role/reflection_facilitator.md",
    "role/quality_gatekeeper.md",
    "references/dialogue_protocol.md",
    "references/maturation_and_gates.md",
    "references/independent_review.md",
    "references/evidence_handoff.md",
    "references/convergence_and_recovery.md",
    "assets/session_summary_template.md",
    "assets/validation_plan_template.md",
    "examples/intuition_to_question.md",
    "examples/hypothesis_revision.md",
    "scripts/validate_session.py",
]

ROLE_QUESTION_TYPE = {
    "concept_clarifier": "CLARIFICATION",
    "premise_evidence_examiner": "PREMISE_EVIDENCE",
    "implication_validator": "IMPLICATION",
    "alternative_explorer": "COMPARISON",
    "reflection_facilitator": "REFLECTION",
    "moderator": "CONFIGURATION",
}


def _run_validator(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run([sys.executable, str(VALIDATOR), *args],
                          capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout + proc.stderr


class TestSkillModulePresence(unittest.TestCase):
    def test_all_modules_exist(self):
        missing = [p for p in REQUIRED_FILES if not (SKILL / p).is_file()]
        self.assertEqual(missing, [], "技能模块缺失：%s" % missing)

    def test_skill_frontmatter(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "SKILL.md 缺少 YAML frontmatter")
        head = text.split("---")[1]
        self.assertIn("name: research-idea-debate", head)
        self.assertIn("description:", head)

    def test_no_replaced_characters(self):
        bad = []
        for path in SKILL.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".json", ".py"):
                if "\ufffd" in path.read_text(encoding="utf-8"):
                    bad.append(str(path.relative_to(SKILL)))
        self.assertEqual(bad, [], "含替换字符：%s" % bad)


class TestSkillInternalLinks(unittest.TestCase):
    """技能内相对链接必须可解析——否则加载时会指向不存在的模块。"""

    def test_relative_links_resolve(self):
        broken = []
        for fp in SKILL.rglob("*.md"):
            text = fp.read_text(encoding="utf-8")
            for m in re.finditer(r"\[[^\]]*\]\(([^)#h][^)]*)\)", text):
                href = m.group(1).strip()
                if href.startswith(("http", "mailto:")):
                    continue
                target = (fp.parent / href.split("#")[0]).resolve()
                if not target.exists():
                    broken.append("%s -> %s" % (fp.relative_to(REPO_ROOT), href))
        self.assertEqual(broken, [], "技能内断链：%s" % broken)

    def test_schema_references_use_relative_paths(self):
        """技能文档引用 canonical schema 时必须用相对路径。

        仓库既有测试 `test_referenced_schema_files_exist` 会把裸写的 `schemas/x.json`
        解析到**技能目录下**的 schemas/ 并要求文件存在，因此裸写必然失败；
        正确形式是 `../../schemas/...`（SKILL.md 层）或 `../../../schemas/...`（子目录层）。
        """
        offenders = []
        for fp in SKILL.rglob("*.md"):
            text = fp.read_text(encoding="utf-8")
            for m in re.finditer(r"`schemas/research_debate_[a-z_]+\.schema\.json`", text):
                offenders.append("%s -> %s" % (fp.relative_to(REPO_ROOT), m.group(0).strip("`")))
        self.assertEqual(offenders, [], "schema 引用缺少相对路径前缀：%s" % offenders)


CANONICAL_SCHEMAS = {
    "research_debate_session.schema.json": "ResearchDebateSession",
    "research_debate_event.schema.json": "ResearchDebateEvent",
    "research_debate_gap.schema.json": "ResearchDebateGapRequest",
}


class TestSkillSchemas(unittest.TestCase):
    """仓库规范：skills/ 内不得存放 *.schema.json；canonical schema 位于根 schemas/。"""

    def test_no_local_schema_files_in_skills(self):
        local = [str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "skills").rglob("*.schema.json")]
        self.assertEqual(local, [], "skills/ 内不得出现 *.schema.json：%s" % local)

    def test_canonical_schemas_exist_and_are_2020_12(self):
        for name, title in CANONICAL_SCHEMAS.items():
            path = REPO_ROOT / "schemas" / name
            self.assertTrue(path.is_file(), "缺少 canonical schema：%s" % name)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data.get("title"), title)
            self.assertTrue(data.get("required"), "%s 未声明 required" % name)

    def test_token_not_allowed_as_hard_budget(self):
        """§7.2：token 只能是观测字段，不得出现在硬约束里。"""
        sess = json.loads((REPO_ROOT / "schemas" / "research_debate_session.schema.json")
                          .read_text(encoding="utf-8"))
        budget = sess["properties"]["execution"]["properties"]["budget"]
        self.assertNotIn("max_tokens", budget["properties"])
        self.assertFalse(budget.get("additionalProperties", True),
                         "budget 必须 additionalProperties=false，否则可塞入 token 字段")

    def test_skill_docs_reference_root_schemas(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in SKILL.rglob("*.md"))
        for name in CANONICAL_SCHEMAS:
            self.assertIn("schemas/%s" % name, text, "技能文档未引用 canonical schema %s" % name)


class TestValidatorBehavior(unittest.TestCase):
    """校验器必须在真实记录上报出违规，在合规样本上放行。"""

    def test_self_check_passes(self):
        code, out = _run_validator("--self-check")
        self.assertEqual(code, 0, out)
        self.assertIn("17/17", out)

    def test_specimen_has_no_violation(self):
        if not SPECIMEN.is_file():
            self.skipTest("规格样本不存在")
        code, out = _run_validator(str(SPECIMEN))
        self.assertEqual(code, 0, out)
        self.assertIn("无结构性违规", out)

    def test_live_session_violation_is_reported(self):
        if not LIVE_SESSION.is_file():
            self.skipTest("实跑记录不存在")
        code, out = _run_validator(str(LIVE_SESSION))
        self.assertEqual(code, 1, out)
        self.assertIn("[RD1]", out)          # 实跑当场暴露的违规
        self.assertIn("[RV15]", out)         # 新规则事后检出（旧记录用字面重合判分歧）
        self.assertIn("R3", out)

    def test_json_output_mode(self):
        if not SPECIMEN.is_file():
            self.skipTest("规格样本不存在")
        code, out = _run_validator(str(SPECIMEN), "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["violations"], [])
        self.assertIn("json_schema", data)

    def test_missing_file_returns_input_error(self):
        code, _ = _run_validator(str(SKILL / "no_such_session.json"))
        self.assertEqual(code, 2, "缺文件应返回输入错误码 2")


class TestSkillDeclaresRequiredRules(unittest.TestCase):
    """技能本体必须包含设计稿中容易被遗漏的硬规则，防止实现时丢失。"""

    def _all_text(self):
        return "\n".join(p.read_text(encoding="utf-8") for p in SKILL.rglob("*.md"))

    def test_role_question_type_mapping_present(self):
        text = self._all_text()
        for role, qtype in ROLE_QUESTION_TYPE.items():
            self.assertIn(role, text, "缺少 role_id：%s" % role)
            self.assertIn(qtype, text, "缺少 question_type：%s" % qtype)

    def test_p0_p6_ladder_present(self):
        text = (SKILL / "role" / "moderator.md").read_text(encoding="utf-8")
        for p in ("P0", "P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn("| %s |" % p, text, "调度阶梯缺少 %s" % p)

    def test_no_bundled_question_rule_and_counterexample(self):
        text = (SKILL / "references" / "dialogue_protocol.md").read_text(encoding="utf-8")
        self.assertIn("语义打包", text)
        self.assertIn("✗", text, "缺少真实违规的反例")

    def test_development_quota_scope_and_signals(self):
        text = (SKILL / "references" / "maturation_and_gates.md").read_text(encoding="utf-8")
        self.assertIn("才能进入 **P3**", text)
        self.assertIn("P2 前提审查与 P4 替代解释属生成性动作", text)
        for sig in ("INTUITION_FORMULATED", "QUESTION_SHARPENED", "PREMISE_SURFACED",
                    "DISCRIMINATION_ADDED"):
            self.assertIn(sig, text)
        self.assertIn("不计入", text)

    def test_high_divergence_no_vote_rule(self):
        text = (SKILL / "references" / "independent_review.md").read_text(encoding="utf-8")
        for phrase in ("投票", "取平均", "HIGH_DIVERGENCE", "不"):
            self.assertIn(phrase, text)

    def test_external_opinion_not_evidence(self):
        text = self._all_text()
        self.assertIn("external_opinion", text)
        self.assertIn("不作为证据", text)

    def test_context_never_upgraded_to_support(self):
        text = (SKILL / "references" / "evidence_handoff.md").read_text(encoding="utf-8")
        self.assertIn("禁止把 `CONTEXT` 当支持使用", text)
        self.assertIn("checked_scope", text)

    def test_no_fabricated_numbers_rule(self):
        text = self._all_text()
        self.assertIn("待补", text)
        self.assertIn("禁止伪造证据", text)

    def test_p3_precondition_for_validation_plan(self):
        text = (SKILL / "references" / "convergence_and_recovery.md").read_text(encoding="utf-8")
        self.assertIn("仅当本会话至少一次进入 P3", text)

    def test_independence_limit_is_declared(self):
        text = (SKILL / "references" / "independent_review.md").read_text(encoding="utf-8")
        self.assertIn("不保证知识来源独立", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
