#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quote_audit.py
--------------
ScholarFlow mechanical quote back-verification gate (literature-evidence-extraction).

For every `verbatim_quote` in an evidence JSON (schemas/extraction_result.schema.json),
verifies that the quoted text actually occurs in the source document (PDF or TXT).
A quote that cannot be located in the source is mechanically demoted to UNSUPPORTED:
no language model judgement is involved in this check.

Rationale: the E1-E4 evidence contract anchors every extracted value to a verbatim
quote. The quote itself is the anchor of anchors — and whether it exists in the
source is a string-matching problem, not a reasoning problem. This script turns
"the auditor re-read the paper" (same-model self-check) into a hard, reproducible gate.

Matching is robust to PDF extraction artifacts:
1. EXACT       — match after whitespace collapsing + confusable-character normalization
                 (curly quotes, µ/μ, unicode dashes, soft hyphens, NFC).
2. HYPHEN_JOIN — match after re-joining hyphenated line breaks ("step- wise" -> "stepwise").
3. FUZZY       — best sliding-window token containment >= threshold (default 0.95).
                 Reported as a warning, not a failure (unless --strict).
4. NOT_FOUND   — no acceptable match: gate failure.

Standard Library Only (pypdf optional, only needed for PDF sources).

Usage:
    python quote_audit.py -i evidence.json -s paper.pdf
    python quote_audit.py -i evidence.json -s paper.txt --strict -o audit_report.json
Exit code: 0 = all quotes verified; 1 = at least one NOT_FOUND (or FUZZY under --strict);
           2 = input error (file/schema missing, pypdf unavailable for PDF source).
