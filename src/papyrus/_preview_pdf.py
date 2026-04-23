"""Playwright-based PDF rendering for Papyrus reports."""

from __future__ import annotations

from pathlib import Path


class PlaywrightNotAvailable(Exception):
    """Raised when playwright is not installed."""


def render_pdf(html_path: Path, server_port: int) -> bytes:
    """Render an A4 PDF from the given HTML file via the preview server.

    Args:
        html_path: Path to the HTML report file.
        server_port: Port of the running preview server.

    Returns:
        PDF content as bytes.

    Raises:
        PlaywrightNotAvailable: If playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightNotAvailable(
            "playwright가 설치되지 않았습니다. "
            "pip install playwright && playwright install chromium"
        ) from exc

    url = f"http://127.0.0.1:{server_port}/{html_path.name}"
    zero = {"top": "0", "right": "0", "bottom": "0", "left": "0"}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_function("document.fonts.ready")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin=zero,
        )
        browser.close()

    return pdf_bytes
