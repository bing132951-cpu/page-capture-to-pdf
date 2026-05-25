# Image Links to PDF

本地工具：自动启动一个项目专用可调试 Chrome 收集图片链接，或者直接接收已有链接列表，再按输入顺序合并成单个图片型 PDF。

## VS Code 一键运行

最方便的是直接用 VS Code 的运行配置：

1. 先打开这个项目文件夹
2. 确保已经创建虚拟环境 `.venv`
3. 点击左侧“运行和调试”
4. 选择 `Run JPG Links Web App`
5. 按 `F5`

这样会直接在 VS Code 集成终端里启动本地网页服务。

也可以用任务面板一键启动：

1. `Command + Shift + P`
2. 输入 `Tasks: Run Task`
3. 选择 `Start JPG Links Web App`

## Requirements

- Python 3.9+
- 项目依赖 `Pillow` 用于把 PNG/WebP 等图片统一转成 JPEG 后写入 PDF

## Quick Start

进入项目目录：

```bash
cd "/Users/weixukai/Downloads/spide前端"
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install .
python3 -m unittest discover -s tests -v
```

如果你还没创建虚拟环境，先跑这一步。之后 VS Code 会优先使用 `.venv/bin/python`。

## Main Flow

推荐直接用本地网页工具：

```bash
python3 -m scribd_exporter.webapp
```

启动后终端会打印本地地址，例如：

```text
Serving JPG-to-PDF web app at http://127.0.0.1:8765/
```

网页里有两条主路径：

1. 输入目标网页 URL，选择收集模式后点击“启动 Chrome 并收集”
2. 直接粘贴或上传已有的图片 URL 列表

收集模式说明：

- `scroll`：适合滚动懒加载页面
- `paginate`：适合点击“下一页”翻页的页面，需要提供 `nextButtonSelector`

收集完成后可以直接一键生成 PDF。

## CLI Usage

从网页收集图片链接并保存成 JSON：

```bash
python3 -m scribd_exporter.cli collect \
  --target-url "https://example.com/document/123" \
  --output output/pages.json
```

从翻页型页面收集图片链接：

```bash
python3 -m scribd_exporter.cli collect \
  --target-url "https://example.com/book" \
  --mode paginate \
  --next-button-selector ".flip_button_right.button" \
  --page-indicator-selector ".page-count" \
  --click-min-wait-ms 1200 \
  --click-max-wait-ms 2500 \
  --output output/pages.json
```

从 TXT 文件导出 PDF：

```bash
python3 -m scribd_exporter.cli export \
  --url-list xx.txt \
  --output output/document.pdf
```

如果你已经有 JSON 格式页列表：

```bash
python3 -m scribd_exporter.cli export \
  --pages-json output/pages.json \
  --output output/document.pdf
```

说明：

- TXT 文件中一行一个 URL
- 支持 `http/https` 的 `.jpg/.jpeg/.png/.webp` 链接
- PDF 页序按 TXT 行顺序决定
- `png/webp` 会由项目内置的 Pillow 转成 JPEG 后写入 PDF，不依赖 macOS 系统工具
- 任意一张图片下载失败会立即停止，并指出失败页号和 URL

如果不想自动打开浏览器：

```bash
python3 -m scribd_exporter.webapp --no-open
```

## Notes

- 当前导出支持 JPG/JPEG/PNG/WebP，非 JPEG 图片会自动转成 JPEG 后写入 PDF
- 图片格式转换不依赖 macOS `sips`，在安装项目依赖后可跨平台运行
- 收集器会新开一个项目专用 Chrome 实例，不复用你平时浏览器的标签页或登录状态
- `paginate` 模式第一版只支持显式 `nextButtonSelector`，不做自动猜测
- 产物是图片型 PDF，不包含文字层或 OCR
- `output/` 已加入 Git 忽略规则
