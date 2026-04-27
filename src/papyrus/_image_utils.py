"""Image embedding utilities — layout blocks, standalone wrapping, base64."""

from __future__ import annotations

import base64
import ipaddress
import logging
import mimetypes
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
_DENIED_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "[::1]"})

_URL_SRC_RE = re.compile(
    r'<img\b[^>]*src\s*=\s*["\']'
    r"(https?://[^\"']*)"
    r'["\']',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_images(html: str, source_dir: Path) -> str:
    """Process layout blocks, wrap standalone imgs, embed as base64."""
    url_cache = _prefetch_urls(html)
    html = _process_layout_blocks(html, source_dir, url_cache)
    html = _wrap_standalone_imgs(html, source_dir, url_cache)
    return html


def _prefetch_urls(html: str) -> dict[str, str]:
    """Fetch all URL images in parallel, return {url: data_uri}."""
    urls = list(dict.fromkeys(_URL_SRC_RE.findall(html)))
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_fetch_url, urls))
    return dict(zip(urls, results))


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

# Matches any <img> tag (handles both <img ...> and <img ... />)
_IMG_TAG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)

_SRC_RE = re.compile(r'src\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_ALT_RE = re.compile(r'alt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _process_layout_blocks(
    html: str, source_dir: Path, url_cache: dict[str, str] | None = None,
) -> str:
    """<!-- img:left/right -->...<img>...text...<!-- /img --> -> grid div."""
    cache = url_cache or {}
    return _LAYOUT_BLOCK_RE.sub(
        lambda m: _build_layout(m.group(1), m.group(2), source_dir, cache),
        html,
    )


def _build_layout(
    direction: str, inner: str, source_dir: Path,
    url_cache: dict[str, str] | None = None,
) -> str:
    """Build a grid layout div from a matched block."""
    img_match = _IMG_TAG_RE.search(inner)
    if not img_match:
        return inner

    attrs = img_match.group(1)
    src = _extract_attr(_SRC_RE, attrs, "")
    alt = _extract_attr(_ALT_RE, attrs, "")
    new_src = _embed_src(src, source_dir, url_cache)
    if new_src == src and not src.startswith("data:"):
        alt = _missing_alt(src, alt)

    figcaption = f"\n    <figcaption>{alt}</figcaption>" if alt else ""
    figure_html = (
        f'  <figure class="img-layout__figure">\n'
        f'    <img src="{new_src}" alt="{alt}">'
        f"{figcaption}\n"
        f"  </figure>"
    )

    # Remove the <img> tag, then clean up any now-empty or orphaned <p> content
    text_content = inner[:img_match.start()] + inner[img_match.end():]
    text_content = re.sub(r"<p>\s*\n", "<p>", text_content)
    text_content = re.sub(r"<p>\s*</p>", "", text_content)
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


def _wrap_standalone_imgs(
    html: str, source_dir: Path, url_cache: dict[str, str] | None = None,
) -> str:
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
        new_src = _embed_src(src, source_dir, url_cache)
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


def _embed_src(
    src: str, source_dir: Path, url_cache: dict[str, str] | None = None,
) -> str:
    """Convert img src to base64 data URI."""
    if src.startswith("data:"):
        return src
    if src.startswith(("http://", "https://")):
        if url_cache and src in url_cache:
            return url_cache[src]
        return _fetch_url(src)
    return _read_local(src, source_dir)


def _is_denied_url(url: str) -> bool:
    """Block requests to private/internal network addresses."""
    host = urlparse(url).hostname or ""
    if host in _DENIED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _fetch_url(url: str) -> str:
    """Download URL and return base64 data URI, or original on failure."""
    if _is_denied_url(url):
        logger.warning("Blocked private/internal URL: %s", url)
        return url
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read(_MAX_IMAGE_BYTES + 1)
            mime = resp.headers.get_content_type() or _guess_mime(url)
        if len(data) > _MAX_IMAGE_BYTES:
            logger.warning("Image too large (>10MB): %s", url)
            return url
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        logger.warning("Failed to fetch image: %s", url)
        return url


def _read_local(src: str, source_dir: Path) -> str:
    """Read local file and return base64 data URI."""
    path = (source_dir / src).resolve()
    if not path.is_relative_to(source_dir.resolve()):
        return src
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
    """Return alt text for missing/failed image."""
    if src.startswith(("http://", "https://")):
        return _failed_url_alt(src)
    if not src.startswith("data:"):
        path = Path(src)
        if not path.is_absolute():
            return f"[이미지 없음: {src}]"
    return alt


def _failed_url_alt(url: str) -> str:
    """Build alt text for a URL that failed to fetch."""
    truncated = url if len(url) <= 60 else url[:57] + "..."
    return f"[이미지 로드 실패: {truncated}]"


def _extract_attr(pat: re.Pattern, attrs: str, default: str) -> str:
    """Extract an attribute value from an img tag's attributes."""
    m = pat.search(attrs)
    return m.group(1) if m else default
