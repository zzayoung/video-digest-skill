# -*- coding: utf-8 -*-
"""平台解析器离线夹具测试。

为什么需要它
------------
抖音 / 小红书 / TikTok 的解析规则依赖页面里 JSON 的**形状**，而这些平台随时会改。
在没有网络（或不想每次跑真链接）的环境里，用夹具锁住「已知形状」能带来两个好处：
  1. 改代码时立刻知道有没有把解析改坏
  2. 每个夹具就是一份「当时长什么样」的存档，联网后可对照实际返回

跑法：python tests/test_parsers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lib_short as S            # noqa: E402
import lib_douyin               # noqa: E402
import lib_xhs                  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILED.append(name)


# --------------------------------------------------------------- 夹具

DOUYIN_HTML = """
<html><head><title>抖音</title></head><body><script>
window._ROUTER_DATA = {"loaderData":{"video_(7391)/page":{"videoInfoRes":{
  "item_list":[{
    "aweme_id":"7391000000000000000",
    "desc":"三句话讲完 #效率 #副业",
    "author":{"nickname":"示例账号"},
    "video":{"duration":47800,"width":1080,"height":1920,
      "play_addr":{"url_list":["https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0300&ratio=720p"]},
      "cover":{"url_list":["https://p3.douyinpic.com/cover.jpg"]}},
    "statistics":{"digg_count":12000,"comment_count":340,"share_count":88,"collect_count":2000}
  }]}},"video_(7391)/page2":{"other":1}}};
</script></body></html>
"""

DOUYIN_IMAGE_HTML = """
<html><body><script>
window._ROUTER_DATA = {"loaderData":{"note_(1)/page":{"videoInfoRes":{"item_list":[{
  "aweme_id":"1","desc":"图文笔记 #旅行",
  "author":{"nickname":"图集账号"},
  "images":[{"url_list":["https://p3.douyinpic.com/a.jpg","https://p9.douyinpic.com/a.jpg"]},
            {"url_list":["https://p3.douyinpic.com/b.jpg"]},
            {"url_list":["//p3.douyinpic.com/c.jpg"]}]
}]}}}};
</script></body></html>
"""

XHS_HTML = """
<html><head><title>小红书</title>
<meta property="og:title" content="示例笔记">
</head><body><script>
window.__INITIAL_STATE__={"note":{"noteDetailMap":{"66aa11bb22cc33dd44ee55ff":{
  "note":{"noteId":"66aa11bb22cc33dd44ee55ff","title":"三句话讲完","desc":"正文 #效率",
    "user":{"nickname":"小红书账号"},
    "video":{"capa":{"duration":48,"width":1080,"height":1920},
      "media":{"stream":{"h264":[{"masterUrl":"https://sns-video-bd.xhscdn.com/abc.mp4",
        "backupUrls":["https://up.xhscdn.com/abc.mp4"]}],"h265":[]}},
      "image":{"firstFrame":"https://sns-img.xhscdn.com/frame.jpg"}},
    "interactInfo":{"likedCount":"1.2万","collectedCount":"3000","commentCount":"210","shareCount":"88"},
    "tagList":[{"name":"效率"},{"name":"副业"}]}},
  "undefinedField":undefined}},"user":{"loggedIn":false}};
</script></body></html>
"""

XHS_IMAGE_HTML = """
<html><body><script>
window.__INITIAL_STATE__={"note":{"noteDetailMap":{"abc123abc123abc123abc1":{
  "note":{"noteId":"abc123abc123abc123abc1","title":"九宫格","desc":"正文",
    "user":{"nickname":"u"},
    "imageList":[
      {"urlDefault":"https://sns-img.xhscdn.com/1.jpg"},
      {"url":"https://sns-img.xhscdn.com/2.jpg"},
      {"urlDefault":null,"infoList":[{"url":"https://sns-img.xhscdn.com/3.jpg"}]}]}}}}};
