"""Live preview server for Papyrus reports."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

_PREVIEW_MARKER_START = "<!-- papyrus-preview-start -->"
_PREVIEW_MARKER_END = "<!-- papyrus-preview-end -->"

_PREVIEW_CSS = """<style>
@media screen {
  .page--body {
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
    min-height: 0 !important;
  }
  .page--body::after { display: none !important; }
  .preview-page {
    width: var(--page-width);
    min-height: var(--page-height);
    margin: 12px auto;
    padding: var(--page-margin);
    background: var(--color-bg-page);
    box-shadow: var(--shadow-page);
    box-sizing: border-box;
    position: relative;
  }
  [contenteditable]:hover { outline: 1px dashed #b0c4de; border-radius: 2px; }
  [contenteditable]:focus { outline: 2px solid #09356E; border-radius: 2px; }
  .preview-toolbar {
    position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
    background: rgba(9,53,110,0.92); color: #fff; padding: 6px 16px;
    border-radius: 20px; font: 12px/1.5 'Noto Sans KR',sans-serif;
    display: flex; gap: 12px; align-items: center;
    z-index: 1000; backdrop-filter: blur(4px);
    box-shadow: 0 2px 12px rgba(0,0,0,0.25);
  }
  .preview-toolbar .dirty-indicator {
    width: 6px; height: 6px; border-radius: 50%;
    background: #ff6b6b; display: none;
  }
  .preview-toolbar.is-dirty .dirty-indicator { display: block; }
  .preview-toolbar button {
    background: none; border: none; color: #fff;
    cursor: pointer; font: inherit; padding: 0;
  }
  .preview-toolbar button:hover { opacity: 0.75; }
  .save-toast {
    position: fixed; bottom: 24px; right: 24px;
    background: #09356E; color: #fff;
    padding: 8px 16px; border-radius: 8px;
    font: 12px 'Noto Sans KR',sans-serif;
    opacity: 0; transition: opacity 0.3s;
    pointer-events: none; z-index: 2000;
  }
  .save-toast.show { opacity: 1; }
  .doc-section { position: relative; }
  .drag-handle {
    position: absolute; left: -20px; top: 8px;
    width: 16px; height: 16px; cursor: grab;
    color: #ccc; font-size: 14px; line-height: 1;
    opacity: 0; transition: opacity 0.15s;
    user-select: none;
  }
  .doc-section:hover .drag-handle { opacity: 1; }
  .doc-section.dragging { opacity: 0.4; border: 1px dashed #09356E; }
  .doc-section.drop-target { border-top: 3px solid #09356E; }
}
@media print {
  .preview-toolbar, .save-toast, .drag-handle { display: none !important; }
  .preview-page { all: unset; }
}
</style>"""

_PREVIEW_JS = """<script>
(function() {
  var SAVE_URL = '{{SAVE_URL}}';
  var _dirty = false;

  var toolbar = document.createElement('div');
  toolbar.className = 'preview-toolbar';
  toolbar.innerHTML = '<span class="dirty-indicator"></span><span>편집 모드</span>'
    + '<button onclick="window.__papyrusSave()">저장 (⌘S)</button>'
    + '<button onclick="window.print()">인쇄</button>';

  var toast = document.createElement('div');
  toast.className = 'save-toast';
  toast.textContent = '저장됨 ✓';

  document.addEventListener('DOMContentLoaded', function() {
    document.body.appendChild(toolbar);
    document.body.appendChild(toast);
    document.querySelectorAll('.doc-section').forEach(function(sec) {
      sec.setAttribute('contenteditable', 'true');
    });
    var bodyEl = document.querySelector('.page--body');
    if (bodyEl) {
      bodyEl.addEventListener('input', function() {
        _dirty = true;
        toolbar.classList.add('is-dirty');
      });
    }
  });

  window.__papyrusSave = function() {
    var bodyEl = document.querySelector('.page--body');
    var pages = bodyEl ? Array.from(bodyEl.querySelectorAll('.preview-page')) : [];
    var savedEls = [];
    pages.forEach(function(pg) {
      Array.from(pg.children).forEach(function(el) { savedEls.push(el); });
    });
    pages.forEach(function(pg) { pg.remove(); });
    savedEls.forEach(function(el) { bodyEl && bodyEl.appendChild(el); });

    document.querySelectorAll('[contenteditable]').forEach(function(el) {
      el.removeAttribute('contenteditable');
    });
    var html = document.documentElement.outerHTML;
    document.querySelectorAll('.doc-section').forEach(function(sec) {
      sec.setAttribute('contenteditable', 'true');
    });
    if (window.__papyrusBuildPages) window.__papyrusBuildPages();

    var clean = html.replace(
      /<!--\\s*papyrus-preview-start\\s*-->[\\s\\S]*?<!--\\s*papyrus-preview-end\\s*-->/g, ''
    );
    fetch(SAVE_URL, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({html: clean})
    }).then(function(r){ return r.json(); }).then(function(d) {
      if (d.ok) {
        _dirty = false;
        toolbar.classList.remove('is-dirty');
        toast.classList.add('show');
        setTimeout(function() { toast.classList.remove('show'); }, 2000);
      }
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
  function buildPreviewPages() {
    var bodyEl = document.querySelector('.page--body');
    if (!bodyEl) return;

    var elements = [];
    var pages = bodyEl.querySelectorAll('.preview-page');
    if (pages.length > 0) {
      pages.forEach(function(pg) {
        Array.from(pg.children).forEach(function(el) { elements.push(el); });
      });
      pages.forEach(function(pg) { pg.remove(); });
    } else {
      elements = Array.from(bodyEl.children);
      elements.forEach(function(el) { el.remove(); });
    }

    var a4H = bodyEl.offsetWidth * (297 / 210);

    function newPage() {
      var page = document.createElement('div');
      page.className = 'preview-page';
      bodyEl.appendChild(page);
      return page;
    }

    var currentPage = newPage();
    elements.forEach(function(el) {
      currentPage.appendChild(el);
      if (currentPage.scrollHeight > a4H && currentPage.children.length > 1) {
        currentPage.removeChild(el);
        currentPage = newPage();
        currentPage.appendChild(el);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', buildPreviewPages);
  if (typeof ResizeObserver !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
      var bodyEl = document.querySelector('.page--body');
      if (bodyEl) { new ResizeObserver(buildPreviewPages).observe(bodyEl); }
    });
  }
  window.__papyrusBuildPages = buildPreviewPages;
})();
(function() {
  var _draggingEl = null;

  function initDnD() {
    document.querySelectorAll('.doc-section').forEach(function(sec) {
      if (sec.querySelector('.drag-handle')) return;
      var handle = document.createElement('span');
      handle.className = 'drag-handle';
      handle.textContent = '\u2807';
      handle.title = '드래그하여 순서 변경';
      sec.insertBefore(handle, sec.firstChild);
      sec.setAttribute('draggable', 'true');

      sec.addEventListener('dragstart', function(e) {
        _draggingEl = sec;
        sec.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });
      sec.addEventListener('dragend', function() {
        sec.classList.remove('dragging');
        document.querySelectorAll('.drop-target').forEach(function(el) {
          el.classList.remove('drop-target');
        });
        if (window.__papyrusBuildPages) window.__papyrusBuildPages();
        if (window.__papyrusSave) window.__papyrusSave();
      });
      sec.addEventListener('dragover', function(e) {
        e.preventDefault();
        if (_draggingEl && _draggingEl !== sec) sec.classList.add('drop-target');
      });
      sec.addEventListener('dragleave', function() {
        sec.classList.remove('drop-target');
      });
      sec.addEventListener('drop', function(e) {
        e.preventDefault();
        sec.classList.remove('drop-target');
        if (!_draggingEl || _draggingEl === sec) return;
        sec.parentNode.insertBefore(_draggingEl, sec);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', initDnD);
  window.__papyrusInitDnD = initDnD;
})();
</script>"""


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
