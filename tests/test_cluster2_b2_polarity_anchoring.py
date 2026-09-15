# -*- coding: utf-8 -*-
"""B2 批次（extraction 极性+值锚定族）回归测试 — 20260913-e2e-cluster2 第二轮。

对应 Panel 决议书（07-panel/moderator/CONSENSUS.md）B2 行：
- H-01  方向洗白：L613 语义短路拆除 + 极性三值化 fail-closed（UNRESOLVED）+ 子句绑定；
- H-02/H-82 否定/反义词表收敛到 shared/text/polarity.py（neither/nor、反转动词、
  n't 收缩词、中文"不同"排除集）+ 四类误挡正例成对落库；
- H-04  metric_direction 受益词表白名单（删 score/rate），白名单外 →
  UNKNOWN_METRIC_DIRECTION + eligible=False；
- H-03  quote_audit 五件半边：FUZZY 值回源文窗口核验（禁自锚定）、比较符双侧
  条件、语义位（同句窗口）、文本型显著性判语 NOT_VERIFIABLE 禁 promotion、
  --strict 语义文档化；
- H-30  CONFUSABLE_TABLE 补 U+00BC/BD/BE、U+3002、全角比较符（既有误挡样例
  B10/B11 零新增失败 = 硬门槛）；
- H-32  派生量纲注册（mass/volume、count/volume、ppm/ppb），25 与 999 mg/L 可区分；
- H-33  区间负号（"83 −85%"）+ 字母邻接负号标不可信（"at-20.5"）；
- H-35  AECE 否定扫描限定目标句（pypdf 零空行整篇"段落"根因）；
- H-37  管线 ATTRIBUTE 数值核验复用 quote_audit.extract_quantities；
- H-17  quote_audit 信封缺失/0 条 → rc≠0 结构化报错；
- 设施-1 summary 计数（UNRESOLVED / UNKNOWN_METRIC_DIRECTION / NOT_VERIFIABLE ...）
  写入 quote_audit 与 alignment 产物；
- ≥8 条真实论文 EXACT/FUZZY 正例（句子逐字取自
  端到端真实跑/20260913-e2e-cluster2/03-extraction/runner/texts/ 的 pypdf 文本，
  含真实排版伪影 ¼、ﬁ 连字、折行）。

红线：每个拒绝用例都配同构合法正例（防 H-82 式副作用）。
运行：python -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sys.path bootstrap)

REPO_ROOT = helpers.REPO_ROOT
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "literature-evidence-extraction", "scripts"))

import claim_alignment as cal  # noqa: E402
import quote_audit as qa  # noqa: E402
from context_expansion import (  # noqa: E402
    AlignmentStatus, CandidateType, TINTaskType,
    evaluate_target_alignment, expand_candidate_context,
)
from extraction_pipeline import process_candidate  # noqa: E402

CTX_RESULT = {"source_role": "CURRENT_STUDY_RESULT", "location": "Results"}


def _verify(claim_text, evidence, predicate="", obj="", subject="", ctx=None):
    claim = {"text": claim_text, "subject": subject, "predicate": predicate, "object": obj}
    return cal.verify_claim_alignment(claim, evidence, ctx or dict(CTX_RESULT))


def _value_verdict(source, value):
    """对逐字引句 + 抽取值跑 quote_audit，返回 (value_verdict, gate_failed, entry)。"""
    report = qa.audit_evidence(
        {"evidence_records": [{"verbatim_quote": source, "extracted_value": value}]}, source)
    entry = report["entries"][0]
    return ((entry.get("value_alignment") or {}).get("verdict"),
            qa.gate_failed(report), entry)


# ---------------------------------------------------------------------------
# H-01 极性门：L613 短路拆除 + 三值化 + 子句绑定
# ---------------------------------------------------------------------------

class TestH01PolarityGate(unittest.TestCase):
    """EXT-C-01 四攻击 → CONTRADICTORY/UNRESOLVED；语义短路不得先于极性检查。"""

    def test_l613_semantic_short_circuit_cannot_bypass_polarity(self):
        """回归：semantic_verdict=SUPPORTED + 谓词在场曾在极性检查之前 return。"""
        claim = {"text": "Drug X increases mortality", "subject": "Drug X",
                 "predicate": "increases", "object": "mortality",
                 "semantic_verdict": "SUPPORTED"}
        evidence = "Drug X reversed the increase in mortality after dosing (P = 0.01)."
        result = cal.verify_claim_alignment(claim, evidence, dict(CTX_RESULT))
        self.assertNotEqual(result["status"], "SUPPORTED")
        self.assertFalse(result["is_confirmed_eligible"])
        # 同构合法正例：忠实证词 + 自报 SUPPORTED 仍然放行（配对正例）
        ok = cal.verify_claim_alignment(
            dict(claim, text="Drug X increases mortality"),
            "Drug X increased mortality after dosing (P = 0.01).", dict(CTX_RESULT))
        self.assertEqual(ok["status"], "SUPPORTED")
        self.assertTrue(ok["is_confirmed_eligible"])

    def test_ext_c01_reversal_verbs_rejected(self):
        for verb_phrase, claim_text, evidence, obj in (
            ("reversed", "Drug X increases mortality",
             "Drug X reversed the increase in mortality after dosing (P = 0.01).", "mortality"),
            ("abolished", "Gene knockout increases survival",
             "Knockout of gene X abolished the increase in survival (P = 0.01).", "survival"),
            ("eliminated", "Treatment increases lesion count",
             "Treatment eliminated the rise in lesion count within two weeks.", "lesion count"),
            ("overturned", "The antagonist increases cAMP levels",
             "The antagonist overturned the elevation of cAMP levels in vitro.", "cAMP levels"),
        ):
            with self.subTest(verb=verb_phrase):
                result = _verify(claim_text, evidence,
                                 predicate="increases", obj=obj,
                                 subject="Drug X" if "Drug X" in evidence else claim_text.split()[0])
                self.assertNotEqual(result["status"], "SUPPORTED", evidence)
                self.assertFalse(result["is_confirmed_eligible"], evidence)

    def test_ext_c01_reversal_positive_pairs(self):
        """每个反转动词拒绝配同构合法正例：反转消除的是"下降"时，肯定方向不被极性门误挡。"""
        pairs = [
            ("Drug X reversed the decrease in mortality after dosing (P = 0.01).",
             "Drug X increases mortality"),
            ("Knockout of gene X abolished the decrease in survival (P = 0.01).",
             "Gene knockout increases survival"),
        ]
        for evidence, claim_text in pairs:
            with self.subTest(evidence=evidence):
                result = _verify(claim_text, evidence,
                                 predicate="increases",
                                 obj="mortality" if "mortality" in evidence else "survival",
                                 subject="Drug X" if "Drug X" in evidence else "Knockout of gene X")
                self.assertNotEqual(result["audit_verdict"], "REJECT_POLARITY_MISMATCH", evidence)
                self.assertNotEqual(result["status"], "CONTRADICTORY", evidence)

    def test_ext_c01_neither_nor_is_not_support(self):
        result = _verify("Drug X promotes tumor growth",
                         "Drug X neither promotes nor inhibits tumor growth in the assay.",
                         predicate="promotes", obj="tumor growth", subject="Drug X")
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertEqual(result["audit_verdict"], "POLARITY_UNRESOLVED")
        self.assertFalse(result["is_confirmed_eligible"])
        # 配对正例：明确肯定句放行
        ok = _verify("Drug X promotes tumor growth",
                     "Drug X promotes tumor growth in the assay.",
                     predicate="promotes", obj="tumor growth", subject="Drug X")
        self.assertEqual(ok["status"], "SUPPORTED")

    def test_ext_c01_mixed_direction_sentence_is_unresolved(self):
        """同句双方向（BOTH）不再静默跳过比较：UNRESOLVED 交人工。"""
        evidence = ("Drug X increases tumor growth while the control arm decreases "
                    "survival markers in the same assay window (p<0.01).")
        result = _verify("Drug X decreases tumor growth", evidence,
                         predicate="decreases", obj="tumor growth", subject="Drug X")
        self.assertEqual(result["audit_verdict"], "POLARITY_UNRESOLVED")
        self.assertFalse(result["is_confirmed_eligible"])
        self.assertEqual(result["status"], "AMBIGUOUS")
        # 方向正确的对照（同构合法正例）：子句绑定把肯定主张锚定到自己的分支，
        # 忠实方向照常 SUPPORTED——只有反向主张被 fail-closed。
        control = _verify("Drug X increases tumor growth", evidence,
                          predicate="increases", obj="tumor growth", subject="Drug X")
        self.assertEqual(control["audit_verdict"], "PASS", control)

    def test_polarity_unresolved_counted_in_summary(self):
        """设施-1：UNRESOLVED 每次拒绝可读数。"""
        evidence = ("Drug X increases tumor growth while the control arm decreases "
                    "survival markers in the same assay window (p<0.01).")
        result = _verify("Drug X decreases tumor growth", evidence,
                         predicate="decreases", obj="tumor growth", subject="Drug X")
        self.assertEqual(result["summary"]["polarity_unresolved"], 1)
        ok = _verify("Drug X increases mortality",
                     "Drug X increased mortality after dosing (P = 0.01).",
                     predicate="increases", obj="mortality", subject="Drug X")
        self.assertEqual(ok["summary"]["polarity_unresolved"], 0)

    def test_contrastive_negation_does_not_cross_branch(self):
        """L613 短路拆除回归（runner CA-11 同机理）：谓词 grounded 在另一分支。"""
        evidence = ("Drug X increases tumor growth while the control arm decreases "
                    "survival markers in the same assay window (p<0.01).")
        claim = {"text": "Drug X decreases tumor growth", "subject": "Drug X",
                 "predicate": "decreases", "object": "tumor growth",
                 "semantic_verdict": "SUPPORTED"}
        result = cal.verify_claim_alignment(claim, evidence, dict(CTX_RESULT))
        self.assertNotEqual(result["status"], "SUPPORTED")
        self.assertFalse(result["is_confirmed_eligible"])

    def test_clause_binding_far_negation_positive(self):
        """H-82：他者否定（20 词外）不再误挡主句肯定。"""
        evidence = ("Unlike drug B, which did not increase feeding in any trial, "
                    "drug A increases feeding in a dose-dependent manner.")
        result = _verify("drug A increases feeding", evidence,
                         predicate="increases", obj="feeding", subject="drug A")
        self.assertEqual(result["status"], "SUPPORTED", result)
        # 配对拒绝：否定落在谓词所在子句时仍拦
        neg = _verify("drug A increases feeding",
                      "drug A did not increase feeding in any trial.",
                      predicate="increases", obj="feeding", subject="drug A")
        self.assertEqual(neg["status"], "CONTRADICTORY")

    def test_did_not_increase_still_contradictory(self):
        """EXT-C-01 对照组（防御有效项）不回归：'did not increase' → CONTRADICTORY。"""
        result = _verify("Drug X increases mortality",
                         "Drug X did not increase mortality in any group.",
                         predicate="increases", obj="mortality", subject="Drug X")
        self.assertEqual(result["status"], "CONTRADICTORY")


# ---------------------------------------------------------------------------
# H-02/H-82 词表收敛与误挡正例
# ---------------------------------------------------------------------------

class TestH02H82Lexicon(unittest.TestCase):
    """shared/text/polarity.py 单一真源 + 词边界 + 双否定 + 中文。"""

    def test_module_is_single_source(self):
        from shared.text import polarity as pol
        self.assertIs(cal.NEGATION_MARKERS, pol.NEGATION_MARKERS)
        self.assertIs(cal.ANTONYM_CLASSES, pol.ANTONYM_PAIRS)

    def test_new_markers_present(self):
        from shared.text import polarity as pol
        markers = " ".join(pol.NEGATION_MARKERS)
        for word in ("neither", "nor", "don't", "doesn't", "didn't", "cannot",
                     "未", "无显著"):
            self.assertIn(word, markers)
        reversal = " ".join(pol.REVERSAL_MARKERS)
        for word in ("abolish", "reverse", "eliminate", "overturn"):
            self.assertIn(word, reversal)

    def test_cannot_word_boundary(self):
        """cannot 按词处理：不能作为 'not ' 子串误报，也不能漏报。"""
        # cannot + 否定性动词 = 双否定 → 对后续命题肯定（H-82 cannot 正例）
        self.assertFalse(__import__("shared.text.polarity", fromlist=["is_negated"])
                         .is_negated("We cannot exclude that drug A increases feeding."))
        # cannot + 普通动词 = 否定
        self.assertTrue(__import__("shared.text.polarity", fromlist=["is_negated"])
                        .is_negated("The drug cannot increase survival."))

    def test_double_negation_positives(self):
        """'not unknown' / 双否定 / cannot but 正例成对落库不回归。"""
        result = _verify("This species is not unknown to science",
                         "The species is not unknown in the regional flora surveys.",
                         predicate="", obj="", subject="species")
        self.assertNotEqual(result["audit_verdict"], "REJECT_POLARITY_MISMATCH")
        self.assertNotEqual(result["audit_verdict"], "POLARITY_UNRESOLVED")
        # cannot but + 动词 = 必定
        ok = _verify("The treatment increases survival",
                     "Given the effect size, the treatment cannot but increase survival.",
                     predicate="increases", obj="survival", subject="treatment")
        self.assertNotEqual(ok["audit_verdict"], "REJECT_POLARITY_MISMATCH")

    def test_double_negation_rejects_when_single_side_negated(self):
        """配对拒绝：一侧双否定（肯定义）对另一侧真否定，方向相反仍拦。"""
        result = _verify("The species is unknown to science",
                         "The species is not unknown in the regional flora surveys.",
                         predicate="", obj="", subject="species")
        self.assertNotEqual(result["status"], "SUPPORTED")

    def test_chinese_bu_tong_is_not_negation(self):
        """中文'不同'命中单字否定'不'的误挡（EXT-C-03）必须保持 ALIGNED。"""
        result = _verify("鼠兔取食强度在退化草甸增加",
                         "不同样地间鼠兔取食强度显著增加（P<0.05）。",
                         predicate="增加", obj="取食强度", subject="鼠兔")
        self.assertEqual(result["status"], "SUPPORTED", result)
        self.assertEqual(result["audit_verdict"], "PASS")

    def test_chinese_negatives_still_rejected(self):
        """配对拒绝：中文真否定（未见/无显著/未）仍拦。"""
        for evidence in ("鼠兔取食强度未见显著增加。",
                         "处理组取食强度无显著变化。",
                         "鼠兔取食强度并未增加。"):
            with self.subTest(evidence=evidence):
                result = _verify("鼠兔取食强度在退化草甸增加", evidence,
                                 predicate="增加", obj="取食强度", subject="鼠兔")
                self.assertNotEqual(result["status"], "SUPPORTED", evidence)

    def test_nt_contractions_rejected(self):
        """don't/doesn't/didn't 收缩词进词表（H-02 debate 侧缺口）。"""
        from shared.text import polarity as pol
        for text in ("The drug doesn't reduce mortality.",
                     "They don't reduce fever.",
                     "It didn't increase survival."):
            with self.subTest(text=text):
                self.assertTrue(pol.is_negated(text))
        # 配对正例：肯定句不误挡
        self.assertFalse(pol.is_negated("The drug does reduce mortality."))

    def test_decreas_root_grounded(self):
        """EXT-R-09：decreas/declin 词根补齐，'decreased' 不再 UNSUPPORTED_PREDICATE。"""
        result = _verify("Treatment A reduces mortality",
                         "Treatment A significantly decreased mortality across all sites.",
                         predicate="reduces", obj="mortality", subject="Treatment A")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertEqual(result["audit_verdict"], "PASS")
        result2 = _verify("Treatment A reduces mortality",
                          "Abundance declined sharply after the treatment began.",
                          predicate="reduces", obj="abundance", subject="Abundance")
        self.assertEqual(result2["audit_verdict"], "PASS")


