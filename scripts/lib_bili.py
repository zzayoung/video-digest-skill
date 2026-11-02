"""B 站开放接口封装：元信息 / 字幕探测 / wbi 签名 / 播放地址 / 流下载。

实测要点（2026-09 验证）：
- api.bilibili.com 在本环境偶发 SSL 握手失败，所有请求必须带重试。
- 更狠的情况：整个 *.bilibili.com 在 SNI 层被掐断（代理隧道 200 建好，
  但 TLS 握手立刻失败）。此时 *.hdslb.com / *.bilivideo.com 仍然可达。
  解法：解析出 IP，用「https://<ip>/path + -H "Host: 原域名" + -k」直连，
  SNI 里不带 bilibili.com 字样即可通过。_curl 已内置该降级链路。
- yt-dlp 走代理会被 B 站 WAF 返回 412，不要用；改为自取 playurl。
- 登录态（--cookies-from-browser edge）在本环境无法读 Edge cookie 库，直接放弃。

playurl 四道闸门（2026-09 实测，缺一不可，详见 get_playurl 文档）：
  1) TLS 指纹 —— 必须 curl_cffi impersonate="chrome124"，普通 curl 过不去
  2) 应用层头 —— sec-ch-ua / sec-fetch-* / Origin（见 CFFI_HEADERS）
  3) 凭证挑战 —— 首次只回 v_voucher，带它二次请求才给 dash
  4) qn 降级   —— 未登录 qn=80/64 静默返回空 dash，须退到 qn=32（480P）
"""
import json
import time
import socket
import hashlib
import urllib.parse
import subprocess
import os
from pathlib import Path

try:
    from curl_cffi import requests as _creq
    _HAVE_CFFI = True
except Exception:
    _HAVE_CFFI = False

MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 57, 3, 31, 43, 5, 62, 56, 61, 44, 12, 60,
    39, 54, 10, 34, 51, 4, 25, 6, 63, 20, 30, 13, 33, 22, 41, 50, 24, 38, 55,
    19, 14, 45, 40, 16, 35, 26, 58, 49, 7, 29, 28, 48, 11, 59, 17, 36, 42, 21,
    37, 52, 1, 27, 0, 9,
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_API = "https://api.bilibili.com"


class BiliError(RuntimeError):
    pass


def _resolve(host, cache={}):
    """解析域名为 IP 列表（用于绕过 SNI 封锁）。结果进程内缓存。"""
    if host in cache and cache[host]:
        return cache[host]
    ips = []
    try:
        for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    cache[host] = ips
    return ips


def _curl_try(url, out=None, referer="https://www.bilibili.com/", cookie=None,
              timeout=40, tries=2, insecure=False, host=None, extra=None):
    """单次（带重试）curl。insecure/host 用于 IP 直连模式。"""
    cmd = ["curl", "-sS", "-m", str(timeout), "--retry", "2",
           "--retry-all-errors", "-L"]
    if insecure:
        cmd.append("-k")
    cmd += ["-H", f"User-Agent: {UA}",
            "-H", f"Referer: {referer}",
            "-H", "Accept: application/json, text/plain, */*",
            "-H", "Accept-Language: zh-CN,zh;q=0.9"]
    if host:
        cmd += ["-H", f"Host: {host}"]
    if cookie:
        cmd += ["-H", f"Cookie: {cookie}"]
    if extra:
        cmd += list(extra)
    if out:
        cmd += ["-o", str(out)]
    cmd.append(url)

    last = ""
    for _ in range(tries):
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            if out:
                p = Path(out)
                if p.exists() and p.stat().st_size > 0:
                    return True
            else:
                return r.stdout
        last = (r.stderr or "").strip()
        time.sleep(1.5)
    raise BiliError(f"curl failed: {last}")


