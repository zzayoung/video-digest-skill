---
name: video-digest
description: 把视频（B站 / YouTube / 微信视频号 / 本地视频文件）拆解成结构化交付物：专题页 HTML、可编辑 SVG 架构图、表格版 Markdown、带时间码全文稿页。当用户给出视频链接、BV 号、视频号分享链接或本地视频文件，说"拆解 / 梳理 / 整理 / 总结 / 做成专题页 / 讲透 / 分析这个视频 / 做个视频笔记"时使用。流程：识别平台→抓元信息→取文稿（YouTube 优先直取字幕，其余走本地 ASR）→抽关键帧→写 outline.json→build 生成四件套。视频无字幕也能做。
agent_created: true
---

# 视频拆解 → 结构化专题页

> **v2.0（2026-11-02 合并版）**：B 站 / YouTube / 视频号 / 本地文件四平台 + `outline.json` 生成管线 + 亮暗双主题设计系统与六项交互。

拿到一个视频（链接或本地文件），产出一套**可直接交付**的专题页：HTML 主页面 + 可编辑 SVG 架构图 + 纯表格版 Markdown + 带时间码的完整文稿页。

## 何时用

- 用户给 B 站链接 / BV 号 / YouTube 链接 / 视频号分享链接 / 本地视频文件，说"拆解""梳理""整理成专题页""讲透""总结内容""分析这个视频"
- 视频没有字幕、没有简介，需要靠语音转写还原内容

## 平台差异（一张表看清为什么要分四路）

| 维度 | B 站 | YouTube | 微信视频号 | 本地文件 |
|---|---|---|---|---|
| 元信息 | 官方 API | yt-dlp | **下载记录里的 `.wx-*.json`** | ffprobe |
| 文稿来源 | 必走本地 ASR | **优先字幕直取**（秒级） | 必走本地 ASR | 必走本地 ASR |
| 媒体获取 | 自研 playurl（yt-dlp 被 WAF 返 412） | yt-dlp | 借 `wx-downloader` + 元宝登录态 | 无需下载 |
| 前置条件 | 无 | 无 | **需人工扫码登录一次** | 文件存在即可 |
| 清晰度上限 | 未登录 480P | 1080P+ | 取决于源 | 原样 |

**`all` 会自动按平台选路**：YouTube 有字幕就跳过 ASR，省掉 483MB 模型 + 约 10 分钟转写；其余三种一律走 ASR。

## 快速开始

**先确认环境**：到新机器第一次用，先读 `INSTALL.md` 并装依赖。之后统一用技能根目录的
`run.py` 调用——它会自动切到技能自带的 `.venv`，不用记解释器路径。

```bash
cd ~/.workbuddy/skills/video-digest        # 或 Windows: %USERPROFILE%\.workbuddy\skills\video-digest

# 首次：建 venv + 装依赖 + 下模型 + 自检（详见 INSTALL.md）
python scripts/setup_env.py

# 0) 自检（四个平台能力分别列出，缺谁不影响谁）
python run.py doctor

# 1) 识别平台（拿不准时用）
python run.py detect "https://weixin.qq.com/sph/AC7XUrwG7z"

# 2) 全流程（最常用）
python run.py all "https://www.youtube.com/watch?v=xxxx" -o ./work --every 20
python run.py all BV1t8oAYuEVf -o ./work --every 20
python run.py all "C:/videos/xxx.mp4" -o ./work                      # 本地文件
python run.py all "https://weixin.qq.com/sph/AC7XUrwG7z" -o ./work   # 视频号

# 3) 渲染交付物（大纲 → 四件套）
python run.py build ./work/outline.json --transcript ./work/asr_segments.json
python run.py build --schema       # 打印 outline.json 字段说明
```

`python` 不可用就换 `python3`；`run.py` 只做解释器转发，任何 3.9+ 都能跑它。
不想用 `run.py` 也可以直连 `python .venv/bin/python scripts/video_digest.py`（Windows 为
`.venv\Scripts\python.exe`）。

`all` 会产出：`info.json` `comments.json` `subtitle_<lang>.json` `asr_segments.json` `transcript.md`（+ 下载了媒体时：`video.*` `audio.*` `audio16k.wav` `frames/` `frames/index.json`）。

转写时长给个大致的量：25 分钟视频、16 线程 CPU、small 模型，约 6–9 分钟。**放后台跑**，别在前台等。

## 交付物生成（这是 skill 的核心价值）

**不要手写 HTML。** 内容与呈现已经解耦：

