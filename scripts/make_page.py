"""outline.json → 专题页四件套（确定性渲染）。

为什么要有这个模块
------------------
之前 HTML 专题页是每次对话现写的，结构、配色、表格样式全凭当场发挥，
同一个人隔一周产出两份风格不同的页面，改一处样式要重新生成整页。

现在把「呈现」从「内容」里分离出来：
  · 内容 → outline.json（结构化数据，agent 只负责填内容）
  · 呈现 → 本模块（固定版式，改样式只改这里，历史页面重新 build 即统一）

产物（默认输出到 outline 同目录）：
  <slug>.html          主专题页（内嵌 SVG 架构图 + 表格 + 关键帧 + 时间码锚点）
  <slug>.svg           可编辑架构图（独立文件，HTML 用 <object> 引用，改完刷新即生效）
  <slug>_table.md      纯表格版（贴飞书 / 腾讯文档 / Excel）
  transcript_full.html 带时间码全文稿（章节锚点 + 全文检索 + 回主页面）

outline.json 字段见 SKILL.md「交付物生成」一节，本文件顶部 _SCHEMA_DOC 也有一份。
"""
import html
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# outline.json 允许的字段（宽松校验：缺的用默认值补，写错的给出明确报错）
# ---------------------------------------------------------------------------
_SCHEMA_DOC = """
{
  "meta": {
    "slug": "wx-AC7XUrwG7z",        // 产物文件名基名（必填或 --name 指定）
    "title": "视频标题",
    "subtitle": "一句话定性",         // 可选
    "author": "作者", "platform": "视频号",
    "url": "来源链接", "duration": "25:41",
    "cover": "frames/f_0001.jpg",    // 可选，相对 outline 所在目录
    "mode": "learn",                 // learn | analysis
    "date": "2026-10-30"
  },
  "tldr": ["结论一", "结论二"],        // 3-6 条，页面顶部要点卡
  "thesis": "全文核心命题",            // 可选，一段话
  "sections": [
    {
      "id": "s1", "title": "章节名",
      "t0": 0, "t1": 180,            // 秒；用于时间码徽标与章节锚点
      "kicker": "背景",               // 可选小标签
      "gist": "一句话概括",            // 可选，架构图节点副标题
      "lead": "章节导语",              // 可选
      "paras": ["正文段落"],
      "bullets": ["要点"],
      "quote": {"text": "原话", "t": 305},
      "table": {"title": "表题", "head": ["列"], "rows": [["值"]]},
      "cards": [{"h": "小标题", "p": "说明"}],
      "figs": [{"src": "frames/f_0003.jpg", "cap": "图注", "t": 40}]
    }
  ],
  "diagram": {                        // 可选；不给就按 sections 自动生成流程骨架
    "title": "架构图标题",
    "style": "flow",                 // flow=自动排布 | manual=用 nodes 的 x/y
    "nodes": [{"id":"a","label":"","sub":"","x":60,"y":80,"w":220,"h":70}],
    "edges": [{"from":"a","to":"b","label":""}]
  },
  "pitfalls": [{"title": "踩坑点", "text": "说明", "t": 120}],
  "takeaways": ["可执行结论"],
  "glossary": [{"term": "术语", "def": "解释"}],
  "analysis": {                       // 仅 mode=analysis 用
    "positioning": "...", "skeleton": "...",
    "methods": ["心法"], "prep": {"选题": ["..."], "素材": ["..."]},
    "template": [{"part": "开场", "how": "..."}]
  }
}
"""

PLATFORM_LABEL = {"wxchannels": "微信视频号", "bilibili": "B 站",
                  "youtube": "YouTube", "local": "本地文件"}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt_t(sec):
    sec = int(float(sec or 0))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _tc(sec, has_tx=True):
    """时间码徽标。有全文稿页时链到对应锚点。"""
    if sec is None:
        return ""
    label = fmt_t(sec)
    if has_tx:
        return (f'<a class="tc" href="transcript_full.html#t-{int(float(sec))}" '
                f'title="跳到全文稿 {label}">🕒 {label}</a>')
    return f'<span class="tc">🕒 {label}</span>'


# ---------------------------------------------------------------------------
# 架构图 SVG
# ---------------------------------------------------------------------------
MONO = ('font-family="system-ui,-apple-system,Segoe UI,Microsoft YaHei,sans-serif"')