# ---------------------------------------------------------------------------
# H-04 metric_direction 白名单
# ---------------------------------------------------------------------------

def _table(metric, target="0.3", baseline="0.1", direction=None):
    bundle = {"type": "TABLE_HEADER_ROW_BUNDLE", "column_header": metric,
              "row_identifier": "Model X", "baseline_row_identifier": "Model Y",
              "cell_values": {"target": target, "baseline": baseline}}
    if direction is not None:
        bundle["metric_direction"] = direction
    return bundle


class TestH04MetricDirectionWhitelist(unittest.TestCase):
    """泛化词（score/rate）删除；白名单外 → UNKNOWN_METRIC_DIRECTION + eligible=False。"""

    def _run(self, metric, **kw):
        return cal.verify_claim_alignment(
            {"text": "Model X outperforms Model Y", "subject": "Model X",
             "predicate": "outperforms", "object": "Model Y"},
            "Table 3", {"source_role": "CURRENT_STUDY_RESULT", "location": "Table 3"},
            table_bundle=_table(metric, **kw))

    def test_higher_is_worse_metrics_not_flipped(self):
        """EXT-C-02 三夹具：假阳性率/感染率/复发率翻倍不得判目标方胜出。"""
        for metric in ("false positive rate", "infection rate", "recurrence rate"):
            with self.subTest(metric=metric):
                result = self._run(metric)
                self.assertEqual(result["audit_verdict"], "UNKNOWN_METRIC_DIRECTION")
                self.assertEqual(result["status"], "AMBIGUOUS")
                self.assertFalse(result["is_confirmed_eligible"])

    def test_plain_rate_and_score_no_longer_beneficiary(self):
        result = self._run("score")
        self.assertEqual(result["audit_verdict"], "UNKNOWN_METRIC_DIRECTION")
        result = self._run("rate")
        self.assertEqual(result["audit_verdict"], "UNKNOWN_METRIC_DIRECTION")

    def test_explicit_beneficiary_metrics_unchanged(self):
        """正例：survival/accuracy/yield 明确受益词行为不变。"""
        for metric, direction in (("survival", "SUPPORTED"),
                                  ("accuracy", "SUPPORTED"),
                                  ("yield", "SUPPORTED")):
            with self.subTest(metric=metric):
                result = self._run(metric)
                self.assertEqual(result["status"], direction)
                self.assertTrue(result["is_confirmed_eligible"])

    def test_lower_is_better_metrics_unchanged(self):
        for metric in ("mortality", "loss", "toxicity"):
            with self.subTest(metric=metric):
                result = self._run(metric)
                self.assertEqual(result["status"], "CONTRADICTORY")  # 0.3 > 0.1 但低者胜

    def test_explicit_direction_still_honored(self):
        """既有用例契约：显式传 metric_direction 的行为不变。"""
        result = cal.verify_claim_alignment(
            {"text": "Model X outperforms Model Y", "subject": "Model X",
             "predicate": "outperforms", "object": "Model Y"},
            "Table 3", {"source_role": "CURRENT_STUDY_RESULT", "location": "Table 3"},
            table_bundle=_table("CustomMetric", target="0.12", baseline="0.45",
                                direction="LOWER_IS_BETTER"))
        self.assertEqual(result["status"], "SUPPORTED")
        result = self._run("CustomMetric", direction="UNKNOWN")
        self.assertEqual(result["audit_verdict"], "UNKNOWN_METRIC_DIRECTION")

    def test_unknown_direction_counted_in_summary(self):
        """设施-1：UNKNOWN_METRIC_DIRECTION 计数入 summary。"""
        result = self._run("false positive rate")
        self.assertEqual(result["summary"]["unknown_metric_direction"], 1)


