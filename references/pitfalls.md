# 常见陷阱与修复（通用 + B 站）

> 经 2026-09-03 / 2026-10-13 / 2026-10-19 / 2026-11-02 真实任务验证。**已修复项标 ✓；仍可能踩到标 ⚠。**
>
> 分工：本文覆盖通用链路与 B 站；YouTube 见 `youtube.md`，视频号见 `wxchannels.md`。

## ✓ 网络层

- **api.bilibili.com 的 HTTPS 在本环境被 SNI 掐断**（代理隧道 200 OK 但 TLS 立刻 RST）。**修复**：lib_bili._curl 内置「解析 IP → https://<ip>/path + -H "Host: 原域名" + -k」直连。
- **.hdslb.com / .bilivideo.com（B 站 CDN）永远可达**，但 bilibili.com 主域要靠 IP 绕。
- **proxy 出口：localhost 代理为 127.0.0.1:55958**（系统级），curl 自身能走，直接用。

## ✓ playurl 四道闸门（缺一不可）

1. **TLS 指纹** —— 普通 curl 必失败，必须 `curl_cffi.requests.get(..., impersonate="chrome124")`。
2. **应用层指纹头** —— sec-ch-ua / sec-fetch-* / Origin / Accept-Encoding: gzip 缺一不可，缺则返 v_voucher 闸门。
3. **凭证挑战** —— 首次请求只回 `v_voucher`，必须把它原样回传再请求一次才给 dash。
4. **qn 降级** —— 未登录态 qn=80/64 会被静默降级成空 dash，必须退到 qn=32（480P）才真正返回流。
   - 实测 480P 流：avc1 308kbps / 135kbps 音频

## ✓ wbi 签名要点

- 密钥来源是 **nav 接口的 wbi_img.img_url + sub_url** 的文件名去 .png 拼接为 64 字符 raw key
- 千万别从 buvid 取，那是另一套
- 公式：`mixin_key = "".join(raw[i] for i in MIXIN_TAB)[:32]`
- 排序 + URL 编码（`!'()*` 必须转义）+ 追加 `wts` + `w_rid = md5(query + mixin)`

## ✓ 流下载

- **断点续传** `-C -`
- **停滞检测** `--speed-limit 1024 --speed-time 30`（**关键**，否则单次卡 15 分钟，累计 36 分钟零产出）
- **m4s 下载**也要带 Referer + Cookie，否则 403

## ✓ DASH 拼接

- 优先 avc1（兼容性最好），取最大 width 的那条
- 音频默认取 30280（~135kbps），人声够用且体积小

## ✓ 字幕探测

- `x/player/v2` 看 `subtitles[0].subtitle_url`
- 链接是 `//aisubtitle.hdslb.com/...`，需补 `https:`
- 真正可用的极少，B 站只有 UP 主主动上传的硬字幕，没有 AI 字幕的接口

## ✓ 抽帧与时间码

- 帧号 i ↔ 时间 `(i-1)×every`（every=20 时）。**但生成 outline 时一律查 `frames/index.json`**，别自己算——every 不整除时长时必错位。
- 抽 10 张左右够用，480P 单张约 20-30KB，整套 `frames/` 约 235-323KB。
- **口播型视频要点**：画面可能全程同一机位，此时优先找三类帧——①章节标题卡（黑底大字）②软件界面/图表 ③字幕金句。这三类才有信息量。

## ✓ 生成器与页面（2026-11 合并版新增）

- **样式只改 `scripts/make_page.py`**：`build` 会把 CSS/JS 内联进每个产出页。不要另建 `assets/page.css` 之类的第二套，两套必然漂移。
- **移动端横向溢出**：`@media` 里 `grid-template-columns:1fr` 会被表格的 min-content 撑破，必须写 `minmax(0,1fr)`（主页面与全文稿页都要）。
- **暗色主题自测**：直接给 `<html>` 加 `data-theme="dark"` 没用——JS 会按 `localStorage`/系统偏好重设。要测就把 `applyTheme(saved)` 临时改成 `applyTheme('dark')`。
- **SVG 在暗色下是浅色块**：架构图是独立文件、自带浅色配色，属预期。别对它加 `filter: invert()`。
- **灯箱绑的是 `figure img`**：自定义 `diagram` 或别处的 `<img>` 不参与放大，要放大就包进 `<figure>`。

