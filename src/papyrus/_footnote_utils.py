"""Footnote rendering utilities — pure functions, no IO."""

from __future__ import annotations

import re

import markdown as md

from papyrus.parser import Section, _preprocess_callouts, _replace_blockquotes


def render_sections_with_footnotes(
    sections: list[Section],
) -> tuple[list[str], str]:
    """Render all sections in one pass to ensure global footnote numbering.

    Returns: (section_html_list, footnotes_html)
    """
    combined = "\n\n".join(
        f"## {s.heading}\n{s.content}" for s in sections
    )
    preprocessed = _preprocess_callouts(combined)
    full_html = md.markdown(preprocessed, extensions=["tables", "footnotes"])
    full_html = _replace_blockquotes(full_html)
    body_html, footnotes_html = _strip_footnote_block(full_html)
    section_htmls = _split_sections_from_html(body_html, sections)
    return section_htmls, footnotes_html


def _strip_footnote_block(html: str) -> tuple[str, str]:
    """Separate the trailing <div class="footnote">...</div> block.

    Returns: (body_html, footnotes_html). Empty string if no footnotes.
    """
    match = re.search(r'<div class="footnote">', html)
    if not match:
        return html, ""
    start = match.start()
    return html[:start].rstrip(), html[start:].strip()


def _split_sections_from_html(
    html: str, sections: list[Section],
) -> list[str]:
    """Split full-body HTML by <h2> tags into per-section html_content.

    Each section's html_content excludes the <h2> tag itself.
    """
    parts = re.split(r"<h2>.*?</h2>", html)
    # parts[0] is content before the first <h2> (usually empty)
    body_parts = parts[1:] if len(parts) > 1 else []
    result: list[str] = []
    for i in range(len(sections)):
        if i < len(body_parts):
            result.append(body_parts[i].strip())
        else:
            result.append("")
    return result