# ---------------------------------------------------------------------------
# H-03 值锚定五件半边
# ---------------------------------------------------------------------------

class TestH03FuzzyValueReanchoring(unittest.TestCase):
    """① FUZZY 引句不可自证：extracted_value 必须回源文窗口核验。"""

    SOURCE = ("Mean canopy cover reached exactly 42 percent across every heavily grazed "
              "elevation belt after three consecutive drought seasons had ended. The survey "
              "teams also recorded livestock pressure, slope exposure and soil moisture at "
              "each visit during the two growing seasons. 45 percent of the plots were "
              "grazed by livestock according to the final survey records.")

    def _audit(self, quote, value):
        rec = {"field_id": "CC", "verbatim_quote": quote, "extracted_value": value}
        return qa.audit_evidence({"evidence_records": [rec]}, self.SOURCE)

    def test_doctored_fuzzy_quote_carries_forged_value_to_failure(self):
        """EXT-A-01 回归：42→45 篡改（FUZZY 容忍）+ 45% 源文他处真实存在 → FAILED rc≠0。"""
        quote = ("Mean canopy cover reached exactly 45 percent across every heavily grazed "
                 "elevation belt after three consecutive drought seasons had ended.")
        report = self._audit(quote, "45%")
        entry = report["entries"][0]
        self.assertEqual(entry["match_type"], "FUZZY")
        self.assertEqual((entry.get("value_alignment") or {}).get("verdict"),
                         "NOT_IN_QUOTE_CONTEXT")
        self.assertTrue(entry["unverified"])
        self.assertTrue(qa.gate_failed(report))

    def test_honest_quote_still_aligned(self):
        """配对正例：忠实的 42% 引句 EXACT + ALIGNED。"""
        quote = ("Mean canopy cover reached exactly 42 percent across every heavily grazed "
                 "elevation belt after three consecutive drought seasons had ended.")
        report = self._audit(quote, "42%")
        entry = report["entries"][0]
        self.assertEqual(entry["match_type"], "EXACT")
        self.assertEqual((entry.get("value_alignment") or {}).get("verdict"), "ALIGNED")
        self.assertFalse(qa.gate_failed(report))

    def test_unanchorable_fuzzy_quote_explicit_code(self):
        """无法回锚 → FUZZY_NOT_ANCHORED 显式码（不得静默通过）。"""
        long_source = " ".join(["filler sentence %d." % i for i in range(60)])
        quote = "completely unrelated narrative tokens with no overlap whatsoever here"
        rec = {"field_id": "F", "verbatim_quote": quote, "extracted_value": "1%"}
        report = qa.audit_evidence({"evidence_records": [rec]}, long_source)
        # containment < threshold → NOT_FOUND（诚实阻断）；本用例锁 NOT_FOUND 语义
        self.assertEqual(report["entries"][0]["match_type"], "NOT_FOUND")
        self.assertTrue(qa.gate_failed(report))


