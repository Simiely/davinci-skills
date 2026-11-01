# DEVELOPMENT.md · 开发者文档

> 面向：维护本仓库的人（含 AI）。用户向说明见 [README.md](README.md)，AI 规则见 [AGENTS.md](AGENTS.md)。

## 1. 仓库结构

```
davinci-skills/
├── README.md            用户向：技能列表表格 + 安装 + 前置条件
├── AGENTS.md            AI 向：文档基线 + 关键坑 + 约定
├── DEVELOPMENT.md       本文：结构 / 流程 / 坑记录 / 方法论
├── CHANGELOG.md         版本记录
└── skills/
    ├── resolve-script-bridge/
    │   ├── SKILL.md
    │   └── resolve_connect.py
    ├── resolve-timeline-build/
    │   ├── SKILL.md
    │   └── build_timeline.py
    ├── resolve-shot-grade-lut/
    │   ├── SKILL.md
    │   └── scripts/{analyze_shots.py, gen_luts.py, apply_luts.py}
    ├── resolve-flicker-fix/
    │   ├── SKILL.md
    │   ├── scripts/flicker_scan.py
    │   └── references/case-20261101-glass-flicker.md
    └── resolve-deliver-check/
        ├── SKILL.md
        └── scripts/verify_deliver.py
```

目录约定：
- **单脚本**直接放技能根目录（`resolve_connect.py`）；**≥2 个脚本**放 `scripts/`
- 坑位清单、案例日志放 `references/`，文件名带日期
- 可复制的模板放 `templates/`（当前无）

## 2. 新增技能流程

1. `skills/<kebab-name>/SKILL.md`，照抄现有技能的 frontmatter 三段（`name` / `description` 含触发词 / `agent_created: true`）
2. 正文写 A 主线 / B 工具库 / C 检查与沉淀，**单列「反模式」**
3. 脚本落地，**去掉项目硬编码路径**，改参数化
4. 自测：脚本能独立跑通并输出可验证的数字
5. 五件事收尾：README 加行 + CHANGELOG 加版本节 + AGENTS 基线行更新 + DEVELOPMENT 补坑（一坑一篇）

## 3. 坑记录（一坑一篇）

### 3.1 `AppendToTimeline` 的 endFrame 排他 → 切点 1 帧纯黑

**现象**：8 段切完，时间线总长比源少 8 帧；渲染成片逐帧扫亮度，**7 个切点上各有 1 帧亮度 0.0**，播放时是肉眼可见的闪黑。

**根因**：`endFrame` 是**排他**的（`GetDuration = end − start` 也印证这套语义）。按"含尾帧"传 `(0,89)` 实际只收 89 帧；再配合显式 `recordFrame` 定位，段与段之间就空出 1 帧 → 黑。

**修法**：边界数组用"下一个起点"作排他端：

```python
BOUNDS = [0, 90, 180, 330, 510, 600, 690, 810, 1110]
infos = [{"mediaPoolItem": clip, "startFrame": BOUNDS[i], "endFrame": BOUNDS[i+1],
          "recordFrame": TL_START + BOUNDS[i], "trackIndex": 1} for i in range(len(BOUNDS)-1)]
```

**验收**：8 段时长 `90/90/150/180/90/90/120/300` 合计 1110；成片逐帧扫描 `亮度<6` 的帧数 = **0**（修前 = 7）。

### 3.2 `SetCDL` 偏红 → 改用 LUT

**现象**：`SetCDL({"NodeIndex":1,"Slope":[1,1,1],"Offset":[0,0,0],"Power":[1,1,1],"Saturation":1})`（身份变换）返回 `True`，但导出帧 R/G/B 均值从 `148/144/148` 变成 `225/56/56` —— 整片红洗。换成真实参数同样偏红。

**判定**：这不是参数问题。对照实验：从**没调过色的原始时间线**导出同帧 = 正常；`ResetAllGrades()` 后 = 正常；只要调过 `SetCDL` 就偏红。⇒ 该版本接口写 primary 工具时有 bug。