## ✓ SVG 内嵌与 viewBox（2026-10-13 新增，两次都踩）

- **`<object>` 写死 height 一定会裁切 SVG**。SVG 按**宽度**缩放，实际渲染高度 = `viewBox高 × 容器宽 / viewBox宽`。
  **修复**——生成器统一用 `<img>`（按 viewBox 等比自适应），不要 `<object>` + 固定 height。
- **画完 SVG 必须回算 viewBox 高度**：`viewBox高 ≥ 内容最底 y 坐标 + 20`。曾把内容写到 y=808 却声明 748，底部两行结语被裁。
- **文字宽度自查**：三栏布局（192px 宽、内边距 24px）用 11.5px 字号时，中文每行约 14 字；通栏 600px 约 50 字。超了会溢出 viewBox。

## ✓ SVG 不支持 `font` 简写属性（2026-10-19 新增）

`<text font="600 12px system-ui">1</text>` 是**无效**的——`font` 简写只能写在 `<style>` 里，不能作为 XML 属性。结果徽章数字变成默认黑色大字，盖在深色圆上完全看不见。

```svg
<!-- ✅ 正确写法 -->
<text font-family="system-ui" font-size="12" font-weight="600" fill="#ffffff">1</text>
```

## ✓ CSS 作用域踩坑：`.pit b { display:block }`

给提示块标题加 `display:block` 时，如果选择器是 `.pit b`（不带子选择器），会**连带影响块内的行内强调**，把句子劈成多段。

**修复**：用 `.pit > b`（或 `:first-child`），只作用于直接子元素。行内 `<b>` 保持 inline。

## ✓ 渲染验证

- **Edge headless 截图的 `--screenshot` 必须给 Windows 反斜杠绝对路径**，且**不能写进工作区目录**（`Failed to write file ... 拒绝访问 (0x5)`）。统一输出到 `%TEMP%` 再 `ViewImage`。
- 可执行文件在 `/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`；`/c/Program Files/` 下**没有**。
- 验证渲染是必做环节——本次正是靠截图才发现 SVG 被裁切、徽章字体失效、callout 断行，肉眼读源码看不出来。
- **检查页面中段**：headless 只截首屏，用 `--window-size=1200,9000` 整页截图，再用 PIL 裁剪到目标区域看：
  ```python
  from PIL import Image
  Image.open('_full.png').crop((0, 3550, 1200, 4700)).save('crop.png')
  ```
- **窄屏验收不要只信 `--window-size`**：本机 DPI 缩放下请求 390 会得到 477 的布局视口，截出来的图被裁一半，看着像溢出其实是误判。用 iframe 探针测真实溢出：
  ```js
  // 页面里嵌 <iframe src="page.html" style="width:375px">，然后读
  // innerDoc.documentElement.scrollWidth === clientWidth 即无溢出
  ```

## ✓ bash 里的 Python

- `python -c "..."` 遇中文/引号极易被 bash 吃掉，报 `syntax error near unexpected token`。**一律改用 `python << 'PYEOF'` heredoc。**

## ⚠ 仍然可能踩到

- **playurl 偶发第一次拿不到 dash** —— 已内置 voucher 二次握手 + qn 降级
- **下载停滞** —— 已加 `--speed-time` 兜底
- **Python 3.13 venv** —— 创建时用 `C:/...` 形式路径，不要用 `/c/...`
- **后台进程静默死亡** —— `nohup ... &` 在某些 shell 下会被 reaper 杀掉。**用 Bash 工具的 `run_in_background=true` 替代**，它有真后台守护
- **ASR 速度比文档慢** —— 文档记的 4x 实时是短 prompt 下的乐观值。2026-10-13 用较长领域术语 prompt 实测 3.07x（46 分钟视频耗时 15 分 12 秒）。别据此判断任务卡死

## ⚠ 暂不支持（B 站）

- 会员/付费视频（403/-104）
- 字幕嵌入（只能外挂）
- 4K/1080P（未登录最高 480P，登录态本环境读不到 Edge cookie 库）
