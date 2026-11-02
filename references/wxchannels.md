# 微信视频号：链路、限制与排错

## 为什么必须借外部工具

视频号分享页 `https://weixin.qq.com/sph/<id>` 的播放地址**不在 HTML 里**：
- 页面是 JS 渲染的，首屏只有骨架
- 媒体地址由前端带签名参数向接口换取的，签名算法未公开且会变
- 服务端会校验请求的上下文（登录态 / 设备指纹）

所以「解析 HTML 找 mp4 地址」这条路走不通，也不该自己维护签名逻辑。

`wx-downloader`（PyPI 包名与命令同名，Python 模块名 `wx_channels_cli`）的做法是：
用**腾讯元宝**的登录 Cookie 请求解析接口 → 拿到真实 CDN 地址 → 直连下载。
不需要微信客户端、不需要抓包代理、不需要 Go 运行时。

## 安装

```bash
# 技能自带 venv 里（推荐，装一次就够）
python run.py wx-status          # 若报缺 wx-downloader，先：
python scripts/setup_env.py      # 或手动：
python -m pip install wx-downloader -i https://pypi.org/simple
```

装到 skill 用的同一个 venv 里最省事：`lib_wx.cli_cmd()` 优先走
`[sys.executable, "-m", "wx_channels_cli"]`，不依赖 PATH，也不受 venv 激活状态影响。

国内镜像（清华等）可能还没同步这个包，报 `No matching distribution found` 时换官方源。

## 登录

```bash
python run.py wx-login --browser msedge
```

- 会开一个**独立的浏览器会话**（不读你日常浏览器的 profile），等 `hy_user` / `hy_token` 出现
- 需要人工扫码或手机号验证，默认等 300 秒
- 凭据落 `~/.config/wx-channels/auth.json`，权限 0600，程序不会打印内容
- 本机没有 Chrome 时用 `--browser msedge`（playwright 复用系统 Edge，省掉下载 Chromium）
- `wx-downloader config set browser msedge` 可持久化，避免每次传参

## 限制（都会以明确报错暴露，不会静默失败）

| 限制 | 现象 | 应对 |
|---|---|---|
| 登录态过期 | 下载报错，提示登录态失效 | 重跑 `wx-login` |
| 非 `sph` 链接 | `parse_share` 直接拒绝 | 只支持 `weixin.qq.com/sph/...` |
| 公众号文章 / 直播 / 图集 | 不支持 | 无替代方案 |
| 微信内短口令 | 不支持 | 先在微信里打开、复制"复制链接"得到的 URL |
| 无字幕轨 | 一定走 ASR | 属正常，不是故障 |
| 接口变更 | 全量失败 | `pip install -U wx-downloader` |

## 与 skill 的集成要点

1. **元信息只能从下载产物反推**：`.wx-<hash>.json` 里有 `author` / `description` / `bytes`，
   标题则从文件名去掉 `_<hash>` 后缀取得。所以 `info` 在下载前只能给出 share id。
2. **成品名不符合 `video.*` 约定**（是「中文标题_哈希.mp4」），
   `_find_video()` 靠 `.wx-*.json` 里的 `source_url` 匹配定位文件。
3. **去重靠 `.wx-*.json`**：删了这些记录，下次会当新文件重新下载。
4. **`all` 默认 `--login-mode forbid`**（等价 CLI 的 `--no-login`），
   凭据不可用立刻失败，避免 agent 卡在等扫码上；交互场景显式传 `--login-mode auto`。
5. 视频号视频**一律同时下音视频**：抽帧需要视频流，而 `wx-downloader` 也没有"只下音频"的选项。

## 合法性边界

工具仅供个人学习/研究用途。转载、二次分发、商用前请确认原作者授权与平台规则，
专题页里的引用请保留作者与来源链接（`meta.author` / `meta.url` 会被渲染到页面上）。
