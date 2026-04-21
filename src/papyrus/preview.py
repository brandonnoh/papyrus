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
  .preview-page-num {
    position: absolute;
    bottom: 5mm;
    left: 0; right: 0;
    text-align: center;
    font-family: var(--font-heading);
    font-size: var(--size-page-num);
    color: var(--color-text-page-meta);
  }
}
@media print {
  .preview-toolbar, .save-toast, .preview-page-num, [data-papyrus-clone] { display: none !important; }
  @page { margin: var(--page-margin); }
  .page { padding: 0 !important; }
  .preview-page { display: contents; }
  .page--body { min-height: 0 !important; }
  .page--cover { height: 100vh !important; }
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
      Array.from(pg.children).forEach(function(el) {
        if (!el.dataset.papyrusClone && !el.dataset.papyrusPageNum) savedEls.push(el);
      });
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

    var rawEls = [];
    var existingPages = Array.from(bodyEl.querySelectorAll('.preview-page'));
    if (existingPages.length > 0) {
      existingPages.forEach(function(pg) {
        Array.from(pg.children).forEach(function(el) {
          if (!el.dataset.papyrusClone && !el.dataset.papyrusPageNum) rawEls.push(el);
        });
        pg.remove();
      });
    } else {
      rawEls = Array.from(bodyEl.children);
      rawEls.forEach(function(el) { bodyEl.removeChild(el); });
    }

    var headerEl = null;
    var sections = [];
    rawEls.forEach(function(el) {
      if (el.classList.contains('doc-header')) headerEl = el;
      else sections.push(el);
    });

    var entries = [];
    sections.forEach(function(sec) {
      if (sec.classList.contains('doc-section')) {
        var cls = sec.className;
        Array.from(sec.children).forEach(function(child) {
          entries.push({el: child, wrapClass: cls});
        });
      } else {
        entries.push({el: sec, wrapClass: null});
      }
    });

    if (entries.length === 0) return;

    var measPage = document.createElement('div');
    measPage.className = 'preview-page';
    measPage.style.cssText = 'visibility:hidden;position:absolute;top:0;left:-9999px';
    document.body.appendChild(measPage);
    if (headerEl) measPage.appendChild(headerEl.cloneNode(true));
    var measSec = document.createElement('section');
    measSec.className = 'doc-section';
    measPage.appendChild(measSec);
    entries.forEach(function(e) { measSec.appendChild(e.el); });

    var heights = entries.map(function(e, i) {
      var next = i + 1 < entries.length ? entries[i + 1].el : null;
      if (next) return next.getBoundingClientRect().top - e.el.getBoundingClientRect().top;
      var rect = e.el.getBoundingClientRect();
      return rect.height + parseFloat(window.getComputedStyle(e.el).marginBottom || '0');
    });

    var r1 = document.createElement('div');
    r1.style.cssText = 'height:297mm;position:absolute;visibility:hidden;pointer-events:none';
    var r2 = document.createElement('div');
    r2.style.cssText = 'height:18mm;position:absolute;visibility:hidden;pointer-events:none';
    document.body.appendChild(r1);
    document.body.appendChild(r2);
    var pageH = r1.offsetHeight;
    var marginPx = r2.offsetHeight;
    document.body.removeChild(r1);
    document.body.removeChild(r2);

    var hdrH = 0;
    var measHdr = measPage.querySelector('.doc-header');
    if (measHdr) {
      var hst = window.getComputedStyle(measHdr);
      hdrH = measHdr.getBoundingClientRect().height + parseFloat(hst.marginBottom || '0');
    }
    var availH = pageH - 2 * marginPx - hdrH;

    document.body.removeChild(measPage);

    var allPages = [];
    var currentPage = null;
    var curWrap = null;
    var curWrapClass = null;
    var usedH = 0;

    function newPage(isFirst) {
      var page = document.createElement('div');
      page.className = 'preview-page';
      bodyEl.appendChild(page);
      if (headerEl) {
        var h = isFirst ? headerEl : headerEl.cloneNode(true);
        if (!isFirst) h.dataset.papyrusClone = 'true';
        page.appendChild(h);
      }
      var numEl = document.createElement('div');
      numEl.className = 'preview-page-num';
      numEl.dataset.papyrusPageNum = 'true';
      page.appendChild(numEl);
      allPages.push({page: page, numEl: numEl});
      curWrap = null;
      curWrapClass = null;
      return page;
    }

    function tableMinHeight(table, fallback) {
      var thead = table.querySelector('thead');
      var firstRow = table.querySelector('tbody > tr');
      if (!firstRow) return fallback;
      var md = document.createElement('div');
      md.className = 'preview-page';
      md.style.cssText = 'visibility:hidden;position:absolute;top:0;left:-9999px';
      document.body.appendChild(md);
      var ms = document.createElement('section');
      ms.className = 'doc-section';
      md.appendChild(ms);
      var mt = table.cloneNode(false);
      if (thead) mt.appendChild(thead.cloneNode(true));
      var mb = document.createElement('tbody');
      mb.appendChild(firstRow.cloneNode(true));
      mt.appendChild(mb);
      ms.appendChild(mt);
      var minH = mt.getBoundingClientRect().height;
      document.body.removeChild(md);
      return minH;
    }

    function splitTableByRows(table, remainH) {
      var thead = table.querySelector('thead');
      var tbody = table.querySelector('tbody');
      if (!tbody) return null;
      var rows = Array.from(tbody.querySelectorAll('tr'));
      if (rows.length <= 1) return null;

      var md = document.createElement('div');
      md.className = 'preview-page';
      md.style.cssText = 'visibility:hidden;position:absolute;top:0;left:-9999px';
      document.body.appendChild(md);
      var ms = document.createElement('section');
      ms.className = 'doc-section';
      md.appendChild(ms);
      var mT = table.cloneNode(false);
      if (thead) mT.appendChild(thead.cloneNode(true));
      var mB = document.createElement('tbody');
      mT.appendChild(mB);
      ms.appendChild(mT);

      var splitAt = rows.length;
      for (var k = 0; k < rows.length; k++) {
        mB.appendChild(rows[k].cloneNode(true));
        if (mT.getBoundingClientRect().height > remainH) { splitAt = k; break; }
      }
      document.body.removeChild(md);
      if (splitAt === 0 || splitAt === rows.length) return null;

      var t1 = table.cloneNode(false);
      if (thead) t1.appendChild(thead.cloneNode(true));
      var b1 = document.createElement('tbody'); t1.appendChild(b1);
      var t2 = table.cloneNode(false);
      if (thead) t2.appendChild(thead.cloneNode(true));
      var b2 = document.createElement('tbody'); t2.appendChild(b2);
      rows.forEach(function(row, idx) { (idx < splitAt ? b1 : b2).appendChild(row); });

      var md2 = document.createElement('div');
      md2.className = 'preview-page';
      md2.style.cssText = 'visibility:hidden;position:absolute;top:0;left:-9999px';
      document.body.appendChild(md2);
      var ms2 = document.createElement('section');
      ms2.className = 'doc-section';
      md2.appendChild(ms2);
      var c1 = t1.cloneNode(true); ms2.appendChild(c1);
      var rh1 = c1.getBoundingClientRect().height;
      ms2.removeChild(c1);
      var c2 = t2.cloneNode(true); ms2.appendChild(c2);
      var rh2 = c2.getBoundingClientRect().height;
      document.body.removeChild(md2);

      return {parts: [t1, t2], heights: [rh1, rh2]};
    }

    currentPage = newPage(true);

    var ei = 0;
    while (ei < entries.length) {
      var e = entries[ei];
      var h = heights[ei];
      var isHead = e.el.tagName === 'H2' || e.el.tagName === 'H3';
      var orphanPad = 0;
      if (isHead) {
        var j = ei + 1;
        while (j < entries.length) {
          var isNextHead = entries[j].el.tagName === 'H2' || entries[j].el.tagName === 'H3';
          var nextMinH = isNextHead ? heights[j]
            : entries[j].el.tagName === 'TABLE'
              ? tableMinHeight(entries[j].el, heights[j])
              : heights[j];
          orphanPad += nextMinH;
          if (!isNextHead) break;
          j++;
        }
      }

      if (e.el.tagName === 'TABLE') {
        var pgTop = currentPage.getBoundingClientRect().top;
        var liveRemain = (pgTop + marginPx + availH) - (function() {
          var lastBottom = pgTop + marginPx + hdrH;
          currentPage.querySelectorAll('section > *').forEach(function(el) {
            var b = el.getBoundingClientRect().bottom
              + parseFloat(window.getComputedStyle(el).marginBottom || '0');
            if (b > lastBottom) lastBottom = b;
          });
          return lastBottom;
        })();

        if (liveRemain < h) {
          if (liveRemain > 60) {
            var split = splitTableByRows(e.el, liveRemain);
            if (split) {
              entries.splice(ei, 1,
                {el: split.parts[0], wrapClass: e.wrapClass},
                {el: split.parts[1], wrapClass: e.wrapClass}
              );
              heights.splice(ei, 1, split.heights[0], split.heights[1]);
              continue;
            }
          }
          if (usedH > 0) {
            currentPage = newPage(false);
            usedH = 0;
            continue;
          }
        }
      }

      if (usedH > 0 && usedH + h + orphanPad > availH) {
        currentPage = newPage(false);
        usedH = 0;
      }

      if (e.wrapClass !== null) {
        if (!curWrap || curWrapClass !== e.wrapClass) {
          curWrap = document.createElement('section');
          curWrap.className = e.wrapClass;
          currentPage.appendChild(curWrap);
          curWrapClass = e.wrapClass;
        }
        curWrap.appendChild(e.el);
      } else {
        currentPage.appendChild(e.el);
        curWrap = null;
        curWrapClass = null;
      }
      usedH += h;
      ei++;
    }

    var hasCover = !!document.querySelector('.page--cover');
    var offset = hasCover ? 1 : 0;
    var total = allPages.length + offset;
    allPages.forEach(function(p, i) {
      p.numEl.textContent = (i + 1 + offset) + ' / ' + total;
    });

    document.querySelectorAll('.doc-section').forEach(function(sec) {
      sec.setAttribute('contenteditable', 'true');
    });
  }

  var _buildTimer = null;
  var _justBuilt = false;

  function safeBuild() {
    clearTimeout(_buildTimer);
    _buildTimer = setTimeout(function() {
      _justBuilt = true;
      buildPreviewPages();
      setTimeout(function() { _justBuilt = false; }, 400);
    }, 0);
  }

  function scheduleInitialBuild() {
    var fontReady = (document.fonts && document.fonts.ready) || Promise.resolve();
    var imgPromises = Array.from(document.images)
      .filter(function(img) { return !img.complete; })
      .map(function(img) {
        return new Promise(function(resolve) { img.onload = img.onerror = resolve; });
      });
    Promise.all([fontReady].concat(imgPromises)).then(safeBuild);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scheduleInitialBuild);
  } else {
    scheduleInitialBuild();
  }

  if (typeof ResizeObserver !== 'undefined') {
    var _attachObserver = function() {
      var bodyEl = document.querySelector('.page--body');
      if (!bodyEl) return;
      new ResizeObserver(function() {
        if (_justBuilt) return;
        clearTimeout(_buildTimer);
        _buildTimer = setTimeout(function() {
          _justBuilt = true;
          buildPreviewPages();
          setTimeout(function() { _justBuilt = false; }, 400);
        }, 200);
      }).observe(bodyEl);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _attachObserver);
    } else {
      _attachObserver();
    }
  }

  window.__papyrusBuildPages = buildPreviewPages;
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
