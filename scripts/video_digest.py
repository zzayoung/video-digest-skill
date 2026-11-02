#!/usr/bin/env python
"""视频拆解统一入口：B 站 + YouTube + 微信视频号 + 本地文件。

设计取舍（为什么四平台长得不一样）
----------------------------------
| | 元信息 | 文稿来源 | 媒体获取 |
|---|---|---|---|
| B 站 | 官方 API | 必走本地 ASR（无开放字幕接口） | 自研 playurl（yt-dlp 被 WAF 412） |
| YouTube | yt-dlp | **优先字幕直取**，秒级；无字幕才 ASR | yt-dlp |
| 视频号 | 下载产物里的 .wx-*.json | 必走本地 ASR（无字幕轨） | 借 wx-downloader（元宝登录态） |
| 本地文件 | ffprobe | 必走本地 ASR | 无需下载 |

子命令：
  detect     <链接|BV号|文件>          识别平台
  info       <链接|BV号|文件> [-o 目录] 元信息 + 字幕探测 + 评论
  subs       <YouTube链接> [-o 目录]   直取字幕 → asr_segments.json
  download   <链接|BV号> [-o 目录]     下载音视频并转 16k 单声道 wav
  transcribe <音频.wav|视频> [-o json] faster-whisper 本地转写
  frames     <视频文件> [-o 目录]      按间隔抽帧
  transcript <segments.json> [-o md]   生成带时间码文稿
  all        <链接|BV号|文件> [-o 目录] 一键跑完全流程
  build      <outline.json> [-o 目录]  由大纲生成 HTML 专题页 + SVG + 表格版
  wx-login   [--browser msedge]        视频号解析所需的元宝扫码登录
  wx-status                            查看视频号登录态与目录配置
  doctor                               环境自检
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_yt      # noqa: E402
import lib_wx      # noqa: E402
import bili_digest  # noqa: E402  (B 站原链路，复用其 cmd_* )

VIDEO_EXT = (".mp4", ".m4v", ".mov", ".mkv", ".webm")
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")


# ---------------------------------------------------------------- 平台识别

def detect(target):
    """识别目标属于哪个平台。

    顺序很重要：**本地文件 > 视频号 > B 站 > YouTube**。
    先把「能确定」的判掉，最后才用弱特征（11 位 ID）兜 YouTube——
    否则一个 11 位的视频号分享 ID 会被误判成 YouTube 视频 ID
    （视频号 share id 与 YouTube video id 长度、字符集完全重合，无法靠形态区分）。
    """
    t = (target or "").strip()
    if not t:
        raise SystemExit("[err] 目标为空")

    # 1) 本地文件：存在且有媒体后缀
    p = Path(t).expanduser()
    if p.exists() and p.is_file():
        if p.suffix.lower() in VIDEO_EXT + AUDIO_EXT:
            return "local"
        raise SystemExit(f"[err] 不是音视频文件：{p}")

    # 2) 视频号分享链接
    if lib_wx.is_channel(t):
        return "wxchannels"

    # 3) B 站
    if re.match(r"^BV[0-9A-Za-z]{10}$", t) or "bilibili.com" in t or "b23.tv" in t:
        return "bilibili"

    # 4) YouTube 显式链接
    if "youtube.com" in t or "youtu.be" in t:
        return "youtube"

    # 5) 裸 11 位 ID：先假设 YouTube，但必须验证存在，否则提示歧义
    if re.match(r"^[0-9A-Za-z_-]{11}$", t):
        if _yt_exists(t):
            return "youtube"
        raise SystemExit(
            f"[err] 无法确定 `{t}` 指什么：\n"
            "  · YouTube 上不存在这个 ID\n"
            "  · 如果它是视频号分享 ID，请给完整链接：\n"
            f"    https://weixin.qq.com/sph/{t}")

    raise SystemExit(f"[err] 无法识别平台：{t}\n"
                     "  B 站：BV号 / bilibili.com 链接\n"
                     "  YouTube：youtube.com / youtu.be 链接 / 11 位 ID\n"
                     "  视频号：weixin.qq.com/sph/... 分享链接\n"
                     "  本地：音视频文件路径")


def _yt_exists(vid):
    """YouTube oEmbed 探测（只用于消除裸 ID 的歧义，不参与主链路）。"""
    r = bili_digest.run([
        "curl", "-sS", "-m", "12", "-o", os.devnull, "-w", "%{http_code}", "-L",
        f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}"
        "&format=json"])
    return (r.stdout or "").strip() == "200"


# ---------------------------------------------------------------- 小工具

def _find_video(wd, prefer_wx_id=None):
    """在工作目录里找视频文件。

    优先级：video.*（下载器约定名）> .wx-*.json 记录指向的文件 > 体积最大的媒体。
    视频号的成品名是「中文标题_哈希.mp4」，不符合 video.* 约定，所以要靠记录文件。
    """
    wd = Path(wd)
    for name in ("video.mp4", "video.m4s", "video.webm", "video.mkv"):
        p = wd / name
        if p.exists():
            return str(p)
    cands = [p for p in wd.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    if prefer_wx_id:
        for j in wd.glob(".wx-*.json"):
            try:
                d = json.loads(j.read_text(encoding="utf-8"))
            except Exception:
                continue
            if prefer_wx_id in (d.get("source_url") or ""):
                p = Path(d.get("path") or "")
                if p.exists():
                    return str(p)
                if (wd / p.name).exists():
                    return str(wd / p.name)
    if not cands:
        return None
    return str(max(cands, key=lambda x: x.stat().st_size))


def _fmt_dur(sec):
    sec = int(sec or 0)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _step(i, label):
    print("=" * 60)
    print(f"[{i}] {label}")


def _done(t0, extra=""):
    print(f"    ✓ {time.time() - t0:.1f}s" + (f"  {extra}" if extra else ""),
          flush=True)


# ---------------------------------------------------------------- 各子命令

def cmd_detect(a):
    p = detect(a.target)
    print(p)
    if p == "youtube":
        print("video_id:", lib_yt.parse_id(a.target))
    elif p == "wxchannels":
        url, sid = lib_wx.parse_share(a.target)
        print("share_id:", sid)
        print("normalized:", url)
    elif p == "local":
        pr = lib_wx.probe(a.target)
        print("duration:", _fmt_dur(pr.get("duration")),
              f"({pr.get('duration')}s)")
        if pr.get("width"):
            print(f"size: {pr['width']}x{pr['height']}")
    return p


def cmd_info(a):
    wd = Path(a.out)
    wd.mkdir(parents=True, exist_ok=True)
    plat = detect(a.target)

    if plat == "bilibili":
        return bili_digest.cmd_info(argparse.Namespace(
            bvid=a.target, out=str(wd), comment_pages=a.comment_pages))

    if plat == "local":
        return _info_local(a.target, wd)

    if plat == "wxchannels":
        return _info_wx(a.target, wd)

    info = lib_yt.video_info(a.target, workdir=str(wd))
    dur = info["duration"] or 0
    info["duration_human"] = _fmt_dur(dur)
    (wd / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"标题  : {info['title']}")
    print(f"频道  : {info['owner']}")
    print(f"时长  : {info['duration_human']}  ({info['duration']}s)")
    print(f"发布  : {info['pubdate']}")
    print(f"播放  : {info['stat'].get('view')}  点赞: {info['stat'].get('like')}")
    print(f"分辨率: {info['width']}x{info['height']}")
    print(f"字幕  : {info['subtitle_langs'] or '无'}")
    print(f"简介  : {info['desc'][:160] or '(空)'}")

    cs = lib_yt.comments(a.target, workdir=str(wd), limit=20)
    if cs:
        (wd / "comments.json").write_text(
            json.dumps(cs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n热评 {len(cs)} 条 → comments.json")
        for c in cs[:5]:
            print(f"  · [{c['like']}赞] {c['text'][:70]}")
    return info


def _info_local(path, wd):
    p = Path(path).expanduser().resolve()
    pr = lib_wx.probe(str(p))
    info = {
        "platform": "local",
        "bvid": p.stem, "aid": p.stem, "cid": p.stem,
        "title": p.stem,
        "owner": "", "owner_mid": "", "pubdate": "",
        "duration": pr.get("duration") or 0,
        "desc": "", "width": pr.get("width"), "height": pr.get("height"),
        "stat": {}, "tags": [], "categories": [],
        "webpage_url": str(p), "thumbnail": None,
        "has_subtitle": False, "subtitle_langs": [],
        "local_video": str(p),
        "bytes": p.stat().st_size,
    }
    (wd / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"文件  : {p.name}")
    print(f"时长  : {_fmt_dur(info['duration'])}  ({info['duration']}s)")
    print(f"分辨率: {info['width']}x{info['height']}")
    print(f"大小  : {info['bytes'] / 1e6:.1f} MB")
    print(f"编码  : {pr.get('vcodec') or '?'} / {pr.get('acodec') or '?'}")
    print("字幕  : 无（本地文件一律走 ASR）")
    return info


def _info_wx(target, wd):
    url, sid = lib_wx.parse_share(target)
    vid = _find_video(wd, prefer_wx_id=sid)
    info = lib_wx.video_info(target, str(wd), video_path=vid)
    if not vid:
        print(f"分享ID: {sid}")
        print("提示  : 视频号没有公开元信息接口，标题/作者要等下载后从"
              "下载记录里读；先跑 download 或 all")
        return info
    print(f"标题  : {info['title']}")
    print(f"作者  : {info['owner'] or '(未知)'}")
    print(f"时长  : {_fmt_dur(info['duration'])}  ({info['duration']}s)")
    print(f"分辨率: {info['width']}x{info['height']}")
    print(f"大小  : {(info.get('bytes') or 0) / 1e6:.1f} MB")
    print(f"分享ID: {sid}")
    print(f"简介  : {(info['desc'] or '')[:160]}")
    print(f"话题  : {' '.join('#' + t for t in info['tags'][:8])}")
    print("字幕  : 无（视频号无字幕轨 → 必走 ASR）")
    return info


def cmd_subs(a):
    """YouTube 字幕直取：把官方/自动字幕转成与 ASR 同构的 asr_segments.json。"""
    plat = detect(a.target)
    if plat != "youtube":
        raise SystemExit("[err] subs 仅支持 YouTube"
                         "（B 站/视频号/本地文件都无字幕轨，请用 transcribe）")

    wd = Path(a.out)
    wd.mkdir(parents=True, exist_ok=True)
    d = lib_yt.raw_info(a.target, workdir=str(wd))
    langs = [x.strip() for x in (a.lang or "").split(",") if x.strip()] or None
    pick = lib_yt.pick_subtitle(d, langs)
    if not pick:
        raise SystemExit("[err] 该视频没有任何字幕轨道 → 请改用 download + transcribe")

    kind, lang, url = pick
    print(f"[subs] 采用 {kind} 字幕，语种 {lang}（原语音: {lib_yt.orig_lang(d)}）")
    raw = lib_yt.fetch_subtitle_json(url, out=str(wd / f"subtitle_{lang}.json"))
    segs = lib_yt.json3_to_segments(raw, max_chars=a.max_chars)
    out = wd / (a.name or "asr_segments.json")
    out.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
    chars = sum(len(x["t"]) for x in segs)
    print(f"[ok] {len(segs)} 段 / {chars} 字 → {out}")
    print("     字幕直取完成，无需本地 ASR")

    # 附加轨：常用于「原始语种 + 中文翻译」双份留存，便于交叉校对
    for extra in [x.strip() for x in (a.also or "").split(",") if x.strip()]:
        p2 = lib_yt.pick_subtitle(d, [extra])
        if not p2 or p2[1] == lang:
            continue
        try:
            r2 = lib_yt.fetch_subtitle_json(
                p2[2], out=str(wd / f"subtitle_{p2[1]}.json"))
            s2 = lib_yt.json3_to_segments(r2, max_chars=a.max_chars)
            o2 = wd / f"segments_{p2[1]}.json"
            o2.write_text(json.dumps(s2, ensure_ascii=False, indent=1),
                          encoding="utf-8")
            print(f"[ok] 附加轨 {p2[1]}: {len(s2)} 段 → {o2}")
        except Exception as e:
            print(f"  [warn] 附加轨 {extra} 失败: {str(e)[:80]}")
    return segs


def _to_wav(src, wd):
    """统一转 16k 单声道 wav（ASR 的唯一输入形态，避免各平台分支各写一遍）。"""
    ff = bili_digest.ffmpeg_path()
    out = Path(wd) / "audio16k.wav"
    r = bili_digest.run([ff, "-hide_banner", "-loglevel", "error", "-i", str(src),
                         "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                         str(out), "-y"])
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 转换失败: {r.stderr[-300:]}")
    print(f"[ff] audio16k.wav {out.stat().st_size / 1e6:.1f} MB")
    return str(out)


def cmd_download(a):
    wd = Path(a.out)
    wd.mkdir(parents=True, exist_ok=True)
    plat = detect(a.target)

    if plat == "local":
        print(f"[skip] 本地文件无需下载：{a.target}")
        return {"video": str(Path(a.target).resolve()), "skipped": True}

    if plat == "bilibili":
        bili_digest.cmd_download(argparse.Namespace(
            bvid=a.target, out=str(wd), qn=a.qn))
        if getattr(a, "no_video", False):
            print("  [note] B 站链路始终同时下音视频流（合并依赖视频流），"
                  "--no-video 只在 YouTube / 视频号分支生效")
        return None

    if plat == "wxchannels":
        res = lib_wx.download(a.target, str(wd),
                              login_mode=getattr(a, "login_mode", "auto"))
        tag = "已存在，跳过" if res["skipped"] else "下载完成"
        print(f"[wx] {tag}")
        print(f"     标题: {res['title']}")
        print(f"     作者: {res['author'] or '(未知)'}")
        print(f"     文件: {res['video']}")
        print(f"     大小: {res['bytes'] / 1e6:.1f} MB")
        wav = wd / "audio16k.wav"
        if wav.exists() and wav.stat().st_mtime >= Path(res["video"]).stat().st_mtime:
            print(f"[ff] audio16k.wav 已存在（{wav.stat().st_size / 1e6:.1f} MB），跳过转换")
        else:
            _to_wav(res["video"], wd)     # 视频号最终一定要转写
        return res

    res = lib_yt.download(a.target, workdir=str(wd), height=a.height,
                          want_video=not a.no_video)
    print("[dl] 结果:", res)
    if res.get("audio"):
        _to_wav(res["audio"], wd)
    return res


def cmd_all(a):
    """按平台组装链路并顺序执行。

    刻意不写死「第 n/共 m 步」：YouTube 走字幕还是走 ASR 要运行时才能定，
    分母会变。改成 [i] 标签 + 每步计时，永远不会算错。
    """
    wd = Path(a.out)
    wd.mkdir(parents=True, exist_ok=True)
    plat = detect(a.target)
    print("=" * 60)
    print(f"平台    : {plat}")
    print(f"工作目录: {wd.resolve()}")
    print("=" * 60)

    ctx = {"info": {}, "video": None, "segs": wd / "asr_segments.json",
           "via": None}
    steps = []

    # ---------- 各步骤实现 ----------
    def s_local_info():
        ctx["info"] = _info_local(a.target, wd)
        ctx["video"] = str(Path(a.target).resolve())

    def s_info():
        ctx["info"] = cmd_info(argparse.Namespace(
            target=a.target, out=str(wd), comment_pages=3))

    def s_wx_download():
        res = cmd_download(argparse.Namespace(
            target=a.target, out=str(wd), qn=a.qn, height=a.height,
            no_video=False, login_mode=getattr(a, "login_mode", "auto")))
        ctx["video"] = res["video"]

    def s_wx_info():
        ctx["info"] = _info_wx(a.target, wd)

    def s_download():
        cmd_download(argparse.Namespace(
            target=a.target, out=str(wd), qn=a.qn, height=a.height,
            no_video=False, login_mode=getattr(a, "login_mode", "auto")))
        ctx["video"] = _find_video(wd)

    def s_subs():
        try:
            cmd_subs(argparse.Namespace(
                target=a.target, out=str(wd), lang=a.lang, also=a.also,
                max_chars=90, name="asr_segments.json"))
            ctx["via"] = "subs"
            return True
        except SystemExit as e:
            print(f"    → 无可用字幕（{e}），回退本地 ASR")
            return False

    def s_asr():
        if not (wd / "audio16k.wav").exists():
            src = ctx["video"] or _find_video(wd)
            if not src:
                raise RuntimeError("找不到可用于转写的媒体文件")
            _to_wav(src, wd)
        bili_digest.cmd_transcribe(argparse.Namespace(
            audio=str(wd / "audio16k.wav"), out=str(ctx["segs"]),
            model=a.model, threads=a.threads, language=a.language,
            prompt=a.prompt, duration=(ctx["info"] or {}).get("duration") or 0))
        ctx["via"] = "asr"

    def s_frames():
        src = ctx["video"] or _find_video(wd)
        if not src:
            print("    （无可用视频文件，跳过抽帧）")
            return
        bili_digest.cmd_frames(argparse.Namespace(
            video=src, out=str(wd / "frames"), every=a.every,
            width=getattr(a, "width", 960)))

    def s_transcript():
        bili_digest.cmd_transcript(argparse.Namespace(
            segments=str(ctx["segs"]), out=str(wd / "transcript.md")))

    # ---------- 组装链路 ----------
    # YouTube 的「字幕 vs ASR」要跑起来才知道，所以前两步（元信息 + 字幕探测）
    # 就地执行，剩下的重活再进统一循环，保证 [i] 编号严格递增不重复。
    done = 0
    if plat == "youtube":
        done += 1
        _step(done, "元信息")
        t0 = time.time(); s_info(); _done(t0)

        done += 1
        _step(done, "字幕探测（命中则跳过 ASR）")
        t0 = time.time()
        if s_subs():
            _done(t0, "走字幕直取，省掉模型下载与转写")
            if not a.no_frames:
                steps += [("下载视频（仅抽帧用）", s_download), ("抽帧", s_frames)]
        else:
            _done(t0, "无字幕轨 → 改走本地 ASR")
            steps += [("下载音视频", s_download),
                      ("抽帧", s_frames),
                      ("本地 ASR 转写", s_asr)]
        steps += [("生成带时间码文稿", s_transcript)]
    elif plat == "local":
        steps = [("读取本地文件", s_local_info),
                 ("抽帧", s_frames),
                 ("本地 ASR 转写", s_asr),
                 ("生成带时间码文稿", s_transcript)]
    elif plat == "wxchannels":
        steps = [("下载视频号视频", s_wx_download),
                 ("读取元信息", s_wx_info),
                 ("抽帧", s_frames),
                 ("本地 ASR 转写", s_asr),
                 ("生成带时间码文稿", s_transcript)]
    else:  # bilibili
        steps = [("元信息", s_info),
                 ("下载音视频", s_download),
                 ("抽帧", s_frames),
                 ("本地 ASR 转写", s_asr),
                 ("生成带时间码文稿", s_transcript)]

    # ---------- 执行 ----------
    i = done
    for label, fn in steps:
        if a.no_frames and (label.startswith("抽帧")
                            or label.startswith("下载视频（仅抽帧")):
            print(f"[skip] {label}（--no-frames）")
            continue
        i += 1
        _step(i, label)
        t0 = time.time()
        fn()
        _done(t0)

    print("=" * 60)
    print(f"全部完成 → {wd.resolve()}")
    print(f"文稿方式: {ctx['via'] or '未生成'}")
    for f in ("info.json", "asr_segments.json", "transcript.md", "frames"):
        p = wd / f
        if p.exists():
            if p.is_dir():
                # 只数帧图；目录里还有 index.json，别把它算成"帧"
                extra = f"（{len(list(p.glob('f_*.jpg')))} 帧）"
            else:
                kb = p.stat().st_size / 1e3
                extra = f"（{kb:.0f} KB）" if kb >= 10 else f"（{kb:.1f} KB）"
            print(f"  · {f} {extra}")
    mode_desc = ("梳理理解学习版（learn）" if a.mode == "learn"
                 else "方法论反向拆解版（analysis）")
    print(f"\n下一步：读 transcript.md，按【{mode_desc}】写 outline.json，"
          "再跑 `build` 生成专题页")
    print("  （outline 结构见 SKILL.md「交付物生成」一节）")


OUTLINE_SCHEMA = r"""
outline.json 字段说明（build 的输入）
════════════════════════════════════════════════════════════

