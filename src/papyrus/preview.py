"""Live preview server for Papyrus reports."""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

from . import _preview_css_js as _assets

_log = logging.getLogger(__name__)

_PREVIEW_MARKER_START = "<!-- papyrus-preview-start -->"
_PREVIEW_MARKER_END = "<!-- papyrus-preview-end -->"


def _inject_preview(html: str, base_url: str, filename: str = "") -> str:
    """Inject preview CSS/JS markers before </body>."""
    save_url = base_url.rstrip("/") + "/save"
    fname_js = f"\n<script>window.__papyrusFilename={json.dumps(filename)};</script>"
    snippet = (
        f"\n{_PREVIEW_MARKER_START}\n"
        + _assets.PREVIEW_CSS.replace("{{SAVE_URL}}", save_url)
        + _assets.PREVIEW_JS.replace("{{SAVE_URL}}", save_url)
        + fname_js
        + f"\n{_PREVIEW_MARKER_END}\n"
    )
    return html.replace("</body>", snippet + "</body>", 1)


class _Handler(BaseHTTPRequestHandler):
    """Request handler with routes for preview, dashboard, PDF, thumbnail."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/dashboard":
            self._serve_dashboard()
        elif path == "/export-pdf":
            self._serve_pdf(qs)
        elif path.startswith("/thumbnail/"):
            self._serve_thumbnail(path)
        elif path == "/":
            self._serve_html_default()
        elif path.endswith(".html"):
            self._serve_html_by_name(path.lstrip("/"))
        else:
            self._respond(404, b"Not Found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/save":
            self._handle_save()
        else:
            self._respond(404, b"Not Found", "text/plain")

    # -- route handlers --------------------------------------------------

    def _serve_dashboard(self) -> None:
        from ._preview_dashboard import build_html
        reports_dir = self._reports_dir()
        body = build_html(reports_dir).encode("utf-8")
        self._respond(200, body, "text/html; charset=utf-8")

    def _serve_pdf(self, qs: dict) -> None:
        fname = (qs.get("file") or [""])[0]
        if not fname:
            self._respond(400, b"missing file param", "text/plain")
            return
        reports_dir = self._reports_dir()
        html_path = reports_dir / fname
        if not html_path.exists() or not html_path.suffix == ".html":
            self._respond(404, b"file not found", "text/plain")
            return
        try:
            from ._preview_pdf import render_pdf
            pdf_bytes = render_pdf(html_path, self._port())
        except Exception as exc:
            _log.debug("PDF export failed: %s", exc)
            self._respond(503, b"playwright unavailable", "text/plain")
            return
        pdf_name = html_path.stem + ".pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{pdf_name}"',
        )
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def _serve_thumbnail(self, path: str) -> None:
        fname = path.split("/thumbnail/", 1)[-1]
        if not fname or ".." in fname:
            self._respond(404, b"Not Found", "text/plain")
            return
        reports_dir = self._reports_dir()
        thumb_path = reports_dir / fname
        if not thumb_path.exists():
            self._respond(404, b"Not Found", "text/plain")
            return
        body = thumb_path.read_bytes()
        self._respond(200, body, "image/png")

    def _serve_html_default(self) -> None:
        html_path = getattr(self.server, "html_path", None)
        if html_path is None or not html_path.exists():
            self._redirect("/dashboard")
            return
        html = html_path.read_text(encoding="utf-8")
        base_url = self.server.base_url  # type: ignore[attr-defined]
        injected = _inject_preview(html, base_url, html_path.name)
        self._respond(200, injected.encode(), "text/html; charset=utf-8")

    def _serve_html_by_name(self, filename: str) -> None:
        reports_dir = self._reports_dir()
        target = reports_dir / filename
        if not target.exists():
            self._respond(404, b"Not Found", "text/plain")
            return
        html = target.read_text(encoding="utf-8")
        base_url = self.server.base_url  # type: ignore[attr-defined]
        injected = _inject_preview(html, base_url, filename)
        self._respond(200, injected.encode(), "text/html; charset=utf-8")

    def _handle_save(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        data = json.loads(raw)
        html_path = getattr(self.server, "html_path", None)
        if html_path is None:
            self._respond(400, b"no target file", "text/plain")
            return
        html_path.write_text(data["html"], encoding="utf-8")
        self._respond(
            200, json.dumps({"ok": True}).encode(), "application/json",
        )

    # -- helpers ---------------------------------------------------------

    def _reports_dir(self) -> Path:
        return self.server.reports_dir  # type: ignore[attr-defined]

    def _port(self) -> int:
        return self.server.server_address[1]

    def _respond(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:  # noqa: ANN002
        pass


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class PreviewServer:
    """Thin wrapper around a threaded HTTP server."""

    def __init__(
        self,
        html_path: Path | None = None,
        *,
        reports_dir: Path | None = None,
    ) -> None:
        if html_path is not None:
            self._html_path: Path | None = html_path.resolve()
            self._reports_dir = html_path.resolve().parent
        else:
            self._html_path = None
            self._reports_dir = (
                reports_dir.resolve() if reports_dir else Path.cwd()
            )
        self._httpd: _ThreadingHTTPServer | None = None
        self.port: int = 0

    def start(self) -> None:
        httpd = _ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        httpd.html_path = self._html_path  # type: ignore[attr-defined]
        httpd.reports_dir = self._reports_dir  # type: ignore[attr-defined]
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


def open_dashboard_in_browser(reports_dir: Path) -> PreviewServer:
    """Start a preview server and open the dashboard in a browser."""
    srv = PreviewServer(reports_dir=reports_dir)
    srv.start()
    webbrowser.open(f"http://127.0.0.1:{srv.port}/dashboard")
    return srv
