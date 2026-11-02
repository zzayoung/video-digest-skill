# -*- coding: utf-8 -*-
"""抖音：分享页 → `_ROUTER_DATA` → 无水印播放地址。

链路（为什么不走官方 API）
--------------------------
抖音 Web 的 `/aweme/v1/web/aweme/detail/` 需要 `a_bogus` 签名（JS 混淆 + 时间戳），
自己实现成本高且随版本失效。**分享页**（`iesdouyin.com/share/video/<id>`）是给
浏览器/微信内置浏览器用的，HTML 里直接带 `_ROUTER_DATA`，匿名可读——这是目前
最省事且稳定的入口。

已知边界（务必看 references/douyin.md）
  · 免登录通常只拿得到 720p、且部分作品会降级成「仅封面」
  · 私密 / 好友可见 / 已删除作品一律失败
  · 图文（非视频）作品没有 play_addr，需要另走图集分支（暂不支持）

解析部分写成纯函数，便于离线用夹具测试；联网行为放在 video_info / download。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import lib_short as S
from lib_short import ShortError

PLATFORM = "douyin"

HOSTS = ("douyin.com", "iesdouyin.com")
SHORT_HOSTS = ("v.douyin.com",)

ID_RE = re.compile(r"/(?:video|note|share/video|share/note)/(\d{15,})")
SHORT_URL_RE = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9_\-]+/?")


# ------------------------------------------------------------------ 识别

def is_douyin(target: str) -> bool:
    t = (target or "").strip().lower()
    return bool(t) and (any(h in t for h in HOSTS) or any(h in t for h in SHORT_HOSTS))


def parse_target(target: str, cookie: str | None = None) -> dict:
    """把各种形态归一成 {id, url}。短链会真实跳转一次。"""
    t = (target or "").strip()
    if not t:
        raise SystemExit("[err] 抖音目标为空")

    m = SHORT_URL_RE.search(t)
    if m:
        t = S.resolve(m.group(0), cookie=cookie)

    mid = ID_RE.search(t)
    if not mid:
        raise SystemExit(
            "[err] 认不出抖音作品 ID。请粘贴 App 里的分享链接（含 v.douyin.com 短链）"
            "或 https://www.douyin.com/video/<id>")
    vid = mid.group(1)
    return {"id": vid, "url": f"https://www.douyin.com/video/{vid}"}


# ------------------------------------------------------------------ 解析

def parse_share(html: str) -> dict:
    """从分享页 HTML 解析出统一结构。纯函数，离线可测。

    兼容三种落点：`_ROUTER_DATA`（现行）、`RENDER_DATA`（旧版，URL 编码）、
    以及退化到 og: meta 标签。
    """
    if not html:
        raise ShortError("分享页返回空内容（大概率被风控，试试 --cookie）")

    data = S.json_after(html, "_ROUTER_DATA =") or S.json_after(html, "_ROUTER_DATA=")

    item = None
    if isinstance(data, dict):
        loader = data.get("loaderData") or {}
        # 键名形如 `video_(id)/page`，随版本变化，取第一个含 videoInfoRes 的
        for _k, v in loader.items():
            cand = S.dig(v, "videoInfoRes.item_list.0", "videoInfoRes.aweme_detail")
            if cand:
                item = cand
                break
        if item is None:
            item = S.find_first(data, ("item_list", "aweme_detail"))
            if isinstance(item, list):
                item = item[0] if item else None

    if item is None:
        rd = S.json_after(html, "RENDER_DATA =") or S.json_after(html, "RENDER_DATA=")
        if isinstance(rd, dict):
            item = S.find_first(rd, ("item_list", "aweme_detail"))
            if isinstance(item, list):
                item = item[0] if item else None

    if not isinstance(item, dict):
        # 最后兜底：只有 og:video 时也能拿到无水印直链（部分作品）
        og_video = S.meta_content(html, "og:video") or S.meta_content(html, "og:video:url")
        if not og_video:
            raise ShortError(
                "分享页里没有找到作品数据。常见原因：作品已删除 / 私密 / 需要登录。\n"
                "  排查：加 --cookie \"<浏览器里的 cookie>\" 重试；"
                "或用 --debug 保存 debug_*.html 看实际返回")
        return {
            "aweme_id": "", "title": S.meta_content(html, "og:title") or "",
            "author": "", "desc": S.meta_content(html, "og:description") or "",
            "duration": 0, "width": None, "height": None,
            "play_url": S.normalize_url(og_video), "cover": None,
            "stat": {}, "tags": [], "images": [], "raw_kind": "og",
        }

    video = item.get("video") or {}
    play = video.get("play_addr") or {}
    urls = play.get("url_list") or []
    # playwm 是带水印的；换成 play 拿无水印。这是公开约定，不是破解签名
    urls = [u.replace("/playwm/", "/play/").replace("playwm", "play") for u in urls]
    play_url = S.first_http(urls)
    if not play_url and play.get("uri"):
        play_url = (f"https://aweme.snssdk.com/aweme/v1/play/"
                    f"?video_id={play['uri']}&ratio=1080p&line=0")

    if not play_url:
        images = item.get("images") or []
        if images:
            raise ShortError(
                "这是**图文作品**（不是视频），当前版本只处理视频。"
                "图文分支尚未实现，见 references/douyin.md「已知边界」")
        raise ShortError("没解析到播放地址：作品可能受限（私密/付费/地区）")

    dur_ms = video.get("duration") or item.get("duration") or 0
    cover_urls = (video.get("cover") or {}).get("url_list") \
        or (video.get("origin_cover") or {}).get("url_list") or []
    desc = item.get("desc") or ""
    stats = item.get("statistics") or {}

    return {
        "aweme_id": str(item.get("aweme_id") or ""),
        "title": (item.get("preview_title") or desc.splitlines()[0] if desc else "") or "",
        "author": S.dig(item, "author.nickname", default="") or "",
        "desc": desc,
        "duration": round(dur_ms / 1000.0, 1) if dur_ms else 0,
        "width": video.get("width"),
        "height": video.get("height"),
        "play_url": play_url,
        "cover": S.first_http(cover_urls),
        "stat": {
            "view": stats.get("play_count"),
            "like": stats.get("digg_count"),
            "comment": stats.get("comment_count"),
            "share": stats.get("share_count"),
            "collect": stats.get("collect_count"),
        },
        "tags": re.findall(r"#([^\s#]+)", desc),
        "images": item.get("images") or [],
        "raw_kind": "router_data",
    }


def fetch_share_page(vid: str, cookie: str | None = None, workdir=None) -> str:
    """拉分享页 HTML。先用移动端分享页，失败再退到 PC 详情页。"""
    errors = []
    for url, ua in (
        (f"https://www.iesdouyin.com/share/video/{vid}/", S.UA_MOBILE),
        (f"https://www.douyin.com/video/{vid}", S.UA_DESKTOP),
    ):
        try:
            _code, html = S.http_get(url, referer="https://www.douyin.com/",
                                     cookie=cookie, ua=ua)
            if html and len(html) > 2000:
                if workdir:
                    S.save_debug(html, workdir, f"douyin_{vid}")
                return html
            errors.append(f"{url} → 返回 {len(html or '')} 字节")
        except ShortError as e:
            errors.append(f"{url} → {e}")
    raise ShortError("抖音分享页取不到：" + "；".join(errors))


# ------------------------------------------------------------------ 对外

def video_info(target, workdir=".", video_path=None, cookie=None):
    """归一化成与 lib_yt / lib_wx 同构的 info 字典。"""
    t = parse_target(target, cookie=cookie)
    info = _blank(t)

    try:
        html = fetch_share_page(t["id"], cookie=cookie, workdir=workdir)
        parsed = parse_share(html)
    except ShortError as e:
        info["error"] = str(e)
        if video_path:                      # 已经下过，可以靠本地文件补齐
            parsed = _from_local(video_path)
        else:
            raise

    info.update({k: parsed[k] for k in
                 ("title", "author", "desc", "duration", "width", "height",
                  "stat", "tags")})
    info["thumbnail"] = parsed.get("cover")
    if video_path and Path(video_path).exists():
        info["local_video"] = str(video_path)
        info["bytes"] = Path(video_path).stat().st_size

    try:
        (Path(workdir) / "info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return info


def download(target, workdir=".", cookie=None, referer="https://www.douyin.com/",
             timeout=900):
    """下载视频到 workdir/video.mp4（与其它平台统一命名，省掉上层特判）。"""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    t = parse_target(target, cookie=cookie)

    dest = wd / "video.mp4"
    if dest.exists() and dest.stat().st_size > 102400:
        return {"video": str(dest), "skipped": True, "title": _title_cache(wd),
                "author": _author_cache(wd), "bytes": dest.stat().st_size}

    html = fetch_share_page(t["id"], cookie=cookie, workdir=str(wd))
    parsed = parse_share(html)

    start = wd / "video.part.mp4"
    size = S.download_media(parsed["play_url"], start, referer=referer,
                            cookie=cookie, timeout=timeout)
    start.replace(dest)

    info = _blank(t)
    info.update({k: parsed[k] for k in ("title", "author", "desc", "duration",
                                        "width", "height", "stat", "tags")})
    info["thumbnail"] = parsed.get("cover")
    info["local_video"] = str(dest)
    info["bytes"] = size
    (wd / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"video": str(dest), "skipped": False, "title": parsed["title"],
            "author": parsed["author"], "bytes": size, "url": parsed["play_url"]}


def _blank(t):
    return {
        "platform": PLATFORM,
        "bvid": t["id"], "aid": t["id"], "cid": t["id"],
        "title": "", "owner": "", "owner_mid": "", "pubdate": "",
        "duration": 0, "desc": "", "width": None, "height": None,
        "stat": {}, "tags": [], "categories": [],
        "webpage_url": t["url"], "thumbnail": None,
        "has_subtitle": False,          # 抖音的自动字幕不在视频文件里 → 一律走 ASR
        "subtitle_langs": [],
        "local_video": None,
    }


def _from_local(path):
    import lib_wx
    pr = lib_wx.probe(str(path))
    return {"title": Path(path).stem, "author": "", "desc": "",
            "duration": pr.get("duration") or 0, "width": pr.get("width"),
            "height": pr.get("height"), "stat": {}, "tags": [], "cover": None}


def _title_cache(wd):
    try:
        return json.loads((Path(wd) / "info.json").read_text(encoding="utf-8"))["title"]
    except Exception:
        return ""


def _author_cache(wd):
    try:
        return json.loads((Path(wd) / "info.json").read_text(encoding="utf-8"))["owner"]
    except Exception:
        return ""