最小骨架
--------
{
  "meta": {"slug": "wx-XXXX", "title": "...", "author": "...",
           "platform": "wxchannels", "duration": "25:41",
           "date": "2026-10-30", "url": "...", "mode": "learn"},
  "thesis": "全文核心命题，一句话",
  "tldr": ["结论一", "结论二", "结论三"],
  "sections": [ { ...见下... } ],
  "pitfalls":  [{"title": "...", "text": "...", "t": 120}],
  "takeaways": ["可执行结论"],
  "glossary":  [{"term": "...", "def": "..."}]
}

meta（必填）
------------
slug       产物文件名基名。必须 ASCII（如 wx-<share_id> / BV<id>），中文会出错
title      页面主标题
subtitle   副标题，可选
author     作者 / UP 主
platform   bilibili | youtube | wxchannels | local（决定页面上的平台标签）
duration   "mm:ss"，可选
date       "YYYY-MM-DD"，可选
url        原视频链接，可选
mode       learn（默认）| analysis

sections[i]（章节）
-------------------
id         锚点 id，建议 s1…sN
title      章节名
kicker     小标签（如「背景」「机制」）
t0 / t1    起止秒数，必须来自 transcript.md 的真实时间码
gist       一句话概括，进架构图的副标题，超过 38 字会被裁
lead       导语段，可选
paras      ["正文段落"]，支持 **粗体** 与 `代码`
bullets    ["要点"]
quote      {"text": "原话", "src": "谁说的", "t": 305}
table      {"title": "表题", "head": ["列1","列2"], "rows": [["a","b"]]}
cards      [{"h": "小标题", "p": "说明"}]
figs       [{"src": "frames/f_0003.jpg", "cap": "图注", "t": 40}]

  · t0/t1 决定全文稿页的章节切分与页面 🕒 跳转，不要估
  · figs 的 t 查 frames/index.json，不要用 (i-1)*every 推算
  · 「设置值 + 原因」「选项 + 差异」「阶段 + 产出」这类结构一律用 table