```
transcript.md + frames/  ──(你：读、分章、提炼)──▶  outline.json
                                                      │
                                        build ────────┴──▶  <slug>.html
                                                             <slug>.svg
                                                             <slug>_table.md
                                                             transcript_full.html
```

好处：样式统一（改版式只改 `scripts/make_page.py`，历史页面重新 build 即对齐）、可增量修订（改一句话只改 outline，不重新生成整页）、四件套天然一致。

### outline.json 怎么写

先跑 `build --schema` 看全量字段。最小可用结构：

```json
{
  "meta": {"slug": "wx-AC7XUrwG7z", "title": "视频标题", "author": "作者",
           "platform": "wxchannels", "duration": "25:41", "mode": "learn",
           "date": "2026-10-30", "url": "https://weixin.qq.com/sph/..."},
  "tldr": ["结论一", "结论二", "结论三"],
  "thesis": "全文核心命题，一句话",
  "sections": [
    {"id": "s1", "title": "章节名", "t0": 0, "t1": 180, "kicker": "背景",
     "gist": "一句话概括（进架构图）", "lead": "导语",
     "paras": ["正文段落，支持 **粗体** 和 `代码`"],
     "bullets": ["要点"],
     "quote": {"text": "原话", "t": 305},
     "table": {"title": "表题", "head": ["列1", "列2"], "rows": [["a", "b"]]},
     "cards": [{"h": "小标题", "p": "说明"}],
     "figs": [{"src": "frames/f_0003.jpg", "cap": "图注", "t": 40}]}
  ],
  "pitfalls": [{"title": "踩坑点", "text": "说明", "t": 120}],
  "takeaways": ["可执行结论"],
  "glossary": [{"term": "术语", "def": "解释"}]
}
```

写 outline 的硬规则：

1. **`t0`/`t1` 必须来自 `transcript.md` 的真实时间码**，不要估。它们同时决定全文稿页的章节切分和页面上的 🕒 跳转。
2. **`figs` 的 `t` 用 `frames/index.json` 查**，不要自己算 `(i-1)*every`（every 不整除时必算错）。
3. **`gist` 一句话**，超过 38 字会被架构图裁掉。
4. 表格优先：凡是「设置值 + 原因」「选项 + 差异」「阶段 + 产出」这类结构，一律 `table`，不要写成段落。用户要求双格式（文本版 + 表格版），`build` 已自动产出 `_table.md`。
5. 作者自己提到的失误 / 警告，进 `pitfalls`，单独成节——这是高价值内容。
6. 外文视频：正文用中文，**关键术语保留原文**（如 `GPT-6 Astra`、`Sol 5.6`），首次出现处给中文释义，并在 `glossary` 登记。
7. `slug` 决定文件名，用 ASCII（如 `wx-<share_id>` / `BV<id>`），别用中文。

### 架构图

- `diagram` 不写 → 按 `sections` 自动生成竖向骨架流程（最省事，够用）
- 要自定义布局 → 给 `diagram.nodes` + `edges` 并设 `"style": "manual"`，节点用 `x/y/w/h` 绝对定位
- 产物是**独立 SVG 文件**，主页面用 `<img>` 引用（不是 `<object>`——object 按固有像素显示，宽屏下右侧留白）
- 用户偏好 SVG 而非位图，是为了能二次编辑：直接改 `.svg` 里的文字，刷新页面即生效
- **SVG 是自带浅色配色的独立文件**：暗色主题下它在页面里仍显示为浅色块，这是预期行为，不要去 invert

## 输出方向

`--mode` 只影响你写 outline 的侧重，以及 `analysis` 字段是否出现：

### 方向 A：梳理理解学习版（默认 `learn`）

侧重从作者叙事中提炼知识框架。章节围绕作者逻辑（概念 → 实践 → 方法论），强调"为什么这么讲""核心论点是什么"。

### 方向 B：方法论反向拆解版（`analysis`）

侧重逆向推理：如果我要做同类内容，需要准备什么、怎么组织。outline 里额外填 `analysis`
（`positioning` / `skeleton` / `methods` / `prep` / `template`），页面会多出「方法论反向拆解」一节，表格版同步输出准备清单与可复用模板。

## 页面设计系统（由生成器统一执行，别自己写样式）

样式与交互**全部内联在 `scripts/make_page.py` 里**，`build` 时自动注入，单文件可分发。你不写 CSS、不写 JS，只写 outline。

