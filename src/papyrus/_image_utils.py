"""Image embedding utilities — layout blocks, standalone wrapping, base64."""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_images(html: str, source_dir: Path) -> str:
    """Process layout blocks, wrap standalone imgs, embed as base64."""
    html = _process_layout_blocks(html, source_dir)
    html = _wrap_standalone_imgs(html, source_dir)
    return html


# ---------------------------------------------------------------------------
# Layout block processor
# ---------------------------------------------------------------------------

_LAYOUT_BLOCK_RE = re.compile(
    r"<!--\s*img:(left|right)\s*-->(.*?)<!--\s*/img\s*-->",
    re.DOTALL | re.IGNORECASE,
)

_IMG_IN_P_RE = re.compile(
    r"<p>\s*<img\b([^>]*)>\s*</p>",
    re.IGNORECASE,
)

_SRC_RE = re.compile(r'src\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_ALT_RE = re.compile(r'alt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _process_layout_blocks(html: str, source_dir: Path) -> str:
    """<!-- img:left/right -->...<img>...text...<!-- /img --> -> grid div."""
    return _LAYOUT_BLOCK_RE.sub(
        lambda m: _build_layout(m.group(1), m.group(2), source_dir),
        html,
    )


def _build_layout(
    direction: str, inner: str, source_dir: Path,
) -> str:
    """Build a grid layout div from a matched block."""
    img_match = _IMG_IN_P_RE.search(inner)
    if not img_match:
        return inner

    attrs = img_match.group(1)
    src = _extract_attr(_SRC_RE, attrs, "")
    alt = _extract_attr(_ALT_RE, attrs, "")
    new_src = _embed_src(src, source_dir)
    if new_src == src and not src.startswith("data:"):
        alt = _missing_alt(src, alt)

    figcaption = f"\n    <figcaption>{alt}</figcaption>" if alt else ""
    figure_html = (
        f'  <figure class="img-layout__figure">\n'
        f'    <img src="{new_src}" alt="{alt}">'
        f"{figcaption}\n"
        f"  </figure>"
    )

    text_content = inner[:img_match.start()] + inner[img_match.end():]
    text_content = text_content.strip()
    text_html = f'  <div class="img-layout__text">\n    {text_content}\n  </div>'

    cls = f"img-layout img-layout--{direction.lower()}"
    if direction.lower() == "left":
        children = f"{figure_html}\n{text_html}"
    else:
        children = f"{text_html}\n{figure_html}"

    return f'<div class="{cls}">\n{children}\n</div>'


# ---------------------------------------------------------------------------
# Standalone image wrapper
# ---------------------------------------------------------------------------

_STANDALONE_IMG_RE = re.compile(
    r"<p>\s*<img\b([^>]*)>\s*</p>",
    re.IGNORECASE,
)


def _wrap_standalone_imgs(html: str, source_dir: Path) -> str:
    """<p><img ...></p> -> <figure class="img-full">..."""
    parts: list[str] = []
    last_end = 0

    for m in _STANDALONE_IMG_RE.finditer(html):
        attrs = m.group(1)
        if "chart-print-img" in attrs:
            continue
        if _inside_context(html, m.start()):
            continue

        src = _extract_attr(_SRC_RE, attrs, "")
        alt = _extract_attr(_ALT_RE, attrs, "")
        new_src = _embed_src(src, source_dir)
        if new_src == src and not src.startswith("data:"):
            alt = _missing_alt(src, alt)

        figcaption = (
            f"\n  <figcaption>{alt}</figcaption>" if alt else ""
        )
        replacement = (
            f'<figure class="img-full">\n'
            f'  <img src="{new_src}" alt="{alt}">'
            f"{figcaption}\n"
            f"</figure>"
        )
        parts.append(html[last_end:m.start()])
        parts.append(replacement)
        last_end = m.end()

    parts.append(html[last_end:])
    return "".join(parts)


def _inside_context(html: str, pos: int) -> bool:
    """Check if pos is inside <figure> or .img-layout."""
    before = html[:pos]
    fig_open = before.rfind("<figure")
    fig_close = before.rfind("</figure>")
    if fig_open > fig_close:
        return True
    layout_open = before.rfind("img-layout")
    if layout_open != -1:
        div_close = before.rfind("</div>", layout_open)
        if div_close == -1 or div_close < layout_open:
            return True
    return False


# ---------------------------------------------------------------------------
# Base64 embedding
# ---------------------------------------------------------------------------


def _embed_src(src: str, source_dir: Path) -> str:
    """Convert img src to base64 data URI."""
    if src.startswith("data:"):
        return src
    if src.startswith(("http://", "https://")):
        return _fetch_url(src)
    return _read_local(src, source_dir)


def _fetch_url(url: str) -> str:
    """Download URL and return base64 data URI, or original on failure."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read()
        mime = resp.headers.get_content_type() or _guess_mime(url)
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        logger.warning("Failed to fetch image: %s", url)
        return url


def _read_local(src: str, source_dir: Path) -> str:
    """Read local file and return base64 data URI."""
    path = (source_dir / src).resolve()
    if not path.is_file():
        return src
    data = path.read_bytes()
    mime = _guess_mime(str(path))
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _guess_mime(path: str) -> str:
    """Guess MIME type from path, fallback to image/png."""
    mime, _ = mimetypes.guess_type(path)
    return mime or "image/png"


def _missing_alt(src: str, alt: str) -> str:
    """Return alt text for missing local file."""
    if not (src.startswith("data:") or src.startswith(("http://", "https://"))):
        path = Path(src)
        if not path.is_absolute():
            return f"[이미지 없음: {src}]"
    return alt


def _extract_attr(pat: re.Pattern, attrs: str, default: str) -> str:
    """Extract an attribute value from an img tag's attributes."""
    m = pat.search(attrs)
    return m.group(1) if m else default
