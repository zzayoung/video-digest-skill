# 专题页设计系统与验收规范

> **这是产出物的质量基线。** 样式与交互全部内联在 `scripts/make_page.py`，
> `build` 时自动注入 `<style>` / `<script>`，产出是单文件可分发的 HTML。
>
> 一句话原则：**你只写 `outline.json`，不写 CSS、不写 HTML、不写 JS。**

---

## 一、为什么是这样

早期每个专题页单独写 CSS，改一次版式要动 N 个文件，风格还会慢慢漂移（页面从「工作笔记」滑向「后台管理系统」）。
现在把样式与交互沉到生成器里：改版只改 `make_page.py` 一处，历史页面重新 `build` 即对齐；内容侧只保留语义结构。

**不要另起第二套样式**（不要再放 `assets/page.css`）：两套必然分叉，一次改动只落到一半页面。

---

## 二、设计变量

所有颜色/圆角/阴影走 CSS 变量，暗色主题只覆盖变量，不写第二份组件样式。

| 变量 | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--bg` | `#f7f6f2` 暖白纸 | `#111315` | 页面底色 |
| `--surface` | `#ffffff` | `#181b1e` | 卡片、表格底 |
| `--surface-2` | `#fbfaf7` | `#1d2125` | 引用块、隔行、内嵌块 |
| `--ink` / `--ink-2` | `#191a1c` / `#3d4045` | `#e8e9ea` / `#c8cbd0` | 正文两档 |
| `--muted` / `--faint` | `#6b7076` / `#9aa0a6` | `#98a0a7` / `#6d757c` | 次要文字 / 注释 |
| `--line` | `#e4e0d7` | `#2a2f34` | 分隔线、描边 |
| `--accent` | `#14556e` 深青 | `#6cc0d8` | 主色：链接、序号、强调 |
| `--accent-soft` | `#e9f2f6` | `#16282f` | 导语块、激活态底 |
| `--danger` / `--warning` | `#a8322c` / `#a9761c` | `#e07b74` / `#d9a848` | 踩坑块 |
| `--radius` | `14px` | 同 | 卡片圆角 |
| 字体 | 系统无衬线栈 | 同 | 中文优先 PingFang / 微软雅黑 |

字号层级：`h1 clamp(23–31px)` / 章节 `h3 20.5px` / 正文 `15px` / 表 `13.5px` / 注 `12.5px`。

---

## 三、outline 字段 → 页面组件

| outline 字段 | 渲染成 | 位置 |
|---|---|---|
| `meta.title` / `subtitle` | `<h1>` + 副标题 | 页头 |
| `meta.mode` / `platform` / `duration` / `date` | 胶囊 chips（mode 用主色） | 页头 |
| `meta.author` / `url` | 元信息行 | 页头 |
| `tldr` + `thesis` | 核心结论卡（左侧主色竖条） | 正文第一屏 |
| `sections[].gist` | 架构图节点标题 | 架构图 |
| `sections[].lead` | 导语块（淡主色底） | 章节头下 |
| `sections[].paras` | `<p>`，支持 `**粗体**` / `` `代码` `` | 章节正文 |
| `sections[].table` | 表格 + caption + 复制按钮 | 章节内 |
| `sections[].cards` | 自适应小卡片网格 | 章节内 |
| `sections[].quote` | 引用块 + 来源 + 🕒 | 章节内 |
| `sections[].figs` | `<figure>` + 图注 + 🕒，可点开放大 | 章节尾 |
| `pitfalls` | 红色踩坑块，独立成节 | 正文后 |
| `takeaways` | 可执行结论卡 | 更后 |
| `glossary` | 术语表（两列表格） | 最后 |
| `analysis` | 「方法论反向拆解」节（含两张表） | 架构图之后 |

组件写作约定：

