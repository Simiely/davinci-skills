---
name: resolve-timeline-build
description: 按帧边界把一段素材精确切分并落到 Resolve 时间线——AppendToTimeline 的 endFrame 是排他的，按"含尾帧"传值会让每段少 1 帧、每个切点留下 1 帧纯黑（成片闪黑）；本技能给出正确边界数组写法 + 段长/总长自检。当用户说"按镜头切开/分镜/建时间线/切点有黑帧/切完总长不对"时使用。附零依赖 build_timeline.py。
agent_created: true
---

# resolve-timeline-build —— 按帧精确建线（零黑帧）

职责单一：把**一条（或几条）素材**按给定帧边界切成若干段，落到一条新时间线的 V1/A1 上，并做几何自检。不负责调色、转场、渲染。

## 什么时候用

- 用户要"按镜头切开""分成 N 段""建一条干净的剪辑线"。
- 成片在**每个剪辑点闪一下黑**，或切完总长比源少几帧。
- 需要把同一素材的不同区间按顺序拼成一条线（B-roll 串片、分镜重排）。

## 反模式（务必避免）

1. **`endFrame` 当含尾帧用** —— 这是本技能存在的唯一原因。`endFrame` 是**排他的**（`GetDuration = end − start` 同一套语义）。按"含尾帧"传 `(0, 89)` 实际只收 89 帧。
2. **加了 `recordFrame` 却没改排他端** —— 两件事叠加最致命：每段少 1 帧 + 段位置按理论值摆 → 段与段之间**空出 1 帧**，渲染出来就是纯黑闪帧。实测 8 段 → 7 个黑帧。
3. **不传 `recordFrame` 靠自动排列** —— 落位由前一段的"排他端"决定，段长一旦算错就整体错位；显式给 `recordFrame` 才能保证与源帧严格对齐。
4. **同名时间线直接再建** —— 会得到 `xxx (2)` 堆一串。先 `DeleteTimelines` 同名旧线，或换名。
5. **只信 API 返回的列表长度** —— `AppendToTimeline` 返回 8 个 item 不代表时长对。必须逐段核对 `GetDuration()` 与期望值。
6. **切点落在运动中间** —— 硬切要选在镜头自然转换处（换机位/换主体）。本技能只管几何，切点选择见 `resolve-flicker-fix` 的场景检测部分。

## A 主线（必做）

1. **定边界数组**（排他端，最后一个是总帧数）：
   ```
   8 段 30fps：BOUNDS = [0, 90, 180, 330, 510, 600, 690, 810, 1110]
   含义：段 i 收源帧 [BOUNDS[i], BOUNDS[i+1])，共 len(BOUNDS)-1 段
   ```
2. **建线**：
   ```powershell
   py -3.12 skills\resolve-timeline-build\build_timeline.py ^
       --media "E:\path\clip.mp4" --bounds 0,90,180,330,510,600,690,810,1110 --timeline "cut_v1"
   ```
3. **读自检表**：每段 `实测 duration` 必须等于 `期望`，总帧数必须等于 `BOUNDS[-1]`。
4. **渲染前抽查切点**：导出切点前后各 1 帧，确认没有纯黑（见 C 组）。

## B 工具库（按需查）

### B1 关键写法

```python
infos = [{
    "mediaPoolItem": clip,
    "startFrame": BOUNDS[i],          # 本段首帧（含）
    "endFrame":   BOUNDS[i + 1],      # 下一段首帧（排他！）
    "recordFrame": TL_START + BOUNDS[i],
    "trackIndex": 1,
} for i in range(len(BOUNDS) - 1)]

items = mp.AppendToTimeline(infos)    # 视频+音频一起进来
```

### B2 几何自检的判据

| 检查项 | 期望 | 不符时的含义 |
|---|---|---|
| 每段 `GetDuration()` | `BOUNDS[i+1] - BOUNDS[i]` | 排他端写错 / 源不够长 |
| `tl.GetEndFrame() - tl.GetStartFrame()` | `BOUNDS[-1]` | 有段被截断 |
| 段首尾相接 | `前段 GetEnd() == 后段 GetStart()` | 有空隙 → 黑帧 |
| A1 片段数 | 与 V1 相同 | 音频没跟进来（必要时 `mediaType` 分开插） |

### B3 时间线起点

默认 `01:00:00:00` = **108000 帧 @30fps**。`recordFrame` 要用绝对帧号，所以 `TL_START + offset`。

## C 检查与沉淀

- **必做验收**：建完线立刻导出切点前后各 1 帧，`mean` 小于 6 判为黑帧：
  ```python
  proj.ExportCurrentFrameAsStill(path)   # 偶发返回 False，重试一次
  ```
- 渲染成片后再做一次全片黑帧扫描（`resolve-deliver-check`），阈值 `亮度 < 6` 的帧数必须为 **0**。
- 本项目实测：边界 `[0,90,180,330,510,600,690,810,1110]` → 8 段 `90/90/150/180/90/90/120/300` 合计 1110，黑帧 **7 → 0**。
