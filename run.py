#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video-digest 启动器：自动挑一个能用的解释器再执行。

    python run.py doctor
    python run.py all "https://www.bilibili.com/video/BVxxxx" -o ./work --every 20
    python run.py build ./work/outline.json --transcript ./work/asr_segments.json

解释器优先级：
  1. 环境变量 VD_PY（显式指定，最高优先级）
  2. 技能目录下的 .venv（scripts/setup_env.py 建的）
  3. WorkBuddy 自带 Python 环境（~/.workbuddy/binaries/python/envs/default）
  4. 当前解释器 sys.executable

所以「已经装好依赖的机器」不用再建 venv 也能直接跑；换到干净机器才需要 setup_env.py。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "scripts" / "video_digest.py"
VENV = Path(os.environ.get("VD_VENV") or (ROOT / ".venv"))
PROBE = "import faster_whisper, imageio_ffmpeg"


def venv_python(v: Path) -> Path:
    return v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def fallback_pythons() -> list[Path]:
    home = Path.home()
    env = home / ".workbuddy" / "binaries" / "python" / "envs" / "default"
    return [venv_python(env), env / "python.exe", env / "bin" / "python"]


def can_run(py: Path) -> bool:
    try:
        r = subprocess.run([str(py), "-c", PROBE], capture_output=True, timeout=25)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pick() -> tuple[Path | None, str]:
    forced = os.environ.get("VD_PY")
    if forced:
        return Path(forced), "VD_PY"

    py = venv_python(VENV)
    if py.exists():
        return py, "技能 .venv"

    for cand in fallback_pythons():
        if cand.exists() and can_run(cand):
            return cand, "WorkBuddy 自带环境（未建 .venv）"

    if can_run(Path(sys.executable)):
        return Path(sys.executable), "当前解释器"
    return None, ""


def main() -> int:
    if not TARGET.exists():
        print(f"[错误] 找不到 {TARGET}，技能目录不完整。")
        return 2

    py, why = pick()
    if py is None:
        print("=" * 62)
        print(" 没找到能用的 Python 环境（缺 faster-whisper / imageio-ffmpeg）。")
        print(" 先装环境：")
        print()
        print(f'   "{sys.executable}" scripts/setup_env.py')
        print(f'   "{sys.executable}" scripts/setup_env.py --skip-model   # 只做 YouTube')
        print()
        print(" 或在已装好依赖的环境上指定解释器：")
        print(f'   VD_PY="/path/to/python" "{sys.executable}" run.py doctor')
        print("=" * 62)
        return 2

    if why != "技能 .venv":
        print(f"[info] 使用 {why}: {py}")

    # 已经在这个解释器里了，直接执行，避免多开一层进程
    try:
        same = Path(sys.executable).resolve() == py.resolve()
    except OSError:
        same = False

    args = [str(py), str(TARGET)] + sys.argv[1:]
    if same:
        sys.argv = [str(TARGET)] + sys.argv[1:]
        return subprocess.call(args)

    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.call(args, env=env)


if __name__ == "__main__":
    sys.exit(main())
