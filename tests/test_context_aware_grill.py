"""Unit tests for ScholarFlow Context-Aware Grill-Me Resolution Layer.

Verifies the 9 core test scenarios specified in Section 39 of the design document:
1. Duplicate info in conversation is not re-asked.
2. Project files automatically populate target entity.
3. Current user message overrides historical project file.
4. Irrelevant project files (cross-domain) do not pollute task.
5. Extraction reuses previous extraction schema from upstream outputs.
6. Multi-cohort paper triggers cohort isolation decision in Grill-Me.
7. Synthesis directly ingests audited Evidence Tables rather than re-asking.
8. Conflicting project files at equal layer trigger UNRESOLVED_CONFLICT.
9. Graceful degradation when project search provider is unavailable.
"""

import unittest
from shared.context_resolution import (
    AttachmentContextProvider,
    ContextFact,
    ContextResolver,
    ContextScope,
    ConversationContextProvider,
    FactType,
    FactVolatility,
    ProjectSearchContextProvider,
    UpstreamArtifactContextProvider,
    VariableStatus,
)
from shared.grill_me.dimensions import (
    get_discovery_dimensions,
    get_extraction_dimensions,
    get_synthesis_dimensions,
)
from shared.grill_me.response_parser import GrillEngine, GrillState, PriorityTier, Provenance


