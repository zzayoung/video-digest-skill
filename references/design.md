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
| `analysis` | 旧字段，等同 `replicate` | — |
| `replicate` | 制作线：三档视图 + 逐节配对 + 清单 | 与学习线并存 |
| `gallery` | 图集：网格 + 逐图说明 + 视觉配方 + 文案结构 | 结论之后、骨架图之前 |

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
- [ ] （有 replicate 时）三档视图切换正常，`1/2/3` 快捷键有效，刷新后停在原视图
- [ ] （有 replicate 时）学习侧「看这段怎么拍的」与制作侧「‹ 看它讲了什么」互跳都能落到对应位置
- [ ] （有 replicate 时）对照视图两栏并排、窄屏堆叠，无内容重叠
- [ ] （有 replicate 时）清单勾选进度刷新后仍在（`localStorage`，按 slug 分键）
- [ ] （有 replicate 时）「复制这段」只复制当前段口播稿

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


---

## 八、双视图：学习线 × 制作线

### 8.1 为什么不是两套页面

同一个视频有两个读法，但**内容只有一个**。如果生成两个独立 HTML，会出现三个问题：
改一处内容要改两份、两张页面的章节号会漂移、用户没法并排对照。
所以做法是：**同一节 = 一个 `<section class="pair">`，里面装两个 pane**，靠 `body[data-view]` 控制显隐。

```html
<section class="pair" id="s1">          <!-- 锚点唯一，三种视图共用 -->
  <div class="pane learn">…学习内容…</div>   <!-- 蓝色顶条 -->
  <div class="pane repl">…制作节拍…</div>    <!-- 琥珀顶条 -->
</section>
```

三种视图只是 CSS：

| `body[data-view]` | 效果 |
|---|---|
| `learn` | 隐藏 `.pane.repl` 与 `.only-repl` |
| `replicate` | 隐藏 `.pane.learn` 与 `.only-learn` |
| `compare` | 两者都显示，`.pair` 变两列；≤1080px 堆叠为单列 |

`only-learn` / `only-repl` 用于不属于某一节的全局块（TL;DR、骨架图 vs 镜头表、清单）。

### 8.2 配对键

`replicate.beats[].ref` = `sections[].id`。配对成功后：

- 学习侧标题旁出现 `看这段怎么拍的 ›`（`data-view-jump="replicate"` + `data-anchor="s1"`）
- 制作侧出现 `‹ 看它讲了什么`（反向）
- 目录该章节后加 `↔`
- 没配对上的章节在制作侧显示「这一节在制作线上没有对应动作」

**不要**用序号配对（第 3 个 beat 配第 3 个 section）——短视频的节拍数与章节数经常不等，
一处插入就会整体错位。

### 8.3 必做交互

| 功能 | 实现要点 |
|---|---|
| 三档切换 | `.viewbar .seg button`，`aria-selected` 表示当前；`localStorage['vd-view-<slug>']` 记忆 |
| 快捷键 | `1/2/3`；输入框内不触发（判断 `tagName`，不要用 `e.target.matches`——`document` 上没有这个方法） |
| 视角互跳 | 事件委托 `[data-view-jump]`，切视图 + 平滑滚到锚点，偏移 96px 避开吸顶条 |
| 执行清单 | `input[type=checkbox][data-ck]`，`localStorage['vd-ck-<slug>']` 存 `{c1:true}`；进度条宽度 = 完成比 |
| 口播稿复制 | `[data-copy="#sc-1"]`，复制目标节点的 `innerText`，复制后按钮文案变「已复制」1.5s |

### 8.4 排版注意

- 对照视图下**隐藏知识骨架图**（`.diagram.only-learn`）：它和左侧目录信息重复，会把对照区推下去一屏。
- 制作侧标题用 `R01` 而不是 `01`，避免与学习侧编号混淆；标题后跟章节名（12.5px，`--faint`）。
- 节拍块用 `--warn` 系配色（琥珀），学习侧用 `--accent`（深青），两栏一眼可辨。
- `compare` 的 `.pair` 用 `align-items:start`，两侧高度不等时不要拉伸。


---

## 九、图集页（图文作品）

### 9.1 为什么单独一套

视频的阅读单位是**段落**，图集的阅读单位是**图**。把 9 张图塞进 `sections[].figs` 会退化成
「一坨图 + 一段文字」：看不出九宫格的排布意图，也没法逐图对照它为什么这么拍。

所以图集是独立区块：网格负责「看」，下方逐图列表负责「读」。

### 9.2 DOM 结构

```html
<section id="gallery">
  <div class="shead">▦ 图集（6 张）</div>
  <div class="lead">这组图的用途</div>
  <div class="gal grid c3">
    <figure class="tile">
      <span class="cvr">封面</span>
      <img src="images/01.jpg" data-cap="图注" data-idx="1">
      <figcaption><span class="idx">01</span><span>图注</span><span class="role">封面</span></figcaption>
    </figure>…
  </div>
  <div class="gnotes">           <!-- 逐图说明：同图两解 -->
    <div class="gn"><span class="gn-no">01</span><div>
      <h4>图注<span class="grole">封面</span></h4>
      <p class="g-note only-learn">学习线：这张在说什么</p>
      <p class="g-design only-repl">制作线：为什么这么做</p>
    </div></div>…
  </div>
  <div class="rblock only-repl" id="recipe">视觉配方表</div>
  <div class="rblock" id="copy">文案结构</div>
</section>
```

`g-note` / `g-design` 复用双视图的 `only-learn` / `only-repl` 规则——
不额外发明机制，图集自然继承三档视图。

### 9.3 排版规则

| 规则 | 做法 | 为什么 |
|---|---|---|
| 列数 | 按张数：≤2 两列、≤6 三列、>6 四列 | 6 张摆 3×2 才像九宫格，摆 4 列会留一排空缺 |
| 缩略图比例 | `aspect-ratio:3/4` + `object-fit:cover` | 不统一比例会让网格参差 |
| 封面角标 | 左上角实心 chip，只在 `cover` 那张出现 | 让读者知道哪张是被投放的封面 |
| 逐图说明 | 44px 序号列 + 内容列，分隔线只画虚线 | 和图注形成"编号—解释"的对应关系 |
| 灯箱 | 支持 `←` `→` 翻页、`n / N` 计数、底部图注渐变条 | 九宫格逐张点开翻页，比关掉再点快得多 |
| 窄屏 | 统一两列，序号列收窄 | 保持可点面积 |

### 9.4 验收补充

- [ ] 图集缩略图比例一致，无拉伸变形
- [ ] 点任意图能进灯箱，`←` `→` 能翻页，`n / N` 数字正确
- [ ] 学习线只出现 `note`、制作线只出现 `design`，对照视图两段都在
- [ ] 视觉配方表只在制作线出现，且可整表复制
- [ ] 图集在没有 `sections` 的 outline 下也能正常渲染