- 配色：暖白纸底 `#f7f6f2` + 深青强调 `#14556e`；暗色 `#111315` + `#6cc0d8`。全部走 CSS 变量，改主题只改变量。
- 版式：左侧吸顶目录（窄屏自动隐藏）+ 右侧卡片流；章节带序号、kicker、🕒 时间码。
- 组件：TL;DR 卡（`.thesis` + 有序列表）、架构图、表格、小卡片网格、引用块、踩坑块（红）、术语表。
- **六项必做交互（已内置于生成器，验收时逐条确认）**：

| 功能 | 表现 |
|---|---|
| 主题切换 | 右上角圆钮，亮/暗双主题，`localStorage` 记忆，首屏跟随系统 |
| 阅读进度 | 顶部 3px 渐变进度条 |
| 章节高亮 | 滚动时左侧目录自动高亮当前章节 |
| 图片放大 | 点关键帧打开灯箱，`Esc` 或点击空白关闭 |
| 表格复制 | hover 表格右上角出现「复制表格」，输出 TSV 可直接粘进 Excel |
| 回到顶部 | 滚动 520px 后右下角浮出 |

- **全文稿页额外**：搜索过滤（输入即过滤上千段、命中词 `<mark>` 高亮、显示「N 段命中」）、`/` 聚焦、`Esc` 清空、章节侧栏、浮动「回专题页」。

### 验收清单（每次交付前必做）

- [ ] `build` 四件套全部产出，无报错
- [ ] Edge headless 整页截图看过：首屏、架构图、至少一个表格区
- [ ] 架构图底部没被裁、徽章数字是白字
- [ ] 表格 hover 出「复制表格」
- [ ] 点关键帧能放大，`Esc` 能关
- [ ] 点主题钮能切暗色，刷新后保持
- [ ] 目录点击能跳，吸顶不漏标题
- [ ] 全文稿页搜一个词能过滤并高亮
- [ ] 375px 窄屏下不横向溢出（表格自己横向滚）
- [ ] 打印预览里没有导航、进度条、浮动按钮

截图命令（**输出到 `%TEMP%`**，直接写工作区目录会被拒）：

```bash
MSEDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"   # 注意不在 Program Files 下
"$MSEDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="C:\\Users\\<你>\\AppData\\Local\\Temp\\page.png" \
  --window-size=1280,2600 "file:///C:/path/to/page.html"
```

## 视频号专用说明（首次必读）

