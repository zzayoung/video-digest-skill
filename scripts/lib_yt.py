"""YouTube 封装：视频 ID 解析 / 元信息 / 字幕直取 / 媒体下载。

与 B 站最大的不同（这是改造的关键收益）：
- YouTube 绝大多数视频自带**官方字幕或自动生成字幕（ASR）**，
  可走「字幕直取」链路，省掉本地 486MB 模型下载 + 10 分钟转写。
- B 站没有开放 AI 字幕接口，只能下音频跑本地 ASR；YouTube 反过来。
  因此本模块的优先级是：**字幕 > 本地 ASR**。

实现依赖 yt-dlp（YouTube 签名算法变更频繁，自维护成本极高）：
- 元信息 / 字幕轨道清单：yt-dlp.extract_info(download=False)
- 字幕正文：直接请求 timedtext 接口并带 `&fmt=json3`
- 媒体下载：yt-dlp -f 表达式

代理：本环境 HTTPS_PROXY 已在 env 中，curl / yt-dlp 均自动继承，无需额外配置。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import yt_dlp
except ImportError:  # 延迟报错，doctor 会给出安装命令
    yt_dlp = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|"
               r"youtube\.com/shorts/|youtube\.com/live/|youtube\.com/v/)([0-9A-Za-z_-]{11})"),
    re.compile(r"^[0-9A-Za-z_-]{11}$"),
]


class YtError(RuntimeError):
    pass


def _need():
    if yt_dlp is None:
        raise YtError("yt-dlp 未安装，请执行 pip install yt-dlp")


def parse_id(url):
    """从各种 YouTube 链接形态里抽 11 位 video id。"""
    url = (url or "").strip()
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    raise YtError(f"无法解析 YouTube 视频 ID: {url}")


def watch_url(url):
    return "https://www.youtube.com/watch?v=" + parse_id(url)


def _ydl_opts(workdir=None, quiet=True):
    o = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noprogress": True,
        "skip_download": True,
        "noplaylist": True,
        "user_agent": UA,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
    }
    if workdir:
        o["paths"] = {"home": str(workdir)}
    return o


def ffmpeg_dir():
    """ffmpeg 所在目录（目录内必须有一个名为 ffmpeg/ffmpeg.exe 的文件）。

    两个坑：
      1) yt-dlp 合并分流格式时必须显式给 ffmpeg_location，否则报
         'ffmpeg is not installed, Aborting'——imageio-ffmpeg 的二进制不在 PATH 上。
      2) yt-dlp 只认**文件名为 ffmpeg(.exe)** 的可执行文件，而 imageio-ffmpeg
         给的是 `ffmpeg-win-x86_64-v7.1.exe`，光传目录仍然报上面的错。
         所以这里复制一份标准名到 ~/.workbuddy/bin/（只做一次，按体积判断是否已存在）。
    """
    exe = None
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
    if not exe:
        return None
    p = Path(exe)
    if p.name.lower() in ("ffmpeg.exe", "ffmpeg"):
        return str(p.parent)

    dst_dir = Path.home() / ".workbuddy" / "bin"
    dst = dst_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != p.stat().st_size:
            shutil.copyfile(p, dst)
            print(f"  [ffmpeg] 已复制标准名副本 → {dst}", flush=True)
        return str(dst_dir)
    except Exception as e:
        print(f"  [warn] ffmpeg 标准名副本失败: {str(e)[:80]}", flush=True)
        return str(p.parent)


def raw_info(url, workdir=None):
    """yt-dlp 抽取完整元信息（含字幕轨道清单）。结果缓存到 workdir/info_raw.json。"""
    _need()
    vid = parse_id(url)
    cache = Path(workdir or ".") / "info_raw.json"
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("id") == vid:
                return d
        except Exception:
            pass
    opts = _ydl_opts(workdir)
    last = ""
    for i in range(4):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                d = ydl.extract_info(watch_url(url), download=False)
            if workdir:
                Path(workdir).mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            return d
        except Exception as e:
            last = str(e)[:300]
            time.sleep(2)
    raise YtError(f"yt-dlp 抽取元信息失败: {last}")


def subtitle_tracks(d):
    """整理字幕轨道：[(kind, lang, ext_list, url)]，kind ∈ manual/asr。

    lang 例：zh-Hans / zh-Hant / en / en-orig / ja。
    YouTube 自动字幕的 lang 一般等于原语音语种（无 -orig 后缀），
    翻译字幕带 -t- 或由 tlang 产生。
    """
    out = []
    for kind, key in (("manual", "subtitles"), ("asr", "automatic_captions")):
        for lang, tracks in (d.get(key) or {}).items():
            for t in tracks or []:
                if t.get("url"):
                    out.append((kind, lang, t.get("ext"), t["url"]))
    return out


def orig_lang(d):
    """原语音语种。YouTube 自动字幕里 `xx-orig` 就是原始 ASR（未翻译），
    保真度最高；没有 -orig 时退回 yt-dlp 给的 language 字段。"""
    langs = {lang for _k, lang, _e, _u in subtitle_tracks(d)}
    for l in sorted(langs):
        if l.endswith("-orig"):
            return l
    return d.get("language") or ""


def pick_subtitle(d, prefer=None):
    """按偏好语种挑一条字幕轨道。返回 (kind, lang, url) 或 None。

    prefer 例：["ja-orig", "zh-Hans", "en"]；也接受 "orig" 占位符代表原语音。
    默认顺序（不传 prefer 时）：**原语音 -orig > 中文 > 英文**。
    理由：自动翻译轨（zh-Hans/ja 互相翻译）错译多，做专题页时
    「原始语种保真 + 自己翻译」远比「机翻轨」可靠。

    规则：
      1) 官方字幕（manual）优先于自动生成（asr）
      2) 同类中按 prefer 顺序：精确匹配 > 前缀匹配（ja 匹配 ja-orig）
      3) 都没有 → 返回 None，交给本地 ASR
    """
    tracks = subtitle_tracks(d)
    if not tracks:
        return None
    if prefer is None:
        _o = orig_lang(d)
        prefer = ([_o] if _o else []) + ["zh-Hans", "zh-Hant", "zh", "en"]
    else:
        prefer = ["orig" if p.strip().lower() == "orig" else p.strip()
                  for p in prefer if p.strip()]
        prefer = [orig_lang(d) if p == "orig" else p for p in prefer]

    def score(lang):
        for i, p in enumerate(prefer):
            if lang.lower() == p.lower():
                return i * 2
        for i, p in enumerate(prefer):
            if lang.lower().startswith(p.lower().split("-")[0]):
                return i * 2 + 1
        return 999

    best = None
    best_key = None
    for kind, lang, _ext, url in tracks:
        s = score(lang)
        if s >= 999:
            continue
        # kind 权重：manual=0，asr=100（同分时官方优先）
        key = (0 if kind == "manual" else 100) + s
        if best_key is None or key < best_key:
            best_key, best = key, (kind, lang, url)
    if best is None:  # 偏好语种全无 → 退化到任意官方，再任意 asr
        for kind in ("manual", "asr"):
            for k, lang, _e, url in tracks:
                if k == kind:
                    return (kind, lang, url)
    return best


def fetch_subtitle_json(url, out=None, tries=6):
    """抓 json3 格式字幕正文。返回原始 dict。

    坑：YouTube timedtext 对**同一视频的连续请求**会返回 429（限流），
    尤其「主轨 + 附加轨」连着抓时必踩。必须按 429 做**指数退避**，
    不能无脑快速重试（越试越 429）。
    """
    if "fmt=" not in url:
        url += ("&" if "?" in url else "?") + "fmt=json3"
    last = ""
    for i in range(tries):
        r = subprocess.run(
            ["curl", "-sS", "-m", "60", "-L", "-w", "\n%{http_code}",
             "-H", f"User-Agent: {UA}", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        raw = (r.stdout or "").rstrip()
        body, _, code = raw.rpartition("\n")
        txt = body.strip()
        if code == "200" and txt.startswith("{"):
            d = json.loads(txt)
            if out:
                Path(out).write_text(json.dumps(d, ensure_ascii=False),
                                     encoding="utf-8")
            return d
        if code == "429":
            wait = min(5 * (2 ** i), 60)      # 5s → 10s → 20s → 40s → 60s
            print(f"  [429 限流] {wait}s 后退避重试 ({i+1}/{tries})", flush=True)
            time.sleep(wait)
            last = f"HTTP 429 rate-limited"
            continue
        last = (r.stderr or f"HTTP {code}: {txt[:120]}").strip()
        time.sleep(3)
    raise YtError(f"字幕下载失败: {last}")


def json3_to_segments(d, max_chars=90, max_gap=1.2):
    """json3 → [{s,e,t}]。把碎事件按「最大字数 / 静音间隔」合并成可读段。"""
    segs = []
    buf, bs, be = [], None, None

    def flush():
        nonlocal buf, bs, be
        if not buf:
            return
        txt = "".join(buf).strip()
        txt = re.sub(r"\s+", " ", txt)
        if txt:
            segs.append({"s": round(bs, 2), "e": round(be, 2), "t": txt})
        buf, bs, be = [], None, None

    for ev in d.get("events") or []:
        if "segs" not in ev:
            continue
        txt = "".join(s.get("utf8", "") for s in ev["segs"])
        if not txt.strip():
            continue
        st = (ev.get("tStartMs") or 0) / 1000.0
        du = (ev.get("dDurationMs") or 0) / 1000.0
        en = st + du
        if bs is None:
            bs, be = st, en
        elif st - be > max_gap or sum(len(x) for x in buf) >= max_chars:
            flush()
            bs, be = st, en
        else:
            be = en
        buf.append(txt)
    flush()
    return segs


def video_info(url, workdir="."):
    """统一结构的元信息（字段对齐 lib_bili.video_info，方便上层共用）。"""
    d = raw_info(url, workdir)
    return {
        "platform": "youtube",
        "bvid": d.get("id"),                      # 复用字段位：YouTube 存 video id
        "aid": d.get("id"),
        "cid": d.get("id"),
        "title": d.get("title"),
        "owner": d.get("uploader") or d.get("channel"),
        "owner_mid": d.get("channel_id"),
        "pubdate": d.get("upload_date"),
        "duration": int(d.get("duration") or 0),
        "desc": (d.get("description") or "")[:4000],
        "width": d.get("width"),
        "height": d.get("height"),
        "stat": {
            "view": d.get("view_count"),
            "like": d.get("like_count"),
            "comment": d.get("comment_count"),
        },
        "tags": (d.get("tags") or [])[:30],
        "categories": d.get("categories") or [],
        "webpage_url": d.get("webpage_url") or watch_url(url),
        "thumbnail": d.get("thumbnail"),
        "has_subtitle": bool((d.get("subtitles") or d.get("automatic_captions"))),
        "subtitle_langs": sorted({l for _k, l, _e, _u in subtitle_tracks(d)}),
    }


def download(url, workdir=".", height=720, want_video=True):
    """下载媒体。返回 dict(video=..., audio=..., wav=...)。

    - 只做 ASR 时 want_video=False，可省掉几十 MB 视频流
    - 抽帧需要视频流，默认一起下
    """
    _need()
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    out = {"video": None, "audio": None, "wav": None}

    def _run(fmt, tpl, label):
        opts = {
            "quiet": False, "no_warnings": True, "noprogress": True,
            "noplaylist": True, "user_agent": UA, "format": fmt,
            "outtmpl": str(wd / tpl),
            # 注意：outtmpl 已是绝对路径，不要再设 paths.home，
            # 否则 yt-dlp 会再拼一层目录（曾出现 work/audio.m4a → work/work/audio.m4a）
            "socket_timeout": 30, "retries": 8, "fragment_retries": 8,
            "concurrent_fragment_downloads": 4,
        }
        fd = ffmpeg_dir()
        if fd:
            opts["ffmpeg_location"] = fd      # 关键：否则分流合并直接失败
        last = ""
        for i in range(3):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([watch_url(url)])
                return True
            except Exception as e:
                last = str(e)[:200]
                time.sleep(3)
        print(f"  [warn] {label} 下载失败: {last}", flush=True)
        return False

    if want_video:
        fmt = (f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
               "/best[ext=mp4]/best")
        if _run(fmt, "video.%(ext)s", "视频+音频"):
            for p in wd.glob("video.*"):
                out["video"] = str(p)
        if not out["video"]:
            # 合并失败（如 ffmpeg 缺失）时退化：单流，不合并
            print("  [降级] 改下单一流（不合并）", flush=True)
            if _run(f"best[height<={height}]/best", "video.%(ext)s", "视频单流"):
                for p in wd.glob("video.*"):
                    out["video"] = str(p)
    # 单独音频（ASR 用，体积小）
    if _run("bestaudio[ext=m4a]/bestaudio/best", "audio.%(ext)s", "音频"):
        for p in wd.glob("audio.*"):
            if p.suffix.lower() != ".wav":
                out["audio"] = str(p)
    return out


def comments(url, workdir=".", limit=20):
    """尽力取评论。YouTube 评论接口近年收紧，拿不到就返回 []（不影响主流程）。"""
    _need()
    opts = _ydl_opts(workdir)
    opts.update({"getcomments": True, "extractor_args": {
        "youtube": {"comment_sort": ["top"], "max_comments": [str(limit)]}}})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            d = ydl.extract_info(watch_url(url), download=False)
        cs = d.get("comments") or []
        return [{"user": c.get("author"), "like": c.get("like_count"),
                 "text": (c.get("text") or "")[:500]} for c in cs[:limit]]
    except Exception as e:
        print(f"  [warn] 评论获取失败（可忽略）: {str(e)[:80]}", flush=True)
        return []


if __name__ == "__main__":
    # 自测入口：python lib_yt.py info <url>
    cmd = sys.argv[1] if len(sys.argv) > 1 else "info"
    if cmd == "info":
        i = video_info(sys.argv[2], ".")
        print(json.dumps(i, ensure_ascii=False, indent=1)[:2000])
