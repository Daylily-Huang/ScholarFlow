#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯标准库 PDF 文本回退提取器（pypdf 缺失时的降级路径）。

## 为什么存在这个模块

`pdf_evidence_locator.py` 在 `pypdf` 不可用时，旧回退实现是
「以 latin-1 解码整个 PDF → 正则抓 `stream...endstream` → 过滤可打印 ASCII」。
而现实中绝大多数学术 PDF 的内容流是 `FlateDecode` 压缩的，于是这条回退路径
拿到的是**压缩二进制噪声**，却仍然报出很大的 `total_character_count`，
把「没有提取到文本」伪装成「提取到了文本、只是关键词没命中」。

2026 实测反例（Frontiers 2012 真实 PDF，1,190,305 字节）：

- 旧回退：`total_pages: 1`、`total_character_count: 1173114`、5 个关键词全部 0 命中；
- 本模块：11 页、约 63k 字符、`soil` 200 次、`microbial` 121 次。

因此 0 命中既可能是「文献确实没有该表述」，也可能是「工具根本没提取出文本」。
两者在证据层面完全不同（前者 → 真实证据缺口；后者 → 工具性假阴性），
本模块的作用就是把后者消除掉。

## 能力与边界（必须如实标注）

- 支持：`FlateDecode`/无压缩内容流、交叉引用流（`/ObjStm`）中的页对象、
  `Tj` / `TJ` / `'` / `"` 文本算符、`Td`/`TD`/`T*`/`Tm` 定位、`Tf` 字体切换、
  用 `/Widths` 逐字符宽度还原词间空格与换行。
- 不支持：`ToUnicode` CMap 解码（仅 latin-1 直读，子集字体的私有码位可能失真）、
  CID/Type0 复杂编码、LZW/JPEG2000 等其它滤镜、加密 PDF、竖排/旋转文本重排。
- 因此本模块**只用于定位与搜检**（`degraded: true` 时必须回原文核对原文句），
  不可作为 verbatim quote 的唯一来源。这是 `literature-evidence-extraction`
  技能 Quote → Extract → Verify 铁律的一环。

输出结构：

```json
{"degraded": true, "engine": "pure-python-fallback", "total_pages": 11,
 "pages": [{"page": 1, "text": "..."}], "warnings": ["..."]}
```
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List, Optional, Tuple

ENGINE_NAME = "pure-python-fallback"

# 词间插入空格的水平位移阈值（相对字号）
_SPACE_GAP_RATIO = 0.08
# 判定换行的纵向位移阈值（相对字号）
_LINE_GAP_RATIO = 0.5
# TJ 数组里超过该值（千分之一 em）的字距才视为词间空格，更小的只是 kerning
_WORD_GAP_TJ = 120.0
# 单页文本上限，防止异常 PDF 撑爆内存
_MAX_CHARS_PER_PAGE = 400_000

_PDF_ESCAPES = {
    ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8,
    ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92,
}


# --------------------------------------------------------------------------
# 低层：PDF 语法
# --------------------------------------------------------------------------

