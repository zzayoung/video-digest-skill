---
name: video-digest
description: 把视频（B站 / YouTube / 微信视频号 / 抖音 / 小红书 / TikTok / 本地文件）拆解成结构化交付物。同一份产出同时提供两条路线——「知识学习线」讲这条视频说了什么，「制作复刻线」讲它怎么拍的、照着怎么做——页面内三档切换（学习 / 复刻 / 对照），逐节互跳。当用户给出视频链接、BV 号、或本地视频文件，说"拆解 / 梳理 / 总结 / 做成专题页 / 分析这个视频 / 这个视频怎么做的 / 我想照着做一个"时使用。流程：识别平台→取媒体与文稿→抽关键帧→写 outline.json→build 生成 HTML + SVG + 表格版 + 全文稿。
agent_created: true
---

# 视频拆解 → 结构化专题页（学习线 × 制作线）

拿到一个视频（链接或本地文件），产出一套**可直接交付**的专题页：HTML 主页面 + 可编辑 SVG 架构图 + 纯表格版 Markdown + 带时间码的完整文稿页。

同一份内容支持**两个读法**，在同一个页面里切换：

| 路线 | 回答的问题 | 产出 |
|---|---|---|
| **学习线** `learn` | 这条视频讲了什么？我怎么理解、记住、用上 | 核心结论、分章讲解、概念表、术语表 |
| **制作线** `replicate` | 它怎么拍的？我照着怎么做出来 | 开场钩子拆解、逐段节拍、镜头清单、可念的口播稿、剪辑参数、发布策略、可勾选执行清单 |

两条线**按章节配对**（`beats[].ref` = `sections[].id`），因此可以互跳、可以并排对照。

## 何时用

- 用户给视频链接 / BV 号 / 本地文件，说"拆解""梳理""整理成专题页""讲透""总结内容"
- 用户说"这个视频怎么做的""我想照着做一个""拆一下它的结构"→ **制作线为主**
- 视频没有字幕、没有简介（很常见），需要靠语音转写还原内容

## 支持的平台

| 维度 | B 站 | YouTube | 微信视频号 | 抖音 | 小红书 | TikTok | 本地文件 |
|---|---|---|---|---|---|---|---|
| 元信息 | 官方 API | yt-dlp | 下载记录 `.wx-*.json` | 分享页 `_ROUTER_DATA` | 笔记页 `__INITIAL_STATE__` | yt-dlp | ffprobe |
| 文稿来源 | 本地 ASR | **优先字幕直取** | 本地 ASR | 本地 ASR | 本地 ASR | 本地 ASR | 本地 ASR |
| 媒体获取 | 自研 playurl | yt-dlp | `wx-downloader` + 登录态 | play_addr（去水印） | `media.stream` | yt-dlp | 无需下载 |
| 前置条件 | 无 | 无 | 扫码一次 | 部分需 cookie | **需带 xsec_token** | 部分需 cookie | 文件存在 |
| 图文作品 | — | — | ✗ 暂不支持 | **✓ 图集** | **✓ 九宫格** | — | **✓ 图片目录** |

> **短视频三站（抖音/小红书/TikTok）的现实**：都没有公开 API，播放地址藏在页面 JSON 或需要签名，
> 匿名请求会被降级。三者统一支持 `--cookie` 传浏览器登录态；图文作品（非视频）当前不支持。
> 具体链路与排错见 `references/douyin.md`、`references/xhs.md`、`references/tiktok.md`。

## 快速开始

**先确认环境**：新机器先读 `INSTALL.md` 装依赖；之后统一用技能根目录的 `run.py`（会自动挑解释器）。