"""

import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MIN_QUOTE_LEN = 15          # shorter quotes cannot be located reliably
FUZZY_THRESHOLD = 0.95      # token containment ratio for FUZZY match
FUZZY_WINDOW_CAP = 400      # max source tokens scanned for fuzzy windows per quote

# Records the gate could not verify (empty quote / too short / quote not found)
# must NOT pass silently. Prior behaviour counted them and returned exit 0,
# which made "leave the quote blank" a free escape hatch — and a blank quote is
# exactly the prescribed shape of an E4/NR record.
UNVERIFIED_FAIL = "fail"    # default: unverified records fail the gate
UNVERIFIED_LIST = "list"    # report them, do not fail (explicit opt-out)
UNVERIFIED_IGNORE = "ignore"  # legacy behaviour; requires a written justification
UNVERIFIED_POLICIES = (UNVERIFIED_FAIL, UNVERIFIED_LIST, UNVERIFIED_IGNORE)

CONFUSABLE_TABLE = {
    "\u2018": "'", "\u2019": "'", "\u201a": ",",          # single curly quotes
    "\u201c": '"', "\u201d": '"',                          # double curly quotes
    "\u00ab": '"', "\u00bb": '"',                          # guillemets
    "\u00b5": "\u03bc",                                    # MICRO SIGN -> GREEK MU
    "\u2013": "-", "\u2014": "-", "\u2212": "-",           # en/em/minus dash
    "\u2010": "-", "\u2011": "-", "\u00ad": "",            # hyphen variants, soft hyphen
    "\u00a0": " ", "\u2028": " ", "\u2029": " ",           # nbsp, line/para separators
    "\ufb01": "fi", "\ufb02": "fl",                        # ligatures
    # --- numeric/typographic variants produced by PDF typesetting -----------
    # Measured: Acta Zoologica Sinica 2007 renders the DECIMAL POINT as U+2219
    # ("55\u22194%"), so a value written "55.4%" in the evidence JSON never matched
    # the source and was falsely reported as fabricated. NFKC does NOT fold U+2219.
    "\u2219": ".", "\u2027": ".", "\u00b7": ".", "\u30fb": ".",
    # C1 controls carry Windows-1252 punctuation in many Chinese typeset PDFs
    # (measured: the comma in the same journal is U+0082).
    "\u0082": ",", "\u0085": "...", "\u0091": "'", "\u0092": "'",
    "\u0093": '"', "\u0094": '"', "\u0096": "-", "\u0097": "-",
    "\u008b": "<", "\u009b": ">",
    # full-width forms that NFKC leaves alone in some CJK journal fonts
    "\uff0e": ".", "\uff0c": ",", "\uff1a": ":", "\uff1b": ";",
    "\uff08": "(", "\uff09": ")", "\uff05": "%",
}


def normalize_text(text: str, fold_case: bool = True) -> str:
    """NFC + confusable-character mapping + whitespace collapse (+ lowercase).

    `fold_case=False` 保留原大小写，供**数量扫描**使用：单位符号区分大小写
    （`Gy` 与 `gy`、`Sv` 与 `sv` 含义不同），按小写扫描会漏掉未知单位。
    """
    t = unicodedata.normalize("NFC", text)
    for src, dst in CONFUSABLE_TABLE.items():
        t = t.replace(src, dst)
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower() if fold_case else t


def join_hyphen_breaks(text: str) -> str:
    """Re-join words split by hyphenated line breaks: 'step- wise' -> 'stepwise'."""
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text, re.UNICODE)


def _best_fuzzy_window(needle_tokens: List[str], haystack_tokens: List[str]) -> float:
    """Max unique-token containment of the needle across sliding windows of the haystack.

    Both sides are reduced to unique token sets: duplicate words (e.g. "was ... was")
    would otherwise double-penalize containment for extraction-noise quotes.
    """
    needle_set = set(needle_tokens)
    m = len(needle_set)
    if m == 0 or not haystack_tokens:
        return 0.0
    best = 0.0
    end_limit = min(len(haystack_tokens), FUZZY_WINDOW_CAP)
    for start in range(0, max(1, len(haystack_tokens) - m + 1)):
        if start >= end_limit:
            break
        window = haystack_tokens[start:start + m]
        ratio = len(needle_set & set(window)) / m
        if ratio > best:
            best = ratio
            if best == 1.0:
                break
    return best


# --------------------------------------------------------------------------
# Value–quote alignment (F1b)
#
# Rationale: verifying that a quote EXISTS in the source says nothing about
# whether the extracted value is supported by it. Measured failure mode: the
# quote "Shrubs were the most important food of black muntjac" with
# extracted_value "95.4%" (source actually says 55.4%) passes quote matching
# cleanly. That is quote laundering, and it is invisible to string matching
# alone. This layer closes the numeric half of that hole.
# --------------------------------------------------------------------------

ALIGNMENT_WINDOW = 200     # chars of source context around the quote location
# Kept deliberately tight: a value that only appears far from the quote it is
# attached to is exactly the "right number, wrong place" failure this layer
# exists to surface. Chunkier analysis units can widen it explicitly.
#: Only tokens that carry quantitative meaning are compared.
#:
#: Bare integers remain excluded (years, page numbers and citation markers
#: would swamp the check), **but** an integer carrying a measurable unit is
#: included: a reaction volume of "999 microliters" against a source saying
#: "20 microliters" is exactly the mismatched-value failure this layer exists
#: to catch, and skipping every unit-bearing integer let it through.
# --------------------------------------------------------------------------
# R02（第二轮核查）：完整数量解析
#
# 旧实现按"字符邻居是不是数字"做词法边界判断，并把数值与单位拆开匹配，于是：
#   2.5 microliters ➜ 抽成 "2.5"      ➜ 与 2.5 milliliters 互相命中
#   15.4%           ➜ 抽成 "4%"       ➜ 在 15.4% 内部命中
#   20.5            ➜ 抽成整数 20     ➜ 与 20.5 互相命中
#   0.054 meters    ➜ 与 5.4% 互转    ➜ 量纲完全不同却放行
#   999 mL          ➜ 抽不出 token    ➜ value_checked=0 直接放行
#
# 现在改为**先解析完整数量**（符号 + 数值 + 指数 + 单位），再按"数值 + 量纲"比较：
#   - 单位参与比较，绝不退化为裸数；
#   - 同一量纲内按换算因子比较（2.5 mL == 2500 µL，但 ≠ 2.5 µL）；
#   - 量纲不同（百分比 vs 长度）直接判不匹配；
#   - 含数字却解析不出数量 → 标为待核验，不得算通过。
# --------------------------------------------------------------------------

#: (量纲, 换算到该量纲基准单位的**精确十进制**因子, 可接受写法)
#:
#: 因子用字符串给出，比较时走 `decimal.Decimal` 定点运算：浮点二进制表示会把
#: "1 nL vs 2 nL" 这类真实差异压到容差之下（第三轮核查 T01），也让换算结果
#: 依赖字面写法。十进制定点比较是精确的，不需要"宽容差"来掩盖。
_UNIT_GROUPS = (
    ("volume", "1", ("l", "L", "liter", "liters", "litre", "litres", "升")),
    ("volume", "0.001", ("ml", "mL", "milliliter", "milliliters", "millilitre",
                         "millilitres", "毫升")),
    ("volume", "0.000001", ("µl", "µL", "μl", "μL", "uL", "ul", "microliter",
                            "microliters", "microlitre", "microlitres", "微升")),
    ("volume", "0.000000001", ("nl", "nL", "nanoliter", "nanoliters", "纳升")),
    ("volume", "0.000000000001", ("pl", "pL", "picoliter", "picoliters", "皮升")),
    ("length", "1", ("m", "meter", "meters", "metre", "metres", "米")),
    ("length", "0.01", ("cm", "centimeter", "centimeters", "厘米")),
    ("length", "0.001", ("mm", "millimeter", "millimeters", "millimetre",
                         "millimetres", "毫米")),
    ("length", "0.000001", ("µm", "μm", "um", "micrometer", "micrometers", "微米")),
    ("length", "0.000000001", ("nm", "nanometer", "nanometers", "纳米")),
    ("length", "1000", ("km", "kilometer", "kilometers", "千米", "公里")),
    ("mass", "1", ("g", "gram", "grams", "克")),
    ("mass", "0.001", ("mg", "milligram", "milligrams", "毫克")),
    ("mass", "0.000001", ("µg", "μg", "ug", "microgram", "micrograms", "微克")),
    ("mass", "0.000000001", ("ng", "nanogram", "nanograms", "纳克")),
    ("mass", "1000", ("kg", "kilogram", "kilograms", "千克", "公斤")),
    ("percent", "0.01", ("%", "percent", "percents", "百分比", "百分数")),
    ("permille", "0.001", ("‰",)),
    ("temperature", "1", ("°c", "°C", "℃", "celsius", "摄氏度")),
    ("time", "1", ("s", "sec", "second", "seconds", "秒")),
    ("time", "60", ("min", "minute", "minutes", "分钟")),
    ("time", "3600", ("h", "hr", "hour", "hours", "小时")),
    ("count_sample", "1", ("sample", "samples", "样本", "份")),
    ("count_individual", "1", ("individual", "individuals", "只", "头", "尾")),
    ("count_species", "1", ("species", "种")),
    ("count_site", "1", ("site", "sites", "plot", "plots", "样地", "样方")),
    ("count_read", "1", ("read", "reads")),
    ("count_base", "1", ("bp",)),
    ("count_base", "1000", ("kb",)),
    ("count_base", "1000000", ("mb",)),
)

#: 单位写法 → (量纲, 因子)。**区分大小写**：mL 是毫升而 ML 不是，mm 是毫米而 Mm 不是。
_UNIT_LOOKUP = {}
for _dim, _factor, _forms in _UNIT_GROUPS:
    for _form in _forms:
        _UNIT_LOOKUP[_form] = (_dim, _factor)

#: 仅对**词形单位**（≥4 个字母）允许忽略大小写，短符号一律区分大小写，
#: 避免把 Mm（兆米）、ML（兆升）、G（高斯）之类折成毫米/毫升/克。
_UNIT_WORD_FALLBACK = {k.lower(): v for k, v in _UNIT_LOOKUP.items()
                       if len(k) >= 4 and k.isalpha()}

_UNIT_MAX_LEN = max(len(k) for k in _UNIT_LOOKUP)

_NUMBER_RE = re.compile(r"(?<![\d.,])(?P<num>\d+(?:[.,]\d+)?)(?:[eE](?P<exp>[+-]?\d+))?(?![\d])")

#: 允许把百分比与裸比例互认的字段类型声明。
RATIO_FIELD_TYPES = ("proportion", "ratio", "percentage", "percent")

#: 明确声明为无量纲 / 计数时，才允许把带未知单位或无量纲的抽取值按数值比较。
DIMENSIONLESS_FIELD_TYPES = ("dimensionless", "count", "frequency", "fold")

#: 未知单位里"像单位符号"的形态（用于把 `5 Gy` 判为带单位，而不是无量纲 5）。
#: SI 符号多为「大写开头 + 至多一个小写」（Gy/Sv/Pa/Hz/Da）或全大写（kPa→首字母大写
#: 但含两个小写，故另加长度 ≤3 的全小写前导判断）；普通英文词（The/Table/This）
#: 因小写字母过多被排除，不会被误当单位。
_UNIT_SYMBOL_RE = re.compile(r"^(?:[A-Za-zµμ°‰%]{1,5}|[\u4e00-\u9fff]{1,3})$")


def _looks_like_unit_symbol(token: str) -> bool:
    """判断一个未知 token 是否"像单位符号"（宁缺毋滥，避免把普通单词当单位）。"""
    if not _UNIT_SYMBOL_RE.match(token):
        return False
    if any(ord(c) > 127 for c in token):
        return True                       # µ/° / 汉字单位
    if token.isupper() and len(token) <= 4:
        return True                       # Sv, Gy, kPa(3), MeV
    if re.fullmatch(r"[A-Z][a-z]?", token):
        return True                       # Pa, Gy, Sv, Da, eV 之外的 T/N
    if re.fullmatch(r"[a-z][A-Z]", token):
        return True                       # eV, mW, dB, pH 的反向写法
    return False

#: 复合单位连接符：出现即视为复合单位（本层不做复合量纲换算，如实阻断）。
_COMPOUND_UNIT_CHARS = "/·*^*×⋅"


def _sign_before(text: str, pos: int) -> int:
    """判断数字前的 +/- 是符号还是区间分隔符，返回 +1 / -1。"""
    if pos == 0:
        return 1
    prev = text[pos - 1]
    if prev in "+-\u2212":
        before_sign = text[pos - 2] if pos >= 2 else ""
        if before_sign == "" or before_sign in " \t(=[,;:（±":
            return -1 if prev in "-\u2212" else 1
    return 1


def _match_unit(text: str, pos: int):
    """从 pos 起匹配一个已知单位；返回 (canonical, dimension, factor, end) 或 None。"""
    i = pos
    while i < len(text) and text[i] in " \t\u00a0":
        i += 1
    if i >= len(text):
        return None
    best = None
    for key, info in _UNIT_LOOKUP.items():
        if text.startswith(key, i):
            end = i + len(key)
            nxt = text[end] if end < len(text) else ""
            if key[-1].isalpha() and nxt.isalpha():
                continue                      # 必须整体成词，避免 ml 命中 mlx
            if best is None or len(key) > len(best[0]):
                best = (key, info, end)
    word = re.match(r"[A-Za-z]{%d,%d}" % (4, _UNIT_MAX_LEN + 2), text[i:i + _UNIT_MAX_LEN + 2])
    if word:
        token = word.group(0)
        lower = token.lower()
        # 只在词形单位上做大小写回退；且不得吞掉更长的精确匹配
        if lower in _UNIT_WORD_FALLBACK and (best is None or len(token) > len(best[0])):
            end = i + len(token)
            nxt = text[end] if end < len(text) else ""
            if not (nxt.isalpha() or nxt.isdigit()):
                best = (token, _UNIT_WORD_FALLBACK[lower], end)
    if best is None:
        return None
    canonical, (dimension, factor), end = best
    return canonical, dimension, factor, end


def _unknown_unit_after(text: str, pos: int):
    """检测数字后紧邻的**未知单位**；返回 (raw_token, end) 或 None。

    T03：`5 Gy` 与 `5 Sv` 在旧实现里都被解析成无量纲的 5 而互相命中。未知单位必须
    保留原始 token 并阻断，不能静默丢成"没有单位"。

    判定"像单位"的条件之一即可（避免把 `20 samples were…` 里的普通单词当单位）：
      - 与数字**紧贴**（无空白），或
      - 以空白分隔但形态像单位符号（短、全大写或含 µ/°/‰ 等符号、或 1–3 个汉字）。
    """
    adjacent = pos < len(text) and text[pos] not in " \t\u00a0"
    i = pos
    while i < len(text) and text[i] in " \t\u00a0":
        i += 1
    if i >= len(text):
        return None
    m = re.match(r"[A-Za-zµμ°‰%\u4e00-\u9fff]+", text[i:])
    if not m:
        return None
    token = m.group(0)
    end = i + len(token)
    if _COMPOUND_UNIT_CHARS and end < len(text) and text[end] in _COMPOUND_UNIT_CHARS:
        return (token + text[end], end + 1)          # 复合单位：如实当未知单位
    if adjacent:
        return (token, end)
    if _looks_like_unit_symbol(token):
        return (token, end)
    return None


def _decimal(num: str) -> "Decimal":
    """把数字字面量解析成 Decimal；区分千分位逗号与欧洲小数逗号。"""
    cleaned = num.replace(" ", "").replace("\u00a0", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", cleaned):
        cleaned = cleaned.replace(",", "")           # 1,000 = 一千
    else:
        cleaned = cleaned.replace(",", ".")          # 2,5 = 2.5
    return Decimal(cleaned)


def extract_quantities(value: Any) -> List[Dict[str, Any]]:
    """把 extracted_value 解析为完整数量列表（数值 + 符号 + 指数 + 单位）。

    `dimension` 取值：
      - `None`：显式无单位（例如 `20`、`0.054`）；
      - 量纲名：已知单位（`volume` / `length` / `percent` / `count_base` …）；
      - `"unknown"`：带未知或复合单位（如 `5 Sv`、`2 m/s`）——保留 `unit` 原文，
        比较时必须单位完全一致，并由门禁标为待核验。
    """
    if value is None:
        return []
    text = str(value)
    out: List[Dict[str, Any]] = []
    for m in _NUMBER_RE.finditer(text):
        try:
            number = _decimal(m.group("num"))
        except (InvalidOperation, ValueError):
            continue
        if m.group("exp"):
            number *= Decimal(10) ** int(m.group("exp"))
        sign = _sign_before(text, m.start("num"))
        unit_info = _match_unit(text, m.end())
        if unit_info is None:
            unknown = _unknown_unit_after(text, m.end())
            if unknown is not None:
                canonical, dimension, factor, end = unknown[0], "unknown", None, unknown[1]
            else:
                canonical, dimension, factor, end = None, None, None, m.end()
        else:
            canonical, dimension, factor, end = unit_info
            # T03：复合/带指数单位（m/s、m2、kg·ha）本层不做量纲换算，
            # 统一按未知单位处理并阻断，避免只取到前缀单位就当作命中。
            if end < len(text) and (text[end] in _COMPOUND_UNIT_CHARS or text[end].isdigit()):
                cont = re.match(r"\S*", text[end:]).group(0)
                canonical, dimension, factor, end = canonical + cont, "unknown", None, end + len(cont)
        out.append({
            "raw": text[m.start("num"):end],
            "value": sign * number,
            "unit": canonical,
            "dimension": dimension,
            "factor": factor,
        })
    return out


def extract_value_tokens(value: Any) -> List[str]:
    """数量 token 的规范化字符串形式（保留此接口以兼容既有调用与报告）。"""
    tokens: List[str] = []
    for q in extract_quantities(value):
        num = _format_decimal(q["value"])
        token = num + (q["unit"] or "")
        if token not in tokens:
            tokens.append(token)
    return tokens


def _format_decimal(value: "Decimal") -> str:
    """人类可读的十进制写法（去掉无意义的尾随零）。"""
    normalized = value.normalize()
    text = format(normalized, "f")
    return text


def _has_digit(value: Any) -> bool:
    return bool(re.search(r"\d", str(value if value is not None else "")))


def _declared_field_type(rec: Dict[str, Any]) -> str:
    return str(rec.get("value_type") or rec.get("quantity_type") or "").strip().lower()


def _is_ratio_field(rec: Dict[str, Any]) -> bool:
    return _declared_field_type(rec) in RATIO_FIELD_TYPES


def _allows_dimensionless(rec: Dict[str, Any]) -> bool:
    return _declared_field_type(rec) in DIMENSIONLESS_FIELD_TYPES


#: 计数类量纲：抽取值未带单位时，仍可与源文中的计数单位比较（"20" ↔ "20 samples"）。
_COUNT_DIMENSIONS = ("count_sample", "count_individual", "count_species",
                     "count_site", "count_read", "count_base")


def _dimension_compatible(ext_q: Dict[str, Any], src_q: Dict[str, Any], rec: Dict[str, Any]) -> bool:
    """量纲是否可比。

    - 同量纲 → 可比（再按换算因子比数值）；
    - 未知/复合单位 → 只有**单位原文完全一致**时才可比，且仍由门禁标待核验；
    - 百分比 ↔ 裸比例 → 仅当字段显式声明为比例/百分比时可比；
    - 抽取值无单位、源文是计数单位 → 可比（"20" 对 "20 samples"）；
    - 其余跨量纲组合一律不可比（百分比不能匹配长度，抽取值带单位而源文没有
      也不能算命中）。
    """
    ed, sd = ext_q["dimension"], src_q["dimension"]
    if ed == "unknown" or sd == "unknown":
        if ed == "unknown" and sd == "unknown":
            return ext_q["unit"] == src_q["unit"]
        # 一侧未知单位、另一侧**无量纲**：只有字段显式声明为无量纲/计数时才按数值比较。
        # 另一侧是已知量纲（如 count_sample）时不可比——那是"数值撞上、含义不同"。
        if (ed is None or sd is None) and _allows_dimensionless(rec):
            return True
        return False
    if ed == sd:
        return True
    if {ed, sd} <= {"percent", "permille"} and _is_ratio_field(rec):
        return True                                      # 5% 与 50‰ 都是比例
    if ed in ("percent", "permille") and sd is None and _is_ratio_field(rec):
        return True
    if sd in ("percent", "permille") and ed is None and _is_ratio_field(rec):
        return True
    if ed is None and sd in _COUNT_DIMENSIONS:
        return True
    if ed is None and sd is not None and _allows_dimensionless(rec):
        return True
    return False


def _quantities_match(ext_q: Dict[str, Any], src_q: Dict[str, Any], rec: Dict[str, Any]) -> bool:
    """数值 + 量纲比较：同量纲按精确十进制换算因子比，跨量纲一律不匹配。

    T01：比较用 `Decimal` 定点值直接相等判定，不设"宽松绝对容差"——容差会把
    `1 nL` 与 `2 nL`（换算后差 1e-9 L）判成相等。解析与换算本身是十进制定点、
    不含浮点误差，因此无需容差来掩盖。
    """
    if not _dimension_compatible(ext_q, src_q, rec):
        return False
    ed, sd = ext_q["dimension"], src_q["dimension"]
    if ed == "unknown" or sd == "unknown":
        # 量纲可比性已由 _dimension_compatible 判定（同未知单位，或声明无量纲）
        return ext_q["value"] == src_q["value"]
    if ed != sd:
        if "percent" in (ed, sd) or "permille" in (ed, sd):
            # 比例字段：percent/‰ 按各自倍率折算成裸比例
            a = _to_base(ext_q) if ext_q["factor"] is not None else ext_q["value"]
            b = _to_base(src_q) if src_q["factor"] is not None else src_q["value"]
        else:
            # 抽取值无单位、源文是计数单位 / 声明无量纲：按原值比较
            a, b = ext_q["value"], src_q["value"]
    else:
        a, b = _to_base(ext_q), _to_base(src_q)
    return a == b


def _to_base(q: Dict[str, Any]) -> "Decimal":
    """换算到量纲基准单位（精确十进制乘法）。"""
    if q["factor"] is None:
        return q["value"]
    return q["value"] * Decimal(q["factor"])


def _scan_quantities(text: str) -> List[Dict[str, Any]]:
    return extract_quantities(text)


def _present_in(ext_q: Dict[str, Any], text: str, rec: Dict[str, Any]) -> bool:
    for src_q in _scan_quantities(text):
        if _quantities_match(ext_q, src_q, rec):
            return True
    return False


def fold_numeric(text: str) -> str:
    """Whitespace-free form for NUMERIC comparison only.

    OCR/typeset output routinely injects spaces inside numbers: measured examples
    are "4 \u00b7 8" (=4.8), "55 , 9 \u2030" (=55.9 ), "21 \u00b7 7" (=21.7). The
    generic normalizer preserves those spaces (it must, so that "43 species"
    keeps its word boundary), so numeric tokens are compared on this stricter
    folding instead. It is scoped to value tokens, never used to match quotes.
    """
    folded = re.sub(r"(?<=\d)\s*[·•∙]\s*(?=\d)", ".", normalize_text(text))
    return re.sub(r"\s+", "", folded)


def numeric_view(text: str, fold_case: bool = True) -> str:
    """Numeric scanning view: repair OCR decimal points but KEEP spaces.

    `fold_numeric()` removes all whitespace, which merges "2.5 microliters" into
    "2.5microlitersin..." and destroys the unit word boundary. Quantity scanning
    therefore needs its own view: same repair, spaces preserved.

    `fold_case=False` 用于**源文**扫描：单位符号大小写有意义，不能先转小写
    （否则 `5 Gy` 会被当成无量纲 5，抽取值悄悄丢掉单位也能通过）。
    """
    return re.sub(r"(?<=\d)\s*[·•∙]\s*(?=\d)", ".", normalize_text(text, fold_case=fold_case))


def check_value_alignment(rec: Dict[str, Any], norm_source: str,
                          quote_span: Optional[tuple],
                          raw_source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Compare extracted quantities against the source.

    Verdicts:
      NO_NUMERIC_VALUE  – nothing quantitative to check (not a pass or a fail)
      ALIGNED           – every quantity found with the same value and dimension
      NOT_FOUND_IN_SOURCE – quantity absent from the WHOLE source (fabrication signal)
      NOT_IN_QUOTE_CONTEXT – quantity exists somewhere but not near the quote
      UNIT_MISMATCH     – same number, different/incompatible unit or dimension
      UNKNOWN_UNIT      – the value carries a unit/dimension this layer does not support
      UNPARSEABLE_VALUE – the value contains digits but no quantity could be parsed
    Returns None when there is nothing to check.
    """
    raw_value = rec.get("extracted_value")
    quantities = extract_quantities(raw_value)
    if not quantities:
        if _has_digit(raw_value):
            # R02：含数字却解析不出数量（例如 "999 foo"）不得当作"没有数值可查"。
            return {"verdict": "UNPARSEABLE_VALUE", "tokens": [],
                    "missing_in_source": [], "not_in_context": [],
                    "unverified": True,
                    "detail": ("extracted_value=%r contains digits but no parsable "
                               "quantity (value + unit); it must be reviewed by hand "
                               "and cannot pass the numeric gate." % (raw_value,))}
        return None

    # 源文扫描保留大小写：单位符号有意义，先转小写会把 `5 Gy` 当成无量纲 5。
    src_fold = numeric_view(raw_source if raw_source is not None else norm_source,
                            fold_case=raw_source is None)
    quote = rec.get("verbatim_quote") or ""
    quote_fold = numeric_view(quote, fold_case=False)
    window_fold = ""
    raw_quote_span = None
    if raw_source:
        pos = raw_source.find(quote)
        if pos >= 0:
            raw_quote_span = (pos, pos + len(quote))
    if raw_quote_span:
        a = max(0, raw_quote_span[0] - ALIGNMENT_WINDOW)
        b = min(len(raw_source), raw_quote_span[1] + ALIGNMENT_WINDOW)
        window_fold = numeric_view(raw_source[a:b], fold_case=False)
    elif quote_span:
        a = max(0, quote_span[0] - ALIGNMENT_WINDOW)
        b = min(len(norm_source), quote_span[1] + ALIGNMENT_WINDOW)
        window_fold = numeric_view(norm_source[a:b])

    tokens = [_format_decimal(q["value"]) + (q["unit"] or "") for q in quantities]

    # T03：带未知/复合单位的数量一律不得当通过——本层不支持该量纲换算，
    # 除非字段显式声明为无量纲/计数（此时按数值比较）。
    unsupported = [tok for q, tok in zip(quantities, tokens)
                   if q["dimension"] == "unknown" and not _allows_dimensionless(rec)]
    if unsupported:
        return {"verdict": "UNKNOWN_UNIT", "tokens": tokens,
                "quantities": [{"value": _format_decimal(q["value"]), "unit": q["unit"],
                                "dimension": q["dimension"]} for q in quantities],
                "missing_in_source": [], "not_in_context": [],
                "unverified": True,
                "detail": ("Value(s) %s carry a unit this auditor does not support "
                           "(no dimension/scale registered). It cannot be converted or "
                           "compared, so it must be reviewed by hand: add the unit to "
                           "the table, or declare value_type=dimensionless/count if that "
                           "is the real contract." % unsupported)}

    missing_in_source = []
    not_in_context = []
    unit_mismatch = []
    for q, tok in zip(quantities, tokens):
        if _present_in(q, src_fold, rec):
            if _present_in(q, quote_fold, rec) or _present_in(q, window_fold, rec):
                continue
            not_in_context.append(tok)
            continue
        missing_in_source.append(tok)
        # 数值本身存在、但单位或量纲不同 → 单独指出，避免与"整段缺失"混淆
        for other in _scan_quantities(src_fold):
            if abs(other["value"]) == abs(q["value"])                     and other["dimension"] != q["dimension"]:
                unit_mismatch.append("%s≠%s" % (
                    tok, _format_decimal(other["value"]) + (other["unit"] or "")))
                break

    if missing_in_source and unit_mismatch:
        verdict = "UNIT_MISMATCH"
        detail = ("Value(s) %s appear in the source with a different unit/dimension (%s). "
                  "Unit conversion is only honoured inside one dimension, so this needs "
                  "human adjudication before citing." % (missing_in_source, unit_mismatch))
    elif missing_in_source:
        verdict = "NOT_FOUND_IN_SOURCE"
        detail = ("Value token(s) %s are not anchored anywhere in the source document. "
                  "Either the value was not taken from this paper (fabrication / wrong "
                  "source) OR the source text is degraded (OCR misread — e.g. measured "
                  "'2\u5de7' for 27.5, '12\u5de7' for 121.5). Both require human "
                  "adjudication; check the page image before citing." % missing_in_source)
    elif not_in_context:
        verdict = "NOT_IN_QUOTE_CONTEXT"
        detail = ("Value token(s) %s exist in the source but not within the quote "
                  "or its ±%d-char context; confirm the value is anchored where "
                  "claimed." % (not_in_context, ALIGNMENT_WINDOW))
    else:
        verdict = "ALIGNED"
        detail = "All numeric tokens located in the quote or its local context."
    return {"verdict": verdict, "tokens": tokens,
            "quantities": [{"value": _format_decimal(q["value"]), "unit": q["unit"],
                            "dimension": q["dimension"]} for q in quantities],
            "missing_in_source": missing_in_source,
            "not_in_context": not_in_context, "detail": detail}