def _curl(url, out=None, referer="https://www.bilibili.com/", cookie=None,
          timeout=40, retries=8, extra=None):
    """带重试的 curl。本环境直连 api.bilibili.com 会间歇性 SSL 失败，重试即可。

    两级降级：
      1) 正常域名请求（快路径，绝大多数情况够用）
      2) 若 SNI 被掐，改用 解析IP + Host头 + -k 直连
    """
    # 阶段 1：正常请求
    try:
        return _curl_try(url, out, referer, cookie, timeout,
                         tries=min(3, retries), extra=extra)
    except BiliError:
        pass

    # 阶段 2：IP + Host + -k 绕过 SNI 封锁
    u = urllib.parse.urlparse(url)
    origin = f"{u.scheme}://{u.netloc}"
    lasts = []
    for ip in _resolve(u.hostname)[:5]:
        alt = url.replace(origin, f"{u.scheme}://{ip}", 1)
        try:
            print(f"  [SNI 降级] 改用 IP 直连 {ip} (Host: {u.hostname})", flush=True)
            return _curl_try(alt, out, referer, cookie, timeout, tries=2,
                             insecure=True, host=u.hostname, extra=extra)
        except BiliError as e:
            lasts.append(str(e))
    raise BiliError(f"curl failed (含 IP 直连降级): {lasts[-1] if lasts else '?'}")


def _get_json(url, **kw):
    txt = _curl(url, **kw)
    try:
        return json.loads(txt)
    except Exception as e:
        raise BiliError(f"non-JSON response: {txt[:200]}") from e


# 浏览器指纹头：B 站 2025 起对 playurl 做指纹风控，缺 sec-fetch-*/sec-ch-ua
# 会触发 v_voucher 闸门且不返回 dash。curl_cffi impersonate 负责 TLS 指纹，
# 这些 HTTP 头负责应用层指纹。二者齐备才能拿到 dash。
CFFI_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.bilibili.com",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


def _cffi_get_json(url, workdir=".", cookie=None, host=None, referer=None):
    """用 curl_cffi（浏览器 TLS 指纹）+ 应用层指纹头取 JSON。
    内置 IP 直连降级（应对 SNI 封锁）。专门用于 playurl 等被风控的接口。"""
    if not _HAVE_CFFI:
        raise BiliError("curl_cffi 未安装，请执行 pip install curl_cffi")
    ck = cookie_of(workdir) if cookie is None else cookie
    if isinstance(ck, str):
        cookies = {}
        for kv in ck.split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, _, v = kv.partition("=")
                cookies[k.strip()] = v.strip()
    else:
        cookies = ck
    u = urllib.parse.urlparse(url)
    hh = dict(CFFI_HEADERS)
    hh["Host"] = host or u.hostname
    if referer:
        hh["Referer"] = referer
    bases = [url]
    for ip in _resolve(u.hostname)[:3]:
        bases.append(url.replace(f"{u.scheme}://{u.netloc}",
                                 f"{u.scheme}://{ip}", 1))
    last = ""
    for cand in bases:
        try:
            r = _creq.get(cand, headers=hh, cookies=cookies,
                          impersonate="chrome124", timeout=30, verify=False)
            return r.json()
        except Exception as e:
            last = str(e)
    raise BiliError(f"cffi request failed: {last}")


def get_buvid(workdir="."):
    """获取 buvid3/buvid4。结果缓存在 workdir/.buvid.json，一次会话内复用。"""
    cache = Path(workdir) / ".buvid.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    d = _get_json(f"{_API}/x/frontend/finger/spi")["data"]
    info = {"b3": d["b_3"], "b4": d["b_4"]}
    cache.write_text(json.dumps(info), encoding="utf-8")
    return info


def cookie_of(workdir="."):
    b = get_buvid(workdir)
    return f"buvid3={b['b3']}; buvid4={b['b4']}"


def get_wbi_keys(workdir="."):
    """wbi 签名密钥来自 nav 接口的 wbi_img（与 buvid 无关）。
    取出 img_url / sub_url 的文件名（去 .png）拼接成 64 位原始串。"""
    cache = Path(workdir) / ".wbi_keys.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    d = _get_json(f"{_API}/x/web-interface/nav", cookie=cookie_of(workdir))
    img = ((d.get("data") or {}).get("wbi_img") or {})
    if not img.get("img_url"):
        raise BiliError("nav 未返回 wbi_img，签名不可用")

    def key(u):
        return u.split("/")[-1].replace(".png", "")

    raw = key(img["img_url"]) + key(img["sub_url"])
    if len(raw) < 64:
        raise BiliError(f"wbi raw key 长度异常: {len(raw)}")
    info = {"raw": raw}
    cache.write_text(json.dumps(info), encoding="utf-8")
    return info


