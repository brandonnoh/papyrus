"""Thumbnail generation for Papyrus reports."""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_THUMB_WIDTH = 300
_THUMB_HEIGHT = 424  # A4 ratio 1:sqrt(2)


def generate_thumbnail(
    html_path: Path,
    server_port: int,
) -> Path | None:
    """Capture a thumbnail of the first page via the preview server.

    Args:
        html_path: Path to the HTML report file.
        server_port: Port of the running preview server.

    Returns:
        Path to the generated thumbnail PNG, or None if playwright
        is not available.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log.debug("playwright not installed -- skipping thumbnail")
        return None

    url = f"http://127.0.0.1:{server_port}/{html_path.name}"
    thumb_path = html_path.parent / f"{html_path.stem}.thumb.png"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 1697})
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("document.fonts.ready")
            page.evaluate(
                "document.querySelectorAll('.preview-toolbar,.no-print')"
                ".forEach(el => el.style.display='none')"
            )

            target = _find_first_page(page)
            if target:
                box = target.bounding_box()
                if box:
                    page.screenshot(
                        path=str(thumb_path),
                        clip={
                            "x": box["x"], "y": box["y"],
                            "width": box["width"], "height": box["height"],
                        },
                    )
                else:
                    target.screenshot(path=str(thumb_path))
            else:
                page.screenshot(
                    path=str(thumb_path),
                    clip={"x": 0, "y": 0, "width": 1200, "height": 1697},
                )

            _resize_thumb(thumb_path)
            browser.close()
    except Exception:
        _log.exception("thumbnail generation failed")
        return None

    return thumb_path if thumb_path.exists() else None


def _find_first_page(page):  # noqa: ANN001, ANN201
    """Locate the first preview page element."""
    for sel in (".preview-page:first-of-type", ".page--body:first-child"):
        el = page.query_selector(sel)
        if el:
            return el
    return None


def _resize_thumb(path: Path) -> None:
    """Resize screenshot to standard thumbnail dimensions."""
    try:
        from PIL import Image
        img = Image.open(path)
        img = img.resize((_THUMB_WIDTH, _THUMB_HEIGHT), Image.LANCZOS)
        img.save(path)
        return
    except ImportError:
        pass
    # PIL 없으면 Playwright 재사용 없이 간단 crop — 비율만 맞춤
    # (이 경로는 PIL 없을 때만 실행, 크기는 원본 유지)
    pass
