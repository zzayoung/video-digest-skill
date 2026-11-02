# 片悟 · Pianwu：第一次运行

这是一份原创合成演示，主题是「60 秒咖啡短片：从看懂到会拍」。它不是对真实视频的分析；时间码、台词、镜头与时长均为示意，没有对应的视频、截图或效果数据。

## 生成四件套

在仓库根目录运行。只需要 Python 3 标准库，无需安装依赖、下载视频或转写模型：

```bash
python -B -S scripts/make_page.py examples/starter/outline.json --transcript examples/starter/transcript.json -o docs/demo
```

生成后，用浏览器打开 `docs/demo/index.html`。保留同目录的文件，时间码和架构图链接才能正常工作。

| 文件 | 用途 |
|---|---|
| `index.html` | 在「知识学习 / 怎么复刻 / 对照看」之间切换 |
| `index.svg` | 可独立打开、编辑的内容架构图 |
| `index_table.md` | 可复制的学习与制作表格 |
| `transcript_full.html` | 带时间码、章节跳转和搜索的演示文稿 |

## 先体验这四步

1. 打开主页面，阅读四个学习章节。
2. 切换「对照看」，比较同一章节的内容与拍摄动作。
3. 点击 00:08 等时间码，跳到对应的原创演示台词。
4. 切换「怎么复刻」，复制镜头清单或口播，试勾选执行清单。

`outline.json` 是内容数据，`transcript.json` 是文稿段落。四个章节通过 `replicate.beats[].ref` 配对；引用时间码与文稿中的段落起点一致。你可以复制这两个文件，再替换为自己有依据的内容。
