#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_luts.py —— 按 shots.json 的统计生成每镜头 33³ cube，并拷进 Resolve 的 LUT 目录。

核心是「黑白位锚定法」：p5→24 / p95→206（施加 blend），三通道同一 a/b 保色相，
再按 --wb-pull 轻度收拢色温（以 0.5 为轴缩放，不动黑位）。

用法:
    py -3.12 gen_luts.py --shots shots.json --lut-subdir myproject
    py -3.12 gen_luts.py --shots shots.json --lut-subdir myproject --blend 0.7 --wh-anchor 200
"""
import argparse
import json
import os
import shutil
import sys

LUT_ROOT = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT"


def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def plan_shot(st, bl_anchor, wh_anchor, blend, wb_pull, wb_target):
    p5, p95 = st["p5"], st["p95"]
    t5 = p5 + blend * (bl_anchor - p5)
    t95 = p95 + blend * (wh_anchor - p95)
    a = (t95 - t5) / max(p95 - p5, 1e-6)
    b = (t5 - a * p5) / 255.0

    # 色温：算完 a/b 后 R/B 会漂移，解析求出需要的通道增益
    R = a * st["R"] / 255.0 + b
    B = a * st["B"] / 255.0 + b
    rb_after = R / max(B, 1e-6)
    rb_want = st["RB"] + wb_pull * (wb_target - st["RB"])
    k = rb_want / max(rb_after, 1e-6)
    kr, kb = k ** 0.5, k ** -0.5
    return a, b, kr, kb, t5, t95


def write_cube(path, a, b, ks, size):
    lines = ['TITLE "%s"' % os.path.splitext(os.path.basename(path))[0],
             "LUT_3D_SIZE %d" % size,
             "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    n = size - 1
    for bi in range(size):
        ob = clamp01(0.5 + ((a * (bi / n) + b) - 0.5) * ks[2])
        for gi in range(size):
            og = clamp01(0.5 + ((a * (gi / n) + b) - 0.5) * ks[1])
            for ri in range(size):
                orr = clamp01(0.5 + ((a * (ri / n) + b) - 0.5) * ks[0])
                lines.append("%.6f %.6f %.6f" % (orr, og, ob))
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="生成每镜头 LUT（黑白位锚定）")
    ap.add_argument("--shots", required=True)
    ap.add_argument("--lut-subdir", required=True, help="LUT 目录下的子目录名，如 myproject")
    ap.add_argument("--prefix", default=None, help="cube 文件名前缀，默认用子目录名")
    ap.add_argument("--bl-anchor", type=int, default=24)
    ap.add_argument("--wh-anchor", type=int, default=206)
    ap.add_argument("--blend", type=float, default=0.85)
    ap.add_argument("--wb-pull", type=float, default=0.22)
    ap.add_argument("--wb-target", type=float, default=1.16, help="色温收拢的目标 R/B")
    ap.add_argument("--size", type=int, default=33)
    ap.add_argument("--out-dir", default=None, help="cube 本地目录（默认 ./luts）")
    args = ap.parse_args()

    with open(args.shots, encoding="utf-8") as f:
        data = json.load(f)
    shots = data["shots"]
    prefix = args.prefix or args.lut_subdir
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.shots)), "luts")
    os.makedirs(out_dir, exist_ok=True)
    lut_dir = os.path.join(LUT_ROOT, args.lut_subdir)

    print(" 镜头  原p5/p95 → 目标t5/t95   slope a    offset b    通道增益 kr/kb   白点")
    results = []
    for st in shots:
        a, b, kr, kb, t5, t95 = plan_shot(st, args.bl_anchor, args.wh_anchor,
                                          args.blend, args.wb_pull, args.wb_target)
        name = "%s_shot%02d.cube" % (prefix, st["index"])
        local = os.path.join(out_dir, name)
        write_cube(local, a, b, (kr, 1.0, kb), args.size)
        results.append({"index": st["index"], "file": name, "a": round(a, 4), "b": round(b, 5),
                        "kr": round(kr, 4), "kb": round(kb, 4), "t5": round(t5, 1), "t95": round(t95, 1)})
        white = max(int(round(clamp01(0.5 + (clamp01(a * 1.0 + b) - 0.5) * k) * 255))
                    for k in (kr, 1.0, kb))
        print("  S%-3d  %3d/%3d → %3.0f/%3.0f    %.3f    %+.5f    %.3f/%.3f      %d" % (
            st["index"], st["p5"], st["p95"], t5, t95, a, b, kr, kb, white))

    os.makedirs(lut_dir, exist_ok=True)
    for r in results:
        shutil.copy2(os.path.join(out_dir, r["file"]), os.path.join(lut_dir, r["file"]))
    plan_path = os.path.join(out_dir, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"lut_subdir": args.lut_subdir, "prefix": prefix,
                   "bl_anchor": args.bl_anchor, "wh_anchor": args.wh_anchor,
                   "blend": args.blend, "shots": results}, f, ensure_ascii=False, indent=1)
    print("\n[ok] cube 已写入本地 %s（%d 个）" % (out_dir, len(results)))
    print("[ok] 已拷入 Resolve LUT 目录 %s" % lut_dir)
    print("[ok] 目标值写入 %s" % plan_path)
    print("     下一步: apply_luts.py --timeline <名字> --lut-subdir %s --plan %s" % (
        args.lut_subdir, plan_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
