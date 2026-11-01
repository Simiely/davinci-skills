#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_deliver.py —— 成片交付校验：规格 / 时长 / 黑帧 / 音频峰值。

用法:
    py -3.12 verify_deliver.py --file "E:\\out\\final.mp4" --expect-frames 1200 --expect-fps 30

依赖: ffprobe + ffmpeg（PATH 里）。纯标准库。
退出码: 0 全绿 / 1 有硬问题（黑帧/帧数不符/无音轨）/ 2 文件或工具缺失
"""
import argparse
import json
import os
import re
import subprocess
import sys

BW, BH = 96, 54
BLACK_THRESHOLD = 6.0


def probe(path):
    cmd = ["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:400])
    return json.loads(p.stdout)


def gray_frames(path):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-an",
           "-vf", "scale=%d:%d,format=gray" % (BW, BH),
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("解码失败: %s" % p.stderr.decode("utf-8", "ignore")[:400])
    n = BW * BH
    return [sum(p.stdout[i * n:(i + 1) * n]) / n for i in range(len(p.stdout) // n)]


def audio_levels(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = p.stderr
    mean_m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", txt)
    max_m = re.search(r"max_volume:\s*(-?[\d.]+) dB", txt)
    return (float(mean_m.group(1)) if mean_m else None,
            float(max_m.group(1)) if max_m else None)


def ranges(idx):
    """把离散帧号压成区间描述，便于读。"""
    if not idx:
        return "无"
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i == prev + 1:
            prev = i
            continue
        out.append((start, prev))
        start = prev = i
    out.append((start, prev))
    return ", ".join("%d" % a if a == b else "%d-%d" % (a, b) for a, b in out)


def main():
    ap = argparse.ArgumentParser(description="成片交付校验")
    ap.add_argument("--file", required=True)
    ap.add_argument("--expect-frames", type=int, default=0, help="与时间线帧数一致的期望值")
    ap.add_argument("--expect-fps", type=float, default=0.0)
    ap.add_argument("--black-threshold", type=float, default=BLACK_THRESHOLD)
    ap.add_argument("--audio-headroom", type=float, default=-0.5,
                    help="max_volume 上限（dB），超过即告警，默认 -0.5")
    ap.add_argument("--skip-audio", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print("[fail] 文件不存在: %s" % args.file)
        return 2

    info = probe(args.file)
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        print("[fail] 没有视频流")
        return 1

    fps = 0.0
    if v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        num, den = v["r_frame_rate"].split("/")
        fps = float(num) / float(den or 1)
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    size = int(fmt.get("size") or os.path.getsize(args.file))
    bitrate = int(fmt.get("bit_rate") or 0)

    print("== 规格 ==")
    print("  文件      : %s" % args.file)
    print("  分辨率    : %sx%s   %s   %.3f fps   %s" % (
        v.get("width"), v.get("height"), v.get("codec_name"), fps, v.get("pix_fmt")))
    print("  时长/体积 : %.2f 秒   %.1f MB   %.1f Mbps" % (duration, size / 1048576, bitrate / 1e6))
    print("  音轨      : %s" % ("%s %s Hz %s ch" % (
        a.get("codec_name"), a.get("sample_rate"), a.get("channels")) if a else "**缺失**"))

    problems = []

    frames = gray_frames(args.file)
    print("\n== 帧数与黑帧 ==")
    print("  实测帧数  : %d" % len(frames))
    if args.expect_frames:
        diff = len(frames) - args.expect_frames
        print("  期望帧数  : %d   %s" % (args.expect_frames, "OK" if diff == 0 else "差 %+d 帧 <== " % diff))
        if diff:
            problems.append("帧数与时间线不符（%+d）" % diff)
    if fps and duration:
        expect_dur = len(frames) / fps
        print("  时长校验  : 帧数/fps = %.2fs，容器写 %.2fs，差 %.2fs" % (expect_dur, duration, abs(expect_dur - duration)))
    black = [i for i, lum in enumerate(frames) if lum < args.black_threshold]
    print("  黑帧(亮度<%g): %d 个   %s" % (args.black_threshold, len(black), ranges(black)))
    if black:
        problems.append("存在 %d 个黑帧" % len(black))
    print("  亮度范围  : min %.1f / max %.1f / mean %.1f" % (
        min(frames), max(frames), sum(frames) / len(frames)))

    if not args.skip_audio:
        print("\n== 音频 ==")
        if not a:
            problems.append("没有音轨")
        else:
            mean_v, max_v = audio_levels(args.file)
            print("  平均电平  : %s dB" % mean_v)
            print("  峰值      : %s dB   (上限 %s dB)" % (max_v, args.audio_headroom))
            if max_v is not None and max_v > args.audio_headroom:
                problems.append("音频峰值 %s dB 顶到满刻度，建议降 2~3 dB" % max_v)

    print("\n== 结论 ==")
    if problems:
        for p_ in problems:
            print("  ✗ %s" % p_)
        return 1
    print("  ✓ 全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print("[fail] %s" % e)
        sys.exit(2)
