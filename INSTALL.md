# video-digest 安装说明（换机器必读）

这个技能把视频（B 站 / YouTube / 微信视频号 / 本地文件）拆成四件套交付物：
专题页 HTML + 可编辑 SVG 架构图 + 表格版 Markdown + 带时间码全文稿。

本文是**给人看的安装步骤**；`SKILL.md` 是给 agent 看的用法说明。

---

## 0. 前置条件

| 项目 | 要求 | 说明 |
|---|---|---|
| Python | 3.9 – 3.13 | 实测 3.13.14 全部依赖可用 |
| 网络 | 能访问 pypi / hf-mirror | 国内网络无需梯子 |
| 磁盘 | 约 1.2 GB | venv 约 500 MB + small 模型 483 MB |
| 浏览器 | 可选，Chrome / Edge 任一 | **仅视频号扫码登录需要**，其余平台不需要 |
| 腾讯元宝账号 | 可选 | **仅视频号需要**，登录态存在本机，不随包分发 |

只用 YouTube（且视频有字幕）的话，可以 `--skip-model`，磁盘占用降到约 150 MB。

---

## 1. 放到技能目录

把整个 `video-digest/` 文件夹放到位：

```
Windows : %USERPROFILE%\.workbuddy\skills\video-digest\
macOS/Linux : ~/.workbuddy/skills/video-digest/
```

目录结构（不要打散，`run.py` 和 `scripts/` 的相对位置是固定的）：

```
video-digest/
├── SKILL.md              agent 用法说明
├── INSTALL.md            本文
├── requirements.txt      依赖清单
├── run.py                启动器（自动找 venv）
├── scripts/
│   ├── video_digest.py   统一入口
│   ├── setup_env.py      安装器
│   ├── bili_digest.py    转写 / 抽帧 / 文稿
│   ├── make_page.py      outline.json → 四件套
│   ├── lib_bili.py  lib_yt.py  lib_wx.py
└── references/           各平台踩坑记录 + design.md（页面设计规范与验收）
```

---

## 2. 一键安装

```bash
cd ~/.workbuddy/skills/video-digest

# 全套（建 venv → 装依赖 → 下模型 → 自检）
python scripts/setup_env.py

# 只装依赖，不下模型（只做 YouTube 时够用）
python scripts/setup_env.py --skip-model

# 只自检，不动环境
python scripts/setup_env.py --check
```

安装器做的事：

1. 在技能目录建 `.venv`（不污染系统 Python）
2. `pip install -r requirements.txt`，清华源 → 阿里源 → 官方源依次重试，主源缺包时用官方源补齐
3. 从 `hf-mirror.com` 下 `faster-whisper-small` 到 `~/.workbuddy/models/`
4. 跑一次 `doctor`，逐项列出四个平台各自缺什么

耗时主要看网速：依赖约 130 MB（`ctranslate2`、`av`、`onnxruntime`、`playwright` 占大头），
宽带下 2–5 分钟，慢速网络可能 30 分钟以上。全程可中断，重跑会复用已下载的 wheel 和已完成的模型文件。

> Windows 上如果 `python` 是应用商店占位符，改用 `py scripts/setup_env.py` 或写完整路径。

装完自检应该看到：

```
faster_whisper   : OK
imageio_ffmpeg   : OK
PIL              : OK
curl_cffi        : OK
yt_dlp           : OK  (yt-dlp 2025.x.x)
ffmpeg           : .../imageio_ffmpeg/binaries/ffmpeg-...
ffprobe          : 缺失（仅影响本地文件元信息精度…）   ← 可忽略
wx-下载器        : OK 0.1.2
ASR模型          : ~/.workbuddy/models/faster-whisper-small  (486 MB)
=== 全部就绪 ===
```

（`model.bin` 本体 483,546,902 字节，加上 tokenizer 等共约 486 MB。）

---

## 3. 验证：跑一条最小命令

```bash
cd ~/.workbuddy/skills/video-digest

python run.py detect "https://www.bilibili.com/video/BV1t8oAYuEVf"
python run.py info   BV1t8oAYuEVf -o ./work
```

`run.py` 按这个顺序挑解释器，全自动：
`.venv` → WorkBuddy 自带环境（`~/.workbuddy/binaries/python/envs/default`）→ 当前解释器。
想强制指定，设 `VD_PY`。

所以**已经装好依赖的机器不用再建 venv**，直接 `python run.py doctor` 就能跑；
只有换到干净机器才需要第 2 步的 `setup_env.py`。启动时它会打一行 `[info] 使用 ...` 说明挑了哪个。

