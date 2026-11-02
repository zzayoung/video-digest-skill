#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video-digest 环境安装器（跨平台，Windows / macOS / Linux 通用）。

做四件事，任何一步失败都会明确告诉你缺什么：

  1. 建一个独立 venv（默认放在技能目录下的 .venv，不污染系统 Python）
  2. 装 requirements.txt 里的依赖（官方源失败自动换国内镜像重试）
  3. 下 faster-whisper small 模型到 ~/.workbuddy/models/（可 --skip-model 跳过）
  4. 跑 video_digest.py doctor 做一次自检

用法：
    python scripts/setup_env.py                 # 全套
    python scripts/setup_env.py --skip-model    # 只装依赖（YouTube 有字幕时够用）
    python scripts/setup_env.py --check         # 只自检，不安装
    python scripts/setup_env.py --venv D:/vd    # 指定 venv 位置

装完用技能根目录的 run.py 调脚本，它会自动找到这个 venv：
    python run.py doctor
    python run.py all "https://www.bilibili.com/video/BVxxxx"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"
DEFAULT_VENV = ROOT / ".venv"

MODEL_DIR = Path.home() / ".workbuddy" / "models" / "faster-whisper-small"
MODEL_MIRROR = "https://hf-mirror.com/Systran/faster-whisper-small/resolve/main"
# 文件名 → 最小合理体积（用来判断是不是残缺文件）
MODEL_FILES = {
    "config.json": 1_000,
    "tokenizer.json": 1_000,
    "vocabulary.txt": 1_000,
    "model.bin": 400_000_000,
}

MIRRORS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",  # 清华：国内快，个别包缺失
    "https://mirrors.aliyun.com/pypi/simple",    # 阿里：备选
    "https://pypi.org/simple",                   # 官方源：包最全但国内常超时
]
# 主源缺包时（如 wx-downloader）从官方源补齐
EXTRA_INDEX = "https://pypi.org/simple"


# ------------------------------------------------------------------ 小工具

def say(msg=""):
    print(msg, flush=True)


def step(n, total, msg):
    say(f"\n[{n}/{total}] {msg}")