**修法**：`Graph.SetLUT(nodeIndex, "<子目录>/xxx.cube")`。注意绝对路径返回 `False`，必须放 LUT 目录 + `RefreshLUTList()` + 相对路径。

### 3.3 分镜调色：别对齐平均亮度

**现象**（第一版做法）：把 8 个镜头的 mean 拉到 118~126 同一区间 → 用户反馈"观感不对，像白天到黑夜的变化被抹平了"，且部分镜头更灰。

**根因**：mean 同时受**曝光**和**画面内容**影响（暗背景镜头天然 mean 低）。对齐 mean 等于拿内容差异当曝光差异修，同时把昼夜层次压平；用 `slope<1` 压亮度还会**降低**对比度。

**修法（黑白位锚定法）**：

```
目标：所有镜头 p5 → 24、p95 → 206（施加 85%，保留 15% 原片性格）
a = (p95' − p5') / (p95 − p5);  b = p5' − a·p5        # 逐通道同一 a/b，保留原色
色温：只做 22% 轻度收拢，别硬拉中性
```

**结果**：动态范围（p95−p5）从 151~184（极差 33）收敛到 **176~184（极差 8）**，切点不再跳；mean 仍保留 99~135 的起伏（昼夜层次在）。

### 3.4 闪烁诊断：块级最大差会把"运动"误判成"噪点"

**现象**：用 16×16 块统计帧间差找闪烁热点，最大的块稳定落在**画面左下角**（单帧跳 ±18 级），一度被判定为闪烁源。实际那是**前景树枝 + LED 灯串在镜头前扫过**，属于运动。

**修法**：判据换成**逐像素帧间变化量在改前/改后版本的比值**（同一区域同一帧段），运动在两个版本里都一样，只有噪点会被降噪吃掉：

```
activity(block) = mean_over_frames |cur − prev|    # 逐像素
改前 8.45 → 改后 6.78  ⇒ −19.9%（这块才真的被降噪作用到）
```

### 3.5 LUT 压高光治不了时域闪烁（量化结论）

在真实帧上逐候选曲线实测（热点 std：8.36）：

| 肩部参数 | 闪烁降幅 | 白点被压到 |
|---|---|---|
| K=0.68 M=0.92 | −2.9% | 235 |
| K=0.58 M=0.84 | −11.8% | 214 |
| K=0.55 M=0.80 | −16.3% | 204 |
| K=0.45 M=0.70 | −30.4% | 178（画面发灰） |

⇒ 静态 LUT 只能"压幅度"，代价是白点崩掉。**时域问题必须用时域手段**（调色页节点 +「降噪」）。

### 3.6 三维玻璃渲染的时域闪烁，后期能压多少

素材是 3D 渲染的玻璃场景，**每帧噪点位置都不同**（蒙特卡洛 + 逐帧独立降噪），单帧看干净、播放才闪。

- ffmpeg `atadenoise`：噪声指数 4.18 → **4.14**（无效）
- ffmpeg `hqdn3d` 时域 6：4.18 → **4.11**（无效）
- Resolve 调色页节点 +「降噪」：玻璃区逐像素帧间变化 **−15% ~ −21%**（有效）

结论：后期 ffmpeg 类时域平均对"小幅高频随机噪点"几乎无效；Resolve 的降噪带运动估计，是唯一有效路径，但**只能手动加节点**（API 不可建节点、不可设参数）。

## 4. 推送方案

本机 `git push` 到 github 有两个坑：**凭据弹窗**（credentialhelperselector/GCM 无交互挂死）与**通道不稳定**（7890 代理时通时断）。

```powershell
# 首选：清掉 credential helper，token 内嵌在 URL 里（不落盘）
git -c credential.helper= push "https://<PAT>@github.com/Simiely/davinci-skills.git" main

# 回退：GitHub Contents API 逐文件 PUT（base64 content）
#   PUT /repos/Simiely/davinci-skills/contents/{path}
```

**token 只走环境变量或一次性 URL，绝不写进任何被提交的文件。**

## 5. 相关

- 上游规范：https://github.com/Simiely/knowledge-base/tree/main/模板库/单项目规范
- 通用技能库：https://github.com/Simiely/workbuddy-skills
