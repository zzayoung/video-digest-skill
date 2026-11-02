# -*- coding: utf-8 -*-
"""小红书：笔记页 → `__INITIAL_STATE__` → video.media.stream 里的分片地址。

链路要点
--------
1. **短链必须带 `xsec_token`**。新分享链接形如
   `https://www.xiaohongshu.com/explore/<note_id>?xsec_token=AB...&xsec_source=pc_share`，
   缺 token 会被判定为「当前笔记暂时无法浏览」——所以解析时必须先真实跟随跳转，
   保留 query，而不是只抠 note_id 重新拼 URL。
2. 页面里的 `window.__INITIAL_STATE__` 是**非严格 JSON**：值里会出现裸 `undefined`，
   直接 `json.loads` 会炸，需要先替换成 `null`。
3. 视频地址在 `note.video.media.stream.{h264,h265,av1}[0].masterUrl`，
   失败时退到 `backupUrls[]`，再退到 `<meta property="og:video">`。

已知边界
  · 无 cookie 常只能拿到 720p 左右的 `masterUrl`，更高清需要登录态
  · 图文笔记（imageList）没有视频，需要另走图集分支（暂不支持）
  · 部分笔记对未登录用户直接返回登录墙 → 用 --cookie
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import lib_images
import lib_short as S
from lib_short import ShortError

PLATFORM = "xhs"

HOSTS = ("xiaohongshu.com", "xhslink.com")
SHORT_HOSTS = ("xhslink.com",)

NOTE_RE = re.compile(r"/(?:explore|discovery/item|user/profile/[^/]+)/([0-9a-f]{20,32})")
SHORT_URL_RE = re.compile(r"https?://xhslink\.com/[A-Za-z0-9/_\-\.]+")


def is_xhs(target: str) -> bool:
    t = (target or "").strip().lower()
    return bool(t) and any(h in t for h in HOSTS)


def parse_target(target: str, cookie: str | None = None) -> dict:
    """返回 {id, url}。url 保留 xsec_token 等 query。"""
    t = (target or "").strip()
    if not t:
        raise SystemExit("[err] 小红书目标为空")

    m = SHORT_URL_RE.search(t)
    if m:
        t = S.resolve(m.group(0), cookie=cookie)

    mid = NOTE_RE.search(t)
    if not mid:
        raise SystemExit(
            "[err] 认不出小红书笔记 ID。请粘贴完整分享链接"
            "（含 xhslink.com 短链 或 xiaohongshu.com/explore/<id>?xsec_token=...）")
    return {"id": mid.group(1), "url": t}


# ------------------------------------------------------------------ 解析

def _image_urls(note):
    """小红书图集：`imageList[]` 里有 urlDefault / 旧版 url / infoList[].url 多种落点。"""
    out = []
    for im in note.get("imageList") or []:
        if isinstance(im, str):
            u = S.normalize_url(im)
        else:
            cands = [im.get("urlDefault"), im.get("url"), im.get("urlPre")]
            for info in im.get("infoList") or []:
                if isinstance(info, dict):
                    cands.append(info.get("url"))
            u = S.first_http([c for c in cands if c])
        if u:
            out.append(u)
    return out


def parse_share(html: str) -> dict:
    """从笔记页 HTML 解析统一结构。纯函数，离线可测。"""
    if not html:
        raise ShortError("笔记页返回空内容（大概率被风控，试 --cookie）")

    data = (S.json_after(html, "__INITIAL_STATE__ =", undefined_safe=True)
            or S.json_after(html, "__INITIAL_STATE__=", undefined_safe=True))

    note = None
    if isinstance(data, dict):
        detail = S.dig(data, "note.noteDetailMap")
        if isinstance(detail, dict):
            for _k, v in detail.items():
                cand = (v or {}).get("note") if isinstance(v, dict) else None
                if cand:
                    note = cand
                    break
        if note is None:
            note = S.find_first(data, ("noteCard", "note"))

    if not isinstance(note, dict):
        og_video = S.meta_content(html, "og:video") or S.meta_content(html, "og:video:url")
        if not og_video:
            if "登录" in (html or "")[:4000] or "login" in (html or "")[:4000].lower():
                raise ShortError("笔记页要求登录（登录墙）。加 --cookie \"web_session=...\" 重试")
            raise ShortError(
                "笔记页里没找到 __INITIAL_STATE__。常见原因：笔记删除/仅自己可见/"
                "链接缺少 xsec_token（请用 App 里「分享 → 复制链接」的原始链接）")
        return {
            "note_id": "", "title": S.meta_content(html, "og:title") or "",
            "author": "", "desc": S.meta_content(html, "og:description") or "",
            "duration": 0, "width": None, "height": None,
            "play_url": S.normalize_url(og_video), "cover": None,
            "stat": {}, "tags": [], "images": [], "image_urls": [],
            "kind": "video", "type": "video",
        }

    video = note.get("video") or {}
    stream = S.dig(video, "media.stream") or {}
    play_url = None
    for codec in ("h264", "h265", "av1", "h266"):
        arr = stream.get(codec) or []
        for one in arr:
            play_url = S.first_http((one or {}).get("masterUrl"))
            if play_url:
                break
            play_url = S.first_http((one or {}).get("backupUrls"))
            if play_url:
                break
        if play_url:
            break
    if not play_url:
        play_url = S.first_http(S.dig(note, "video.consumer.originVideoKey"))

    image_urls = _image_urls(note)
    kind = "video" if play_url else ("images" if image_urls else "unknown")
    if not play_url and not image_urls:
        raise ShortError("笔记里既没有视频也没有图片，可能是纯文字笔记")

    dur = S.dig(video, "capa.duration") or S.dig(video, "capa.durationMs")
    if dur and dur > 1000:            # 有些版本给毫秒
        dur = dur / 1000.0
    interact = note.get("interactInfo") or {}
    title = note.get("title") or ""
    desc = note.get("desc") or ""

    return {
        "note_id": str(note.get("noteId") or note.get("id") or ""),
        "title": title or (desc.splitlines()[0] if desc else ""),
        "author": S.dig(note, "user.nickname", "user.nickName", default="") or "",
        "desc": desc,
        "duration": round(float(dur or 0), 1),
        "width": S.dig(video, "capa.width") or S.dig(video, "media.video.width"),
        "height": S.dig(video, "capa.height") or S.dig(video, "media.video.height"),
        "play_url": play_url,
        "cover": S.first_http(S.dig(video, "image.firstFrame") or
                              S.dig(note, "imageList.0.urlDefault")),
        "stat": {
            "like": interact.get("likedCount"),
            "collect": interact.get("collectedCount"),
            "comment": interact.get("commentCount"),
            "share": interact.get("shareCount"),
        },
        "tags": [t.get("name") for t in (note.get("tagList") or []) if t.get("name")],
        "image_urls": image_urls,
        "images": note.get("imageList") or [],
        "kind": kind,
        "type": kind,
    }


def fetch_note_page(t: dict, cookie: str | None = None, workdir=None) -> str:
    errors = []
    for ua in (S.UA_DESKTOP, S.UA_MOBILE):
        try:
            _c, html = S.http_get(t["url"], referer="https://www.xiaohongshu.com/",
                                  cookie=cookie, ua=ua)
            if html and len(html) > 2000:
                if workdir:
                    S.save_debug(html, workdir, f"xhs_{t['id']}")
                return html
            errors.append(f"{len(html or '')} 字节")
        except ShortError as e:
            errors.append(str(e))
    raise ShortError("小红书笔记页取不到：" + "；".join(errors))


# ------------------------------------------------------------------ 对外

def video_info(target, workdir=".", video_path=None, cookie=None):
    t = parse_target(target, cookie=cookie)
    info = _blank(t)
    html = fetch_note_page(t, cookie=cookie, workdir=workdir)
    parsed = parse_share(html)

    info.update({k: parsed[k] for k in
                 ("title", "author", "desc", "duration", "width", "height",
                  "stat", "tags")})
    info["kind"] = parsed.get("kind") or "video"
    if info["kind"] == "images":
        info["images_count"] = len(parsed.get("image_urls") or [])
        info["note"] = "图文笔记：无音轨，走图集分支（不转写、不抽帧）"
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


def download(target, workdir=".", cookie=None, referer="https://www.xiaohongshu.com/",
             timeout=900):
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    t = parse_target(target, cookie=cookie)

    dest = wd / "video.mp4"
    if dest.exists() and dest.stat().st_size > 102400:
        return {"video": str(dest), "skipped": True, "title": _cached(wd, "title"),
                "author": _cached(wd, "owner"), "bytes": dest.stat().st_size}

    html = fetch_note_page(t, cookie=cookie, workdir=str(wd))
    parsed = parse_share(html)
    if parsed.get("kind") == "images":
        return _download_images(wd, parsed, cookie, referer, timeout)

    part = wd / "video.part.mp4"
    size = S.download_media(parsed["play_url"], part, referer=referer,
                            cookie=cookie, timeout=timeout)
    part.replace(dest)

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


def _download_images(wd, parsed, cookie, referer, timeout=180):
    """图集下载：落 images/01.jpg…，写 images_index.json。"""
    items, failed = lib_images.download_all(
        parsed.get("image_urls") or [], wd, referer=referer, cookie=cookie,
        timeout=timeout)
    if not items:
        raise ShortError("图集一张都没下下来：直链可能过期，或该笔记需要 cookie")
    meta = {"platform": PLATFORM, "title": parsed.get("title"),
            "author": parsed.get("author"), "desc": parsed.get("desc"),
            "tags": parsed.get("tags")}
    lib_images.write_manifest(wd, items, meta, failed)

    info = _blank({"id": parsed.get("note_id", ""), "url": ""})
    info.update({"kind": "images", "title": parsed.get("title") or "",
                 "owner": parsed.get("author") or "", "desc": parsed.get("desc") or "",
                 "stat": parsed.get("stat") or {}, "tags": parsed.get("tags") or [],
                 "images_count": len(items), "has_subtitle": False})
    (wd / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"kind": "images", "video": None, "images": items, "failed": failed,
            "title": info["title"], "author": info["owner"],
            "bytes": sum(x["bytes"] for x in items)}


def _blank(t):
    return {
        "platform": PLATFORM,
        "bvid": t["id"], "aid": t["id"], "cid": t["id"],
        "title": "", "owner": "", "owner_mid": "", "pubdate": "",
        "duration": 0, "desc": "", "width": None, "height": None,
        "stat": {}, "tags": [], "categories": [],
        "webpage_url": t["url"], "thumbnail": None,
        "has_subtitle": False,     # 小红书的字幕是硬字幕/贴纸，不在文件里 → 走 ASR
        "subtitle_langs": [],
        "local_video": None,
    }


def _cached(wd, key):
    try:
        return json.loads((Path(wd) / "info.json").read_text(encoding="utf-8")).get(key, "")
    except Exception:
        return ""