class TestH03ComparatorRules(unittest.TestCase):
    """② 比较符双侧条件比对：双侧不一致拦截，单侧缺失不误挡。"""

    SRC = "The effect was P < 0.05 in the tested group of plots."

    def test_both_sides_differ_blocked(self):
        verdict, failed, _ = _value_verdict(self.SRC, ">0.05")
        self.assertEqual(verdict, "NOT_FOUND_IN_SOURCE")
        self.assertTrue(failed)

    def test_both_sides_same_passes(self):
        verdict, failed, _ = _value_verdict(self.SRC, "P < 0.05")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)

    def test_one_sided_comparator_not_blocked(self):
        """单侧缺失（OCR 丢比较符 / 源文 '=' 用 ¼ 铸字）不因比较符误挡。"""
        verdict, failed, _ = _value_verdict(self.SRC, "0.05")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)

    def test_uncertainty_marker_one_sided_still_blocked(self):
        """±/~ 不确定度标记单侧出现仍阻断（既有契约不回退）。"""
        verdict, failed, _ = _value_verdict("The value was 0.3 in the sample.", "±0.3")
        self.assertTrue(failed)


class TestH03SemanticPosition(unittest.TestCase):
    """③ 语义位：值锚定窗口收窄到同句；'1,234 在 1,234,567 内' 维持拦截。"""

    def test_thousands_embedding_still_blocked(self):
        verdict, failed, _ = _value_verdict(
            "The sample yielded 1,234,567 reads in total.", "1,234")
        self.assertTrue(failed)

    def test_far_sentence_value_not_accepted_via_window(self):
        """值在 ±200 窗口内但跨句 → 不得以窗口为锚。"""
        src = ("Treatment raised survival to 88 percent in the first year of the trial. "
               "Mortality fell to 12 percent afterward among the control plots only.")
        rec = {"field_id": "F", "verbatim_quote":
               "Treatment raised survival to 88 percent in the first year of the trial.",
               "extracted_value": "12%"}
        report = qa.audit_evidence({"evidence_records": [rec]}, src)
        va = report["entries"][0].get("value_alignment") or {}
        self.assertEqual(va["verdict"], "NOT_IN_QUOTE_CONTEXT")
        self.assertTrue(qa.gate_failed(report))


