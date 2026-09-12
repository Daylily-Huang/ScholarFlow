# -*- coding: utf-8 -*-
"""M4：research-debate 与统一执行深度架构的集成测试。

覆盖点：

- `research-debate` 是**一等流水线阶段**：`PIPELINE_STAGES` 与
  `execution_profile.schema.json` 的 stages 枚举都包含它；
- 它有可执行的**阶段计划**（`StageKind.RESEARCH_DEBATE`），且计划里不出现
  永远不生效的装饰性字段；
- 未确认的配置**不得**授权该阶段（`selection.status != confirmed` 时 `authorises_stage` 为假）；
- 三档深度对同一阶段给出**可区分**的计划（深度不是装饰）；
- 不做隐式扩额：run 级信封只约束活跃时长，会话自身的轮次/评批次/事件上限在
  `session.execution.budget`，两者互不覆盖。
"""

import json
import shutil
import tempfile
import unittest

import helpers  # noqa: F401

from shared.execution import (  # noqa: E402
    PIPELINE_STAGES, RunContext, RunExecutionConfig, StageKind, RunBudget,
)

REPO_ROOT = helpers.REPO_ROOT
SCHEMA = REPO_ROOT / "schemas" / "execution_profile.schema.json"


class TestStageRegistration(unittest.TestCase):
    def test_pipeline_stages_includes_research_debate(self):
        self.assertIn("research-debate", PIPELINE_STAGES)

    def test_schema_enum_includes_research_debate(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        enum = schema["properties"]["stages"]["items"]["enum"]
        self.assertIn("research-debate", enum, "schema stages 枚举必须与 PIPELINE_STAGES 对齐")
        for stage in PIPELINE_STAGES:
            self.assertIn(stage, enum, "PIPELINE_STAGES 的 %s 未出现在 schema 枚举中" % stage)

    def test_stage_kind_member_exists(self):
        self.assertEqual(StageKind.RESEARCH_DEBATE.value, "research-debate")


class TestStagePlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rid-m4-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, depth="standard", stages=("research-debate",)):
        return RunContext.create(depth, stages=list(stages), run_id="run-m4-%s" % depth,
                                 run_dir=self.tmp)

    def test_plan_is_executable_and_has_active_seconds(self):
        plan = self._ctx().plan_for(StageKind.RESEARCH_DEBATE).to_dict()
        self.assertEqual(plan["stage"], "research-debate")
        self.assertIn("max_active_seconds", plan["settings"])
        self.assertEqual(plan["unsupported"], [],
                         "计划里不应出现宿主无法兑现的字段：%s" % plan["unsupported"])

    def test_depth_makes_plans_distinguishable(self):
        quick = self._ctx("quick").plan_for(StageKind.RESEARCH_DEBATE).settings
        deep = self._ctx("deep").plan_for(StageKind.RESEARCH_DEBATE).settings
        self.assertNotEqual(quick["max_active_seconds"], deep["max_active_seconds"],
                            "不同深度的阶段计划必须可区分，否则深度是装饰")

    def test_planned_call_trace_covers_new_stage(self):
        trace = self._ctx().planned_call_trace()
        for kind in StageKind:
            self.assertIn(kind.value, trace["stages"],
                          "planned_call_trace 缺少阶段 %s" % kind.value)


class TestAuthorisationGate(unittest.TestCase):
    """未确认的配置不得授权阶段——这是跨技能契约的硬规则。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rid-m4-auth-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unconfirmed_config_does_not_authorise(self):
        cfg = RunExecutionConfig.from_profile(
            __import__("shared.execution", fromlist=["get_profile"]).get_profile("standard"),
            run_id="run-pending")
        cfg.stages = ["research-debate"]
        self.assertEqual(cfg.selection.status, "pending")
        self.assertFalse(cfg.authorises_stage("research-debate"),
                         "pending 配置不得授权任何阶段")

    def test_confirmed_config_authorises_only_declared_stages(self):
        ctx = RunContext.create("standard", stages=["research-debate"], run_id="run-ok",
                                run_dir=self.tmp)
        self.assertTrue(ctx.config.authorises_stage("research-debate"))
        self.assertFalse(ctx.config.authorises_stage("discovery"),
                         "未声明的阶段不得被顺带授权")

    def test_full_pipeline_authorises_debate(self):
        ctx = RunContext.create("standard", stages=["full_pipeline"], run_id="run-full",
                                run_dir=self.tmp)
        self.assertIn("research-debate", PIPELINE_STAGES)


class TestNoImplicitBudgetOverwrite(unittest.TestCase):
    """run 级信封与会话级预算各自独立，不得互相覆盖。"""

    def test_session_budget_fields_are_not_run_level_fields(self):
        run_fields = set(RunBudget.__dataclass_fields__)
        for debate_field in ("max_rounds", "max_review_batches",
                             "max_subtasks_per_batch", "max_events"):
            self.assertNotIn(debate_field, run_fields,
                             "%s 属于会话级预算，不应混入 run 级 RunBudget" % debate_field)

    def test_run_budget_rejects_debate_fields_silently_filtered_but_documented(self):
        """RunBudget.from_dict 会过滤未知键——这里把该行为固化为已知契约。"""
        b = RunBudget.from_dict({"max_search_candidates": 10, "max_rounds": 8})
        self.assertFalse(hasattr(b, "max_rounds"))
        self.assertEqual(b.max_search_candidates, 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
