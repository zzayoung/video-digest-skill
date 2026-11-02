# TikTok：链路、限制与排错

> ⚠ **状态说明**：本机环境无法访问 tiktok.com，本链路**未经真实网络验证**。
> 好处是它几乎全部依赖 yt-dlp，而 yt-dlp 的 TikTok 抽取器由社区持续维护，
> 所以首次联网大概率可用；不可用时优先升级 yt-dlp，而不是改本项目代码。

## 为什么不自己写解析

TikTok 的播放地址由 `webapp-prime` 接口下发，带 `msToken` / `X-Bogus` / `_signature`
多重签名，且算法随版本更换。社区维护这条链路，自己实现只会更快过期。
所以本模块是**薄封装**：协议交给 yt-dlp，我们只做归一化与降级。

## 链路

```
vm.tiktok.com/xxx ──curl -L──▶ tiktok.com/@user/video/<id>
                                    │
                    yt-dlp extract_info(download=False)
                                    │
        title / uploader / duration / width / height / view_count ...
                                    │
                    yt-dlp download（mp4/bv*+ba/b）
```

降级顺序：

1. **yt-dlp 取元信息**（含无水印直链、作者、时长、封面）
2. 失败 → **oEmbed**（`www.tiktok.com/oembed?url=`）只取标题/作者/封面——拿不到视频，
   但足够先写 outline 的结构
3. 仍失败 → 明确报错，提示 `--cookie`

## 字幕

yt-dlp 有时能报告字幕轨（`subtitles` / `automatic_captions`），当前版本**没有接入**，
一律走本地 ASR。想省时间可以在 `lib_tiktok.video_info()` 里读 `info["subtitle_langs"]`
后再决定是否走 `subs`，但要注意 TikTok 的自动字幕语言常与口播语言不一致，
**不要默认拿它当主依据**（与 YouTube 的 `-orig` 原则一致）。

## 已知边界

- **地区限制**：部分视频只在特定地区可播，报错通常是 403 / 空响应。
- **私密与好友可见**：必须登录态。
- **图文（photo mode）**：yt-dlp 能识别但产出多图，本项目当前只处理视频。
- **限流**：短时间内大量请求会要求验证，表现为 `Sign in to confirm you're not a bot`。

## 什么时候需要 --cookie

```bash
python run.py all "https://vm.tiktok.com/ZMxxxx/" -o ./work --cookie "sessionid=...; tt_chain_token=..."
```

cookie 通过 yt-dlp 的 `http_headers.Cookie` 传入，不落盘。

## 排错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `yt-dlp 取元信息失败` | 版本旧 / 地区限制 | `pip install -U yt-dlp` 再试 |
| `Sign in to confirm...` | 触发风控 | 加 `--cookie` |
| 下载得到 0 字节 | 直链过期或地区墙 | 换网络；升级 yt-dlp |
| 落到 oEmbed 兜底（只有标题） | 元信息取不到 | 只能先写 outline 结构，下载仍需 cookie |
| `认不出 TikTok 视频 ID` | 短链未展开 | 用 `vm.tiktok.com` 短链或完整 `@user/video/<id>` |
