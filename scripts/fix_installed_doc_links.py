#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把安装树里技能文档指向仓库根同级目录的相对链接改写为正确深度（P2-06）。

**问题**：技能文档按仓库布局写死了上溯级数——

    仓库：  <repo>/skills/<skill>/SKILL.md        -> ../../schemas/   = <repo>/schemas/
    安装：  <dest>/<skill>/SKILL.md               -> ../../schemas/   = <dest> 的上一级

安装器把技能平铺到 `<dest>/<skill>/`（宿主 Agent 约定如此），比仓库布局少一层
`skills/`，于是所有指向 `schemas/` 的相对链接在安装后**全部断链**（同为 `references/`
下的文档级数又不同）。链接级数是布局的算术结果，静态文本无法同时满足两种布局，
因此由安装器在复制后按实际深度改写。

用法：``python scripts/fix_installed_doc_links.py <dest>``
（`<dest>` 下应有 `<skill>/` 目录与 `<dest>/schemas/`。）

纯标准库。
"""

from __future__ import annotations

import io
import os
import re
import sys

#: 仓库根下被技能文档引用的同级目录。安装树把它们平铺在 `<dest>/` 下，
#: 因此链接级数比仓库布局少一级，需要按实际深度改写。
ROOT_DIRS = ("schemas", "shared", "docs")

#: `](<任意级 ../><根目录>/<路径>)`
_ROOT_LINK_RE = re.compile(
    r"\]\(((?:\.\./)+)(%s)/([^)\s]+)\)" % "|".join(ROOT_DIRS))


def _rewrite_text(src: str, depth: int, dest: str):
    """把链接前缀统一改成从该文件到 `<dest>/<根目录>` 的正确级数。

    返回 (新文本, 改写的链接数)。目标文件不存在时**保持原样**，避免把指向别处的
    链接误改（例如装后仍未随附的文件）。
    """
    prefix = "../" * depth
    changed = [0]

    def _sub(match):
        root, name = match.group(2), match.group(3)
        if not os.path.exists(os.path.join(dest, root, name)):
            return match.group(0)
        replacement = "](%s%s/%s)" % (prefix, root, name)
        if replacement != match.group(0):
            changed[0] += 1
        return replacement

    return _ROOT_LINK_RE.sub(_sub, src), changed[0]


def fix_tree(dest: str) -> dict:
    """改写 `<dest>` 下所有技能文档；返回统计。"""
    dest = os.path.abspath(dest)
    stats = {"files_scanned": 0, "files_rewritten": 0, "links_rewritten": 0,
             "schemas_present": os.path.isdir(os.path.join(dest, "schemas"))}
    if not stats["schemas_present"]:
        return stats

    for skill in sorted(os.listdir(dest)):
        skill_dir = os.path.join(dest, skill)
        if not os.path.isdir(skill_dir) or skill == "schemas" or skill == "shared":
            continue
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            # 该目录到 <dest> 需要上溯几级：
            #   <dest>/<skill>/            -> relpath 1 段 -> "../"
            #   <dest>/<skill>/references/ -> relpath 2 段 -> "../../"
            depth = len(os.path.relpath(root, dest).split(os.sep))
            for name in files:
                if not name.endswith(".md"):
                    continue
                stats["files_scanned"] += 1
                path = os.path.join(root, name)
                src = io.open(path, encoding="utf-8").read()
                fixed, n = _rewrite_text(src, depth, dest)
                if n and fixed != src:
                    io.open(path, "w", encoding="utf-8", newline="\n").write(fixed)
                    stats["files_rewritten"] += 1
                    stats["links_rewritten"] += n
    return stats


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        sys.stderr.write("用法: python scripts/fix_installed_doc_links.py <dest>\n")
        return 2
    stats = fix_tree(argv[0])
    if not stats["schemas_present"]:
        sys.stderr.write("[WARNING] %s 下没有 schemas/，链接未改写\n" % argv[0])
        return 0
    print("  [doc-links] 扫描 %d 个 .md，改写 %d 个文件 / %d 条根目录相对链接"
          % (stats["files_scanned"], stats["files_rewritten"], stats["links_rewritten"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
