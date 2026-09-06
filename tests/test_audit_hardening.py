"""ScholarFlow v0.6.1 Integration Hardening Contract & Adversarial Tests.

Covers the 12 contract tests (Section 41) and 5 adversarial tests (Section 42)
specified in the Full-Repo Integration Hardening Manual (v0.6.1).
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

from shared.context_resolution import (
    AttachmentContextProvider,
    ContextResolver,
    ContextScope,
    ConversationContextProvider,
    FactVolatility,
    ProjectSearchContextProvider,
    VariableStatus,
)
from shared.grill_me.dimensions import (
    get_discovery_dimensions,
    get_extraction_dimensions,
)
from shared.grill_me.response_parser import (
    GrillEngine,
    GrillQuestion,
    GrillResponseParser,
    PriorityTier,
    Provenance,
)

try:
    import helpers
except ImportError:
    from tests import helpers

from controversy_analyzer import resolve_evidence_weight

REPO_ROOT = helpers.REPO_ROOT


class TestAuditHardeningContracts(unittest.TestCase):
    """Section 41: 12 Contract Tests."""

    def test_skill_entrypoint_requires_context_resolution(self):
        """1. Check that all 3 SKILL.md mandate Stage 0A Context Resolution -> 0B Grill -> 0C Snapshot."""
        skills = [
            REPO_ROOT / "skills" / "literature-discovery-acquisition" / "SKILL.md",
            REPO_ROOT / "skills" / "literature-evidence-extraction" / "SKILL.md",
            REPO_ROOT / "skills" / "literature-synthesis" / "SKILL.md",
        ]
        for sk_path in skills:
            self.assertTrue(sk_path.exists(), f"Missing skill file: {sk_path}")
            text = sk_path.read_text(encoding="utf-8")
            self.assertIn("Stage 0A", text, f"Missing Stage 0A in {sk_path.name}")
            self.assertIn("Context Resolution", text, f"Missing Context Resolution in {sk_path.name}")
            self.assertIn("Stage 0B", text, f"Missing Stage 0B in {sk_path.name}")
            self.assertIn("Adaptive Grill", text, f"Missing Adaptive Grill in {sk_path.name}")
            self.assertIn("Stage 0C", text, f"Missing Stage 0C in {sk_path.name}")
            self.assertIn("Protocol Snapshot", text, f"Missing Protocol Snapshot in {sk_path.name}")
            self.assertNotIn("唯一必须读取 references/stage0_grill_me.md", text)
            self.assertNotIn("唯一必须读取 stage0_grill_me.md", text)

    def test_discovery_no_fixed_q1_q2(self):
        """2. Check that Discovery SKILL.md does not mandate fixed Q1/Q2 questions."""
        disc_skill = REPO_ROOT / "skills" / "literature-discovery-acquisition" / "SKILL.md"
        text = disc_skill.read_text(encoding="utf-8")
        self.assertNotIn("Q1 Deep Search vs Quick Search", text)
        self.assertNotIn("Q2 硕博学位论文需求", text)
        self.assertNotIn("固定必问两个核心问题", text)

    def test_single_domain_lens_source_of_truth(self):
        """3. Assert single source of truth for domain lenses."""
        dup_dir = REPO_ROOT / "shared" / "grill_me" / "domain_lenses"
        canonical_dir = REPO_ROOT / "shared" / "domain_lenses"
        self.assertFalse(dup_dir.exists(), "Duplicate domain_lenses directory must be removed")
        self.assertTrue(canonical_dir.exists(), "Canonical domain_lenses directory must exist")
        lenses = list(canonical_dir.glob("*.md"))
        self.assertEqual(len(lenses), 9, f"Expected exactly 9 domain lenses, found {len(lenses)}")

    def test_readme_lens_names_match_files(self):
        """4. Check that README.md lists exact matching domain lens filenames."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        canonical_dir = REPO_ROOT / "shared" / "domain_lenses"
        lens_stems = {f.stem for f in canonical_dir.glob("*.md")}
        for stem in lens_stems:
            self.assertIn(stem, readme, f"Domain lens '{stem}' not found in README.md")

    def test_discovery_result_validates_schema(self):
        """5. Check that discovery result schema exists and validates minimal payload."""
        schema_path = REPO_ROOT / "schemas" / "discovery_result.schema.json"
        self.assertTrue(schema_path.exists())
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("required", schema)
        self.assertIn("candidates", schema["required"])

        sample_discovery = {
            "schema_version": "1.1",
            "status": "SUCCESS",
            "search_target": "test",
            "search_protocol": {"mode": "deep"},
            "candidates": [
                {
                    "schema_version": "1.0",
                    "record_id": "REC001",
                    "title": "Test Paper",
                    "authors": ["Author A"],
                    "year": 2023,
                    "source_databases": ["OpenAlex"],
                }
            ],
        }
        for req in schema["required"]:
            self.assertIn(req, sample_discovery)

    def test_extraction_result_validates_schema(self):
        """6. Check that extraction result schema exists and validates minimal payload."""
        schema_path = REPO_ROOT / "schemas" / "extraction_result.schema.json"
        self.assertTrue(schema_path.exists())
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("required", schema)
        self.assertIn("evidence_records", schema["required"])

        sample_extraction = {
            "schema_version": "1.1",
            "paper_metadata": {"title": "P", "authors": ["A"], "year": 2022},
            "extraction_metadata": {"mode": "extract", "timestamp": "2026-09-06T00:00:00Z"},
            "evidence_records": [
                {
                    "schema_version": "1.0",
                    "evidence_id": "EV01",
                    "record_id": "REC01",
                    "field": "sample_size",
                    "extracted_value": 42,
                    "support_type": "EXPLICIT",
                    "claim_status": "SUPPORTED",
                }
            ],
            "auditor_verdict": {"verdict": "PASS", "checklist_passed": True},
        }
        for req in schema["required"]:
            self.assertIn(req, sample_extraction)

    def test_bare_e4_is_rejected(self):
        """7. Bare E4 must be rejected as AMBIGUOUS_LEGACY_TIER with weight 0.0."""
        claim = {"claim_id": "C1", "evidence_tier": "E4"}
        w, tier, _ = resolve_evidence_weight(claim)
        self.assertEqual(tier, "AMBIGUOUS_LEGACY_TIER")
        self.assertEqual(w, 0.0)

    def test_missing_evidence_strength_is_unknown(self):
        """8. Missing evidence_strength must default to UNKNOWN with weight 0.3."""
        claim = {"claim_id": "C1", "statement": "Some assertion"}
        w, tier, _ = resolve_evidence_weight(claim)
        self.assertEqual(tier, "UNKNOWN")
        self.assertEqual(w, 0.3)

    def test_attachment_protocol_is_not_fulltext(self):
        """9. Non-paper attachment (project_protocol.docx) must produce PROTOCOL and NOT fulltext_pdf."""
        provider = AttachmentContextProvider(
            attachments=[{"name": "project_protocol.docx", "text": "Study protocol description"}]
        )
        facts = provider.fetch_facts(task_prompt="Extract", target_dimension_ids=["E2"])
        e2_facts = [f for f in facts if f.dimension_id == "E2"]
        doc_kind_facts = [f for f in facts if f.dimension_id == "DOC_KIND"]

        self.assertEqual(len(e2_facts), 0, "Protocol document must not trigger E2 fulltext_pdf")
        self.assertEqual(len(doc_kind_facts), 1)
        self.assertEqual(doc_kind_facts[0].value, "PROTOCOL")

    def test_conversation_latest_decision_wins(self):
        """10. Scan turns in reverse recency order so latest confirmed decision wins."""
        provider = ConversationContextProvider(
            turns=[
                {"content": "我想检索英文论文，仅限英文", "timestamp": 1.0},
                {"content": "范围调整，中英双语都需要检索", "timestamp": 8.0},
            ]
        )
        facts = provider.fetch_facts(task_prompt="搜文献", target_dimension_ids=["D10"])
        d10_facts = [f for f in facts if f.dimension_id == "D10"]
        self.assertEqual(len(d10_facts), 1)
        self.assertEqual(d10_facts[0].value, "en_and_zh")

    def test_ok_does_not_accept_all_recommended(self):
        """11. Ambiguous words ('ok', 'yes', '确认') must not trigger accept all recommended."""
        self.assertFalse(GrillResponseParser.is_all_recommended("ok"))
        self.assertFalse(GrillResponseParser.is_all_recommended("yes"))
        self.assertFalse(GrillResponseParser.is_all_recommended("确认"))
        self.assertFalse(GrillResponseParser.is_all_recommended("proceed"))
        self.assertFalse(GrillResponseParser.is_all_recommended("全选A"))
        self.assertTrue(GrillResponseParser.is_all_recommended("按推荐"))
        self.assertTrue(GrillResponseParser.is_all_recommended("全部按推荐"))

    def test_python_version_contract(self):
        """12. Check that pyproject.toml requires Python >=3.9."""
        pyproj = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.9"', pyproj)


