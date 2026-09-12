# -*- coding: utf-8 -*-
"""Bootstrap sys.path so test modules can import skill scripts directly."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

for _p in [
    REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts",
    REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts",
    REPO_ROOT / "skills" / "literature-synthesis" / "scripts",
]:
    sys.path.insert(0, str(_p))

FIXTURES = REPO_ROOT / "tests" / "fixtures"


def semantic_verification(evidence_id, proposition, role="CURRENT_STUDY_RESULT",
                          idea_version=None, verifier="extraction-qc",
                          verification_ref="audit#1", **overrides):
    """Build a **binding-complete** semantic-verification credential.

    R01（第二轮核查）之后，`to_evidence_link()` 只在语义核验凭据绑定完整时才允许
    `VERIFIED`，因此期望"支持成立"的测试必须提供真实凭据，而不是靠默认放行。
    """
    from shared.execution.debate_handoff import proposition_fingerprint

    payload = {
        "status": "VERIFIED",
        "semantic_role": role,
        "is_empirical_result": role in ("CURRENT_STUDY_RESULT", "CURRENT_STUDY_OBSERVATION"),
        "evidence_id": evidence_id,
        "proposition_fingerprint": proposition_fingerprint(proposition),
        "verifier": verifier,
        "verification_ref": verification_ref,
        "reasoning": "人工/上游结构化语义核验：引句为当前研究实证结果且方向一致",
    }
    if idea_version is not None:
        payload["idea_version"] = idea_version
    payload.update(overrides)
    return payload
