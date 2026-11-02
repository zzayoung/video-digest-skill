# -*- coding: utf-8 -*-
"""图集（图文作品）的公共处理层。

为什么单独一层
--------------
图集没有音频，走不了 ASR；抽帧也失去意义（图本身就是帧）。所以图集不是"视频的变种"，
而是**另一条媒体形态**：取到的是 N 张图 + 一段文案，产出是图集页而不是章节页。

这一层只做四件事：
  1. 从平台返回的原始结构里抽出图片 URL（各平台字段不同，抽法留在各自 lib）
  2. 批量下载 + 命名规范化（01.jpg、02.jpg …，排序稳定）
  3. 读尺寸（PIL，可选；没有就跳过）
  4. 写 manifest（images/index.json），供 outline 引用与 agent 挑选
"""

from __future__ import annotations

import json
from pathlib import Path

import lib_short as S

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")


def is_image_file(p) -> bool:
    return Path(p).suffix.lower() in IMAGE_EXT


def natural_key(p: Path):
    """按文件名里的数字排序：1.jpg < 2.jpg < 10.jpg（而不是 1,10,2）。"""
    import re
    nums = re.findall(r"\d+", p.stem)
    return (int(nums[0]) if nums else 10 ** 9, p.stem.lower())


def scan_dir(dirpath) -> list[Path]:
    """扫描目录下的图片，按自然序返回。"""
    d = Path(dirpath).expanduser()
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and is_image_file(p)]
    return sorted(files, key=natural_key)


def has_images(dirpath) -> bool:
    return bool(scan_dir(dirpath))


def probe_size(path):
    """返回 (width, height)；没有 PIL 或读失败就 (None, None)。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None, None


def download_all(urls, workdir, referer=None, cookie=None, min_bytes=3072,
                 timeout=180):
    """按顺序下载图片到 workdir/images/，返回 manifest 条目列表。

    单张失败不致命：记进 failed 列表，让 agent 知道缺哪张，
    总比整组图集因为第 7 张挂了而全废要好。
    """
    wd = Path(workdir)
    out_dir = wd / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    items, failed = [], []
    for i, url in enumerate(urls, 1):
        dest = out_dir / f"{i:02d}.jpg"
        if dest.exists() and dest.stat().st_size >= min_bytes:
            w, h = probe_size(dest)
            items.append({"src": f"images/{dest.name}", "idx": i,
                          "bytes": dest.stat().st_size, "width": w, "height": h,
                          "source": url})
            continue
        try:
            size = S.download_media(url, dest, referer=referer, cookie=cookie,
                                    timeout=timeout)
            if size < min_bytes:
                raise S.ShortError(f"返回 {size} 字节，疑似不是图片")
            w, h = probe_size(dest)
            items.append({"src": f"images/{dest.name}", "idx": i, "bytes": size,
                          "width": w, "height": h, "source": url})
        except Exception as e:                       # noqa: BLE001
            failed.append({"idx": i, "url": url, "error": str(e)[:120]})
            dest.unlink(missing_ok=True)
    return items, failed


def from_local_dir(dirpath, workdir=None):
    """把本地图片目录整理成 manifest 条目（不复制文件，只记路径）。

    用途：视频号图文目前没有可靠的第三方下载器，用户手动存图后可以直接喂进来。
    """
    files = scan_dir(dirpath)
    items = []
    for i, p in enumerate(files, 1):
        w, h = probe_size(p)
        items.append({"src": str(p.resolve()), "idx": i,
                      "bytes": p.stat().st_size, "width": w, "height": h,
                      "source": str(p)})
    return items


def write_manifest(workdir, items, meta=None, failed=None):
    """写 images/index.json。caption 交给 agent 后续补，不在这里编。"""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "images",
        "count": len(items),
        "items": items,
        **(meta or {}),
    }
    if failed:
        manifest["failed"] = failed
    (wd / "images_index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def aspect_tag(w, h):
    """给个粗略画幅标签，方便 agent 判断九宫格还是单图。"""
    if not w or not h:
        return ""
    r = w / h
    if r > 1.25:
        return "横"
    if r < 0.8:
        return "竖"
    return "方"
