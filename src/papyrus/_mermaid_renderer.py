"""Mermaid.js diagram rendering — code block detection + CDN injection."""

from __future__ import annotations

import html
import re

# Matches <pre><code class="language-mermaid">...</code></pre>
_MERMAID_BLOCK_RE = re.compile(
    r'<pre><code\s+class="language-mermaid">(.*?)</code></pre>',
    re.DOTALL,
)

_MERMAID_CDN = (
    "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
)

_SUPPORTED_TYPES = frozenset({
    "flowchart", "graph", "sequencediagram", "mindmap",
})


def _is_supported(diagram_src: str) -> bool:
    """Check if diagram type is in the supported set."""
    first_word = diagram_src.strip().split()[0] if diagram_src.strip() else ""
    return first_word.lower() in _SUPPORTED_TYPES


def _layout_variant(diagram_src: str) -> str:
    """Return CSS modifier class based on diagram layout type."""
    first = diagram_src.strip().split()[0].lower() if diagram_src.strip() else ""
    if first in {"sequencediagram"}:
        return " papyrus-mermaid--tall"
    tokens = diagram_src.strip().split()
    if len(tokens) >= 2 and tokens[1].upper() in {"TD", "TB"}:
        return " papyrus-mermaid--vertical"
    return ""


def _decode_html_entities(text: str) -> str:
    """Restore HTML-encoded characters back to plain text."""
    return html.unescape(text)


def inject_mermaid_diagrams(
    full_html: str, primary_color: str,
) -> str:
    """Replace mermaid code blocks with div.mermaid + inject CDN."""
    blocks = list(_MERMAID_BLOCK_RE.finditer(full_html))
    if not blocks:
        return full_html

    found = False
    for match in reversed(blocks):
        raw = _decode_html_entities(match.group(1))
        if not _is_supported(raw):
            continue
        found = True
        variant = _layout_variant(raw)
        diagram_div = (
            f'<div class="papyrus-mermaid-wrap{variant}">'
            f'<pre class="mermaid">{raw}</pre>'
            f'</div>'
        )
        full_html = (
            full_html[:match.start()]
            + diagram_div
            + full_html[match.end():]
        )

    if not found:
        return full_html

    init_script = _build_init_script(primary_color)
    full_html = full_html.replace("</body>", init_script + "\n</body>")
    return full_html


def _build_init_script(primary_color: str) -> str:
    """Generate Mermaid.js CDN load + initialize script."""
    return (
        f'<script src="{_MERMAID_CDN}"></script>\n'
        f"<script>\n"
        f"mermaid.initialize({{\n"
        f"  startOnLoad: true,\n"
        f"  theme: 'base',\n"
        f"  flowchart: {{ useMaxWidth: true }},\n"
        f"  sequence: {{ useMaxWidth: true, width: 500 }},\n"
        f"  themeVariables: {{\n"
        f"    primaryColor: '{primary_color}20',\n"
        f"    primaryBorderColor: '{primary_color}',\n"
        f"    primaryTextColor: '#1a1a1a',\n"
        f"    lineColor: '{primary_color}',\n"
        f"    secondaryColor: '#f0f4f8',\n"
        f"    tertiaryColor: '#e8eaed',\n"
        f"    fontFamily: \"'Noto Sans KR', sans-serif\",\n"
        f"    fontSize: '11px'\n"
        f"  }}\n"
        f"}});\n"
        f"</script>"
    )
