#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calculate_screening_agreement.py
--------------------------------
ScholarFlow PRISMA 2020 Item 8 Dual-Reviewer Blind Screening Evaluator.

Computes inter-rater agreement statistics (Cohen's Kappa κ, Observed Agreement,
Contingency Matrix) between two independent screening reviewers (e.g., SubAgent-A
and SubAgent-B), and outputs PRISMA-compliant audit trails and arbitration queues.

Standard Library Only (Zero third-party pip dependencies required).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

VALID_STATUSES = ["Include", "Exclude", "Uncertain"]

def normalize_status(val: str) -> str:
    """Normalize status string to Include, Exclude, or Uncertain."""
    if not val:
        return "Uncertain"
    s = str(val).strip().lower()
    if s in ["include", "included", "inc", "纳入", "yes", "y", "1"]:
        return "Include"
    elif s in ["exclude", "excluded", "exc", "排除", "no", "n", "0"]:
        return "Exclude"
    elif s in ["uncertain", "maybe", "borderline", "待定", "存疑", "u", "?"]:
        return "Uncertain"
    return "Uncertain"


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
                    rid = str(item.get("id") or item.get("rec_id") or item.get("doi") or item.get("title") or "")
                    if rid:
                        records[rid] = {
                            "id": rid,
                            "title": item.get("title", ""),
                            "status": normalize_status(item.get("status", "")),
                            "reason_code": item.get("reason_code", ""),
                            "reason_detail": item.get("reason_detail", ""),
                            "confidence_score": float(item.get("confidence_score", 0.0)) if item.get("confidence_score") is not None else None
                        }
            elif isinstance(data, dict):
                for rid, item in data.items():
                    if isinstance(item, dict):
                        records[str(rid)] = {
                            "id": str(rid),
                            "title": item.get("title", ""),
                            "status": normalize_status(item.get("status", "")),
                            "reason_code": item.get("reason_code", ""),
                            "reason_detail": item.get("reason_detail", ""),
                            "confidence_score": float(item.get("confidence_score", 0.0)) if item.get("confidence_score") is not None else None
                        }
                    else:
                        records[str(rid)] = {
                            "id": str(rid),
                            "title": "",
                            "status": normalize_status(str(item)),
                            "reason_code": "",
                            "reason_detail": "",
                            "confidence_score": None
                        }

    elif suffix in [".csv", ".tsv"]:
        delimiter = "\t" if suffix == ".tsv" else ","
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                rid = row.get("id") or row.get("rec_id") or row.get("ID") or row.get("doi") or row.get("title") or ""
                if rid:
                    status_raw = row.get("status") or row.get("Status") or row.get("decision") or ""
                    records[rid] = {
                        "id": rid,
                        "title": row.get("title", ""),
                        "status": normalize_status(status_raw),
                        "reason_code": row.get("reason_code", row.get("code", "")),
                        "reason_detail": row.get("reason_detail", row.get("reason", "")),
                        "confidence_score": float(row.get("confidence_score", 0.0)) if row.get("confidence_score") else None
                    }
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .json or .csv")

    return records


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
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_discrepancies": len(metrics["discrepancies"]),
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

    metrics = calculate_cohens_kappa(rev_a_data, rev_b_data)

    if "error" in metrics:
        print(f"Error: {metrics['error']}", file=sys.stderr)
        sys.exit(1)

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
