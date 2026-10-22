# -*- coding: utf-8 -*-
"""
GIF -> WebP 帧序列，供网页手动播放。

用法：
    python split_frames.py <gif目录> <输出目录>

为什么不用 GIF：浏览器对 GIF 的播放由内嵌时钟驱动，CSS 管不到，
也无法"暂停在当前帧"。要手动控制必须拆帧。

输出：<输出目录>/<name>/f000.webp… + meta.json（含每帧 duration，供页面注入 data-dur）
"""

import io
import json
import os
import sys
import glob
from PIL import Image

OUT = None


def split_one(gif_path, quality=84):
    name = os.path.splitext(os.path.basename(gif_path))[0]
    dst = os.path.join(OUT, name)
    os.makedirs(dst, exist_ok=True)

    im = Image.open(gif_path)
    n = getattr(im, "n_frames", 1)
    durations = []
    for i in range(n):
        im.seek(i)
        durations.append(im.info.get("duration", 80))
        frame = im.convert("RGB")
        # 统一尺寸（GIF 帧可能是局部尺寸）
        if frame.size != im.size:
            canvas = Image.new("RGB", im.size, "white")
            canvas.paste(frame, (0, 0))
            frame = canvas
        frame.save(os.path.join(dst, "f%03d.webp" % i), "WEBP",
                   quality=quality, method=6)

    meta = {"w": im.size[0], "h": im.size[1], "n": n, "durations": durations}
    with io.open(os.path.join(dst, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    total = sum(os.path.getsize(os.path.join(dst, "f%03d.webp" % i)) for i in range(n))
    print("  %-24s %2d 帧  %5.0f KB  %dx%d"
          % (name, n, total / 1024.0, im.size[0], im.size[1]))
    return meta


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    SRC, OUT = args.source, args.output
    os.makedirs(OUT, exist_ok=True)
    gifs = sorted(glob.glob(os.path.join(SRC, "*.gif")))
    print("拆帧：%d 个 GIF  ->  %s" % (len(gifs), OUT))
    grand = 0
    for g in gifs:
        split_one(g)
        name = os.path.splitext(os.path.basename(g))[0]
        d = os.path.join(OUT, name)
        n = len([x for x in os.listdir(d) if x.endswith(".webp")])
        grand += sum(os.path.getsize(os.path.join(d, x)) for x in os.listdir(d))
    print("合计 %.1f MB" % (grand / 1024.0 / 1024.0))