```bash
cd ~/.workbuddy/skills/video-digest

python scripts/setup_env.py          # 首次：venv + 依赖 + 模型 + 自检
python run.py doctor                 # 各平台能力分别列出

# 识别平台（拿不准时）
python run.py detect "https://v.douyin.com/xxxx/"

# 全流程
python run.py all BV1t8oAYuEVf -o ./work --mode replicate      # B 站
python run.py all "https://www.youtube.com/watch?v=xxxx" -o ./work
python run.py all "https://weixin.qq.com/sph/xxxx" -o ./work   # 需先 wx-login
python run.py all "https://v.douyin.com/xxxx/" -o ./work       # 抖音
python run.py all "https://xhslink.com/xxxx" -o ./work         # 小红书
python run.py all "https://vm.tiktok.com/xxxx/" -o ./work      # TikTok
python run.py all "C:/videos/xxx.mp4" -o ./work                # 本地

# 需要登录态时
python run.py all "<链接>" -o ./work --cookie "sessionid=...; web_session=..."

# 渲染交付物
python run.py build ./work/outline.json --transcript ./work/asr_segments.json
python run.py build --schema       # 打印 outline.json 全部字段
```

`--mode` 三个取值：`learn`（默认）、`replicate`、`analysis`（旧名，等同 replicate）。
**它只决定页面默认停在哪条线**——只要 outline 里有 `replicate`，两条线都会生成。

## 交付物生成（核心价值）

**不要手写 HTML。** 内容与呈现解耦：

```
transcript.md + frames/  ──(你：读、分章、提炼)──▶  outline.json
                                                      │
                                        build ────────┴──▶  <slug>.html   ← 双视图
                                                             <slug>.svg
                                                             <slug>_table.md
                                                             transcript_full.html
```

### outline.json 怎么写

先跑 `build --schema` 看全量字段。学习线的最小结构：

```json
{
  "meta": {"slug": "xhs-abc", "title": "...", "author": "...", "platform": "xhs",
           "duration": "00:48", "mode": "replicate", "date": "2026-11-02", "url": "..."},
  "tldr": ["结论一", "结论二"], "thesis": "一句话核心命题",
  "sections": [
    {"id": "s1", "title": "章节名", "t0": 0, "t1": 6, "kicker": "钩子",
     "gist": "一句话概括（进架构图）", "lead": "导语",
     "paras": ["正文，支持 **粗体** 与 `代码`"], "bullets": ["要点"],
     "quote": {"text": "原话", "t": 1},
     "table": {"title": "表题", "head": ["列1","列2"], "rows": [["a","b"]]},
     "cards": [{"h": "小标题", "p": "说明"}],
     "figs": [{"src": "frames/f_0003.jpg", "cap": "图注", "t": 40}]}
  ],
  "pitfalls": [{"title": "踩坑点", "text": "说明", "t": 20}],
  "takeaways": ["可执行结论"],
  "glossary": [{"term": "术语", "def": "解释"}]
}
```

要出**制作线**，再加一个 `replicate` 块（写完页面自动变双视图）：

```json
"replicate": {
  "snapshot":  {"head": ["维度","做法","你该怎么定"], "rows": [["时长/画幅","48 秒竖屏","先控 60 秒内"]]},
  "hook":      {"text": "前 3 秒原话", "why": "为什么有效", "template": "可套用句式"},
  "beats":     [{"ref": "s1", "name": "抛代价", "t0": 0, "t1": 6,
                 "role": "阻止划走", "how": "怎么拍/怎么剪", "shot": "画面·机位",
                 "tip": "复刻要点", "line": "原口播", "xnote": "换个角度的一句话"}],
  "shots":     [{"desc": "画面", "framing": "景别/机位", "dur": "3s", "props": "道具"}],
  "script":    [{"seg": "00 · 开场", "t": "0–6s", "pace": "≈5.4 字/秒", "text": "可直接念的稿"}],
  "assets":    {"器材": ["手机","补光灯"], "场景": ["白墙"], "道具": ["提词器"]},
  "edit":      {"head": ["环节","参数"], "rows": [["字幕","单行 ≤12 字"]]},
  "publish":   {"head": ["项","做法"], "rows": [["标题","损失感 + 数字"]]},
  "checklist": [{"stage": "Day 1", "task": "写结论句", "out": "结论句", "min": 30}],
  "variants":  ["换受众：把「笔记」换成「简历」"]
}
```