diagram（架构图，可选）
----------------------
不写 → 按 sections 自动生成竖向骨架流程（最省事，够用）
要自定义：
  "diagram": {"title": "图题", "style": "manual",
              "nodes": [{"id":"n1","label":"...","sub":"...","x":0,"y":0,
                         "w":320,"h":74,"tone":"n","t0":0,"t1":180}],
              "edges": [{"from":"n1","to":"n2","label":"..."}]}
  style=manual 时 x/y/w/h 为绝对坐标；tone 可选 n/ok/warn/bad

pitfalls / takeaways / glossary
-------------------------------
pitfalls   [{"title": "踩坑点", "text": "说明", "t": 120}]  ← 作者自己的失误/警告，高价值
takeaways  ["可执行结论"]                                  ← 页面末尾的结论卡
glossary   [{"term": "术语", "def": "解释"}]                ← 外文术语首次出现处要给释义

analysis（仅 mode=analysis 时）
-------------------------------
{"positioning": "...", "skeleton": "...",
 "methods": ["..."],
 "prep": {"环节": ["要准备什么"]},
 "template": [{"part": "段落", "how": "做法"}]}

产物
----
<slug>.html            专题页主文件
<slug>.svg             可编辑架构图（改 svg 里的文字，刷新页面即生效）
<slug>_table.md        纯表格版（文本 + 表格双格式交付）
transcript_full.html   带时间码全文稿页（传了 --transcript 才有）
"""


def cmd_build(a):
    """由 outline.json 渲染 HTML 专题页 + SVG + 表格版 md + 全文稿页。"""
    if getattr(a, "schema", False) or not a.outline:
        print(OUTLINE_SCHEMA)
        return 0
    import make_page
    return make_page.build(a.outline, a.out or None,
                           name=a.name, transcript=a.transcript)


def cmd_wx_login(a):
    print("[wx] 正在打开元宝登录页，请用微信扫码或手机号登录…")
    out = lib_wx.login(browser=a.browser, timeout=a.timeout)
    print(out.strip())
    st = lib_wx.status()
    print(f"[wx] 本地凭据: {st.get('auth')}")
    print(f"     下载目录: {st.get('download_dir')}")
    print("     提示：这个目录是 wx-downloader 自己的约定；"
          "本 skill 用 all/download 时会用 --output 覆盖到工作目录。")


def cmd_wx_status(a):
    st = lib_wx.status()
    ok, ver = lib_wx.available()
    print(f"wx-downloader : {'OK ' + ver if ok else '不可用 ← ' + ver}")
    for k, v in st.items():
        print(f"{k:<12}: {v}")


def cmd_doctor(a):
    """环境自检。四个平台的能力分别查，缺谁不影响谁。"""
    ok = True
    print("=== 环境自检（B站 + YouTube + 视频号 + 本地） ===\n")
    print(f"Python  : {sys.version.split()[0]}  ({sys.executable})")

    for mod, pip in [("faster_whisper", "faster-whisper"),
                     ("imageio_ffmpeg", "imageio-ffmpeg"),
                     ("PIL", "Pillow"),
                     ("curl_cffi", "curl_cffi"),
                     ("yt_dlp", "yt-dlp")]:
        try:
            if mod == "yt_dlp":
                import yt_dlp
                print(f"{mod:<17}: OK  (yt-dlp {yt_dlp.version.__version__})")
            else:
                __import__(mod)
                print(f"{mod:<17}: OK")
        except ImportError:
            need = mod in ("curl_cffi",)
            print(f"{mod:<17}: 缺失 → pip install {pip}"
                  + ("  (仅 B 站 playurl 需要)" if need else ""))
            if mod != "curl_cffi":
                ok = False

    try:
        ff = bili_digest.ffmpeg_path()
        print(f"ffmpeg  : {ff}")
    except Exception as e:
        print(f"ffmpeg  : 缺失 → {e}")
        ok = False

    import shutil as _sh
    probe_exe = _sh.which("ffprobe")
    print("ffprobe : " + (probe_exe or
          "缺失（仅影响本地文件元信息精度，会退化用 ffmpeg -i 解析）"))

    wx_ok, wx_msg = lib_wx.available()
    print(f"wx-下载器: {'OK ' + wx_msg if wx_ok else '不可用 ← ' + wx_msg}")
    if wx_ok:
        try:
            st = lib_wx.status()
            print(f"           登录态: {st.get('auth')}")
        except Exception as e:
            print(f"           登录态: 读取失败 {str(e)[:60]}")

    print("\n--- 连通性 ---")
    r = bili_digest.run([
        "curl", "-sS", "-m", "25", "--retry", "3", "--retry-all-errors",
        "-o", os.devnull,
        "-w", "%{http_code}", "-L", "https://www.youtube.com/"])
    code = (r.stdout or "").strip()
    print(f"YouTube : HTTP {code}"
          + ("" if code == "200" else "  （非 200 只影响 YouTube 链路，其余平台不受影响）"))

    r = bili_digest.run([
        "curl", "-sS", "-m", "20", "--retry", "3", "--retry-all-errors",
        "-o", os.devnull,
        "-w", "%{http_code}", "-L", "https://weixin.qq.com/"])
    code = (r.stdout or "").strip()
    print(f"视频号  : HTTP {code}")

    md = Path(a.model) if a.model else bili_digest.DEFAULT_MODEL
    if md.exists():
        size = sum(f.stat().st_size for f in md.glob("*") if f.is_file())
        print(f"ASR模型 : {md}  ({size / 1e6:.0f} MB)")
    else:
        print(f"ASR模型 : 未下载 → {md}")
        print("         YouTube 有字幕时不需要；B站/视频号/本地文件必用")

    print("\n" + ("=== 全部就绪 ===" if ok else "=== 有缺失项，按提示安装 ==="))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(
        description="视频拆解工具（B站 + YouTube + 微信视频号 + 本地文件）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("detect", help="识别平台")
    s.add_argument("target"); s.set_defaults(f=cmd_detect)

    s = sub.add_parser("info"); s.add_argument("target")
    s.add_argument("-o", "--out", default=".")
    s.add_argument("--comment-pages", type=int, default=3)
    s.set_defaults(f=cmd_info)

    s = sub.add_parser("subs", help="YouTube 字幕直取（跳过 ASR）")
    s.add_argument("target"); s.add_argument("-o", "--out", default=".")
    s.add_argument("--lang", default="",
                   help="偏好语种，逗号分隔；留空=自动（原语音 > 中 > 英），可用 orig 占位")
    s.add_argument("--also", default="",
                   help="额外再抓一条字幕轨留存（如 zh-Hans），用于交叉校对")
    s.add_argument("--max-chars", type=int, default=90)
    s.add_argument("--name", default="asr_segments.json")
    s.set_defaults(f=cmd_subs)

    s = sub.add_parser("download"); s.add_argument("target")
    s.add_argument("-o", "--out", default=".")
    s.add_argument("--qn", type=int, default=80)
    s.add_argument("--height", type=int, default=720)
    s.add_argument("--no-video", action="store_true", help="只下音频（ASR 用）")
    s.add_argument("--login-mode", choices=["auto", "forbid"], default="auto",
                   help="视频号：auto=缺凭据时弹浏览器扫码；forbid=绝不弹窗")
    s.set_defaults(f=cmd_download)

    s = sub.add_parser("transcribe"); s.add_argument("audio")
    s.add_argument("-o", "--out", default="asr_segments.json")
    s.add_argument("--model", default=None)
    s.add_argument("--threads", type=int, default=0,
                   help="0=自动（CPU 核数，上限 16）")
    s.add_argument("--language", default="zh")
    s.add_argument("--prompt", default="")
    s.add_argument("--duration", type=float, default=0)
    s.set_defaults(f=bili_digest.cmd_transcribe)

    s = sub.add_parser("frames"); s.add_argument("video")
    s.add_argument("-o", "--out", default="frames")
    s.add_argument("--every", type=int, default=20)
    s.add_argument("--width", type=int, default=960,
                   help="帧图最大宽度，0=原始尺寸")
    s.set_defaults(f=bili_digest.cmd_frames)

    s = sub.add_parser("transcript"); s.add_argument("segments")
    s.add_argument("-o", "--out", default="transcript.md")
    s.set_defaults(f=bili_digest.cmd_transcript)

    s = sub.add_parser("build", help="outline.json → HTML 专题页 + SVG + 表格版")
    s.add_argument("outline", nargs="?", help="outline.json 路径；配合 --schema 可省略")
    s.add_argument("-o", "--out", default=None, help="输出目录，默认 outline 所在目录")
    s.add_argument("--name", default=None, help="产物基名，默认取 outline 里 meta.slug")
    s.add_argument("--schema", action="store_true", help="打印 outline.json 字段说明")
    s.add_argument("--transcript", default=None,
                   help="asr_segments.json 路径，给了就一并生成 transcript_full.html")
    s.set_defaults(f=cmd_build)

    s = sub.add_parser("wx-login", help="视频号：元宝扫码登录")
    s.add_argument("--browser", default=None,
                   choices=[None, "auto", "chrome", "chromium", "msedge"])
    s.add_argument("--timeout", type=int, default=300)
    s.set_defaults(f=cmd_wx_login)

    s = sub.add_parser("wx-status", help="视频号：登录态与目录")
    s.set_defaults(f=cmd_wx_status)

    s = sub.add_parser("doctor", help="环境自检")
    s.add_argument("--model", default=None); s.set_defaults(f=cmd_doctor)

    s = sub.add_parser("all"); s.add_argument("target")
    s.add_argument("-o", "--out", default=".")
    s.add_argument("--qn", type=int, default=80)
    s.add_argument("--height", type=int, default=720)
    s.add_argument("--every", type=int, default=20)
    s.add_argument("--width", type=int, default=960, help="帧图最大宽度，0=原始尺寸")
    s.add_argument("--model", default=None)
    s.add_argument("--threads", type=int, default=0)
    s.add_argument("--language", default="zh")
    s.add_argument("--lang", default="", help="YouTube 字幕偏好语种，留空=自动")
    s.add_argument("--also", default="", help="额外字幕轨（如 zh-Hans）")
    s.add_argument("--prompt", default="",
                   help="ASR 领域词提示，能显著降低专有名词错字")
    s.add_argument("--no-frames", action="store_true")
    s.add_argument("--login-mode", choices=["auto", "forbid"], default="forbid",
                   help="视频号：agent/批量场景默认 forbid，避免卡在等扫码")
    s.add_argument("--mode", choices=["learn", "analysis"], default="learn")
    s.set_defaults(f=cmd_all)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
