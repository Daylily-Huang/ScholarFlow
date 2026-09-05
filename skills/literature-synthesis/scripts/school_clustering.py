#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
School & Paradigm Clustering Analyzer (school_clustering.py)
-----------------------------------------------------------
Part of the `literature-synthesis` skill.

Analyzes collections of studies to:
1. Cluster papers by methodological paradigm and theoretical schools.
2. Formally distinguish between genuine "ESTABLISHED SCHOOL" and methodological "ANALYTICAL GROUPING".
3. Map chronological paradigm shifts and methodological evolution over time.
4. Highlight paradigm fault lines and core assumptions.

Usage:
    python school_clustering.py --input studies.json --format markdown
    python school_clustering.py --input studies.json --output school_landscape.json
    python school_clustering.py --help
"""

import argparse
import json
import sys
import io
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scholarly Paradigm & School Clustering Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example JSON input structure:
[
  {
    "paper_id": "Zhang2010",
    "year": 2010,
    "authors": "Zhang et al.",
    "paradigm": "Traditional Transect & Pellet Counts",
    "method": "Line transect pellet counting",
    "core_assumption": "Constant defecation rate and uniform visibility",
    "school_label": "Field Ecology Survey Group",
    "is_established_school": false
  },
  {
    "paper_id": "Borchers2008",
    "year": 2008,
    "authors": "Borchers & Efford",
    "paradigm": "Spatially Explicit Capture-Recapture",
    "method": "SECR maximum likelihood",
    "core_assumption": "Individual activity centers with distance-decay detection",
    "school_label": "Otago-St Andrews Biometrics School",
    "is_established_school": true
  }
]
        """
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to input JSON file containing studies metadata."
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path to save output report (default: stdout)."
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown", "summary"],
        default="markdown",
        help="Output format: json, markdown, or summary (default: markdown)."
    )
    return parser.parse_args()


def load_input_data(filepath: str) -> List[Dict[str, Any]]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")
        
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if isinstance(data, dict) and "studies" in data:
        data = data["studies"]
    elif not isinstance(data, list):
        raise ValueError("Input JSON must be an array of study objects or an object with a 'studies' array.")
        
    return data


def cluster_by_paradigm(studies: List[Dict[str, Any]]) -> Dict[str, Any]:
    clusters = defaultdict(list)
    
    for s in studies:
        paradigm = s.get("paradigm") or s.get("school_label") or "Unclassified Paradigm"
        clusters[paradigm.strip()].append(s)
        
    results = {}
    for paradigm, papers in clusters.items():
        years = [p.get("year") for p in papers if isinstance(p.get("year"), int)]
        earliest_yr = min(years) if years else "Unknown"
        latest_yr = max(years) if years else "Unknown"
        
        methods = list(set(p.get("method") for p in papers if p.get("method")))
        assumptions = list(set(p.get("core_assumption") for p in papers if p.get("core_assumption")))
        
        # Check school status
        established_votes = [p.get("is_established_school", False) for p in papers]
        is_established = any(established_votes)
        
        status_label = "ESTABLISHED SCHOOL" if is_established else "ANALYTICAL GROUPING"
        
        results[paradigm] = {
            "paradigm_name": paradigm,
            "status": status_label,
            "study_count": len(papers),
            "temporal_range": f"{earliest_yr} - {latest_yr}",
            "earliest_year": earliest_yr,
            "latest_year": latest_yr,
            "representative_papers": [p.get("paper_id", "Unknown") for p in papers],
            "common_methods": methods,
            "core_assumptions": assumptions,
            "papers": papers
        }
        
    return results


def detect_paradigm_shifts(clustered: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect chronological progression across paradigms."""
    timeline = []
    for name, c in clustered.items():
        if isinstance(c["earliest_year"], int):
            timeline.append({
                "paradigm": name,
                "status": c["status"],
                "start": c["earliest_year"],
                "end": c["latest_year"],
                "count": c["study_count"]
            })
            
    timeline.sort(key=lambda x: x["start"])
    shifts = []
    for i in range(len(timeline) - 1):
        prev_p = timeline[i]
        next_p = timeline[i+1]
        if prev_p["start"] < next_p["start"]:
            shifts.append({
                "transition": f"{prev_p['paradigm']} ({prev_p['start']}-{prev_p['end']}) → {next_p['paradigm']} ({next_p['start']}-{next_p['end']})",
                "description": f"Methodological evolution from earlier paradigm [{prev_p['paradigm']}] to contemporary paradigm [{next_p['paradigm']}]."
            })
            
    return shifts


def format_markdown_report(clustered: Dict[str, Any], shifts: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# 学派谱系与研究范式演进分析报告 (School & Paradigm Landscape Report)")
    lines.append("")
    lines.append(f"> **生成模块**：`school_clustering.py` | **识别范式数**：{len(clustered)}")
    lines.append("")
    lines.append("## 1. 范式与学派特征总览")
    lines.append("")
    lines.append("| 范式 / 学派名称 | 类别判定 | 文献篇数 | 时间跨度 | 代表性文献 | 核心方法 |")
    lines.append("|---|---|---|---|---|---|")
    for name, c in clustered.items():
        status_badge = f"`{c['status']}`"
        reps = ", ".join(c["representative_papers"][:3])
        if len(c["representative_papers"]) > 3:
            reps += f" (等 {len(c['representative_papers'])} 篇)"
        meth = ", ".join(c["common_methods"][:2]) if c["common_methods"] else "N/A"
        lines.append(f"| **{name}** | {status_badge} | {c['study_count']} | {c['temporal_range']} | {reps} | {meth} |")
    lines.append("")
    
    if shifts:
        lines.append("## 2. 范式更迭与时间演进轴 (Chronological Paradigm Shifts)")
        lines.append("")
        for s in shifts:
            lines.append(f"- 🔄 **{s['transition']}**")
            lines.append(f"  - *{s['description']}*")
        lines.append("")
        
    lines.append("## 3. 范式核心假定与断层面对决")
    lines.append("")
    for name, c in clustered.items():
        lines.append(f"### {name} ({c['status']})")
        lines.append(f"- **研究文献**：{', '.join(c['representative_papers'])}")
        lines.append(f"- **核心理论假定**：{'; '.join(c['core_assumptions']) if c['core_assumptions'] else '未显式注明'}")
        lines.append(f"- **常用方法工具**：{', '.join(c['common_methods']) if c['common_methods'] else '未显式注明'}")
        lines.append("")
        
    return "\n".join(lines)


def main():
    args = parse_args()
    try:
        studies = load_input_data(args.input)
    except Exception as e:
        sys.stderr.write(f"Error loading input studies: {e}\n")
        sys.exit(1)
        
    clustered = cluster_by_paradigm(studies)
    shifts = detect_paradigm_shifts(clustered)
    
    output_obj = {
        "paradigms": clustered,
        "paradigm_shifts": shifts
    }
    
    if args.format == "json":
        output_content = json.dumps(output_obj, indent=2, ensure_ascii=False)
    elif args.format == "summary":
        lines = [f"Found {len(clustered)} paradigm clusters:"]
        for k, v in clustered.items():
            lines.append(f"- {k} [{v['status']}]: {v['study_count']} studies ({v['temporal_range']})")
        output_content = "\n".join(lines)
    else:
        output_content = format_markdown_report(clustered, shifts)
        
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_content)
        print(f"[SUCCESS] School clustering written to {args.output}")
    else:
        print(output_content)


if __name__ == "__main__":
    main()
