# 片悟 · 安装与第一次成功

[返回首页](README.md) · [English installation summary](#english-installation-summary)

**先选你的目的：**只看成品，用下方的免安装演示；处理自己的视频，需要 Python 和一个能执行本地命令的 AI 助手。脚本取素材，助手写大纲，生成器排版。

## 先看效果：不用安装任何东西

1. [下载演示 ZIP](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/pianwu-demo.zip)。
2. 解压整个文件夹，双击 `index.html`，用 Chrome、Edge、Safari 或 Firefox 打开。
3. 按 `1 / 2 / 3` 切换学习、制作和对照视图；打开时间码，搜索全文稿。

演示使用原创虚构内容，所有时间码和镜头均为示意。它验证生成器的界面与交付方式，不是远程视频下载或 AI 分析实测。

## 1. 准备环境

| 项目 | 需要什么 |
|---|---|
| Python | 建议 3.12 或 3.13；本次示例验证使用 Python 3.12 |
| AI 助手 | 能读本地文件、加载技能、执行终端命令；写大纲时使用它配置的模型 |
| 网络 | 安装依赖、下载语音模型、读取在线视频需要联网 |
| 磁盘 | 完整环境建议预留数 GB；取决于系统、缓存、模型与视频大小 |
| GPU | 不需要；当前脚本使用 CPU 转写 |
| 浏览器 | 看成品需要；视频号还需浏览器扫码登录 |

已装好依赖的环境可直接自检，不必重复创建环境。没有 Git 也没关系：点击仓库 **Code → Download ZIP**，解压后使用。

## 2. 选择一个 Agent 宿主

以下入口依据各宿主官方文档整理，**不是三个客户端都已完成本仓库端到端实测的承诺**。完整保留 `SKILL.md`、`run.py`、`scripts/`、`references/` 等相对结构。

### WorkBuddy：图形界面导入

1. [下载技能包 video-digest-skill.zip](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/video-digest-skill.zip)。
2. 在 WorkBuddy 打开 **技能 → 添加技能 → 上传技能**，选择这个 ZIP。
3. 确认已安装列表能找到 `video-digest`，新开会话再使用。

技能包的顶层就是 `SKILL.md`，并附完整运行脚本、参考文档、安装说明和示例；不需要自己重新压缩。已检查 ZIP 结构与文件完整性，具体客户端版本的导入行为仍以实际结果为准。

也可在自己的 WorkBuddy 项目中把完整仓库文件放到 `.codebuddy/skills/video-digest/`，然后在该项目内使用。确认技能列表能够找到 `video-digest`，再开始处理素材。

参考：[WorkBuddy 技能](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market) · [项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)。

### Claude Code：用户级安装

macOS / Linux：

```bash
git clone https://github.com/zzayoung/video-digest-skill.git ~/.claude/skills/video-digest
cd ~/.claude/skills/video-digest
```

Windows PowerShell：

```powershell
git clone https://github.com/zzayoung/video-digest-skill.git "$HOME/.claude/skills/video-digest"
Set-Location "$HOME/.claude/skills/video-digest"
```

打开新会话后，可输入 `/video-digest` 或用自然语言请求拆解视频。项目级安装则使用项目内 `.claude/skills/video-digest/`。参考：[官方 Skills 文档](https://code.claude.com/docs/en/skills)。

### Codex：用户级安装

macOS / Linux：

```bash
git clone https://github.com/zzayoung/video-digest-skill.git ~/.agents/skills/video-digest
cd ~/.agents/skills/video-digest
```

Windows PowerShell：

```powershell
git clone https://github.com/zzayoung/video-digest-skill.git "$HOME/.agents/skills/video-digest"
Set-Location "$HOME/.agents/skills/video-digest"
```

项目级目录为 `.agents/skills/video-digest/`。重开会话，确认技能可见后，使用 `$video-digest` 或自然语言调用。参考：[官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

> **后续命令都在实际安装目录执行。** 不同宿主路径不同，以安装位置为准。若目录已存在，请更新现有安装，不要在里面再嵌套一份仓库。

## 3. 先重建内置示例

如果不确定 Python 是否正常，先执行：

```bash
python --version
python scripts/make_page.py examples/starter/outline.json --transcript examples/starter/transcript.json -o ./out/demo
```

macOS / Linux 可改用 `python3`；Windows 可改用 `py`。本步骤只用 Python 标准库，不需要模型或第三方依赖。

成功后，`out/demo/` 中应有 `index.html`、`index.svg`、`index_table.md`、`transcript_full.html` 四个文件。打开 `index.html` 能看到学习与制作视图，就完成了生成器验证。

## 4. 安装真实视频处理环境

在实际技能目录执行，以下两种安装命令**选一种**：

```bash
# 本地视频、无字幕视频：安装依赖与语音模型
python scripts/setup_env.py
```

```bash
# 暂时只处理能取得字幕的 YouTube：跳过语音模型下载
python scripts/setup_env.py --skip-model
```

`--skip-model` **只跳过模型，仍会安装运行依赖**。之后遇到无字幕内容，再运行完整安装。

安装器会在技能目录创建 `.venv`，安装 `requirements.txt`，并将默认模型放在 `~/.workbuddy/models/faster-whisper-small/`；这只是脚本的默认模型位置，其他 Agent 宿主也可使用。首次安装耗时取决于网络，不承诺固定分钟数。

然后执行：

```bash
python run.py doctor
```

`doctor` 会检查依赖、模型和平台连通性，**会联网**。只需要确认本次来源的条件；没有视频号账号不影响本地视频处理。`run.py` 优先选择 `.venv`，其次查找原 WorkBuddy 环境，再尝试当前解释器。

## 5. 处理自己的第一条视频

建议先用一个短中文 MP4。在下面的路径中换成你的文件名，每个视频使用独立输出目录。

Windows 示例：

```powershell
python run.py all "C:/Users/你的用户名/Videos/my-video.mp4" -o ./work/my-first-video
```

macOS / Linux 示例：

```bash
python run.py all "/path/to/my-video.mp4" -o ./work/my-first-video
```

`all` 负责下载（本地文件无需下载）、音频转写与抽帧，得到 `info.json`、`transcript.md`、`asr_segments.json` 与 `frames/`。**到这里还没有 `outline.json`。**

把下面这段发给安装了技能的 AI 助手：

```text
请读取当前技能目录中 work/my-first-video 的文稿、元信息和关键画面。
依据 SKILL.md 的格式编写 work/my-first-video/outline.json。
请同时提供学习线与制作拆解线，章节与制作节拍逐一对应。
时间码取自文稿，画面结论需要有素材支持；额外拍摄建议单独标明。
然后运行 build 并检查成品，告诉我应该打开哪个文件。
```

助手应执行的构建命令为：

```bash
python run.py build ./work/my-first-video/outline.json --transcript ./work/my-first-video/asr_segments.json
```

文件名由大纲 `meta.slug` 决定。只有加入 `replicate` 数据才有制作 / 对照视图；只有提供可读取的文稿 JSON 才会生成全文稿页。纯命令行用户也可参考 [示例大纲](examples/starter/outline.json) 手工填写。

## 6. 其他来源与可选设置

- [首页支持范围](README.md#支持范围) 区分了当前实现与待校准链路。
- YouTube 有字幕时优先使用字幕；无字幕英文素材在 `all` 后加 `--language en`，默认转写语言为 `zh`。
- 短视频希望更密集采样，可以用 `--every 3`，会增加图片数量和处理成本；它仍不是逐镜头自动检测。
- 图文作品使用 `python run.py all "/path/to/images" -o ./work/my-gallery`，得到图片清单后让助手填写 `gallery` 大纲，不走音频转写。
- 抖音 / 小红书 / TikTok 可能需要 `--cookie`，详见对应平台文档。不要把 Cookie 发到公开 Issue。
- 小红书要保留完整分享 URL，不能只拿作品 ID 重新拼接。

### 微信视频号

首次由本人扫码：

```bash
python run.py wx-login --browser msedge
```

也可将 `msedge` 改成 `chrome`。下载链路依赖第三方 [wx-downloader](https://github.com/QinGeneral/wx-downloader)，登录态过期时需要重新登录；这与本地视频处理无关。更多见 [视频号说明](references/wxchannels.md)。

## 7. 卡住时先看这里

| 你看到的情况 | 下一步 |
|---|---|
| `python` 不存在或打开 Microsoft Store | Windows 试 `py`；macOS / Linux 试 `python3`，确认已安装 Python |
| `run.py` 提示缺 `faster-whisper / imageio-ffmpeg` | 在实际技能目录运行 `python scripts/setup_env.py`；只看演示请直接运行 `scripts/make_page.py` |
| 下载依赖很慢 | 等待当前安装完成；可使用下方 `--index-url` 切换镜像，避免同时启动多个安装器 |
| 模型缺失或下载失败 | 重跑完整安装；检查磁盘与模型下载地址的网络可达性 |
| 视频下载失败 | 先检查链接、登录条件和来源支持；用本地文件验证其余链路 |
| `all` 跑完却没有网页 | 还需要让 Agent 写 `outline.json`，再运行 `build` |
| 页面没有制作 / 对照按钮 | 检查大纲是否包含完整的 `replicate` 块 |
| 页面没有全文稿或时间码不能跳转 | 构建时提供有效的 `--transcript` 文件，并保留生成的全文稿 HTML |
| 分享后图表 / 图片丢失 | 把 SVG、全文稿和 `frames/` / `images/` 一起打包，保持目录结构 |

切换依赖源的示例（选一个）：

```bash
python scripts/setup_env.py --index-url https://pypi.org/simple
```

如果使用自定义模型目录：

```bash
python scripts/setup_env.py --model-dir /path/to/models/faster-whisper-small
python run.py all "/path/to/my-video.mp4" -o ./work/my-first-video --model /path/to/models/faster-whisper-small
```

## 8. 数据、费用与分享

本地脚本完成媒体处理和页面渲染。安装、模型下载、平台请求与连通性检查需要网络；视频号还涉及第三方下载器。宿主 Agent 读取文稿与选定画面时，可能将它们发送给你配置的云端模型服务。**本地 ASR 不等于整个流程全离线**。

代码按 MIT 开源；Agent、模型服务和网络资源的费用取决于你的配置。只处理你有权使用的素材。

真实项目建议直接在大纲所在目录构建。指定新 `-o` 目录不会自动复制图片。交付时把 HTML、SVG、全文稿和引用素材整体打包；仓库的 [演示 ZIP](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/pianwu-demo.zip) 就是一个完整示例。

## English installation summary

1. **Try first:** download the demo ZIP linked above, extract it, and open `index.html`. No Python or model is required. Its fictional content and UI are Chinese.
2. **Pick one host:** WorkBuddy supports uploading the ready-made [skill ZIP](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/video-digest-skill.zip) (with SKILL.md at its root), or project-local `.codebuddy/skills/video-digest/`; Claude Code uses `~/.claude/skills/video-digest/`; Codex uses `~/.agents/skills/video-digest/`. The official documentation links above verify discovery conventions, not end-to-end compatibility testing of this repository.
3. Keep the complete repository layout and run commands from the **actual installed skill directory**. Use the location selected for your host.
4. Rebuild the sample with `python scripts/make_page.py examples/starter/outline.json --transcript examples/starter/transcript.json -o ./out/demo`. This uses only the standard library.
5. For real media, run `python scripts/setup_env.py`, then `python run.py doctor`. `--skip-model` skips only the speech model, not dependencies. The default model folder is `~/.workbuddy/models/faster-whisper-small/`, regardless of the host.
6. Run `python run.py all "/path/to/video.mp4" -o ./work/my-first-video --language en` for English speech. Ask your Agent to read the outputs and write `outline.json`, then build with `python run.py build ./work/my-first-video/outline.json --transcript ./work/my-first-video/asr_segments.json`.
7. Share the resulting HTML together with its SVG, transcript and referenced media. Local transcription does not prevent the host Agent from sending content to its configured cloud model.

See [the English README](README.en.md) for the workflow, supported sources and limitations.