class TestContextAwareGrill(unittest.TestCase):
    """Test suite covering the 9 core requirements of Context-Aware Grill-Me."""

    def test_1_duplicate_info_not_reasked(self):
        """Test 1: Information stated in prior conversation is not re-asked."""
        conv_provider = ConversationContextProvider(
            turns=[
                {"role": "user", "content": "我想做医学文献调研，仅限英文论文。"},
                {"role": "assistant", "content": "好的，请问时间范围？"},
                {"role": "user", "content": "时间范围锁定在 2018-2024 年。"},
            ]
        )
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(conv_provider)

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="biomedical")
        engine.register_dimensions(get_discovery_dimensions())

        questions = engine.select_questions(
            task_prompt="继续检索免疫疗法相关论文",
            context_resolver=resolver,
        )
        question_dim_ids = [q.dimension.id for q in questions]

        # D8 (Time scope) and D10 (Language scope) must NOT be asked
        self.assertNotIn("D8", question_dim_ids)
        self.assertNotIn("D10", question_dim_ids)

        # Both must be recorded in resolutions with correct values
        self.assertIn("D8", engine.resolutions)
        self.assertIn("D10", engine.resolutions)
        self.assertEqual(engine.resolutions["D8"].selected_value, "2018-2024")
        self.assertEqual(engine.resolutions["D10"].selected_value, "en_only")
        self.assertEqual(engine.resolutions["D10"].provenance, Provenance.USER)

    def test_2_project_file_populates_target_entity(self):
        """Test 2: Project files automatically populate research target entity on-demand."""
        project_docs = {
            "protocols/clinical_study.md": (
                "# Research Protocol\n"
                "Target disease: breast cancer\n"
                "Phase: III trial evaluation\n"
            )
        }
        proj_provider = ProjectSearchContextProvider(project_docs=project_docs)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(proj_provider)

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="clinical")
        engine.register_dimensions(get_discovery_dimensions())

        questions = engine.select_questions(
            task_prompt="继续搜相关文献",
            context_resolver=resolver,
        )
        question_dim_ids = [q.dimension.id for q in questions]

        # Target entity (D3) should be inherited from project search
        self.assertNotIn("D3", question_dim_ids)
        self.assertIn("D3", engine.resolutions)
        self.assertEqual(engine.resolutions["D3"].selected_value, "breast cancer")
        self.assertEqual(engine.resolutions["D3"].provenance, Provenance.PROJECT)

    def test_3_current_user_overrides_project_file(self):
        """Test 3: Current user prompt explicitly overrides settings in project files."""
        project_docs = {
            "guidelines/cohort_criteria.md": (
                "Target population: adults only\n"
                "Age: >= 18 years\n"
            )
        }
        proj_provider = ProjectSearchContextProvider(project_docs=project_docs)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(proj_provider)

        # User explicitly broadens scope in current prompt
        user_prompt = "检索相关临床干预方案，这次包括儿童"
        inferred, unresolved = resolver.resolve(
            task_prompt=user_prompt,
            target_dimensions=["D3"],
        )

        self.assertEqual(inferred.get("D3"), "adults + children")
        var = resolver.resolved_variables["D3"]
        self.assertEqual(var.status, VariableStatus.RESOLVED_FROM_USER)
        self.assertEqual(var.primary_fact.source_layer, "current_user")
        # Overridden historical fact must be tracked for auditability
        self.assertEqual(len(var.overridden_facts), 1)
        self.assertEqual(var.overridden_facts[0].source_layer, "project_search")
        self.assertEqual(var.overridden_facts[0].value, "adults only")

    def test_4_irrelevant_project_file_does_not_pollute(self):
        """Test 4: Cross-domain orthogonal project files do not pollute the task."""
        project_docs = {
            "field_notes/ecology_survey.md": (
                "Wildlife biodiversity habitat ecology population survey.\n"
                "Species conservation in forested landscape.\n"
            )
        }
        proj_provider = ProjectSearchContextProvider(project_docs=project_docs)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(proj_provider)

        # Computer science prompt
        cs_prompt = "调研 Transformer benchmark 与 long-context LLMs neural model 评估体系"
        inferred, unresolved = resolver.resolve(
            task_prompt=cs_prompt,
            target_dimensions=["D1", "D2", "D3", "D8"],
        )

        # Ecology documents should have been filtered out completely
        self.assertNotIn("D3", inferred)
        self.assertEqual(len(resolver.resolved_variables), 0)

    def test_5_extraction_reuses_upstream_schema(self):
        """Test 5: Extraction skill reuses schema snapshot from upstream executions."""
        upstream_provider = UpstreamArtifactContextProvider(
            upstream_data={
                "extraction_schema": "biomedical_v1",
                "source_pipeline": "discovery_run_04",
            }
        )
        resolver = ContextResolver(scope=ContextScope.CURRENT_PLUS_UPSTREAM)
        resolver.add_provider(upstream_provider)

        engine = GrillEngine(skill_name="literature-evidence-extraction", domain="biomedical")
        engine.register_dimensions(get_extraction_dimensions())

        questions = engine.select_questions(
            task_prompt="继续按上一篇的标准提取新文献中的定量参数",
            context_resolver=resolver,
        )
        question_dim_ids = [q.dimension.id for q in questions]

        # E3 (Schema selection) should be resolved from upstream outputs
        self.assertNotIn("E3", question_dim_ids)
        self.assertIn("E3", engine.resolutions)
        self.assertEqual(engine.resolutions["E3"].selected_value, "biomedical_v1")
        self.assertEqual(engine.resolutions["E3"].provenance, Provenance.UPSTREAM)

    def test_6_new_paper_triggers_cohort_isolation_grill(self):
        """Test 6: Multi-cohort paper triggers cohort isolation decision in Grill-Me."""
        attachment_provider = AttachmentContextProvider(
            attachments=[
                {
                    "name": "clinical_trial_triple_arm.txt",
                    "text": (
                        "We evaluated efficacy across three distinct cohorts.\n"
                        "Cohort 1 received low-dose regimen (n=50).\n"
                        "Cohort 2 received high-dose regimen (n=60).\n"
                        "Cohort 3 received placebo control (n=55).\n"
                    ),
                }
            ]
        )
        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        resolver.add_provider(attachment_provider)

        engine = GrillEngine(skill_name="literature-evidence-extraction", domain="clinical")
        engine.register_dimensions(get_extraction_dimensions())

        questions = engine.select_questions(
            task_prompt="提取该篇文献的关键临床终点指标",
            context_resolver=resolver,
        )
        question_dim_ids = [q.dimension.id for q in questions]

        # E4 (证据单元切分与多实验隔离粒度) is CRITICAL and must NOT be silently auto-decided;
        # It must be presented to the user as a Grill question
        self.assertIn("E4", question_dim_ids)
        # Meanwhile, E2 (待抽取的文献范围) is resolved to fulltext_pdf from the attachment
        self.assertNotIn("E2", question_dim_ids)
        self.assertEqual(engine.resolutions["E2"].selected_value, "fulltext_pdf")

    def test_7_synthesis_ingests_audited_evidence_tables(self):
        """Test 7: Synthesis directly ingests audited Evidence Tables from upstream Extraction."""
        upstream_provider = UpstreamArtifactContextProvider(
            upstream_data={
                "evidence_records": [
                    {"study_id": "ST01", "claim": "Drug A reduces LDL-C by 25%", "verdict": "SUPPORTED"},
                    {"study_id": "ST02", "claim": "Drug A reduces LDL-C by 28%", "verdict": "SUPPORTED"},
                ],
                "extraction_schema": "biomedical_v1",
            }
        )
        resolver = ContextResolver(scope=ContextScope.CURRENT_PLUS_UPSTREAM)
        resolver.add_provider(upstream_provider)

        engine = GrillEngine(skill_name="literature-synthesis", domain="biomedical")
        engine.register_dimensions(get_synthesis_dimensions())

        questions = engine.select_questions(
            task_prompt="对现有证据进行综合分析并评估学派共识",
            context_resolver=resolver,
        )
        question_dim_ids = [q.dimension.id for q in questions]

        # S3 (证据体纳入边界与前置清洗标准) must be resolved to audited_extraction_table
        self.assertNotIn("S3", question_dim_ids)
        self.assertIn("S3", engine.resolutions)
        self.assertEqual(engine.resolutions["S3"].selected_value, "audited_extraction_table")
        self.assertEqual(engine.resolutions["S3"].provenance, Provenance.UPSTREAM)

    def test_8_conflicting_project_files_triggers_unresolved_conflict(self):
        """Test 8: Conflicting project files at equal layer trigger UNRESOLVED_CONFLICT."""
        project_docs = {
            "reports/preliminary_cohort.md": "Sample size: 120 subjects included in study.\n",
            "reports/updated_cohort.md": "Sample size: 135 subjects included in study.\n",
        }
        proj_provider = ProjectSearchContextProvider(project_docs=project_docs)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(proj_provider)

        inferred, unresolved = resolver.resolve(
            task_prompt="统计当前队列总样本量并进行后续分析",
            target_dimensions=["SAMPLE_SIZE"],
        )

        # Because both files are at project_search layer without timestamps, a conflict is detected
        self.assertIn("SAMPLE_SIZE", unresolved)
        self.assertIn("SAMPLE_SIZE", resolver.resolved_variables)
        var = resolver.resolved_variables["SAMPLE_SIZE"]
        self.assertEqual(var.status, VariableStatus.UNRESOLVED_CONFLICT)
        self.assertEqual(len(var.conflicting_facts), 2)
        self.assertEqual(len(resolver.conflicts), 1)

        # Brief must flag the conflict explicitly for user arbitration
        brief = resolver.render_context_brief_markdown()
        self.assertIn("待仲裁的同级上下文冲突", brief)
        self.assertIn("SAMPLE_SIZE", brief)

    def test_9_graceful_degradation_without_project_provider(self):
        """Test 9: Graceful degradation when project search provider is unavailable."""
        # Empty resolver or only conversation provider
        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        # Disabled project provider
        disabled_provider = ProjectSearchContextProvider(project_docs=None, is_enabled=False)
        resolver.add_provider(disabled_provider)
        self.assertFalse(disabled_provider.is_available())
        self.assertEqual(len(resolver.providers), 0)

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions(get_discovery_dimensions())

        # Should execute cleanly without errors, generating standard Grill questions
        questions = engine.select_questions(
            task_prompt="帮我调研可解释机器学习相关文献",
            context_resolver=resolver,
        )
        self.assertGreaterEqual(len(questions), 3)
        self.assertLessEqual(len(questions), 5)
        self.assertEqual(engine.state, GrillState.STAGE0_UNRESOLVED)

        presentation = engine.render_presentation()
        self.assertIn("现有科研上下文确认简报", presentation)
        self.assertIn("待确认科研决策维度", presentation)


if __name__ == "__main__":
    unittest.main()
