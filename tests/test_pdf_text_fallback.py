# -*- coding: utf-8 -*-
"""证据技能 PDF 回退文本提取的行为测试。

为什么需要这个测试文件
----------------------
2026 真实闭环暴露：`pdf_evidence_locator.py` 在 `pypdf` 缺失时，旧回退把整个 PDF
以 latin-1 解码后过滤可打印字符，遇到 FlateDecode 压缩的内容流只会得到二进制噪声，
却报出 `total_character_count: 1173114`、5 个关键词全部 0 命中。
使用者会把「工具没提取出文本」误读成「文献里没有这句话」——两者证据含义完全不同。

因此本文件锁定以下行为：

1. 能解压 FlateDecode 内容流并解析 `/ObjStm` 交叉引用流（页/字体都在里面）；
2. 词间空格靠 `/Widths` 累计推进量 + `TJ` 字距还原（`Micro bial` 这类断词不得被切碎）；
3. 拿不到文本时**显式标注** `TEXT_UNAVAILABLE`，不得返回二进制噪声冒充正文；
4. 真实学术 PDF（若在仓库内）能提取到实际内容——用真样本而非仅合成样本。

合成 PDF 由本文件现场拼装，不引入二进制 fixture；真实 PDF 缺失时相关用例跳过。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zlib

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT
SCRIPTS = os.path.join(REPO_ROOT, "skills", "literature-evidence-extraction", "scripts")
sys.path.insert(0, SCRIPTS)

import extract_pdf_text as E  # noqa: E402  (path inserted above)
import pdf_evidence_locator as L  # noqa: E402

REAL_PDF = os.path.join(
    REPO_ROOT, ".planning", "research-idea-debate", "live-run-3", "handoff", "papers",
    "2012_Joshua_Microbial_control_over_carbon_cycling_in.pdf",
)


def _obj(num, body):
    return b"%d 0 obj\n%s\nendobj\n" % (num, body)


def _stream(num, dict_body, payload, compress=True):
    data = zlib.compress(payload) if compress else payload
    filt = b"/Filter/FlateDecode" if compress else b""
    return (b"%d 0 obj\n<<%s/Length %d>>\nstream\r\n" % (num, filt, len(data))
            + data + b"\r\nendstream\nendobj\n")


def build_synthetic_pdf(compress=True):
    """拼一个结构完整的 PDF：内容流为顶层对象，页/字体在对象流内。

    文本：`Hello world`（两个词之间用 -600 的 TJ 字距分开），
    再加一段 `Micro bial` 式连写（TJ 字距仅 -20，属 kerning，不得当空格）。
    """
    content = (b"BT /T1_0 1 Tf 10 0 0 10 50 700 Tm "
               b"[(Hello)-600(world)]TJ "
               b"[(Micro)-20(bial)]TJ ET")
    widths = b"[" + b" ".join(b"500" for _ in range(95)) + b"]"  # FirstChar=32
    font_dict = (b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica"
                 b"/FirstChar 32/Widths" + widths + b">>")
    page_dict = (b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
                 b"/Resources<</Font<</T1_0 20 0 R>>>>"
                 b"/Contents 10 0 R>>")

    # 对象流：把字体（20）与页（21）按 /N /First 头部拼进去
    objects = [(20, font_dict), (21, page_dict)]
    header = b""
    body = b""
    for num, blob in objects:
        header += b"%d %d " % (num, len(body))
        body += blob + b"\n"
    objstm_payload = header + body
    first = len(header)
    objstm = _stream(30, b"/Type/ObjStm/N %d/First %d" % (len(objects), first),
                     objstm_payload, compress)

    parts = [
        b"%PDF-1.6\r%\xe2\xe3\xcf\xd3\r\n",
        _obj(10, b"<<%s/Length %d>>" % (b"/Filter/FlateDecode" if compress else b"",
                                        len(zlib.compress(content) if compress else content))),
        b"%d 0 obj\n<<%s/Length %d>>\nstream\r\n" % (
            10, b"/Filter/FlateDecode" if compress else b"",
            len(zlib.compress(content) if compress else content)),
        (zlib.compress(content) if compress else content) + b"\r\nendstream\nendobj\n",
        objstm,
        b"trailer\n<</Root 2 0 R>>\n%%EOF\n",
    ]
    return b"".join(parts)


class SyntheticPdfTest(unittest.TestCase):
    """合成 PDF：锁定提取链路的机械行为。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf-pdf-")

    def _write(self, blob, name="s.pdf"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(blob)
        return path

    def test_01_compressed_content_stream_is_decompressed(self):
        path = self._write(build_synthetic_pdf(compress=True))
        res = E.extract_pdf_pages(path)
        text = " ".join(p["text"] for p in res["pages"])
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertTrue(res["degraded"])
        self.assertEqual(res["engine"], "pure-python-fallback")

    def test_02_uncompressed_content_stream_also_works(self):
        path = self._write(build_synthetic_pdf(compress=False))
        res = E.extract_pdf_pages(path)
        text = " ".join(p["text"] for p in res["pages"])
        self.assertIn("Hello", text)

    def test_03_object_stream_yields_a_real_page(self):
        """页对象在 /ObjStm 内：必须靠 /N /First 头部解析出来，而不是全文乱猜。"""
        path = self._write(build_synthetic_pdf())
        res = E.extract_pdf_pages(path)
        self.assertEqual(res["total_pages"], 1)
        self.assertNotIn("NO_PAGE_OBJECTS", res["warnings"])
        self.assertNotIn("NO_OBJECT_STREAMS", res["warnings"])

    def test_04_word_gap_becomes_space_and_kerning_does_not(self):
        """TJ -600 → 词间空格；TJ -20 → kerning，`Microbial` 必须连写。"""
        path = self._write(build_synthetic_pdf())
        text = " ".join(p["text"] for p in E.extract_pdf_pages(path)["pages"])
        self.assertIn("Hello world", text)
        self.assertIn("Microbial", text)
        self.assertNotIn("Micro bial", text)

    def test_05_no_binary_noise_as_text(self):
        """旧回退会把压缩字节当正文；新实现不得出现高比例不可读字符。"""
        path = self._write(build_synthetic_pdf())
        text = " ".join(p["text"] for p in E.extract_pdf_pages(path)["pages"])
        printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\t")
        self.assertGreater(printable / max(len(text), 1), 0.95)


class RealPdfTest(unittest.TestCase):
    """真实样本：证明该回退在真学术 PDF 上可用，而不只是在合成样本上可用。"""

    @unittest.skipUnless(os.path.isfile(REAL_PDF), "真实样本 PDF 不在仓库内，跳过")
    def test_10_real_pdf_yields_multipage_text(self):
        res = E.extract_pdf_pages(REAL_PDF)
        self.assertGreaterEqual(res["total_pages"], 10)
        self.assertNotIn("EMPTY_TEXT", res["warnings"])
        text = " ".join(p["text"] for p in res["pages"])
        self.assertGreater(len(text), 50000)
        for kw in ("microbial", "soil", "carbon"):
            self.assertGreater(text.lower().count(kw), 5, kw)

    @unittest.skipUnless(os.path.isfile(REAL_PDF), "真实样本 PDF 不在仓库内，跳过")
    def test_11_real_pdf_locator_reports_real_matches(self):
        """回归护栏：该 PDF 曾因回退失效而报 5 个关键词全部 0 命中。"""
        pages = L.extract_pages_from_pdf(REAL_PDF)
        self.assertGreaterEqual(len(pages), 10)
        self.assertNotIn("TEXT_UNAVAILABLE", pages[0].get("warnings", []))
        joined = " ".join(p["text"] for p in pages).lower()
        self.assertGreater(joined.count("community composition"), 5)
        self.assertIn("microbial", joined)

    @unittest.skipUnless(os.path.isfile(REAL_PDF), "真实样本 PDF 不在仓库内，跳过")
    def test_12_verbatim_quote_locatable_after_hyphen_repair(self):
        """定位原句必须先接回连字符断行，否则跨行引句永远匹配不上。"""
        from shared.execution.debate_handoff import join_hyphen_breaks
        res = E.extract_pdf_pages(REAL_PDF)
        flat = re.sub(r"\s+", " ", " ".join(join_hyphen_breaks(p["text"])
                                            for p in res["pages"]))
        self.assertIn("there is less conclusive evidence that microbial community", flat)
        self.assertIn("likely not important in the mineral soil", flat)


class LocatorWiringTest(unittest.TestCase):
    """接线：拿不到文本时必须显式标注，不得静默返回噪声。"""

    def test_20_missing_text_is_explicitly_flagged(self):
        """非 PDF 输入 → 回退失败 → 必须给出 TEXT_UNAVAILABLE 而不是一段噪声。"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "broken.pdf")
            with open(path, "wb") as f:
                f.write(b"%PDF-1.6\nnot really a pdf at all\n")
            pages = L.extract_pages_from_pdf(path)
        self.assertTrue(pages)
        self.assertEqual(pages[0]["text"], "")
        self.assertIn("TEXT_UNAVAILABLE", pages[0]["warnings"])

    def test_21_pages_carry_engine_and_degraded_flags(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.pdf")
            with open(path, "wb") as f:
                f.write(build_synthetic_pdf())
            pages = L.extract_pages_from_pdf(path)
        self.assertEqual(pages[0]["extraction_engine"], "pure-python-fallback")
        self.assertTrue(pages[0]["degraded"])
        self.assertIn("Hello", pages[0]["text"])

    def test_22_cli_runs_and_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "s.pdf")
            out = os.path.join(d, "o.json")
            with open(pdf, "wb") as f:
                f.write(build_synthetic_pdf())
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "pdf_evidence_locator.py"),
                 "-i", pdf, "-q", "Hello,world", "-o", out],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
        self.assertGreaterEqual(data["total_pages"], 1)
        self.assertGreater(data["total_character_count"], 0)
        hits = {q["keyword"]: q["match_count"] for q in data["queries"]}
        self.assertGreaterEqual(hits["Hello"], 1)
        self.assertGreaterEqual(hits["world"], 1)


if __name__ == "__main__":
    unittest.main()
