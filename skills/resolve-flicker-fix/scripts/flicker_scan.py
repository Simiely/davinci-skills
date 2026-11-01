#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flicker_scan.py —— 闪烁诊断：单文件扫描（定位/分型）或两版对比（判定降噪是否生效）。

单文件扫描:
    py -3.12 flicker_scan.py --media "E:\\src\\clip.mp4" --range 600,810
两版对比（改前 vs 改后，同一帧段）:
    py -3.12 flicker_scan.py --compare before.mp4 after.mp4 --range 600,810

依赖: ffmpeg（PATH 里）。纯标准库，无需 Pillow。
"""
import argparse
import subprocess
import sys

W, H, B = 480, 270, 16      # 块分析分辨率与块大小
NW, NH = 96, 54             # 亮度曲线分辨率


def read_gray(path, w, h):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-an",
           "-vf", "scale=%d:%d,format=gray" % (w, h),
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 读取失败: %s\n%s" % (path, p.stderr.decode("utf-8", "ignore")[:400]))
    n = w * h
    buf = p.stdout
    return [memoryview(buf)[i * n:(i + 1) * n] for i in range(len(buf) // n)]


def luma_curve(frames):
    n = NW * NH
    return [sum(f) / n for f in frames]


def hp_std(v, k=5):
    res = []
    for i in range(len(v)):
        a, b = max(0, i - k), min(len(v), i + k + 1)
        res.append(v[i] - sum(v[a:b]) / (b - a))
    m = sum(res) / len(res)
    return (sum((x - m) ** 2 for x in res) / len(res)) ** 0.5


def block_activity(frames, f0, f1):
    """每块逐像素帧间变化均值"""
    acc, cnt = {}, 0
    for i in range(max(1, f0), min(f1, len(frames))):
        cur, prev = frames[i], frames[i - 1]
        for by in range(H // B):
            for bx in range(W // B):
                s = 0
                for y in range(by * B, (by + 1) * B):
                    o = y * W + bx * B
                    s += sum(abs(cur[o + k] - prev[o + k]) for k in range(B))
                acc[(bx, by)] = acc.get((bx, by), 0) + s / (B * B)
        cnt += 1
    return {k: v / max(cnt, 1) for k, v in acc.items()}


def scan_single(path, f0, f1):
    frames = read_gray(path, W, H)
    print("[info] %s  共 %d 帧，分析区间 %d~%d" % (path, len(frames), f0, min(f1, len(frames) - 1)))

    small = read_gray(path, NW, NH)
    lum = luma_curve(small)[f0:min(f1 + 1, len(small))]
    black = [(f0 + i, round(v, 1)) for i, v in enumerate(lum) if v < 6]
    print("\n== 全帧亮度（段内）==")
    print("   min %.1f  max %.1f  mean %.1f" % (min(lum), max(lum), sum(lum) / len(lum)))
    print("   黑帧(<6): %s" % (black if black else "无"))
    d = [abs(lum[i + 1] - lum[i]) for i in range(len(lum) - 1)]
    big = [(f0 + 1 + i, round(lum[i + 1] - lum[i], 1)) for i in range(len(d)) if d[i] > 2]
    print("   帧间跳变>2 级: %s" % (big[:10] if big else "无"))

    act = block_activity(frames, f0, f1)
    rank = sorted(act.items(), key=lambda kv: -kv[1])
    print("\n== 局部热点（16x16 块，逐像素帧间变化）==")
    for (bx, by), v in rank[:6]:
        pos = ("上" if by < (H // B) / 3 else ("中" if by < (H // B) * 2 / 3 else "下")) + \
              ("左" if bx < (W // B) / 3 else ("中" if bx < (W // B) * 2 / 3 else "右"))
        print("   块(%2d,%2d) %-3s  activity %.2f   ≈ 全画面(像素 %d,%d)" % (
            bx, by, pos, v, bx * B * 4, by * B * 4))
    vals = sorted(act.values())
    print("   全画面: 中位 %.2f  P90 %.2f  最大 %.2f" % (
        vals[len(vals) // 2], vals[int(len(vals) * 0.9)], vals[-1]))
    print("\n[提示] 块值大 ≠ 噪点：连续 ±15 以上的差分多半是运动。")
    print("       要进一步确认，用 --compare 改前/改后两版同一帧段对比。")


def scan_compare(a, b, f0, f1):
    fa, fb = read_gray(a, W, H), read_gray(b, W, H)
    if len(fa) != len(fb):
        print("[warn] 两版帧数不同（%d vs %d），按较短的对齐" % (len(fa), len(fb)))
    end = min(f1, len(fa), len(fb))
    aa = block_activity(fa, f0, end)
    ab = block_activity(fb, f0, end)
    ta, tb = sum(aa.values()), sum(ab.values())
    print("[compare] %s  →  %s" % (a, b))
    print("  全画面活动量 %.1f → %.1f (%.1f%%)" % (ta, tb, (tb - ta) / max(ta, 1e-6) * 100))
    rows = sorted(((k, aa[k], ab[k]) for k in aa),
                  key=lambda r: (r[2] - r[1]) / max(r[1], 1e-6))
    print("\n  变化最大的 8 块（负=变安静）:")
    for (bx, by), x, y in rows[:8]:
        print("    块(%2d,%2d)  %.2f → %.2f  %+6.1f%%" % (bx, by, x, y, (y - x) / max(x, 1e-6) * 100))
    quiet = [r for r in rows if (r[2] - r[1]) / max(r[1], 1e-6) < -0.10]
    print("\n[判定] 降噪命中 %d 块（<-10%%）；全画面 %.1f%% %s" % (
        len(quiet), (tb - ta) / max(ta, 1e-6) * 100,
        "→ 生效" if quiet else "→ 基本无效（没打开/参数太弱/问题不是噪点）"))


def main():
    ap = argparse.ArgumentParser(description="闪烁诊断（定位 / 对比）")
    ap.add_argument("--media", help="单文件扫描")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="两版对比")
    ap.add_argument("--range", default="0,0", help="帧区间 start,end（end=0 表示到结尾）")
    args = ap.parse_args()

    f0, f1 = [int(x) for x in args.range.split(",")]
    try:
        if args.compare:
            if f1 == 0:
                f1 = 10 ** 9
            scan_compare(args.compare[0], args.compare[1], f0, f1)
        elif args.media:
            frames_probe = read_gray(args.media, NW, NH)
            if f1 == 0:
                f1 = len(frames_probe) - 1
            scan_single(args.media, f0, f1)
        else:
            print("[fail] 需要 --media 或 --compare")
            return 1
    except RuntimeError as e:
        print("[fail] %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
