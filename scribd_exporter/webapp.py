import argparse
import json
import os
import tempfile
import uuid
import webbrowser
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .browser_collect import BrowserCollectError, collect_from_browser
from .exporter import export_document_pdf
from .models import CollectedDocument, PageImage
from .url_input import UrlInputError, parse_urls_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the local JPG-to-PDF web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the local web server.")
    parser.add_argument("--port", default=8765, type=int, help="Port to bind the local web server.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    app = WebAppState(output_root=os.path.join(os.getcwd(), "output", "webapp"))
    server = ThreadingHTTPServer((args.host, args.port), app.make_handler())
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving JPG-to-PDF web app at {url}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


class WebAppState:
    def __init__(self, output_root: str) -> None:
        self.output_root = output_root
        self.download_names = {}
        os.makedirs(self.output_root, exist_ok=True)

    def log(self, message: str) -> None:
        print(message, flush=True)

    def make_handler(self):
        state = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                state.log(f"[GET] {parsed.path}")
                if parsed.path == "/":
                    self._send_html(INDEX_HTML)
                    return
                if parsed.path == "/api/download":
                    query = parse_qs(parsed.query)
                    token = query.get("token", [""])[0]
                    if not token:
                        self._send_json({"ok": False, "error": "Missing download token."}, HTTPStatus.BAD_REQUEST)
                        return
                    path = os.path.join(state.output_root, f"{token}.pdf")
                    if not os.path.exists(path):
                        self._send_json({"ok": False, "error": "File not found."}, HTTPStatus.NOT_FOUND)
                        return
                    filename = state.download_names.get(token, "document.pdf")
                    self._send_file(path, filename)
                    return
                self._send_json({"ok": False, "error": "Not found."}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                try:
                    parsed = urlparse(self.path)
                    state.log(f"[POST] {parsed.path}")
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_length)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError:
                        self._send_json({"ok": False, "error": "Request body must be valid JSON."}, HTTPStatus.BAD_REQUEST)
                        return

                    if parsed.path == "/api/collect-from-browser":
                        try:
                            result = create_collection_from_payload(payload)
                        except (BrowserCollectError, RuntimeError, ValueError) as exc:
                            state.log(f"[ERROR] collect-from-browser: {exc}")
                            self._send_json(_build_error_payload(exc), HTTPStatus.BAD_REQUEST)
                            return
                        self._send_json(result)
                        return

                    if parsed.path != "/api/export":
                        self._send_json({"ok": False, "error": "Not found."}, HTTPStatus.NOT_FOUND)
                        return

                    try:
                        result = create_export_from_payload(payload, state.output_root)
                        state.download_names[result["token"]] = result["outputName"]
                    except (UrlInputError, RuntimeError, ValueError) as exc:
                        state.log(f"[ERROR] export: {exc}")
                        self._send_json(_build_error_payload(exc), HTTPStatus.BAD_REQUEST)
                        return

                    self._send_json(
                        {
                            "ok": True,
                            "totalPages": result["totalPages"],
                            "downloadUrl": f"/api/download?token={result['token']}",
                            "pdfPath": result["pdfPath"],
                        }
                    )
                except Exception as exc:
                    state.log(f"[FATAL] {exc}")
                    state.log(traceback.format_exc())
                    self._send_json(
                        {"ok": False, "error": f"Internal server error: {exc}"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )

            def log_message(self, format: str, *args) -> None:
                return

            def _send_html(self, html: str) -> None:
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_file(self, path: str, filename: str) -> None:
                with open(path, "rb") as handle:
                    body = handle.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _safe_output_name(value: str) -> str:
    name = (value or "document.pdf").strip()
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    safe = "".join(ch for ch in name if ch.isalnum() or ch in {"-", "_", ".", " "}).strip()
    return safe or "document.pdf"


def _build_error_payload(exc: Exception) -> dict:
    message = str(exc)
    payload = {"ok": False, "error": message}
    if hasattr(exc, "page_number"):
        payload["failedIndex"] = getattr(exc, "page_number")
    if hasattr(exc, "image_url"):
        payload["failedUrl"] = getattr(exc, "image_url")
    if hasattr(exc, "stage"):
        payload["stage"] = getattr(exc, "stage")
    return payload


def create_collection_from_payload(payload: dict) -> dict:
    target_url = str(payload.get("targetUrl", "")).strip()
    if not target_url:
        raise ValueError("A targetUrl is required.")
    result = collect_from_browser(target_url, collector_options=payload.get("collectorOptions"))
    return {
        "ok": True,
        "title": result["title"],
        "totalPages": result["totalPages"],
        "urlsText": result["urlsText"],
        "pagesJson": result["pagesJson"],
        "stopReason": result.get("stopReason"),
        "stopDetails": result.get("stopDetails"),
        "stats": result.get("stats", {}),
        "configUsed": result.get("configUsed", {}),
    }


def create_export_from_payload(payload: dict, output_root: str) -> dict:
    output_name = _safe_output_name(payload.get("outputName", "document.pdf"))
    document = _document_from_payload(payload, title=os.path.splitext(output_name)[0] or "document")
    token = uuid.uuid4().hex
    pdf_path = os.path.join(output_root, f"{token}.pdf")
    with tempfile.TemporaryDirectory(dir=output_root) as temp_dir:
        export_document_pdf(
            output_path=pdf_path,
            document=document,
            work_dir=os.path.join(temp_dir, "downloads"),
        )
    return {
        "token": token,
        "outputName": output_name,
        "pdfPath": pdf_path,
        "totalPages": document.total_pages,
    }


def _document_from_payload(payload: dict, title: str) -> CollectedDocument:
    pages_json = payload.get("pagesJson")
    if isinstance(pages_json, list) and pages_json:
        pages = [
            PageImage(
                page_number=index,
                image_url=item["imageUrl"],
                width=item.get("width"),
                height=item.get("height"),
            )
            for index, item in enumerate(pages_json, start=1)
        ]
        return CollectedDocument(title=title, total_pages=len(pages), pages=pages)
    return parse_urls_text(payload.get("urlsText", ""), title=title)


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>JPG Links to PDF</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f1e8;
        --panel: #fffdf8;
        --ink: #18212b;
        --muted: #5d6875;
        --accent: #1f6f78;
        --accent-strong: #145259;
        --border: #d9cfbf;
        --danger: #a33636;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Iowan Old Style", "Palatino Linotype", serif;
        background:
          radial-gradient(circle at top right, rgba(31,111,120,0.10), transparent 28%),
          linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
        color: var(--ink);
      }
      .shell {
        max-width: 1100px;
        margin: 0 auto;
        padding: 40px 20px 56px;
      }
      .header { margin-bottom: 24px; }
      h1 { margin: 0 0 10px; font-size: 40px; line-height: 1.05; font-weight: 700; }
      p { margin: 0; color: var(--muted); font-size: 17px; line-height: 1.55; }
      .panel {
        background: rgba(255,253,248,0.92);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 20px;
        backdrop-filter: blur(6px);
      }
      .grid {
        display: grid;
        grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.9fr);
        gap: 18px;
      }
      label { display: block; margin-bottom: 8px; font-size: 14px; font-weight: 600; }
      textarea, input[type="text"] {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 12px 14px;
        font: inherit;
        color: var(--ink);
        background: white;
      }
      textarea { min-height: 250px; resize: vertical; }
      pre {
        margin: 0;
        min-height: 180px;
        max-height: 280px;
        overflow: auto;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: white;
        padding: 12px 14px;
        font-size: 12px;
        line-height: 1.45;
      }
      input[type="file"] { width: 100%; font: inherit; color: var(--muted); }
      .side { display: grid; gap: 16px; align-content: start; }
      button {
        width: 100%;
        border: 0;
        border-radius: 6px;
        padding: 13px 16px;
        font: inherit;
        font-weight: 700;
        color: white;
        background: var(--accent);
        cursor: pointer;
      }
      button:hover { background: var(--accent-strong); }
      button:disabled { background: #98a4ab; cursor: progress; }
      .note, .status, .error {
        border-radius: 6px;
        padding: 12px 14px;
        font-size: 14px;
        line-height: 1.5;
      }
      .note { background: #f6efe3; border: 1px solid #eadbc0; color: var(--muted); }
      .status { display: none; background: #eef7f7; border: 1px solid #c8e1e2; }
      .status.visible { display: block; }
      .error { display: none; background: #fbefee; border: 1px solid #efc8c2; color: var(--danger); }
      .error.visible { display: block; }
      .download { display: none; color: var(--accent-strong); font-weight: 700; }
      .download.visible { display: inline-block; }
      .meta { font-size: 13px; color: var(--muted); }
      @media (max-width: 860px) {
        .grid { grid-template-columns: 1fr; }
        h1 { font-size: 32px; }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <h1>JPG Links to PDF</h1>
        <p>输入目标网页 URL 让工具启动项目专用 Chrome 自动收集懒加载 JPG/JPEG 链接，或者直接粘贴已有链接列表，再按顺序生成单个 PDF。</p>
      </div>
      <div class="panel grid">
        <div>
          <label for="targetUrl">目标网页地址</label>
          <input id="targetUrl" type="text" placeholder="https://example.com/document/123" />
          <div style="height: 14px;"></div>
          <label for="collectorMode">收集模式</label>
          <select id="collectorMode" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:12px 14px;font:inherit;color:var(--ink);background:white;">
            <option value="scroll" selected>scroll（滚动加载）</option>
            <option value="paginate">paginate（点击下一页）</option>
          </select>
          <div style="height: 14px;"></div>
          <label for="collectorSettings">收集器设置</label>
          <div id="collectorSettings" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px;">
            <div><label for="maxSteps">maxSteps</label><input id="maxSteps" type="text" value="220" /></div>
            <div><label for="delayMs">delayMs</label><input id="delayMs" type="text" value="800" /></div>
            <div class="scroll-only"><label for="scrollRatio">scrollRatio</label><input id="scrollRatio" type="text" value="1.2" /></div>
            <div class="scroll-only"><label for="noNewLimit">noNewLimit</label><input id="noNewLimit" type="text" value="18" /></div>
            <div><label for="minWidth">minWidth</label><input id="minWidth" type="text" value="180" /></div>
            <div><label for="minHeight">minHeight</label><input id="minHeight" type="text" value="180" /></div>
            <div style="grid-column:1 / -1;"><label for="imageSelector">imageSelector</label><input id="imageSelector" type="text" value="img" /></div>
            <div class="scroll-only" style="grid-column:1 / -1;"><label for="scrollContainerSelector">scrollContainerSelector</label><input id="scrollContainerSelector" type="text" value="" placeholder="留空表示 window 滚动" /></div>
            <div class="paginate-only" style="grid-column:1 / -1;display:none;"><label for="nextButtonSelector">nextButtonSelector</label><input id="nextButtonSelector" type="text" value="" placeholder=".flip_button_right.button" /></div>
            <div class="paginate-only" style="grid-column:1 / -1;display:none;"><label for="pageIndicatorSelector">pageIndicatorSelector</label><input id="pageIndicatorSelector" type="text" value="" placeholder=".page-number, .pager, [aria-label*='page']" /></div>
            <div class="paginate-only" style="display:none;"><label for="maxPages">maxPages</label><input id="maxPages" type="text" value="" placeholder="可选硬上限" /></div>
            <div class="paginate-only" style="display:none;"><label for="clickDelayMs">clickDelayMs</label><input id="clickDelayMs" type="text" value="1000" /></div>
            <div class="paginate-only" style="display:none;"><label for="maxUnchangedSteps">maxUnchangedSteps</label><input id="maxUnchangedSteps" type="text" value="3" /></div>
            <div style="grid-column:1 / -1;"><label for="imageFilterPattern">imageFilterPattern</label><input id="imageFilterPattern" type="text" value="auto" placeholder="auto: 自动识别 jpg/jpeg/png/webp/gif/bmp/avif/svg" /></div>
            <div style="grid-column:1 / -1;"><label for="pageNumberPattern">pageNumberPattern</label><input id="pageNumberPattern" type="text" value="auto" placeholder="auto: 自动从文件名或 ?page=12 这类地址里提取页码" /></div>
          </div>
          <label for="urlsText">图片链接列表</label>
          <textarea id="urlsText" spellcheck="false" placeholder="https://example.com/page-001.jpg&#10;https://example.com/page-002.jpg"></textarea>
          <div style="height: 14px;"></div>
          <label for="pagesJsonPreview">收集结果 JSON 预览</label>
          <pre id="pagesJsonPreview">[]</pre>
          <div style="height: 14px;"></div>
          <label for="collectorSummary">停止条件与统计</label>
          <pre id="collectorSummary">尚未执行收集。</pre>
        </div>
        <div class="side">
          <div>
            <label for="outputName">输出 PDF 文件名</label>
            <input id="outputName" type="text" value="document.pdf" />
          </div>
          <div>
            <label for="txtFile">或上传 TXT 文件</label>
            <input id="txtFile" type="file" accept=".txt,text/plain" />
          </div>
          <button id="collectBtn" type="button">启动 Chrome 并收集</button>
          <button id="submitBtn" type="button">开始生成 PDF</button>
          <div id="status" class="status"></div>
          <div id="error" class="error"></div>
          <a id="downloadLink" class="download" href="">下载生成的 PDF</a>
          <div id="collectionMeta" class="meta"></div>
          <div class="note">
            说明：收集器默认使用 auto 模式自动识别常见图片地址，包含相对 src；导出 PDF 这一步目前仍只支持公开可访问的 JPG/JPEG 链接。
          </div>
        </div>
      </div>
    </div>
    <script>
      const targetUrl = document.getElementById("targetUrl");
      const collectorMode = document.getElementById("collectorMode");
      const urlsText = document.getElementById("urlsText");
      const pagesJsonPreview = document.getElementById("pagesJsonPreview");
      const collectorSummary = document.getElementById("collectorSummary");
      const outputName = document.getElementById("outputName");
      const txtFile = document.getElementById("txtFile");
      const collectBtn = document.getElementById("collectBtn");
      const submitBtn = document.getElementById("submitBtn");
      const statusBox = document.getElementById("status");
      const errorBox = document.getElementById("error");
      const downloadLink = document.getElementById("downloadLink");
      const collectionMeta = document.getElementById("collectionMeta");
      var collectedPagesJson = [];

      function toggleCollectorMode() {
        const isPaginate = collectorMode.value === "paginate";
        document.querySelectorAll(".scroll-only").forEach(node => {
          node.style.display = isPaginate ? "none" : "";
        });
        document.querySelectorAll(".paginate-only").forEach(node => {
          node.style.display = isPaginate ? "" : "none";
        });
      }

      function readCollectorOptions() {
        return {
          mode: collectorMode.value,
          maxSteps: document.getElementById("maxSteps").value,
          delayMs: document.getElementById("delayMs").value,
          scrollRatio: document.getElementById("scrollRatio").value,
          noNewLimit: document.getElementById("noNewLimit").value,
          minWidth: document.getElementById("minWidth").value,
          minHeight: document.getElementById("minHeight").value,
          imageSelector: document.getElementById("imageSelector").value,
          scrollContainerSelector: document.getElementById("scrollContainerSelector").value,
          nextButtonSelector: document.getElementById("nextButtonSelector").value,
          pageIndicatorSelector: document.getElementById("pageIndicatorSelector").value,
          maxPages: document.getElementById("maxPages").value,
          clickDelayMs: document.getElementById("clickDelayMs").value,
          maxUnchangedSteps: document.getElementById("maxUnchangedSteps").value,
          imageFilterPattern: document.getElementById("imageFilterPattern").value,
          pageNumberPattern: document.getElementById("pageNumberPattern").value
        };
      }

      function renderCollectorSummary(data) {
        collectorSummary.textContent = JSON.stringify({
          stopReason: data.stopReason,
          stopDetails: data.stopDetails,
          totalPages: data.totalPages,
          stats: data.stats || {},
          configUsed: data.configUsed || {}
        }, null, 2);
      }

      function showError(message) {
        statusBox.classList.remove("visible");
        errorBox.textContent = message;
        errorBox.classList.add("visible");
      }

      function clearStatus() {
        errorBox.classList.remove("visible");
        downloadLink.classList.remove("visible");
        statusBox.classList.add("visible");
      }

      txtFile.addEventListener("change", async () => {
        const file = txtFile.files && txtFile.files[0];
        if (!file) return;
        urlsText.value = await file.text();
        collectedPagesJson = [];
        pagesJsonPreview.textContent = "[]";
        collectorSummary.textContent = "已手动载入 TXT，暂无浏览器收集统计。";
        collectionMeta.textContent = "已从 TXT 文件载入链接列表。";
      });

      collectorMode.addEventListener("change", toggleCollectorMode);
      toggleCollectorMode();

      collectBtn.addEventListener("click", async () => {
        clearStatus();
        statusBox.textContent = "正在启动项目专用 Chrome 并收集图片链接，请稍候...";
        collectBtn.disabled = true;
        submitBtn.disabled = true;

        try {
          const response = await fetch("/api/collect-from-browser", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              targetUrl: targetUrl.value,
              collectorOptions: readCollectorOptions()
            })
          });
          const rawText = await response.text();
          let data = null;
          try {
            data = rawText ? JSON.parse(rawText) : null;
          } catch (parseError) {
            throw new Error(`收集接口返回了非 JSON 响应（HTTP ${response.status}）：${rawText.slice(0, 300)}`);
          }
          if (!response.ok || !data.ok) {
            throw new Error(data.error || `收集失败（HTTP ${response.status}）`);
          }
          urlsText.value = data.urlsText;
          collectedPagesJson = data.pagesJson;
          pagesJsonPreview.textContent = JSON.stringify(data.pagesJson, null, 2);
          renderCollectorSummary(data);
          collectionMeta.textContent = `已收集 ${data.totalPages} 张图片链接，停止原因：${data.stopReason || "unknown"}。`;
          statusBox.textContent = "收集完成，可以直接生成 PDF。";
        } catch (error) {
          showError(error && error.message ? error.message : String(error));
        } finally {
          collectBtn.disabled = false;
          submitBtn.disabled = false;
        }
      });

      submitBtn.addEventListener("click", async () => {
        clearStatus();
        statusBox.textContent = "正在下载图片并生成 PDF，请稍候...";
        submitBtn.disabled = true;
        collectBtn.disabled = true;

        try {
          const response = await fetch("/api/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              urlsText: urlsText.value,
              outputName: outputName.value,
              pagesJson: collectedPagesJson
            })
          });
          const rawText = await response.text();
          let data = null;
          try {
            data = rawText ? JSON.parse(rawText) : null;
          } catch (parseError) {
            throw new Error(`导出接口返回了非 JSON 响应（HTTP ${response.status}）：${rawText.slice(0, 300)}`);
          }
          if (!response.ok || !data.ok) {
            throw new Error(data.error || `生成失败（HTTP ${response.status}）`);
          }
          statusBox.textContent = `已生成 ${data.totalPages} 页 PDF。`;
          downloadLink.href = data.downloadUrl;
          downloadLink.textContent = "下载生成的 PDF";
          downloadLink.classList.add("visible");
        } catch (error) {
          showError(error && error.message ? error.message : String(error));
        } finally {
          submitBtn.disabled = false;
          collectBtn.disabled = false;
        }
      });
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
