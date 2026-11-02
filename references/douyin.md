# 抖音：链路、限制与排错

> ⚠ **状态说明**：本机环境（代理只放通部分域名）无法访问 douyin.com，因此这份文档里的
> 解析规则来自公开页面结构与既有实测经验，**首次在可联网环境使用时请按下方「校准」一节
> 核对一遍**。解析函数已用离线夹具锁住已知形状（`tests/test_parsers.py`）。

## 为什么不用官方详情接口

`/aweme/v1/web/aweme/detail/` 需要 `a_bogus` 签名（JS 混淆 + 设备指纹 + 时间戳），
自己实现成本高、且随前端版本失效。**分享页**（`iesdouyin.com/share/video/<id>`）是给
浏览器和微信内置浏览器用的，HTML 里直接带 `_ROUTER_DATA`，匿名可读——这是目前最省事的入口。

## 链路

```
短链 v.douyin.com/xxx  ──curl -L──▶  https://www.douyin.com/video/<aweme_id>
                                          │
                iesdouyin.com/share/video/<id>（移动 UA）
                                          │
                 window._ROUTER_DATA = {...}  ← 从 HTML 里抠 JSON
                                          │
        loaderData["video_(<id>)/page"].videoInfoRes.item_list[0]
                                          │
   video.play_addr.url_list[0]  ──(playwm → play)──▶  无水印 CDN 直链
```

关键字段：

| 目标 | 路径 |
|---|---|
| 标题 | `desc` 首行（或 `preview_title`） |
| 作者 | `author.nickname` |
| 时长 | `video.duration`（**毫秒**，要 /1000） |
| 分辨率 | `video.width` / `video.height` |
| 播放地址 | `video.play_addr.url_list[]` |
| 封面 | `video.cover.url_list[]` |
| 数据 | `statistics.digg_count / comment_count / share_count / collect_count` |
| 话题 | `desc` 里的 `#话题` |

**`playwm` → `play`**：分享页给的是带水印地址（playwm = play with mark），把路径里的
`playwm` 换成 `play` 即为无水印版。这是长期存在的公开约定，不涉及破解签名。

## 已知边界

- **免登录通常只有 720p**，且部分账号的作品会降级成「仅封面」。
- **私密 / 好友可见 / 已删除** 一律失败，报错会明确说「作品受限」。
- **图文作品**（`images` 而非 `video`）当前不支持，会抛出带说明的 `ShortError`。
- **地区限制**：部分作品只在境内网络可取。
- 频繁请求会触发风控（返回验证页），表现为「分享页返回空内容」。

## 什么时候需要 --cookie

按这个顺序试，绝大多数情况第一步就够：

```bash
# 1) 直接跑
python run.py all "https://v.douyin.com/xxxx/" -o ./work

# 2) 失败再带 cookie（浏览器登录 douyin.com 后从 DevTools 复制整条 Cookie）
python run.py all "https://v.douyin.com/xxxx/" -o ./work --cookie "ttwid=...; passport_csrf_token=...; sessionid=..."
```

`--cookie` 只用于本次请求，不会写进任何文件。

## 校准（首次联网时做一次）

```bash
python run.py info "https://www.douyin.com/video/<id>" -o ./work
ls ./work/debug_douyin_*.html     # 失败时会把原始 HTML 存下来
```

拿到 `debug_*.html` 后：

1. 搜 `_ROUTER_DATA`，确认 `loaderData` 的键名（形如 `video_(<id>)/page`）
2. 确认 `item_list[0].video.play_addr.url_list` 还在
3. 若结构变了，改 `lib_douyin.parse_share()` 里的取值路径，
   并在 `tests/test_parsers.py` 的 `DOUYIN_HTML` 夹具里同步形状

## 排错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `分享页里没有找到作品数据` | 作品删除/私密；或被风控 | 换 `--cookie`；换网络；用浏览器打开确认还能播 |
| `认不出抖音作品 ID` | 贴的不是分享链接 | 用 App「分享 → 复制链接」，含 `v.douyin.com` 短链 |
| 下载 403 | 直链过期（有时效） | 重跑一次；不要复用旧的 `info.json` 里的地址 |
| 下到的是封面图 | 拿到的是图片轨 | 确认是视频作品（不是图文） |
| 速度极慢 | CDN 限速 | 换 `--cookie` 走登录态，通常更快 |
