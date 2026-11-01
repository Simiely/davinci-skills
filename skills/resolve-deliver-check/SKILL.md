---
name: resolve-deliver-check
description: 成片交付前用数字把关——ffprobe 对分辨率/帧数/码率/音轨，逐帧灰度扫描黑帧（亮度<6 必须 0 个），volumedetect 查音频峰值（0 dBFS 需留 2~3 dB 余量），可选核对片尾卡与帧数是否等于时间线长度。当用户说"导出前检查一下/成片有没有问题/这段有没有黑帧/音量够不够"时使用。附 verify_deliver.py。
agent_created: true
---

# resolve-deliver-check —— 成片交付校验

职责单一：对**已经渲染出来的文件**做客观体检，输出可复现的数字与结论。不负责渲染、不改工程。

## 什么时候用

- 渲染完要交付/上传前。
- 用户反馈"中间好像黑了一下""总长不对""声音爆了"。
- 改了时间线（加片尾、换 BGM）之后，确认新成片与工程一致。

## 反模式（务必避免）

1. **只看播放器能不能播** —— 黑帧、音轨缺失、帧数差几帧，播放器都不会报警。
2. **用眼睛数黑帧** —— 1/30 秒的闪黑在正常播放里几乎看不见，但会被观众感知成"卡了一下"。必须逐帧扫。
3. **只看文件大小判断画质** —— 码率高不代表没问题（黑帧、掉帧照样高码率）。
4. **忽略音频峰值** —— `max_volume: 0.0 dB` 就是**顶到满刻度**。平台二次转码极易在鼓点上爆音，交付前应留 2~3 dB 余量。
5. **帧数只信 ffprobe 的 `nb_frames`** —— 有些封装不写这个字段（返回 0/缺失），要再和 `duration × fps` 交叉验证。
6. **忘记片尾卡** —— 加了 logo/字卡后总长会变（本项目 37s → 40s），校验要以**当前时间线**为准，别拿旧数字比。

## A 主线（必做）

```powershell
py -3.12 skills\resolve-deliver-check\scripts\verify_deliver.py ^
    --file "E:\out\final.mp4" --expect-frames 1200 --expect-fps 30
```

读四组结论，全绿才交付：

| 组 | 判据 |
|---|---|
| 规格 | 分辨率/帧率/编码符合交付要求；`nb_frames` 与 `--expect-frames` 一致 |
| 时长 | `duration ≈ 帧数 / fps`（±0.05s 内） |
| 黑帧 | 亮度 < 6 的帧数 **必须 0** |
| 音频 | 有音轨；`max_volume` ≤ −0.5 dB（理想 −1 ~ −3）；`mean_volume` 约 −14 ~ −18 dB |

## B 工具库（按需查）

### B1 手工命令（脚本不好用时）

```powershell
# 规格
ffprobe -hide_banner -show_entries format=duration,bit_rate ^
        -show_entries stream=codec_name,width,height,nb_frames,r_frame_rate -of default=nw=1 final.mp4

# 音频电平
ffmpeg -hide_banner -i final.mp4 -af volumedetect -f null - 2>&1 | Select-String "mean_volume|max_volume"

# 黑帧
ffmpeg -hide_banner -i final.mp4 -vf "blackdetect=d=0.02:pix_th=0.10" -an -f null - 2>&1 | Select-String black_start
```

### B2 为什么用"逐帧灰度均值"而不是 blackdetect

`blackdetect` 对**纯黑**敏感，但切点处那种"帧里还有一点点内容"的暗帧会漏。逐帧灰度均值是更硬的判据：本项目 7 个黑帧的均值都是 **0.0**，正常帧最低 60.7（夜景），阈值 6 分开得很干净。

### B3 常见问题对照

| 症状 | 数值特征 | 原因 |
|---|---|---|
| 切点闪黑 | 孤立帧亮度 0.0，数量 = 切点数 | `AppendToTimeline` 排他端写错（见 resolve-timeline-build） |
| 总长多/少几帧 | `nb_frames` 与时间线帧数差 1~8 | 同上 |
| 音轨缺失 | 只有 1 条 stream | 建线时没带音频 / 渲染没勾 ExportAudio |
| 峰值 0 dBFS | `max_volume: 0.0 dB` | BGM 未降增益，需 −2~−3 dB |
| 片尾黑 | 最后一秒亮度 < 6 | 片尾卡没铺满 / 时长没对齐 |

## C 检查与沉淀

- 校验脚本**必须自己解码**，不要相信容器头里的字段（本项目 `nb_frames` 是准的，但别的封装不一定）。
- 交付前把三样留下：成片路径、`nb_frames`、黑帧数。以后出问题能立刻对齐。
- 本项目实测基准：`1200 帧 / 40.00s / 1920×1080 / 36.0 Mbps / 黑帧 0 / max_volume 0.0 dB（需降 2 dB）`。
