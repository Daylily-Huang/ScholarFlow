# -*- coding: utf-8 -*-
"""「非证据」语义的单一真源（2026-09-13 集群测试 P0 修复；H-05 二轮全量收口）。

背景：上游 EvidenceRecord 用多个字段表达"这条到底算不算证据"：
`support_type` / `claim_status` / `extracted_value` / `verification_status` /
`fulltext_verification_status`。
旧实现只在 `controversy_analyzer.resolve_evidence_weight()` 里按字面量
`["NOT_REPORTED", "NR"]` 匹配 `support_type`，于是：

- `support_type="NOT REPORTED"`（带空格的人类写法）→ 满权重；
- `claim_status="unchecked"` / `"inaccessible"` / `"cited_only"` → 满权重且完全不读；
- 结果是「没查」被当作「有证据」进入共识，可直接产出 STRONG_CONSENSUS。

第一轮修复把判定收成一处并归一化了空格/连字符；第二轮实测（H-05）证明标点仍可
逃逸（`Not reported.` / `NOT.REPORTED` / `N/R`），且 `REFERENCED_ONLY`（二级转引）
漏映射、空值缺省 fail-open。本轮收口：

1. **归一化表驱动全覆盖**：大小写折叠，空格/连字符/标点等一切非字母数字字符折叠为
   分隔符——所有写法变体与规范写法折叠到同一 token，再查同一张表；
2. **空值 fail-closed**：字段显式给出但为空串/纯标点/显式 null（可空的
   `extracted_value` 除外）→ `UNPARSEABLE`：排除出权重并在共识排除计数中可读，
   不再静默当有效；
3. **REFERENCED_ONLY 与 CITED_ONLY 同层零权**（二级转引不是一手证据）；
4. `resolve_non_evidence_class()`：消费端统一入口，优先消费归一化时基于**原始输入**
   判定的 `non_evidence_class`，保证「未声明」与「显式空声明」全链路语义一致。
"""

import re
from typing import Any, Dict, Optional

#: 归一化 token → 语义类别（表驱动，H-05）。键必须先过 `normalize_state_token()`。
NON_EVIDENCE_CLASSES = {
    "NOT_REPORTED": "NOT_REPORTED",   # 原文已查、作者未报告
    "NOTREPORTED": "NOT_REPORTED",
    "NR": "NOT_REPORTED",
    "N_R": "NOT_REPORTED",            # "N/R"、"N.R."、"n r"
    "N_A": "NOT_REPORTED",            # "N/A"、"N.A."
    "NA": "NOT_REPORTED",
    "NONE": "NOT_REPORTED",           # 字符串 "None"
    "NULL": "NOT_REPORTED",           # 字符串 "null"
    "NOT_AVAILABLE": "NOT_REPORTED",
    "UNCHECKED": "UNCHECKED",         # 没查（≠ 没报告）
    "NOT_CHECKED": "UNCHECKED",
    "UN_CHECKED": "UNCHECKED",        # "un-checked"
    "INACCESSIBLE": "INACCESSIBLE",   # 拿不到全文
    "NOT_ACCESSIBLE": "INACCESSIBLE",
    "CITED_ONLY": "CITED_ONLY",       # 仅转引他人数据
    "CITEDONLY": "CITED_ONLY",
    "REFERENCED_ONLY": "CITED_ONLY",  # 二级转引与 CITED_ONLY 同层零权（H-05/SYN-R-01）
    "REFERENCEDONLY": "CITED_ONLY",
    # P2-23（2026-09-15 集群审查）：`REFERENCED` 是**抽取域 `support_type` 的 canonical
    # 取值**（SKILL.md §四：转引他文的行必须是 support_type=REFERENCED，即 E3 二手证据；
    # 抽取侧由 `_resolve_support_type` 产出）。而本表此前只列 `REFERENCED_ONLY` /
    # `CITED_ONLY`——两侧词表对不上，二级转引以**满权重**进入共识分母。
    # （抽取侧修复后 REFERENCED 被正确产出，该缺口的实际暴露面随之变大。）
    "REFERENCED": "CITED_ONLY",
    "REFERENCED_WORK": "CITED_ONLY",  # 语义角色名，同层零权
}