def run(cmd, **kw):
    say("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], **kw)


def venv_python(venv: Path) -> Path:
    """venv 里的 python 可执行文件（Windows 与 POSIX 路径不同）。"""
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ------------------------------------------------------------------ 1. venv

def ensure_venv(base_py: str, venv: Path, force: bool = False) -> Path:
    py = venv_python(venv)
    if force and venv.exists():
        say(f"  删除旧 venv: {venv}")
        shutil.rmtree(venv, ignore_errors=True)

    if py.exists():
        say(f"  venv 已存在: {venv}")
    else:
        say(f"  创建 venv: {venv}")
        venv.parent.mkdir(parents=True, exist_ok=True)
        r = run([base_py, "-m", "venv", str(venv)])
        if r.returncode != 0 or not py.exists():
            raise SystemExit(
                "\n[失败] 无法创建 venv。\n"
                "  · Linux 可能缺 python3-venv：sudo apt install python3-venv\n"
                "  · 或改用现有解释器：--python /path/to/python --no-venv")

    # 有些发行版的 venv 不带 pip
    r = run([py, "-m", "pip", "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        say("  venv 缺 pip，尝试 ensurepip")
        run([py, "-m", "ensurepip", "--upgrade"])

    v = run([py, "-c",
             "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True)
    say(f"  Python: {v.stdout.strip() or v.stderr.strip()}")
    return py


# ------------------------------------------------------------------ 2. 依赖

def install_deps(py: Path, index_url: str | None = None) -> None:
    if not REQ.exists():
        raise SystemExit(f"[失败] 找不到 {REQ}")

    say("  升级 pip（失败不影响后续）")
    run([py, "-m", "pip", "install", "--upgrade", "pip",
         "--index-url", MIRRORS[0], "--timeout", "20", "--retries", "2",
         "--disable-pip-version-check"], stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT)

    targets = [index_url] if index_url else MIRRORS
    last = ""
    for i, idx in enumerate(targets, 1):
        say(f"  源 {i}/{len(targets)}: {idx}")
        cmd = [py, "-m", "pip", "install", "-r", str(REQ),
               "--index-url", idx,
               "--timeout", "25", "--retries", "2",
               "--disable-pip-version-check"]
        if idx != EXTRA_INDEX:
            cmd += ["--extra-index-url", EXTRA_INDEX]
        r = run(cmd)
        if r.returncode == 0:
            say("  依赖安装完成")
            return
        last = idx
        say("  该源失败，换下一个")
    raise SystemExit(
        f"\n[失败] 依赖安装失败（最后尝试的源：{last}）。\n"
        "  · 网络问题：换源重试 python scripts/setup_env.py --index-url <url>\n"
        "  · 只做 YouTube 且视频有字幕：可以只装 yt-dlp 与 Pillow")


# ------------------------------------------------------------------ 3. 模型

def _curl() -> str | None:
    return shutil.which("curl")


def _download_curl(url: str, out: Path) -> bool:
    curl = _curl()
    if not curl:
        return False
    r = run([curl, "-sS", "-L", "-C", "-", "-m", "1800",
             "--retry", "5", "--retry-all-errors",
             url, "-o", str(out)], capture_output=True, text=True)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 0


def _download_urllib(url: str, out: Path, min_size: int) -> bool:
    """curl 不可用时的兜底：支持 Range 续传。"""
    have = out.stat().st_size if out.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "video-digest-setup"})
    if have:
        req.add_header("Range", f"bytes={have}-")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            mode = "ab" if have and resp.status == 206 else "wb"
            if mode == "wb":
                have = 0
            total = int(resp.headers.get("Content-Length") or 0) + have
            with open(out, mode) as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    have += len(chunk)
                    if total:
                        pct = have * 100 // total
                        print(f"\r    {pct:3d}%  {human(have)} / {human(total)}",
                              end="", flush=True)
        print()
        return out.exists() and out.stat().st_size >= min_size
    except (urllib.error.URLError, OSError) as e:
        print()
        say(f"    下载出错: {e}")
        return False


def download_model(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, min_size in MODEL_FILES.items():
        out = model_dir / name
        if out.exists() and out.stat().st_size >= min_size:
            say(f"  {name:<15} 已有 {human(out.stat().st_size)}")
            continue

        say(f"  {name:<15} 下载中 …")
        url = f"{MODEL_MIRROR}/{name}"
        ok = False
        for attempt in range(4):
            if _download_curl(url, out) or _download_urllib(url, out, min_size):
                if out.stat().st_size >= min_size:
                    ok = True
                    break
            say(f"    第 {attempt + 1} 次失败，重试")
        if not ok:
            raise SystemExit(
                f"\n[失败] 模型文件 {name} 下载不完整。\n"
                f"  手动下载：{url}\n"
                f"  存到：{out}\n"
                "  完成后重跑 setup_env.py（会跳过已完成的文件）")
        say(f"  {name:<15} OK  {human(out.stat().st_size)}")
    say(f"  模型就绪: {model_dir}")


# ------------------------------------------------------------------ 4. 自检

def doctor(py: Path) -> int:
    r = run([py, ROOT / "scripts" / "video_digest.py", "doctor"], cwd=str(ROOT))
    return r.returncode


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(
        description="video-digest 环境安装器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="装完用：python run.py doctor")
    ap.add_argument("--venv", default=str(DEFAULT_VENV),
                    help=f"venv 目录（默认 {DEFAULT_VENV}）")
    ap.add_argument("--python", default=sys.executable,
                    help="用哪个解释器建 venv（默认当前 python）")
    ap.add_argument("--no-venv", action="store_true",
                    help="不建 venv，直接往当前解释器里装")
    ap.add_argument("--force", action="store_true", help="重建 venv")
    ap.add_argument("--skip-model", action="store_true",
                    help="跳过大模型下载（YouTube 有字幕时不需要）")
    ap.add_argument("--model-dir", default=str(MODEL_DIR),
                    help=f"模型目录（默认 {MODEL_DIR}）")
    ap.add_argument("--index-url", default=None, help="指定 pip 源")
    ap.add_argument("--check", action="store_true", help="只自检，不安装")
    a = ap.parse_args()

    say("=" * 62)
    say(" video-digest 环境安装")
    say(f" 技能目录: {ROOT}")
    say(f" 基础解释器: {a.python}")
    say("=" * 62)

    if a.check:
        py = venv_python(Path(a.venv)) if not a.no_venv else Path(sys.executable)
        if not py.exists():
            say(f"venv 不存在：{py}\n先跑 python scripts/setup_env.py")
            return 1
        return doctor(py)

    ver = sys.version_info
    if ver < (3, 9):
        raise SystemExit(f"[失败] 需要 Python 3.9+，当前 {ver.major}.{ver.minor}")

    total = 4 if not a.skip_model else 3
    n = 0

    n += 1
    step(n, total, "准备 Python 环境")
    py = Path(sys.executable) if a.no_venv else ensure_venv(a.python, Path(a.venv), a.force)

    n += 1
    step(n, total, "安装第三方依赖")
    install_deps(py, a.index_url)

    if not a.skip_model:
        n += 1
        step(n, total, "下载 faster-whisper small 模型（约 483 MB）")
        download_model(Path(a.model_dir))
    else:
        say("\n[跳过] 模型下载。B站 / 视频号 / 本地文件在首次转写时会自动补下。")

    n += 1
    step(n, total, "环境自检")
    code = doctor(py)

    say("\n" + "=" * 62)
    if code == 0:
        say(" 安装完成。常用命令：")
    else:
        say(" 依赖已装，但自检有缺失项（见上）。常用命令：")
    say(f'   "{py}" run.py doctor')
    say(f'   "{py}" run.py all "<视频链接>" -o ./work --every 20')
    say(f'   "{py}" run.py wx-login --browser msedge    # 视频号首次')
    say("=" * 62)
    return code


if __name__ == "__main__":
    sys.exit(main())