def decode_pdf_string(raw: bytes) -> bytes:
    """解码 PDF 字面量字符串的转义序列（内容为 `(...)` 内部字节）。"""
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == 0x5C and i + 1 < n:  # 反斜杠
            nxt = raw[i + 1]
            if nxt in _PDF_ESCAPES:
                out.append(_PDF_ESCAPES[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:  # 八进制，最多三位
                j = i + 1
                digits = b""
                while j < n and len(digits) < 3 and 0x30 <= raw[j] <= 0x37:
                    digits += bytes([raw[j]])
                    j += 1
                out.append(int(digits, 8) & 0xFF)
                i = j
                continue
            if nxt in (10, 13):  # 行继续
                i += 2
                if nxt == 13 and i < n and raw[i] == 10:
                    i += 1
                continue
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def _split_streams(raw: bytes) -> List[bytes]:
    """切出所有原始 stream 数据（按 `stream` / `endstream` 标记）。"""
    out = []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end > 0:
            out.append(raw[start:end])
    return out


def _inflate(data: bytes) -> Optional[bytes]:
    """尽力解压；返回 None 表示可能本身未压缩或解压失败。"""
    for cand in (data, data.rstrip(b"\r\n")):
        try:
            return zlib.decompress(cand)
        except zlib.error:
            continue
        except Exception:
            continue
    return None


def _iter_inflated_objects(raw: bytes) -> List[bytes]:
    """返回所有 stream 的解压结果；无法解压的原样返回（可能是裸内容流）。"""
    out = []
    for s in _split_streams(raw):
        d = _inflate(s)
        out.append(d if d is not None else s)
    return out


def iter_stream_dicts(raw: bytes) -> List[Tuple[bytes, bytes]]:
    """返回 [(紧跟 stream 之前的对象字典字节, 解压后的流内容), ...]。"""
    return [(d, data) for _, d, data in iter_stream_entries(raw)]


def iter_stream_entries(raw: bytes) -> List[Tuple[Optional[int], bytes, bytes]]:
    """返回 [(对象号或 None, 流字典字节, 解压后的流内容), ...]。

    三个坑：
    1. `/ObjStm`、`/Length`、`/Filter` 在**流之外的字典**里，解压后搜不到，
       必须回原始字节取字典；
    2. 页的 `/Contents` 指向的是**内容流对象号**，因此必须记录 `N 0 obj`；
    3. **压缩字节里可能恰好出现 `stream\\r\\n` 字面量**，若全文乱扫会把一个对象
       匹配成两次、并把二进制块当成"内容流"。因此按 `N 0 obj` 顺序定位、
       逐个对象取**紧跟其后的第一个** `stream`，不做全文字面量扫描。
    """
    out: List[Tuple[Optional[int], bytes, bytes]] = []
    starts = [(m.start(), int(m.group(1)))
              for m in re.finditer(rb"(\d+)\s+0\s+obj\b", raw)]
    bounds = {start: (starts[i + 1][0] if i + 1 < len(starts) else len(raw))
              for i, (start, _) in enumerate(starts)}

    for start, num in starts:
        limit = bounds[start]
        m = re.compile(rb"stream\r?\n").search(raw, start, limit)
        if not m:
            continue  # 该对象没有流（如页字典、字体字典）
        open_idx = raw.find(b"<<", start, m.start())
        dict_blob = _match_dict(raw, open_idx) if open_idx >= 0 else None
        body_start = m.end()
        end = raw.find(b"endstream", body_start, limit)
        body = raw[body_start:end if end > 0 else limit]
        inflated = _inflate(body)
        out.append((num, dict_blob or b"", inflated if inflated is not None else body))

    # 无 `N 0 obj` 头部的裸内容流（极少数 PDF）另行兜底
    if not out:
        for m in re.finditer(rb"stream\r?\n", raw):
            body_start = m.end()
            end = raw.find(b"endstream", body_start)
            if end < 0:
                continue
            body = raw[body_start:end]
            inflated = _inflate(body)
            out.append((None, b"", inflated if inflated is not None else body))
    return out


def _match_dict(data: bytes, start: int) -> Optional[bytes]:
    """从 `start` 处的 `<<` 起，按深度匹配出完整字典字节。"""
    if not data.startswith(b"<<", start):
        return None
    depth = 0
    i = start
    n = len(data)
    while i < n - 1:
        two = data[i:i + 2]
        if two == b"<<":
            depth += 1
            i += 2
            continue
        if two == b">>":
            depth -= 1
            i += 2
            if depth == 0:
                return data[start:i]
            continue
        i += 1
    return None


def parse_object_streams(stream_dicts: List[Tuple[bytes, bytes]]) -> Dict[int, bytes]:
    """解析 `/Type /ObjStm` 交叉引用流，返回 {对象号: 对象字节}。

    学术 PDF（PDF 1.5+）普遍把**页对象、资源字典、字体**压进对象流，
    顶层只剩内容流。不解对象流就既找不到页、也拿不到字体宽度表。
    对象流结构：`/N <对象个数> /First <首对象数据偏移>`，
    流头是 N 组 `对象号 相对偏移`，其后为拼接的对象字节。
    """
    index: Dict[int, bytes] = {}
    for dict_blob, data in stream_dicts:
        if b"/ObjStm" not in dict_blob:
            continue
        n_m = re.search(rb"/N\s+(\d+)", dict_blob)
        f_m = re.search(rb"/First\s+(\d+)", dict_blob)
        if not (n_m and f_m):
            continue
        count, first = int(n_m.group(1)), int(f_m.group(1))
        header = data[:first]
        pairs = re.findall(rb"(\d+)\s+(\d+)", header)
        if len(pairs) < count:
            continue
        body = data[first:]
        nums = [int(p[0]) for p in pairs[:count]]
        offs = [int(p[1]) for p in pairs[:count]]
        for i, num in enumerate(nums):
            start = offs[i]
            end = offs[i + 1] if i + 1 < len(offs) and offs[i + 1] > start else len(body)
            index[num] = body[start:end]
    return index


def _find_page_dicts(objects: List[bytes],
                     obj_index: Optional[Dict[int, bytes]] = None) -> List[bytes]:
    """找出页对象字典，按出现顺序返回。

    优先用对象流解析出的对象号顺序（可靠）；找不到时退回全文扫描。
    """
    if obj_index:
        hits = [v for v in obj_index.values()
                if re.search(rb"/Type\s*/Page(?![sA-Za-z])", v)]
        if hits:
            return hits

    # 退路：在已解压对象里扫描；对象流内多对象拼接时无法可靠界定边界，
    # 故只接受能完整匹配出字典的片段，匹配失败即跳过（不猜）。
    dicts = []
    for data in objects:
        for m in re.finditer(rb"/Type\s*/Page(?![sA-Za-z])", data):
            pos = m.start()
            open_idx = -1
            for probe in range(pos, -1, -1):
                if data[probe:probe + 2] == b"<<":
                    open_idx = probe
                    break
                if probe > 0 and data[probe - 1:probe + 1] == b">>":
                    break  # 落到上一个字典之后，放弃
            if open_idx < 0:
                continue
            blob = _match_dict(data, open_idx)
            if blob and re.search(rb"/Type\s*/Page(?![sA-Za-z])", blob):
                dicts.append(blob)
    return dicts


# --------------------------------------------------------------------------
# 低层：字体宽度
# --------------------------------------------------------------------------

def _parse_widths(dict_text: bytes) -> Optional[Dict[int, float]]:
    """从字体字典解析 /FirstChar + /Widths → {char_code: width/1000}。"""
    fc = re.search(rb"/FirstChar\s+(\d+)", dict_text)
    wm = re.search(rb"/Widths\s*\[(.*?)\]", dict_text, re.DOTALL)
    if not fc or not wm:
        return None
    first = int(fc.group(1))
    widths: Dict[int, float] = {}
    idx = 0
    for tok in wm.group(1).split():
        try:
            widths[first + idx] = float(tok)
        except ValueError:
            pass
        idx += 1
    return widths or None


def _parse_font_map(res_dict: bytes,
                    obj_index: Dict[int, bytes]) -> Dict[str, Dict[int, float]]:
    """解析 /Font<< /T1_0 12 0 R ... >> → {资源名: 宽度表}。"""
    font_map: Dict[str, Dict[int, float]] = {}
    fm = re.search(rb"/Font\s*<<(.*?)>>", res_dict, re.DOTALL)
    if not fm:
        return font_map
    for name, num in re.findall(rb"/([A-Za-z0-9_.\-]+)\s+(\d+)\s+0\s+R", fm.group(1)):
        font_obj = obj_index.get(int(num))
        if not font_obj:
            continue
        widths = _parse_widths(font_obj)
        if widths:
            font_map[name.decode("latin-1")] = widths
    return font_map


def _parse_resources(page_dict: bytes, obj_index: Dict[int, bytes]) -> bytes:
    """取页的 /Resources 字典字节；若是间接引用则解引用。"""
    m = re.search(rb"/Resources\s*(\d+)\s+0\s+R", page_dict)
    if m:
        return obj_index.get(int(m.group(1)), b"")
    m = re.search(rb"/Resources\s*", page_dict)
    if not m:
        return b""
    return _match_dict(page_dict, m.end()) or b""


def _parse_contents(page_dict: bytes, obj_index: Dict[int, bytes]) -> List[int]:
    """取页的 /Contents 对象号列表（支持单引用与数组）。"""
    m = re.search(rb"/Contents\s*(\d+)\s+0\s+R", page_dict)
    if m:
        return [int(m.group(1))]
    m = re.search(rb"/Contents\s*\[(.*?)\]", page_dict, re.DOTALL)
    if m:
        return [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", m.group(1))]
    return []


# --------------------------------------------------------------------------
# 中层：内容流排版
# --------------------------------------------------------------------------

def _numbers(tok: bytes) -> List[float]:
    """把算符里的数字 token 转成 float（非数字 token 直接跳过）。"""
    out: List[float] = []
    for t in tok.split():
        try:
            out.append(float(t))
        except ValueError:
            continue
    return out


def _text_ops(content: bytes) -> List[Tuple[str, List[bytes]]]:
    """切出文本相关算符序列，返回 [(op, args), ...]。"""
    ops: List[Tuple[str, List[bytes]]] = []
    # 只保留 BT..ET 区间，避免图形算符干扰
    for bt in re.finditer(rb"BT(.*?)ET", content, re.DOTALL):
        body = bt.group(1)
        for m in re.finditer(
            rb"(\[(?:[^\[\]\\]|\\.)*\]\s*TJ)"
            rb"|(\((?:[^()\\]|\\.)*\)\s*(?:Tj|'|\"))"
            rb"|([-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+Tm)"
            rb"|([-\d.]+\s+[-\d.]+\s+(?:Td|TD))"
            rb"|(T\*)"
            rb"|(/([A-Za-z0-9_.\-]+)\s+[-\d.]+\s+Tf)",
            body, re.DOTALL,
        ):
            tok = m.group(0).strip()
            if tok.endswith(b"TJ"):
                arr = re.match(rb"\[(.*)\]", tok, re.DOTALL)
                items = re.findall(rb"\((?:[^()\\]|\\.)*\)|[-\d.]+", arr.group(1), re.DOTALL) if arr else []
                ops.append(("TJ", items))
            elif tok.endswith(b"Tf"):
                name = re.search(rb"/([A-Za-z0-9_.\-]+)\s+([-\d.]+)\s+Tf", tok)
                if name:
                    ops.append(("Tf", [name.group(1), name.group(2)]))
                else:
                    ops.append(("Tf", [b""]))
            elif tok.endswith(b"Tm"):
                # 不能直接用 tok.split() 前 6 项：PDF 的 Tm 是 `a b c d e f Tm`，
                # 但数字里可能混入无法转 float 的 token；统一用 float 判定并保留 6 位。
                ops.append(("Tm", _numbers(tok)[:6]))
            elif tok.endswith(b"Td") or tok.endswith(b"TD"):
                ops.append((tok[-2:].decode(), _numbers(tok)[:2]))
            elif tok == b"T*":
                ops.append(("T*", []))
            else:
                strm = re.match(rb"\((?:[^()\\]|\\.)*\)", tok, re.DOTALL)
                ops.append(("Tj", [strm.group(0) if strm else b""]))
    return ops


def _layout_page(content: bytes, font_widths: Dict[str, Dict[int, float]]) -> str:
    """按文本算符还原阅读顺序文本，依据位移补空格与换行。

    两处关键判定（都决定「能不能拿去定位原句」）：

    1. 字距：`TJ` 数组里的负数项表示加宽字距。`> _WORD_GAP_TJ`（千分之一 em）
       视为词间空格；更小的只是 kerning，不能当空格，否则 `Micro-bial` 会被切碎。
    2. 位移：`Tm`/`Td`/`T*` 会重置当前文本原点到新位置，若直接拿它和「本段起点」
       比较，差恒为 0，永远补不出空格。必须记住**上一段实际结束位置**
       （`last_end_x`，用 `/Widths` 累计推进量算得）再比较。
    """
    ops = _text_ops(content)
    if not ops:
        return ""

    out: List[str] = []
    font = ""
    size = 10.0
    tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]  # a b c d e f
    tlm = list(tm)
    last_end_x: Optional[float] = None
    last_y: Optional[float] = None
    eol = False  # 已在本行末尾输出过换行

    widths = font_widths.get(font)

    def advance_of(data: bytes) -> float:
        return sum(char_w(b) for b in data)

    def char_w(code: int) -> float:
        w = widths.get(code) if widths else None
        return (w if w is not None else 0.5) * size

    def is_new_line(y: float) -> bool:
        return last_y is not None and abs(y - last_y) > _LINE_GAP_RATIO * size

    def emit_chunk(text: str) -> None:
        nonlocal last_end_x, last_y, eol
        if not text:
            return
        x, y = tm[4], tm[5]
        if out and not eol:
            if is_new_line(y):
                out.append("\n")
                eol = True
            elif last_end_x is not None and (x - last_end_x) > _SPACE_GAP_RATIO * size:
                if not out[-1].endswith((" ", "\n")):
                    out.append(" ")
        out.append(text)
        eol = False
        last_end_x = x + advance_of(text.encode("latin-1", errors="replace"))
        last_y = y

    for op, args in ops:
        if op == "Tf":
            font = (args[0] or b"").decode("latin-1")
            widths = font_widths.get(font)
            if len(args) > 1:
                try:
                    size = float(args[1])
                except (TypeError, ValueError):
                    pass
            continue
        if op == "Tm" and len(args) == 6:
            tm = list(args)
            tlm = list(tm)
            continue
        if op in ("Td", "TD") and len(args) == 2:
            tlm[4] += args[0]
            tlm[5] += args[1]
            tm = list(tlm)
            continue
        if op == "T*":
            tlm[5] -= size * 1.2
            tm = list(tlm)
            continue

        # Tj / TJ：按字符宽度推进并渲染
        if op in ("Tj", "TJ"):
            for item in args:
                if item.startswith(b"("):
                    data = decode_pdf_string(item[1:-1])
                    emit_chunk(data.decode("latin-1"))
                    continue
                try:  # TJ 的数字项：负值表示加宽字距
                    adv = float(item)
                except ValueError:
                    continue
                if -adv > _WORD_GAP_TJ and out and not out[-1].endswith((" ", "\n")):
                    out.append(" ")
                    last_end_x = (last_end_x or tm[4]) - adv / 1000.0 * size
                elif last_end_x is not None:
                    last_end_x += -adv / 1000.0 * size
            continue

    text = "".join(out)
    # 归并空白：行内多空格压缩，行尾去空格，最多保留单换行
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()[:_MAX_CHARS_PER_PAGE]


# --------------------------------------------------------------------------
# 顶层入口
# --------------------------------------------------------------------------

def extract_pdf_pages(pdf_path: str) -> Dict[str, Any]:
    """提取 PDF 每页文本。返回 dict（见模块 docstring）。"""
    with open(pdf_path, "rb") as f:
        raw = f.read()

    warnings: List[str] = []
    entries = iter_stream_entries(raw)
    stream_dicts = [d for _, d, _ in entries]
    objects = [data for _, _, data in entries]
    # 内容流对象号 → 解压后的内容
    stream_by_num: Dict[int, bytes] = {
        num: data for num, _, data in entries if num is not None
    }
    if not any(b"/Type" in o for o in objects):
        warnings.append("NO_DECOMPRESSABLE_OBJECTS：未解出任何 PDF 对象，可能为加密或非 FlateDecode PDF")

    # 建立 对象号 → 对象字节 索引：先顶层 `N 0 obj`，再对象流内部对象
    obj_index: Dict[int, bytes] = {}
    stream_objs = parse_object_streams([(d, data) for _, d, data in entries])
    for m in re.finditer(rb"(\d+)\s+0\s+obj", raw):
        head = raw.find(b"<<", m.end())
        if head < 0 or head - m.end() > 32:
            continue  # 不是本对象的字典（或为数组等其它类型）
        blob = _match_dict(raw, head)
        if blob:
            obj_index[int(m.group(1))] = blob
    # 对象流内的对象优先（它们才是页、资源、字体的真实归属）
    obj_index.update(stream_objs)
    if not stream_objs:
        warnings.append("NO_OBJECT_STREAMS：未解析到交叉引用流，页/字体可能缺失")

    page_dicts = _find_page_dicts(objects, obj_index)
    if not page_dicts:
        warnings.append("NO_PAGE_OBJECTS：未识别到页对象，回退为整篇单页")

    pages: List[Dict[str, Any]] = []
    if not page_dicts:
        joined = "\n".join(_layout_page(o, {}) for o in objects if b"BT" in o)
        pages.append({"page": 1, "text": joined})
        return {
            "degraded": True, "engine": ENGINE_NAME, "total_pages": 1,
            "pages": pages, "warnings": warnings,
        }

    unresolved = 0
    for idx, pd in enumerate(page_dicts, start=1):
        res = _parse_resources(pd, obj_index)
        font_widths = _parse_font_map(res, obj_index)
        contents = _parse_contents(pd, obj_index)
        chunks = []
        for num in contents:
            blob = stream_by_num.get(num)
            if blob is None:
                unresolved += 1
                continue
            chunks.append(blob)
        content = b"\n".join(chunks)
        pages.append({"page": idx, "text": _layout_page(content, font_widths)})

    if unresolved:
        warnings.append(f"UNRESOLVED_CONTENT_OBJECTS：{unresolved} 个内容流对象未解出，相关页文本不完整")
    if not any(p["text"] for p in pages):
        warnings.append("EMPTY_TEXT：所有页均为空文本，疑似扫描版或 CID 编码，需 OCR 或 pypdf/pdfminer")

    return {
        "degraded": True,
        "engine": ENGINE_NAME,
        "total_pages": len(pages),
        "pages": pages,
        "warnings": warnings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="纯标准库 PDF 文本提取（pypdf 缺失时的降级路径）")
    ap.add_argument("-i", "--input", required=True, help="PDF 路径")
    ap.add_argument("--page", type=int, default=0, help="只输出某一页（1 起）")
    ap.add_argument("--raw", action="store_true", help="输出纯文本而非 JSON")
    args = ap.parse_args(argv)

    result = extract_pdf_pages(args.input)
    if args.page:
        sel = [p for p in result["pages"] if p["page"] == args.page]
        result = dict(result, pages=sel, total_pages=len(sel))
    if args.raw:
        print("\n".join(p["text"] for p in result["pages"]))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