def _svg_flow(o, sections):
    """按章节自动生成「叙事骨架」图。

    版式策略：
      · ≤7 个节点 → 单列竖直链，左侧带时间轴（读起来最顺）
      · ≥8 个节点 → 双列蛇形（第 1 列向下、第 2 列向上），高度直接减半；
        时间码改放卡片右上角，否则一条 12 节点的时间轴会把页面拖到两屏高
      · diagram.style == "manual" → 完全按 nodes 里的 x/y/w/h 摆，不参与自动排布
    """
    nodes = []
    if o.get("nodes"):
        for n in o["nodes"]:
            nodes.append({
                "id": str(n.get("id") or len(nodes)),
                "label": n.get("label") or "",
                "sub": n.get("sub") or "",
                "x": float(n.get("x") or 0), "y": float(n.get("y") or 0),
                "w": float(n.get("w") or 300), "h": float(n.get("h") or 74),
                "tone": n.get("tone") or "n",
            })
        manual = True
    else:
        manual = False
        for i, s in enumerate(sections):
            nodes.append({
                "id": s.get("id") or f"s{i+1}",
                "label": s.get("title") or "",
                "sub": s.get("gist") or "",
                "x": 0, "y": 0, "w": 0, "h": 74,
                "tone": "n", "t0": s.get("t0"), "t1": s.get("t1"),
            })

    two_col = (not manual) and len(nodes) > 7
    max_len = 22 if two_col else 30
    sub_len = 26 if two_col else 38

    if manual:
        W = max([n["x"] + n["w"] for n in nodes] + [640]) + 60
        H = max([n["y"] + n["h"] for n in nodes] + [320]) + 60
        top = 0
    elif two_col:
        rows = (len(nodes) + 1) // 2
        gap, w = 46.0, 388.0
        pitch = 96.0
        top = 92.0
        for i, n in enumerate(nodes):
            c, r = i // rows, i % rows
            n["x"] = 52 + c * (w + gap)
            n["w"] = w
            # 两列都自上而下：中文长文里读者习惯scan down，
            # 蛇形（第二列倒序）会让右列出现 12→7 的倒读，得不偿失
            n["y"] = top + r * pitch
        W = 52 * 2 + w * 2 + gap
        H = top + rows * pitch + 40
    else:
        top = 92.0
        for i, n in enumerate(nodes):
            n["x"] = 118
            n["w"] = 452
            n["y"] = i * 104
        W = 640
        H = max(200, len(nodes) * 104 + 96)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'width="100%" {MONO} role="img">',
        '<defs>'
        '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#9aa4b8"/></marker></defs>',
        f'<rect width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>',
    ]

    dtitle = (o.get("title") or "内容骨架")
    parts.append(f'<text x="40" y="42" font-size="16" font-weight="700" '
                 f'fill="#1a1d24">{esc(dtitle)}</text>')
    parts.append(f'<line x1="40" y1="58" x2="{W - 40:.0f}" y2="58" '
                 'stroke="#e3e6ec"/>')

    # 单列才画时间轴；双列的时间码进卡片
    if (not manual) and not two_col and nodes:
        ax = 72
        t_pos = nodes[0]["y"] + top + nodes[0]["h"] / 2
        b_pos = nodes[-1]["y"] + top + nodes[-1]["h"] / 2
        parts.append(f'<line x1="{ax}" y1="{t_pos:.0f}" x2="{ax}" y2="{b_pos:.0f}" '
                     'stroke="#d6dbe6" stroke-width="2"/>')

    idx = {}
    for i, n in enumerate(nodes):
        idx[n["id"]] = n
        n["y"] += top if (not manual) else 0
        fill, stroke, badge = {
            "n": ("#f7f9fd", "#d8e0ef", "#2358c8"),
            "hl": ("#eef4ff", "#b8cdf5", "#1c4bb0"),
            "warn": ("#fff8f0", "#f3d3b3", "#b45309"),
            "ok": ("#f2fbf5", "#c3e6cf", "#137a3c"),
        }.get(n["tone"], ("#f7f9fd", "#d8e0ef", "#2358c8"))
        cx0, cy0, h, w = n["x"], n["y"], n["h"], n["w"]
        mid = cy0 + h / 2

        if (not manual) and not two_col:
            parts.append(f'<circle cx="72" cy="{mid:.0f}" r="7" fill="#fff" '
                         'stroke="#2358c8" stroke-width="2.5"/>')
            if n.get("t0") is not None:
                parts.append(f'<text x="72" y="{mid + 30:.0f}" font-size="11" '
                             f'fill="#8891a3" text-anchor="middle">'
                             f'{fmt_t(n["t0"])}</text>')

        parts.append(
            f'<g><rect x="{cx0:.0f}" y="{cy0:.0f}" width="{w:.0f}" '
            f'height="{h:.0f}" rx="12" fill="{fill}" stroke="{stroke}" '
            'stroke-width="1.5"/>'
            f'<circle cx="{cx0 + 24:.0f}" cy="{mid:.0f}" r="13" '
            f'fill="{badge}" opacity="0.12"/>'
            f'<text x="{cx0 + 24:.0f}" y="{mid + 4:.0f}" '
            f'font-size="12" font-weight="700" fill="{badge}" '
            f'text-anchor="middle">{i + 1}</text>'
            f'<text x="{cx0 + 48:.0f}" '
            f'y="{cy0 + (mid - cy0 - 2 if n["sub"] else mid + 5):.0f}" '
            f'font-size="13.5" font-weight="600" fill="#1a1d24">'
            f'{esc(_clip(n["label"], max_len))}</text>')
        if n["sub"]:
            parts.append(
                f'<text x="{cx0 + 48:.0f}" y="{cy0 + (mid - cy0 + 18):.0f}" '
                f'font-size="11.5" fill="#69748a">'
                f'{esc(_clip(n["sub"], sub_len))}</text>')
        if two_col and n.get("t0") is not None:
            parts.append(
                f'<text x="{cx0 + w - 13:.0f}" y="{cy0 + 21:.0f}" font-size="10.5" '
                f'fill="#98a1b2" text-anchor="end">{fmt_t(n["t0"])}</text>')
        parts.append("</g>")

    edges = o.get("edges")
    if not edges and not manual:
        edges = [{"from": nodes[i]["id"], "to": nodes[i + 1]["id"]}
                 for i in range(len(nodes) - 1)]
    for e in edges or []:
        a, b = idx.get(str(e.get("from"))), idx.get(str(e.get("to")))
        if not a or not b:
            continue
        acx, acy = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
        bcx, bcy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
        # 同列 → 竖直连；跨列 → 水平曲线。比按 style 分支更不容易错。
        if abs(acx - bcx) < 6:
            if bcy > acy:
                x1, y1 = acx, a["y"] + a["h"] + 3
                x2, y2 = bcx, b["y"] - 7
            else:
                x1, y1 = acx, a["y"] - 3
                x2, y2 = bcx, b["y"] + b["h"] + 7
            d = f"M{x1:.0f},{y1:.0f} L{x2:.0f},{y2:.0f}"
        elif two_col and bcy < acy:
            # 左列末 → 右列首：必须走两列之间的空隙上升，
            # 直接连到右列顶部的中心会竖穿整列方框（踩过）
            yb = max(a["y"] + a["h"], b["y"] + b["h"]) + 16
            x1, y1 = acx, a["y"] + a["h"] + 3
            xm = b["x"] - 23                 # 两列之间的走线通道
            x2, y2 = b["x"] - 7, bcy         # 从左侧进入首节点
            d = (f"M{x1:.0f},{y1:.0f} L{x1:.0f},{yb:.0f} "
                 f"L{xm:.0f},{yb:.0f} L{xm:.0f},{y2:.0f} L{x2:.0f},{y2:.0f}")
        else:
            if bcx > acx:
                x1, y1 = a["x"] + a["w"] + 3, acy
                x2, y2 = b["x"] - 7, bcy
            else:
                x1, y1 = a["x"] - 3, acy
                x2, y2 = b["x"] + b["w"] + 7, bcy
            d = (f"M{x1:.0f},{y1:.0f} C{x1 + 30:.0f},{y1:.0f} "
                 f"{x2 - 30:.0f},{y2:.0f} {x2:.0f},{y2:.0f}")
        parts.append(f'<path d="{d}" fill="none" stroke="#9aa4b8" '
                     'stroke-width="1.6" marker-end="url(#ar)"/>')
        if e.get("label"):
            parts.append(f'<text x="{(x1 + x2) / 2:.0f}" y="{(y1 + y2) / 2 - 4:.0f}" '
                         f'font-size="10.5" fill="#98a1b2" text-anchor="middle">'
                         f'{esc(e["label"])}</text>')

    parts.append("</svg>")
    return "".join(parts)