class TestH03TextualValue(unittest.TestCase):
    """④ 文本型显著性判语 → NOT_VERIFIABLE 且禁 promotion。"""

    SRC = ("Seedling survival differed between treatments (P < 0.05, n = 120 plots) "
           "across the whole monitoring period of three years.")

    def test_not_significant_not_verifiable(self):
        """EXT-A-02 回归：篡改比较符 + 'not significant' 曾 rc=0。"""
        quote = ("Seedling survival differed between treatments (P > 0.05, n = 120 plots) "
                 "across the whole monitoring period of three years.")
        rec = {"field_id": "S", "verbatim_quote": quote, "extracted_value": "not significant"}
        report = qa.audit_evidence({"evidence_records": [rec]}, self.SRC)
        entry = report["entries"][0]
        self.assertEqual((entry.get("value_alignment") or {}).get("verdict"), "NOT_VERIFIABLE")
        self.assertTrue(entry["unverified"])
        self.assertTrue(qa.gate_failed(report))
        self.assertGreaterEqual(report["summary"]["value_not_verifiable"], 1)

    def test_descriptive_text_value_unchanged(self):
        """纯描述性文本值维持既有契约：不参与数值对齐、不因此失败。"""
        verdict, failed, _ = _value_verdict(self.SRC, "以木本植物叶及嫩枝为主")
        self.assertIsNone(verdict)
        self.assertFalse(failed)

    def test_numeric_verdict_still_verified(self):
        """配对正例：数值型判语照常核验。"""
        verdict, failed, _ = _value_verdict(self.SRC, "P < 0.05")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)

    def test_strict_semantics_documented(self):
        """⑤ --strict 语义文档化：模块 docstring 与 --strict help 声明容忍边界。"""
        doc = (qa.__doc__ or "")
        self.assertIn("--strict", doc)
        self.assertIn("NOT_VERIFIABLE", doc)
        self.assertIn("FUZZY", doc)


# ---------------------------------------------------------------------------
# H-30 confusable 切片（硬门槛：既有误挡样例零新增失败）
# ---------------------------------------------------------------------------

class TestH30ConfusableSlice(unittest.TestCase):

    def test_vulgar_fractions_are_equals(self):
        self.assertEqual(qa.normalize_text("\u00bc"), "=")
        self.assertEqual(qa.normalize_text("\u00bd"), "=")
        self.assertEqual(qa.normalize_text("\u00be"), "=")

    def test_ideographic_full_stop_normalized(self):
        self.assertEqual(qa.normalize_text("\u3002"), ".")

    def test_fullwidth_comparators_normalized(self):
        self.assertEqual(qa.normalize_text("\uff1c"), "<")
        self.assertEqual(qa.normalize_text("\uff1e"), ">")
        self.assertEqual(qa.normalize_text("\u2266"), "<=")
        self.assertEqual(qa.normalize_text("\u2267"), ">=")

    def test_b10_real_statistic_not_falsely_flagged(self):
        """硬门槛 B10（runner）：'P ¼ 0.002' 忠实抽取不再被诬 NOT_FOUND。"""
        src = ("Species richness differed (w 2 ¼ 9.99, df ¼ 1, P ¼ 0.002; Fig. 2a) "
               "between the paired sites.")
        for value in ("0.002", "P ¼ 0.002", "9.99"):
            with self.subTest(value=value):
                verdict, failed, _ = _value_verdict(src, value)
                self.assertEqual(verdict, "ALIGNED", value)
                self.assertFalse(failed, value)

    def test_b11_ocr_glued_statistic_no_new_failure(self):
        """硬门槛 B11（runner）：'P40.2' 引句逐字抽取保持 ALIGNED（零新增失败）。"""
        src = ("there was no significant effect of protection on rarefied richness "
               "(95% CI: -31.06 to 13.5%; w2 = 1.33, df = 1, P40.2; Fig. 2c)")
        verdict, failed, _ = _value_verdict(src, "P40.2")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)

    def test_fullwidth_comparator_quote_aligned(self):
        src = "The threshold was P＜0.01 for all models in the benchmark suite."
        verdict, failed, _ = _value_verdict(src, "P < 0.01")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)


# ---------------------------------------------------------------------------
# H-32 派生量纲
# ---------------------------------------------------------------------------

class TestH32DerivedUnits(unittest.TestCase):

    def test_mass_per_volume_registered(self):
        for form in ("25 mg/L", "25 mg/l", "500 µg/L", "500 μg/L", "2 ug/L"):
            q = qa.extract_quantities(form, strict_units=True)
            self.assertEqual(q[0]["dimension"], "mass_volume", form)
            self.assertIsNotNone(q[0]["factor"], form)

    def test_count_per_volume_registered(self):
        for form in ("10000 cells/mL", "50 ind/L", "20 ind/mL"):
            q = qa.extract_quantities(form, strict_units=True)
            self.assertEqual(q[0]["dimension"], "count_per_volume", form)

    def test_ppm_ppb_registered(self):
        self.assertEqual(qa.extract_quantities("12 ppm")[0]["dimension"], "concentration")
        self.assertEqual(qa.extract_quantities("3 ppb")[0]["dimension"], "concentration")

    def test_real_and_forged_concentration_distinguishable(self):
        """真实 25 mg/L ALIGNED；伪造 999 mg/L NOT_FOUND，detail 含量纲与数值。"""
        src = ("The measured concentration was 25 mg/L in the treated mesocosms "
               "throughout the experiment.")
        verdict, failed, _ = _value_verdict(src, "25 mg/L")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)
        verdict, failed, entry = _value_verdict(
            "The measured concentration was 999 mg/L in the treated mesocosms "
            "throughout the experiment.", "25 mg/L")
        self.assertEqual(verdict, "NOT_FOUND_IN_SOURCE")
        self.assertTrue(failed)
        detail = (entry.get("value_alignment") or {}).get("detail", "")
        self.assertIn("25", detail)
        quantities = (entry.get("value_alignment") or {}).get("quantities", [])
        self.assertTrue(any(q["dimension"] == "mass_volume" for q in quantities))


# ---------------------------------------------------------------------------
# H-33 数值符号
# ---------------------------------------------------------------------------

