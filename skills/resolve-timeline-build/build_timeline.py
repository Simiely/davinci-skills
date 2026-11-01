#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_timeline.py —— 按帧边界把素材切成段，落到一条新时间线，并做几何自检。

用法:
    py -3.12 build_timeline.py --media "E:\\path\\clip.mp4" \
        --bounds 0,90,180,330,510,600,690,810,1110 --timeline "cut_v1"

    # 只检查不建线
    py -3.12 build_timeline.py --media ... --bounds 0,90,180 --timeline t --dry-run

约定: --bounds 是**排他端**数组，段 i = 源帧 [bounds[i], bounds[i+1])。
      最后一项 = 素材总帧数。
退出码: 0 成功 / 1 参数或几何错误 / 2 连不上 Resolve
"""
import argparse
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


def find_clip(folder, filename):
    """在媒体池里递归找素材（按文件名匹配，忽略大小写）。"""
    for c in folder.GetClipList() or []:
        if (c.GetClipProperty("File Path") or "").lower().endswith(filename.lower()):
            return c
    for sf in folder.GetSubFolderList() or []:
        hit = find_clip(sf, filename)
        if hit:
            return hit
    return None


def main():
    ap = argparse.ArgumentParser(description="按帧边界建 Resolve 时间线（零黑帧）")
    ap.add_argument("--media", required=True, help="素材绝对路径")
    ap.add_argument("--bounds", required=True, help="排他端帧边界，逗号分隔，如 0,90,180,330")
    ap.add_argument("--timeline", required=True, help="新时间线名称")
    ap.add_argument("--track", type=int, default=1, help="落到第几条视频轨（默认 1）")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--lib", default=DEFAULT_LIB)
    ap.add_argument("--dry-run", action="store_true", help="只校验边界，不动 Resolve")
    args = ap.parse_args()

    try:
        bounds = [int(x) for x in args.bounds.replace(" ", "").split(",") if x != ""]
    except ValueError:
        print("[fail] --bounds 解析失败")
        return 1
    if len(bounds) < 2:
        print("[fail] --bounds 至少要 2 个值")
        return 1
    if any(bounds[i] >= bounds[i + 1] for i in range(len(bounds) - 1)):
        print("[fail] --bounds 必须严格递增")
        return 1
    segs = len(bounds) - 1
    print("[plan] %d 段, 总 %d 帧: %s" % (segs, bounds[-1], " / ".join(
        str(bounds[i + 1] - bounds[i]) for i in range(segs))))
    if args.dry_run:
        print("[dry-run] 不执行")
        return 0

    resolve = connect(args.api, args.lib)
    if not resolve:
        print("[fail] 连不上 Resolve（没运行 / 未允许外部脚本）")
        return 2

    proj = resolve.GetProjectManager().GetCurrentProject()
    if not proj:
        print("[fail] 没有打开的项目")
        return 2
    mp = proj.GetMediaPool()

    clip = find_clip(mp.GetRootFolder(), os.path.basename(args.media))
    if not clip:
        print("[info] 媒体池里没有，尝试导入: %s" % args.media)
        got = mp.ImportMedia([{"FilePath": args.media}])
        clip = got[0] if got else None
        if not clip:
            print("[fail] 导入失败（路径对吗？素材是否被 Resolve 支持？）")
            return 1
    total = int(clip.GetClipProperty("Frames") or 0)
    print("[clip] %s  %d 帧" % (clip.GetName(), total))
    if total and bounds[-1] > total:
        print("[fail] 边界末端 %d 超过素材总帧数 %d" % (bounds[-1], total))
        return 1

    # 同名时间线先删，避免 "xxx (2)"
    for i in range(proj.GetTimelineCount(), 0, -1):
        tl = proj.GetTimelineByIndex(i)
        if tl and tl.GetName() == args.timeline:
            mp.DeleteTimelines([tl])
            print("[info] 删除同名旧时间线: %s" % args.timeline)

    tl = mp.CreateEmptyTimeline(args.timeline)
    if not tl:
        print("[fail] CreateEmptyTimeline 失败")
        return 1
    proj.SetCurrentTimeline(tl)          # 注意: 是 Project 上的方法，不是 ProjectManager
    tl_start = tl.GetStartFrame()
    print("[info] 新时间线 %s  起点帧 %d (时间码见 resolve-script-bridge)" % (tl.GetName(), tl_start))

    infos = [{
        "mediaPoolItem": clip,
        "startFrame": bounds[i],
        "endFrame": bounds[i + 1],        # 排他！
        "recordFrame": tl_start + bounds[i],
        "trackIndex": args.track,
    } for i in range(segs)]

    got = mp.AppendToTimeline(infos)
    print("[append] 返回 %s 个 item" % (len(got) if got else "0"))

    items = tl.GetItemListInTrack("video", args.track) or []
    ok = True
    print("\n 段  时间线范围            实测/期望 时长   源范围")
    for i, it in enumerate(items, 1):
        want = bounds[i] - bounds[i - 1]
        dur = it.GetDuration()
        flag = "" if dur == want else "  <== 不符"
        if dur != want:
            ok = False
        print("  %2d  %d..%-8d %4d / %-4d      %d..%d%s" % (
            i, it.GetStart(), it.GetEnd(), dur, want,
            it.GetSourceStartFrame(), it.GetSourceEndFrame(), flag))

    want_total = bounds[-1]
    got_total = tl.GetEndFrame() - tl_start
    print("\n[check] 总帧 %d / 期望 %d %s" % (got_total, want_total, "OK" if got_total == want_total else "不符"))

    # 段首尾相接检查
    gaps = [(items[i].GetStart(), items[i - 1].GetEnd()) for i in range(1, len(items))
            if items[i].GetStart() != items[i - 1].GetEnd()]
    if gaps:
        ok = False
        print("[check] 发现 %d 处空隙（会渲染成黑帧）: %s" % (len(gaps), gaps[:5]))
    else:
        print("[check] 段与段严丝合缝，无空隙")

    a_items = tl.GetItemListInTrack("audio", 1) or []
    print("[check] A1 片段数 %d（V1 为 %d）" % (len(a_items), len(items)))
    return 0 if (ok and got_total == want_total) else 1


if __name__ == "__main__":
    sys.exit(main())