写 outline 的硬规则：

1. **`t0`/`t1` 必须来自 `transcript.md` 的真实时间码**，不要估。它们同时决定全文稿页的章节切分和页面上的 🕒 跳转。
2. **`beats[].ref` 必须等于某个 `sections[].id`**：这是两条线的配对键。配不上的章节在制作线上会显示「这一节没有对应动作」——不是错误，但要确认是有意的。
3. **`figs` 的 `t` 用 `frames/index.json` 查**，不要自己算 `(i-1)*every`。
4. **`gist` 一句话**，超过 38 字会被架构图裁掉。
5. 表格优先：凡是「设置值 + 原因」「选项 + 差异」「阶段 + 产出」，一律 `table`，不要写成段落。
6. 作者自己提到的失误 / 警告进 `pitfalls`，单独成节——这是高价值内容。
7. 外文视频：正文用中文，**关键术语保留原文**，首次出现处给释义，并在 `glossary` 登记。
8. `slug` 决定文件名，用 ASCII。

### 两条线怎么写才有价值（关键）

**学习线**要「可迁移」：不是复述视频，而是提炼出作者没明说的框架、条件、边界。
**制作线**要「可执行」：读者看完能直接开拍，不需要再问"那我具体拍什么"。

| 检查 | 不合格 | 合格 |
|---|---|---|
| 制作线是否可执行 | 「注意节奏」 | 「平均 2.4 秒一个切点，共 19 个」 |
| 是否给了原话 | 「开场很抓人」 | 直接引原句 + 说明为什么抓人 |
| 是否可套用 | 「要引起共鸣」 | 给句式模板：`你花了〔投入〕，别人只用〔极短时间〕` |
| 两条线是否互指 | 各写各的 | `xnote` 里写「学习线里这叫损失厌恶，制作线上就是句子位置的问题」 |

`beats[].xnote` 是**双向关联的落点**：用一句话把同一处内容在两个视角下的叫法对上，
读者在对照视图里看到左右两栏时会立刻"哦，原来是同一件事"。

## 图文作品（图集）：另一条媒体形态

抖音图集、小红书九宫格、本地图片目录**不走视频链路**：没有音轨、不转写、不抽帧，
产出是一张图集页。取数入口不用改，同一个 `all`：

```bash
python run.py all "https://www.xiaohongshu.com/explore/<id>?xsec_token=..." -o ./work
python run.py all "https://v.douyin.com/xxxx/" -o ./work
python run.py all "C:/我的图集/" -o ./work          # 本地图片目录（也支持单张图）
```

产出 `images/01.jpg…` + `images_index.json`（含每张的宽高与体积），然后写 outline：

```json
{
  "meta": {"kind": "images", "platform": "xhs", "mode": "replicate"},
  "gallery": {
    "layout": "grid",
    "cover": "images/01.jpg",
    "items": [
      {"src": "images/01.jpg", "role": "封面", "cap": "封面说了什么",
       "note": "学习线：这张在传达什么",
       "design": "制作线：为什么这么排版 / 配色 / 字号"}
    ],
    "recipe": {"head": ["维度", "做法"], "rows": [["画幅", "3:4 竖图统一"]]},
    "copy":   {"title": "标题写法", "body": ["正文结构"], "tags": ["话题"]}
  }
}
```

要点：

- **`note` 与 `design` 是同一张图的两个读法**：前者在「知识学习」显示，后者在「怎么复刻 / 对照」显示。
  这是图集版实现"融会贯通"的方式——不是两段文字，而是同图两解。
- 图集页的灯箱支持 `←` `→` 翻页与 `n / N` 计数，点任意缩略图进入。
- 网格列数按张数自动定：≤2 两列、≤6 三列、更多四列；窄屏统一两列。
- **图集可以完全没有 `sections` / `replicate`**，只有 gallery 也能出页；反过来也成立。
- 视频号图文目前没有可靠的第三方下载路径（下载器只处理视频）——
  可行做法是手动存图后用 `local-images`（`all <目录>`）走同一套图集页。

