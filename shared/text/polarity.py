# -*- coding: utf-8 -*-
"""
shared/text/polarity.py — ScholarFlow 共享否定/反义（极性）词表模块（B2 批次）。

单一真源（H-02/H-82，2026-09-13 第二轮集群测试决议）：
`claim_alignment.py`（B2）、`debate_handoff.py`（B3 接入）等消费方必须从这里 import，
禁止各自复制词表。H-02 的根因正是三处词表互不一致（neither/nor、n't 收缩词、
abolish/reverse 类反转动词只在一处存在）。

公开导出接口（一次定型，B3 依赖；新增成员只能追加不能改名）：
- ``NEGATION_MARKERS``      tuple[str]   否定标记全集（文档/再导出用）
- ``NEGATION_TOKEN_RE``     re.Pattern   否定标记编译正则（英文词边界；中文带排除集）
- ``AECE_NEGATION_MARKERS`` tuple[str]   AECE 层（context_expansion）使用的子集
- ``AECE_NEGATION_RE``      re.Pattern   AECE 子集编译正则
- ``CONTRASTIVE_MARKERS``   tuple[str]   对比/转折标记（子句切分）
- ``CLAUSE_SPLIT_RE``       re.Pattern   子句切分正则
- ``ANTONYM_PAIRS``         tuple        反义类 ((正向词...), (反向词...))，词根式子串匹配
- ``ANTONYM_LOOKUP``        dict         词 -> (类索引, "POS"/"NEG")
- ``REVERSAL_MARKERS``      tuple[str]   反转动词（abolish/reverse/eliminate/overturn...）
- ``REVERSAL_RE``           re.Pattern   反转动词编译正则
- ``DOUBLE_NEGATION_RES``   tuple        双否定短语正则（not unknown / cannot but / cannot exclude...）
- ``net_negation_count(text) -> int``
- ``is_negated(text) -> bool``           该文本净极性是否为否定（双否定已折算）
- ``find_negations(text) -> List[str]``  命中的否定标记原文（detect_negation 兼容接口）
- ``split_clauses(text) -> List[str]``
- ``clause_polarity(clause) -> dict``    单子句极性：{"negated", "classes", "has_reversal"}
- ``polarity_signature(text) -> dict``   全文极性签名（子句翻转合并）
- ``predicate_stem(word) -> str``        谓词词干（去屈折，供子句定位）
- ``check_polarity(claim_text, evidence_text, predicate="", obj="") -> Optional[dict]``
    三值判定：``{"verdict": None | "CONTRADICTORY" | "UNRESOLVED", "reason": str}``
    - None           —— 方向一致（或无可比的极性问题）
    - CONTRADICTORY  —— 主张方向与证据子句方向相反（含否定奇偶/反义类失配）
    - UNRESOLVED     —— 极性签名不可比（BOTH / 谓词-宾语跨分支 / 反转不可解），fail-closed 交人工

极性语义（H-01 三值化 + 子句绑定）：
1. 否定只作用于其所在子句（split_clauses），避免远距离否定误挡（H-82 "Unlike drug B"）。
2. 双否定/否定负词成对折算为肯定（"not unknown"、"cannot but"、"cannot exclude"、
   中文"不排除"），H-82 正例成对落库不回归。
3. 反转动词（abolish/reverse/eliminate/overturn...）出现即翻转同子句方向词的极性
   （"reversed the increase" ≈ decrease），H-02/H-01 攻击面。
4. 相关子句 = 同时包含谓词与宾语的子句；谓词与宾语分属不同子句（方向分支分裂）
   → UNRESOLVED，不判 SUPPORTED（L613 短路的根治）。
5. 一侧签名 BOTH（同句同现 increase/decrease）→ UNRESOLVED，绝不静默跳过比较。

Python 3.9 兼容，仅标准库。
"""

import re
from typing import Any, Dict, List, Optional

