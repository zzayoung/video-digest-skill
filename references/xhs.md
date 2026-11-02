# 小红书：链路、限制与排错

> ⚠ **状态说明**：本机环境无法访问 xiaohongshu.com，解析规则来自页面结构与既有经验，
> **首次联网请按下文「校准」核对**。已知形状已用离线夹具锁定（`tests/test_parsers.py`）。

## 两个必须知道的坑

**1）链接必须带 `xsec_token`**

新分享链接长这样：

```
https://www.xiaohongshu.com/explore/66aa11bb22cc33dd44ee55ff?xsec_token=ABxxxx&xsec_source=pc_share
```

`xsec_token` 是一次性的访问凭证，缺了会被判定为「当前笔记暂时无法浏览」。
所以解析时**必须保留完整 URL**，不能只抠 note_id 重新拼。

**2）`__INITIAL_STATE__` 不是严格 JSON**

页面里的对象值会出现裸 `undefined`（JS 字面量），直接 `json.loads` 会炸。
`lib_short.json_after(..., undefined_safe=True)` 会先原样解析，失败再把 `undefined`
替换成 `null` 重试。

## 链路

```
xhslink.com/xxx ──curl -L──▶ xiaohongshu.com/explore/<id>?xsec_token=...
                                     │
              window.__INITIAL_STATE__ = {...}   ← 从 HTML 里抠
                                     │
        note.noteDetailMap[<note_id>].note
                                     │
   video.media.stream.{h264|h265|av1}[0].masterUrl  →  masterUrl / backupUrls
```

关键字段：

| 目标 | 路径 |
|---|---|
| 标题 | `note.title`（空则取 `desc` 首行） |
| 作者 | `note.user.nickname` |
| 时长 | `note.video.capa.duration`（秒；>1000 视为毫秒） |
| 分辨率 | `note.video.capa.width/height` |
| 播放地址 | `video.media.stream.h264[0].masterUrl` → `backupUrls[]` |
| 封面 | `video.image.firstFrame` |
| 数据 | `interactInfo.likedCount / collectedCount / commentCount / shareCount` |
| 话题 | `note.tagList[].name` |

`likedCount` 常是字符串（`"1.2万"`），原样保留，不要强转数字。

## 已知边界

- **未登录通常只能拿到 720p 左右的 `masterUrl`**，更高清需要登录态。
- **图文笔记**（`imageList`，没有 `video`）：已支持，走图集分支。图片地址按
  `urlDefault → url → infoList[].url` 的顺序取，兼容新旧三种字段。
- **登录墙**：部分笔记对未登录用户直接返回登录页，报错会提示加 `--cookie`。
- 短链有效期有限，过期需重新复制。

## 什么时候需要 --cookie

```bash
# 1) 直接跑（多数公开笔记不需要登录）
python run.py all "https://www.xiaohongshu.com/explore/<id>?xsec_token=..." -o ./work

# 2) 提示登录墙时
python run.py all "<同上>" -o ./work --cookie "web_session=...; a1=..."
```

`web_session` 是登录态主凭证，从 DevTools → Application → Cookies 里取。

## 校准

```bash
python run.py info "<笔记链接>" -o ./work
ls ./work/debug_xhs_*.html
```

1. 搜 `__INITIAL_STATE__`，确认 `note.noteDetailMap` 还在（旧版是 `noteDetailMap` 直接挂 `note`）
2. 确认 `video.media.stream.h264[0].masterUrl` 的层级
3. 结构变了就改 `lib_xhs.parse_share()`，并同步 `tests/test_parsers.py`

## 排错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `没有找到 __INITIAL_STATE__` | 缺 `xsec_token` / 笔记删除 / 仅自己可见 | 用 App「分享 → 复制链接」重新取 |
| `要求登录（登录墙）` | 该笔记需登录 | 加 `--cookie "web_session=..."` |
| 图集缺几张 | 单张直链过期 | 重跑会补；`images_index.json.failed` 里有清单 |
| 只有 720p | 未登录 | 加 cookie |
| `认不出小红书笔记 ID` | 链接形态不对 | 需要 `xhslink.com` 短链或 `/explore/<id>` |