def _clip(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# 主页面 HTML
# ---------------------------------------------------------------------------
CSS = """
:root{
  --bg:#f7f6f2; --surface:#ffffff; --surface-2:#fbfaf7;
  --ink:#191a1c; --ink-2:#3d4045; --muted:#6b7076; --faint:#9aa0a6;
  --line:#e4e0d7; --line-strong:#d3cec2;
  --accent:#14556e; --accent-2:#1d7a8c; --accent-soft:#e9f2f6; --on-accent:#ffffff;
  --ok:#1d6b45; --ok-soft:#e8f4ec; --warn:#a9761c; --warn-soft:#fbf3e2;
  --danger:#a8322c; --danger-soft:#fbeceb;
  --radius:14px; --radius-sm:8px;
  --shadow:0 1px 2px rgba(20,25,30,.04),0 10px 30px -16px rgba(20,25,30,.22);
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
  color-scheme:light;
}
[data-theme="dark"]{
  --bg:#111315; --surface:#181b1e; --surface-2:#1d2125;
  --ink:#e8e9ea; --ink-2:#c8cbd0; --muted:#98a0a7; --faint:#6d757c;
  --line:#2a2f34; --line-strong:#3a4046;
  --accent:#6cc0d8; --accent-2:#8ad4e6; --accent-soft:#16282f; --on-accent:#0b1215;
  --ok:#5fc08c; --ok-soft:#14261c; --warn:#d9a848; --warn-soft:#2a2318;
  --danger:#e07b74; --danger-soft:#2c1b1a;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.7);
  color-scheme:dark;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:78px}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.78 var(--sans);-webkit-font-smoothing:antialiased;
  transition:background .18s ease,color .18s ease}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code{font-family:var(--mono);font-size:.9em;background:var(--surface-2);
  border:1px solid var(--line);border-radius:5px;padding:1px 5px}
/* 阅读进度 */
#progress{position:fixed;top:0;left:0;height:3px;width:0;z-index:100;
  background:linear-gradient(90deg,var(--accent),var(--accent-2));
  transition:width .08s linear}
/* 主题按钮 */
.icon-btn{position:fixed;top:14px;right:18px;z-index:99;width:34px;height:34px;
  display:grid;place-items:center;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:var(--surface);
  color:var(--ink-2);backdrop-filter:blur(8px);transition:.16s;opacity:.92}
.icon-btn:hover{color:var(--accent);border-color:var(--accent);transform:translateY(-1px)}
.icon-btn svg{width:17px;height:17px}
/* 布局 */
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 80px;
  display:grid;grid-template-columns:228px minmax(0,1fr);gap:40px}
/* 头部 */
.hero{grid-column:1/-1;padding:52px 0 30px;border-bottom:1px solid var(--line)}
.eyebrow{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.chip{font-size:12px;padding:3px 10px;border-radius:999px;background:var(--surface);
  border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.chip.mode{background:var(--accent-soft);border-color:var(--accent);
  color:var(--accent);font-weight:600}
h1{font-size:clamp(23px,3.4vw,31px);line-height:1.34;margin:0 0 12px;
  letter-spacing:-.4px;font-weight:700}
.subtitle{color:var(--muted);font-size:15.5px;margin:0 0 18px;max-width:74ch}
.metaline{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--muted)}
.metaline b{color:var(--ink);font-weight:600}
/* 侧栏目录 */
nav.toc{position:sticky;top:24px;align-self:start;font-size:13.5px;
  max-height:calc(100vh - 48px);overflow:auto;padding-right:6px}
nav.toc .ttl{font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--faint);margin:0 0 12px;font-weight:700}
nav.toc a{display:block;color:var(--muted);padding:5px 0 5px 12px;
  border-left:2px solid transparent;line-height:1.5}
nav.toc a:hover{color:var(--accent);border-left-color:var(--line-strong);text-decoration:none}
nav.toc a.on{color:var(--accent);border-left-color:var(--accent);font-weight:600;
  background:linear-gradient(90deg,var(--accent-soft),transparent)}
/* 卡片与章节 */
main{min-width:0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:24px 26px;margin:0 0 22px;box-shadow:var(--shadow)}
.card.tldr{border-left:3px solid var(--accent)}
.card h2{font-size:12.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--faint);margin:0 0 14px;font-weight:700}
.tldr ol{margin:0;padding-left:22px}
.tldr li{margin:9px 0}
.thesis{font-size:16.5px;line-height:1.85;margin:0 0 14px;color:var(--ink-2)}
section{scroll-margin-top:22px;margin:0 0 26px}
.shead{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding:24px 0 10px}
.snum{font-size:12px;font-weight:700;color:var(--accent);background:var(--accent-soft);
  border-radius:7px;padding:2px 8px;letter-spacing:.04em}
.shead h3{font-size:20.5px;margin:0;letter-spacing:-.2px;line-height:1.4;font-weight:680}
.kicker{font-size:11.5px;color:var(--faint);border:1px dashed var(--line-strong);
  border-radius:999px;padding:2px 9px}
.lead{font-size:15.5px;color:var(--ink-2);background:var(--accent-soft);
  border-radius:10px;padding:14px 18px;margin:12px 0 16px}
.bd p{margin:0 0 14px}
.bd ul,.bd ol{margin:0 0 16px;padding-left:22px}
.bd li{margin:6px 0}
blockquote{margin:16px 0;padding:14px 20px;background:var(--surface-2);
  border-left:3px solid var(--accent);border-radius:0 10px 10px 0;color:var(--ink-2);font-size:15px}
blockquote .src{display:block;margin-top:8px;font-size:12.5px;color:var(--faint)}
.tc{font-size:11.5px;color:var(--accent);background:var(--surface);border:1px solid var(--line);
  border-radius:6px;padding:1px 7px;white-space:nowrap;font-variant-numeric:tabular-nums}
/* 表格 */
.tw{position:relative;margin:16px 0;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;line-height:1.62}
caption{caption-side:top;text-align:left;font-size:12.5px;color:var(--faint);padding:0 0 8px}
th,td{border:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top}
th{background:var(--surface-2);font-weight:600;color:var(--ink-2);white-space:nowrap}
tbody tr:nth-child(even){background:var(--surface-2)}
td:first-child{font-weight:500}
.copy-btn{position:absolute;top:6px;right:6px;opacity:0;transition:.15s;
  border:1px solid var(--line);background:var(--surface);color:var(--muted);
  border-radius:6px;padding:3px 9px;font-size:12px;cursor:pointer}
.tw:hover .copy-btn{opacity:1}
.copy-btn:hover{color:var(--accent);border-color:var(--accent)}
.copy-btn.done{color:var(--ok);border-color:var(--ok)}
/* 小卡片网格 */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}
.mini{border:1px solid var(--line);border-radius:11px;padding:14px 16px;background:var(--surface-2)}
.mini b{display:block;font-size:14px;margin-bottom:5px;color:var(--ink)}
.mini span{font-size:13px;color:var(--muted);line-height:1.65}
/* 图 */
figure{margin:18px 0;background:var(--surface);border:1px solid var(--line);
  border-radius:12px;overflow:hidden}
figure img{display:block;width:100%;height:auto;cursor:zoom-in}
figcaption{padding:10px 14px;font-size:12.5px;color:var(--muted);
  border-top:1px solid var(--line);display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
/* 提示块 */
.pit{background:var(--danger-soft);border:1px solid var(--danger);
  border-radius:12px;padding:16px 18px;margin:14px 0}
.pit > b{color:var(--danger);font-size:14px;display:block;margin-bottom:6px}
.pit p{margin:0;font-size:14px;color:var(--ink-2)}
/* 架构图 */
.diagram{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:12px;margin:0 0 22px;box-shadow:var(--shadow)}
.diagram img.arch{width:100%;height:auto;display:block;background:var(--surface)}
.diagram .cap{font-size:12px;color:var(--faint);padding:8px 6px 2px;
  display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
footer{grid-column:1/-1;border-top:1px solid var(--line);padding:24px 0 0;
  font-size:12.5px;color:var(--faint);display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:12px}
/* 灯箱 */
#lightbox{position:fixed;inset:0;z-index:120;display:none;place-items:center;
  background:rgba(12,15,18,.86);padding:4vh 4vw;cursor:zoom-out}
#lightbox.on{display:grid}
#lightbox img{max-width:100%;max-height:92vh;border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
/* 回到顶部 */
#toTop{position:fixed;right:20px;bottom:24px;z-index:99;width:38px;height:38px;
  display:grid;place-items:center;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:var(--surface);color:var(--ink-2);
  box-shadow:var(--shadow);opacity:0;pointer-events:none;transition:.18s}
#toTop.on{opacity:1;pointer-events:auto}
#toTop:hover{color:var(--accent);border-color:var(--accent);transform:translateY(-2px)}
#toTop svg{width:16px;height:16px}
@media(max-width:900px){
  .wrap{grid-template-columns:minmax(0,1fr);gap:0;padding:0 18px 56px}
  nav.toc{position:static;max-height:none;display:none}
  h1{font-size:24px}
  .icon-btn{top:10px;right:12px}
}
@media print{
  body{background:#fff;font-size:12pt}
  nav.toc,footer .noprint,#progress,.icon-btn,#toTop,.copy-btn{display:none}
  .wrap{grid-template-columns:minmax(0,1fr);max-width:none;padding:0}
  .card,section,figure,table{break-inside:avoid}
  .hero{padding-top:0}
  .card,.diagram{box-shadow:none}
}
"""


JS_TOC = r"""
(function(){
  var root=document.documentElement;
  var KEY='vd-theme';
  var SUN='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function applyTheme(t){
    if(t==='dark') root.setAttribute('data-theme','dark');
    else root.removeAttribute('data-theme');
    var b=document.getElementById('themeBtn');
    if(b){b.innerHTML=(t==='dark'?SUN:MOON);
      b.setAttribute('aria-label',t==='dark'?'切换到亮色':'切换到暗色');}
  }
  var saved=null;
  try{saved=localStorage.getItem(KEY);}catch(e){}
  if(saved!=='dark'&&saved!=='light'){
    try{saved=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}
    catch(e){saved='light';}
  }
  applyTheme(saved);
  var tb=document.getElementById('themeBtn');
  if(tb){tb.addEventListener('click',function(){
    var next=root.getAttribute('data-theme')==='dark'?'light':'dark';
    applyTheme(next);
    try{localStorage.setItem(KEY,next);}catch(e){}
  });}

  var bar=document.getElementById('progress');
  var toTop=document.getElementById('toTop');
  function onScroll(){
    var h=document.documentElement.scrollHeight-window.innerHeight;
    var p=h>0?(window.scrollY/h)*100:0;
    if(bar)bar.style.width=Math.min(100,Math.max(0,p))+'%';
    if(toTop)toTop.classList.toggle('on',window.scrollY>520);
  }
  window.addEventListener('scroll',onScroll,{passive:true});onScroll();
  if(toTop){toTop.addEventListener('click',function(){
    window.scrollTo({top:0,behavior:'smooth'});});}

  var links=[].slice.call(document.querySelectorAll('nav.toc a'));
  var secs=links.map(function(a){return document.getElementById(a.dataset.id);});
  function upd(){
    var y=window.scrollY+140,best=0;
    secs.forEach(function(s,i){if(s&&s.offsetTop<=y)best=i;});
    links.forEach(function(a,i){a.classList.toggle('on',i===best);});
  }
  window.addEventListener('scroll',upd,{passive:true});upd();

  var lb=document.getElementById('lightbox');
  if(lb){
    document.addEventListener('click',function(e){
      var img=e.target.closest('figure img');
      if(img){
        lb.innerHTML='<img src="'+img.src+'" alt="'+(img.alt||'')+'">';
        lb.classList.add('on');document.body.style.overflow='hidden';return;
      }
      if(e.target===lb){lb.classList.remove('on');document.body.style.overflow='';}
    });
    document.addEventListener('keydown',function(e){
      if(e.key==='Escape'&&lb.classList.contains('on')){
        lb.classList.remove('on');document.body.style.overflow='';}
    });
  }

  document.querySelectorAll('.tw').forEach(function(wrap){
    if(!wrap.querySelector('table'))return;
    var btn=document.createElement('button');
    btn.className='copy-btn';btn.type='button';btn.textContent='复制表格';
    wrap.appendChild(btn);
    btn.addEventListener('click',function(){
      var rows=[];
      wrap.querySelectorAll('tr').forEach(function(tr){
        var cells=[].slice.call(tr.children).map(function(c){
          return c.innerText.replace(/\s+/g,' ').trim();});
        if(cells.length)rows.push(cells.join('\t'));
      });
      var txt=rows.join('\n');
      var done=function(){btn.textContent='已复制';btn.classList.add('done');
        setTimeout(function(){btn.textContent='复制表格';btn.classList.remove('done');},1600);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(done).catch(function(){});
      }else{
        var ta=document.createElement('textarea');
        ta.value=txt;document.body.appendChild(ta);ta.select();
        try{document.execCommand('copy');done();}catch(e){}
        document.body.removeChild(ta);
      }
    });
  });

  document.querySelectorAll('a[href^="#"]').forEach(function(a){
    a.addEventListener('click',function(e){
      var id=a.getAttribute('href').slice(1);
      var el=document.getElementById(id);
      if(!el)return;
      e.preventDefault();
      var top=el.getBoundingClientRect().top+window.scrollY-76;
      window.scrollTo({top:top,behavior:'smooth'});
      history.replaceState(null,'','#'+id);
    });
  });
})();
"""


def render_section(s, i, has_tx):
    b = [f'<section id="{esc(s.get("id") or f"s{i+1}")}">']
    head = [f'<div class="shead"><span class="snum">{i+1:02d}</span>',
            f'<h3>{esc(s.get("title"))}</h3>']
    if s.get("kicker"):
        head.append(f'<span class="kicker">{esc(s["kicker"])}</span>')
    t0, t1 = s.get("t0"), s.get("t1")
    if t0 is not None:
        span = f'{fmt_t(t0)}' + (f'–{fmt_t(t1)}' if t1 is not None else '')
        head.append(f'<span class="tc">🕒 {span}</span>')
    head.append("</div>")
    b.append("".join(head))

    if s.get("lead"):
        b.append(f'<div class="lead">{esc(s["lead"])}</div>')

    b.append('<div class="bd">')
    for p in s.get("paras") or []:
        b.append(f"<p>{_md(p)}</p>")

    if s.get("bullets"):
        b.append("<ul>" + "".join(f"<li>{_md(x)}</li>" for x in s["bullets"]) + "</ul>")

    q = s.get("quote")
    if q:
        src = q.get("src") or ""
        tcm = _tc(q.get("t"), has_tx) if q.get("t") is not None else ""
        b.append(f'<blockquote>{_md(q.get("text"))}'
                 f'<span class="src">{esc(src)} {tcm}</span></blockquote>')

    if s.get("cards"):
        b.append('<div class="grid">' + "".join(
            f'<div class="mini"><b>{esc(c.get("h"))}</b>'
            f'<span>{_md(c.get("p"))}</span></div>'
            for c in s["cards"]) + "</div>")

    tb = s.get("table")
    if tb:
        b.append(_table(tb))

    b.append("</div>")

    figs = s.get("figs") or []
    if figs:
        if len(figs) == 1:
            f = figs[0]
            b.append(_fig(f, has_tx))
        else:
            b.append('<figs>' + "".join(_fig(f, has_tx) for f in figs) + "</figs>")
    b.append("</section>")
    return "".join(b)


def _table(tb):
    if isinstance(tb, list):        # 允许直接给 [[头],[行],[行]]
        tb = {"head": tb[0], "rows": tb[1:]}
    head = tb.get("head") or []
    rows = tb.get("rows") or []
    out = ['<div class="tw"><table>']
    if tb.get("title"):
        out.append(f'<caption>{esc(tb["title"])}</caption>')
    if head:
        out.append("<thead><tr>" + "".join(f"<th>{_md(h)}</th>" for h in head)
                   + "</tr></thead>")
    out.append("<tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{_md(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _fig(f, has_tx):
    if isinstance(f, str):
        f = {"src": f}
    cap = f.get("cap") or ""
    tc = _tc(f["t"], has_tx) if f.get("t") is not None else ""
    return (f'<figure><img src="{esc(f.get("src"))}" alt="{esc(cap)}" loading="lazy">'
            f'<figcaption>{tc}<span>{esc(cap)}</span></figcaption></figure>')


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _md(s):
    """极简行内标记：**粗体** 与 `代码`。正文先转义再加标记，避免 XSS。"""
    x = esc(s)
    x = _BOLD.sub(r"<strong>\1</strong>", x)
    x = _CODE.sub(r"<code>\1</code>", x)
    return x


def render_html(o, svg_name, has_tx, tx_name="transcript_full.html"):
    m = o.get("meta") or {}
    secs = o.get("sections") or []
    mode = (m.get("mode") or "learn").lower()
    mode_label = {"learn": "梳理理解 · 学习版",
                  "analysis": "方法论反向拆解 · analysis"}.get(mode, mode)
    plat = PLATFORM_LABEL.get(m.get("platform"), m.get("platform") or "")

    out = ["<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           f"<title>{esc(m.get('title'))} · 视频拆解</title>",
           f"<style>{CSS}</style></head><body>",
           '<div id="progress"></div>',
           '<button class="icon-btn" id="themeBtn" type="button" '
           'aria-label="切换主题"></button>',
           '<div class="wrap">',
           '<header class="hero">']

    chips = [f'<span class="chip mode">{esc(mode_label)}</span>']
    if plat:
        chips.append(f'<span class="chip">{esc(plat)}</span>')
    if m.get("duration"):
        chips.append(f'<span class="chip">时长 {esc(m["duration"])}</span>')
    if m.get("date"):
        chips.append(f'<span class="chip">{esc(m["date"])}</span>')
    out.append('<div class="eyebrow">' + "".join(chips) + "</div>")
    out.append(f'<h1>{esc(m.get("title"))}</h1>')
    if m.get("subtitle"):
        out.append(f'<p class="subtitle">{esc(m["subtitle"])}</p>')

    meta_bits = []
    if m.get("author"):
        meta_bits.append(f'<span>作者 <b>{esc(m["author"])}</b></span>')
    if m.get("duration"):
        meta_bits.append(f'<span>时长 <b>{esc(m["duration"])}</b></span>')
    if len(secs):
        meta_bits.append(f'<span>章节 <b>{len(secs)}</b></span>')
    if m.get("url"):
        meta_bits.append(f'<span>来源 <a href="{esc(m["url"])}" target="_blank" '
                         'rel="noopener">原链接</a></span>')
    if has_tx:
        meta_bits.append(f'<span><a href="{esc(tx_name)}">查看全文稿 →</a></span>')
    out.append('<div class="metaline">' + "".join(meta_bits) + "</div>")
    out.append("</header>")

    # 左侧目录
    nav = ['<nav class="toc"><p class="ttl">目录</p>']
    if o.get("tldr"):
        nav.append('<a href="#tldr" data-id="tldr">核心结论</a>')
    if svg_name:
        nav.append('<div style="height:6px"></div>')
    for i, s in enumerate(secs):
        sid = esc(s.get("id") or f"s{i+1}")
        nav.append(f'<a href="#{sid}" data-id="{sid}">{i+1}. '
                   f'{esc(_clip(s.get("title"), 18))}</a>')
    if o.get("pitfalls"):
        nav.append('<div style="height:6px"></div>')
        nav.append('<a href="#pitfalls" data-id="pitfalls">踩坑与提醒</a>')
    if o.get("takeaways"):
        nav.append('<a href="#takeaways" data-id="takeaways">可执行结论</a>')
    if o.get("glossary"):
        nav.append('<a href="#glossary" data-id="glossary">术语表</a>')
    if o.get("analysis"):
        nav.insert(1, '<a href="#analysis" data-id="analysis">方法论拆解</a>')
    nav.append("</nav>")
    out.append("".join(nav))

    out.append("<main>")

    # TL;DR
    if o.get("tldr"):
        out.append('<div class="card tldr" id="tldr"><h2>核心结论 / TL;DR</h2>')
        if o.get("thesis"):
            out.append(f'<p class="thesis">{_md(o["thesis"])}</p>')
        out.append("<ol>" + "".join(f"<li>{_md(x)}</li>" for x in o["tldr"])
                   + "</ol></div>")

    # 架构图
    if svg_name:
        out.append('<div class="diagram">')
        # 用 <img> 而不是 <object>：img 会按 viewBox 比例自适应容器宽度，
        # object 会按 SVG 的固有像素尺寸显示，宽屏下右侧留一大片空白。
        out.append(f'<img src="{esc(svg_name)}" alt="内容架构图" '
                   'class="arch" loading="lazy">')
        out.append('<div class="cap"><span>内容骨架图（可编辑 SVG，'
                   f'直接改 {esc(svg_name)} 后刷新本页）</span>'
                   f'<a href="{esc(svg_name)}" target="_blank">单独打开 ↗</a></div>')
        out.append("</div>")

    # 方法论（analysis 模式）
    an = o.get("analysis")
    if an:
        out.append('<section id="analysis"><div class="shead">'
                   '<span class="snum">A</span><h3>方法论反向拆解</h3>'
                   '<span class="kicker">analysis</span></div>')
        out.append('<div class="bd">')
        for key, label in (("positioning", "内容定位"), ("skeleton", "内容骨架")):
            if an.get(key):
                out.append(f"<p><strong>{label}：</strong>{_md(an[key])}</p>")
        if an.get("methods"):
            out.append("<ul>" + "".join(f"<li>{_md(x)}</li>" for x in an["methods"])
                       + "</ul>")
        if an.get("prep"):
            rows = [[k, "；".join(v) if isinstance(v, list) else str(v)]
                    for k, v in an["prep"].items()]
            out.append(_table({"title": "制作准备清单", "head": ["环节", "要准备什么"],
                               "rows": rows}))
        if an.get("template"):
            rows = [[t.get("part"), t.get("how")] for t in an["template"]]
            out.append(_table({"title": "可复用模板", "head": ["段落", "做法"],
                               "rows": rows}))
        out.append("</div></section>")

    # 正文章节
    for i, s in enumerate(secs):
        out.append(render_section(s, i, has_tx))

    # 踩坑
    if o.get("pitfalls"):
        out.append('<section id="pitfalls"><div class="shead">'
                   '<span class="snum">!</span><h3>踩坑与提醒</h3>'
                   '<span class="kicker">作者明确提到的失误 / 警告</span></div>')
        for p in o["pitfalls"]:
            if isinstance(p, str):
                p = {"title": "", "text": p}
            tc = _tc(p["t"], has_tx) if p.get("t") is not None else ""
            t = f"<b>{esc(p['title'])}</b>" if p.get("title") else ""
            out.append(f'<div class="pit">{t}<p>{_md(p.get("text"))} {tc}</p></div>')
        out.append("</section>")

    # 结论
    if o.get("takeaways"):
        out.append('<div class="card" id="takeaways"><h2>可执行结论</h2><ul>'
                   + "".join(f"<li>{_md(x)}</li>" for x in o["takeaways"])
                   + "</ul></div>")

    # 术语表
    if o.get("glossary"):
        rows = [[g.get("term"), g.get("def")] for g in o["glossary"]]
        out.append('<div class="card" id="glossary"><h2>术语表</h2>'
                   + _table({"head": ["术语", "释义"], "rows": rows}) + "</div>")

    out.append("</main>")

    foot = [f'<span>由 video-digest 生成 · {esc(m.get("date") or "")}</span>',
            '<span class="noprint">'
            + (f'<a href="{esc(tx_name)}">全文稿</a>' if has_tx else "")
            + (f' · <a href="{esc(svg_name)}">架构图 SVG</a>' if svg_name else "")
            + "</span>"]
    out.append('<footer>' + "".join(foot) + "</footer>")
    out.append('<div id="lightbox"></div>'
               '<button id="toTop" type="button" aria-label="回到顶部">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
               '<path d="M12 19V5M5 12l7-7 7 7"/></svg></button>')
    out.append(f"</div><script>{JS_TOC}</script></body></html>")
    return "".join(out)


# ---------------------------------------------------------------------------
# 全文稿页
# ---------------------------------------------------------------------------
TX_CSS = """
:root{
  --bg:#f7f6f2; --surface:#ffffff; --surface-2:#fbfaf7;
  --ink:#191a1c; --ink-2:#3d4045; --muted:#6b7076; --faint:#9aa0a6;
  --line:#e4e0d7; --accent:#14556e; --accent-soft:#e9f2f6;
  --mark:#fde68a; color-scheme:light;
}
[data-theme="dark"]{
  --bg:#111315; --surface:#181b1e; --surface-2:#1d2125;
  --ink:#e8e9ea; --ink-2:#c8cbd0; --muted:#98a0a7; --faint:#6d757c;
  --line:#2a2f34; --accent:#6cc0d8; --accent-soft:#16282f;
  --mark:#7a6520; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.85 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  transition:background .18s ease,color .18s ease}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.top{position:sticky;top:0;z-index:9;background:var(--bg);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:12px 24px;
  display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.top h1{font-size:15px;margin:0;font-weight:650;flex:1;min-width:180px}
.top input{border:1px solid var(--line);background:var(--surface);border-radius:8px;
  padding:7px 12px;font-size:13px;min-width:210px;outline:none;color:var(--ink)}
.top input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.btn{border:1px solid var(--line);background:var(--surface);border-radius:8px;
  padding:7px 12px;font-size:13px;color:var(--muted);cursor:pointer;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent)}
#hit{font-size:12.5px;color:var(--faint);font-variant-numeric:tabular-nums;white-space:nowrap}
.layout{max-width:1080px;margin:0 auto;padding:22px 24px 90px;
  display:grid;grid-template-columns:196px minmax(0,1fr);gap:34px}
aside{position:sticky;top:70px;align-self:start;font-size:13px;
  max-height:calc(100vh - 100px);overflow:auto}
aside p.ttl{font-size:11px;letter-spacing:.12em;color:var(--faint);font-weight:700;
  margin:0 0 10px;text-transform:uppercase}
aside a{display:block;color:var(--muted);padding:4px 0 4px 10px;
  border-left:2px solid transparent;line-height:1.5}
aside a.on{color:var(--accent);border-left-color:var(--accent);font-weight:600}
main{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:10px 26px 26px}
h2.ch{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);
  margin:26px 0 12px;padding-top:14px;border-top:1px dashed var(--line)}
h2.ch:first-child{border-top:0;margin-top:12px}
.seg{display:grid;grid-template-columns:62px 1fr;gap:14px;padding:6px 0;border-radius:6px}
.seg:hover{background:var(--surface-2)}
.seg .t{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums;
  padding-top:3px;cursor:pointer;user-select:all}
.seg .t:hover{color:var(--accent)}
.seg .c{font-size:15px}
mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 1px}
.hidden{display:none}
@media(max-width:820px){.layout{grid-template-columns:minmax(0,1fr);gap:0}
  aside{display:none}main{padding:8px 16px 20px}.top{padding:10px 14px}}
@media print{.top,aside{display:none}.layout{grid-template-columns:minmax(0,1fr);max-width:none}
  main{border:0;padding:0}.seg{break-inside:avoid}mark{background:none}}
"""


JS_TX = r"""
(function(){
  var root=document.documentElement, KEY='vd-theme';
  function applyTheme(t){
    if(t==='dark')root.setAttribute('data-theme','dark');
    else root.removeAttribute('data-theme');
    var b=document.getElementById('themeBtn');
    if(b)b.textContent=(t==='dark'?'亮色':'暗色');
  }
  var saved=null;
  try{saved=localStorage.getItem(KEY);}catch(e){}
  if(saved!=='dark'&&saved!=='light'){
    try{saved=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}
    catch(e){saved='light';}
  }
  applyTheme(saved);
  var tb=document.getElementById('themeBtn');
  if(tb)tb.addEventListener('click',function(){
    var next=root.getAttribute('data-theme')==='dark'?'light':'dark';
    applyTheme(next);
    try{localStorage.setItem(KEY,next);}catch(e){}
  });

  var box=document.getElementById('q');
  var hit=document.getElementById('hit');
  var segs=[].slice.call(document.querySelectorAll('.seg'));
  var links=[].slice.call(document.querySelectorAll('aside a'));
  var chs=[].slice.call(document.querySelectorAll('h2.ch'));
  segs.forEach(function(s){
    var c=s.querySelector('.c');
    s.dataset.raw=c.textContent;
    s.dataset.body=c.textContent.toLowerCase();
  });
  function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function escRe(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
  function filter(){
    var raw=box?box.value.trim():'';
    var v=raw.toLowerCase();
    var n=0;
    segs.forEach(function(s){
      var c=s.querySelector('.c');
      var on=!v||s.dataset.body.indexOf(v)>=0;
      s.classList.toggle('hidden',!on);
      if(!c)return;
      if(!on){c.innerHTML=escHtml(s.dataset.raw);return;}
      if(v){
        n++;
        var re=new RegExp('('+escRe(raw)+')','gi');
        c.innerHTML=escHtml(s.dataset.raw).replace(re,'<mark>$1</mark>');
      }else{c.innerHTML=escHtml(s.dataset.raw);}
    });
    chs.forEach(function(h){
      var el=h.nextElementSibling,any=false;
      while(el&&!el.classList.contains('ch')){
        if(el.classList.contains('seg')&&!el.classList.contains('hidden'))any=true;
        el=el.nextElementSibling;
      }
      h.classList.toggle('hidden',!!v&&!any);
    });
    if(hit)hit.textContent=v?(n+' 段命中'):'';
  }
  if(box){
    box.addEventListener('input',filter);
    document.addEventListener('keydown',function(e){
      if(e.key==='/'&&document.activeElement!==box){e.preventDefault();box.focus();}
      if(e.key==='Escape'){box.value='';filter();box.blur();}
    });
  }
  document.querySelectorAll('.seg .t').forEach(function(t){
    t.addEventListener('click',function(){
      var r=t.closest('.seg').getBoundingClientRect();
      window.scrollTo({top:window.scrollY+r.top-70,behavior:'smooth'});
    });
  });
  function upd(){
    var y=window.scrollY+90,best=0;
    chs.forEach(function(h,i){if(h.offsetTop<=y)best=i;});
    links.forEach(function(a,i){a.classList.toggle('on',i===best);});
  }
  window.addEventListener('scroll',upd,{passive:true});upd();
})();
"""


def render_transcript(segs, meta, sections, main_name="index.html"):
    """segs: [{"s","e","t"}]；按 sections 的时间区间打章节标题。"""
    bounds = []
    for i, s in enumerate(sections or []):
        t0 = s.get("t0")
        if t0 is None:
            continue
        bounds.append((float(t0), i + 1, s.get("title") or ""))
    bounds.sort()

    def chapter_of(t):
        cur = None
        for t0, n, title in bounds:
            if t >= t0:
                cur = (n, title)
            else:
                break
        return cur

    body, cur = [], None
    for g in segs:
        t = float(g["s"])
        ch = chapter_of(t)
        if ch != cur:
            cur = ch
            label = f"{ch[0]:02d} · {ch[1]}" if ch else "未分章"
            body.append(f'<h2 class="ch" id="ch-{ch[0] if ch else 0}">'
                        f'{esc(label)}</h2>')
        txt = esc(g["t"])
        body.append(
            f'<div class="seg" id="t-{int(t)}" data-text="{esc(g["t"]).lower()}" '
            f'data-raw="{esc(g["t"])}">'
            f'<div class="t">{fmt_t(t)}</div><div class="c">{txt}</div></div>')

    aside = ['<aside><p class="ttl">章节</p>']
    seen = []
    for g in segs:
        ch = chapter_of(float(g["s"]))
        if ch and ch not in seen:
            seen.append(ch)
            aside.append(f'<a href="#ch-{ch[0]}">{ch[0]:02d}. '
                         f'{esc(_clip(ch[1], 14))}</a>')
    aside.append("</aside>")

    title = (meta or {}).get("title") or "全文稿"
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)} · 全文稿</title><style>{TX_CSS}</style></head><body>'
        '<div class="top">'
        f'<a class="btn" href="{esc(main_name)}">← 回专题页</a>'
        f'<h1>{esc(title)}</h1>'
        '<input id="q" placeholder="搜索文稿…（/ 聚焦）" '
        'autocomplete="off">'
        '<span id="hit"></span>'
        '<button class="btn" id="themeBtn" type="button">暗色</button>'
        '</div><div class="layout">' + "".join(aside) + "<main>"
        + "".join(body) + "</main></div>"
        f"<script>{JS_TX}</script></body></html>")


