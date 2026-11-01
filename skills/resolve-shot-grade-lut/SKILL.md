---
name: resolve-shot-grade-lut
description: 按镜头逐个调色且不抹平昼夜层次——不要对齐平均亮度，对齐黑位 p5→24 / 白位 p95→206（施加 85%），让动态范围收敛；SetCDL 在本版本有 bug（中性参数也偏红）改用 Graph.SetLUT + 自建 33³ cube，且必须用 LUT 目录内的相对路径。当用户说"每个镜头单独调色/统一色调/切点亮度跳/画面发灰/对比度不一致"时使用。附 3 个脚本（抽帧统计 / 生成 cube / 上色验证）。
agent_created: true
---

# resolve-shot-grade-lut —— 分镜统一调色（黑白位锚定法）

职责单一：给一条已切好的时间线**逐镜头套一层可回退的颜色变换**（LUT），让镜头之间的曝光与对比度对齐。不负责降噪、不做风格化创作、不动剪辑结构。

## 什么时候用

- 用户说"每个镜头简单调一下色""切点处画面一跳""有的镜头发灰/有的太暗"。
- 素材是多镜头拼接、且**昼夜或曝光本来就不一致**（这类最容易被"统一亮度"毁掉）。
- 需要在 Resolve 里留下**可手动微调**的调色（LUT 挂在节点上，调色页能看见、能改）。

## 反模式（务必避免）

1. **不要用 `TimelineItem.SetCDL` 做调色**。本版本（21.1.0.17）实测：连身份 CDL（`slope=1 / offset=0 / power=1 / sat=1`）都会把画面压成红洗——R/G/B 从 `148/144/148` 变 `225/56/56`。`ResetAllGrades()` 能恢复，但只要调过就偏。改用 `Graph.SetLUT`。
2. **不要对齐 mean（平均亮度）**。mean 同时被曝光和**画面内容**污染（暗背景镜头天然低）。把 8 个镜头的 mean 拉进同一区间 = 拿内容差异当曝光差异修，还会把"白天→黑夜"的层次抹平。要对齐 **p5 / p95**。
3. **不要用 `slope < 1` 去压亮度**。线性缩小 slope 会**同时降低对比度**——画面更灰，正是用户抱怨的"不稳"。要压亮度就用"黑位/白位重映射"。
4. **`SetLUT` 不要传绝对路径**。实测直接返回 `False`。必须放进 Resolve 的 LUT 目录下、用相对路径。
5. **拷完 LUT 不调 `RefreshLUTList()`** → 找不到文件，`SetLUT` 返回 `False`。
6. **不要做 65³ 的 cube**。33³ 已 1MB/个；65³ 是 8MB/个，肉眼无差、加载变慢。
7. **不要在没做 A/B 的情况下一次性套 8 段**。先出 4 帧对比图让人看过再全量。

## A 主线（必做）

三步，每步都有可核对的数字：

```powershell
# 1) 抽每镜中间帧，统计 p5 / p95 / mean / R-B
py -3.12 skills\resolve-shot-grade-lut\scripts\analyze_shots.py ^
    --media "E:\path\clip.mp4" --bounds 0,90,180,330,510,600,690,810,1110 --out shots.json

# 2) 按统计生成 cube（默认 p5→24 / p95→206，85% 施加，色温收 22%）
py -3.12 skills\resolve-shot-grade-lut\scripts\gen_luts.py ^
    --shots shots.json --lut-subdir myproject

# 3) 挂到时间线每个镜头 + 导出验证帧比对
py -3.12 skills\resolve-shot-grade-lut\scripts\apply_luts.py ^
    --timeline cut_v1 --lut-subdir myproject --shots shots.json
```

1. **看第 2 步输出的预估表**：动态范围是否收敛、白点被压到多少。不满意就调 `--bl-anchor` / `--wh-anchor` / `--blend` 重跑。
2. **看第 3 步的实测表**：`Δ目标` 列（实测 p5/p95 与目标差）应 ≤ ±3。差得多说明 LUT 没生效（查 4/5 两条反模式）。
3. **出对比图**：`analyze_shots.py` 会写 `*_after.png`，和原帧左右拼起来给用户看。

## B 工具库（按需查）

### B1 黑白位锚定公式（本技能的核心）

```
p5, p95 = 源帧的 5% / 95% 亮度分位（0..255）
t5  = p5  + blend·(BL_ANCHOR − p5)          # BL_ANCHOR 默认 24
t95 = p95 + blend·(WH_ANCHOR − p95)         # WH_ANCHOR 默认 206
a   = (t95 − t5) / (p95 − p5)
b   = (t5 − a·p5) / 255                      # 归一化到 0..1
out = clamp(a·x + b)                          # 三通道同一 a/b → 保留原色相
```

色温只做轻度收拢（默认 22%）：

```
RB' = (a·R_mean + b) / (a·B_mean + b)
k   = (RB + pull·(WB_TARGET − RB)) / RB'      # WB_TARGET 默认 1.16
kr, kb = sqrt(k), 1/sqrt(k)                   # 以 0.5 为轴缩放，不动黑位
```

### B2 参数表

| 参数 | 默认 | 说明 |
|---|---|---|
| `--bl-anchor` | 24 | 目标黑位 |
| `--wh-anchor` | 206 | 目标白位 |
| `--blend` | 0.85 | 施加比例，1.0=完全对齐（丢原片性格），0.7 以下不够压 |
| `--wb-pull` | 0.22 | 色温收拢比例，0=完全保留原色温 |
| `--size` | 33 | cube 网格边长 |

### B3 LUT 落地路径

```
C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\<lut-subdir>\<prefix>_shotNN.cube
```

`gen_luts.py` 会自动拷到上面这个目录（该目录**可写、无需管理员**），然后 `apply_luts.py` 用 `RefreshLUTList()` + `SetLUT(1, "<lut-subdir>/<file>")`。

### B4 验收判据

| 指标 | 合格线 | 说明 |
|---|---|---|
| 动态范围（p95−p5）极差 | ≤ 10 | 本项目 33 → 8 |
| 实测 vs 目标 p5/p95 | ≤ ±3 | 超过说明 LUT 未生效 |
| 相邻镜头 mean 差 | 允许 10~35 | 昼夜层次要留，别强求一致 |
| 白点（curve[255]） | ≥ 200 | 低于 195 画面开始发灰 |

## C 检查与沉淀

- `apply_luts.py` 会 `ResetAllGrades()` 再挂 LUT —— 这样做是**幂等**的（重跑不会叠加两层）。
- 每镜头一个 LUT 的好处：调色页里看得见、能手动改、能单条回退（把该节点 LUT 清空即可）。
- 清理：`C:\ProgramData\...\LUT\<lut-subdir>\` 里的 cube 是文件，换方案时记得删旧目录，否则 Resolve 的 LUT 列表会越堆越长。
- 本项目实测（8 镜头）：目标 p5 24 / p95 206 → 实测 p5 24~32 / p95 205~211，动态范围 176~184，mean 99~135 保留梯度。
