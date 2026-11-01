#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calculate_screening_agreement.py
--------------------------------
ScholarFlow PRISMA 2020 Item 8 Dual-Reviewer Blind Screening Evaluator.

Computes inter-rater agreement statistics (Cohen's Kappa κ, Observed Agreement,
Contingency Matrix) between two independent screening reviewers (e.g., SubAgent-A
and SubAgent-B), and outputs PRISMA-compliant audit trails and arbitration queues.

H-27 (2026-09-13, cluster-2 round 2) — the kappa gate now also verifies the
*preconditions* of dual screening:
1. Source independence: A/B inputs that are byte-identical (same content
   fingerprint) with fully agreeing decisions, or that reuse the same
   non-empty ``task_id``, are rejected as IDENTICAL_SOURCES with rc=1 and no
   report is emitted — kappa=1.0 laundered from a single source is never a
   pass.
2. Reviewer coverage: records reviewed by only one reviewer never enter the
   confusion matrix; a coverage gap produces an explicit ``coverage_warning``
   (coverage_status=WARNING, non-PASS) in the metrics and the markdown report
   while rc stays 0, so legitimately complete inputs are never blocked.

Standard Library Only (Zero third-party pip dependencies required).
"""

import argparse
import csv
import hashlib
import json
import math
import sys

from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# 保证中文产物在 zh-CN Windows（默认 cp936）上以 UTF-8 输出：上游按 UTF-8
# 读取 stdout 时不再解码失败（P2-08 同类项，2026-09-16 普查补齐）。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


VALID_STATUSES = ["Include", "Exclude", "Uncertain"]

#: 记录标识键（含 canonical `record_id`）与裁决键（含 canonical `screening_status`）。
#: 2026-09-15（集群审查 P1）：加载器原先只认 `id|rec_id|doi|title` 与
#: `status|Status|decision`，而本技能的两个生产者只写 canonical 名——两边错开，
#: 整份文件的裁决被读成空值。
RECORD_ID_KEYS = ("record_id", "id", "rec_id", "doi", "title")
STATUS_KEYS = ("screening_status", "status", "Status", "decision", "reviewer_decision")


def normalize_status(val: Any) -> Optional[str]:
    """把裁决归一为 Include / Exclude / Uncertain；**无法识别一律返回 None**。

    2026-09-15（集群审查 P1）：旧实现对任何未识别值（含键缺失时的空串）一律
    `return "Uncertain"`。于是「一条裁决都没读进来」与「两评阅人都判待定」在产物里
    完全同形——逐条对立的两份初筛会被判 `κ=1.000`「Almost Perfect（符合顶级发表
    标准）」且 rc=0、零告警。「读不到」与「都判待定」必须是两件事。
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    key = s.lower()
    if key in ["include", "included", "inc", "纳入", "yes", "y", "1"]:
        return "Include"
    elif key in ["exclude", "excluded", "exc", "排除", "no", "n", "0"]:
        return "Exclude"
    elif key in ["uncertain", "maybe", "borderline", "待定", "存疑", "u", "?"]:
        return "Uncertain"
    return None


def _first_present(mapping: Dict[str, Any], keys) -> Any:
    """按 keys 顺序取第一个"有内容"的值；全空返回 None。

    与旧实现的 `a or b or c` 取值口径一致（空串视为未提供），但把键名集合显式化，
    避免 canonical 名（`record_id` / `screening_status`）被漏掉。
    """
    for k in keys:
        if k not in mapping:
            continue
        value = mapping[k]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def summarize_unreadable(records: Dict[str, Dict[str, Any]]) -> List[Tuple[str, Any]]:
    """列出裁决无法识别的记录（id, 原始值）。空列表表示全部可读。"""
    return [(rid, rec.get("status_raw")) for rid, rec in records.items()
            if rec.get("status") is None]


