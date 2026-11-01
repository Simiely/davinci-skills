#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_luts.py —— 把每镜头的 LUT 挂到时间线上（幂等），并导出验证帧做实测比对。

用法:
    py -3.12 apply_luts.py --timeline cut_v1 --lut-subdir myproject --plan luts\\plan.json
    py -3.12 apply_luts.py --timeline cut_v1 --lut-subdir myproject --no-export

幂等性: 每个镜头先 ResetAllGrades() 再 SetLUT，重复跑不会叠两层。
依赖: Pillow（仅 --export 时用于实测比对）
"""
import argparse
import json
import os
import sys

DEFAULT_API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
DEFAULT_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"


def connect(api_dir, lib_path):
    os.environ["RESOLVE_SCRIPT_API"] = api_dir
    os.environ["RESOLVE_SCRIPT_LIB"] = lib_path
    modules = os.path.join(api_dir, "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


def tc_of(frame, fps):
    fps = int(round(fps))
    f = frame % fps
    total = frame // fps
    return "%02d:%02d:%02d:%02d" % (total // 3600, (total // 60) % 60, total % 60, f)


def measure(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    hist = im.convert("L").histogram()
    total = sum(hist)

    def pct(q):
        acc = 0
        for v, c in enumerate(hist):
            acc += c
            if acc >= total * q:
                return v
        return 255

    r, g, b = im.split()
    mr = sum(v * c for v, c in enumerate(r.histogram())) / total
    mb = sum(v * c for v, c in enumerate(b.histogram())) / total
    return pct(0.05), pct(0.95), mr / max(mb, 1e-6)


def main():
    ap = argparse.ArgumentParser(description="给时间线每镜头挂 LUT 并验证")
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--lut-subdir", required=True)
    ap.add_argument("--prefix", default=None, help="默认同 --lut-subdir")
    ap.add_argument("--plan", default=None, help="gen_luts.py 写的 plan.json（用于比对目标）")
    ap.add_argument("--export-dir", default="verify")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--lib", default=DEFAULT_LIB)
    args = ap.parse_args()

    resolve = connect(args.api, args.lib)
    if not resolve:
        print("[fail] 连不上 Resolve")
        return 2
    proj = resolve.GetProjectManager().GetCurrentProject()
    tl = None
    for i in range(1, proj.GetTimelineCount() + 1):
        t = proj.GetTimelineByIndex(i)
        if t and t.GetName() == args.timeline:
            tl = t
    if not tl:
        print("[fail] 找不到时间线 %s" % args.timeline)
        return 1
    proj.SetCurrentTimeline(tl)
    print("[ok] 时间线 %s  (%d 帧)" % (tl.GetName(), tl.GetEndFrame() - tl.GetStartFrame()))

    print("[ok] RefreshLUTList ->", proj.RefreshLUTList())
    prefix = args.prefix or args.lut_subdir
    items = tl.GetItemListInTrack("video", 1) or []
    if not items:
        print("[fail] V1 上没有片段")
        return 1

    ok_count = 0
    for i, it in enumerate(items, 1):
        g = it.GetNodeGraph()
        g.ResetAllGrades()                                   # 幂等：先清再挂
        rel = "%s/%s_shot%02d.cube" % (args.lut_subdir, prefix, i)
        ok = g.SetLUT(1, rel)
        ok_count += 1 if ok else 0
        print("  S%-2d  %-42s -> %-5s  读回 %r" % (i, rel, ok, g.GetLUT(1)))
    print("[summary] 成功 %d / %d" % (ok_count, len(items)))
    if ok_count != len(items):
        print("          失败多半是: LUT 没放进 LUT 目录 / 没 RefreshLUTList / 文件名不对")

    if args.no_export:
        return 0 if ok_count == len(items) else 1

    os.makedirs(args.export_dir, exist_ok=True)
    plan = {}
    if args.plan and os.path.exists(args.plan):
        with open(args.plan, encoding="utf-8") as f:
            plan = {s["index"]: s for s in json.load(f)["shots"]}

    fps = float(tl.GetSetting("timelineFrameRate") or 30.0)
    print("\n 镜头  实测 p5/p95   目标 t5/t95   偏差      R/B")
    worst = 0
    for i, it in enumerate(items, 1):
        mid = (it.GetStart() + it.GetEnd()) // 2
        tl.SetCurrentTimecode(tc_of(mid, fps))
        path = os.path.abspath(os.path.join(args.export_dir, "shot%02d.png" % i))
        if not proj.ExportCurrentFrameAsStill(path):          # 偶发 False，重试一次
            proj.ExportCurrentFrameAsStill(path)
        if not os.path.exists(path):
            print("  S%-2d  导出失败（跳过比对）" % i)
            continue
        p5, p95, rb = measure(path)
        exp = plan.get(i)
        if exp:
            d5, d95 = p5 - exp["t5"], p95 - exp["t95"]
            worst = max(worst, abs(d5), abs(d95))
            print("  S%-2d  %3d/%3d       %3.0f/%3.0f      %+3.0f/+%-3.0f   %.3f" % (
                i, p5, p95, exp["t5"], exp["t95"], d5, d95, rb))
        else:
            print("  S%-2d  %3d/%3d       (无 plan)              %.3f" % (i, p5, p95, rb))
    if plan:
        print("\n[check] 最大偏差 %.0f（≤3 合格；偏差大说明 LUT 未生效）" % worst)
    return 0 if ok_count == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
