"""Live preview server for Papyrus reports."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

# ---------------------------------------------------------------------------
# Markers & injected assets
# ---------------------------------------------------------------------------

_PREVIEW_MARKER_START = "<!-- papyrus-preview-start -->"
_PREVIEW_MARKER_END = "<!-- papyrus-preview-end -->"

_PREVIEW_CSS = """<style>
@media screen {
  .page-break-indicator {
    width: 100%;
    height: 24px;
    margin: 0;
    background: #e8e8e8;
    border-top: 2px dashed #bbb;
    border-bottom: 2px dashed #bbb;
    display: flex;
    align-items: center;
    justify-content: center;
    font: 10px/1 'Noto Sans KR', sans-serif;
    color: #999;
    letter-spacing: 0.5px;
    pointer-events: none;
    user-select: none;
  }
}
@media print {
  .preview-toolbar, .page-break-indicator { display: none !important; }
}
</style>"""

_PREVIEW_JS = """<script>
(function() {
  const SAVE_URL = '{{SAVE_URL}}';
  window.__papyrusSave = function() {
    const html = document.documentElement.outerHTML;
    const clean = html.replace(
      /<!--\\s*papyrus-preview-start\\s*-->[\\s\\S]*?<!--\\s*papyrus-preview-end\\s*-->/g,
      ''
    );
    fetch(SAVE_URL, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({html: clean})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.ok) console.log('papyrus: saved');
    });
  };
  document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      window.__papyrusSave();
    }
  });
})();
(function() {
  function refreshPageBreaks() {
    var bodyEl = document.querySelector('.page--body');
    if (!bodyEl) return;
    bodyEl.querySelectorAll('.page-break-indicator').forEach(function(el) { el.remove(); });
    var a4H = bodyEl.offsetWidth * (297 / 210);
    var sections = Array.from(bodyEl.querySelectorAll('.doc-section'));
    var pageNum = 1;
    sections.forEach(function(sec) {
      var secTop = sec.offsetTop;
      while (secTop > pageNum * a4H) {
        var ind = document.createElement('div');
        ind.className = 'page-break-indicator';
        ind.textContent = pageNum + '페이지 / ' + (pageNum + 1) + '페이지';
        sec.parentNode.insertBefore(ind, sec);
        pageNum++;
      }
    });
  }
  document.addEventListener('DOMContentLoaded', refreshPageBreaks);
  if (typeof ResizeObserver !== 'undefined') {
    var ro = new ResizeObserver(refreshPageBreaks);
    var bodyEl = document.querySelector('.page--body');
    if (bodyEl) ro.observe(bodyEl);
  }
  window.__papyrusRefreshPages = refreshPageBreaks;
})();
</script>"""


# ---------------------------------------------------------------------------
# Injection helper
# ---------------------------------------------------------------------------


def _inject_preview(html: str, base_url: str) -> str:
    """Inject preview CSS/JS markers before </body>."""
    save_url = base_url.rstrip("/") + "/save"
    snippet = (
        f"\n{_PREVIEW_MARKER_START}\n"
        + _PREVIEW_CSS.replace("{{SAVE_URL}}", save_url)
        + _PREVIEW_JS.replace("{{SAVE_URL}}", save_url)
        + f"\n{_PREVIEW_MARKER_END}\n"
    )
    return html.replace("</body>", snippet + "</body>", 1)


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """Request handler — reads html_path from server instance."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/":
            self._respond(404, b"Not Found", "text/plain")
            return
        html = self.server.html_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
        injected = _inject_preview(html, self.server.base_url)  # type: ignore[attr-defined]
        self._respond(200, injected.encode(), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/save":
            self._respond(404, b"Not Found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        data = json.loads(raw)
        self.server.html_path.write_text(  # type: ignore[attr-defined]
            data["html"], encoding="utf-8",
        )
        self._respond(200, json.dumps({"ok": True}).encode(), "application/json")

    def _respond(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:  # noqa: ANN002
        pass


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class PreviewServer:
    """Thin wrapper around a threaded HTTP server."""

    def __init__(self, html_path: Path) -> None:
        self._html_path = html_path.resolve()
        self._httpd: _ThreadingHTTPServer | None = None
        self.port: int = 0

    def start(self) -> None:
        httpd = _ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        httpd.html_path = self._html_path  # type: ignore[attr-defined]
        self.port = httpd.server_address[1]
        httpd.base_url = f"http://127.0.0.1:{self.port}"  # type: ignore[attr-defined]
        self._httpd = httpd
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def open_browser(self) -> None:
        webbrowser.open(self.url)


def open_preview(html_path: Path) -> PreviewServer:
    """Create, start, and open a preview server."""
    srv = PreviewServer(html_path)
    srv.start()
    srv.open_browser()
    return srv