小技巧：`python` 在有些机器上是 python2 或不存在，那就显式写 `python3` / 完整路径。

---

## 4. 视频号：首次要扫码（只有这一步必须人工）

视频号分享页是 JS 渲染 + 签名校验，纯 HTTP 拿不到播放地址。本技能借
[`wx-downloader`](https://github.com/QinGeneral/wx-downloader)（PyPI 包名 `wx-downloader`，
模块名 `wx_channels_cli`）用腾讯元宝的登录 Cookie 换真实 CDN 地址。

```bash
python run.py wx-login --browser msedge     # Windows 有 Edge 就用这个
python run.py wx-login --browser chrome     # 或 Chrome
python run.py wx-login                      # 不指定 → 用 playwright 默认浏览器
```

- 会弹出浏览器窗口，**用户本人扫码**，agent 不要代劳
- 凭据自动存 `~/.config/wx-channels/auth.json`（Windows 在 `%USERPROFILE%\.config\wx-channels\auth.json`）
- **这个文件不随包分发**：新机器要重新扫一次
- 登录态会过期，报"登录态失效"就重跑 `wx-login`

如果 `wx-login` 报找不到浏览器，装一个 Edge/Chrome 即可，**不需要
`playwright install chromium`**（本技能只用系统已装的浏览器）。

> 未登录也能下载吗？不能。视频号没有匿名可用的解析路径。

---

## 5. 各平台分别需要什么

| 平台 | 依赖 | 是否要模型 | 是否要登录 |
|---|---|---|---|
| YouTube | `yt-dlp` | 有字幕时不需要 | 不需要 |
| B 站 | `curl_cffi` | 需要 | 不需要（未登录 480P） |
| 微信视频号 | `wx-downloader` + 浏览器 | 需要 | **需要扫码** |
| 本地文件 | `imageio-ffmpeg` | 需要 | 不需要 |

缺某一平台的依赖，只影响那个平台，`doctor` 会分开报。
比如没装 `curl_cffi`，B 站下载会失败，但 YouTube 一切正常。

---

## 6. 常见问题

**pip 卡住 / 超时**
安装器默认**先走清华源**（国内快），失败再退阿里、官方源，且已加 `--extra-index-url`
到官方源，所以清华源缺 `wx-downloader` 也能装上。想强制某一家：

```bash
python scripts/setup_env.py --index-url https://mirrors.aliyun.com/pypi/simple
python scripts/setup_env.py --index-url https://pypi.org/simple          # 海外网络
```

**报 `No module named venv` / 无法创建 venv（Linux）**
```bash
sudo apt install python3-venv     # Debian/Ubuntu
```

**模型下载中断**
直接重跑 `python scripts/setup_env.py`，会按已有文件续传、跳过完整文件。
仍然失败就手动下这四个文件到 `~/.workbuddy/models/faster-whisper-small/`：

```
https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/config.json
https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/tokenizer.json
https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/vocabulary.txt
https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/model.bin   # 483,546,902 字节
```

**不要用 `huggingface_hub` 自动下载**：本环境下会留下残缺 `model.bin`（体积对但加载报错）。

**转写很慢**
25 分钟视频、16 线程 CPU、small 模型约 6–9 分钟。**放后台跑**，别在前台等。
GPU 机器可改 `--device cuda`（faster-whisper 支持，需装对应 CUDA 库）。

**视频号下载后文件名是中文 + 哈希**
这是 `wx-downloader` 自己的命名约定，技能靠同目录的 `.wx-*.json` 记录定位与去重。
**不要删这些 json**，删了会重复下载、丢失标题作者。

**想换模型目录**
```bash
python scripts/setup_env.py --model-dir D:/models/faster-whisper-small
# 之后每次调用加 --model D:/models/faster-whisper-small
```

---

## 7. 在 WorkBuddy 里启用

放到 `~/.workbuddy/skills/video-digest/` 后，重启 WorkBuddy（或重开会话），
技能列表里会出现 `video-digest`。之后直接说：

> 把这个视频拆解成专题页 https://www.bilibili.com/video/BVxxxx

agent 会读 `SKILL.md` 按流程走。

---

## 8. 卸载 / 迁移

- 卸载：删掉 `~/.workbuddy/skills/video-digest/` 即可，无系统级残留
- 顺带清理：`~/.workbuddy/models/faster-whisper-small/`（483 MB）、
  `~/.config/wx-channels/`（登录态）
- 迁移到新机器：整包拷过去 → 重跑第 2 步 → 视频号重新扫码
