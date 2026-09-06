"""Unit tests for ScholarFlow Stage 0 Adaptive Research Grill Engine."""

import unittest
from shared.grill_me.dimensions import (
    get_discovery_dimensions,
    get_extraction_dimensions,
    get_synthesis_dimensions,
)
from shared.grill_me.response_parser import (
    DimensionOption,
    DimensionResolution,
    GrillDimension,
    GrillEngine,
    GrillQuestion,
    GrillResponseParser,
    GrillState,
    PriorityTier,
    Provenance,
)


class TestGrillResponseParser(unittest.TestCase):
    def setUp(self):
        self.dim1 = GrillDimension(
            id="D1",
            name="研究目标与产出定位",
            priority=PriorityTier.CRITICAL,
            description="明确研究目标",
            options=[
                DimensionOption("A", "系统综述调研", is_recommended=True, rationale="全面覆盖", confidence="high", value="survey"),
                DimensionOption("B", "技术方案对比", is_recommended=False, rationale="方案评估", confidence="moderate", value="protocol"),
            ],
            default_key="A",
            default_value="survey",
        )
        self.dim2 = GrillDimension(
            id="D2",
            name="核心研究问题",
            priority=PriorityTier.CRITICAL,
            description="因果命题",
            options=[
                DimensionOption("A", "因果机制", is_recommended=True, rationale="深度研究", confidence="high", value="causal"),
                DimensionOption("B", "现状普查", is_recommended=False, rationale="描述性", confidence="moderate", value="survey"),
            ],
            default_key="A",
            default_value="causal",
        )
        self.dim3 = GrillDimension(
            id="D8",
            name="时间跨度",
            priority=PriorityTier.HIGH_IMPACT,
            description="时间范围",
            options=[
                DimensionOption("A", "近10年+经典追溯", is_recommended=True, rationale="兼顾前沿与历史", confidence="high", value="10y"),
                DimensionOption("B", "近5年极高前沿", is_recommended=False, rationale="最新突破", confidence="moderate", value="5y"),
            ],
            default_key="A",
            default_value="10y",
        )
        self.questions = [
            GrillQuestion(index=1, dimension=self.dim1, prompt="Q1: 研究目标"),
            GrillQuestion(index=2, dimension=self.dim2, prompt="Q2: 核心问题"),
            GrillQuestion(index=3, dimension=self.dim3, prompt="Q3: 时间跨度"),
        ]

    def test_is_all_recommended(self):
        affirmative_replies = [
            "按推荐", "全部按推荐", "全部推荐", "全选推荐",
            "all recommended", "accept all", "accept all recommended", "按建议", "全部按建议",
        ]
        for reply in affirmative_replies:
            self.assertTrue(GrillResponseParser.is_all_recommended(reply), f"Failed on: {reply}")

        negative_replies = [
            "1A 2B", "我想要补充", "不确定", "随便",
            "yes", "Y", "ok", "确认", "同意", "proceed", "全选A", "全A"
        ]
        for reply in negative_replies:
            self.assertFalse(GrillResponseParser.is_all_recommended(reply), f"Should not match: {reply}")

    def test_parse_all_recommended(self):
        res, unresolved = GrillResponseParser.parse("按推荐", self.questions)
        self.assertEqual(len(unresolved), 0)
        self.assertEqual(len(res), 3)
        self.assertEqual(res["D1"].selected_key, "A")
        self.assertEqual(res["D1"].provenance, Provenance.USER)
        self.assertEqual(res["D2"].selected_key, "A")
        self.assertEqual(res["D8"].selected_key, "A")

    def test_parse_indexed_choices(self):
        # Test compact indexed format: "1A 2B 3A"
        res, unresolved = GrillResponseParser.parse("1A 2B 3A", self.questions)
        self.assertEqual(len(unresolved), 0)
        self.assertEqual(res["D1"].selected_key, "A")
        self.assertEqual(res["D2"].selected_key, "B")
        self.assertEqual(res["D8"].selected_key, "A")

        # Test punctuation formats: "1.B, 2.A, 3.B"
        res2, unresolved2 = GrillResponseParser.parse("1.B, 2.A, 3.B", self.questions)
        self.assertEqual(res2["D1"].selected_key, "B")
        self.assertEqual(res2["D2"].selected_key, "A")
        self.assertEqual(res2["D8"].selected_key, "B")

        # Test Chinese style: "1选A 2选B 3按推荐"
        res3, unresolved3 = GrillResponseParser.parse("1选A 2选B 3按推荐", self.questions)
        self.assertEqual(res3["D1"].selected_key, "A")
        self.assertEqual(res3["D2"].selected_key, "B")
        self.assertEqual(res3["D8"].selected_key, "A")

    def test_parse_bare_letters(self):
        res, unresolved = GrillResponseParser.parse("A B A", self.questions)
        self.assertEqual(len(unresolved), 0)
        self.assertEqual(res["D1"].selected_key, "A")
        self.assertEqual(res["D2"].selected_key, "B")
        self.assertEqual(res["D8"].selected_key, "A")

    def test_parse_custom_override(self):
        res, unresolved = GrillResponseParser.parse("1按推荐 2选A 3自定义：仅限2022-2024年临床数据", self.questions)
        self.assertEqual(len(unresolved), 0)
        self.assertEqual(res["D1"].selected_key, "A")
        self.assertEqual(res["D2"].selected_key, "A")
        self.assertEqual(res["D8"].selected_key, "CUSTOM")
        self.assertIn("2022-2024", res["D8"].selected_label)
        self.assertEqual(res["D8"].provenance, Provenance.USER)

    def test_unresolved_critical(self):
        # User only answers question 3 (HIGH_IMPACT), leaving critical D1 & D2 unresolved
        res, unresolved = GrillResponseParser.parse("3选A", self.questions)
        self.assertIn("D1", unresolved)
        self.assertIn("D2", unresolved)
        self.assertNotIn("D8", unresolved)


class TestGrillEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="biomedical")
        self.engine.register_dimensions(get_discovery_dimensions())

    def test_question_selection_budget_and_priority(self):
        # Should select at most MAX_QUESTIONS_PER_ROUND (5)
        questions = self.engine.select_questions("请帮我进行CRISPR前沿研究调研")
        self.assertLessEqual(len(questions), 5)
        self.assertGreaterEqual(len(questions), 3)

        # All selected questions should be CRITICAL or HIGH_IMPACT
        priorities = [q.dimension.priority for q in questions]
        self.assertTrue(all(p in (PriorityTier.CRITICAL, PriorityTier.HIGH_IMPACT) for p in priorities))

        # DEFAULTABLE dimensions should be silently defaulted in resolutions
        for dim_id in ["D10", "D11", "D12", "D13", "D14"]:
            self.assertIn(dim_id, self.engine.resolutions)
            self.assertEqual(self.engine.resolutions[dim_id].provenance, Provenance.DEFAULTED)

    def test_inferred_values_bypass_question_slots(self):
        inferred = {
            "D1": "开题综述调研",
            "D2": "CRISPR脱靶效应因果机制",
            "D8": "2020-2024",
        }
        questions = self.engine.select_questions("已明确只要开题综述", inferred_values=inferred)
        question_dim_ids = [q.dimension.id for q in questions]
        # Inferred dimensions should NOT be re-asked
        self.assertNotIn("D1", question_dim_ids)
        self.assertNotIn("D2", question_dim_ids)
        self.assertNotIn("D8", question_dim_ids)
        # And they should be recorded as INFERRED
        self.assertEqual(self.engine.resolutions["D1"].provenance, Provenance.INFERRED)

    def test_happy_path_fast_reply(self):
        self.engine.select_questions("调研mRNA疫苗中和抗体反应")
        state, payload = self.engine.submit_response("按推荐")
        self.assertEqual(state, GrillState.STAGE0_CONFIRMED)
        self.assertEqual(payload["status"], "CONFIRMED")
        self.assertIn("# Stage 0 Protocol Snapshot", payload["snapshot"])
        self.assertIn("[USER]", payload["snapshot"])
        self.assertIn("[DEFAULTED]", payload["snapshot"])

    def test_multi_round_and_exhaustion(self):
        # Round 1: user provides ambiguous answer that leaves critical dimensions unresolved
        self.engine.select_questions("调研某新药物疗效")
        state, payload = self.engine.submit_response("随便，先看看")
        # Should require Round 2 because Criticals are unresolved
        self.assertEqual(state, GrillState.STAGE0_ROUND2)
        self.assertEqual(payload["status"], "ROUND2_REQUIRED")
        self.assertEqual(self.engine.round, 2)

        # Round 2: user still gives invalid response -> engine applies safe defaults upon exhaustion
        state2, payload2 = self.engine.submit_response("还是不确定")
        self.assertEqual(state2, GrillState.STAGE0_CONFIRMED)
        self.assertEqual(payload2["status"], "CONFIRMED_WITH_WARNING")
        self.assertIn("SYSTEM_RULE", payload2["snapshot"])

    def test_headless_bypass(self):
        engine = GrillEngine(skill_name="literature-evidence-extraction", domain="biomedical")
        engine.register_dimensions(get_extraction_dimensions())
        params = {
            "E1": "meta_analysis_params",
            "E2": "fulltext_pdf",
            "E3": "general_empirical_v1",
            "E4": "fine_grained_assay",
        }
        state, snapshot = engine.bypass_headless(params)
        self.assertEqual(state, GrillState.STAGE0_BYPASSED)
        self.assertIn("STAGE0_BYPASSED", snapshot)
        self.assertIn("[USER]", snapshot)


class TestPresetDimensionsIntegrity(unittest.TestCase):
    def test_discovery_dimensions(self):
        dims = get_discovery_dimensions()
        self.assertEqual(len(dims), 14)
        dim_ids = [d.id for d in dims]
        for i in range(1, 15):
            self.assertIn(f"D{i}", dim_ids)

        for d in dims:
            self.assertIsNotNone(d.get_recommended_option(), f"{d.id} missing recommended option")
            rec = d.get_recommended_option()
            self.assertTrue(len(rec.rationale) > 0, f"{d.id} recommended option missing rationale")
            self.assertIn(rec.confidence, ("high", "moderate", "low"))

    def test_extraction_dimensions(self):
        dims = get_extraction_dimensions()
        self.assertEqual(len(dims), 9)
        dim_ids = [d.id for d in dims]
        for i in range(1, 10):
            self.assertIn(f"E{i}", dim_ids)

        for d in dims:
            rec = d.get_recommended_option()
            self.assertIsNotNone(rec, f"{d.id} missing recommended option")
            self.assertTrue(len(rec.rationale) > 0)

    def test_synthesis_dimensions(self):
        dims = get_synthesis_dimensions()
        self.assertEqual(len(dims), 11)
        dim_ids = [d.id for d in dims]
        for i in range(1, 12):
            self.assertIn(f"S{i}", dim_ids)

        for d in dims:
            rec = d.get_recommended_option()
            self.assertIsNotNone(rec, f"{d.id} missing recommended option")
            self.assertTrue(len(rec.rationale) > 0)


if __name__ == "__main__":
    unittest.main()
