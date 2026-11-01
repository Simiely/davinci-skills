# davinci-skills

DaVinci Resolve 脚本化剪辑 / 调色 / 交付技能集——把**实测跑通**的 Resolve 自动化流程沉淀成可安装技能，触发词即用。

每个技能都是 `SKILL.md` + 可直接运行的 Python 脚本，脚本零第三方依赖（除 ffmpeg / Pillow 外），全部在 Resolve Studio 21.1 / Windows 实测通过。

## 技能列表

| 技能 | 一句话 | 入口 | 状态 |
|---|---|---|---|
| **resolve-script-bridge** 连上 Resolve | 用 Python 连上**正在运行**的 Resolve——必须自设 `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` + `sys.path`；`Project.SetCurrentTimeline` 而非 ProjectManager；时间线默认起点 01:00:00:00（=108000 帧@30fps）；附连通性自检脚本 | [skills/resolve-script-bridge/SKILL.md](skills/resolve-script-bridge/SKILL.md) | v1 稳定 |
| **resolve-timeline-build** 按帧精确建线 | 按帧边界切分素材并落到时间线——`AppendToTimeline` 的 `endFrame` 是**排他**的，按"含尾帧"传值会让每段少 1 帧、切点留下**1 帧纯黑**；正确写法 `边界=[0,90,...,1110]`；附建线与几何自检脚本 | [skills/resolve-timeline-build/SKILL.md](skills/resolve-timeline-build/SKILL.md) | v1 稳定 |
| **resolve-shot-grade-lut** 分镜统一调色 | 按镜头逐个调色且**不抹平昼夜层次**——别对齐 mean，对齐**黑位 p5→24 / 白位 p95→206**（施加 85%），动态范围收敛到 176~184；`SetCDL` 有 bug（中性参数也偏红）改用 `Graph.SetLUT` + 自建 `.cube`，**必须用 LUT 目录内的相对路径**；附 3 个脚本（抽帧统计 / 生成 cube / 上色验证） | [skills/resolve-shot-grade-lut/SKILL.md](skills/resolve-shot-grade-lut/SKILL.md) | v1 稳定 |
| **resolve-flicker-fix** 闪烁诊断与修复 | 分辨"**运动**"和"**噪点**"再动手——块级最大差会把前景运动误判成闪烁；判据用同一区域**逐像素帧间变化量**在改前/改后的比值；LUT 压高光只值 −3%~−30%（白点掉到 178），正解是调色页加节点 +「降噪」（玻璃区实测 −15%~−21%） | [skills/resolve-flicker-fix/SKILL.md](skills/resolve-flicker-fix/SKILL.md) | v1 稳定 |
| **resolve-deliver-check** 成片交付校验 | 交付前用数字把关——`ffprobe` 对帧数/时长/码率；逐帧灰度扫描黑帧（阈值 <6）；`volumedetect` 查峰值（0 dBFS 要留 2~3 dB 余量）；片尾卡目视确认；附一键校验脚本 | [skills/resolve-deliver-check/SKILL.md](skills/resolve-deliver-check/SKILL.md) | v1 稳定 |

## 安装

每个技能是一个目录，内含 `SKILL.md`。安装到用户技能目录即可：

```powershell
# Windows
Copy-Item -Recurse skills\resolve-script-bridge "$env:USERPROFILE\.workbuddy\skills\"
```

安装后在对话里说触发词（见各技能 frontmatter 的 `description`）即可使用。

## 前置条件

- **DaVinci Resolve Studio**（免费版脚本接口受限，本仓库全部在 Studio 21.1.0.17 实测）
- Python 3.9+（只用标准库；调色统计脚本额外用 Pillow）
- `ffmpeg` / `ffprobe` 在 PATH 里（抽帧、校验用）
- Resolve 需**正在运行**并且允许外部脚本（偏好设置 → 系统 → 常规 → External scripting using 设为 Local）

## 维护规范

遵循 [knowledge-base 单项目规范](https://github.com/Simiely/knowledge-base/tree/main/模板库/单项目规范)：

- **四件套**：README（用户向）/ AGENTS（AI 向 + 文档基线）/ DEVELOPMENT（开发者向）/ CHANGELOG（版本记录）
- **文档基线**：`AGENTS.md` 顶部标日期 + 版本，改后更新（断点续传）
- **生长式拆分**：主文件超阈值才拆（README >150 行、DEVELOPMENT >200 行），平时保持精简
- **新增技能五件事**：`skills/` 加目录 + README 技能列表加行 + CHANGELOG 加版本节 + AGENTS 基线行更新 + DEVELOPMENT 补坑记录（一坑一篇）

## 相关

- 通用 AI 工作流技能：https://github.com/Simiely/workbuddy-skills
- 知识库（跨项目文档沉淀）：https://github.com/Simiely/knowledge-base