__all__ = [
    "NEGATION_MARKERS", "NEGATION_TOKEN_RE",
    "AECE_NEGATION_MARKERS", "AECE_NEGATION_RE",
    "CONTRASTIVE_MARKERS", "CLAUSE_SPLIT_RE",
    "ANTONYM_PAIRS", "ANTONYM_LOOKUP",
    "REVERSAL_MARKERS", "REVERSAL_RE",
    "DOUBLE_NEGATION_RES",
    "net_negation_count", "is_negated", "find_negations",
    "split_clauses", "clause_polarity", "polarity_signature",
    "predicate_stem", "check_polarity",
]

# ---------------------------------------------------------------------------
# 1. 否定词表
# ---------------------------------------------------------------------------
# 英文一律词边界匹配（H-82：cannot 的 "not " 子串误报即旧实现的根因之一）。
# 中文否定带排除集：不同/不断/不过/不仅/不少/不久/不错/不论 等"否定字 + 非否定义"
# 的合成词不算否定（"不同样地间…显著增加" 必须仍 ALIGNED）。

NEGATION_MARKERS = (
    # --- English, word-boundary ---
    "not", "no", "never", "neither", "nor", "none", "without",
    "lack", "lacks", "lacking", "absence", "absent",
    "rarely", "seldom", "fail to", "fails to", "failed to", "failing to",
    "no evidence", "declined to", "decline to", "refuse to", "refused to",
    "cannot", "don't", "doesn't", "didn't", "can't", "won't", "wouldn't",
    "couldn't", "shouldn't", "isn't", "aren't", "wasn't", "weren't",
    "hasn't", "haven't", "hadn't",
    # --- Chinese ---
    "不", "未", "无显著", "没有", "并未", "并非", "并不",
    "缺乏", "缺少", "极少", "很少", "未见", "未发现", "未支持",
    "不能", "无法", "排除",
)

#: 中文否定字的"非否定合成词"排除集（H-82：中文"不同/相反"）。
_CN_NEG_EXCLUDE = {
    "不": ("同", "断", "过", "仅", "少", "久", "错", "论", "时", "拘", "朽"),
    "无": ("疑", "论", "碍", "恙"),
    "未": (),
}

_EN_NEGATION_RE = re.compile(
    r"(?:\b(?:not|no|never|neither|nor|none|without|lack|lacks|lacking|absence|absent"
    r"|rarely|seldom|failed? to|failing to|no evidence|declined? to|refused? to"
    r"|cannot|can\s+not"
    r"|(?:do|does|did|can|could|wo|would|should|is|are|was|were|has|have|had)n't)\b)",
    re.IGNORECASE,
)

_CN_NEGATION_RE = re.compile(
    r"不(?![同断过仅少久错论时拘朽])|未|无(?![疑论碍恙])|没有|并未|并非|并不"
    r"|缺乏|缺少|极少|很少|未见|未发现|未支持|不能|无法|无显著|排除"
)

NEGATION_TOKEN_RE = re.compile(
    "(?:" + _EN_NEGATION_RE.pattern + "|" + _CN_NEGATION_RE.pattern + ")",
    re.IGNORECASE,
)

#: AECE 层（context_expansion.detect_negation）使用的否定子集：与 2026-09-11 起
#: AECE 既有行为等价，收敛到本模块维护。AECE 把"否定"直接当 CONTRADICTS_TARGET，
#: 语义更重，因此子集刻意比极性判定的小（rarely/lack 等强度词留给极性层）。
AECE_NEGATION_MARKERS = (
    "not", "no", "never", "neither", "nor", "failed to", "fail to",
    "did not", "does not", "without", "non-significant", "insignificant",
    "lack of", "unsupported", "no effect", "no difference",
    "declined to", "decline to", "refused to", "refuse to", "rejected",
    "reject", "denied", "without establishing",
    "未发现", "并未", "并无", "无显著", "没有", "不具有", "未见", "未支持",
    "拒绝", "排除",
)

