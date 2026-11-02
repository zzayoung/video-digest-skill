#!/usr/bin/env python
"""B 站视频 → 结构化专题页 全流程工具。

子命令：
  info       BV号                 取元信息 + 字幕探测 + 评论
  download   BV号 [-o 目录]       下载音视频流并转 16k 单声道 wav
  transcribe 音频.wav [-o json]   faster-whisper 中文转写
  frames     视频.m4s [-o 目录]   按间隔抽帧
  transcript json [-o md]         生成带时间码文稿 md
  all        BV号 [-o 目录]       一键跑完 info→download→transcribe→frames→transcript

实测环境（Windows / 无 GPU / 走代理）：
- 42 分钟视频：下载 ~2 分钟，转写 ~10.6 分钟（small 模型，16 线程，约 4x 实时）
- 所有网络请求内部已带重试，不必外部包 retry
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_bili  # noqa: E402

# faster-whisper small 中文模型：优先用已缓存的，避免重复下载 483MB
DEFAULT_MODEL = Path.home() / ".workbuddy" / "models" / "faster-whisper-small"
HF_MIRROR = "https://hf-mirror.com/Systran/faster-whisper-small/resolve/main"
MODEL_FILES = ["config.json", "tokenizer.json", "vocabulary.txt", "model.bin"]

def ffmpeg_path():
    """ffmpeg 二进制：优先 imageio-ffmpeg 自带，其次 PATH。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        p = shutil.which("ffmpeg")
        if not p:
            raise RuntimeError(
                "缺 ffmpeg：pip install imageio-ffmpeg（会自动带二进制）")
        return p


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def ensure_model(model_dir=DEFAULT_MODEL):
    """确保本地有 faster-whisper small 模型，没有就从 hf-mirror 下。

    注意：huggingface.co 在本环境被代理返回 502；huggingface_hub 直接下载
    会留下残缺的 model.bin，必须手动 curl 完整下载。
    """
    model_dir = Path(model_dir)
    need = [f for f in MODEL_FILES if not (model_dir / f).exists()
            or (model_dir / f).stat().st_size == 0]
    if not need:
        return model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    print(f"[model] 需要下载: {need}")
    for f in need:
        out = model_dir / f
        for i in range(10):
            r = run(["curl", "-sS", "-m", "900", "-L", "-C", "-",
                     "--retry", "5", "--retry-all-errors",
                     f"{HF_MIRROR}/{f}", "-o", str(out)])
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                print(f"[model] {f} {out.stat().st_size} bytes")
                break
        else:
            raise RuntimeError(f"模型文件下载失败: {f}")
    return model_dir


# ---------------------------------------------------------------- 子命令

