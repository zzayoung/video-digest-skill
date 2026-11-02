# 贡献指南

这个项目最有价值的资产不是代码，而是 `references/pitfalls.md`——每一条都是踩过的真坑。所以贡献的首要形式是**补充踩坑记录**，其次才是功能。

## 目录约定

| 路径 | 职责 | 改动注意 |
|---|---|---|
| `SKILL.md` | 给 Agent 读的流程与规则 | 改流程必须同步改这里，否则 Agent 会按旧流程走 |
| `references/` | 人读的踩坑与设计规范 | 新增坑请标 ✓（已修复）或 ⚠（仍可能踩到） |
| `scripts/video_digest.py` | CLI 统一入口 | 新增子命令请同时更新 `SKILL.md` 的快速开始 |
| `scripts/make_page.py` | 页面生成器（样式与交互唯一来源） | **不要再引入第二套 CSS**，见 `references/design.md` |
| `scripts/lib_*.py` | 各平台取数与签名 | 每个平台一个文件，互不影响 |

## 本地开发

```bash
python scripts/setup_env.py --check     # 环境自检
python run.py build --schema            # 看 outline 字段
python scripts/make_page.py examples/outline.example.json -o /tmp/out   # 只测渲染，不需要视频
```

改完 `make_page.py` 一定要跑一次渲染并截图核对（见 `references/design.md` 的验收清单）。

## 提 PR 之前

- [ ] `python -m py_compile scripts/*.py run.py` 通过
- [ ] 用 `examples/outline.example.json` 渲染一次，四件套齐全
- [ ] 改到页面样式的，附一张截图（亮色 + 暗色各一）
- [ ] 改到平台链路的，说明实测环境与失败现象
- [ ] 不提交任何视频文件、逐字稿、Cookie 或登录态

## 提交信息

用 Conventional Commits：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`。
涉及平台的加 scope，例如 `fix(bili): qn=32 降级未命中时给出明确错误`。

## 新增一个平台

1. 在 `scripts/` 加 `lib_<平台>.py`，实现「元信息 / 取媒体 / 文稿来源」三件事
2. 在 `video_digest.py` 的 `detect` 与 `all` 里挂上分支
3. 在 `references/` 加一份链路说明，把限流、签名、风控写清楚
4. 更新 `SKILL.md` 的平台差异表
5. 用真实视频跑通全链路后再提 PR——只测 happy path 的接入会在别人机器上炸
