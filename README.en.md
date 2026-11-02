<div align="center">

# Pianwu · 片悟

### Learn the content. Unpack the craft.

Turn videos into learning notes and practical creator playbooks.

[Download the no-install demo](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/pianwu-demo.zip) · [Get started](#get-started) · [Supported sources](#supported-sources) · [简体中文](README.md)

[![MIT License](https://img.shields.io/badge/License-MIT-14556e.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent-Skill-1d7a8c.svg)](SKILL.md)
[![Build smoke](https://github.com/zzayoung/video-digest-skill/actions/workflows/build-smoke.yml/badge.svg)](https://github.com/zzayoung/video-digest-skill/actions/workflows/build-smoke.yml)

</div>

**A saved video is more useful when you can act on it.** Pianwu connects what a video teaches with how it communicates: learning notes on one side, a production breakdown on the other, matched section by section.

It is an **Agent Skill with local Python tools**. Your AI assistant reads the material and writes the content outline; the scripts acquire media, transcribe speech, extract frames and render the pages. The display name is Pianwu; the installation and invocation identifier remains `video-digest`.

## See the result first

| Your goal | What you get |
|---|---|
| Learn from a course or tutorial | Key ideas, chapters, concept tables and timestamp references |
| Study a short video's craft | Narrative structure, shot list, voiceover draft, editing suggestions and checklist |
| Connect meaning and presentation | Learn / Create / Compare views, linked to the same sections |
| Study image posts | Content notes and design breakdowns for the same images |

![Existing renderer example: learning notes beside a creator breakdown](docs/preview-compare.png)

*This existing renderer screenshot shows paired views with illustrative copy, not measured audience results. The download below uses a new fictional 60-second coffee example. Its UI and content are currently in Chinese.*

**No Python, model, account or API key needed:** [download the demo ZIP](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/pianwu-demo.zip), extract the entire folder, then open `index.html`.

Press `1 / 2 / 3` to switch views, follow a section's cross-link, tick a checklist item, or click a timestamp and search the transcript for `侧光` (side lighting).

> If this way of learning from videos is useful to you, a **Star** helps you find the project again. [Feedback](https://github.com/zzayoung/video-digest-skill/issues) on your first run is welcome.

## Get started

### 1. Use your existing AI assistant

**WorkBuddy:** [download the skill ZIP](https://github.com/zzayoung/video-digest-skill/raw/refs/heads/main/docs/video-digest-skill.zip) and use Skills → Add skill → Upload skill. [Other hosts and details →](INSTALL.md#english-installation-summary)

You need an Agent host that can read local files and run Python. See the [installation guide](INSTALL.md#english-installation-summary) for WorkBuddy, Claude Code and Codex entry points. After installing the skill, send:

```text
Use video-digest to break down this video: <URL or local file path>

I want both learning notes and a practical production breakdown.
Read INSTALL.md in the actual installed skill directory and check the environment.
Use the transcript and selected frames to write paired learning/creator sections.
Separate source observations from your creative suggestions; do not invent timecodes or shots.
Write outline.json, build the pages, check their asset/transcript links,
and tell me which HTML file to open.
```

For your first real run, try a short local video you have permission to use. Installation and model downloads take time. Your host's subscription limits or model charges still apply.

Without an Agent host, you can try the prebuilt demo, acquire media and render an outline yourself. The scripts do not automatically call an LLM to write the learning notes.

### 2. Rebuild the demo with Python only

Download or clone the repository and run this from its root. **No `pip install` or model download is required for this example:**

```bash
python scripts/make_page.py examples/starter/outline.json --transcript examples/starter/transcript.json -o ./out/demo
```

Open **`out/demo/index.html`**. Use `python3` on macOS/Linux or `py` on Windows if appropriate.

### 3. Process your own video

From the repository or actual skill directory:

```bash
python scripts/setup_env.py
python run.py all "/path/to/your-video.mp4" -o ./work/my-first-video --language en
```

`--language en` selects English transcription; the default is Chinese (`zh`). YouTube captions, when available, use the caption path instead.

**Next, ask your Agent to read `transcript.md`, `info.json` and `frames/` in that directory and write `outline.json`.** The `all` command prepares the inputs; it does not write this outline.

Then render:

```bash
python run.py build ./work/my-first-video/outline.json --transcript ./work/my-first-video/asr_segments.json
```

The output filename comes from `meta.slug`. Add a `replicate` block for the creator and compare views; set `meta.mode` to `replicate` to open the creator view by default.

## What makes the workflow useful

The learning and creator views share section identifiers. You can move from a concept to the way it is demonstrated, then turn that observation into your own shot list or practice plan.

Production analysis uses the transcript, sampled frames and your Agent's judgment. It is **not automatic detection of every edit or camera setup**. Unobservable equipment, intentions and settings should be labeled as inference or suggestions.

## Supported sources

These are implemented routes, not guarantees that every link will succeed. Access restrictions, region, login state and platform changes can affect acquisition.

| Source | Route | Conditions |
|---|---|---|
| Local video | Local transcription and frame extraction | Recommended for the first real run |
| YouTube | Captions first; local transcription as fallback | Network or anti-bot checks can require additional login conditions |
| Bilibili | Dedicated download route and local transcription | Some content or quality levels require login |
| WeChat Channels | Third-party downloader and local transcription | First-time QR login by the user |
| Douyin | Share-page parsing; video and image-post branches | **Full live calibration pending**; cookies may be needed |
| Xiaohongshu / RED | Page parsing; video and image-post branches | **Full live calibration pending**; preserve the complete share URL and `xsec_token` |
| TikTok | `yt-dlp` and local transcription | Region, login state and extractor version affect availability |
| Local image directory | Image index for an Agent-authored gallery outline | No audio transcription |

CI checks offline fixtures and page rendering. It does not continuously verify live platform availability.

## Files you can keep

| Output | Purpose |
|---|---|
| `<slug>.html` | Main page with learning/creator/compare views, copy controls and checklist |
| `<slug>.svg` | Editable structure diagram |
| `<slug>_table.md` | Markdown tables for continued editing |
| `transcript_full.html` | Searchable timestamped transcript, **generated when transcript JSON is supplied** |

CSS and JavaScript are inline. To share or host a result, keep the HTML, SVG, transcript page and referenced `frames/` or `images/` together with their relative paths intact. Changing the build output directory does not copy media automatically.

## Questions before installing

**Is it free?** The code is MIT-licensed. There is no built-in paid summarization API; your own Agent supplies the reasoning and may use a paid plan or model. The complete demo is free to open.

**Do I need a GPU?** No. The current transcription implementation uses the CPU. Runtime depends on the video, model and hardware; allow several GB of disk space for a full setup.

**Where does my data go?** Media processing and rendering run on the machine executing the scripts. Installation, model downloads, platform requests and connectivity checks use the network. Your host Agent reads the transcript and selected frames to write the outline; this content may be sent to its configured cloud provider. Local transcription does not make the entire Agent workflow offline.

**Can I use only the learning view?** Yes. The creator/compare controls appear when the outline includes `replicate`.

**Does it work in an ordinary chat window?** The host must load the skill, access the material and execute scripts. Pasting a link into a chat window without those capabilities does not run this workflow.

## Documentation and contribution

[Installation / troubleshooting](INSTALL.md) · [Agent instructions](SKILL.md) · [Examples](examples/) · [Architecture](docs/architecture.svg) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

Near-term priorities: real-link platform calibration, outline validation and a batch-results index. Reports with your operating system, source type and a minimal reproducible error are useful. Never include credentials or cookies in public issues.

Only process material you have permission to use. Follow platform rules and respect creators' rights; use the structural lessons to create your own content.

[MIT License](LICENSE) · Video learning notes · Creator breakdown · Agent Skills · Local transcription