#: 显式给出但无法解析出任何语义的值（空串/纯标点/显式 null）→ UNPARSEABLE：
#: 排除出权重并计数，不静默当有效（H-05 fail-closed）。
UNPARSEABLE_CLASS = "UNPARSEABLE"

#: evidence_record.schema.json 中合法可空的状态字段（"未抽取到值"是合法状态，
#: 显式 null 不得当 UNPARSEABLE）；其余状态字段的显式 null = 声明被抹除 → fail-closed。
NULLABLE_STATE_FIELDS = frozenset({"extracted_value"})

#: 会被检查的字段（顺序即优先级）
STATE_FIELDS = ("support_type", "claim_status", "extracted_value",
                "verification_status", "fulltext_verification_status")


def normalize_state_token(value: Any) -> str:
    """把上游标签写法归一化（H-05 表驱动全覆盖）。

    大小写折叠；空格/连字符/标点等一切非字母数字字符折叠为 "_"，连续折叠压缩、
    首尾剥离。因此 `"Not reported."` / `"NOT.REPORTED"` / `"N/R"` / `"not reported!"`
    与规范写法落入同一 token，标点逃逸不再绕过零权重隔离。
    """
    text = str(value or "").strip()
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "_", text)
    return text.strip("_").upper()


def classify_non_evidence(raw: Dict[str, Any]) -> Optional[str]:
    """判定记录是否属于「非证据」语义；返回类别名或 None。

    - 任一状态字段的写法变体命中 `NON_EVIDENCE_CLASSES` → 对应类别；
    - 字段**显式给出**（键存在）但值归一化后为空（空串/纯标点），或显式 null
      （可空的 `extracted_value` 除外）→ `UNPARSEABLE`（排除出权重并计数）；
    - 字段缺失（键不存在）→ 不发表意见，权重交由 `evidence_strength` 决定。
    """
    if not isinstance(raw, dict):
        return None
    for key in STATE_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if value is None:
            if key in NULLABLE_STATE_FIELDS:
                continue
            return UNPARSEABLE_CLASS
        token = normalize_state_token(value)
        if not token:
            return UNPARSEABLE_CLASS
        cls = NON_EVIDENCE_CLASSES.get(token)
        if cls:
            return cls
    return None


def resolve_non_evidence_class(record: Any) -> Optional[str]:
    """消费端统一入口：**一律从状态字段重新判定**，不信任入参的自声明结论。

    **P1（2026-09-15 集群审查）：自声明字段不得成为关停开关。** 旧实现只要
    `"non_evidence_class" in record` 就无条件返回其值，而 `load_input_data()` 接受宿主
    Agent 任意构造的 claim 对象——给一条 `support_type="NOT REPORTED"` 的记录加
    `"non_evidence_class": null` 即可跳过全部状态字段分类，该记录改由 `evidence_strength`
    计权（实测 weight=1.0、consensus_eligible=True、excluded_from_consensus 为空），
    3 条即产出 Level 1「Strong Prevailing Consensus」。这正是本套件威胁模型要防的
    「把自声明字段当授权依据」（README 明文否定「传了字段即已授权」的同类）。

    该短路原本是为幂等而设：归一化产物旧会**无条件写入** `support_type=None`，二次分类
    会把「上游未声明」误读成「显式空声明」。现已治源——`normalize_claim` 改为只在有值
    时写键（与 `claim_status` 一致），分类在原始输入与归一化产物上均幂等，短路随之
    移除，分类结果只由状态字段决定。
    """
    return classify_non_evidence(record)


def is_evidence_bearing(raw: Dict[str, Any]) -> bool:
    """是否属于"可承载证据"的记录（非证据/不可解析语义一律 False）。"""
    return resolve_non_evidence_class(raw) is None
