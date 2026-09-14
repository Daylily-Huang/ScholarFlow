# -*- coding: utf-8 -*-
"""Bootstrap sys.path so test modules can import skill scripts directly."""
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

for _p in [
    REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts",
    REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts",
    REPO_ROOT / "skills" / "literature-synthesis" / "scripts",
]:
    sys.path.insert(0, str(_p))

FIXTURES = REPO_ROOT / "tests" / "fixtures"

#: 并发 / 中断恢复类测试必须在**仓库所在卷**上落盘（第一轮用 /mnt 9p 挂载，
#: 并发观测失真），所以不能用系统临时目录。但它们也不该把临时目录直接丢进
#: 仓库根——进程被 kill 时会留下未跟踪残留。统一落到仓库内一个已被
#: `.gitignore` 覆盖的 scratch 目录（`test_output/`）。
SCRATCH_ROOT = REPO_ROOT / "test_output"


def make_scratch_dir(prefix):
    """在仓库内的 gitignore 覆盖目录下建临时目录，返回其路径字符串。"""
    SCRATCH_ROOT.mkdir(exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=str(SCRATCH_ROOT))


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