class TestH33NumericSigns(unittest.TestCase):

    def test_range_dash_is_separator(self):
        """'83 −85%'：两数字间减号按区间分隔符，忠实引句 ALIGNED。"""
        src = ("We show that 83 −85% of the surveys presented losses in forest biomass "
               "and tree species richness.")
        for value in ("83-85%", "85%", "83"):
            with self.subTest(value=value):
                verdict, failed, _ = _value_verdict(src, value)
                self.assertEqual(verdict, "ALIGNED", value)
                self.assertFalse(failed, value)

    def test_semantically_wrong_negative_not_aligned(self):
        """语义错误的 '-85%' 不得 ALIGNED（runner 与 verifier 双双中招处）。"""
        src = ("We show that 83 −85% of the surveys presented losses in forest biomass "
               "and tree species richness.")
        verdict, failed, _ = _value_verdict(src, "-85%")
        self.assertEqual(verdict, "NOT_FOUND_IN_SOURCE")
        self.assertTrue(failed)

    def test_letter_glued_minus_untrusted(self):
        """'at-20.5'（OCR 丢空格）：丢负号的伪造值不得 ALIGNED。"""
        src = "The reactor was held at-20.5 °C for the whole incubation period."
        verdict, failed, _ = _value_verdict(src, "20.5 °C")
        self.assertEqual(verdict, "NOT_FOUND_IN_SOURCE")
        self.assertTrue(failed)

    def test_spaced_minus_faithful_still_aligned(self):
        """配对正例：源文负号前有空界（'at -20.5 °C'）时忠实负值 ALIGNED。"""
        src = "The reactor was held at -20.5 °C for the whole incubation period."
        verdict, failed, _ = _value_verdict(src, "-20.5 °C")
        self.assertEqual(verdict, "ALIGNED")
        self.assertFalse(failed)

    def test_sign_flip_still_blocked(self):
        """既有契约不回退：源文 -5 Gy 抽 5 Gy 仍阻断。"""
        src = "The net change was -5 Gy after correction of the dose."
        verdict, failed, _ = _value_verdict(src, "5 Gy")
        self.assertTrue(failed)


# ---------------------------------------------------------------------------
# H-35 AECE 否定扫描限定目标句
# ---------------------------------------------------------------------------

class TestH35NegationScope(unittest.TestCase):
    """pypdf 零空行文本 → 整篇一个"段落"；否定扫描必须只看目标句。"""

    DOC = (
        "3. Results\n"
        "No significant difference was observed in any preliminary screening round of "
        "the survey and no treatment effect emerged in that phase of the study. "
        + "Filler sentence describing methodology details and site conditions. " * 60 +
        "Nitrogen addition significantly increased microbial respiration by 28.5%."
    )

    def _align(self):
        tin = {"task_type": TINTaskType.CLAIM,
               "target_claim": "Nitrogen addition increases microbial respiration",
               "target_entity": "nitrogen addition"}
        offset = self.DOC.find("28.5%")
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "28.5%", "offset": offset}
        ctx = expand_candidate_context(self.DOC, cand, tin=tin)
        return evaluate_target_alignment(tin, ctx), ctx

    def test_far_negation_does_not_poison_target_sentence(self):
        align, ctx = self._align()
        # 旧实现：整篇（本夹具 ≥2000 字符）扫描 → "No significant" 误判 CONTRADICTS_TARGET
        self.assertNotEqual(align["status"], AlignmentStatus.CONTRADICTS_TARGET, align)
        # 段落启发式全量改造 DEFER（决议 H-35 半边）：切分行为本轮不动
        self.assertIn(ctx["level_reached"], ("SENTENCE", "ADJACENT_SENTENCES", "PARAGRAPH"))

    def test_negation_in_target_sentence_still_contradicts(self):
        """硬门槛（--test 同构）：目标句内的否定仍报 CONTRADICTS_TARGET。"""
        doc = ("However, Compound Y did not significantly affect performance in the "
               "replicated mesocosm experiment.")
        tin = {"task_type": TINTaskType.CLAIM,
               "target_claim": "Compound Y affects performance",
               "target_entity": "Compound Y"}
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "affect",
                "offset": doc.find("did not")}
        ctx = expand_candidate_context(doc, cand, tin=tin)
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.CONTRADICTS_TARGET)


# ---------------------------------------------------------------------------
# H-37 管线 ATTRIBUTE 数值核验
# ---------------------------------------------------------------------------

