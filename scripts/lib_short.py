# -*- coding: utf-8 -*-
"""短视频平台（抖音 / 小红书 / TikTok）共用的取数原语。

为什么单独抽一层
----------------
这三个平台与 B 站/YouTube 的本质区别：
  · 没有公开 API，元信息与播放地址都藏在**分享页 HTML 里的 JSON 字面量**里
  · 短链（v.douyin.com / xhslink.com / vt.tiktok.com）必须真实跟随一次跳转才拿到 id
  · 风控比内容平台严，匿名请求常被降级（只给封面 / 要求登录）

所以这一层只做四件事：HTTP、短链解析、从 HTML 里抠 JSON、下载媒体。
平台差异留在各自的 lib_<平台>.py 里，别混进来。

所有网络请求走 curl（与 bili_digest 一致），因此自动继承系统代理设置。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import bili_digest

UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
             "Mobile/15E148 Safari/604.1")

ACCEPT_HTML = ("Accept: text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8")


class ShortError(RuntimeError):
    """平台取数失败的统一异常（上层捕获后给出人话提示）。"""


# --------------------------------------------------------------------- HTTP

def _cookie_header(cookie: str | None) -> list[str]:
    return ["-b", cookie] if cookie else []


def http_get(url, referer=None, cookie=None, ua=UA_DESKTOP, timeout=25,
             with_url=False):
    """GET 一个页面，返回 (status, text[, final_url])。

    用 curl 而不是 urllib：项目其它链路也走 curl，代理与 TLS 行为一致。
    """
    cmd = ["curl", "-sSL", "--compressed", "--max-time", str(timeout),
           "-A", ua, "-H", ACCEPT_HTML,
           "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8"]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd += _cookie_header(cookie)
    if with_url:
        cmd += ["-w", "\n@@FINAL_URL@@%{url_effective}"]
    cmd.append(url)

    r = bili_digest.run(cmd)
    if r.returncode != 0 and not r.stdout:
        raise ShortError(f"网络请求失败（curl {r.returncode}）：{(r.stderr or '')[:160]}")
    body = r.stdout or ""
    final = ""
    if with_url and "@@FINAL_URL@@" in body:
        body, _, final = body.rpartition("@@FINAL_URL@@")
        final = final.strip()
    code = "200" if body else "000"
    if with_url:
        return code, body, final or url
    return code, body


def resolve(url, cookie=None, timeout=20):
    """跟随短链跳转，返回最终 URL。"""
    cmd = ["curl", "-sS", "-o", os.devnull, "-w", "%{url_effective}", "-L",
           "--max-time", str(timeout), "-A", UA_MOBILE]
    cmd += _cookie_header(cookie)
    cmd.append(url)
    r = bili_digest.run(cmd)
    out = (r.stdout or "").strip()
    if not out.startswith("http"):
        raise ShortError(f"短链解析失败：{url}")
    return out


# ------------------------------------------------------------- HTML → JSON

def json_after(html: str, marker: str, undefined_safe: bool = True):
    """从 `marker`（如 `window._ROUTER_DATA=`) 后面抠出配平的 JSON 对象。

    比正则可靠：字符串里出现 `}` 也不会截断（做了引号与转义状态机）。
    `undefined_safe=True` 时，解析失败会把裸 `undefined` 换成 `null` 重试
    ——小红书与部分抖音页面的 `__INITIAL_STATE__` 是非严格 JSON。
    """
    i = html.find(marker)
    if i < 0:
        return None
    i += len(marker)
    while i < len(html) and html[i] in " \t\r\n=":
        i += 1
    if i >= len(html) or html[i] not in "{[":
        return None

    depth, in_str, esc, start = 0, False, False, i
    quote = ""
    while i < len(html):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in "\"'":
                in_str, quote = True, ch
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    blob = html[start:i + 1]
                    for candidate in (
                        blob,
                        blob.replace("undefined", "null") if undefined_safe else None,
                    ):
                        if candidate is None:
                            continue
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            try:                 # 有些站把 JSON 再转义一层
                                return json.loads(json.loads(f'"{candidate}"'))
                            except Exception:
                                continue
                    return None
        i += 1
    return None


def dig(obj, *paths, default=None):
    """按多条候选路径取值，第一个命中的返回（容忍平台改结构）。"""
    for path in paths:
        cur = obj
        ok = True
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            elif isinstance(cur, list) and key.isdigit() and int(key) < len(cur):
                cur = cur[int(key)]
            else:
                ok = False
                break
        if ok and cur not in (None, "", [], {}):
            return cur
    return default


def find_first(obj, keys, max_depth=8):
    """深度优先找第一个命中的 key（结构不确定时的兜底）。"""
    stack = [(obj, 0)]
    while stack:
        cur, d = stack.pop()
        if d > max_depth:
            continue
        if isinstance(cur, dict):
            for k in keys:
                if k in cur and cur[k] not in (None, "", [], {}):
                    return cur[k]
            stack.extend((v, d + 1) for v in cur.values())
        elif isinstance(cur, list):
            stack.extend((v, d + 1) for v in cur)
    return None


def meta_content(html: str, prop: str):
    """读 <meta property="og:xxx" content="...">，作为结构化数据的兜底。"""
    pat = (rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*'
           rf'content=["\']([^"\']*)["\']')
    m = re.search(pat, html, re.I)
    return m.group(1) if m else None


# ----------------------------------------------------------------- 下载

def download_media(url, dest, referer=None, cookie=None, timeout=900):
    """流式下载媒体到 dest，返回字节数。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-sSL", "--fail", "--max-time", str(timeout),
           "-A", UA_DESKTOP,
           "-H", "Accept: */*",
           "--retry", "3", "--retry-delay", "2",
           # 停滞检测：单次卡住就重来，避免整段静默挂死
           "--speed-limit", "2048", "--speed-time", "45",
           "-o", str(dest)]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd += _cookie_header(cookie)
    cmd.append(url)

    r = bili_digest.run(cmd, timeout=timeout + 60)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 10240:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise ShortError(f"媒体下载失败（curl {r.returncode}）：{(r.stderr or '')[:160]}")
    return dest.stat().st_size


def normalize_url(url: str) -> str:
    """把 `//host/path`、`http://` 等形态统一成 https。"""
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        return "https://" + u[7:]
    return u


def first_http(urls):
    """从候选列表里取第一个 http(s) 地址。"""
    if isinstance(urls, str):
        urls = [urls]
    for u in urls or []:
        u = normalize_url(u)
        if u.startswith("https://"):
            return u
    return None


def save_debug(html, workdir, name):
    """把原始 HTML 落盘，便于联网后校准解析规则。"""
    try:
        p = Path(workdir) / f"debug_{name}.html"
        p.write_text(html, encoding="utf-8")
        return str(p)
    except Exception:
        return None
