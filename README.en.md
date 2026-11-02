# video-digest — turn any video into a two-track structured HTML page

**An AI Agent Skill that converts a video (Bilibili / YouTube / WeChat Channels / Douyin / Xiaohongshu / TikTok / local file) into a ready-to-ship static page: long-form article + editable SVG diagram + Markdown table version + timestamped transcript.**

Every digest ships **two reading tracks in one page**:

- **Learn** — what the video says, and how to understand it
- **Replicate** — how it was made, and how *you* can make one like it (shot list, ready-to-read script, checkable production checklist)
- **Compare** — the same section side by side, both angles

Works when the video has no subtitles — transcription runs locally with `faster-whisper`.

[![License: MIT](https://img.shields.io/badge/License-MIT-14556e.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%20–%203.13-3776AB.svg)](requirements.txt)

<sub>中文说明 → [README.md](README.md)</sub>

---

## What it is

`video-digest` is not an app. It is a **skill** for AI agents: a `SKILL.md` playbook plus standalone Python scripts.

1. **detect** the platform
2. **fetch** metadata and media
3. **get the transcript** — YouTube subtitles when available, otherwise local ASR
4. **extract keyframes** with a timestamp index
5. **write `outline.json`** — chapters, timestamps, tables, keyframes, plus a `replicate` block
6. **build** the deliverables — HTML (dual view), SVG, table Markdown, transcript page

> **One-line definition (citable):** video-digest converts any video into a timestamped static HTML feature page that offers both a study track and a shot-by-shot replication track, supporting Bilibili, YouTube, WeChat Channels, Douyin, Xiaohongshu, TikTok and local files.

![compare view](docs/preview-compare.png)

## Two tracks, one source of truth

The dual view is not two documents. Each chapter is one `<section>` holding two panes:

```html
<section class="pair" id="s1">
  <div class="pane learn">…what it says…</div>   <!-- teal -->
  <div class="pane repl">…how it was made…</div> <!-- amber -->
</section>
```

`body[data-view]` switches between `learn` / `replicate` / `compare` — so anchors, TOC and the
reading progress bar stay valid in all three views. Chapters pair with production beats by id
(`beats[].ref === sections[].id`), which is what makes the two-way jump reliable.

| Track | Answers | Output |
|---|---|---|
| Learn | What does it say, and why does it hold? | TL;DR, chapters, comparison tables, glossary |
| Replicate | How was it made, how do I do it? | Hook teardown + reusable template, beat-by-beat breakdown, shot list, spoken script, edit settings, publishing plan, checkable checklist |
| Compare | How do the two angles line up? | Side-by-side per section |

## Platforms

| | Bilibili | YouTube | WeChat Channels | Douyin | Xiaohongshu | TikTok | Local |
|---|---|---|---|---|---|---|---|
| Media | custom playurl | yt-dlp | `wx-downloader` + login | page JSON (play_addr) | page JSON (media.stream) | yt-dlp | read directly |
| Transcript | local ASR | **subtitles first** | local ASR | local ASR | local ASR | local ASR | local ASR |
| Login | no | no | one QR scan | sometimes cookie | cookie may be needed | sometimes cookie | no |
| Image posts | — | — | not yet | **carousel** | **grid note** | — | **image folder** |

Honest notes:

- Douyin's share page returns a **watermarked** URL (`playwm`); swapping it to `play` gives the clean one. Duration fields are in milliseconds.
- Xiaohongshu links **must keep `xsec_token`** — rebuilding the URL from the note id alone always fails.
- TikTok signing is delegated to yt-dlp; if it breaks, upgrade yt-dlp before touching our code.
- Image posts (Douyin carousels, Xiaohongshu grid notes, local image folders) take a **separate gallery branch**: no audio, no ASR, no keyframes — the deliverable is a gallery page. Each image carries two readings: `note` for the learn track ("what this one says") and `design` for the replicate track ("why it's laid out this way").

## Output

| File | Contents |
|---|---|
| `<slug>.html` | Dual-view page: learn / replicate / compare |
| `<slug>.svg` | Editable diagram — change the text, refresh, done |
| `<slug>_table.md` | Table-only version, **both tracks** |
| `transcript_full.html` | Timestamped transcript with full-text search |

## Quick start

```bash
git clone https://github.com/zzayoung/video-digest-skill.git ~/.workbuddy/skills/video-digest
cd ~/.workbuddy/skills/video-digest
python scripts/setup_env.py          # venv + deps + ASR model + self-check

python run.py doctor
python run.py all BV1t8oAYuEVf -o ./work --mode replicate
python run.py all "https://v.douyin.com/xxxx/" -o ./work
python run.py all "https://xhslink.com/xxxx" -o ./work
python run.py all "https://vm.tiktok.com/xxxx/" -o ./work
python run.py all "C:/videos/xxx.mp4" -o ./work
python run.py build ./work/outline.json --transcript ./work/asr_segments.json
```

`run.py` picks a working interpreter automatically, so no path juggling.

## FAQ

**Do I have to write both tracks?** No. Without a `replicate` block the page stays a single-view study page, exactly like before.

**Does it need a GPU?** No. CPU with `faster-whisper small` is enough.

**Are Douyin / Xiaohongshu / TikTok stable?** They have no public API and change often. Douyin is parsed from the share page's `_ROUTER_DATA`, Xiaohongshu from `__INITIAL_STATE__`, TikTok via yt-dlp. Anonymous requests get downgraded (720p, or cover only), hence `--cookie`. Parser shapes are pinned by offline fixtures in `tests/test_parsers.py`.

**Where does the data go?** Nowhere. Download, transcribe and keyframe extraction are local.

**Can I restyle the output?** One place: `scripts/make_page.py`. Rebuild old pages to re-align.

## License & fair use

MIT. For personal study and research only — respect each platform's terms and local copyright law.
Do not redistribute downloaded videos or transcripts. **Remaking ≠ copying**: the replicate track
gives you structure and craft; fill it with your own content.

---

<sub>**Keywords**: video to HTML, video notes generator, short-video teardown, video replication, Bilibili transcript, YouTube subtitle extractor, WeChat Channels downloader, Douyin downloader, Xiaohongshu note download, TikTok download, local video transcription, Chinese ASR, faster-whisper, AI agent skill, dual view, outline-driven site generation, static feature page, editable SVG diagram.</sub>
