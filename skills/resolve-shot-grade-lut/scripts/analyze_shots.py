#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_shots.py —— 按镜头边界抽样中间帧，统计 p5 / p95 / mean / R-B，供 gen_luts.py 用。

用法:
    py -3.12 analyze_shots.py --media "E:\\path\\clip.mp4" \
        --bounds 0,90,180,330 --out shots.json

依赖: ffmpeg（PATH 里）+ Pillow（py -3.12 -m pip install pillow）
"""
import argparse
import json
import os
import subprocess
import sys

try:
    from PIL import Image
except ImportError:
    print("[fail] 需要 Pillow: py -3.12 -m pip install pillow")
    sys.exit(1)


def grab_frame(media, frame, fps, out_path):
    """抽指定帧（-ss 用秒，精度足够；要严格对齐可用 select=eq(n,frame)）。"""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", "%.4f" % (frame / fps), "-i", media, "-frames:v", "1",
           "-q:v", "1", out_path]
    subprocess.run(cmd, check=True)


def pct(hist, total, q):
    acc = 0
    for v, c in enumerate(hist):
        acc += c
        if acc >= total * q:
            return v
    return 255


def stats(path):
    im = Image.open(path).convert("RGB")
    r, g, b = im.split()
    hist = im.convert("L").histogram()
    total = sum(hist)
    mr = sum(v * c for v, c in enumerate(r.histogram())) / total
    mg = sum(v * c for v, c in enumerate(g.histogram())) / total
    mb = sum(v * c for v, c in enumerate(b.histogram())) / total
    return {
        "p5": pct(hist, total, 0.05),
        "p50": pct(hist, total, 0.50),
        "p95": pct(hist, total, 0.95),
        "mean": round(0.2126 * mr + 0.7152 * mg + 0.0722 * mb, 2),
        "R": round(mr, 2), "G": round(mg, 2), "B": round(mb, 2),
        "RB": round(mr / max(mb, 1e-6), 3),
    }


def main():
    ap = argparse.ArgumentParser(description="按镜头抽帧统计（调色基线）")
    ap.add_argument("--media", required=True)
    ap.add_argument("--bounds", required=True, help="排他端边界，如 0,90,180,330")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--out", default="shots.json")
    ap.add_argument("--stills", default="stills", help="参考帧输出目录")
    args = ap.parse_args()

    bounds = [int(x) for x in args.bounds.replace(" ", "").split(",") if x]
    if len(bounds) < 2:
        print("[fail] --bounds 至少 2 个值")
        return 1
    os.makedirs(args.stills, exist_ok=True)

    shots = []
    print(" 镜头   范围(帧)      采样帧   p5  p95  mean   R/B    参考帧")
    for i in range(len(bounds) - 1):
        mid = (bounds[i] + bounds[i + 1]) // 2
        path = os.path.join(args.stills, "s%02d.png" % (i + 1))
        grab_frame(args.media, mid, args.fps, path)
        st = stats(path)
        st.update({"index": i + 1, "start": bounds[i], "end": bounds[i + 1],
                   "mid": mid, "still": os.path.abspath(path)})
        shots.append(st)
        print("  S%-3d  %5d-%-6d %5d   %3d  %3d  %5.1f  %.3f   %s" % (
            i + 1, bounds[i], bounds[i + 1], mid, st["p5"], st["p95"], st["mean"], st["RB"], path))

    drift = max(s["p95"] - s["p5"] for s in shots) - min(s["p95"] - s["p5"] for s in shots)
    means = [s["mean"] for s in shots]
    print("\n  动态范围(p95-p5) 极差 %.0f  |  mean %.1f ~ %.1f  |  R/B %.3f ~ %.3f" % (
        drift, min(means), max(means), min(s["RB"] for s in shots), max(s["RB"] for s in shots)))
    print("  提示: 动态范围极差 > 20 说明镜头间对比度明显不一致；mean 差是内容差异，不必强行拉平")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"media": os.path.abspath(args.media), "fps": args.fps,
                   "bounds": bounds, "shots": shots}, f, ensure_ascii=False, indent=1)
    print("\n[ok] 写出 %s" % os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