class TestH37PipelineAttributeValueVerification(unittest.TestCase):

    DOC = ("3. Results\n"
           "PCR was first described in 1985 and widely adopted by molecular laboratories "
           "worldwide for routine diagnostics.")
    DOC_REAL = ("3. Results\n"
                "The PCR reaction volume was 20 uL in all reactions and cycling used 35 "
                "amplification rounds.")

    def _tin(self):
        return {"task_type": "ATTRIBUTE", "target_entity": "PCR",
                "target_field": "pcr_description", "expected_value_type": "NUMERIC"}

    def _run(self, doc, value, hit="PCR"):
        cand = {"id": "CAND-01", "type": CandidateType.TEXT_SENTENCE,
                "text": hit, "offset": doc.find(hit), "section": "Results"}
        return process_candidate(tin=self._tin(), candidate=cand, doc_text=doc,
                                 record_id="REC-01", field="pcr_volume",
                                 extracted_value=value)

    def test_forged_value_not_promoted(self):
        """EXT-D-01 回归：伪造 25 uL（上下文唯一数字 1985）不得升级 SUPPORTED/EXPLICIT。"""
        res = self._run(self.DOC, "25 uL")
        self.assertFalse(res["promoted"])
        self.assertIsNone(res["evidence_record"])
        self.assertIsNotNone(res.get("error"))
        ccr = res["candidate_context_record"]
        self.assertNotEqual(ccr["alignment"]["status"], "ALIGNED")

    def test_real_attribute_value_promoted(self):
        """真实 ATTRIBUTE 正例：20 uL 在上下文中 → 照常提升。"""
        res = self._run(self.DOC_REAL, "20 uL", hit="20 uL")
        self.assertTrue(res["promoted"], res.get("error"))
        self.assertIsNotNone(res["evidence_record"])

    def test_dimension_mismatch_blocked(self):
        """同数值不同量纲（20 uL 抽成 20 mL）不得锚定。"""
        res = self._run(self.DOC_REAL, "20 mL", hit="20 uL")
        self.assertFalse(res["promoted"])

    # ---- P1（2026-09-15 集群审查）：锚定对象是引句，不是 AECE 扩展上下文 ----
    #: 引句无数字 ⇒ 完整性检查判 NUMERIC_VALUE 缺失 ⇒ AECE 逐级升到 PARAGRAPH
    #: （零空行文本 = 整段即整篇，pypdf 常态）；值 `25 uL` 落在远离引句的另一实验里。
    _HIT = "The PCR reaction volume was recorded for every sample."
    DOC_FAR_VALUE = ("Results " + _HIT + " "
                     + ("The study site is described in detail elsewhere in this report. " * 4)
                     + "In a separate assay the PCR reaction volume was 25 uL.")

    def test_fixture_really_reaches_paragraph_expansion(self):
        """前置自检：本夹具必须真的把 AECE 推到 PARAGRAPH 级。

        AECE 若只停在 SENTENCE / ADJACENT_SENTENCES，`context_text` 本来就窄，
        下一条测的就不是本缺陷（实测：带编号标题 `3. Results` 时那个 `3` 会满足
        NUMERIC_VALUE 检查，AECE 停在邻句级，测试静默失去判别力）。
        """
        doc = self.DOC_FAR_VALUE
        cand = {"id": "C-1", "type": CandidateType.TEXT_SENTENCE, "text": type(self)._HIT,
                "offset": doc.find(type(self)._HIT), "section": "Results"}
        ctx = expand_candidate_context(doc, cand, tin=self._tin())
        self.assertEqual(ctx.get("level_reached"), "PARAGRAPH",
                         "夹具不再触发 PARAGRAPH 扩级，本类测试已失去判别力")
        self.assertIn("25 uL", ctx.get("context_text", ""))

    def test_value_far_outside_the_quote_is_not_anchoring(self):
        """引句外的数值不得锚定。

        AECE 扩到 PARAGRAPH 级时 `context_text` 就是**整段（零空行文本下即整篇）**
        （H-35 注释自承：pypdf 文本零空行时实测 80,701 字符）。于是"值锚定在扩展
        上下文"退化为"该数值在论文任何位置出现过"——别的实验、别的句子里的数字都能
        挂到任意字段上，跨实验数值污染（`assay_context_isolation` 与 E4 隔离要防的）
        被机械门禁盖章为 EXPLICIT。现在比较对象是引句及其同句窗口（±200 字符）。
        """
        res = self._run(self.DOC_FAR_VALUE, "25 uL",
                        hit=type(self)._HIT)
        self.assertFalse(res["promoted"], "另一实验里的数值不得锚定到本引句")
        self.assertIsNone(res["evidence_record"])

    def test_anchor_text_is_a_window_not_the_whole_context(self):
        from extraction_pipeline import VALUE_ANCHOR_WINDOW, _value_anchor_text
        doc = ("P" * 500) + "QUOTE" + ("S" * 500)
        anchor = _value_anchor_text({"text": "QUOTE"}, doc)
        self.assertLess(len(anchor), len(doc), "锚定文本不得等于整篇文档")
        self.assertLessEqual(len(anchor), len("QUOTE") + 2 * VALUE_ANCHOR_WINDOW)
        self.assertIn("QUOTE", anchor)


# ---------------------------------------------------------------------------
# H-17 quote_audit 信封侧
# ---------------------------------------------------------------------------

class TestH17EnvelopeGate(unittest.TestCase):

    SCRIPT = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts" / "quote_audit.py"

    def _run_cli(self, payload_text):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ev = td / "ev.json"
            src = td / "src.txt"
            ev.write_text(payload_text, encoding="utf-8")
            src.write_text("The sample volume was 20 uL in all reactions.", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(self.SCRIPT), "-i", str(ev), "-s", str(src)],
                capture_output=True, text=True, encoding="utf-8")
            return proc.returncode, (proc.stderr or "") + (proc.stdout or "")

    def test_wrong_top_level_key_structured_error(self):
        """EXT-A-09 回归：错误顶层 key 曾零核验 rc=0。"""
        rc, out = self._run_cli(json.dumps(
            {"records": [{"verbatim_quote": "sample volume was 20 uL",
                          "extracted_value": "999 uL"}]}))
        self.assertNotEqual(rc, 0)
        self.assertIn("ENVELOPE_INVALID", out)

    def test_empty_envelope_structured_error(self):
        rc, out = self._run_cli(json.dumps({"evidence_records": []}))
        self.assertNotEqual(rc, 0)
        self.assertIn("ENVELOPE_EMPTY", out)

    def test_bare_list_structured_error_no_traceback(self):
        """裸 list 输入 → 结构化报错（不再裸 AttributeError traceback）。"""
        rc, out = self._run_cli(json.dumps([{"verbatim_quote": "x"}]))
        self.assertNotEqual(rc, 0)
        self.assertIn("ENVELOPE_INVALID", out)
        self.assertNotIn("Traceback", out)

    def test_valid_envelope_still_exit_zero(self):
        """配对正例：合法信封 + 忠实记录仍 rc=0。"""
        rc, out = self._run_cli(json.dumps(
            {"evidence_records": [{"verbatim_quote": "The sample volume was 20 uL in all reactions.",
                                   "extracted_value": "20 uL"}]}))
        self.assertEqual(rc, 0, out)


# ---------------------------------------------------------------------------
# 设施-1 summary 计数
# ---------------------------------------------------------------------------

class TestFacility1SummaryCounters(unittest.TestCase):

    def test_quote_audit_summary_has_new_counters(self):
        report = qa.audit_evidence(
            {"evidence_records": [{"verbatim_quote": "The value was 0.3 in the sample.",
                                   "extracted_value": "not significant"}]},
            "The value was 0.3 in the sample.")
        s = report["summary"]
        for key in ("value_not_verifiable", "value_fuzzy_not_anchored",
                    "value_ambiguous_sign", "value_unparsable", "value_checked"):
            self.assertIn(key, s)

    def test_alignment_summary_and_aggregate(self):
        results = [
            _verify("Drug X decreases tumor growth",
                    "Drug X increases tumor growth while the control arm decreases "
                    "survival markers in the same assay window (p<0.01).",
                    predicate="decreases", obj="tumor growth", subject="Drug X"),
            _verify("Drug X increases mortality",
                    "Drug X increased mortality after dosing (P = 0.01).",
                    predicate="increases", obj="mortality", subject="Drug X"),
        ]
        agg = cal.aggregate_alignment_summary(results)
        self.assertEqual(agg["total_results"], 2)
        self.assertEqual(agg["polarity_unresolved"], 1)
        self.assertEqual(agg["confirmed_eligible"], 1)
        self.assertIn("status_counts", agg)
        self.assertIn("audit_verdict_counts", agg)


# ---------------------------------------------------------------------------
# ≥8 条真实论文正例（句子逐字取自 runner texts 的 pypdf 提取文本，含真实伪影）
# ---------------------------------------------------------------------------