def load_decisions(path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load decisions from JSON or CSV file.
    Returns a dict mapping record ID -> decision dict.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    records = {}
    suffix = path.suffix.lower()

    if suffix in [".json"]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    rid = str(_first_present(item, RECORD_ID_KEYS) or "")
                    if rid:
                        raw_status = _first_present(item, STATUS_KEYS)
                        records[rid] = {
                            "id": rid,
                            "title": item.get("title", ""),
                            "status": normalize_status(raw_status),
                            "status_raw": raw_status,
                            "reason_code": item.get("reason_code", ""),
                            "reason_detail": item.get("reason_detail", ""),
                            "confidence_score": float(item.get("confidence_score", 0.0)) if item.get("confidence_score") is not None else None,
                            "task_id": item.get("task_id") or item.get("reviewer_task_id") or ""
                        }
            elif isinstance(data, dict):
                for rid, item in data.items():
                    if isinstance(item, dict):
                        raw_status = _first_present(item, STATUS_KEYS)
                        records[str(rid)] = {
                            "id": str(rid),
                            "title": item.get("title", ""),
                            "status": normalize_status(raw_status),
                            "status_raw": raw_status,
                            "reason_code": item.get("reason_code", ""),
                            "reason_detail": item.get("reason_detail", ""),
                            "confidence_score": float(item.get("confidence_score", 0.0)) if item.get("confidence_score") is not None else None,
                            "task_id": item.get("task_id") or item.get("reviewer_task_id") or ""
                        }
                    else:
                        records[str(rid)] = {
                            "id": str(rid),
                            "title": "",
                            "status": normalize_status(str(item)),
                            "status_raw": str(item),
                            "reason_code": "",
                            "reason_detail": "",
                            "confidence_score": None,
                            "task_id": ""
                        }

    elif suffix in [".csv", ".tsv"]:
        delimiter = "\t" if suffix == ".tsv" else ","
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                rid = str(_first_present(row, RECORD_ID_KEYS + ("ID",)) or "")
                if rid:
                    status_raw = _first_present(row, STATUS_KEYS)
                    records[rid] = {
                        "id": rid,
                        "title": row.get("title", ""),
                        "status": normalize_status(status_raw),
                        "status_raw": status_raw,
                        "reason_code": row.get("reason_code", row.get("code", "")),
                        "reason_detail": row.get("reason_detail", row.get("reason", "")),
                        "confidence_score": float(row.get("confidence_score", 0.0)) if row.get("confidence_score") else None,
                        "task_id": row.get("task_id") or ""
                    }
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .json or .csv")

    return records


def compute_source_fingerprint(path: Path) -> Optional[str]:
    """H-27: sha256 content fingerprint used to detect same-source input files."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_canonical_fingerprint(records: Dict[str, Dict[str, Any]]) -> str:
    """裁决内容的**规范化**指纹（P2-10，2026-09-15 集群审查）。

    字节级指纹只需改一个空格（重排键序、换行风格、缩进）即失效——而"同一份初筛
    结果换个格式喂两次"是同源洗白的典型手法。此指纹与序列化形式无关。

    必须覆盖**全部裁决字段**，而不只是 id→status：只看裁决大类会把"两份各自独立、
    恰好判得一样"的正常双评阅误判为同源（既有测试
    `test_independent_files_with_full_agreement_allowed` 正是这种情形——两份文件的
    理由码不同）。把理由码/理由说明/任务号/置信度一并纳入，则"同一份结果换格式"
    仍然同指纹，而独立评阅之间的实质差异得以保留。
    """
    parts = []
    for rid, rec in sorted(records.items()):
        parts.append("|".join(str(rec.get(k) or "") for k in (
            rid, "status", "reason_code", "reason_detail", "task_id", "confidence_score")))
    canonical = "\n".join(parts)
    return "canon:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: κ 的最小共同评阅样本量（P2-10）。低于此值时 κ 的方差极大，"自选子集"极易
#: 刷出 1.000；该阈值与既有 `coverage_status` 同一约定：**告警不阻断**（rc 仍为 0），
#: 但报告与产物必须显示非 PASS，使"小样本一致性"无法被当成顶级一致性证据。
MIN_COMMON_RECORDS = 5


def check_source_independence(
    path_a: Path,
    path_b: Path,
    rev_a_data: Dict[str, Dict[str, Any]],
    rev_b_data: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """H-27: reject same-source reviewer inputs before any kappa is certified.

    Two same-source signals are detected (either one is fatal):

    1. byte-identical input files (identical content fingerprint, e.g. the
       same file fed to both ``-a`` and ``-b``) whose decisions fully agree —
       the classic kappa=1.0 laundering route;
    2. both payloads reusing the same non-empty ``task_id`` (one screening run
       relabelled as two reviewers).

    Returns None when the inputs are plausibly independent; otherwise a
    structured ``IDENTICAL_SOURCES`` error dict. The caller must exit rc=1 and
    must NOT emit a passing report.
    """
    fp_a = compute_source_fingerprint(path_a)
    fp_b = compute_source_fingerprint(path_b)
    common_ids = sorted(set(rev_a_data) & set(rev_b_data))
    reasons: List[str] = []

    # P2-10：字节级之外再看内容级——同一份裁决换格式（键序/缩进/换行）喂两次，
    # 字节指纹不同但语义同源，同样必须在签发 κ 之前拦下。
    canon_a = compute_canonical_fingerprint(rev_a_data)
    canon_b = compute_canonical_fingerprint(rev_b_data)
    if canon_a == canon_b and common_ids:
        reasons.append(
            "Reviewer A and Reviewer B carry the SAME decisions after canonicalisation "
            "(keys/order/whitespace differences do not make two screenings independent); "
            "kappa computed from one screening relabelled twice is not dual review.")

    if fp_a and fp_b and fp_a == fp_b and common_ids:
        fully_agree = all(
            rev_a_data[r]["status"] == rev_b_data[r]["status"] for r in common_ids
        )
        if fully_agree:
            reasons.append(
                "Reviewer A and Reviewer B inputs are byte-identical "
                f"(same source fingerprint {fp_a}) with fully agreeing decisions; "
                "kappa=1.0 from identical sources is not evidence of independent "
                "dual screening."
            )

    def _task_ids(records: Dict[str, Dict[str, Any]]) -> set:
        vals = set()
        for r in records.values():
            tid = str(r.get("task_id") or "").strip()
            if tid:
                vals.add(tid)
        return vals

    task_a = _task_ids(rev_a_data)
    task_b = _task_ids(rev_b_data)
    shared_tasks = sorted(task_a & task_b)
    if shared_tasks:
        reasons.append(
            "Reviewer A and Reviewer B payloads reuse the same task_id "
            f"({', '.join(shared_tasks)}); the two decision sets come from one "
            "screening run, not two independent reviewers."
        )

    if reasons:
        return {
            "error": "IDENTICAL_SOURCES",
            "reasons": reasons,
            "fingerprint_a": fp_a,
            "fingerprint_b": fp_b,
            "common_records": len(common_ids),
        }
    return None


def check_reviewer_coverage(
    rev_a_data: Dict[str, Dict[str, Any]],
    rev_b_data: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """H-27: reviewer coverage check — unreviewed records must be disclosed.

    Records present in only one reviewer's file never enter the confusion
    matrix. A gap raises ``coverage_warning`` (coverage_status=WARNING, i.e.
    non-PASS) without blocking: legitimately complete inputs stay rc=0/PASS.
    """
    a_ids = set(rev_a_data)
    b_ids = set(rev_b_data)
    union = a_ids | b_ids
    a_missing = sorted(b_ids - a_ids)  # only B reviewed these -> A missed them
    b_missing = sorted(a_ids - b_ids)  # only A reviewed these -> B missed them
    warning = bool(a_missing or b_missing)
    return {
        "union_records": len(union),
        "reviewer_a_count": len(a_ids),
        "reviewer_b_count": len(b_ids),
        "common_records": len(a_ids & b_ids),
        "missing_from_reviewer_a": a_missing,
        "missing_from_reviewer_b": b_missing,
        "coverage_warning": warning,
        "coverage_status": "WARNING" if warning else "PASS",
    }


def calculate_cohens_kappa(
    reviewer_a_map: Dict[str, Dict[str, Any]],
    reviewer_b_map: Dict[str, Dict[str, Any]],
    categories: List[str] = ["Include", "Exclude", "Uncertain"]
) -> Dict[str, Any]:
    """
    Calculate 3-class Cohen's Kappa, Binary Kappa (Include vs Non-Include),
    observed agreement, and confusion matrix.
    """
    common_ids = sorted(list(set(reviewer_a_map.keys()) & set(reviewer_b_map.keys())))
    n = len(common_ids)

    if n == 0:
        return {"error": "No overlapping record IDs found between Reviewer A and Reviewer B."}

    # 2026-09-15（集群审查 P1）：无法识别的裁决不得被 `cat_to_idx.get(stat, 2)` 静默
    # 塞进 Uncertain 格——那等于把「读不到」算成「两方都判待定」，制造虚假一致。
    unreadable = sorted(
        rid for rid in common_ids
        if reviewer_a_map[rid].get("status") is None
        or reviewer_b_map[rid].get("status") is None)
    if unreadable:
        return {"error": "UNREADABLE_DECISIONS: %d 条共同记录的裁决无法识别（例：%s）；"
                         "拒绝据此计算 κ——「读不到」不等于「两方都判待定」。"
                         % (len(unreadable), ", ".join(unreadable[:5]))}

    # Build 3x3 Confusion Matrix
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    num_cats = len(categories)
    matrix = [[0 for _ in range(num_cats)] for _ in range(num_cats)]

    for rid in common_ids:
        stat_a = reviewer_a_map[rid]["status"]
        stat_b = reviewer_b_map[rid]["status"]
        idx_a = cat_to_idx.get(stat_a, 2)
        idx_b = cat_to_idx.get(stat_b, 2)
        matrix[idx_a][idx_b] += 1

    # Observed agreement po
    agreed_count = sum(matrix[i][i] for i in range(num_cats))
    po = agreed_count / n

    # Expected agreement pe
    row_sums = [sum(matrix[i][j] for j in range(num_cats)) for i in range(num_cats)]
    col_sums = [sum(matrix[i][j] for i in range(num_cats)) for j in range(num_cats)]

    pe = sum((row_sums[i] * col_sums[i]) for i in range(num_cats)) / (n * n)

    if 1.0 - pe == 0:
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1.0 - pe)

    # Standard Error and 95% Confidence Interval for Cohen's Kappa
    # Formula: SE = sqrt(po * (1 - po) / (n * (1 - pe)^2))
    denom = (1.0 - pe)
    if denom > 0 and po < 1.0 and po > 0:
        se_kappa = math.sqrt((po * (1.0 - po)) / (n * (denom ** 2)))
        ci_lower = max(-1.0, kappa - 1.96 * se_kappa)
        ci_upper = min(1.0, kappa + 1.96 * se_kappa)
    else:
        se_kappa = 0.0
        ci_lower = kappa
        ci_upper = kappa

    # Binary Kappa (Include vs Rest [Exclude + Uncertain])
    bin_matrix = [[0, 0], [0, 0]]
    for rid in common_ids:
        a_is_inc = 1 if reviewer_a_map[rid]["status"] == "Include" else 0
        b_is_inc = 1 if reviewer_b_map[rid]["status"] == "Include" else 0
        bin_matrix[1 - a_is_inc][1 - b_is_inc] += 1

    bin_agreed = bin_matrix[0][0] + bin_matrix[1][1]
    bin_po = bin_agreed / n
    bin_r0 = bin_matrix[0][0] + bin_matrix[0][1]
    bin_r1 = bin_matrix[1][0] + bin_matrix[1][1]
    bin_c0 = bin_matrix[0][0] + bin_matrix[1][0]
    bin_c1 = bin_matrix[0][1] + bin_matrix[1][1]
    bin_pe = ((bin_r0 * bin_c0) + (bin_r1 * bin_c1)) / (n * n)
    bin_kappa = (bin_po - bin_pe) / (1.0 - bin_pe) if (1.0 - bin_pe) > 0 else (1.0 if bin_po == 1.0 else 0.0)

    # Interpretation based on Landis & Koch (1977)
    if kappa >= 0.81:
        interpretation = "Almost Perfect (极佳一致性 - 符合顶级发表标准)"
        action_recommendation = "两评阅员裁决极度一致，一致通过项直接纳入，仅需对极少数分歧项进行人工确认。"
    elif kappa >= 0.61:
        interpretation = "Substantial (高度良好一致性 - 符合 PRISMA 标准)"
        action_recommendation = "一致通过项直接进入下一阶段，所有分歧项交由第三评阅人/资深学者进行争议仲裁。"
    elif kappa >= 0.41:
        interpretation = "Moderate (中度一致 - 存在边界模糊)"
        action_recommendation = "两评阅员存在一定分歧，建议召开双人对齐会议讨论判准，并对所有分歧项进行全面双审仲裁。"
    elif kappa >= 0.21:
        interpretation = "Fair (一般一致 - 判准执行松散)"
        action_recommendation = "一致性较低，说明纳入/排除标准存在较多歧义，强烈建议重构标准并在微调后重新初筛。"
    else:
        interpretation = "Slight / Poor (微弱或近乎随机一致 - 不合格)"
        action_recommendation = "初筛标准严重失真或未被正确理解，初筛结果不可直接用于系统综述发表，必须重新制定标准！"

    # Identify discrepancies
    discrepancies = []
    agreed_records = []
    for rid in common_ids:
        item_a = reviewer_a_map[rid]
        item_b = reviewer_b_map[rid]
        if item_a["status"] == item_b["status"]:
            agreed_records.append({
                "id": rid,
                "title": item_a.get("title") or item_b.get("title", ""),
                "agreed_status": item_a["status"],
                "reason_a": item_a.get("reason_detail", ""),
                "reason_b": item_b.get("reason_detail", "")
            })
        else:
            discrepancies.append({
                "id": rid,
                "title": item_a.get("title") or item_b.get("title", ""),
                "status_reviewer_a": item_a["status"],
                "status_reviewer_b": item_b["status"],
                "reason_code_a": item_a.get("reason_code", ""),
                "reason_detail_a": item_a.get("reason_detail", ""),
                "reason_code_b": item_b.get("reason_code", ""),
                "reason_detail_b": item_b.get("reason_detail", ""),
                "arbitration_required": True
            })

    return {
        "sample_size": n,
        # P2-10：低于最小样本量时 κ 方差极大，"自选子集"极易刷出 1.000。
        # 与 coverage_status 同一约定：告警不阻断，但产物必须显示非 PASS。
        "sample_status": "PASS" if n >= MIN_COMMON_RECORDS else "UNDERPOWERED",
        "min_common_records": MIN_COMMON_RECORDS,
        "categories": categories,
        "confusion_matrix": matrix,
        "observed_agreement": round(po, 4),
        "expected_agreement": round(pe, 4),
        "cohens_kappa": round(kappa, 4),
        "kappa_95_ci": (round(ci_lower, 4), round(ci_upper, 4)),
        "binary_kappa_include_vs_other": round(bin_kappa, 4),
        "binary_observed_agreement": round(bin_po, 4),
        "interpretation": interpretation,
        "action_recommendation": action_recommendation,
        "agreed_count": agreed_count,
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "agreed_records": agreed_records
    }


def generate_markdown_report(metrics: Dict[str, Any], reviewer_a_name: str, reviewer_b_name: str) -> str:
    """Generate a clean PRISMA 2020 Item 8 compliant Markdown summary."""
    n = metrics["sample_size"]
    kappa = metrics["cohens_kappa"]
    ci = metrics["kappa_95_ci"]
    po = metrics["observed_agreement"] * 100
    mat = metrics["confusion_matrix"]
    cats = metrics["categories"]

    md = []
    md.append("# PRISMA 2020 Item 8 双评阅人背对背独立初筛一致性检验报告\n")
    md.append(f"- **审查总样本量 (N)**: {n} 篇")
    md.append(f"- **评阅人 A (Reviewer A)**: `{reviewer_a_name}`")
    md.append(f"- **评阅人 B (Reviewer B)**: `{reviewer_b_name}`")
    md.append(f"- **观测一致率 (Observed Agreement $P_o$)**: **{po:.2f}%** ({metrics['agreed_count']}/{n})")
    md.append(f"- **Cohen's Kappa 系数 (κ)**: **{kappa:.3f}** (95% CI: [{ci[0]:.3f}, {ci[1]:.3f}])")
    md.append(f"- **二分类 Cohen's Kappa (Include vs 其它)**: **{metrics['binary_kappa_include_vs_other']:.3f}**")
    md.append(f"- **一致性评定 (Landis & Koch)**: **{metrics['interpretation']}**")
    md.append(f"- **分歧文献量 (Discrepancies)**: **{metrics['discrepancy_count']} 篇** (需仲裁)\n")

    # H-27: reviewer coverage section — always disclosed, WARNING when a
    # reviewer missed records that the other one reviewed.
    coverage = metrics.get("coverage")
    if coverage:
        md.append("## 〇、评阅覆盖率核查 (Reviewer Coverage Check)\n")
        md.append(f"- **覆盖率状态 (Coverage Status)**: **{coverage['coverage_status']}**")
        md.append(
            f"- Reviewer A 已评 **{coverage['reviewer_a_count']}/{coverage['union_records']}** 篇，"
            f"Reviewer B 已评 **{coverage['reviewer_b_count']}/{coverage['union_records']}** 篇，"
            f"双方共同评阅 **{coverage['common_records']}** 篇（κ 仅基于共同评阅样本计算）"
        )
        if coverage["missing_from_reviewer_b"]:
            preview = ", ".join(coverage["missing_from_reviewer_b"][:10])
            if len(coverage["missing_from_reviewer_b"]) > 10:
                preview += ", ..."
            md.append(
                f"- **⚠ WARNING**: Reviewer B 缺审 **{len(coverage['missing_from_reviewer_b'])}** 篇"
                f"（未进入 κ 计算）: `{preview}`"
            )
        if coverage["missing_from_reviewer_a"]:
            preview = ", ".join(coverage["missing_from_reviewer_a"][:10])
            if len(coverage["missing_from_reviewer_a"]) > 10:
                preview += ", ..."
            md.append(
                f"- **⚠ WARNING**: Reviewer A 缺审 **{len(coverage['missing_from_reviewer_a'])}** 篇"
                f"（未进入 κ 计算）: `{preview}`"
            )
        md.append("")

    md.append("## 一、评阅交叉混淆矩阵 (Contingency Matrix)\n")
    header = "| Reviewer A \\ Reviewer B | " + " | ".join(cats) + " | 合计 |"
    md.append(header)
    md.append("|:---|:---:|:---:|:---:|:---:|")
    for i, cat in enumerate(cats):
        row_vals = mat[i]
        row_sum = sum(row_vals)
        md.append(f"| **{cat}** | " + " | ".join(str(v) for v in row_vals) + f" | **{row_sum}** |")
    col_sums = [sum(mat[i][j] for i in range(len(cats))) for j in range(len(cats))]
    md.append("| **合计** | " + " | ".join(f"**{cs}**" for cs in col_sums) + f" | **{n}** |\n")

    md.append("## 二、执行建议与流转规程 (Action Recommendation)\n")
    md.append(f"> {metrics['action_recommendation']}\n")

    if metrics["discrepancies"]:
        md.append("## 三、待仲裁分歧文献清单 (Disagreement Arbitration Queue)\n")
        md.append("| 文献 ID | 标题 | Reviewer A | Reviewer B | 分歧类型 | 推荐仲裁动作 |")
        md.append("|:---|:---|:---:|:---:|:---|:---|")
        for d in metrics["discrepancies"][:30]:
            disc_type = f"{d['status_reviewer_a']} vs {d['status_reviewer_b']}"
            t = (d['title'][:40] + "...") if len(d['title']) > 40 else d['title']
            md.append(f"| `{d['id']}` | {t} | {d['status_reviewer_a']} | {d['status_reviewer_b']} | `{disc_type}` | 资深专家全文复核 |")
        if len(metrics["discrepancies"]) > 30:
            md.append(f"\n*(仅展示前 30 项分歧，完整待仲裁队列已导出至 JSON/CSV 文件)*\n")

    return "\n".join(md)


def export_prisma_audit_csv(
    metrics: Dict[str, Any],
    rev_a_map: Dict[str, Dict[str, Any]],
    rev_b_map: Dict[str, Dict[str, Any]],
    output_path: Path
):
    """
    Export PRISMA-compliant CSV containing decision traceability for every item.
    """
    common_ids = sorted(list(set(rev_a_map.keys()) & set(rev_b_map.keys())))
    fieldnames = [
        "record_id",
        "title",
        "reviewer_a_decision",
        "reviewer_a_code",
        "reviewer_a_reason",
        "reviewer_b_decision",
        "reviewer_b_code",
        "reviewer_b_reason",
        "consensus_status",
        "arbitrated_decision",
        "arbitrator_notes"
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rid in common_ids:
            a = rev_a_map[rid]
            b = rev_b_map[rid]
            is_agreed = (a["status"] == b["status"])
            writer.writerow({
                "record_id": rid,
                "title": a.get("title") or b.get("title", ""),
                "reviewer_a_decision": a["status"],
                "reviewer_a_code": a.get("reason_code", ""),
                "reviewer_a_reason": a.get("reason_detail", ""),
                "reviewer_b_decision": b["status"],
                "reviewer_b_code": b.get("reason_code", ""),
                "reviewer_b_reason": b.get("reason_detail", ""),
                "consensus_status": "AGREED" if is_agreed else "DISCREPANCY",
                "arbitrated_decision": a["status"] if is_agreed else "",
                "arbitrator_notes": "" if is_agreed else "PENDING_ARBITRATION"
            })


def export_arbitration_queue(metrics: Dict[str, Any], output_path: Path):
    """Export discrepancy items as JSON for human or arbitrator subagent."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coverage = metrics.get("coverage") or {}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_discrepancies": len(metrics["discrepancies"]),
            "coverage_warning": bool(coverage.get("coverage_warning")),
            "coverage_status": coverage.get("coverage_status"),
            "items": metrics["discrepancies"]
        }, f, indent=2, ensure_ascii=False)


