# CHANGELOG

## v1.0.0 · 2026-11-01

首版。5 个技能，全部来自一次完整的真实项目（37 秒 8 镜头素材 → 分镜调色 → 修闪烁 → 40 秒成片交付），结论都带实测数字。

### 新增技能

- **resolve-script-bridge** 连上 Resolve
  - 自设 `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` + `sys.path` 再 import（本机这两个环境变量本来就是空的）
  - `resolve_connect.py`：一次打印产品名/版本/项目/时间线/媒体池概览，作为一切操作的前置自检
  - 记录 `Project.SetCurrentTimeline`（不是 ProjectManager）、默认起点 108000 帧@30fps

- **resolve-timeline-build** 按帧精确建线
  - 定位并修复 `AppendToTimeline` 排他语义导致的**切点 1 帧纯黑**（7 个黑帧 → 0）
  - `build_timeline.py`：按边界数组建线 + 几何自检（段长/总长/源范围对照）

- **resolve-shot-grade-lut** 分镜统一调色
  - 发现 `SetCDL` 本版本有 bug（身份参数也偏红 225/56/56），改走 `Graph.SetLUT` + 自建 33³ `.cube`
  - 确立「**黑白位锚定法**」：对齐 p5→24 / p95→206（85% 施加），动态范围极差 33 → 8，且不抹平昼夜层次
  - 3 个脚本：`analyze_shots.py`（抽帧统计）/ `gen_luts.py`（生成 cube 到 LUT 目录）/ `apply_luts.py`（上色 + 导出验证帧）

- **resolve-flicker-fix** 闪烁诊断与修复
  - 诊断流程：全帧亮度曲线（查黑帧/整帧闪）→ 分区域亮度 → 逐像素帧间活动量（区分运动 vs 噪点）
  - 量化证明 LUT 压高光对时域闪烁无效（−3%~−30%，白点 235→178）
  - 量化 3D 玻璃渲染闪烁的可行解：调色页节点 +「降噪」= 玻璃区 −15%~−21%；ffmpeg `atadenoise`/`hqdn3d` ≈ 0
  - `references/case-20261101-glass-flicker.md`：完整案例（含 API 能力边界的两条实测证据）

- **resolve-deliver-check** 成片交付校验
  - `verify_deliver.py`：ffprobe 规格 + 逐帧灰度扫黑帧 + `volumedetect` 峰值 + 时长/帧数一致性
  - 判据：黑帧（亮度<6）必须 0；峰值 0 dBFS 需留 2~3 dB 余量（平台二次转码会爆）

### 约定

- 四件套（README / AGENTS / DEVELOPMENT / CHANGELOG）+ SKILL.md 三层结构（A 主线 / B 工具库 / C 检查沉淀）
- 遵循 [knowledge-base 单项目规范](https://github.com/Simiely/knowledge-base/tree/main/模板库/单项目规范)