- 表格**必须**走 `table` 字段（不要用 `paras` 里手工排 `|`）。只有 `table` 才会挂「复制表格」按钮。
- 图注 `cap` 一句话，时间码交给 `t` 自动渲染，别手写 `🕒`。
- 卡片 `h` 控制在 6 字内，`p` 一句话；超过会自动换行破坏栅格。
- `gist` ≤ 38 字，架构图节点会裁。

---

## 四、必做交互（已内置，别重复造）

| 功能 | 实现要点 |
|---|---|
| 主题切换 | 右上角 `#themeBtn`，**默认跟随系统** `prefers-color-scheme`，点击后写 `localStorage['vd-theme']` |
| 阅读进度 | 顶部 `#progress`，宽度 = 滚动百分比，3px 渐变 |
| 章节高亮 | 滚动时给 `nav.toc a.on` 加当前章节样式 |
| 图片放大 | 点 `figure img` 填充 `#lightbox`，`Esc` / 点空白关闭，关闭时恢复 `body.overflow` |
| 表格复制 | 每个 `.tw` 动态插 `.copy-btn`，输出 TSV；`navigator.clipboard` 失败回落到 `execCommand` |
| 回到顶部 | `#toTop` 滚动 520px 后 `opacity` 显隐 |

### 全文稿页额外

- 搜索：输入即过滤，命中词包 `<mark>`，右上角显示「N 段命中」；
- `/` 聚焦搜索框、`Esc` 清空并失焦；
- 左侧章节侧栏跟随滚动高亮；
- 点时间码平滑定位到该段；
- 逐字稿动辄上千段，**没有搜索基本不可用**，这项不能省。

---

## 五、SVG 架构图规范

1. **用 `<img>` 引用，不用 `<object>`**：object 按固有像素显示，宽屏下右侧留白；`<img>` 按 viewBox 比例自适应。
2. **不写死容器高度**：靠 `width:100%;height:auto`。
3. **画完回算 viewBox 高度** ≥ 内容最底 `y + 20`。
4. **`font` 简写属性在 SVG 里无效**，必须拆 `font-family` / `font-size` / `font-weight`。
5. 单行文字长度：11.5px 字号下，192px 宽栏约 14 个中文字，600px 通栏约 50 字。
6. 配色沿用页面语义色（主色 `#14556e`、警示 `#a8322c`、中性 `#f1efe8`），**SVG 是独立浅色文件**，暗色主题下呈现为浅色块属预期。

---

## 六、验收清单

- [ ] `build` 四件套齐全，无报错、无 `[warn]`
- [ ] 全页截图看过首屏、架构图、至少一个表格区
- [ ] 架构图底部不裁、徽章数字是白字
- [ ] 表格 hover 出「复制表格」，点一下真能复制
- [ ] 关键帧能点开放大，`Esc` 能关
- [ ] 主题钮切暗色后：卡片、表格、引用块全部跟着变，**没有白底黑字残留**
- [ ] 刷新后主题保持
- [ ] 目录点击能跳、滚动时高亮跟随
- [ ] 全文稿页搜一个高频词，有过滤 + 高亮 + 段数统计
- [ ] 375px 窄屏无横向溢出（表格自己横向滚）
- [ ] `Ctrl+P` 打印预览里没有导航、进度条、浮动按钮

---

## 七、自测命令

```bash
# 生成
python scripts/make_page.py work/outline.json -o work/out --transcript work/asr_segments.json

# 截图（必须输出到 %TEMP%，写工作区目录会被拒）
MSEDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
"$MSEDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="C:\\Users\\<你>\\AppData\\Local\\Temp\\p.png" \
  --window-size=1280,2600 "file:///C:/path/to/page.html"
```

窄屏验收用 iframe 探针（本机 DPI 缩放下 `--window-size=390` 会得到 477 的布局视口，截图会被裁，容易误判）：

```html
<iframe src="page.html" style="width:375px;height:1200px"></iframe>
<script>
// scrollWidth === clientWidth 即无横向溢出
</script>
```
