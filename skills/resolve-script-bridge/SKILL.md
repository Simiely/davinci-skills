---
name: resolve-script-bridge
description: 用 Python 连上正在运行的 DaVinci Resolve——自设 RESOLVE_SCRIPT_API/RESOLVE_SCRIPT_LIB + sys.path 再 import，避开"环境变量本来就没设"的坑；一次打印版本/项目/时间线/媒体池做前置自检。当用户说"用脚本控制达芬奇/连接 Resolve/写 Resolve 脚本/自动化剪片"时使用。附零依赖 resolve_connect.py。
agent_created: true
---

# resolve-script-bridge —— 连上 Resolve（自动化一切的前置）

职责单一：把 Python 进程和**正在运行的** Resolve 连起来，并输出一份环境自检报告。不负责建线、调色、渲染。

## 什么时候用

- 用户说"用我的达芬奇剪/调色/导出""帮我写个 Resolve 脚本""能不能自动化剪辑"。
- 任何要在 Resolve 里执行脚本操作之前——**先跑本技能自检**，连不上就别往下做。
- 脚本报 `No module named DaVinciResolveScript` 或 `scriptapp` 返回 `None` 时，用它定位。

## 反模式（务必避免）

1. **不要假设环境变量已设**。本机实测 `RESOLVE_SCRIPT_API` 与 `RESOLVE_SCRIPT_LIB` **都是空的**——必须脚本自己设，否则 `import DaVinciResolveScript` 直接失败（模块不在 sys.path 里）。
2. **不要把路径写死成别人的机器**。默认值给 Windows 标准安装路径，但必须允许 `--api` / `--lib` 覆盖。
3. **不要用 `ProjectManager.SetCurrentTimeline`**。`pm` 上根本没有这个方法，会抛 `'NoneType' object is not callable`；正确是 `Project.SetCurrentTimeline(timeline)`。
4. **不要自己给时间码加 1 小时**。时间线默认起点就是 `01:00:00:00`（30fps = 108000 帧），`frame // 30` 直接换算即可。
5. **不要在 Resolve 没启动时反复重试**。`scriptapp` 返回 `None` 只有两种原因：没运行，或没允许外部脚本（偏好设置 → 系统 → 常规 → External scripting using 设为 Local）。让用户处理，别循环重试。
6. **不要输出 token / 路径里的用户名**到日志里（本仓库是公开仓库）。

## A 主线（必做）

1. **确认 Resolve 在跑**：任务管理器能看到 `Resolve.exe`。没跑就先让用户打开（本技能不负责启动它）。
2. **跑自检**：
   ```powershell
   py -3.12 skills\resolve-script-bridge\resolve_connect.py
   ```
3. **读输出三行关键信息**：`product/version`（确认是 Studio 而非免费版）、`project`（确认在正确的项目里）、`timeline` + `page`（确认当前上下文）。
4. **接入自己的脚本**：直接 `from resolve_connect import connect`，复用同一套环境设置，不要重写。

## B 工具库（按需查）

### B1 最小可用连接代码

```python
import os, sys

API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
os.environ["RESOLVE_SCRIPT_API"] = API
os.environ["RESOLVE_SCRIPT_LIB"] = LIB
sys.path.append(os.path.join(API, "Modules"))

import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
if not resolve:
    raise SystemExit("Resolve 未运行，或未允许外部脚本")
```

### B2 常用对象链

| 想要 | 拿法 |
|---|---|
| 项目管理 | `resolve.GetProjectManager()` |
| 当前项目 | `pm.GetCurrentProject()` |
| 媒体池 | `proj.GetMediaPool()` → `GetRootFolder()` |
| 某个时间线 | `proj.GetTimelineByIndex(i)`（i 从 **1** 开始） |
| 切到某条时间线 | `proj.SetCurrentTimeline(tl)` ← 注意不是 pm |
| 当前页 | `resolve.GetCurrentPage()`（`cut` / `edit` / `color` / `fusion` / `fairlight` / `deliver`） |
| 打开某页 | `proj.OpenPage("color")` |
| 视频轨片段 | `tl.GetItemListInTrack("video", 1)` |
| 播放头定位 | `tl.SetCurrentTimecode("01:00:12:00")` |

### B3 环境自检该看什么

| 字段 | 期望 | 异常含义 |
|---|---|---|
| `GetProductName()` | `DaVinci Resolve Studio` | 免费版 → 部分脚本能力受限 |
| `GetVersionString()` | 如 `21.1.0.17` | 记录版本，行为差异按版本记 |
| `GetCurrentProject()` | 非 None | 为 None → 有 Resolve 但没开项目 |
| `tl.GetSetting("timelineFrameRate")` | 如 `30.0` | 换算帧/秒全靠它 |

## C 检查与沉淀

- 自检脚本输出里必须包含：产品名、版本、项目名、时间线名与帧数、当前页。
- 如果 `scriptapp` 返回 `None`，先问用户两件事：Resolve 开着吗？外部脚本允许了吗？
- 新发现的版本差异（某方法在某版本不可用）→ 记到 `AGENTS.md` 的「关键坑」，不要只写在对话里。
