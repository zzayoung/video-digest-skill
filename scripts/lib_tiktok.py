# -*- coding: utf-8 -*-
"""TikTok：交给 yt-dlp，元信息失败时退到 oEmbed。

为什么这个平台不自己写解析
--------------------------
TikTok 的播放地址由 `webapp-prime` 接口下发，带 `msToken` / `X-Bogus` / `_signature`
等多重签名，且算法随版本更换。yt-dlp 社区维护这条链路，自己实现只会更快过期。
所以本模块是**薄封装**：协议细节交给 yt-dlp，只做归一化与降级。

降级顺序
  1. yt-dlp 取元信息（含无水印直链、作者、时长、封面）
  2. 失败 → `www.tiktok.com/oembed?url=` 只取标题/作者/封面（拿不到视频，仅够写 outline）
  3. 仍失败 → 明确报错并提示 --cookie（部分区域/私密内容必须登录态）

字幕：TikTok 的自动字幕不总可用，因此**默认走本地 ASR**；若 yt-dlp 报告有字幕轨，
上层可以选择性使用（当前版本未接，见 references/tiktok.md）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import lib_short as S
from lib_short import ShortError

try:
    import yt_dlp
except ImportError:                     # doctor 会给出安装命令
    yt_dlp = None

PLATFORM = "tiktok"

HOSTS = ("tiktok.com",)
SHORT_URL_RE = re.compile(r"https?://(?:vm|vt)\.tiktok\.com/[A-Za-z0-9]+/?")
VIDEO_RE = re.compile(r"/video/(\d{6,})")
MOBILE_RE = re.compile(r"/t/([A-Za-z0-9]+)/?")


def is_tiktok(target: str) -> bool:
    t = (target or "").strip().lower()
    return bool(t) and any(h in t for h in HOSTS)


def parse_target(target: str, cookie: str | None = None) -> dict:
    t = (target or "").strip()
    if not t:
        raise SystemExit("[err] TikTok 目标为空")

    m = SHORT_URL_RE.search(t)
    if m:
        t = S.resolve(m.group(0), cookie=cookie)

    mid = VIDEO_RE.search(t) or MOBILE_RE.search(t)
    vid = mid.group(1) if mid else ""
    if not vid:
        raise SystemExit(
            "[err] 认不出 TikTok 视频 ID。请粘贴完整链接"
            "（tiktok.com/@user/video/<id> 或 vm.tiktok.com 短链）")
    return {"id": vid, "url": t if t.startswith("http") else f"https://www.tiktok.com/@/video/{vid}"}


def _need():
    if yt_dlp is None:
        raise ShortError("缺少 yt-dlp：pip install yt-dlp（doctor 也会提示）")


def _opts(workdir=None, cookie=None, quiet=True):
    o = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noplaylist": True,
        "retries": 3,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": S.UA_DESKTOP, "Referer": "https://www.tiktok.com/"},
    }
    if cookie:
        o["http_headers"]["Cookie"] = cookie
    if workdir:
        o["paths"] = {"home": str(workdir)}
    return o


# ------------------------------------------------------------------ 对外

def video_info(target, workdir=".", video_path=None, cookie=None):
    t = parse_target(target, cookie=cookie)
    info = _blank(t)

    data = None
    if yt_dlp is not None:
        try:
            with yt_dlp.YoutubeDL(_opts(workdir=workdir, cookie=cookie)) as ydl:
                data = ydl.extract_info(t["url"], download=False)
        except Exception as e:                      # noqa: BLE001  yt-dlp 异常类型繁杂
            info["error"] = f"yt-dlp 取元信息失败：{str(e)[:160]}"

    if data:
        info.update({
            "title": data.get("title") or data.get("description", "")[:60],
            "owner": data.get("uploader") or data.get("creator") or "",
            "owner_mid": data.get("uploader_id") or "",
            "duration": int(data.get("duration") or 0),
            "desc": data.get("description") or "",
            "width": data.get("width"), "height": data.get("height"),
            "thumbnail": data.get("thumbnail"),
            "pubdate": _date(data.get("timestamp")),
            "stat": {"view": data.get("view_count"), "like": data.get("like_count"),
                     "comment": data.get("comment_count"),
                     "share": data.get("repost_count")},
            "tags": re.findall(r"#([^\s#]+)", data.get("description") or ""),
            "subtitle_langs": sorted((data.get("subtitles") or {}).keys()),
            "has_subtitle": bool(data.get("subtitles")),
        })
    else:
        meta = _oembed(t["url"], cookie=cookie)
        if meta:
            info.update({
                "title": meta.get("title") or "",
                "owner": meta.get("author_name") or "",
                "thumbnail": meta.get("thumbnail_url"),
                "desc": meta.get("title") or "",
            })
        elif info.get("error"):
            raise ShortError(info["error"] +
                             "\n  常见原因：地区限制 / 私密视频 / 需要登录态。"
                             "试 --cookie \"<浏览器 cookie>\"，或换网络环境")

    if video_path and Path(video_path).exists():
        info["local_video"] = str(video_path)
        info["bytes"] = Path(video_path).stat().st_size
    try:
        (Path(workdir) / "info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return info


def download(target, workdir=".", cookie=None, timeout=900):
    _need()
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    t = parse_target(target, cookie=cookie)

    dest = wd / "video.mp4"
    if dest.exists() and dest.stat().st_size > 102400:
        return {"video": str(dest), "skipped": True,
                "title": _cached(wd, "title"), "author": _cached(wd, "owner"),
                "bytes": dest.stat().st_size}

    info = video_info(target, workdir=str(wd), cookie=cookie)
    opts = _opts(workdir=str(wd), cookie=cookie, quiet=False)
    opts.update({
        "outtmpl": {"default": str(wd / "video.%(ext)s")},
        "format": "mp4/bv*+ba/b",
        "merge_output_format": "mp4",
        "overwrites": True,
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([t["url"]])
    except Exception as e:                          # noqa: BLE001
        raise ShortError(f"TikTok 下载失败：{str(e)[:200]}\n"
                         "  私密/地区限制内容需要 --cookie")

    got = next((p for p in wd.glob("video.*")
                if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")), None)
    if not got:
        raise ShortError("yt-dlp 报告成功但没找到输出文件，检查 workdir 权限")
    if got != dest:
        got.replace(dest)

    return {"video": str(dest), "skipped": False, "title": info.get("title", ""),
            "author": info.get("owner", ""), "bytes": dest.stat().st_size}


# ------------------------------------------------------------------ 小工具

def _oembed(url, cookie=None):
    """oEmbed 不需要签名，能拿到标题/作者/封面——拿不到视频，仅用于兜底。"""
    try:
        _c, body = S.http_get(
            "https://www.tiktok.com/oembed?url=" + S.normalize_url(url),
            cookie=cookie)
        return json.loads(body)
    except Exception:
        return None


def _date(ts):
    if not ts:
        return ""
    import datetime
    try:
        return datetime.date.fromtimestamp(int(ts)).isoformat()
    except Exception:
        return ""


def _blank(t):
    return {
        "platform": PLATFORM,
        "bvid": t["id"], "aid": t["id"], "cid": t["id"],
        "title": "", "owner": "", "owner_mid": "", "pubdate": "",
        "duration": 0, "desc": "", "width": None, "height": None,
        "stat": {}, "tags": [], "categories": [],
        "webpage_url": t["url"], "thumbnail": None,
        "has_subtitle": False,
        "subtitle_langs": [],
        "local_video": None,
    }


def _cached(wd, key):
    try:
        return json.loads((Path(wd) / "info.json").read_text(encoding="utf-8")).get(key, "")
    except Exception:
        return ""
