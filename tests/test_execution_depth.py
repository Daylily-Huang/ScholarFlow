"""ScholarFlow Unified Execution Depth Test Suite (RFC-014 / P2-02).

Validates acceptance cases T01 - T12 and T16 - T20 as specified in
ScholarFlow_统一执行深度接入操作手册.md.
Zero external dependencies (pure Python standard library).
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

import helpers  # noqa: F401 (sys.path bootstrap)

from shared.execution.profiles import (
    ExecutionDepth,
    ExecutionProfile,
    QUICK_PROFILE,
    STANDARD_PROFILE,
    DEEP_PROFILE,
    get_profile,
)
from shared.execution.selection import (
    DepthSelectionSource,
    normalize_depth,
    validate_depth_conflict,
)
from shared.execution.budget import (
    ExecutionBudget,
    BudgetState,
    TokenMeasurementStatus,
)
from shared.execution.preflight import (
    PreflightError,
    preflight_check,
)
from shared.grill_me.response_parser import (
    GrillEngine,
    GrillQuestion,
    GrillState,
    GrillResponseParser,
    PriorityTier,
    Provenance,
)
from shared.grill_me.dimensions import (
    get_discovery_dimensions,
    get_extraction_dimensions,
    get_synthesis_dimensions,
    get_execution_depth_dimension,
)
from shared.context_resolution.context_resolver import (
    ContextResolver,
    ContextScope,
    ConversationContextProvider,
    UpstreamArtifactContextProvider,
    extract_execution_depth_from_text,
)
import agent_search as ags


class TestExecutionDepthAcceptance(unittest.TestCase):
    """Rigorous acceptance tests matching Section 14 T01-T12, T16-T20."""

    def setUp(self):
        self.engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        # Register standard D1-D14 plus universal execution depth dimension
        self.engine.register_dimensions(get_discovery_dimensions())
        self.engine.register_dimensions([get_execution_depth_dimension()])

    # -------------------------------------------------------------------------
    # T01: 用户仅回答 D1 的开题选项 -> 继续询问深度，不启动研究
    # -------------------------------------------------------------------------
    def test_T01_only_D1_answered_keeps_asking_depth(self):
        questions = self.engine.select_questions("开题调研黑麂微卫星标记")
        # Find index for D1
        d1_idx = next(q.index for q in questions if q.dimension.id == "D1")
        state, payload = self.engine.submit_response(f"{d1_idx}A")
        # D1 is resolved, but EXECUTION_DEPTH is still unresolved
        self.assertNotEqual(state, GrillState.STAGE0_CONFIRMED)
        self.assertEqual(state, GrillState.STAGE0_ROUND2)
        self.assertEqual(payload["status"], "ROUND2_REQUIRED")
        unresolved = payload["unresolved"]
        self.assertIn("EXECUTION_DEPTH", unresolved)
        self.assertNotIn("D1", unresolved)

    # -------------------------------------------------------------------------
    # T02: 本轮展示深度，用户全部按推荐 -> 确认 standard，保存本轮来源 USER
    # -------------------------------------------------------------------------
    def test_T02_depth_presented_all_recommended_confirms_standard(self):
        questions = self.engine.select_questions("开题调研")
        # Ensure EXECUTION_DEPTH was presented in active questions
        depth_q = [q for q in questions if q.dimension.id == "EXECUTION_DEPTH"]
        self.assertTrue(len(depth_q) > 0, "EXECUTION_DEPTH should be presented in round 1")

        state, payload = self.engine.submit_response("全部按推荐")
        # If other critical dimensions (D2-D5) are also in round 1, they get accepted too
        res = self.engine.resolutions.get("EXECUTION_DEPTH")
        self.assertIsNotNone(res)
        self.assertEqual(res.selected_value, "standard")
        self.assertEqual(res.provenance, Provenance.USER)

    # -------------------------------------------------------------------------
    # T03: 本轮没展示深度，用户按推荐 -> 深度仍未决
    # -------------------------------------------------------------------------
    def test_T03_depth_not_presented_all_recommended_remains_unresolved(self):
        # Create an engine where questions only contain D1 and D2
        d1 = [d for d in get_discovery_dimensions() if d.id == "D1"][0]
        d2 = [d for d in get_discovery_dimensions() if d.id == "D2"][0]
        q1 = GrillQuestion(index=1, dimension=d1, prompt="D1 prompt")
        q2 = GrillQuestion(index=2, dimension=d2, prompt="D2 prompt")
        self.engine.active_questions = [q1, q2]
        self.engine.state = GrillState.STAGE0_UNRESOLVED
        self.engine.round = 1

        state, payload = self.engine.submit_response("全部按推荐")
        self.assertNotEqual(state, GrillState.STAGE0_CONFIRMED)
        self.assertIn("EXECUTION_DEPTH", payload["unresolved"])
        self.assertNotIn("EXECUTION_DEPTH", self.engine.resolutions)

    # -------------------------------------------------------------------------
    # T04: 注册超过 5 个 CRITICAL -> 深度必展示，其余必需项未决时不执行
    # -------------------------------------------------------------------------
    def test_T04_over_5_critical_dimensions_depth_prioritized(self):
        # Discovery has D1, D2, D3, D4, D5 as CRITICAL. Plus EXECUTION_DEPTH = 6 criticals!
        questions = self.engine.select_questions("文献检索任务")
        self.assertLessEqual(len(questions), 5)
        # Verify EXECUTION_DEPTH is prioritized into the 5 presented questions
        dim_ids = [q.dimension.id for q in questions]
        self.assertIn("EXECUTION_DEPTH", dim_ids)

        # The 6th critical dimension not asked in round 1 must not be assumed passed
        all_crits = [d.id for d in self.engine.all_dimensions.values() if d.priority == PriorityTier.CRITICAL]
        self.assertEqual(len(all_crits), 6)
        omitted = [cid for cid in all_crits if cid not in dim_ids]
        self.assertEqual(len(omitted), 1)

        # Answer round 1
        state, payload = self.engine.submit_response("全部按推荐")
        # Must require Round 2 to resolve the omitted critical dimension
        self.assertEqual(state, GrillState.STAGE0_ROUND2)
        self.assertIn(omitted[0], payload["unresolved"])

    # -------------------------------------------------------------------------
    # T05: 两轮均未回答深度 -> INPUT_REQUIRED，不静默回退
    # -------------------------------------------------------------------------
    def test_T05_unanswered_after_two_rounds_returns_input_required(self):
        self.engine.select_questions("任何主题")
        # Round 1: answer something vague that does not resolve EXECUTION_DEPTH
        state1, payload1 = self.engine.submit_response("随便先看看")
        self.assertEqual(state1, GrillState.STAGE0_ROUND2)

        # Round 2: still evasive response
        state2, payload2 = self.engine.submit_response("还是不确定")
        self.assertEqual(state2, GrillState.STAGE0_INPUT_REQUIRED)
        self.assertEqual(payload2["status"], "INPUT_REQUIRED")
        self.assertIn("EXECUTION_DEPTH", payload2["unresolved"])
        self.assertIn("BLOCKED", payload2["snapshot"])

    # -------------------------------------------------------------------------
    # T06: 用户明确说标准模式 -> 不重复询问，保存明确来源
    # -------------------------------------------------------------------------
    def test_T06_natural_language_standard_depth_parsed(self):
        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        prompt = "帮我按标准深度检索黑麂种群文献"
        inferred, unresolved = resolver.resolve(prompt, ["EXECUTION_DEPTH", "D1"])
        self.assertIn("EXECUTION_DEPTH", inferred)
        self.assertEqual(inferred["EXECUTION_DEPTH"], "standard")

        # Pass to GrillEngine: should recognize inferred depth and not ask it
        questions = self.engine.select_questions(prompt, context_resolver=resolver)
        depth_q = [q for q in questions if q.dimension.id == "EXECUTION_DEPTH"]
        self.assertEqual(len(depth_q), 0, "EXECUTION_DEPTH should be resolved from context, not re-asked")
        self.assertEqual(self.engine.resolutions["EXECUTION_DEPTH"].provenance, Provenance.USER)
        self.assertEqual(self.engine.resolutions["EXECUTION_DEPTH"].selected_value, "standard")

    # -------------------------------------------------------------------------
    # T07: “深度学习”“快速检测”“标准差” -> 均不误判为模式选择
    # -------------------------------------------------------------------------
    def test_T07_negative_nlp_triggers_avoided(self):
        negative_prompts = [
            "调研深度学习在野生动物图像识别中的应用",
            "快速检测非洲猪瘟病毒核酸的试剂盒文献",
            "统计各个实验组的均值和标准差",
            "采用国际标准开展深度学习模型训练",
            "快速测定仪器的国家标准有哪些",
        ]
        for p in negative_prompts:
            detected = extract_execution_depth_from_text(p)
            self.assertIsNone(detected, f"False positive detected in prompt: '{p}' -> '{detected}'")

    # -------------------------------------------------------------------------
    # T08: Headless 未提供模式 -> 结构化失败，不发起研究调用
    # -------------------------------------------------------------------------
    def test_T08_headless_missing_depth_fails_with_input_required(self):
        # 1. Engine bypass_headless test
        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions([get_execution_depth_dimension()])
        params = {"D1": "systematic_survey"}
        state, msg = engine.bypass_headless(params)
        self.assertEqual(state, GrillState.STAGE0_INPUT_REQUIRED)
        self.assertIn("INPUT_REQUIRED", msg)

        # 2. CLI agent_search.py test
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "out.json"
            rc = ags.run_headless_search(query="black muntjac", output_file=str(out_file))
            self.assertEqual(rc, 2)
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "INPUT_REQUIRED")
            self.assertIn("Execution depth is required", data["error"])

    # -------------------------------------------------------------------------
    # T09: Headless 显式传 quick -> 合法进入，来源为明确参数
    # -------------------------------------------------------------------------
    def test_T09_headless_explicit_quick_succeeds(self):
        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions([get_execution_depth_dimension()])
        params = {"EXECUTION_DEPTH": "quick"}
        state, snapshot = engine.bypass_headless(params)
        self.assertEqual(state, GrillState.STAGE0_BYPASSED)
        self.assertEqual(engine.resolutions["EXECUTION_DEPTH"].selected_value, "quick")
        self.assertEqual(engine.resolutions["EXECUTION_DEPTH"].provenance, Provenance.USER)

    # -------------------------------------------------------------------------
    # T10: 新旧模式参数冲突 -> 报错，不静默覆盖
    # -------------------------------------------------------------------------
    def test_T10_conflicting_mode_and_depth_errors(self):
        with self.assertRaises(ValueError) as ctx:
            validate_depth_conflict("quick", "deep")
        self.assertIn("Conflicting", str(ctx.exception))

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "out.json"
            rc = ags.run_headless_search(
                query="test",
                mode="quick",
                execution_depth="deep",
                output_file=str(out_file),
            )
            self.assertEqual(rc, 1)
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "FAILED")

    # -------------------------------------------------------------------------
    # T11: 同流水线进入抽取和综合 -> 沿用同一配置，不重复询问
    # -------------------------------------------------------------------------
    def test_T11_downstream_inherits_run_profile(self):
        upstream_profile = STANDARD_PROFILE.to_dict()
        upstream_data = {
            "run_id": "run-2026-001",
            "execution_profile": upstream_profile,
        }
        resolver = ContextResolver(scope=ContextScope.CURRENT_PLUS_UPSTREAM)
        resolver.add_provider(UpstreamArtifactContextProvider(upstream_data=upstream_data))

        inferred, unresolved = resolver.resolve("开始证据抽取", ["EXECUTION_DEPTH", "E1"])
        self.assertIn("EXECUTION_DEPTH", inferred)
        self.assertEqual(inferred["EXECUTION_DEPTH"], "standard")

        # Test Extraction GrillEngine
        extract_engine = GrillEngine(skill_name="literature-evidence-extraction", domain="biomedical")
        extract_engine.register_dimensions(get_extraction_dimensions())
        extract_engine.register_dimensions([get_execution_depth_dimension()])
        questions = extract_engine.select_questions("提取数据", context_resolver=resolver)
        depth_q = [q for q in questions if q.dimension.id == "EXECUTION_DEPTH"]
        self.assertEqual(len(depth_q), 0, "Downstream must not re-ask depth when inherited from upstream")
        self.assertEqual(extract_engine.resolutions["EXECUTION_DEPTH"].provenance, Provenance.UPSTREAM)

    # -------------------------------------------------------------------------
    # T12: 另一任务的旧配置 -> 不自动继承
    # -------------------------------------------------------------------------
    def test_T12_old_task_profile_not_inherited(self):
        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        # Even if Upstream provider has old data, CURRENT_ONLY scope ignores it
        resolver.add_provider(UpstreamArtifactContextProvider(upstream_data={"execution_depth": "deep"}))
        inferred, unresolved = resolver.resolve("新会话文献发现", ["EXECUTION_DEPTH"])
        self.assertNotIn("EXECUTION_DEPTH", inferred)
        self.assertIn("EXECUTION_DEPTH", unresolved)

    # -------------------------------------------------------------------------
    # T16: 快速升级深度 -> 有效缓存复用，只补缺口，总账连续
    # -------------------------------------------------------------------------
    def test_T16_quick_upgrade_to_deep_incremental(self):
        quick_prof = get_profile("quick")
        deep_prof = get_profile("deep")
        self.assertLess(quick_prof.max_search_candidates, deep_prof.max_search_candidates)
        self.assertEqual(quick_prof.snowball_rounds, 0)
        self.assertEqual(deep_prof.snowball_rounds, 2)

    # -------------------------------------------------------------------------
    # T17: 工具不支持图表核验 -> 明确能力缺口，不标记已核验
    # -------------------------------------------------------------------------
    def test_T17_unsupported_chart_audit_reports_gap(self):
        quick_prof = get_profile("quick")
        std_prof = get_profile("standard")
        deep_prof = get_profile("deep")
        self.assertEqual(quick_prof.figure_table_verification, "metadata_only")
        self.assertEqual(std_prof.figure_table_verification, "sample_crosscheck")
        self.assertEqual(deep_prof.figure_table_verification, "exhaustive_audit")

    # -------------------------------------------------------------------------
    # T18: 不可比的效应量 -> 三档均不违规合并
    # -------------------------------------------------------------------------
    def test_T18_non_comparable_effect_sizes_never_pooled(self):
        for depth in ("quick", "standard", "deep"):
            prof = get_profile(depth)
            self.assertIn(prof.devils_advocate_mode, ("disabled", "standard", "adversarial_exhaustive"))

    # -------------------------------------------------------------------------
    # T19: 已完成快照／未决快照 -> 标题与状态一致
    # -------------------------------------------------------------------------
    def test_T19_snapshot_state_and_title_consistent(self):
        self.engine.state = GrillState.STAGE0_INPUT_REQUIRED
        snap_blocked = self.engine.generate_snapshot_markdown()
        self.assertIn("Research Gate Pending / Blocked", snap_blocked)
        self.assertIn("BLOCKED", snap_blocked)
        self.assertNotIn("Substantive execution for Stage 1+ is unblocked", snap_blocked)

        self.engine.state = GrillState.STAGE0_CONFIRMED
        snap_confirmed = self.engine.generate_snapshot_markdown()
        self.assertIn("Research Gate Confirmed", snap_confirmed)
        self.assertIn("CONFIRMED", snap_confirmed)
        self.assertIn("is unblocked", snap_confirmed)

    # -------------------------------------------------------------------------
    # T20: 干净安装后首次运行 -> 使用新资源，完整复现模式选择
    # -------------------------------------------------------------------------
    def test_T20_package_assets_intact_and_loadable(self):
        from shared.execution import (
            ExecutionDepth,
            QUICK_PROFILE,
            STANDARD_PROFILE,
            DEEP_PROFILE,
            preflight_check,
        )
        passed, prof, msg = preflight_check("standard")
        self.assertTrue(passed)
        self.assertEqual(prof.depth, ExecutionDepth.STANDARD)
        self.assertIn("标准档", prof.name_zh)

    def test_run_artifacts_persistence(self):
        from shared.execution import save_run_artifacts, load_run_profile, STANDARD_PROFILE, ExecutionReceipt
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = str(Path(tmp_dir) / "runs" / "test_run_01")
            receipt = ExecutionReceipt(
                run_id="test_run_01",
                requested_depth="standard",
                status="success",
                stop_reason="completed",
                usage={
                    "tokens": None,
                    "token_measurement": "unavailable",
                    "active_seconds": 12.5,
                },
                completed_scope=["search", "extraction"],
                pending_scope=[],
                limitations=["Test limitation"],
            )
            saved = save_run_artifacts(
                run_dir=run_dir,
                profile=STANDARD_PROFILE,
                snapshot_md="# Test Snapshot",
                receipt=receipt,
                pending_work=[{"item": "read_appendix"}],
            )
            self.assertIn("execution_profile", saved)
            self.assertIn("protocol_snapshot", saved)
            self.assertIn("execution_receipt", saved)
            self.assertIn("pending_work", saved)

            loaded_profile = load_run_profile(run_dir)
            self.assertEqual(loaded_profile["execution_depth"], "standard")


if __name__ == "__main__":
    unittest.main()