def run_selftest():
    """Built-in self-test to verify math and contingency matrix calculation."""
    rev_a = {
        "REC01": {"id": "REC01", "status": "Include", "title": "Paper 1"},
        "REC02": {"id": "REC02", "status": "Include", "title": "Paper 2"},
        "REC03": {"id": "REC03", "status": "Exclude", "title": "Paper 3"},
        "REC04": {"id": "REC04", "status": "Exclude", "title": "Paper 4"},
        "REC05": {"id": "REC05", "status": "Exclude", "title": "Paper 5"},
        "REC06": {"id": "REC06", "status": "Uncertain", "title": "Paper 6"},
        "REC07": {"id": "REC07", "status": "Include", "title": "Paper 7"},
        "REC08": {"id": "REC08", "status": "Exclude", "title": "Paper 8"},
        "REC09": {"id": "REC09", "status": "Include", "title": "Paper 9"},
        "REC10": {"id": "REC10", "status": "Exclude", "title": "Paper 10"},
    }
    rev_b = {
        "REC01": {"id": "REC01", "status": "Include", "title": "Paper 1"},
        "REC02": {"id": "REC02", "status": "Include", "title": "Paper 2"},
        "REC03": {"id": "REC03", "status": "Exclude", "title": "Paper 3"},
        "REC04": {"id": "REC04", "status": "Exclude", "title": "Paper 4"},
        "REC05": {"id": "REC05", "status": "Exclude", "title": "Paper 5"},
        "REC06": {"id": "REC06", "status": "Uncertain", "title": "Paper 6"},
        "REC07": {"id": "REC07", "status": "Uncertain", "title": "Paper 7"},
        "REC08": {"id": "REC08", "status": "Exclude", "title": "Paper 8"},
        "REC09": {"id": "REC09", "status": "Exclude", "title": "Paper 9"},
        "REC10": {"id": "REC10", "status": "Exclude", "title": "Paper 10"},
    }
    res = calculate_cohens_kappa(rev_a, rev_b)
    assert res["sample_size"] == 10
    assert res["agreed_count"] == 8
    assert res["discrepancy_count"] == 2
    assert res["observed_agreement"] == 0.8
    assert res["cohens_kappa"] > 0.65
    print(f"Self-test PASSED! Cohen's Kappa: {res['cohens_kappa']}, Observed agreement: {res['observed_agreement']}")