## 页面形态：三档视图

有 `replicate` 时，页面顶部出现切换条，键盘 `1 / 2 / 3` 也能切：

| 视图 | 内容 |
|---|---|
| **知识学习** `1` | 只显示学习线：结论、骨架图、分章讲解、术语表 |
| **怎么复刻** `2` | 只显示制作线：逐段节拍、钩子、镜头表、口播稿、清单 |
| **对照看** `3` | 同一节左右并排（学习在左、制作在右），窄屏自动堆叠 |

交互细节（都已内置于生成器）：

- 选择记忆在 `localStorage`（按 slug 区分），下次打开还在上次那条线
- 每节标题旁有互跳按钮：学习侧「看这段怎么拍的 ›」，制作侧「‹ 看它讲了什么」
- 目录里配对成功的章节带 `↔` 标记
- 口播稿每段有「复制这段」，镜头表 / 参数表支持整表复制 TSV
- 执行清单可勾选，进度条 + `n / N` 计数，自动存本地

## 架构图

- 不写 `diagram` → 按 `sections` 自动生成竖向骨架流程（最省事，够用）
- 要自定义 → 给 `diagram.nodes` + `edges` 并设 `"style": "manual"`，节点用 `x/y/w/h` 绝对定位
- 产物是**独立 SVG**，主页面用 `<img>` 引用（不是 `<object>`）
- 用户偏好 SVG 是为了能二次编辑：直接改 `.svg` 里的文字，刷新即生效
- **SVG 自带浅色配色**：暗色主题下它是浅色块，属预期，不要 invert

## 视频号专用说明（首次必读）

