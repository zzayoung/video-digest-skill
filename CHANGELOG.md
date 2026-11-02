# 更新日志

本项目从两个分支合并而来：`bilibili-video-digest`（B 站单平台 + 自建设计系统）与
`video-digest v1.0`（四平台 + outline 生成管线）。下列版本按合并后的主线记录。

## v2.0 — 2026-11-02

**四平台能力 × 设计系统，合并为一个技能。**

新增
- 四平台统一入口：B 站 / YouTube / 微信视频号 / 本地视频文件，`all` 自动按平台选路
- `outline.json` 驱动的内容管线：`build` 一次产出 HTML + SVG + 表格版 + 全文稿
- 视频号链路：借 `wx-downloader` + 登录态换 CDN 地址，默认 `--login-mode forbid` 不阻塞 Agent
- YouTube 字幕直取，默认原语音轨 `-orig`，避免机翻字幕污染结论
- `run.py` 解释器回退链：`VD_PY` → 技能 `.venv` → WorkBuddy 自带环境 → 当前解释器
- 设计系统并入生成器：暖白 + 深青配色、亮暗双主题、阅读进度条、目录跟随高亮、
  关键帧灯箱、表格一键复制 TSV、回到顶部
- 全文稿页：命中高亮 + 「N 段命中」计数 + `/` 聚焦 + `Esc` 清空
- `references/design.md`：outline 字段 → 页面组件映射、验收清单

修复
- 窄屏 `grid-template-columns:1fr` 被表格 min-content 撑破导致横向溢出，改为 `minmax(0,1fr)`
- 暗色主题下 `.pit` 提示块与表格描边对比度不足
- SVG 架构图在暗色页面中出现亮色块被误判为 bug，明确为预期行为并写入文档

## v1.0 — 2026-10

- 四平台下载与转写链路打通（B 站 / YouTube / 视频号 / 本地）
- `outline.json` + `make_page.py` 内容与呈现解耦
- `setup_env.py` 一键装环境，`doctor` 分平台自检

## 2026-10-19（B 站分支）

- 抽出 `assets/page.css` + `assets/page.js` 作为共享设计系统（v2.0 已并入生成器）
- 新增 `--mode learn / analysis` 双输出方向
- 全文稿页加入搜索过滤

## 2026-09-03（起点）

- B 站单平台版本：playurl 取流、wbi 签名、本地 ASR、抽帧、专题页生成