视频号分享页是 JS 渲染 + 签名校验，纯 HTTP 拿不到播放地址。目前唯一稳定的路子是借
[`wx-downloader`](https://github.com/QinGeneral/wx-downloader)（PyPI 同名包，模块名
`wx_channels_cli`）——它用**腾讯元宝**的登录 Cookie 请求解析接口，把分享链接还原成真实 CDN 地址。

```bash
# 首次：扫码登录（会拉起浏览器，用户本人操作；凭据自动存 ~/.config/wx-channels/auth.json）
python run.py wx-login --browser msedge

# 查看登录态与目录
python run.py wx-status
```

关键约定：

- **只有 `weixin.qq.com/sph/...` 形态的链接可用**。公众号文章、直播、图集、微信内短口令都不支持。
- **登录态会过期**（服务端侧）。报错带"登录态失效"提示时重跑 `wx-login`。
- **`all` 默认 `--login-mode forbid`**，凭据不可用就直接失败，绝不把 agent 卡在等扫码上。
  交互场景想让它自动弹窗，显式传 `--login-mode auto`。
- 分享链接的 `?from=...` 等 tracking 参数会被剥掉再下载，保证「同一视频」被认成同一个。
- 视频号**没有任何字幕轨**，所以一定走 ASR，不存在"省掉转写"的可能。

## 字幕语种怎么选（YouTube）

**默认顺序：原语音 `-orig` > 中文 > 英文。**

理由：YouTube 的 `zh-Hans` 轨对日语/英语视频多是**机器翻译轨**，错译会直接污染专题页结论。正确做法是拿原始语种保真文本，再由 agent 自己翻译理解。

- `ja-orig` / `en-orig` = 该视频原始语音的 ASR（未翻译）
- `ja` / `zh-Hans`（无 `-orig`）= 可能是翻译轨
- `--also zh-Hans` 可同时留存一份中文轨交叉校对，但**不要把它当主依据**

## 怎么把内容"讲透"

工具只出原料（文稿 + 帧图），真正的价值在整理。按这个顺序：

1. **读 `transcript.md` 全文**（带时间码），不要只读片段。
2. **划章节**：按内容转折点切段，记录每段起止时间码。
3. **提炼骨架**：找出作者的"核心框架"（多数优质视频有一个分层/分类结构），这是专题页的脊柱，也是 `gist` 的集合。
4. **参数/清单表格化**：菜单项、设置项、对比，一律表格（设置值 + 原因 两列）。
5. **配关键帧**：查 `frames/index.json` 按时间码挑图，图注标 `🕒 mm:ss`。
6. **补"踩坑"章节**：作者提到的自身失误 / 警告，单独成节。

## 输出物清单

| 文件 | 内容 |
|---|---|
| `<slug>.html` | 主专题页：结论 + 架构图 + 章节 + 表格 + 关键帧 + 时间码 |
| `<slug>.svg` | 可编辑架构图（独立文件，改文字刷新即生效） |
| `<slug>_table.md` | 纯表格版，方便复制到飞书 / 腾讯文档 / Excel |
| `transcript_full.html` | 带时间码全文稿，章节锚点 + 全文搜索 |

用户要求**双格式**（文本版 + 表格版）时，`_table.md` 不可省——`build` 会自动生成，但要检查内容完整。

## 环境依赖

| 依赖 | 说明 |
|---|---|
| Python 3.9+ | 实测 3.13.14 全部依赖可用 |
| 技能自带 venv | 技能目录下 `.venv/`，`scripts/setup_env.py` 自动创建，不污染系统 Python |
| faster-whisper | 本地 ASR 兜底（无字幕时） |
| imageio-ffmpeg | 提供 ffmpeg 二进制（转换 + 抽帧） |
| curl_cffi | **仅 B 站** playurl 需要（TLS 指纹） |
| yt-dlp | **仅 YouTube** 需要 |
| wx-downloader | **仅视频号** 需要；依赖 playwright + 系统已装的 Chrome/Edge |
| faster-whisper small 模型 | 默认 `~/.workbuddy/models/faster-whisper-small/`（483MB，从 hf-mirror 下载） |

```bash
python scripts/setup_env.py            # 一条命令：venv + 依赖 + 模型 + 自检
python scripts/setup_env.py --skip-model   # 只做 YouTube 时可跳过 483MB
python scripts/setup_env.py --check        # 只自检
# 等价手动安装：pip install -r requirements.txt
```

换机器、装依赖失败、模型下载中断的处置办法，全部写在 `INSTALL.md`。

## 关键约束（踩过的坑，详见 references/）

- **YouTube**：timedtext 连续请求会 **429 限流**，必须指数退避（已内置）。
- **YouTube**：`--lang` 默认走原语音 `-orig`，别默认吃机翻轨。
- **B 站**：不要用 yt-dlp（WAF 返 412），走自实现 playurl；未登录最高 480P。
- **视频号**：解析依赖元宝登录态；`all` 默认不弹窗（`--login-mode forbid`），避免 agent 卡死。
- **视频号**：成品文件名是「中文标题_哈希.mp4」，不符合 `video.*` 约定，靠 `.wx-*.json` 记录定位，**不要删这些记录**（去重也靠它们）。
- **裸 11 位 ID 有歧义**：视频号 share id 与 YouTube video id 字符集重合，`detect` 会用 oEmbed 探测消歧，探测失败就明确报错而不是瞎猜。
- **抽帧时间码**：一律查 `frames/index.json`，不要算 `(i-1)*every`。
- **后台任务**：用 Bash 工具的 `run_in_background=true`，`nohup ... &` 起的进程会被回收。
- **模型下载**：走 `hf-mirror.com`（`huggingface.co` 在本环境被代理返 502）；`huggingface_hub` 会留下残缺 `model.bin`，必须 curl 完整下载。
- **HTML 截图自查**：`msedge --headless=new --screenshot=...` 写不进工作区目录（权限拒绝），输出到 `%TEMP%` 再 `ViewImage`。
- **SVG**：不支持 `font` 简写属性、不许给容器写死高度、画完回算 viewBox 高度。

详见 `references/pitfalls.md`（通用 + B 站）、`references/youtube.md`、`references/wxchannels.md`；
页面组件与验收细则见 `references/design.md`。

## 清理

完成后工作目录会残留大量中间文件。
**内容类可删**：`video.*` `audio.*` `audio16k.wav` 及临时 json。
**必须留**：`frames/`（交付物还在引用它）、`outline.json`（可增量修订）、`~/.workbuddy/models/`（模型缓存，复用资产）。