AECE_NEGATION_RE = re.compile(
    r"(?:\b(?:not|no|never|neither|nor|failed\s+to|fail\s+to|did\s+not|does\s+not"
    r"|without|non-significant|insignificant|lack\s+of|unsupported|no\s+effect"
    r"|no\s+difference|declined\s+to|decline\s+to|refused\s+to|refuse\s+to|rejected"
    r"|reject|denied|without\s+establishing)\b"
    r"|未发现|并未|并无|无显著|没有|不具有|未见|未支持|拒绝|排除)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# 2. 双否定（成对折算为肯定；每命中一次在否定计数上 +1，即翻转奇偶）
# ---------------------------------------------------------------------------

DOUBLE_NEGATION_RES = (
    # not + 负义形容词："not unknown"（= 存在/已知）
    re.compile(r"\bnot\s+(?:unknown|unlikely|impossible|negligible|absent|insignificant"
               r"|uncommon|unexpected|unreported|uncertain|unavailable)\b", re.IGNORECASE),
    # cannot but + 动词 = 不得不/必定
    re.compile(r"\bcannot\s+but\b", re.IGNORECASE),
    # 否定 + 否定性动词（exclude/deny/rule out ...）= 对后续命题的肯定
    re.compile(r"\b(?:cannot|can\s*not|can't|could\s+not|couldn't|did\s+not|didn't"
               r"|does\s+not|doesn't|do\s+not|don't|cannot)\s+(?:be\s+)?"
               r"(?:excluded|denied|ruled\s+out|refuted|rejected|dismissed|overlooked"
               r"|exclude|deny|rule\s+out|refute|reject|dismiss)\b", re.IGNORECASE),
    # no/without doubt = 无疑（肯定）
    re.compile(r"\b(?:no|without)\s+doubt\b", re.IGNORECASE),
    # 中文：不排除 / 不能排除 / 并非没有 / 不无
    re.compile(r"(?:不|不能|并未|未)排除|并非没有|不无"),
)


# ---------------------------------------------------------------------------
# 3. 反转 / 对比标记
# ---------------------------------------------------------------------------

#: 反转动词：出现即翻转同子句内方向词的极性（H-02：abolish/reverse/eliminate/overturn）。
REVERSAL_MARKERS = (
    "abolish", "abolishes", "abolished", "abolishing", "abrogation",
    "reverse", "reverses", "reversed", "reversing",
    "eliminate", "eliminates", "eliminated", "eliminating",
    "overturn", "overturns", "overturned", "overturning",
    "abrogate", "abrogates", "abrogated", "abrogating",
    "nullify", "nullifies", "nullified", "nullifying",
    "抵消", "逆转", "扭转", "消除", "推翻", "废除",
)

REVERSAL_RE = re.compile(
    r"(?:\b(?:abolish\w*|revers\w*|eliminat\w*|overturn\w*|abrogat\w*|nullif\w*)\b"
    r"|抵消|逆转|扭转|消除|推翻|废除)",
    re.IGNORECASE,
)

#: 对比/转折标记：子句切分点（否定不跨子句作用）。
CONTRASTIVE_MARKERS = (
    "while", "whereas", "but", "however", "unlike", "although", "though",
    "yet", "in contrast", "by contrast", "conversely", "on the contrary",
    "相反", "然而", "但是", "不过", "尽管", "虽然", "相比之下", "反观",
)

_CLAUSE_PUNCT_RE = re.compile(r"[，,；;。！!？?\n]+")
_CLAUSE_CONTRAST_RE = re.compile(
    r"(?:\b(?:while|whereas|but|however|unlike|although|though|yet"
    r"|in\s+contrast|by\s+contrast|conversely|on\s+the\s+contrary)\b"
    r"|然而|但是|不过|相反|尽管|虽然|相比之下|反观|而(?!且))",
    re.IGNORECASE,
)
CLAUSE_SPLIT_RE = _CLAUSE_CONTRAST_RE


# ---------------------------------------------------------------------------
# 4. 反义类（词根式子串匹配，与 2026-09-13 首轮极性检查同构，收敛至此）
# ---------------------------------------------------------------------------

ANTONYM_PAIRS = (
    # class 0：程度极值
    (("most", "highest", "greatest", "dominant", "predominant", "maximum", "maximal",
      "最高", "主要", "主导"),
     ("least", "lowest", "smallest", "minor", "negligible", "minimum", "minimal",
      "最低", "次要", "可忽略")),
    # class 1：增/降方向（含词根：increas/decreas/reduc/declin/elevat/promot/...）
    (("increas", "elevat", "enhanc", "promot", "upregul", "higher", "greater",
      "positive", "上升", "增加", "升高", "高于", "促进", "增强", "提升", "提高", "上调", "正相关"),
     ("decreas", "declin", "reduc", "suppress", "inhibit", "impair", "diminish",
      "weaken", "downregul", "lower", "negative", "下降", "减少", "降低", "低于",
      "抑制", "减弱", "削弱", "下调", "负相关")),
    # class 2：比较级
    (("more", "更多", "大于"),
     ("less", "fewer", "更少", "小于")),
)

ANTONYM_LOOKUP: Dict[str, Any] = {}
for _idx, (_pos_side, _neg_side) in enumerate(ANTONYM_PAIRS):
    for _w in _pos_side:
        ANTONYM_LOOKUP[_w] = (_idx, "POS")
    for _w in _neg_side:
        ANTONYM_LOOKUP[_w] = (_idx, "NEG")

_ANTONYM_RES = tuple(
    (re.compile("|".join(re.escape(w) for w in pos), re.IGNORECASE),
     re.compile("|".join(re.escape(w) for w in neg), re.IGNORECASE))
    for pos, neg in ANTONYM_PAIRS
)


# ---------------------------------------------------------------------------
# 5. 帮助函数
# ---------------------------------------------------------------------------

def net_negation_count(text: str) -> int:
    """净否定标记数（双否定短语额外 +1，翻转奇偶）。"""
    if not text:
        return 0
    count = len(NEGATION_TOKEN_RE.findall(text))
    for pat in DOUBLE_NEGATION_RES:
        count += len(pat.findall(text))
    return count


def is_negated(text: str) -> bool:
    """该文本（应为单个子句）的净极性是否为否定。"""
    return net_negation_count(text) % 2 == 1


def find_negations(text: str) -> List[str]:
    """命中的否定标记原文（context_expansion.detect_negation 兼容接口）。"""
    if not text:
        return []
    return [m.group(0) for m in NEGATION_TOKEN_RE.finditer(text)]


def split_clauses(text: str) -> List[str]:
    """按标点与对比标记切分子句（否定/反转只在子句内作用）。"""
    if not text:
        return []
    pieces: List[str] = []
    start = 0
    for m in _CLAUSE_CONTRAST_RE.finditer(text):
        # 对比标记本身归属下一子句开头，切点在标记之前
        if m.start() > start:
            pieces.append(text[start:m.start()])
        start = m.start()
    pieces.append(text[start:])
    out: List[str] = []
    for piece in pieces:
        for part in _CLAUSE_PUNCT_RE.split(piece):
            part = part.strip()
            if part:
                out.append(part)
    return out


def clause_polarity(clause: str) -> Dict[str, Any]:
    """单子句极性：否定/反转先折算，再落反义类方向。

    返回 {"negated": bool, "classes": {idx: "POS"/"NEG"}, "has_reversal": bool}
    """
    negated = is_negated(clause)
    has_reversal = bool(REVERSAL_RE.search(clause))
    classes: Dict[int, str] = {}
    for idx, (pos_re, neg_re) in enumerate(_ANTONYM_RES):
        side = None
        if pos_re.search(clause):
            side = "POS"
        if neg_re.search(clause):
            side = "NEG" if side is None else "BOTH"
        if side is None:
            continue
        if side != "BOTH" and (negated or has_reversal):
            side = "NEG" if side == "POS" else "POS"
        classes[idx] = side
    return {"negated": negated, "classes": classes, "has_reversal": has_reversal}


def polarity_signature(text: str) -> Dict[str, Any]:
    """全文极性签名：子句级方向合并 + 整体净否定奇偶。

    返回 {"negated": bool, "classes": {idx: "POS"/"NEG"/"BOTH"},
          "has_reversal": bool, "negated_clauses": int, "total_clauses": int}
    """
    clauses = split_clauses(text)
    if not clauses:
        clauses = [text] if text.strip() else []
    classes: Dict[int, str] = {}
    has_reversal = False
    negated_clauses = 0
    for clause in clauses:
        cp = clause_polarity(clause)
        if cp["negated"]:
            negated_clauses += 1
        if cp["has_reversal"]:
            has_reversal = True
        for idx, side in cp["classes"].items():
            merged = classes.get(idx)
            if merged is None:
                classes[idx] = side
            elif merged != side:
                classes[idx] = "BOTH"
    return {
        "negated": is_negated(text),
        "classes": classes,
        "has_reversal": has_reversal,
        "negated_clauses": negated_clauses,
        "total_clauses": len(clauses),
    }


_INFLECTIONS = ("ing", "ed", "es", "s", "e")


def predicate_stem(word: str) -> str:
    """谓词词干（去屈折）：increases -> increas，reduced -> reduc。

    供子句定位使用：证据句里的谓词常带不同屈折形式。
    """
    w = (word or "").strip().lower()
    changed = True
    while changed and len(w) > 4:
        changed = False
        for suf in _INFLECTIONS:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                changed = True
                break
    return w


def _clause_contains(clause_lower: str, needle: str) -> bool:
    if not needle:
        return False
    n = needle.lower().strip()
    if not n:
        return False
    if n in clause_lower:
        return True
    stem = predicate_stem(n)
    return len(stem) >= 4 and stem in clause_lower


def _claim_overlap(clause_lower: str, claim_text: str) -> int:
    """主张词项在该子句中的覆盖数（用于挑选"主张锚定"的子句）。"""
    tokens = [t for t in re.findall(r"[\w']+", claim_text.lower()) if len(t) > 2]
    if not tokens:
        return 0
    return sum(1 for t in tokens if t in clause_lower)


def _pick_relevant_clauses(clauses: List[str], predicate: str, obj: str,
                           claim_text: str = "") -> List[str]:
    """极性判定的相关子句：优先同时含谓词与宾语的子句（H-01 子句绑定）。

    - 谓词与宾语都给定时：同时命中的子句为相关子句；若没有任何子句同时命中，
      但谓词确实出现（方向分支分裂）→ 返回空列表（上游判 UNRESOLVED）。
      多个同时命中的子句按"主张词项覆盖"挑选，避免把别的分支上的同形
      谓词（如 "Unlike drug B, which did not increase feeding, drug A
      increases feeding" 里从句中的否定）牵连进来（H-82 远距离否定）。
    - 只给谓词：谓词所在子句。
    - 只给宾语 / 都为空：包含宾语的子句；再退化为全部子句。
    """
    lowered = [c.lower() for c in clauses]
    if predicate:
        pred_hits = [i for i, c in enumerate(lowered) if _clause_contains(c, predicate)]
        if obj:
            both = [i for i in pred_hits if _clause_contains(lowered[i], obj)]
            if both:
                best = max(_claim_overlap(lowered[i], claim_text) for i in both)
                both = [i for i in both
                        if _claim_overlap(lowered[i], claim_text) == best] or both
                return [clauses[i] for i in both]
            if pred_hits:
                # 谓词出现、宾语不在同一子句：方向分支分裂（另一分支上的谓词
                # 不能为本主张背书）→ 交人工，不得判 SUPPORTED。
                return []
        if pred_hits:
            return [clauses[i] for i in pred_hits]
        # 谓词被反转/转述改写（"overturned the elevation"）而任何子句都不含
        # 谓词词干时，方向信息仍挂在宾语所在子句上——用宾语子句承载极性。
        if obj:
            obj_hits = [i for i, c in enumerate(lowered) if _clause_contains(c, obj)]
            if obj_hits:
                return [clauses[i] for i in obj_hits]
        return []
    if obj:
        obj_hits = [i for i, c in enumerate(lowered) if _clause_contains(c, obj)]
        if obj_hits:
            return [clauses[i] for i in obj_hits]
    return list(clauses)


def check_polarity(claim_text: str, evidence_text: str,
                   predicate: str = "", obj: str = "") -> Optional[Dict[str, Any]]:
    """三值极性判定（H-01/H-02/H-82）。

    返回：
      - ``None``                          方向一致（或无可比的极性问题）
      - ``{"verdict": "CONTRADICTORY", "reason": ...}``
      - ``{"verdict": "UNRESOLVED", "reason": ...}``   签名不可比，fail-closed 交人工
    """
    claim_text = claim_text or ""
    evidence_text = evidence_text or ""
    if not claim_text.strip() or not evidence_text.strip():
        return None

    claim_sig = polarity_signature(claim_text)
    clauses = split_clauses(evidence_text) or [evidence_text]
    relevant = _pick_relevant_clauses(clauses, predicate, obj, claim_text)

    # 谓词在证据中找不到任何子句 → 极性无从谈起（未绑定谓词由其它门禁处理）
    if predicate and not relevant:
        if any(_clause_contains(c.lower(), predicate) for c in clauses):
            return {"verdict": "UNRESOLVED",
                    "reason": ("polarity unresolved: predicate '%s' and object '%s' sit in "
                               "different direction branches of the same sentence; the "
                               "predicate cannot be bound for this claim"
                               % (predicate, obj))}
        return None

    merged: Dict[int, str] = {}
    neg_flags: List[bool] = []
    has_reversal = False
    any_direction_token = False
    for clause in relevant or clauses:
        cp = clause_polarity(clause)
        neg_flags.append(cp["negated"])
        has_reversal = has_reversal or cp["has_reversal"]
        for idx, side in cp["classes"].items():
            any_direction_token = True
            merged_side = merged.get(idx)
            if merged_side is None:
                merged[idx] = side
            elif merged_side != side:
                merged[idx] = "BOTH"
    relevant_negated = all(neg_flags) if neg_flags else False

    # 1) 反义类比较（方向词折算否定/反转后比）
    claim_classes = claim_sig["classes"]
    if claim_classes:
        for idx, claim_side in claim_classes.items():
            if claim_side == "BOTH":
                return {"verdict": "UNRESOLVED",
                        "reason": ("polarity unresolved: claim itself carries mixed "
                                   "direction on antonym class %d" % idx)}
            ev_side = merged.get(idx)
            if ev_side == "BOTH":
                return {"verdict": "UNRESOLVED",
                        "reason": ("polarity unresolved: evidence sentence mixes both "
                                   "directions of antonym class %d; comparison skipped "
                                   "would be direction laundering" % idx)}
            if ev_side is None:
                if has_reversal:
                    return {"verdict": "UNRESOLVED",
                            "reason": ("polarity unresolved: reversal verb in evidence "
                                       "clause but no comparable direction token for "
                                       "antonym class %d" % idx)}
                if any_direction_token:
                    # 跨反义类不配对：证据有方向词但与主张不同类，方向不可比
                    return {"verdict": "UNRESOLVED",
                            "reason": ("polarity unresolved: claim direction (class %d) "
                                       "has no comparable direction token in the bound "
                                       "evidence clause" % idx)}
                continue
            if ev_side != claim_side:
                return {"verdict": "CONTRADICTORY",
                        "reason": ("polarity mismatch on antonym class %d: claim=%s "
                                   "evidence=%s" % (idx, claim_side, ev_side))}
        return None

    # 2) 无反义类可比时，退回否定奇偶比较（限定相关子句；多子句奇偶打架 → 交人工）
    if len(set(neg_flags)) > 1:
        return {"verdict": "UNRESOLVED",
                "reason": ("polarity unresolved: bound evidence clauses disagree on "
                           "negation; human adjudication required")}
    if claim_sig["negated"] != relevant_negated:
        return {"verdict": "CONTRADICTORY",
                "reason": ("polarity mismatch: claim negated=%s but evidence clause "
                           "negated=%s" % (claim_sig["negated"], relevant_negated))}
    if has_reversal and claim_sig["negated"] == relevant_negated and not any_direction_token:
        # 反转词在场但两侧都没有方向词：反转对象不可判 → 交人工
        return {"verdict": "UNRESOLVED",
                "reason": ("polarity unresolved: reversal verb in evidence clause; the "
                           "reversed direction cannot be inferred from the lexicon")}
    return None
