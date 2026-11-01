# AGENTS.md · 项目规则

> 📌 **文档基线**：2026-11-01 v1.0.0（首版：5 个技能 — 连通 / 建线 / 分镜调色 / 闪烁诊断 / 交付校验）
> **更新文档/代码后，请更新此行**（日期 + 新 commit hash），并在 CHANGELOG 追加版本

## 技术栈

- **Resolve 脚本接口**：官方 Python 模块 `DaVinciResolveScript`，路径
  `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`
- **DLL**：`C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll`
- 本机实测环境：Resolve **Studio 21.1.0.17** + 系统 Python 3.13（无 numpy，有 Pillow）
- 调色数据通路：`Graph.SetLUT(nodeIndex, 相对路径)` + 自建 33³ `.cube`
- 视频测量：`ffmpeg` 滤镜 `signalstats` / `blackdetect` / `volumedetect`，raw 灰度管道 + Pillow 统计

## 关键坑

- **环境变量默认是空的**：`RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` 在本机**都没设**，脚本必须自己 `os.environ[...] = ...` 再 `sys.path.append(.../Modules)`，否则 `import DaVinciResolveScript` 直接失败。
- **`ProjectManager` 没有 `SetCurrentTimeline`**：`pm.SetCurrentTimeline(tl)` 会抛 `'NoneType' object is not callable`，要用 **`Project.SetCurrentTimeline(tl)`**。
- **`AppendToTimeline` 的 `endFrame` 是排他的**（与 `GetDuration = end − start` 一致）。按"含尾帧"传值 → 每段少 1 帧；再配合显式 `recordFrame` 定位，就在**每个切点留 1 帧纯黑**，成片里是肉眼可见的闪黑。正确写法：`startFrame = 本段首帧`、`endFrame = 下一段首帧`。
- **`TimelineItem.SetCDL` 在本版本是坏的**：连身份 CDL（`slope=1 / offset=0 / power=1 / sat=1`）都会把画面压成红色渐变（R/G/B 从 148/144/148 变成 225/56/56）。`ResetAllGrades()` 可恢复。**别用 CDL 做调色，改用 `Graph.SetLUT`。**
- **`SetLUT` 只认 LUT 目录内的相对路径**：传绝对路径直接返回 `False`。LUT 必须放到
  `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\<子目录>\`，拷完调 `Project.RefreshLUTList()`，然后 `SetLUT(1, "<子目录>/xxx.cube")`，`GetLUT(1)` 会回读成 `子目录\xxx.cube`。
- **API 不能建节点、不能设降噪参数**：运行时反射 `Graph` 只有 11 个方法（`SetLUT / GetLUT / SetNodeEnabled / GetNodeCacheMode / GetNodeLabel / GetToolsInNode / GetNumNodes / ResetAllGrades / ApplyGradeFromDRX / ApplyArriCdlLut`），**没有 AddNode**。降噪只能读到工具名（`GetToolsInNode` 返回 `['降噪']`），帧数/阈值读写都不行。
- **Fusion 里也没有降噪节点**：`AddFusionComp()` 可用，但注册表实测**没有** `Denoise / TemporalNR / SpatialNR / Deflicker / TimeAverager / Trail / Echo / Median`，只有 `Blur / VectorMotionBlur / TimeStretcher / BrightnessContrast / ColorCorrector` 这类。
- **`ExportCurrentFrameAsStill` 偶发返回 `False`**：同一路径前一轮成功、后一轮失败（未见规律）。失败时换输出路径或重试一次；批量导出要对返回值逐个断言，别只看有没有抛异常。
- **时间线默认起点是 01:00:00:00**（30fps 下 = 108000 帧）。算 timecode 时不要自己加 1 小时，`frame//30` 直接换算即可。
- **判断网络用 Python urllib，不用 `curl -w`**：本机 `curl -w "%{http_code}"` 会假失败（exit 43 / http_code 000），同一条命令去掉 `-w` 就正常。

## 约定

- 每个技能一个子目录，`SKILL.md` 为唯一入口
- `SKILL.md` frontmatter 必须有 `name` + `description`（**description 里要写触发词**）+ `agent_created: true`
- 正文三层结构：**A 主线（必做）/ B 工具库（按需查）/ C 检查与沉淀**，并单列「反模式」
- 中文文档；脚本纯标准库优先，第三方依赖必须在 SKILL.md 里写明安装命令
- 职责单一：连通 ≠ 建线 ≠ 调色 ≠ 诊断 ≠ 校验，分开建技能，不捆绑
- **所有结论必须带实测数字**（改前/改后、误差、帧号），不写"效果不错"这类空话
- 脚本内**不写死项目路径/项目名**，一律走参数或环境变量
- 归档惯例：不再维护的技能移入 `skills/_archived/`，SKILL.md 顶部加「⚠️ 已归档」+ 被谁替代

## 常用命令

```powershell
# 连通性自检（先跑这个，能连上再做别的事）
py -3.12 skills\resolve-script-bridge\resolve_connect.py

# 建线 + 几何自检
py -3.12 skills\resolve-timeline-build\build_timeline.py --media "E:\path\clip.mp4" --bounds 0,90,180,330 --timeline "cut_v1"

# 分镜调色三步：抽帧统计 → 生成 cube → 上色并导出验证帧
py -3.12 skills\resolve-shot-grade-lut\scripts\analyze_shots.py --media "..." --bounds 0,90,180
py -3.12 skills\resolve-shot-grade-lut\scripts\gen_luts.py --shots shots.json --lut-subdir myproject
py -3.12 skills\resolve-shot-grade-lut\scripts\apply_luts.py --timeline cut_v1 --lut-subdir myproject

# 闪烁诊断（先判断是运动还是噪点）
py -3.12 skills\resolve-flicker-fix\scripts\flicker_scan.py --media "..." --range 600,810

# 成片校验
py -3.12 skills\resolve-deliver-check\scripts\verify_deliver.py --file "E:\out\final.mp4"
```

## 详细规则（按需 @引用）

- @DEVELOPMENT.md  仓库结构、新增技能流程、坑记录（一坑一篇）、调色方法论、推送方案
