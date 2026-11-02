"""微信视频号封装：分享链接解析 / 调用 wx-downloader 下载 / 元信息提取。

为什么单独成一个模块
--------------------
B 站和 YouTube 都能靠「链接 → 官方 API / yt-dlp」拿到元信息与媒体地址；
视频号**没有对外开放的解析接口**，分享页是 JS 渲染 + 签名校验的，
纯 HTTP 请求拿不到播放地址。

目前工程上唯一稳定可复用的路子是借第三方工具 `wx-downloader`
（PyPI 包名 `wx-downloader`，模块名 `wx_channels_cli`）：
它用**腾讯元宝**的登录 Cookie 去请求解析接口，把 `weixin.qq.com/sph/...`
还原成真实 CDN 地址。所以本模块本质是一个**薄封装 + 结果归一化层**，
不做任何破解，也不保存用户凭据（凭据由 wx-downloader 自己管，
落在 ~/.config/wx-channels/auth.json）。

登录态说明（重要）
------------------
视频号解析**必须**有有效的元宝登录态。首次使用需要人工扫码：

    python video_digest.py wx-login

此后 `download()` 默认 `login="auto"`：
  · 本地凭据有效 → 直接下，不弹窗
  · 本地凭据缺失/过期 → 自动拉起浏览器让用户扫码（会阻塞等待）
批量/无人值守场景传 `login="forbid"`（等价 CLI 的 --no-login），
凭据不可用就直接失败，不会把 agent 卡在等扫码上。

依赖：wx-downloader 本身依赖 playwright + 一个 Chromium 系浏览器
（Chrome / Edge / Playwright Chromium 均可）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 视频号分享链接：https://weixin.qq.com/sph/<id>
# id 是大小写字母数字混合，长度不固定（实测 11 位，但不要写死）
SHARE_RE = re.compile(
    r"https?://(?:www\.)?weixin\.qq\.com/sph/([0-9A-Za-z_-]+)", re.I)

MODULE_NAME = "wx_channels_cli"

# 这些后缀视作视频号解析产物
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")


class WxError(RuntimeError):
    pass


# ------------------------------------------------------------------ 链接解析

def is_channel(target):
    """判断 target 是不是视频号分享链接（容忍分享参数 / 前后空格）。"""
    return bool(SHARE_RE.search((target or "").strip()))


def parse_share(target):
    """抽出 (规范化链接, share_id)。会丢掉 ?from=... 之类的分享参数。

    微信分享出来的链接常带一堆 tracking 参数，且同一视频不同入口参数不同，
    统一剥掉才能让「同一视频」在下载去重时被认成同一个。
    """
    t = (target or "").strip()
    m = SHARE_RE.search(t)
    if not m:
        raise WxError(f"不是视频号分享链接: {t}\n"
                      "  期望形态：https://weixin.qq.com/sph/XXXXXXXX")
    sid = m.group(1)
    return f"https://weixin.qq.com/sph/{sid}", sid


# ------------------------------------------------------------------ CLI 定位

def cli_cmd():
    """返回调用 wx-downloader 的命令前缀（list），找不到就报错。

    优先级：
      1) 环境变量 WX_DOWNLOADER_BIN（指定可执行文件全路径）
      2) 当前解释器能 import wx_channels_cli → [python, -m wx_channels_cli]
         （最稳，不依赖 PATH，也不受 venv 激活状态影响）
      3) PATH 上的 wx-downloader 可执行文件
    """
    env_bin = os.environ.get("WX_DOWNLOADER_BIN")
    if env_bin and Path(env_bin).exists():
        return [env_bin]
    try:
        import wx_channels_cli  # noqa: F401
        return [sys.executable, "-m", MODULE_NAME]
    except ImportError:
        pass
    exe = shutil.which("wx-downloader") or shutil.which("wx-downloader.exe")
    if exe:
        return [exe]
    raise WxError(
        "未找到 wx-downloader。请任选一种安装方式：\n"
        f'  "{sys.executable}" -m pip install wx-downloader '
        "-i https://pypi.org/simple\n"
        "  uv tool install wx-downloader\n"
        "或用环境变量 WX_DOWNLOADER_BIN 指向可执行文件。"
    )


def _run(args, timeout=None):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r


def available():
    """给 doctor 用：返回 (是否可用, 说明)。"""
    try:
        cmd = cli_cmd()
    except WxError as e:
        return False, str(e).splitlines()[0]
    r = _run(cmd + ["--version"], timeout=90)
    ver = (r.stdout or "").strip().splitlines()
    if r.returncode == 0 and ver:
        return True, ver[-1]
    err = (r.stderr or r.stdout or "").strip().splitlines()
    return False, err[-1] if err else f"退出码 {r.returncode}"


# ------------------------------------------------------------------ 登录态

def status():
    """读本地登录态（只反映本地文件，服务端有效性要到下载时才知）。"""
    cmd = cli_cmd()
    r = _run(cmd + ["status"], timeout=90)
    txt = (r.stdout or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        raise WxError(f"wx-downloader status 输出无法解析: {txt[:200]}")


def login(browser=None, timeout=300):
    """拉起浏览器让用户扫码。会阻塞到登录成功或超时。"""
    cmd = cli_cmd() + ["login", "--timeout", str(int(timeout))]
    if browser:
        cmd += ["--browser", browser]
    r = _run(cmd, timeout=timeout + 120)
    out = (r.stdout or "").strip() + (r.stderr or "").strip()
    if r.returncode != 0:
        raise WxError(f"登录失败: {out[-300:] or '退出码 ' + str(r.returncode)}")
    return out


# ------------------------------------------------------------------ 元信息

def _record_for(video_path):
    """视频号下载时 wx-downloader 会在成品目录写 `.wx-<hash>.json` 去重记录，
    里面带 title 以外的全部元信息（author / description / bytes）。

    成品文件名本身就是「标题_链接哈希.mp4」，标题 = 文件名去掉 `_<hash>` 后缀。
    """
    p = Path(video_path)
    rec = {}
    for j in p.parent.glob(".wx-*.json"):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            continue
        if Path(d.get("path") or "").name == p.name:
            rec = d
            break
    # 成品名形如「标题_-<hash>.mp4」（hash 前有时带 `-`），要连分隔符一起剥掉
    title = p.stem
    title = re.sub(r"_[-‐-―]?[0-9a-f]{8,}$", "", title)
    return {
        "title": rec.get("title") or title,
        "author": rec.get("author") or "",
        "desc": rec.get("description") or "",
        "source_url": rec.get("source_url") or "",
        "bytes": rec.get("bytes") or (p.stat().st_size if p.exists() else 0),
    }


def video_info(target, workdir=".", video_path=None):
    """归一化成和 lib_yt.video_info 同构的元信息，方便上层共用模板。"""
    url, sid = parse_share(target)
    wd = Path(workdir)
    info = {
        "platform": "wxchannels",
        "bvid": sid,
        "aid": sid,
        "cid": sid,
        "title": "",
        "owner": "",
        "owner_mid": "",
        "pubdate": "",
        "duration": 0,
        "desc": "",
        "width": None,
        "height": None,
        "stat": {},
        "tags": re.findall(r"#([^\s#]+)", ""),
        "categories": [],
        "webpage_url": url,
        "thumbnail": None,
        "has_subtitle": False,      # 视频号一律没有字幕轨 → 必走 ASR
        "subtitle_langs": [],
        "local_video": None,
    }
    if video_path and Path(video_path).exists():
        rec = _record_for(video_path)
        info.update({
            "title": rec["title"],
            "owner": rec["author"],
            "desc": rec["desc"],
            "local_video": str(video_path),
        })
        info["tags"] = re.findall(r"#([^\s#]+)", rec["desc"])
        pr = probe(video_path)
        info["duration"] = pr.get("duration") or 0
        info["width"] = pr.get("width")
        info["height"] = pr.get("height")
        info["bytes"] = rec["bytes"]
        try:
            (wd / "info.json").write_text(
                json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return info


def probe(path):
    """ffprobe 读时长/分辨率。ffmpeg 用 skill 里统一的那份（imageio-ffmpeg）。"""
    import bili_digest                       # 复用其 ffmpeg 定位逻辑
    ff = bili_digest.ffmpeg_path()
    out = {}
    # ffprobe 查找顺序：PATH > ffmpeg 同目录 > 放弃（退化到 ffmpeg -i 解析）
    # 注意 imageio-ffmpeg 只带 ffmpeg 一个二进制，同目录下通常没有 ffprobe，
    # 所以 PATH 优先，能命中系统装的完整 ffmpeg 套件。
    probe_exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe") or str(
        Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    if Path(probe_exe).exists():
        r = bili_digest.run([probe_exe, "-v", "error", "-print_format", "json",
                             "-show_format", "-show_streams", str(path)])
        if r.returncode == 0:
            try:
                d = json.loads(r.stdout)
            except Exception:
                d = {}
            out["duration"] = int(float((d.get("format") or {}).get("duration") or 0))
            for s in d.get("streams") or []:
                if s.get("codec_type") == "video":
                    out["width"] = s.get("width")
                    out["height"] = s.get("height")
                    out["vcodec"] = s.get("codec_name")
                elif s.get("codec_type") == "audio":
                    out["acodec"] = s.get("codec_name")
            return out
    # 没有 ffprobe 就退回用 ffmpeg -i 的 stderr 里解析 Duration
    r = bili_digest.run([ff, "-hide_banner", "-i", str(path)])
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)", r.stderr or "")
    if m:
        h, mi, se = (int(x) for x in m.groups())
        out["duration"] = h * 3600 + mi * 60 + se
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr or "")
    if m:
        out["width"], out["height"] = int(m.group(1)), int(m.group(2))
    return out


# ------------------------------------------------------------------ 下载

def download(target, workdir=".", login_mode="auto", timeout=None):
    """调 wx-downloader 把视频号视频下到 workdir。

    参数 login_mode：
      auto   —— 缺凭据时自动弹浏览器扫码（交互场景默认）
      forbid —— 缺凭据直接失败，绝不弹窗（批量 / agent 场景用 --no-login）
      never  —— 同 forbid，语义别名

    返回 dict(video=<mp4 路径>, bytes=..., title=..., author=..., skipped=bool)
    """
    url, sid = parse_share(target)
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    cmd = cli_cmd() + ["download", url, "--json", "--output", str(wd)]
    if str(login_mode).lower() in ("forbid", "never", "no", "no-login"):
        cmd.append("--no-login")
    if timeout:
        cmd += ["--timeout", str(int(timeout))]

    r = _run(cmd, timeout=(timeout or 3600) + 300)
    raw = (r.stdout or "").strip()
    # stdout 只放 JSON（进度日志走 stderr），但为稳妥仍从最后一个 { 开始找
    data = None
    if raw:
        for i, ch in enumerate(raw):
            if ch == "{":
                try:
                    data = json.loads(raw[i:])
                    break
                except Exception:
                    continue
    if data is None:
        err = ((r.stderr or "") + raw).strip().splitlines()
        hint = "（可能是登录态失效 → 先跑 video_digest.py wx-login）"
        raise WxError(f"视频号下载失败{hint}: "
                      f"{err[-1] if err else '退出码 ' + str(r.returncode)}")

    res = (data.get("results") or [{}])[0]
    if res.get("status") == "failed":
        raise WxError(f"视频号下载失败: {res.get('error') or res}")
    p = Path(res.get("path") or "")
    if not p.exists():
        raise WxError(f"下载结果里没有可用文件: {res}")
    # 去重命中（status=skipped）时 CLI 只回文件路径，title/author 为空，
    # 从同目录的 .wx-*.json 记录里补回来，否则上层拿到的元信息是空的。
    rec = {}
    if not (res.get("title") and res.get("author")):
        rec = _record_for(p)
    return {
        "video": str(p),
        "bytes": res.get("bytes") or p.stat().st_size,
        "title": res.get("title") or rec.get("title") or p.stem,
        "author": res.get("author") or rec.get("author") or "",
        "skipped": res.get("status") == "skipped",
        "share_id": sid,
    }


if __name__ == "__main__":
    # 自测：python lib_wx.py status | python lib_wx.py info <链接>
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    elif cmd == "info":
        print(json.dumps(video_info(sys.argv[2]), ensure_ascii=False, indent=1))
    elif cmd == "probe":
        print(json.dumps(probe(sys.argv[2]), ensure_ascii=False, indent=1))
