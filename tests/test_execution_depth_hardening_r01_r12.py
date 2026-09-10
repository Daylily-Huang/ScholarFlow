# -*- coding: utf-8 -*-
"""
test_execution_depth_hardening_r01_r12.py
-----------------------------------------
Regression suite for the 2026-09-10 execution-depth implementation review.

Every test here corresponds to a defect (R01-R12) that was reproduced against
commit 2c54c02 and documented in
``docs/implementation/ScholarFlow_执行深度实现审查与详细修改建议_2026-09-10.md``.

The intent is that deleting or bypassing the corresponding production code
makes these tests fail -- unlike the configuration-only assertions they replace.

Pure Python standard library (zero external runtime dependencies).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import tests.helpers as helpers
from tests.schema_helpers import validate_payload, JSONSCHEMA_AVAILABLE


# ---------------------------------------------------------------------------
# R01: natural-language depth intent must not be misread as a confirmation
# ---------------------------------------------------------------------------
class TestR01DepthIntentClassification(unittest.TestCase):
    """R01: negation / question / quotation / conditional must never confirm."""

    def setUp(self):
        from shared.context_resolution.context_resolver import (
            classify_execution_depth_intent,
            extract_execution_depth_from_text,
            DepthIntent,
        )
        self.classify = classify_execution_depth_intent
        self.extract = extract_execution_depth_from_text
        self.DepthIntent = DepthIntent

    def _assert_resolves_to(self, text, expected_value):
        result = self.classify(text)
        self.assertTrue(
            result.intent.is_confirmable,
            "%r should resolve to %r but was classified %s (%s)"
            % (text, expected_value, result.intent.value, result.reason),
        )
        self.assertEqual(result.value, expected_value, "for %r" % text)
        self.assertEqual(self.extract(text), expected_value, "for %r" % text)

    def _assert_not_confirmable(self, text, expected_intent=None):
        result = self.classify(text)
        self.assertFalse(
            result.intent.is_confirmable,
            "%r must not confirm a depth but was classified %s" % (text, result.intent.value),
        )
        self.assertIsNone(result.value, "for %r" % text)
        self.assertIsNone(self.extract(text), "for %r" % text)
        if expected_intent is not None:
            self.assertEqual(result.intent, expected_intent, "for %r" % text)

    # --- the four rows of the review document's R01 table -------------------
    def test_negation_is_not_a_confirmation(self):
        self._assert_not_confirmable("不要用深度模式", self.DepthIntent.NEGATED)

    def test_question_is_not_a_confirmation(self):
        self._assert_not_confirmable("深度模式是什么意思", self.DepthIntent.QUESTION)

    def test_quotation_is_not_a_confirmation(self):
        self._assert_not_confirmable(
            "论文中写着“采用深度模式”", self.DepthIntent.QUOTED
        )

    def test_explicit_correction_uses_last_value(self):
        self._assert_resolves_to("先用快速模式，不，改用深度模式", "deep")

    # --- additional acceptance cases required by the review -----------------
    def test_assistant_recommendation_is_not_a_user_decision(self):
        self._assert_not_confirmable("建议深度模式")

    def test_user_discussing_whether_to_use_depth(self):
        self._assert_not_confirmable("是否需要深度模式")

    def test_conditional_without_commitment_is_not_a_decision(self):
        self._assert_not_confirmable("如果时间够就用深度档")

    def test_conditional_with_separate_commitment_is_a_decision(self):
        self._assert_resolves_to("如果时间够就用深度档。请你用深度档。", "deep")

    def test_conflicting_tiers_without_correction_stay_ambiguous(self):
        self._assert_not_confirmable("用深度档还是标准档", self.DepthIntent.AMBIGUOUS)
        self._assert_not_confirmable("深度模式或快速模式", self.DepthIntent.AMBIGUOUS)

    def test_unqualified_tier_words_are_not_selections(self):
        # Without a tier suffix or command prefix these are prose, not choices.
        self._assert_not_confirmable("先快速，后深度", self.DepthIntent.NONE)

    def test_quoted_text_with_internal_comma_is_not_a_decision(self):
        self._assert_not_confirmable("论文中写着“采用深度模式，但样本少”")

    def test_switch_verb_overrides_negated_tier(self):
        self._assert_resolves_to("不要用标准档，改用快速档", "quick")
        self._assert_resolves_to("这次不用深度，换成快速", "quick")

    def test_affirmative_selections_still_work(self):
        for text, expected in (
            ("用深度模式", "deep"),
            ("标准档", "standard"),
            ("快速模式", "quick"),
            ("中等", "standard"),
            ("这次用深度模式", "deep"),
            ("我选深度档", "deep"),
            ("帮我按标准深度检索黑麂种群文献", "standard"),
            ("请帮我针对KV-Cache开展检索，用深度档", "deep"),
        ):
            self._assert_resolves_to(text, expected)

    def test_domain_false_positives_are_ignored(self):
        for text in (
            "采用国际标准开展深度学习模型训练",
            "统计各个实验组的均值和标准差",
            "快速检测非洲猪瘟病毒核酸的试剂盒文献",
            "快速测定仪器的国家标准有哪些",
            "中等收入国家的文献",
            "快速发展的领域",
            "深度访谈方法",
            "按推荐",
        ):
            self._assert_not_confirmable(text, self.DepthIntent.NONE)

    def test_result_exposes_auditable_fields(self):
        result = self.classify("不要用深度模式")
        payload = result.to_dict()
        for key in ("intent", "value", "source", "scope", "ambiguity", "candidates", "reason"):
            self.assertIn(key, payload)
        self.assertEqual(payload["source"], "current_user")
        self.assertEqual(payload["scope"], "current_run")
        self.assertTrue(payload["reason"])

    # --- conversation history must only trust genuine user turns -----------
    def test_assistant_turn_is_not_treated_as_user_selection(self):
        from shared.context_resolution.context_resolver import ContextResolver, ContextScope

        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        resolver.add_provider(
            _conversation_provider(
                [
                    {"role": "assistant", "content": "建议采用深度模式"},
                    {"role": "assistant", "content": "深度模式是指更彻底的检索"},
                ]
            )
        )
        inferred, _ = resolver.resolve("开始吧", ["EXECUTION_DEPTH"])
        self.assertNotIn(
            "EXECUTION_DEPTH",
            inferred,
            "an assistant recommendation must not resolve the depth dimension",
        )

    def test_negated_user_turn_is_not_treated_as_selection(self):
        from shared.context_resolution.context_resolver import ContextResolver, ContextScope

        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        resolver.add_provider(
            _conversation_provider([{"role": "user", "content": "不要用深度模式"}])
        )
        inferred, _ = resolver.resolve("开始吧", ["EXECUTION_DEPTH"])
        self.assertNotIn("EXECUTION_DEPTH", inferred)

    def test_affirmative_user_turn_is_inherited(self):
        from shared.context_resolution.context_resolver import ContextResolver, ContextScope

        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        resolver.add_provider(
            _conversation_provider([{"role": "user", "content": "用深度模式"}])
        )
        inferred, _ = resolver.resolve("开始吧", ["EXECUTION_DEPTH"])
        self.assertEqual(inferred.get("EXECUTION_DEPTH"), "deep")


# ---------------------------------------------------------------------------
# R02: the Grill gate must validate legality and provenance, not mere presence
# ---------------------------------------------------------------------------
class TestR02GateValidation(unittest.TestCase):
    """R02: invalid values and inferred values must not unlock a closed dimension."""

    def _engine(self):
        from shared.grill_me.response_parser import GrillEngine
        from shared.grill_me.dimensions import get_execution_depth_dimension

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions([get_execution_depth_dimension()])
        return engine

    def _value(self, engine):
        resolution = engine.resolutions.get("EXECUTION_DEPTH")
        return resolution.selected_value if resolution else None

    def test_invalid_interactive_value_does_not_confirm(self):
        for answer in ("1 zzz", "1 banana", "1 zzz 2 zzz", "1: banana", "1:2"):
            engine = self._engine()
            engine.select_questions("开始检索")
            state, payload = engine.submit_response(answer)
            self.assertNotEqual(
                state,
                __import__("shared.grill_me.response_parser", fromlist=["GrillState"]).GrillState.STAGE0_CONFIRMED,
                "%r must not confirm the gate" % answer,
            )
            self.assertIsNone(self._value(engine), "for %r" % answer)

    def test_invalid_interactive_value_is_reported_as_field_error(self):
        engine = self._engine()
        engine.select_questions("开始检索")
        state, payload = engine.submit_response("1: banana")
        self.assertEqual(payload["status"], "INVALID_SELECTION")
        self.assertEqual(payload["invalid_selections"], {"EXECUTION_DEPTH": "banana"})

    def test_blank_value_does_not_confirm(self):
        engine = self._engine()
        engine.select_questions("开始检索")
        state, payload = engine.submit_response("1   ")
        from shared.grill_me.response_parser import GrillState

        self.assertNotEqual(state, GrillState.STAGE0_CONFIRMED)

    def test_valid_tiers_and_chinese_aliases_confirm(self):
        from shared.grill_me.response_parser import GrillState

        for answer, expected in (
            ("1A", "standard"),
            ("1B", "quick"),
            ("1C", "deep"),
            ("1 深度", "deep"),
            ("1 中等", "standard"),
            ("1 快速", "quick"),
            ("1: 标准", "standard"),
        ):
            engine = self._engine()
            engine.select_questions("开始检索")
            state, _ = engine.submit_response(answer)
            self.assertEqual(state, GrillState.STAGE0_CONFIRMED, "for %r" % answer)
            self.assertEqual(self._value(engine), expected, "for %r" % answer)

    def test_headless_invalid_value_blocks(self):
        from shared.grill_me.response_parser import GrillState
        from shared.grill_me.dimensions import get_discovery_dimensions

        for invalid in ("banana", "zzz", "", "   "):
            engine = self._engine()
            engine.register_dimensions(get_discovery_dimensions())
            state, message = engine.bypass_headless(
                {"D1": "systematic_survey", "EXECUTION_DEPTH": invalid}
            )
            self.assertEqual(state, GrillState.STAGE0_INPUT_REQUIRED, "for %r" % invalid)
            self.assertIn("INPUT_REQUIRED", message)

    def test_headless_valid_values_bypass(self):
        from shared.grill_me.response_parser import GrillState
        from shared.grill_me.dimensions import get_discovery_dimensions

        for valid, expected in (("deep", "deep"), ("深度", "deep"), ("standard", "standard")):
            engine = self._engine()
            engine.register_dimensions(get_discovery_dimensions())
            state, _ = engine.bypass_headless(
                {"D1": "systematic_survey", "EXECUTION_DEPTH": valid}
            )
            self.assertEqual(state, GrillState.STAGE0_BYPASSED, "for %r" % valid)
            self.assertEqual(self._value(engine), expected, "for %r" % valid)

    def test_inferred_value_is_only_a_recommendation(self):
        engine = self._engine()
        questions = engine.select_questions("开始检索", inferred_values={"EXECUTION_DEPTH": "deep"})
        ids = [q.dimension.id for q in questions]
        self.assertIn(
            "EXECUTION_DEPTH",
            ids,
            "an inferred depth must not silently unlock the closed dimension",
        )
        state, _ = engine.submit_response("1A")
        from shared.grill_me.response_parser import GrillState

        self.assertEqual(state, GrillState.STAGE0_CONFIRMED)
        self.assertEqual(self._value(engine), "standard")

    def test_free_text_still_allowed_for_open_dimensions(self):
        from shared.grill_me.response_parser import (
            GrillResponseParser,
            GrillDimension,
            GrillQuestion,
            PriorityTier,
            DimensionOption,
        )

        dimension = GrillDimension(
            id="D8",
            name="时间跨度",
            priority=PriorityTier.CRITICAL,
            description="时间范围",
            options=[DimensionOption("A", "近10年", is_recommended=True, value="recent_10y")],
            default_key="A",
            default_value="recent_10y",
        )
        question = GrillQuestion(index=1, dimension=dimension, prompt="时间跨度")
        resolutions, _unresolved = GrillResponseParser.parse(
            "1: 仅限2022-2024年临床数据", [question]
        )
        self.assertEqual(resolutions["D8"].selected_key, "CUSTOM")
        self.assertIn("2022-2024", resolutions["D8"].selected_label)


# ---------------------------------------------------------------------------
# R08: a blocked run must be resumable instead of unusable
# ---------------------------------------------------------------------------
class TestR08ResumeAfterInputRequired(unittest.TestCase):
    """R08: ``STAGE0_INPUT_REQUIRED`` must accept a valid follow-up answer."""

    def _blocked_engine(self):
        from shared.grill_me.response_parser import GrillEngine
        from shared.grill_me.dimensions import get_execution_depth_dimension

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions([get_execution_depth_dimension()])
        engine.select_questions("开始检索")
        engine.submit_response("先随便说说")
        state, payload = engine.submit_response("还是没决定")
        return engine, state, payload

    def test_two_unanswered_rounds_block_the_run(self):
        from shared.grill_me.response_parser import GrillState

        engine, state, payload = self._blocked_engine()
        self.assertEqual(state, GrillState.STAGE0_INPUT_REQUIRED)
        self.assertEqual(payload["status"], "INPUT_REQUIRED")

    def test_blocked_run_accepts_a_valid_follow_up(self):
        from shared.grill_me.response_parser import GrillState

        engine, _state, _payload = self._blocked_engine()
        state, payload = engine.resume_input("1C")
        self.assertEqual(state, GrillState.STAGE0_CONFIRMED)
        self.assertEqual(payload["status"], "CONFIRMED")
        self.assertEqual(engine.resolutions["EXECUTION_DEPTH"].selected_value, "deep")

    def test_blocked_run_still_rejects_invalid_follow_up(self):
        from shared.grill_me.response_parser import GrillState

        engine, _state, _payload = self._blocked_engine()
        state, payload = engine.resume_input("1 banana")
        self.assertEqual(state, GrillState.STAGE0_INPUT_REQUIRED)
        self.assertEqual(payload["status"], "INVALID_SELECTION")

    def test_earlier_answers_survive_the_pause(self):
        from shared.grill_me.response_parser import GrillEngine, GrillState
        from shared.grill_me.dimensions import (
            get_discovery_dimensions,
            get_execution_depth_dimension,
        )

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions(get_discovery_dimensions() + [get_execution_depth_dimension()])
        questions = engine.select_questions("开始检索")
        # Round 1 asks EXECUTION_DEPTH first; answer a later question instead so
        # the depth dimension stays open while another answer is recorded.
        other = next(q for q in questions if q.dimension.id != "EXECUTION_DEPTH")
        other_id = other.dimension.id
        engine.submit_response("%dA" % other.index)
        answered_value = engine.resolutions[other_id].selected_value
        # Round 2 re-asks the depth dimension first; answer a later question again.
        state, _payload = engine.submit_response("2A")
        self.assertEqual(state, GrillState.STAGE0_INPUT_REQUIRED)
        engine.resume_input("1C")
        self.assertEqual(engine.resolutions[other_id].selected_value, answered_value)
        self.assertEqual(engine.resolutions["EXECUTION_DEPTH"].selected_value, "deep")

    def test_stale_question_set_binding_is_rejected(self):
        engine, _state, _payload = self._blocked_engine()
        with self.assertRaises(ValueError):
            engine.resume_input("1C", question_set_id="some-other-set")

    def test_matching_question_set_binding_is_accepted(self):
        from shared.grill_me.response_parser import GrillState

        engine, _state, payload = self._blocked_engine()
        state, _ = engine.resume_input("1C", question_set_id=payload["question_set_id"])
        self.assertEqual(state, GrillState.STAGE0_CONFIRMED)


# ---------------------------------------------------------------------------
# R03: headless entry points must not bypass the depth gate
# ---------------------------------------------------------------------------
class TestR03HeadlessEntryPoints(unittest.TestCase):
    """R03: invalid values and un-gated snowball must perform zero research calls."""

    def setUp(self):
        import agent_search

        self.ags = agent_search
        self.calls = []

        def _record(name):
            def _fn(*args, **kwargs):
                self.calls.append(name)
                if name == "query":
                    # Quick mode consumes the rich tuple container.
                    return agent_search.QueryExecutionResult([], None, meta={})
                if name == "snowball":
                    return [], []
                return [], {"errors": [], "reported_total_hits": 0, "rounds_executed": 1}

            return _fn

        self._saved = {
            "query": agent_search.query_openalex_headless,
            "standard": agent_search.run_standard_search,
            "deep": agent_search.run_deep_search,
            "snowball": agent_search.run_snowball_search,
        }
        agent_search.query_openalex_headless = _record("query")
        agent_search.run_standard_search = _record("standard")
        agent_search.run_deep_search = _record("deep")
        agent_search.run_snowball_search = _record("snowball")

    def tearDown(self):
        self.ags.query_openalex_headless = self._saved["query"]
        self.ags.run_standard_search = self._saved["standard"]
        self.ags.run_deep_search = self._saved["deep"]
        self.ags.run_snowball_search = self._saved["snowball"]

    def _run(self, **kwargs):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = self.ags.run_headless_search(output_file=str(out), **kwargs)
            payload = json.loads(out.read_text(encoding="utf-8"))
        return rc, payload

    def test_query_without_depth_blocks_with_zero_calls(self):
        rc, payload = self._run(query="topic")
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "INPUT_REQUIRED")
        self.assertEqual(self.calls, [])

    def test_query_with_invalid_depth_blocks_with_zero_calls(self):
        rc, payload = self._run(query="topic", execution_depth="banana")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "INVALID_PARAMETER")
        self.assertEqual(self.calls, [])

    def test_snowball_without_depth_blocks_with_zero_calls(self):
        rc, payload = self._run(snowball_seed="10.0/fake")
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "INPUT_REQUIRED")
        self.assertEqual(self.calls, [])

    def test_snowball_with_invalid_depth_blocks_with_zero_calls(self):
        rc, payload = self._run(snowball_seed="10.0/fake", execution_depth="banana")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "INVALID_PARAMETER")
        self.assertEqual(self.calls, [])

    def test_blank_and_whitespace_depths_block(self):
        for blank in ("", "   "):
            self.calls.clear()
            rc, payload = self._run(query="topic", execution_depth=blank)
            self.assertEqual(rc, 2, "for %r" % blank)
            self.assertEqual(self.calls, [], "for %r" % blank)

    def test_conflicting_mode_and_depth_blocks_with_zero_calls(self):
        rc, payload = self._run(query="topic", mode="quick", execution_depth="deep")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "INVALID_PARAMETER")
        self.assertEqual(self.calls, [])

    def test_valid_depths_do_run_exactly_once(self):
        for depth, expected_call in (
            ("quick", "query"),
            ("standard", "standard"),
            ("deep", "deep"),
            ("中等", "standard"),
            ("深度", "deep"),
        ):
            self.calls.clear()
            rc, payload = self._run(query="topic", execution_depth=depth)
            self.assertEqual(rc, 0, "for %r" % depth)
            self.assertEqual(self.calls, [expected_call], "for %r" % depth)
            expected_depth = {"query": "quick"}.get(expected_call, expected_call)
            self.assertEqual(
                payload["search_protocol"]["execution_depth"],
                expected_depth,
                "for %r" % depth,
            )

    def test_snowball_with_valid_depth_runs(self):
        rc, payload = self._run(snowball_seed="10.0/fake", execution_depth="standard")
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, ["snowball"])
        self.assertTrue(payload["search_protocol"]["is_snowball"])

    def test_error_payload_respects_the_discovery_contract(self):
        _rc, payload = self._run(query="topic", execution_depth="banana")
        self.assertIn("search_protocol", payload)
        self.assertIn("candidates", payload)
        self.assertEqual(payload["schema_version"], "1.1")

    def test_success_payload_respects_the_discovery_contract(self):
        _rc, payload = self._run(query="topic", execution_depth="standard")
        self.assertEqual(payload["search_protocol"]["mode"], "standard")
        self.assertIsInstance(payload["retrieval_coverage_ledger"], dict)
        self.assertIn("entries", payload["retrieval_coverage_ledger"])

    @unittest.skipUnless(JSONSCHEMA_AVAILABLE, "jsonschema is required for contract validation")
    def test_success_payload_validates_against_canonical_schema(self):
        _rc, payload = self._run(query="topic", execution_depth="standard")
        # Raises ValidationError on any contract violation.
        validate_payload(payload, "discovery_result.schema.json")

    @unittest.skipUnless(JSONSCHEMA_AVAILABLE, "jsonschema is required for contract validation")
    def test_error_payload_validates_against_canonical_schema(self):
        _rc, payload = self._run(query="topic", execution_depth="banana")
        validate_payload(payload, "discovery_result.schema.json")


# ---------------------------------------------------------------------------
# R04: one canonical run-configuration contract
# ---------------------------------------------------------------------------
class TestR04RunConfigContract(unittest.TestCase):
    """R04: presets round-trip, run configs validate, and the two stay distinct."""

    def setUp(self):
        from shared.execution import (
            ExecutionDepth,
            ExecutionProfile,
            RunExecutionConfig,
            STANDARD_PROFILE,
            preflight_check,
        )

        self.RunExecutionConfig = RunExecutionConfig
        self.STANDARD_PROFILE = STANDARD_PROFILE
        self.ExecutionProfile = ExecutionProfile
        self.ExecutionDepth = ExecutionDepth
        self.preflight_check = preflight_check

    # --- preset symmetry ---------------------------------------------------
    def test_preset_roundtrip_is_symmetric(self):
        for profile in (
            __import__("shared.execution", fromlist=["QUICK_PROFILE"]).QUICK_PROFILE,
            self.STANDARD_PROFILE,
            __import__("shared.execution", fromlist=["DEEP_PROFILE"]).DEEP_PROFILE,
        ):
            restored = self.ExecutionProfile.from_dict(profile.to_dict())
            self.assertEqual(restored, profile, "preset must round-trip exactly")

    def test_preset_rejects_unknown_fields(self):
        payload = self.STANDARD_PROFILE.to_dict()
        payload["mystery_field"] = 1
        with self.assertRaises(ValueError):
            self.ExecutionProfile.from_dict(payload)

    def test_preset_rejects_conflicting_depth_aliases(self):
        payload = self.STANDARD_PROFILE.to_dict()
        payload["execution_depth"] = "deep"
        with self.assertRaises(ValueError):
            self.ExecutionProfile.from_dict(payload)

    def test_preflight_accepts_enum_directly(self):
        passed, profile, _message = self.preflight_check(self.ExecutionDepth.STANDARD)
        self.assertTrue(passed)
        self.assertEqual(profile.depth, self.ExecutionDepth.STANDARD)

    def test_get_profile_rejects_unknown_value(self):
        from shared.execution import get_profile

        with self.assertRaises(ValueError):
            get_profile("nope")

    # --- run config --------------------------------------------------------
    def test_run_config_roundtrips(self):
        config = self.RunExecutionConfig.confirmed("standard", run_id="run-1")
        restored = self.RunExecutionConfig.from_dict(config.to_dict())
        self.assertEqual(restored.to_dict(), config.to_dict())

    def test_run_config_requires_valid_depth(self):
        with self.assertRaises(ValueError):
            self.RunExecutionConfig.confirmed("banana")

    def test_preset_cannot_impersonate_a_confirmed_run(self):
        config = self.RunExecutionConfig.from_profile(self.STANDARD_PROFILE, run_id="run-2")
        self.assertEqual(config.selection.status, "pending")
        self.assertFalse(config.is_confirmed)
        self.assertFalse(config.authorises_stage("discovery"))

    def test_confirmed_config_authorises_its_stages(self):
        config = self.RunExecutionConfig.confirmed("deep", run_id="run-3")
        self.assertTrue(config.is_confirmed)
        self.assertTrue(config.authorises_stage("extraction"))
        self.assertFalse(config.authorises_stage("unknown_stage"))

    def test_validate_reports_concrete_problems(self):
        config = self.RunExecutionConfig.confirmed("quick", run_id="run-4")
        config.budgets.max_search_candidates = 0
        config.enforcement = "whenever"
        problems = config.validate()
        self.assertTrue(any("max_search_candidates" in p for p in problems))
        self.assertTrue(any("enforcement" in p for p in problems))

    def test_confirmed_selection_must_match_depth(self):
        config = self.RunExecutionConfig.confirmed("deep", run_id="run-5")
        config.selection.selected_value = "quick"
        self.assertTrue(any("must match depth" in p for p in config.validate()))

    # --- persistence -------------------------------------------------------
    def test_save_then_load_roundtrips_through_disk(self):
        config = self.RunExecutionConfig.confirmed("standard", run_id="run-6")
        with tempfile.TemporaryDirectory() as td:
            saved = self.RunExecutionConfig.save(config, td)
            self.assertTrue(os.path.exists(saved))
            loaded = self.RunExecutionConfig.load(td)
        self.assertEqual(loaded.to_dict(), config.to_dict())

    def test_save_refuses_invalid_config(self):
        config = self.RunExecutionConfig.confirmed("standard", run_id="run-7")
        config.budgets.extraction_unit_limit = 0
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                self.RunExecutionConfig.save(config, td)
            self.assertFalse(os.path.exists(os.path.join(td, "execution_profile.json")))

    def test_load_rejects_corrupted_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "execution_profile.json"
            path.write_text(json.dumps({"run_id": "x", "depth": "standard"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.RunExecutionConfig.load(td)

    def test_legacy_flat_payload_converts_but_stays_pending(self):
        from shared.execution import save_run_artifacts

        legacy = self.STANDARD_PROFILE.to_dict()
        with tempfile.TemporaryDirectory() as td:
            save_run_artifacts(td, legacy)
            loaded = self.RunExecutionConfig.load(td)
        self.assertEqual(loaded.depth.value, "standard")
        self.assertFalse(
            loaded.is_confirmed,
            "an unconfirmed legacy payload must never be promoted to confirmed",
        )

    # --- schema congruence -------------------------------------------------
    def test_saved_config_validates_against_canonical_schema(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema is required for contract validation")
        config = self.RunExecutionConfig.confirmed("standard", run_id="run-8")
        validate_payload(config.to_dict(), "execution_profile.schema.json")

    def test_contract_document_example_validates_against_same_schema(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema is required for contract validation")
        import re as _re

        doc = (helpers.REPO_ROOT / "shared" / "core" / "cross_skill_contract.md").read_text(
            encoding="utf-8"
        )
        blocks = _re.findall(r"```json\n(.*?)\n```", doc, _re.S)
        examples = [b for b in blocks if "profile_version" in b]
        self.assertTrue(examples, "contract document must contain a canonical example")
        validate_payload(json.loads(examples[0]), "execution_profile.schema.json")

    def test_schema_rejects_unknown_fields(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema is required for contract validation")
        from tests.schema_helpers import get_validator

        validator = get_validator("execution_profile.schema.json")
        payload = self.RunExecutionConfig.confirmed("quick", run_id="run-9").to_dict()
        payload["surprise"] = True
        self.assertTrue(list(validator.iter_errors(payload)))

    def test_schema_rejects_invalid_budget(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema is required for contract validation")
        from tests.schema_helpers import get_validator

        validator = get_validator("execution_profile.schema.json")
        payload = self.RunExecutionConfig.confirmed("quick", run_id="run-10").to_dict()
        payload["budgets"] = dict(payload["budgets"])
        payload["budgets"]["max_active_seconds"] = 0
        self.assertTrue(list(validator.iter_errors(payload)))


# ---------------------------------------------------------------------------
# R05: budget and run artifacts must be wired into real execution
# ---------------------------------------------------------------------------
class TestR05RunContextWiring(unittest.TestCase):
    """R05: budgets and plans are consumed by the run, not merely declared."""

    def test_context_raises_when_model_budget_is_exhausted(self):
        from shared.execution import BudgetLimitError, RunContext

        ctx = RunContext.create("quick")
        # Shrink the usable allowance to two requests (10% is held back for a
        # clean finalisation).
        ctx.budget.requests_bucket.limit = 3
        ctx.budget.requests_bucket.closing_reserve = 1
        reservations = [ctx.begin_model_request() for _ in range(2)]
        for rid in reservations:
            ctx.end_model_request(rid, actual_tokens=10)
        with self.assertRaises(BudgetLimitError):
            ctx.begin_model_request()

    def test_database_requests_are_not_billed_as_model_requests(self):
        from shared.execution import RunContext

        ctx = RunContext.create("standard")
        ctx.count_database_request(3)
        ctx.count_database_request()
        self.assertEqual(ctx.database_requests, 4)
        self.assertEqual(ctx.budget.requests_bucket.used, 0)

    def test_finalize_persists_receipt_and_pending_work(self):
        from shared.execution import RunContext, StageKind

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.begin_stage(StageKind.DISCOVERY)
            ctx.defer_stage_work(StageKind.DISCOVERY, ["paper-7"])
            receipt = ctx.finalize()
            self.assertEqual(receipt.status, "partial")
            self.assertTrue((Path(td) / "execution_receipt.json").exists())
            self.assertTrue((Path(td) / "pending_work.json").exists())
            self.assertTrue((Path(td) / "usage_ledger.jsonl").exists())

    def test_resume_does_not_reset_consumed_budget(self):
        from shared.execution import RunContext

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.consume_candidates(15)
            ctx.finalize()
            resumed = RunContext.resume(td)
            self.assertEqual(resumed.candidates_processed, 15)
            self.assertEqual(resumed.remaining_candidates, 5)

    def test_different_depths_produce_different_plans(self):
        from shared.execution import RunContext

        quick = RunContext.create("quick").planned_call_trace()
        deep = RunContext.create("deep").planned_call_trace()
        self.assertNotEqual(
            quick["stages"]["discovery"]["settings"],
            deep["stages"]["discovery"]["settings"],
        )
        self.assertNotEqual(
            quick["stages"]["extraction"]["settings"],
            deep["stages"]["extraction"]["settings"],
        )

    def test_host_dependent_capabilities_are_reported_as_gaps(self):
        from shared.execution import RunContext

        plan = RunContext.create("deep").plan_for("synthesis")
        self.assertIn("devils_advocate_mode", plan.unsupported)

    def test_unauthorised_stage_is_refused(self):
        from shared.execution import RunContext
        from shared.execution.preflight import PreflightError

        ctx = RunContext.create("standard", stages=["discovery"])
        with self.assertRaises(PreflightError):
            ctx.begin_stage("extraction")

    def test_run_id_mismatch_is_refused_at_construction(self):
        from shared.execution import RunContext
        from shared.execution.config import RunExecutionConfig
        from shared.execution.preflight import PreflightError

        config = RunExecutionConfig.confirmed("standard", run_id="run-A")
        with self.assertRaises(PreflightError):
            RunContext(config, run_id="run-B")


# ---------------------------------------------------------------------------
# R11: candidate ceiling and real round reporting
# ---------------------------------------------------------------------------
class TestR11CandidateCeilingAndRoundReporting(unittest.TestCase):
    """R11: the run-level ceiling holds and reported rounds match reality."""

    def setUp(self):
        import agent_search

        self.ags = agent_search
        self._saved = {
            "query": agent_search.query_openalex_headless,
            "standard": agent_search.run_standard_search,
            "deep": agent_search.run_deep_search,
            "snowball": agent_search.run_snowball_search,
        }
        self._saved_snowball = agent_search.run_snowball_search

    def tearDown(self):
        self.ags.query_openalex_headless = self._saved["query"]
        self.ags.run_standard_search = self._saved["standard"]
        self.ags.run_deep_search = self._saved["deep"]
        self.ags.run_snowball_search = self._saved["snowball"]

    @staticmethod
    def _records(count, prefix="R"):
        return [
            {
                "record_id": "%s%03d" % (prefix, i),
                "title": "Record %d" % i,
                "doi": "10.0/%s%d" % (prefix, i),
                "source_databases": ["OpenAlex"],
            }
            for i in range(count)
        ]

    def _run(self, **kwargs):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = self.ags.run_headless_search(output_file=str(out), **kwargs)
            payload = json.loads(out.read_text(encoding="utf-8"))
        return rc, payload

    @staticmethod
    def _stub(records, queries=1, expansions=0, snowball=0):
        def _fn(*args, **kwargs):
            return records, {
                "errors": [],
                "reported_total_hits": len(records),
                "queries_executed": queries,
                "expansion_rounds_executed": expansions,
                "snowball_rounds_executed": snowball,
                "skipped_steps": [],
            }

        return _fn

    def test_run_level_candidate_ceiling_holds(self):
        # Standard ceiling is 50; a per-query fetch of 100 must be capped.
        self.ags.run_standard_search = self._stub(self._records(100))
        _rc, payload = self._run(query="topic", execution_depth="standard", limit=100)
        self.assertLessEqual(len(payload["candidates"]), 50)

    def test_over_ceiling_records_are_preserved_not_dropped(self):
        self.ags.run_standard_search = self._stub(self._records(80))
        _rc, payload = self._run(query="topic", execution_depth="standard", limit=80)
        unprocessed = payload["unprocessed_candidates"]
        self.assertTrue(unprocessed, "fetched-but-unprocessed records must be recorded")
        total = len(payload["candidates"]) + len(unprocessed)
        self.assertEqual(total, 80)
        for record in unprocessed:
            self.assertEqual(record["processing_status"], "UNPROCESSED_BEYOND_RUN_CEILING")

    def test_reported_rounds_match_actual_queries(self):
        self.ags.run_standard_search = self._stub(self._records(5), queries=1, expansions=0)
        _rc, payload = self._run(query="生态学", execution_depth="standard")
        usage = payload["search_protocol"]["actual_usage"]
        self.assertEqual(usage["queries_executed"], 1)
        self.assertEqual(usage["expansion_rounds_executed"], 0)
        self.assertEqual(
            payload["saturation_tracking"]["rounds_executed"],
            usage["queries_executed"] + usage["expansion_rounds_executed"],
        )

    def test_payload_exposes_configured_limits_and_actual_usage(self):
        self.ags.run_deep_search = self._stub(self._records(5), queries=2, expansions=2)
        _rc, payload = self._run(query="topic", execution_depth="deep")
        protocol = payload["search_protocol"]
        self.assertEqual(protocol["configured_limits"]["snowball_rounds"], 2)
        self.assertEqual(protocol["actual_usage"]["queries_executed"], 2)
        self.assertEqual(protocol["actual_usage"]["expansion_rounds_executed"], 2)

    def test_limit_is_documented_as_per_query(self):
        self.ags.run_standard_search = self._stub(self._records(3))
        _rc, payload = self._run(query="topic", execution_depth="standard", limit=7)
        protocol = payload["search_protocol"]
        self.assertEqual(protocol["per_query_limit"], 7)
        self.assertEqual(protocol["configured_limits"]["max_search_candidates"], 50)

    def test_profile_rounds_drive_the_real_call_trace(self):
        """Changing the configured rounds must change the executed trace (R11)."""
        from shared.execution import RunContext

        self.ags.query_openalex_headless = self._stub(self._records(4))
        self.ags.run_snowball_search = lambda *a, **k: ([], [])

        standard_profile = self.ags.get_profile("standard")
        deep_profile = self.ags.get_profile("deep")
        _std_records, std_info = self.ags.run_standard_search(
            "habitat connectivity", limit=5, profile=standard_profile
        )
        _deep_records, deep_info = self.ags.run_deep_search(
            "habitat connectivity", limit=5, profile=deep_profile
        )
        self.assertEqual(std_info["expansion_rounds_executed"], standard_profile.concept_expansion_rounds)
        self.assertEqual(deep_info["expansion_rounds_executed"], deep_profile.concept_expansion_rounds)
        self.assertGreater(deep_info["queries_executed"], std_info["queries_executed"])
        self.assertEqual(deep_info["rounds_executed"], deep_info["queries_executed"])

        # A profile declaring zero rounds must not report any expansion.
        quick_profile = self.ags.get_profile("quick")
        _quick_records, quick_info = self.ags.run_standard_search(
            "habitat connectivity", limit=5, profile=quick_profile
        )
        self.assertEqual(quick_info["expansion_rounds_executed"], 0)
        self.assertEqual(quick_info["queries_executed"], 1)

    def test_skipped_steps_are_reasoned_not_counted(self):
        self.ags.query_openalex_headless = self._stub(self._records(2))
        _records, info = self.ags.run_deep_search("生态学", limit=5, profile=self.ags.get_profile("deep"))
        self.assertTrue(info["skipped_steps"])
        for entry in info["skipped_steps"]:
            self.assertEqual(entry["executed_rounds"], 0)
            self.assertTrue(entry["reason"])
        self.assertEqual(info["expansion_rounds_executed"], 0)

    def test_different_depths_can_produce_different_traces(self):
        self.ags.run_deep_search = self._stub(self._records(5), queries=3, expansions=2)
        self.ags.run_standard_search = self._stub(self._records(5), queries=1, expansions=0)
        _rc1, standard = self._run(query="topic", execution_depth="standard")
        _rc2, deep = self._run(query="topic", execution_depth="deep")
        self.assertNotEqual(
            standard["search_protocol"]["actual_usage"]["queries_executed"],
            deep["search_protocol"]["actual_usage"]["queries_executed"],
        )


# ---------------------------------------------------------------------------
# R06: an installed skill tree must resolve the shared engine
# ---------------------------------------------------------------------------
class TestR06InstalledRuntime(unittest.TestCase):
    """R06: the installer ships a single engine copy that resolves in isolation."""

    INSTALLER = helpers.REPO_ROOT / "scripts" / "install.sh"

    def _install(self, destination):
        env = dict(os.environ)
        env["SCHOLARFLOW_SKILLS_DEST"] = str(destination)
        import subprocess

        return subprocess.run(
            ["bash", str(self.INSTALLER)],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(helpers.REPO_ROOT),
        )

    def test_installer_ships_exactly_one_engine_copy(self):
        if not self.INSTALLER.exists():
            self.skipTest("bash installer not available on this platform")
        with tempfile.TemporaryDirectory() as td:
            result = self._install(td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            engine_dirs = [p for p in Path(td).rglob("shared") if p.is_dir()]
            self.assertEqual(len(engine_dirs), 1, "the engine must be vendored exactly once")
            self.assertTrue((engine_dirs[0] / "__init__.py").is_file())

    def test_installed_entry_point_resolves_the_engine(self):
        if not self.INSTALLER.exists():
            self.skipTest("bash installer not available on this platform")
        with tempfile.TemporaryDirectory() as td:
            result = self._install(td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            entry = Path(td) / "literature-discovery-acquisition" / "scripts" / "agent_search.py"
            self.assertTrue(entry.is_file())

            import subprocess

            probe = (
                "from pathlib import Path;"
                "import os, sys;"
                "here = Path(os.path.abspath('agent_search.py'));"
                "sys.path.insert(0, str(here.parents[2]));"
                "import shared;"
                "print(shared.__file__)"
            )
            probe_result = subprocess.run(
                ["python3", "-I", "-S", "-c", probe],
                cwd=str(entry.parent),
                capture_output=True,
                text=True,
            )
            self.assertEqual(probe_result.returncode, 0, probe_result.stderr)
            resolved = probe_result.stdout.strip()
            self.assertIn(str(Path(td) / "shared"), resolved)
            self.assertNotIn(str(helpers.REPO_ROOT / "shared"), resolved)

    def test_installed_entry_point_enforces_the_depth_gate(self):
        if not self.INSTALLER.exists():
            self.skipTest("bash installer not available on this platform")
        with tempfile.TemporaryDirectory() as td:
            result = self._install(td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            scripts_dir = Path(td) / "literature-discovery-acquisition" / "scripts"
            import subprocess

            missing = subprocess.run(
                ["python3", "-I", "-S", "agent_search.py", "-q", "topic"],
                cwd=str(scripts_dir),
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)

            invalid = subprocess.run(
                ["python3", "-I", "-S", "agent_search.py", "-q", "topic", "-d", "banana"],
                cwd=str(scripts_dir),
                capture_output=True,
                text=True,
            )
            self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)

    def test_runtime_lookup_prefers_the_installed_layout(self):
        """The resolver must find <dest>/shared when no repo root exists."""
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            installed = Path(td) / "literature-discovery-acquisition" / "scripts"
            installed.mkdir(parents=True)
            (Path(td) / "shared").mkdir()
            (Path(td) / "shared" / "__init__.py").write_text("", encoding="utf-8")

            probe = (
                "from pathlib import Path;"
                "import os, sys;"
                "here = Path(os.path.abspath('probe.py'));"
                "candidates = [here.parents[3], here.parents[2]];"
                "print([str(c) for c in candidates if (c / 'shared' / '__init__.py').is_file()])"
            )
            (installed / "probe.py").write_text("", encoding="utf-8")
            result = subprocess.run(
                ["python3", "-I", "-S", "-c", probe],
                cwd=str(installed),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(Path(td)), result.stdout)


def _conversation_provider(turns):
    from shared.context_resolution.context_resolver import ConversationContextProvider

    return ConversationContextProvider(turns=turns)


if __name__ == "__main__":
    unittest.main()
