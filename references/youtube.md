# YouTube 拆解链路 — 要点与踩坑

> 2026-09 首次接入 YouTube 时实测记录。**已修复项标 ✓；仍可能踩到标 ⚠。**

## 与 B 站的本质差异（决定了架构怎么改）

| | B 站 | YouTube |
|---|---|---|
| 字幕接口 | 只有 UP 主手动上传的硬字幕，**无 AI 字幕接口** | 官方字幕 + **自动生成字幕（ASR）**，数百语种，`timedtext` 公开可拉 |
| 取文稿成本 | 必跑本地 ASR：486MB 模型 + 约 10min / 40min 视频 | **字幕直取，秒级** |
| 下载 | 自研 playurl（yt-dlp 会被 WAF 返 412） | yt-dlp 标准链路 |

所以 `all` 在 YouTube 上的顺序是 **info → subs（命中即止）→ 仅当需要抽帧时下载视频 → transcript**，
不要照搬 B 站「先下载再转写」的链路，会白白多花十几分钟和几百 MB。

## ✓ yt-dlp 三个必踩的坑

1. **ffmpeg_location 必须显式给**，否则报
   `ERROR: You have requested merging of multiple formats but ffmpeg is not installed`。
   原因：imageio-ffmpeg 的二进制不在 PATH 上。
2. **更隐蔽的一层**：光把 imageio 的目录传给 `ffmpeg_location` **仍然报错**，
   因为 yt-dlp 只认**文件名为 `ffmpeg` / `ffmpeg.exe`** 的可执行文件，
   而 imageio 给的是 `ffmpeg-win-x86_64-v7.1.exe`。
   解法：复制一份标准名副本到 `~/.workbuddy/bin/`（`lib_yt.ffmpeg_dir()` 已实现，按体积判断是否已存在）。
3. **`outtmpl` 用了绝对路径就别再设 `paths.home`**，否则 yt-dlp 会再拼一层目录，
   出现 `work/audio.m4a` 实际落在 `work/work/audio.m4a` 的怪事。

## ✓ timedtext 429 限流

同一视频**连续请求**字幕（尤其「主轨 + 附加轨」连着抓）必定触发 **HTTP 429**。
无脑快速重试只会越试越 429，必须**指数退避**：5s → 10s → 20s → 40s → 60s。
`lib_yt.fetch_subtitle_json()` 已内置（按 HTTP code 判断，不靠 returncode）。

## ✓ 字幕语种选择：默认原语音 `-orig`

YouTube 自动字幕里：
- `ja-orig` / `en-orig` = **原始语音的 ASR**（未翻译，保真度最高）
- `ja`、`zh-Hans`（无 -orig）= 可能是**机器翻译轨**

实测：日语视频的 `zh-Hans` 轨质量很差（把「Codex」译成「国际法典委员会」、「Grockbot」译成「格洛克机器人」、
「DevDay」译成「非开放日」）。拿机翻轨做专题页会直接污染结论。

**正确做法**：主依据取 `-orig` 原始轨，由 agent 自己翻译理解；
`--also zh-Hans` 留一份中文轨仅作交叉校对，不当主依据。

## ⚠ 仍然可能踩到

- **签名算法变更**：YouTube 播放器签名几乎月月变，yt-dlp 需保持最新
  （`pip install -U yt-dlp`）。不要自维护签名逻辑，这是无底洞。
- **会员 / 年龄限制 / 地区限制视频**：yt-dlp 会直接失败，需要 cookies，本环境不处理。
- **评论抓取**：YouTube 评论接口近年收紧，`getcomments` 常返回空。
  `lib_yt.comments()` 已做「失败即返回 []」，不影响主流程。
- **长视频抽帧**：`--every 20` 在 1 小时视频上是 180 张，注意磁盘与整理成本。

## 附：json3 字幕结构

```json
{"events": [{"tStartMs": 1230, "dDurationMs": 2000,
             "segs": [{"utf8": "文本"}]}]}
```

`lib_yt.json3_to_segments()` 按「累计 90 字 或 静音间隔 > 1.2s」切段，
把 YouTube 的碎事件合并成可读段落（否则一句话被切成十几个片段，没法读）。