视频号分享页是 JS 渲染 + 签名校验，纯 HTTP 拿不到播放地址。目前唯一稳定的路子是借
[`wx-downloader`](https://github.com/QinGeneral/wx-downloader)（模块名 `wx_channels_cli`）——
它用**腾讯元宝**的登录 Cookie 换真实 CDN 地址。

```bash
python run.py wx-login --browser msedge    # 用户本人扫码，agent 不要代劳
python run.py wx-status
```

- **只有 `weixin.qq.com/sph/...` 形态的链接可用**
- **`all` 默认 `--login-mode forbid`**，凭据不可用就直接失败，绝不把 agent 卡在等扫码上
- 视频号**没有字幕轨**，一定走 ASR

## 字幕语种怎么选（YouTube）

**默认顺序：原语音 `-orig` > 中文 > 英文。** 因为 `zh-Hans` 轨对日语/英语视频多是机翻轨，
错译会直接污染结论。`--also zh-Hans` 可同时留一份交叉校对，但不要当主依据。

## 怎么把内容"讲透"

1. **读 `transcript.md` 全文**（带时间码），不要只读片段
2. **划章节**：按内容转折点切段，记录起止时间码
3. **提炼骨架**：找出作者的"核心框架"，这是专题页的脊柱，也是 `gist` 的集合
4. **两线分写**：同一节，先写"它说了什么"，再写"它怎么做的"；写不出制作动作的章节留空即可
5. **配关键帧**：查 `frames/index.json` 按时间码挑图，图注标 `🕒 mm:ss`
6. **补踩坑**：作者提到的自身失误 / 警告，单独成节

## 输出物清单

| 文件 | 内容 |
|---|---|
| `<slug>.html` | 主页面：双视图（有 replicate 时）+ 结论 + 架构图 + 章节 + 图 + 表 |
| `<slug>.svg` | 可编辑架构图 |
| `<slug>_table.md` | 纯表格版，**含两条路线**（学习表格 + 复刻方案全套表 + 图集表格） |
| `transcript_full.html` | 带时间码全文稿，章节锚点 + 全文搜索 |

## 验收清单（每次交付前必做）

**通用**

- [ ] `build` 四件套齐全，无报错
- [ ] Edge headless 整页截图看过：首屏、架构图、至少一个表格区
- [ ] 架构图底部不裁、徽章数字是白字
- [ ] 表格 hover 出「复制表格」，点一下真能复制
- [ ] 关键帧能点开放大，`Esc` 能关
- [ ] 主题钮切暗色后无白底残留；刷新后保持
- [ ] 全文稿页搜一个词能过滤并高亮
- [ ] 375px 窄屏不横向溢出
- [ ] 打印预览里没有导航、进度条、浮动按钮

**双视图（有 replicate 时额外做）**

- [ ] 三档切换都能点，`1/2/3` 快捷键有效
- [ ] 学习侧「看这段怎么拍的」跳过去后，落在对应的制作节拍上
- [ ] 制作侧「看它讲了什么」跳回来，落在对应章节
- [ ] 对照视图左右两栏高度不炸、窄屏堆叠正常
- [ ] 勾选两个清单项后刷新页面，勾选还在
- [ ] 口播稿「复制这段」复制的是该段文本，不是整页

截图命令（**输出到 `%TEMP%`**，写工作区目录会被拒）：

```bash
MSEDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
"$MSEDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="C:\\Users\\<你>\\AppData\\Local\\Temp\\page.png" \
  --window-size=1280,2600 "file:///C:/path/to/page.html"
```

## 环境依赖

| 依赖 | 说明 |
|---|---|
| Python 3.9+ | 实测 3.13.14 全部依赖可用 |
| 技能自带 venv | `scripts/setup_env.py` 自动创建；已有环境时可跳过（`run.py` 自动回退） |
| faster-whisper | 本地 ASR（无字幕时） |
| imageio-ffmpeg | ffmpeg 二进制（转码 + 抽帧） |
| curl_cffi | **仅 B 站** playurl（TLS 指纹） |
| yt-dlp | **YouTube / TikTok** |
| wx-downloader | **仅视频号**（依赖 playwright + 系统 Chrome/Edge） |
| faster-whisper small | `~/.workbuddy/models/faster-whisper-small/`（483MB） |

## 关键约束（踩过的坑，详见 references/）

- **B 站**：不要用 yt-dlp（WAF 返 412），走自实现 playurl；未登录最高 480P
- **YouTube**：timedtext 连续请求会 429，必须指数退避（已内置）
- **视频号**：`all` 默认不弹窗（`--login-mode forbid`）；成品名是「中文标题_哈希.mp4」，靠 `.wx-*.json` 定位，**别删这些记录**
- **抖音**：分享页给的是 `playwm`（带水印），改成 `play` 才是无水印；时长字段是**毫秒**
- **小红书**：链接**必须带 `xsec_token`**，只抠 note_id 会失败；`__INITIAL_STATE__` 里有裸 `undefined`，不是严格 JSON
- **TikTok**：签名交给 yt-dlp，失败先 `pip install -U yt-dlp`，别急着改代码
- **图文作品**走图集分支：不转写、不抽帧；`images_index.json` 里带尺寸，选图注时用它
- **图集不凑九宫格**：张数由信息块决定；多出来的图会稀释完读率
- **裸 11 位 ID 有歧义**：视频号 share id 与 YouTube video id 字符集重合，`detect` 会探测消歧
- **抽帧时间码**：一律查 `frames/index.json`
- **后台任务**：用 `run_in_background=true`，`nohup &` 会被回收
- **模型下载**：走 `hf-mirror.com`；`huggingface_hub` 会留下残缺 `model.bin`
- **HTML 截图**：写不进工作区目录，输出到 `%TEMP%` 再 `ViewImage`
- **SVG**：不支持 `font` 简写、不许写死高度、画完回算 viewBox

详见 `references/pitfalls.md`（通用 + B 站）、`references/douyin.md`、`references/xhs.md`、
`references/tiktok.md`、`references/youtube.md`、`references/wxchannels.md`；
页面组件与验收细则见 `references/design.md`。

## 清理

完成后工作目录会残留大量中间文件。
**内容类可删**：`video.*` `audio.*` `audio16k.wav` 及临时 json（含 `debug_*.html`）。
**必须留**：`frames/`、`outline.json`、`~/.workbuddy/models/`。