def _mixin_key(raw):
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def _enc(v):
    return urllib.parse.quote(str(v), safe="").replace(
        "!", "%21").replace("'", "%27").replace("(", "%28").replace(
        ")", "%29").replace("*", "%2A")


def wbi_sign(url, workdir="."):
    """给 URL 追加 wts + w_rid 两个参数。"""
    mk = _mixin_key(get_wbi_keys(workdir)["raw"])

    u = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(u.query))
    params["wts"] = int(time.time())
    query = "&".join(f"{_enc(k)}={_enc(params[k])}" for k in sorted(params))
    params["w_rid"] = hashlib.md5((query + mk).encode()).hexdigest()
    qs = "&".join(f"{_enc(k)}={_enc(params[k])}" for k in sorted(params))
    return f"{u.scheme}://{u.netloc}{u.path}?{qs}"


def video_info(bvid, workdir="."):
    """视频元信息：标题 / UP 主 / 时长 / cid / 简介 / 是否有字幕。"""
    d = _get_json(f"{_API}/x/web-interface/view?bvid={bvid}")
    if d.get("code") != 0:
        raise BiliError(f"view failed: {d.get('message')}")
    data = d["data"]

    # 字幕探测
    sub = data.get("subtitle") or {}
    raw_sub = ""
    try:
        p = _get_json(f"{_API}/x/player/v2?bvid={bvid}&cid={data['cid']}",
                      cookie=cookie_of(workdir),
                      referer=f"https://www.bilibili.com/video/{bvid}/")
        lst = ((p.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        if lst:
            su = lst[0].get("subtitle_url") or ""
            if su:
                if su.startswith("//"):
                    su = "https:" + su
                raw_sub = _curl(su)
    except Exception:
        pass

    return {
        "bvid": bvid,
        "aid": data.get("aid"),
        "cid": data.get("cid"),
        "title": data.get("title"),
        "owner": (data.get("owner") or {}).get("name"),
        "owner_mid": (data.get("owner") or {}).get("mid"),
        "pubdate": data.get("pubdate"),
        "duration": data.get("duration"),
        "desc": data.get("desc") or "",
        "width": (data.get("dimension") or {}).get("width"),
        "height": (data.get("dimension") or {}).get("height"),
        "stat": data.get("stat") or {},
        "has_subtitle": bool(raw_sub),
        "subtitle_json": raw_sub,
        "pages": data.get("pages") or [],
    }


def _playurl_raw(bvid, cid, workdir=".", qn=80, voucher=None):
    """单次 playurl 请求（curl_cffi 指纹 + IP 直连降级）。"""
    q = {"bvid": bvid, "cid": cid, "qn": qn, "fnval": 16,
         "fourk": 1, "otype": "json"}
    if voucher:
        q["v_voucher"] = voucher
    url = f"{_API}/x/player/wbi/playurl?" + urllib.parse.urlencode(q)
    signed = wbi_sign(url, workdir)
    hh = dict(CFFI_HEADERS)
    hh["Referer"] = f"https://www.bilibili.com/video/{bvid}/"
    return _cffi_get_json(signed, workdir=workdir, referer=hh["Referer"])


def get_playurl(bvid, cid, workdir=".", qn=80):
    """取 dash 播放地址。返回 (video_url, audio_url, meta)。

    B 站 2025 起 playurl 有三道闸门，缺一不可：
      1) TLS 指纹  —— curl_cffi impersonate="chrome124"
      2) 应用层头  —— sec-ch-ua / sec-fetch-* / Origin（见 CFFI_HEADERS）
      3) 凭证挑战  —— 首次请求只回 v_voucher，须带上它二次请求才给 dash
      4) qn 降级   —— 未登录态 qn=80/64 会被静默降级成空 dash，
                      必须退到 qn=32（480P）才真正返回流
    本函数按 qn 序列 (传入值 → 64 → 32 → 16) + voucher 二次握手自动打通。
    """
    if not _HAVE_CFFI:
        raise BiliError("curl_cffi 未安装，请执行 pip install curl_cffi")

    order = [qn] + [q for q in (80, 64, 32, 16) if q != qn]
    voucher = None
    data = None

    for attempt_qn in order:
        # 第一拍：可能只拿到 voucher
        d = _playurl_raw(bvid, cid, workdir, attempt_qn, voucher)
        dd = d.get("data") or {}
        if not dd.get("dash"):
            v = dd.get("v_voucher")
            if v and v != voucher:
                voucher = v          # 二次握手
                d = _playurl_raw(bvid, cid, workdir, attempt_qn, voucher)
                dd = d.get("data") or {}
        if dd.get("dash"):
            data = dd
            print(f"  [playurl] qn={attempt_qn} 成功 quality={dd.get('quality')}",
                  flush=True)
            break
        print(f"  [playurl] qn={attempt_qn} 无 dash，降级中…", flush=True)
        time.sleep(0.8)

    if data is None:
        raise BiliError("playurl 全档位失败（风控或会员视频）")

    dash = data.get("dash") or {}
    vids = dash.get("video") or []
    auds = dash.get("audio") or []
    if not vids or not auds:
        raise BiliError("no dash stream (可能是付费/会员视频)")

    # 优先 avc1（兼容性最好），取最高分辨率
    vids_avc = [v for v in vids if v.get("codecs", "").startswith("avc1")]
    pool = vids_avc or vids
    v = max(pool, key=lambda x: (x.get("width", 0), x.get("bandwidth", 0)))
    a = max(auds, key=lambda x: x.get("bandwidth", 0))

    meta = {
        "quality": data.get("quality"),
        "accept_quality": data.get("accept_quality"),
        "video": f'{v.get("width")}x{v.get("height")}',
        "video_bandwidth": v.get("bandwidth"),
        "audio_bandwidth": a.get("bandwidth"),
    }
    return v["baseUrl"], a["baseUrl"], meta


def download_stream(url, out, referer, workdir=".", retries=6, timeout=600):
    """断点续传下载 m4s。内置「IP+Host+-k」降级与停滞检测。

    停滞检测很关键：默认 curl 会一直等到 -m 超时，曾出现单次卡 15 分钟、
    累计 36 分钟零产出的情况。--speed-limit/--speed-time 让卡住的流
    30 秒内失败并切下一个候选地址。
    """
    p = Path(out)
    u = urllib.parse.urlparse(url)
    origin = f"{u.scheme}://{u.netloc}"
    ck = cookie_of(workdir)
    extra = ["-C", "-", "--retry", "2", "--retry-all-errors",
             "--speed-limit", "1024", "--speed-time", "30",
             "-H", f"Cookie: {ck}"]

    # 候选地址：正常域名 → 逐个 IP 直连
    cands = [(url, False, None)]
    for ip in _resolve(u.hostname)[:4]:
        cands.append((url.replace(origin, f"{u.scheme}://{ip}", 1),
                      True, u.hostname))

    last = ""
    for i in range(retries):
        for curl_url, insecure, host in cands:
            try:
                _curl_try(curl_url, out=out, referer=referer, timeout=timeout,
                          tries=1, insecure=insecure, host=host, extra=extra)
                if p.exists() and p.stat().st_size > 0:
                    return p
            except BiliError as e:
                last = str(e)
        print(f"  [下载重试 {i+1}/{retries}] {Path(out).name} "
              f"{p.stat().st_size if p.exists() else 0} bytes", flush=True)
        time.sleep(3)
    raise BiliError(f"download failed: {out} ({last})")


def comments(aid, pages=3, ps=20):
    """取热门评论（sort=2）。有时能补充视频要点。"""
    out = []
    for pn in range(1, pages + 1):
        try:
            d = _get_json(f"{_API}/x/v2/reply?pn={pn}&ps={ps}&type=1&oid={aid}&sort=2")
            for r in (d.get("data") or {}).get("replies") or []:
                out.append({
                    "user": (r.get("member") or {}).get("uname"),
                    "like": r.get("like"),
                    "text": (r.get("content") or {}).get("message", ""),
                })
        except Exception:
            break
        time.sleep(0.5)
    return out
