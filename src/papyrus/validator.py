"""Style validator — pure functions, no IO."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from papyrus.catalog import TemplateMeta


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    severity: str  # "error" | "warning"
    message: str
    location: str


class StyleViolationError(Exception):
    """Raised when error-level style violations are found."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        msgs = [f"[{v.rule}] {v.message} ({v.location})" for v in violations]
        super().__init__("\n".join(msgs))


# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

_ALLOWED_FONTS: set[str] = {
    "noto serif kr",
    "batang",
    "noto sans kr",
    "sans-serif",
    "serif",
    "monospace",
}


# ---------------------------------------------------------------------------
# Individual checkers
# ---------------------------------------------------------------------------

def check_hardcoded_colors(html: str) -> list[Violation]:
    """Detect hardcoded hex colors in <style> blocks."""
    violations: list[Violation] = []
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, re.DOTALL):
        block = m.group(1)
        block_start = m.start(1)
        for cm in re.finditer(r"#[0-9a-fA-F]{3,8}\b", block):
            abs_pos = block_start + cm.start()
            lineno = html[:abs_pos].count("\n") + 1
            violations.append(Violation(
                rule="no-hardcoded-color",
                severity="error",
                message=f"Hardcoded color '{cm.group()}' in <style>",
                location=f"약 {lineno}번 줄",
            ))
    return violations


def check_allowed_fonts(html: str) -> list[Violation]:
    """Detect disallowed font-family values."""
    violations: list[Violation] = []
    pattern = r"font-family\s*:\s*([^;}\n]+)"
    for m in re.finditer(pattern, html, re.IGNORECASE):
        raw = m.group(1).strip().rstrip(";")
        fonts = [f.strip().strip("'\"").lower() for f in raw.split(",")]
        for font in fonts:
            if font and font not in _ALLOWED_FONTS:
                violations.append(Violation(
                    rule="allowed-fonts",
                    severity="warning",
                    message=f"Disallowed font '{font}'",
                    location=f"font-family declaration",
                ))
    return violations


def check_inline_styles(html: str) -> list[Violation]:
    """Detect inline style= attributes."""
    violations: list[Violation] = []
    for m in re.finditer(r"""style\s*=\s*["']""", html):
        lineno = html[:m.start()].count("\n") + 1
        violations.append(Violation(
            rule="no-inline-style",
            severity="error",
            message="Inline style attribute found",
            location=f"약 {lineno}번 줄",
        ))
    return violations


def check_image_structure(html: str) -> list[Violation]:
    """Detect <img> tags not wrapped in figure or .img-left/.img-right."""
    violations: list[Violation] = []
    img_pat = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    figure_ctx = re.compile(
        r"<figure\b[^>]*>.*?</figure>",
        re.DOTALL | re.IGNORECASE,
    )
    div_ctx = re.compile(
        r"<div[^>]*class\s*=\s*[\"'][^\"']*"
        r"(?:img-left|img-right)[^\"']*[\"'][^>]*>"
        r".*?</div>",
        re.DOTALL | re.IGNORECASE,
    )
    safe_ranges = [
        (m.start(), m.end()) for m in figure_ctx.finditer(html)
    ] + [
        (m.start(), m.end()) for m in div_ctx.finditer(html)
    ]
    for m in img_pat.finditer(html):
        pos = m.start()
        inside = any(s <= pos < e for s, e in safe_ranges)
        if not inside:
            lineno = html[:pos].count("\n") + 1
            violations.append(Violation(
                rule="image-structure",
                severity="error",
                message="<img> not wrapped in <figure> or .img-left/.img-right",
                location=f"약 {lineno}번 줄",
            ))
    return violations


def check_table_captions(html: str) -> list[Violation]:
    """Detect <table> without <caption> or .table-caption nearby."""
    violations: list[Violation] = []
    for m in re.finditer(r"<table\b[^>]*>", html, re.IGNORECASE):
        end = html.find("</table>", m.start())
        if end == -1:
            end = len(html)
        table_block = html[m.start():end]
        before = html[max(0, m.start() - 200):m.start()]
        has_caption = "<caption" in table_block.lower()
        has_div_cap = "table-caption" in before.lower()
        if not has_caption and not has_div_cap:
            lineno = html[:m.start()].count("\n") + 1
            violations.append(Violation(
                rule="table-caption",
                severity="warning",
                message="<table> missing caption",
                location=f"약 {lineno}번 줄",
            ))
    return violations


def check_required_sections(
    html: str, meta: TemplateMeta,
) -> list[Violation]:
    """Check that required sections from meta exist in HTML."""
    violations: list[Violation] = []
    required = [
        s for s in meta.sections
        if isinstance(s, dict) and s.get("required")
    ]
    lower_html = html.lower()
    for sec in required:
        sec_id = sec.get("id", "")
        sec_name = sec.get("name", "")
        found = (
            sec_id.lower() in lower_html
            or sec_name.lower() in lower_html
        )
        if not found:
            violations.append(Violation(
                rule="required-section",
                severity="error",
                message=f"Required section '{sec_name}' ({sec_id}) missing",
                location="document",
            ))
    return violations


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def validate_style(
    html: str,
    template_meta: TemplateMeta,
    *,
    full_html: str | None = None,
) -> list[Violation]:
    """Run all 6 style checks and return combined violations.

    Args:
        html: Content HTML to check for colors, inline styles, images,
              tables, and fonts.
        template_meta: Template metadata for required-section check.
        full_html: Full rendered HTML (including design-system CSS).
                   Used for required-section check when provided.
    """
    doc = full_html if full_html is not None else html
    violations: list[Violation] = []
    violations.extend(check_hardcoded_colors(html))
    violations.extend(check_allowed_fonts(html))
    violations.extend(check_inline_styles(html))
    violations.extend(check_image_structure(html))
    violations.extend(check_table_captions(html))
    violations.extend(check_required_sections(doc, template_meta))
    return violations
