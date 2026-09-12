# -*- coding: utf-8 -*-
"""「非证据」语义的单一真源（2026-09-13 集群测试 P0 修复）。

背景：上游 EvidenceRecord 用多个字段表达"这条到底算不算证据"：
`support_type` / `claim_status` / `extracted_value` / `verification_status`。
旧实现只在 `controversy_analyzer.resolve_evidence_weight()` 里按字面量
`["NOT_REPORTED", "NR"]` 匹配 `support_type`，于是：

- `support_type="NOT REPORTED"`（带空格的人类写法）→ 满权重；
- `claim_status="unchecked"` / `"inaccessible"` / `"cited_only"` → 满权重且完全不读；
- 结果是「没查」被当作「有证据」进入共识，可直接产出 STRONG_CONSENSUS。

本模块把判定收成一处，供综合链路的权重与资格检查共同使用。
"""

import re
from typing import Any, Dict, Optional

#: 语义类别（与 schemas/evidence_record.schema.json 的枚举对齐，并容忍写法差异）
NON_EVIDENCE_CLASSES = {
    "NOT_REPORTED": "NOT_REPORTED",   # 原文已查、作者未报告
    "NOTREPORTED": "NOT_REPORTED",
    "NR": "NOT_REPORTED",
    "UNCHECKED": "UNCHECKED",         # 没查（≠ 没报告）
    "NOT_CHECKED": "UNCHECKED",
    "INACCESSIBLE": "INACCESSIBLE",   # 拿不到全文
    "NOT_ACCESSIBLE": "INACCESSIBLE",
    "CITED_ONLY": "CITED_ONLY",       # 仅转引他人数据
    "CITEDONLY": "CITED_ONLY",
}

#: 会被检查的字段（顺序即优先级）
STATE_FIELDS = ("support_type", "claim_status", "extracted_value",
                "verification_status", "fulltext_verification_status")


def normalize_state_token(value: Any) -> str:
    """把上游标签写法归一化：去空格/连字符、统一大写。"""
    return re.sub(r"[\s\-]+", "_", str(value or "").strip()).upper()


def classify_non_evidence(raw: Dict[str, Any]) -> Optional[str]:
    """判定记录是否属于「非证据」语义；返回类别名或 None。"""
    if not isinstance(raw, dict):
        return None
    for key in STATE_FIELDS:
        token = normalize_state_token(raw.get(key))
        if token in NON_EVIDENCE_CLASSES:
            return NON_EVIDENCE_CLASSES[token]
    return None


def is_evidence_bearing(raw: Dict[str, Any]) -> bool:
    """是否属于"可承载证据"的记录（非证据语义一律 False）。"""
    return classify_non_evidence(raw) is None