def cmd_info(a):
    wd = Path(a.out); wd.mkdir(parents=True, exist_ok=True)
    info = lib_bili.video_info(a.bvid, workdir=str(wd))
    dur = info["duration"] or 0
    info["duration_human"] = f"{dur//60:02d}:{dur%60:02d}"
    (wd / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"标题  : {info['title']}")
    print(f"UP主  : {info['owner']} (mid {info['owner_mid']})")
    print(f"时长  : {info['duration_human']}  ({info['duration']}s)")
    print(f"分辨率: {info['width']}x{info['height']}")
    print(f"cid   : {info['cid']}   aid: {info['aid']}")
    print(f"简介  : {info['desc'][:100] or '(空)'}")
    print(f"字幕  : {'有' if info['has_subtitle'] else '无 → 需 ASR'}")

    try:
        cs = lib_bili.comments(info["aid"], pages=a.comment_pages)
        if cs:
            (wd / "comments.json").write_text(
                json.dumps(cs, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\n热评 {len(cs)} 条（已存 comments.json）：")
            for c in cs[:5]:
                print(f"  · [{c['like']}赞] {c['text'][:70]}")
    except Exception as e:
        print(f"[warn] 评论获取失败: {e}")

    # 字幕落盘（如果有）
    if info["has_subtitle"]:
        (wd / "subtitle.json").write_text(info["subtitle_json"], encoding="utf-8")
        print("[info] 已有官方字幕 → subtitle.json，可跳过 ASR")
    return info


def cmd_download(a):
    wd = Path(a.out); wd.mkdir(parents=True, exist_ok=True)
    info = lib_bili.video_info(a.bvid, workdir=str(wd))
    vurl, aurl, meta = lib_bili.get_playurl(
        a.bvid, info["cid"], workdir=str(wd), qn=a.qn)
    print(f"[play] quality={meta['quality']} {meta['video']} "
          f"audio_bw={meta['audio_bandwidth']}")
    print(f"[play] 可选清晰度: {meta['accept_quality']}")

    referer = f"https://www.bilibili.com/video/{a.bvid}/"
    print("[dl] 音频…")
    lib_bili.download_stream(aurl, wd / "audio.m4s", referer, workdir=str(wd))
    print("[dl] 视频…")
    lib_bili.download_stream(vurl, wd / "video.m4s", referer, workdir=str(wd))

    ff = ffmpeg_path()
    print("[ff] 转 16k 单声道 wav…")
    r = run([ff, "-hide_banner", "-loglevel", "error", "-i", str(wd / "audio.m4s"),
             "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
             str(wd / "audio16k.wav"), "-y"])
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 转换失败: {r.stderr}")

    for f in ["audio.m4s", "video.m4s", "audio16k.wav"]:
        print(f"  {f}: {(wd/f).stat().st_size/1e6:.1f} MB")
    (wd / "playurl_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[ok] 下载完成")


def cmd_transcribe(a):
    ensure_model(Path(a.model) if a.model else DEFAULT_MODEL)
    from faster_whisper import WhisperModel
    import os

    model_dir = str(Path(a.model) if a.model else DEFAULT_MODEL)
    print(f"[asr] 载入 {model_dir}")
    m = WhisperModel(model_dir, device="cpu", compute_type="int8",
                     cpu_threads=a.threads)

    # initial_prompt 喂领域词能明显减少术语错字
    prompt = a.prompt or ""
    t0 = time.time()
    segs, _ = m.transcribe(
        a.audio, language=a.language, beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 150},
        condition_on_previous_text=True,
        initial_prompt=prompt,
    )
    out = []
    n = 0
    total = a.duration or 0
    for s in segs:
        out.append({"s": round(s.start, 2), "e": round(s.end, 2),
                    "t": s.text.strip()})
        n += 1
        if n % 50 == 0:
            el = time.time() - t0
            pct = (s.start / total * 100) if total else 0
            print(f"  [{el:6.1f}s] {n} 段, 音频 {s.start:6.1f}s "
                  f"({pct:.1f}%), {s.start/max(el,1):.2f}x", flush=True)

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    el = time.time() - t0
    chars = sum(len(x["t"]) for x in out)
    print(f"[ok] {len(out)} 段 / {chars} 字 / 耗时 {el:.1f}s"
          + (f" / {(total/el):.2f}x 实时" if total else ""))
    print(f"     → {a.out}")


def cmd_frames(a):
    """按固定间隔抽帧，并落一份 frames/index.json 记录「帧 ↔ 时间码」。

    为什么要 index.json：以前要人工算「第 i 张 = (i-1)*every 秒」，
    every 不是整数分钟时几乎必算错，写专题页图注的时间码就会飘。
    现在直接查表，agent 按时间码挑图不会再错。
    """
    wd = Path(a.out); wd.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_path()
    every = max(1, int(a.every))
    width = int(getattr(a, "width", 0) or 0)
    vf = f"fps=1/{every}"
    if width:
        # 只缩不放，避免小视频被拉糊
        vf += f",scale='min({width},iw)':-2"
    r = run([ff, "-hide_banner", "-loglevel", "error", "-i", a.video,
             "-vf", vf, "-q:v", "3", str(wd / "f_%04d.jpg"), "-y"])
    if r.returncode != 0:
        raise RuntimeError(f"抽帧失败: {r.stderr[-400:]}")

    files = sorted(wd.glob("f_*.jpg"))
    index = [{"file": p.name, "t": i * every} for i, p in enumerate(files)]
    (wd / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(p.stat().st_size for p in files) / 1e6
    print(f"[ok] {len(files)} 帧（每 {every}s，{total:.1f} MB）→ {wd}")
    print(f"     时间码对照已写入 {wd / 'index.json'}："
          f"{files[0].name if files else '-'} ↔ 00:00")


def cmd_transcript(a):
    d = json.loads(Path(a.segments).read_text(encoding="utf-8"))

    def t(x):
        return f"{int(x//60):02d}:{int(x%60):02d}"

    lines = []
    cur = -1
    for seg in d:
        m = int(seg["s"] // 60)
        if m != cur:
            cur = m
            lines.append(f"\n## [{t(seg['s'])}]")
        lines.append(f"[{t(seg['s'])}] {seg['t']}")
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")
    chars = sum(len(x["t"]) for x in d)
    print(f"[ok] {len(d)} 段 / {chars} 字 → {a.out}")
    print("     提示：读这份文稿，按内容划分章节，再写 HTML 专题页")


def cmd_doctor(a):
    """环境自检：换机器 / 换 agent 后先跑这个。"""
    ok = True
    print("=== 环境自检 ===\n")

    print(f"Python  : {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info < (3, 9):
        print("  [!] 建议 3.9+")
        ok = False

    r = run(["curl", "--version"])
    curl_ok = r.returncode == 0 and "curl" in (r.stdout or "")
    print(f"curl    : {'OK' if curl_ok else '缺失（下载流必需）'}")
    if not curl_ok:
        ok = False

    for mod, pip in [("faster_whisper", "faster-whisper"),
                     ("imageio_ffmpeg", "imageio-ffmpeg"),
                     ("PIL", "Pillow")]:
        try:
            __import__(mod)
            print(f"{mod:<17}: OK")
        except ImportError:
            print(f"{mod:<17}: 缺失 → pip install {pip}")
            ok = False

    try:
        ff = ffmpeg_path()
        print(f"ffmpeg  : {ff}")
    except Exception as e:
        print(f"ffmpeg  : 缺失 → {e}")
        ok = False

    md = Path(a.model) if a.model else DEFAULT_MODEL
    if md.exists():
        size = sum(f.stat().st_size for f in md.glob("*") if f.is_file())
        print(f"ASR模型 : {md}  ({size/1e6:.0f} MB)")
    else:
        print(f"ASR模型 : 未下载 → {md}")
        print("         首次 transcribe 会自动从 hf-mirror 拉取（483MB）")
        if a.strict:
            ok = False

    # 网络连通（本环境 SSL 失败率约 1/3，重试次数给足）
    print("\n--- 连通性 ---")
    try:
        d = lib_bili._get_json(
            "https://api.bilibili.com/x/web-interface/nav", retries=10)
        print(f"B站 API : OK (code={d.get('code')})")
    except Exception as e:
        print(f"B站 API : 失败 → {str(e)[:80]}")
        print("         本环境偶发 SSL 握手失败，重试即可；持续失败需检查代理")
        ok = False

    try:
        r = run(["curl", "-sS", "-m", "20", "--retry", "5",
                 "--retry-all-errors", "-o", os.devnull, "-w", "%{http_code}",
                 "-L", "https://hf-mirror.com/Systran/faster-whisper-small/"
                 "resolve/main/config.json"])
        code = (r.stdout or "").strip()
        print(f"hf-mirror: HTTP {code}"
              + ("" if code == "200" else "（非 200，换 huggingface.co 试试）"))
    except Exception as e:
        print(f"hf-mirror: 失败 → {str(e)[:60]}")

    print("\n" + ("=== 全部就绪 ===" if ok else "=== 有缺失项，按提示安装 ==="))
    return 0 if ok else 1


def cmd_all(a):
    wd = Path(a.out); wd.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("1/5 元信息")
    info = cmd_info(argparse.Namespace(bvid=a.bvid, out=str(wd),
                                       comment_pages=3))
    if info["has_subtitle"]:
        print("  → 有官方字幕，后续可用 subtitle.json 替代 ASR")
    print("=" * 60)
    print("2/5 下载")
    cmd_download(argparse.Namespace(bvid=a.bvid, out=str(wd), qn=a.qn))
    print("=" * 60)
    print("3/5 抽帧")
    cmd_frames(argparse.Namespace(video=str(wd / "video.m4s"),
                                  out=str(wd / "frames"), every=a.every,
                                  width=getattr(a, "width", 960)))
    print("=" * 60)
    print("4/5 转写（耗时最长，建议放后台）")
    cmd_transcribe(argparse.Namespace(
        audio=str(wd / "audio16k.wav"), out=str(wd / "asr_segments.json"),
        model=a.model, threads=a.threads, language="zh",
        prompt=a.prompt, duration=info["duration"]))
    print("=" * 60)
    print("5/5 文稿")
    cmd_transcript(argparse.Namespace(
        segments=str(wd / "asr_segments.json"), out=str(wd / "transcript.md")))
    print("=" * 60)
    print(f"全部完成 → {wd}")
    mode = getattr(a, "mode", "learn")
    mode_desc = "梳理理解学习版（learn）" if mode == "learn" else "方法论反向拆解版（analysis）"
    print(f"下一步：读 transcript.md，按【{mode_desc}】生成 HTML 专题页 + SVG 架构图")
    print(f"  --mode={mode}  # 可切方向：learn=学习版，analysis=方法论版")


def main():
    p = argparse.ArgumentParser(description="B 站视频拆解工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info"); s.add_argument("bvid"); s.add_argument("-o", "--out", default=".")
    s.add_argument("--comment-pages", type=int, default=3); s.set_defaults(f=cmd_info)

    s = sub.add_parser("download"); s.add_argument("bvid"); s.add_argument("-o", "--out", default=".")
    s.add_argument("--qn", type=int, default=80); s.set_defaults(f=cmd_download)

    s = sub.add_parser("transcribe"); s.add_argument("audio"); s.add_argument("-o", "--out", default="asr_segments.json")
    s.add_argument("--model", default=None); s.add_argument("--threads", type=int, default=16)
    s.add_argument("--language", default="zh"); s.add_argument("--prompt", default="")
    s.add_argument("--duration", type=float, default=0); s.set_defaults(f=cmd_transcribe)

    s = sub.add_parser("frames"); s.add_argument("video"); s.add_argument("-o", "--out", default="frames")
    s.add_argument("--every", type=int, default=20)
    s.add_argument("--width", type=int, default=960)
    s.set_defaults(f=cmd_frames)

    s = sub.add_parser("transcript"); s.add_argument("segments"); s.add_argument("-o", "--out", default="transcript.md")
    s.set_defaults(f=cmd_transcript)

    s = sub.add_parser("doctor", help="环境自检（换机器先跑这个）")
    s.add_argument("--model", default=None)
    s.add_argument("--strict", action="store_true", help="缺模型也算失败")
    s.set_defaults(f=cmd_doctor)

    s = sub.add_parser("all"); s.add_argument("bvid"); s.add_argument("-o", "--out", default=".")
    s.add_argument("--qn", type=int, default=80); s.add_argument("--every", type=int, default=20)
    s.add_argument("--width", type=int, default=960)
    s.add_argument("--model", default=None); s.add_argument("--threads", type=int, default=16)
    s.add_argument("--prompt", default="")
    s.add_argument(
        "--mode",
        choices=["learn", "analysis"],
        default="learn",
        help="learn=梳理理解学习版；analysis=方法论反向拆解版",
    )
    s.set_defaults(f=cmd_all)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