class TestAuditHardeningAdversarial(unittest.TestCase):
    """Section 42: 5 Adversarial Tests."""

    def test_adversarial_legacy_e4(self):
        """42.A: Legacy E4 data must resolve to AMBIGUOUS_LEGACY_TIER, never EXPERT_OPINION."""
        raw_e4 = {"evidence_tier": "E4", "claim": "Historic assertion"}
        w, resolved_tier, _ = resolve_evidence_weight(raw_e4)
        self.assertEqual(resolved_tier, "AMBIGUOUS_LEGACY_TIER")
        self.assertNotEqual(resolved_tier, "EXPERT_OPINION")
        self.assertEqual(w, 0.0)

    def test_adversarial_word_document_not_paper(self):
        """42.B: Word file project_protocol.docx must not unlock full-text extraction gate."""
        att_provider = AttachmentContextProvider(
            attachments=[{"name": "project_protocol.docx", "text": "Meeting and protocol notes"}]
        )
        resolver = ContextResolver(scope=ContextScope.CURRENT_ONLY)
        resolver.add_provider(att_provider)

        engine = GrillEngine(skill_name="literature-evidence-extraction", domain="generic")
        engine.register_dimensions(get_extraction_dimensions())
        questions = engine.select_questions(
            task_prompt="提取文献定量参数",
            context_resolver=resolver,
        )
        q_dims = [q.dimension.id for q in questions]

        # E2 should NOT be silently resolved to fulltext_pdf
        self.assertNotIn("E2", engine.resolutions)
        self.assertIn("E2", q_dims)

    def test_adversarial_conversation_override(self):
        """42.C: Turn 1 English-only vs Turn 8 Bilingual -> Bilingual wins."""
        turns = [
            {"role": "user", "content": "检索仅限英文", "timestamp": 1.0},
            {"role": "assistant", "content": "已记录仅限英文。"},
            {"role": "user", "content": "这里改成中英双语检索", "timestamp": 8.0},
        ]
        conv_provider = ConversationContextProvider(turns=turns)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(conv_provider)

        engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="generic")
        engine.register_dimensions(get_discovery_dimensions())
        questions = engine.select_questions(task_prompt="执行文献检索", context_resolver=resolver)

        self.assertIn("D10", engine.resolutions)
        self.assertEqual(engine.resolutions["D10"].selected_value, "en_and_zh")

    def test_adversarial_ok_does_not_bypass_critical(self):
        """42.D: Replying 'ok' to 5 questions leaves critical dimensions unresolved."""
        dim1 = get_discovery_dimensions()[0]  # D1: CRITICAL
        dim2 = get_discovery_dimensions()[1]  # D2: CRITICAL
        questions = [
            GrillQuestion(index=1, dimension=dim1, prompt="Q1"),
            GrillQuestion(index=2, dimension=dim2, prompt="Q2"),
        ]
        resolutions, unresolved = GrillResponseParser.parse("ok", questions)
        self.assertIn(dim1.id, unresolved)
        self.assertIn(dim2.id, unresolved)
        self.assertNotEqual(len(unresolved), 0)

    def test_adversarial_cross_domain_isolation(self):
        """42.E: Computer science task + ecology project doc yields 0 irrelevant inheritance."""
        project_docs = {
            "protocols/wildlife_dna.md": (
                "# Noninvasive genetic study\n"
                "Target entity: Cervid species\n"
                "Methods: Fecal DNA PCR microsatellite genotyping\n"
            )
        }
        proj_provider = ProjectSearchContextProvider(project_docs=project_docs)
        resolver = ContextResolver(scope=ContextScope.PROJECT_AWARE)
        resolver.add_provider(proj_provider)

        cs_prompt = "调研 Transformer benchmark 与 long-context LLMs neural model 评估体系"
        inferred, unresolved = resolver.resolve(
            task_prompt=cs_prompt,
            target_dimensions=["D1", "D2", "D3", "D8"],
        )
        self.assertNotIn("D3", inferred)
        self.assertEqual(len(resolver.resolved_variables), 0)


if __name__ == "__main__":
    unittest.main()