</script></body></html>
"""


def main():
    print("[1] lib_short.json_after —— 花括号配平与 undefined 容错")
    html = '<script>var x = {"a":{"b":"} 不该截断 {"},"c":[1,2]};</script>'
    got = S.json_after(html, "var x =")
    check("嵌套对象与字符串里的花括号", got == {"a": {"b": "} 不该截断 {"}, "c": [1, 2]},
          str(got))
    check("marker 不存在返回 None", S.json_after("<html></html>", "nope") is None)
    got2 = S.json_after('x = {"a": undefined, "b": 1}', "x =", undefined_safe=True)
    check("裸 undefined 替换为 null", got2 == {"a": None, "b": 1}, str(got2))

    print("[2] 抖音：分享页解析")
    d = lib_douyin.parse_share(DOUYIN_HTML)
    check("标题取 desc 首行", d["title"] == "三句话讲完 #效率 #副业", d["title"])
    check("作者", d["author"] == "示例账号", d["author"])
    check("时长 47800ms → 47.8s", d["duration"] == 47.8, str(d["duration"]))
    check("playwm 换成 play（去水印）", "/play/" in d["play_url"] and "playwm" not in d["play_url"],
          d["play_url"])
    check("点赞数", d["stat"]["like"] == 12000, str(d["stat"]))
    check("话题提取", d["tags"] == ["效率", "副业"], str(d["tags"]))
    check("封面地址", (d["cover"] or "").startswith("https://"), str(d["cover"]))

    print("[3] 抖音：图文作品走图集分支")
    dg = lib_douyin.parse_share(DOUYIN_IMAGE_HTML)
    check("kind=images", dg["kind"] == "images", dg["kind"])
    check("取到 3 张图", len(dg["image_urls"]) == 3, str(len(dg["image_urls"])))
    check("多候选取第一个 https", dg["image_urls"][0].startswith("https://p3."), dg["image_urls"][0])
    check("协议相对地址补 https", dg["image_urls"][2].startswith("https://"), dg["image_urls"][2])
    check("图文没有播放地址", not dg.get("play_url"), str(dg.get("play_url")))
    check("图文也带话题", dg["tags"] == ["旅行"], str(dg["tags"]))

    print("[4] 小红书：__INITIAL_STATE__ 解析")
    x = lib_xhs.parse_share(XHS_HTML)
    check("标题", x["title"] == "三句话讲完", x["title"])
    check("作者", x["author"] == "小红书账号", x["author"])
    check("时长", x["duration"] == 48.0, str(x["duration"]))
    check("取 h264 masterUrl", x["play_url"].endswith("/abc.mp4"), x["play_url"])
    check("话题", x["tags"] == ["效率", "副业"], str(x["tags"]))
    check("收藏数（字符串原样）", x["stat"]["collect"] == "3000", str(x["stat"]))
    check("类型 video", x["type"] == "video", x["type"])

    print("[5] 小红书：图文笔记走图集分支")
    xg = lib_xhs.parse_share(XHS_IMAGE_HTML)
    check("kind=images", xg["kind"] == "images", xg["kind"])
    check("三种图片字段都能取", len(xg["image_urls"]) == 3, str(xg["image_urls"]))
    check("第二张走 url 字段", xg["image_urls"][1].endswith("/2.jpg"), xg["image_urls"][1])
    check("第三张走 infoList[].url", xg["image_urls"][2].endswith("/3.jpg"), xg["image_urls"][2])
    check("图文无 play_url", not xg.get("play_url"), str(xg.get("play_url")))

    print("[6] 平台识别（不联网）")
    import video_digest as V

    cases = [
        ("https://www.douyin.com/video/7391000000000000000", "douyin"),
        ("https://v.douyin.com/iRNBho6u/", "douyin"),
        ("https://www.xiaohongshu.com/explore/66aa11bb22cc33dd44ee55ff?xsec_token=AB", "xhs"),
        ("https://xhslink.com/a/abcDEF", "xhs"),
        ("https://www.tiktok.com/@user/video/7300000000000000000", "tiktok"),
        ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
        ("https://www.bilibili.com/video/BV1t8oAYuEVf", "bilibili"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://weixin.qq.com/sph/AC7XUrwG7z", "wxchannels"),
    ]

    # 本地图片：用临时目录造一张图
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "1.jpg").write_bytes(b"\xff\xd8\xff\xd9" + b"0" * 4096)
    cases = cases + [(str(tmp), "local-images"), (str(tmp / "1.jpg"), "local-images")]
    for url, want in cases:
        try:
            got = V.detect(url)
        except SystemExit as e:
            got = f"SystemExit({e})"
        check(f"{want:<11} ← {url[:46]}", got == want, f"得到 {got}")

    print()
    if FAILED:
        print(f"× {len(FAILED)} 项失败：" + ", ".join(FAILED))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
