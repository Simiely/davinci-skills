#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_connect.py —— 连接正在运行的 DaVinci Resolve 并做环境自检。

用法:
    py -3.12 resolve_connect.py                 # 默认 Windows 安装路径
    py -3.12 resolve_connect.py --api <dir> --lib <fusionscript.dll>

退出码: 0 成功 / 2 连不上 / 1 环境错误
"""
import argparse
import os
import sys

DEFAULT_API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
DEFAULT_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"


def connect(api_dir: str = DEFAULT_API, lib_path: str = DEFAULT_LIB):
    """设置环境变量并返回 resolve 对象；连不上返回 None。"""
    if not os.path.isdir(api_dir):
        raise FileNotFoundError("脚本目录不存在: %s" % api_dir)
    if not os.path.isfile(lib_path):
        raise FileNotFoundError("fusionscript.dll 不存在: %s" % lib_path)

    os.environ["RESOLVE_SCRIPT_API"] = api_dir
    os.environ["RESOLVE_SCRIPT_LIB"] = lib_path
    modules = os.path.join(api_dir, "Modules")
    if modules not in sys.path:
        sys.path.append(modules)

    import DaVinciResolveScript as dvr  # noqa: E402  (必须先设环境变量再 import)
    return dvr.scriptapp("Resolve")


def tc(frame: int, fps: float = 30.0) -> str:
    """时间线绝对帧号 -> 时间码（默认起点 01:00:00:00）。"""
    fps = int(round(fps))
    f = frame % fps
    total = frame // fps
    return "%02d:%02d:%02d:%02d" % (total // 3600, (total // 60) % 60, total % 60, f)


def main() -> int:
    ap = argparse.ArgumentParser(description="连接 DaVinci Resolve 并自检")
    ap.add_argument("--api", default=DEFAULT_API, help="Scripting 目录")
    ap.add_argument("--lib", default=DEFAULT_LIB, help="fusionscript.dll 路径")
    args = ap.parse_args()

    try:
        resolve = connect(args.api, args.lib)
    except FileNotFoundError as e:
        print("[fail] %s" % e)
        return 1

    if not resolve:
        print("[fail] scriptapp 返回 None —— 两种可能：")
        print("       1) Resolve 没在运行")
        print("       2) 偏好设置 → 系统 → 常规 → External scripting using 不是 Local")
        return 2

    print("[ok] product : %s" % resolve.GetProductName())
    print("[ok] version : %s" % resolve.GetVersionString())

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    if not proj:
        print("[warn] 有 Resolve 但没打开项目")
        return 0

    print("[ok] project : %s" % proj.GetName())
    print("[ok] page    : %s" % resolve.GetCurrentPage())

    n = proj.GetTimelineCount()
    print("[ok] timelines: %d" % n)
    cur = proj.GetCurrentTimeline()
    for i in range(1, n + 1):
        tl = proj.GetTimelineByIndex(i)
        if not tl:
            continue
        fps = float(tl.GetSetting("timelineFrameRate") or 30.0)
        frames = tl.GetEndFrame() - tl.GetStartFrame()
        mark = "  <== 当前" if cur and tl.GetName() == cur.GetName() else ""
        print("   - %-28s %5d 帧 (%.2f 秒)  %s x %s%s" % (
            tl.GetName(), frames, frames / fps,
            tl.GetSetting("timelineResolutionWidth"), tl.GetSetting("timelineResolutionHeight"), mark))

    if cur:
        print("[ok] current : %s  起点 %s" % (cur.GetName(), tc(cur.GetStartFrame())))

    root = proj.GetMediaPool().GetRootFolder()
    clips = root.GetClipList() or []
    print("[ok] media   : %d 个素材, %d 个子文件夹" % (len(clips), len(root.GetSubFolderList() or [])))
    for c in clips[:10]:
        print("   - %-40s %s" % (c.GetName(), c.GetClipProperty("File Path") or ""))
    if len(clips) > 10:
        print("   ... 其余 %d 个省略" % (len(clips) - 10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