def audit_evidence(evidence: Dict[str, Any], source_text: str,
                   min_quote_len: int = MIN_QUOTE_LEN,
                   fuzzy_threshold: float = FUZZY_THRESHOLD,
                   unverified_policy: str = UNVERIFIED_FAIL) -> Dict[str, Any]:
    """
    Pure audit core: verify every verbatim_quote in evidence records against source text,
    then check that each extracted_value is anchored where the quote is.
    Returns a report dict; file I/O stays in main() so this is unit-testable.
    """
    norm_source = normalize_text(source_text)
    joined_source = join_hyphen_breaks(norm_source)
    source_tokens = tokenize(joined_source)

    entries: List[Dict[str, Any]] = []
    counts = {"exact_match": 0, "hyphen_join": 0, "fuzzy_match": 0,
              "not_found": 0, "skipped_no_quote": 0, "too_short": 0,
              "unverified": 0, "value_aligned": 0, "value_not_found_in_source": 0,
              "value_not_in_quote_context": 0, "value_unit_mismatch": 0,
              "value_unknown_unit": 0, "value_unparsable": 0, "value_checked": 0}

    for rec in evidence.get("evidence_records", []):
        quote = rec.get("verbatim_quote") or ""
        field_id = rec.get("field_id", "")
        field_name = rec.get("field_name", "")
        level = rec.get("evidence_level", "")
        base = {"field_id": field_id, "field_name": field_name,
                "evidence_level": level, "quote": quote}

        if not quote.strip():
            counts["skipped_no_quote"] += 1
            counts["unverified"] += 1
            entries.append({**base, "match_type": "SKIPPED_NO_QUOTE",
                            "unverified": True,
                            "detail": "Empty quote (E4_NR or not yet filled)."})
            continue

        if len(quote.strip()) < min_quote_len:
            counts["too_short"] += 1
            counts["unverified"] += 1
            entries.append({**base, "match_type": "TOO_SHORT", "unverified": True,
                            "detail": f"Quote shorter than {min_quote_len} chars; cannot verify mechanically."})
            continue

        norm_quote = normalize_text(quote)
        span = None
        pos = norm_source.find(norm_quote)
        if pos >= 0:
            counts["exact_match"] += 1
            span = (pos, pos + len(norm_quote))
            entry = {**base, "match_type": "EXACT", "unverified": False,
                     "detail": "Found after confusable-char/whitespace normalization."}
        elif join_hyphen_breaks(norm_quote) in joined_source:
            counts["hyphen_join"] += 1
            entry = {**base, "match_type": "HYPHEN_JOIN", "unverified": False,
                     "detail": "Found after re-joining hyphenated line breaks."}
        else:
            ratio = _best_fuzzy_window(tokenize(norm_quote), source_tokens)
            if ratio >= fuzzy_threshold:
                counts["fuzzy_match"] += 1
                entry = {**base, "match_type": "FUZZY", "unverified": False,
                         "detail": f"Token containment {ratio:.3f} >= {fuzzy_threshold}; "
                                   "likely extraction artifact, verify manually."}
            else:
                counts["not_found"] += 1
                entry = {**base, "match_type": "NOT_FOUND", "unverified": True,
                         "detail": "Quote not located in source document. "
                                   "Per the E1-E4 contract this record must be demoted "
                                   "(quote unverified -> treat as UNSUPPORTED until human-confirmed)."}

        # F1b: value–quote alignment runs on every record that carries a quote.
        va = check_value_alignment(rec, norm_source, span, source_text)
        if va is not None:
            counts["value_checked"] += 1
            entry["value_alignment"] = va
            if va["verdict"] == "ALIGNED":
                counts["value_aligned"] += 1
            elif va["verdict"] == "NOT_FOUND_IN_SOURCE":
                counts["value_not_found_in_source"] += 1
                entry["unverified"] = True
                counts["unverified"] += 1
            elif va["verdict"] == "NOT_IN_QUOTE_CONTEXT":
                counts["value_not_in_quote_context"] += 1
                # The value exists in the paper but not where the quote is.
                # That is "right number, wrong place": it must not be
                # deliverable as a verified record.
                entry["unverified"] = True
                counts["unverified"] += 1
            elif va["verdict"] == "UNIT_MISMATCH":
                # R02：数字对上了但单位/量纲不同，同样不是"已验证"。
                counts["value_unit_mismatch"] += 1
                entry["unverified"] = True
                counts["unverified"] += 1
            elif va["verdict"] == "UNKNOWN_UNIT":
                # T03：本层不支持该单位 -> 待核验，不得算通过。
                counts["value_unknown_unit"] += 1
                entry["unverified"] = True
                counts["unverified"] += 1
            elif va["verdict"] == "UNPARSEABLE_VALUE":
                # R02：含数字却解析不出数量 → 待核验，不得算通过。
                counts["value_unparsable"] += 1
                entry["unverified"] = True
                counts["unverified"] += 1
        entries.append(entry)

    total = len(entries)
    unverified = counts["unverified"]
    out_of_context = counts["value_not_in_quote_context"]
    value_broken = (counts["value_not_found_in_source"]
                    + counts["value_unit_mismatch"] + counts["value_unknown_unit"]
                    + counts["value_unparsable"])
    if unverified_policy == UNVERIFIED_FAIL:
        gate = unverified > 0 or counts["not_found"] > 0 or out_of_context > 0
    else:
        # An explicit opt-out of the *quote* policy must not also excuse a value
        # anchored in the wrong place, in the wrong unit, or not parsable at all.
        gate = counts["not_found"] > 0 or out_of_context > 0 or value_broken > 0
    return {
        "summary": {
            "total_records": total,
            **counts,
            "unverified_policy": unverified_policy,
            "gate_failed": gate,
        },
        "entries": entries,
    }