ECO3_SRC = """Local biodiversity inside and outside protected areas . Samples
from protected sites (Fig. 1b) contained 10.6% more species
(95% CI: 4.1 to 17.6%; w
2 ¼ 9.99, df ¼ 1, P ¼ 0.002; Fig. 2a)
and 14.5% more individuals (95% CI: 2.0 to 28.7%; w2 ¼ 5.09,
df ¼ 1, P ¼ 0.024; Fig. 2b) than samples from unprotected sites."""

ECO4_SRC = """We show that 83 −85% of the surveys presented losses in forest biomass and tree species
richness, functional traits, and conservation value. On average, forest fragments have 25
−32% less biomass, 23 −31% fewer species, and 33, 36, and 42% fewer individuals of late-
successional, large-seeded, and endemic species, respectively."""

MP4_SRC = """acetylcholinesterase
(AChE) activity in the brain of zebra ﬁsh (PVC-MPs, 3-30 μg/L for
20 days) ( 93). However, in common goby ( P. microps ), MP
exposure (0.184 mg/L for 96 hours) does not affect either predatory
performance or brain acetylcholine levels ( 94) and in zebra ﬁsh
larvae, exposure to PS-MPs (10–100 mg/L from 2 hours to 120 hours
post-fertilization) decreases locomotion but increases neurotrans-
mitter (serotonin, dopamine and acetylcholine) levels and activity"""

MP4_SRC2 = """mg/L for 14 days; MPs 10 mg and 17.5 mg/L for 5 days; 200 μg/L
and 1 mg/L for 30 days; 10,000 PE-MPs/L, for 1, 5, or 10 days) ( 100,
131, 181, 204, 205), discus (PS-NPs 200 μg/L for 96 hours) ( 88),"""


class TestRealPaperPositives(unittest.TestCase):
    """真实论文 EXACT/FUZZY 正例随批落库（≥8 条，含排版伪影）。"""

    def _aligned(self, source, quote, value, expect_match="EXACT"):
        rec = {"field_id": "REAL", "verbatim_quote": quote, "extracted_value": value}
        report = qa.audit_evidence({"evidence_records": [rec]}, source)
        entry = report["entries"][0]
        self.assertEqual(entry["match_type"], expect_match,
                         (quote, entry["match_type"], entry["detail"]))
        self.assertEqual((entry.get("value_alignment") or {}).get("verdict"), "ALIGNED",
                         (value, entry.get("value_alignment")))
        self.assertFalse(qa.gate_failed(report), quote)

    def test_eco3_species_richness_percent(self):
        self._aligned(ECO3_SRC,
                      "from protected sites (Fig. 1b) contained 10.6% more species",
                      "10.6%")                                                  # 1

    def test_eco3_individuals_percent(self):
        self._aligned(ECO3_SRC,
                      "and 14.5% more individuals (95% CI: 2.0 to 28.7%",
                      "14.5%")                                                  # 2

    def test_mp4_fuzzy_dropped_word(self):
        """真实伪影（FUZZY 正例）：pypdf 抽取丢词（mid-span "either" 丢失）→
        EXACT 失配、FUZZY 命中（containment 0.966），抽取值回源文窗口核验通过
        ——FUZZY 引句的值锚定走源文侧，不再拿引句自证。"""
        self._aligned(MP4_SRC,
                      "However, in common goby ( P. microps ), MP exposure "
                      "(0.184 mg/L for 96 hours) does not affect predatory performance "
                      "or brain acetylcholine levels ( 94) and in zebra fish larvae",
                      "0.184 mg/L", expect_match="FUZZY")                       # 3

    def test_eco3_typeset_equals_sign(self):
        """真实伪影：¼ 是排版等号 → 0.002 / 9.99 照常锚定（B10 正向）。"""
        self._aligned(ECO3_SRC,
                      "w 2 ¼ 9.99, df ¼ 1, P ¼ 0.002",
                      "0.002")                                                  # 4

    def test_eco4_range_minus_sign(self):
        self._aligned(ECO4_SRC,
                      "We show that 83 −85% of the surveys presented losses in forest "
                      "biomass and tree species",
                      "83-85%")                                                 # 5

    def test_eco4_two_ranges(self):
        self._aligned(ECO4_SRC,
                      "forest fragments have 25 −32% less biomass, 23 −31% fewer species",
                      "25-32%")                                                 # 6

    def test_eco4_individuals_percent(self):
        self._aligned(ECO4_SRC,
                      "and 33, 36, and 42% fewer individuals",
                      "42%")                                                    # 7

    def test_mp4_mass_per_volume(self):
        self._aligned(MP4_SRC,
                      "exposure (0.184 mg/L for 96 hours) does not affect either predatory",
                      "0.184 mg/L")                                             # 8

    def test_mp4_en_dash_range_concentration(self):
        self._aligned(MP4_SRC,
                      "exposure to PS-MPs (10–100 mg/L from 2 hours to 120 hours",
                      "100 mg/L")                                               # 9

    def test_mp4_ligature_fi(self):
        """真实伪影：ﬁ 连字由 confusable 归一化处理，浓度值 30 μg/L 锚定。"""
        self._aligned(MP4_SRC,
                      "(AChE) activity in the brain of zebra fish (PVC-MPs, 3-30 μg/L for",
                      "30 μg/L")                                                # 10

    def test_mp4_second_concentration(self):
        self._aligned(MP4_SRC2,
                      "MPs 10 mg and 17.5 mg/L for 5 days; 200 μg/L",
                      "17.5 mg/L")                                              # 11

    def test_real_paper_doctored_token_still_blocked(self):
        """真实语料上的同构拒绝：真实长引句篡改 1 个数值 token → 拦截。"""
        quote = ("contained 10.6% more species (95% CI: 4.1 to 17.6%; "
                 "w ¼ 9.99, df ¼ 1, P ¼ 0.02; Fig. 2a)")  # 0.002 → 0.02
        rec = {"field_id": "REAL", "verbatim_quote": quote, "extracted_value": "0.02"}
        report = qa.audit_evidence({"evidence_records": [rec]}, ECO3_SRC)
        entry = report["entries"][0]
        self.assertIn(entry["match_type"], ("FUZZY", "NOT_FOUND"))
        self.assertTrue(qa.gate_failed(report))


if __name__ == "__main__":
    unittest.main()