# ---------------------------------------------------------------------------
# 表格版 md
# ---------------------------------------------------------------------------

def _md_cell(v):
    s = str(v if v is not None else "").replace("\n", "<br>").replace("|", "\\|")
    return s.strip()


def _md_table(head, rows, title=None):
    out = []
    if title:
        out.append(f"**{title}**\n")
    out.append("| " + " | ".join(_md_cell(h) for h in head) + " |")
    out.append("|" + "|".join([" --- "] * len(head)) + "|")
    for r in rows:
        r = list(r) + [""] * (len(head) - len(r))
        out.append("| " + " | ".join(_md_cell(c) for c in r[:len(head)]) + " |")
    return "\n".join(out)


def render_table_md(o):
    m = o.get("meta") or {}
    secs = o.get("sections") or []
    L = [f"# {m.get('title') or '视频拆解'}（表格版）", ""]

    basic = [["标题", m.get("title")], ["作者", m.get("author")],
             ["平台", PLATFORM_LABEL.get(m.get("platform"), m.get("platform"))],
             ["时长", m.get("duration")], ["方向",
              "learn（梳理理解）" if (m.get("mode") or "learn") == "learn"
              else "analysis（方法论反向拆解）"],
             ["来源", m.get("url")], ["生成日期", m.get("date")]]
    L.append(_md_table(["项", "值"], [r for r in basic if r[1]], "基本信息"))
    L.append("")

    if o.get("thesis"):
        L += ["## 核心命题", "", o["thesis"], ""]
    if o.get("tldr"):
        L += ["## 核心结论", ""]
        L += [f"{i+1}. {x}" for i, x in enumerate(o["tldr"])]
        L.append("")

    if secs:
        L += ["## 章节索引", ""]
        L.append(_md_table(
            ["#", "章节", "时间码", "一句话概括"],
            [[i + 1, s.get("title"),
              (fmt_t(s.get("t0")) + (f"–{fmt_t(s.get('t1'))}"
                                     if s.get("t1") is not None else ""))
              if s.get("t0") is not None else "",
              s.get("gist") or s.get("lead") or ""]
             for i, s in enumerate(secs)]))
        L.append("")

    for i, s in enumerate(secs):
        t0, t1 = s.get("t0"), s.get("t1")
        span = (fmt_t(t0) + (f"–{fmt_t(t1)}" if t1 is not None else "")
                if t0 is not None else "")
        L += [f"## {i+1}. {s.get('title')}" + (f"（{span}）" if span else ""), ""]
        if s.get("lead"):
            L += ["> " + s["lead"], ""]
        for p in s.get("paras") or []:
            L += [p, ""]
        if s.get("bullets"):
            L += [f"- {x}" for x in s["bullets"]] + [""]
        if s.get("quote"):
            q = s["quote"]
            L += [f"> {q.get('text')}"
                  + (f"（🕒 {fmt_t(q['t'])}）" if q.get("t") is not None else ""), ""]
        if s.get("table"):
            tb = s["table"]
            if isinstance(tb, list):
                tb = {"head": tb[0], "rows": tb[1:]}
            L += [_md_table(tb.get("head") or [], tb.get("rows") or [],
                            tb.get("title")), ""]
        if s.get("cards"):
            L += [_md_table(["要点", "说明"],
                            [[c.get("h"), c.get("p")] for c in s["cards"]]), ""]
        if s.get("figs"):
            L += ["；".join(
                f"🕒 {fmt_t(f['t']) if isinstance(f, dict) and f.get('t') is not None else ''} "
                f"{f.get('cap') if isinstance(f, dict) else ''}"
                for f in s["figs"]), ""]

    an = o.get("analysis")
    if an:
        L += ["## 方法论反向拆解", ""]
        rows = []
        for k, label in (("positioning", "内容定位"), ("skeleton", "内容骨架")):
            if an.get(k):
                rows.append([label, an[k]])
        if an.get("methods"):
            rows.append(["方法论", "；".join(an["methods"])])
        L += [_md_table(["维度", "结论"], rows), ""]
        if an.get("prep"):
            L += [_md_table(["环节", "要准备什么"],
                            [[k, "；".join(v) if isinstance(v, list) else v]
                             for k, v in an["prep"].items()], "制作准备清单"), ""]
        if an.get("template"):
            L += [_md_table(["段落", "做法"],
                            [[t.get("part"), t.get("how")] for t in an["template"]],
                            "可复用模板"), ""]

    if o.get("pitfalls"):
        L += ["## 踩坑与提醒", ""]
        L += [_md_table(["点", "说明", "时间码"],
                        [[p.get("title") if isinstance(p, dict) else "",
                          p.get("text") if isinstance(p, dict) else p,
                          fmt_t(p.get("t")) if isinstance(p, dict)
                          and p.get("t") is not None else ""]
                         for p in o["pitfalls"]]), ""]

    if o.get("takeaways"):
        L += ["## 可执行结论", ""] + [f"- {x}" for x in o["takeaways"]] + [""]

    if o.get("glossary"):
        L += ["## 术语表", "",
              _md_table(["术语", "释义"],
                        [[g.get("term"), g.get("def")] for g in o["glossary"]]), ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def build(outline_path, outdir=None, name=None, transcript=None):
    op = Path(outline_path).expanduser().resolve()
    if not op.exists():
        raise SystemExit(f"[err] 找不到 outline：{op}")
    o = json.loads(op.read_text(encoding="utf-8"))
    if not isinstance(o, dict):
        raise SystemExit("[err] outline.json 顶层必须是对象")

    m = o.setdefault("meta", {})
    base = op.parent
    out = Path(outdir).expanduser().resolve() if outdir else base
    out.mkdir(parents=True, exist_ok=True)

    slug = name or m.get("slug") or re.sub(r"[^\w\-]+", "-",
                                          (m.get("title") or "digest"))[:40]
    slug = slug.strip("-_") or "digest"

    # 时长兜底：从 sections 推
    if not m.get("duration") and o.get("sections"):
        last = max((s.get("t1") or s.get("t0") or 0) for s in o["sections"])
        if last:
            m["duration"] = fmt_t(last)

    # 1) SVG
    secs = o.get("sections") or []
    svg = _svg_flow(o.get("diagram") or {}, secs)
    svg_path = out / f"{slug}.svg"
    svg_path.write_text(svg, encoding="utf-8")

    # 2) 全文稿（可选）
    has_tx = False
    if transcript:
        tp = Path(transcript).expanduser()
        if not tp.is_absolute():
            tp = (Path.cwd() / tp)
        if tp.exists():
            segs = json.loads(tp.read_text(encoding="utf-8"))
            (out / "transcript_full.html").write_text(
                render_transcript(segs, m, secs,
                                  main_name=f"{slug}.html"), encoding="utf-8")
            has_tx = True
            print(f"[ok] transcript_full.html（{len(segs)} 段）")
        else:
            print(f"[warn] 文稿片段不存在，跳过全文稿页：{tp}")
    elif (base / "transcript_full.html").exists():
        has_tx = True

    # 3) 主页面
    html_path = out / f"{slug}.html"
    html_path.write_text(
        render_html(o, svg_path.name if svg else None, has_tx), encoding="utf-8")

    # 4) 表格版
    md_path = out / f"{slug}_table.md"
    md_path.write_text(render_table_md(o), encoding="utf-8")

    print(f"[ok] {html_path}")
    print(f"[ok] {svg_path}")
    print(f"[ok] {md_path}")
    return {"html": str(html_path), "svg": str(svg_path), "md": str(md_path),
            "transcript": str(out / "transcript_full.html") if has_tx else None}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="outline.json → 专题页四件套")
    p.add_argument("outline")
    p.add_argument("-o", "--out", default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--transcript", default=None)
    p.add_argument("--schema", action="store_true", help="打印 outline 字段说明")
    a = p.parse_args()
    if a.schema:
        print(_SCHEMA_DOC)
    else:
        build(a.outline, a.out, a.name, a.transcript)