def gate_failed(report: Dict[str, Any], strict: bool = False) -> bool:
    """Hard gate.

    Fails on: NOT_FOUND always; a value absent from the whole source; a value
    present in the paper but not anchored at the quote (NOT_IN_QUOTE_CONTEXT);
    FUZZY under --strict; and unverified records unless --unverified-policy
    explicitly downgrades them. Unverified = empty quote, quote below the length
    floor, or any of the value-anchoring failures above.
    """
    s = report["summary"]
    if s["not_found"] > 0:
        return True
    if s.get("value_not_found_in_source", 0) > 0:
        return True
    if s.get("value_not_in_quote_context", 0) > 0:
        return True
    if s.get("value_unit_mismatch", 0) > 0:
        return True
    if s.get("value_unknown_unit", 0) > 0:
        return True
    if s.get("value_unparsable", 0) > 0:
        return True
    if strict and s["fuzzy_match"] > 0:
        return True
    if s.get("unverified_policy", UNVERIFIED_FAIL) == UNVERIFIED_FAIL \
            and s.get("unverified", 0) > 0:
        return True
    return False


def source_provenance(path: Path) -> Dict[str, Any]:
    """Hash and size of the gate's -s source (F1c).

    The gate is only as trustworthy as the source handed to it: appending 184
    bytes of forged text to a copy of the source flipped a record from
    NOT_FOUND/exit=1 to EXACT/exit=0 in testing, with no trace recorded.
    """
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def verify_source_pins(pins: Dict[str, Any], prov: Dict[str, Any]) -> List[str]:
    """Compare a stored provenance manifest against the current source."""
    problems: List[str] = []
    if not isinstance(pins, dict):
        return ["source_pins is not an object"]
    exp = pins.get("sha256")
    if exp and exp != prov["sha256"]:
        problems.append("sha256 mismatch: pinned %s, actual %s" % (exp, prov["sha256"]))
    sz = pins.get("size_bytes")
    if isinstance(sz, int) and sz != prov["size_bytes"]:
        problems.append("size mismatch: pinned %d, actual %d" % (sz, prov["size_bytes"]))
    return problems