def main():
    parser = argparse.ArgumentParser(
        description="ScholarFlow PRISMA 2020 Item 8 Dual-Reviewer Blind Screening Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate two separate reviewer outputs:
  python calculate_screening_agreement.py -a reviewer_a.json -b reviewer_b.json -o report.md --csv audit.csv

  # Run built-in unit tests:
  python calculate_screening_agreement.py --test
        """
    )
    parser.add_argument("-a", "--reviewer-a", type=str, help="Path to Reviewer A decisions (.json or .csv)")
    parser.add_argument("-b", "--reviewer-b", type=str, help="Path to Reviewer B decisions (.json or .csv)")
    parser.add_argument("-o", "--output-md", type=str, help="Path to write Markdown summary report")
    parser.add_argument("--csv", "--output-csv", type=str, help="Path to write PRISMA Item 8 audit CSV")
    parser.add_argument("--arbitration-json", type=str, help="Path to write arbitration queue JSON")
    parser.add_argument("--test", action="store_true", help="Run built-in verification self-test")

    args = parser.parse_args()

    if args.test:
        run_selftest()
        sys.exit(0)

    if not args.reviewer_a or not args.reviewer_b:
        parser.print_help()
        sys.exit(1)

    path_a = Path(args.reviewer_a)
    path_b = Path(args.reviewer_b)

    rev_a_data = load_decisions(path_a)
    rev_b_data = load_decisions(path_b)

    # 2026-09-15 gate 0（集群审查 P1）：裁决字段读不出来的输入必须显式拒绝。
    # 旧实现把未识别值一律归一为 Uncertain，于是「一条裁决都没读进来」与「两评阅人
    # 都判待定」在产物里同形——逐条对立的两份初筛会被判 κ=1.000「Almost Perfect」
    # 且 rc=0、零告警，分歧仲裁队列为空。读不到就是读不到，不得折成一致。
    unreadable_a = summarize_unreadable(rev_a_data)
    unreadable_b = summarize_unreadable(rev_b_data)
    if unreadable_a or unreadable_b:
        payload = {
            "error": "UNREADABLE_DECISIONS",
            "reviewer_a": {"unreadable": len(unreadable_a),
                           "samples": [[r, s] for r, s in unreadable_a[:10]]},
            "reviewer_b": {"unreadable": len(unreadable_b),
                           "samples": [[r, s] for r, s in unreadable_b[:10]]},
            "accepted_status_keys": list(STATUS_KEYS),
            "accepted_id_keys": list(RECORD_ID_KEYS),
            "hint": "裁决字段无法识别（或整列为空）。请使用 canonical 键名 "
                    "record_id / screening_status，或用 status / decision。"
                    "不得把这些记录当作 Uncertain 计入一致性。",
        }
        sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        sys.stderr.write(
            "[-] UNREADABLE_DECISIONS: Reviewer A 有 %d 条、Reviewer B 有 %d 条记录的"
            "裁决无法识别；拒绝签发一致性结论（PRISMA 2020 Item 8 要求可核验的双评阅"
            "人裁决，而非把读不到的折成一致）。\n"
            % (len(unreadable_a), len(unreadable_b))
        )
        sys.exit(1)

    # H-27 gate 1: same-source inputs must be rejected before any kappa is
    # certified (rc=1, structured IDENTICAL_SOURCES, no passing report).
    identical = check_source_independence(path_a, path_b, rev_a_data, rev_b_data)
    if identical:
        sys.stderr.write(json.dumps(identical, ensure_ascii=False, indent=2) + "\n")
        sys.stderr.write(
            "[-] IDENTICAL_SOURCES: Reviewer A/B inputs are not independent; "
            "refusing to certify kappa agreement (PRISMA Item 8 requires two "
            "independent reviewers).\n"
        )
        sys.exit(1)

    metrics = calculate_cohens_kappa(rev_a_data, rev_b_data)

    if "error" in metrics:
        print(f"Error: {metrics['error']}", file=sys.stderr)
        sys.exit(1)

    # H-27 gate 2: reviewer coverage — disclose unreviewed records without
    # blocking legitimately complete inputs (rc stays 0).
    coverage = check_reviewer_coverage(rev_a_data, rev_b_data)
    metrics["coverage"] = coverage
    # P2-10：低于最小共同样本量时必须显式告警——κ 在小样本上方差极大，
    # "自选若干条一致的记录"即可刷出 1.000，不得当作顶级一致性证据。
    if metrics.get("sample_status") == "UNDERPOWERED":
        sys.stderr.write(
            "[WARNING] sample too small: only %d common record(s) (minimum %d); "
            "kappa is not reliable at this size and a hand-picked agreeing subset "
            "will trivially reach 1.000.\n"
            % (metrics.get("sample_size"), metrics.get("min_common_records")))
    if coverage["coverage_warning"]:
        sys.stderr.write(
            "[WARNING] Reviewer coverage gap: Reviewer A reviewed %d/%d records, "
            "Reviewer B reviewed %d/%d records; kappa is computed on the %d common "
            "records only (missing ids are disclosed in the report).\n"
            % (
                coverage["reviewer_a_count"], coverage["union_records"],
                coverage["reviewer_b_count"], coverage["union_records"],
                coverage["common_records"],
            )
        )

    md_report = generate_markdown_report(metrics, path_a.name, path_b.name)

    if args.output_md:
        out_p = Path(args.output_md)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md_report, encoding="utf-8")
        print(f"Saved Markdown report to: {out_p}")
    else:
        print(md_report)

    if args.csv:
        csv_p = Path(args.csv)
        export_prisma_audit_csv(metrics, rev_a_data, rev_b_data, csv_p)
        print(f"Saved PRISMA audit CSV to: {csv_p}")

    if args.arbitration_json:
        arb_p = Path(args.arbitration_json)
        export_arbitration_queue(metrics, arb_p)
        print(f"Saved arbitration queue JSON to: {arb_p}")


if __name__ == "__main__":
    main()