def load_source_text(path: Path) -> str:
    """Read TXT directly; extract PDF text via pypdf/PyPDF2 if available."""
    if path.suffix.lower() == ".pdf":
        pypdf = None
        try:
            import pypdf as pypdf  # noqa: F811
        except ImportError:
            try:
                import PyPDF2 as pypdf  # type: ignore
            except ImportError:
                print("[ERROR] PDF source requires pypdf: pip install pypdf "
                      "(or provide a plain-text extraction instead).", file=sys.stderr)
                sys.exit(2)
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScholarFlow mechanical quote back-verification gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python quote_audit.py -i evidence.json -s paper.pdf
  python quote_audit.py -i evidence.json -s paper.txt --strict -o audit_report.json
Exit codes: 0 all verified | 1 gate failed | 2 input error
        """)
    parser.add_argument("-i", "--evidence", required=True,
                        help="Evidence JSON following schemas/extraction_result.schema.json")
    parser.add_argument("-s", "--source", required=True, help="Source document (.pdf or .txt)")
    parser.add_argument("-o", "--output", help="Optional path to write the JSON audit report")
    parser.add_argument("--strict", action="store_true",
                        help="Treat FUZZY matches as gate failures as well")
    parser.add_argument("--min-quote-len", type=int, default=MIN_QUOTE_LEN)
    parser.add_argument("--unverified-policy", choices=UNVERIFIED_POLICIES,
                        default=UNVERIFIED_FAIL,
                        help="How to treat records the gate cannot verify (empty quote / "
                             "too short / quote not found). Default 'fail' — a blank quote "
                             "must not be a silent escape hatch.")
    parser.add_argument("--source-pins", metavar="PINS_JSON",
                        help="Provenance manifest with sha256/size_bytes to pin the -s source")
    parser.add_argument("--write-source-pins", metavar="PINS_JSON",
                        help="Record the current -s provenance (sha256/size_bytes) and continue")
    args = parser.parse_args()

    ev_path, src_path = Path(args.evidence), Path(args.source)
    if not ev_path.exists() or not src_path.exists():
        print("[ERROR] Evidence or source file not found.", file=sys.stderr)
        sys.exit(2)

    try:
        evidence = json.loads(ev_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Evidence JSON invalid: {e}", file=sys.stderr)
        sys.exit(2)

    prov = source_provenance(src_path)

    if args.write_source_pins:
        pins_path = Path(args.write_source_pins)
        pins_path.parent.mkdir(parents=True, exist_ok=True)
        pins_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Source provenance pinned to: {pins_path}")

    pin_problems: List[str] = []
    if args.source_pins:
        pins_path = Path(args.source_pins)
        if not pins_path.exists():
            pin_problems.append(f"pins file not found: {pins_path}")
        else:
            try:
                pins = json.loads(pins_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                pins = None
                pin_problems.append(f"pins file invalid JSON: {e}")
            if pins is not None:
                pin_problems = verify_source_pins(pins, prov)

    source_text = load_source_text(src_path)
    report = audit_evidence(evidence, source_text, min_quote_len=args.min_quote_len,
                            unverified_policy=args.unverified_policy)
    report["summary"]["source_provenance"] = prov
    report["summary"]["source_pin_problems"] = pin_problems
    report["summary"]["gate_failed"] = gate_failed(report, strict=args.strict) or bool(pin_problems)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Audit report saved to: {out}")

    s = report["summary"]
    print("=" * 56)
    print(" ScholarFlow Quote Back-Verification Report")
    print("=" * 56)
    print(f" Records in evidence JSON : {s['total_records']}")
    print(f" EXACT match              : {s['exact_match']}")
    print(f" HYPHEN_JOIN match        : {s['hyphen_join']}")
    print(f" FUZZY match (>=thr)      : {s['fuzzy_match']}" + ("  [--strict: FAILED]" if args.strict and s['fuzzy_match'] else ""))
    print(f" TOO_SHORT (unverifiable) : {s['too_short']}")
    print(f" SKIPPED (empty quote)    : {s['skipped_no_quote']}")
    print(f" NOT_FOUND                : {s['not_found']}")
    print("-" * 56)
    print(f" Value tokens checked     : {s['value_checked']}")
    print(f"   value ALIGNED          : {s['value_aligned']}")
    print(f"   value NOT_IN_CONTEXT   : {s['value_not_in_quote_context']}")
    print(f"   value ABSENT FROM SRC  : {s['value_not_found_in_source']}  <- fabrication signal")
    print(f" Unverified records       : {s['unverified']}  (policy={s['unverified_policy']})")
    print(f" Source sha256            : {prov['sha256'][:16]}…  ({prov['size_bytes']} bytes)")
    if pin_problems:
        print(" SOURCE PIN PROBLEMS      :")
        for p in pin_problems:
            print(f"   - {p}")
    print("=" * 56)
    for e in report["entries"]:
        if e["match_type"] in ("NOT_FOUND", "TOO_SHORT", "FUZZY", "SKIPPED_NO_QUOTE"):
            print(f" [{e['match_type']}] {e['field_id']} {e['field_name']}: {e['detail']}")
        va = e.get("value_alignment")
        if va and va["verdict"] != "ALIGNED":
            print(f" [VALUE_{va['verdict']}] {e['field_id']} {e['field_name']}: {va['detail']}")

    sys.exit(1 if report["summary"]["gate_failed"] else 0)


if __name__ == "__main__":
    main()
