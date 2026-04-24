"""Markdown report parser — pure functions, no IO."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import markdown as md


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TableData:
    headers: list[str]
    rows: list[list[str]]
    chart_type: str | None = None


@dataclass
class Section:
    heading: str
    level: int
    content: str
    html_content: str = ""
    tables: list[TableData] = field(default_factory=list)
    key_messages: list[str] = field(default_factory=list)
    subsections: list[Section] = field(default_factory=list)


@dataclass
class ReportData:
    title: str
    authors: str
    date: str
    classification: str
    template_id: str
    sections: list[Section] = field(default_factory=list)
    footnotes_html: str = ""


# ---------------------------------------------------------------------------
# 1. parse_frontmatter
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract metadata from YAML frontmatter or H1 + blockquote."""
    yaml_match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if yaml_match:
        import yaml
        try:
            meta = yaml.safe_load(yaml_match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML frontmatter 파싱 오류: {exc}") from exc
        body = text[yaml_match.end():]
        return meta, body

    return _parse_h1_quote(text)


def _parse_h1_quote(text: str) -> tuple[dict, str]:
    """Fallback: parse H1 title and first blockquote for authors/date."""
    meta: dict = {}
    lines = text.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("# ") and "title" not in meta:
            meta["title"] = line[2:].strip()
            body_start = i + 1
            continue
        if line.startswith("> ") and "title" in meta and "authors" not in meta:
            raw = line[2:].strip()
            parts = raw.split("|")
            meta["authors"] = parts[0].strip()
            meta["date"] = parts[1].strip() if len(parts) > 1 else ""
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).lstrip("\n")
    return meta, body


# ---------------------------------------------------------------------------
# 2. split_sections
# ---------------------------------------------------------------------------

def split_sections(body: str) -> list[Section]:
    """Split body text into Section objects by ## headings."""
    chunks = re.split(r"(?m)^## ", body)
    sections: list[Section] = []
    for chunk in chunks[1:]:
        heading, _, content = chunk.partition("\n")
        content = content.strip()
        subsections = _extract_subsections(content)
        sections.append(Section(
            heading=heading.strip(),
            level=2,
            content=content,
            subsections=subsections,
        ))
    return sections


def _extract_subsections(content: str) -> list[Section]:
    """Extract ### subsections from section content."""
    chunks = re.split(r"(?m)^### ", content)
    if len(chunks) <= 1:
        return []
    subs: list[Section] = []
    for chunk in chunks[1:]:
        heading, _, sub_content = chunk.partition("\n")
        subs.append(Section(
            heading=heading.strip(),
            level=3,
            content=sub_content.strip(),
        ))
    return subs


# ---------------------------------------------------------------------------
# 3. parse_tables
# ---------------------------------------------------------------------------

_CHART_COMMENT_RE = re.compile(
    r"^\s*<!--\s*chart:(bar|line|pie|gantt)\s*-->\s*$",
    re.IGNORECASE,
)

_VALID_CHART_TYPES = frozenset({"bar", "line", "pie", "gantt"})


def parse_tables(content: str) -> list[TableData]:
    """Parse markdown pipe-tables from content."""
    tables: list[TableData] = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        if _is_table_row(lines[i]):
            table, i = _consume_table(lines, i)
            if table:
                chart_type = _peek_chart_comment(lines, i)
                if chart_type:
                    table = TableData(
                        headers=table.headers,
                        rows=table.rows,
                        chart_type=chart_type,
                    )
                    i += 1  # skip the comment line
                tables.append(table)
        else:
            i += 1
    return tables


def _peek_chart_comment(
    lines: list[str], idx: int,
) -> str | None:
    """Return chart type if lines[idx] is a chart comment."""
    if idx >= len(lines):
        return None
    m = _CHART_COMMENT_RE.match(lines[idx])
    if m:
        ctype = m.group(1).lower()
        return ctype if ctype in _VALID_CHART_TYPES else None
    return None


def _is_table_row(line: str) -> bool:
    """Check if a line looks like a markdown table row."""
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3


def _consume_table(lines: list[str], start: int) -> tuple[TableData | None, int]:
    """Consume consecutive table rows starting at `start`."""
    rows_raw: list[str] = []
    i = start
    while i < len(lines) and _is_table_row(lines[i]):
        rows_raw.append(lines[i])
        i += 1
    if len(rows_raw) < 2:
        return None, i

    headers = _split_cells(rows_raw[0])
    sep_idx = _find_separator(rows_raw)
    data_start = sep_idx + 1 if sep_idx is not None else 1
    data_rows = [_split_cells(r) for r in rows_raw[data_start:]]
    return TableData(headers=headers, rows=data_rows), i


def _find_separator(rows: list[str]) -> int | None:
    """Find the |---|---| separator row index."""
    for idx, row in enumerate(rows):
        cells = _split_cells(row)
        if all(re.fullmatch(r":?-+:?", c.strip()) for c in cells):
            return idx
    return None


def _split_cells(row: str) -> list[str]:
    """Split a pipe-delimited row into cell strings."""
    stripped = row.strip().strip("|")
    return [c.strip() for c in stripped.split("|")]


# ---------------------------------------------------------------------------
# 4. extract_key_messages
# ---------------------------------------------------------------------------

def extract_key_messages(content: str) -> list[str]:
    """Extract blockquote lines (> ...) from content."""
    messages: list[str] = []
    for line in content.split("\n"):
        if line.startswith("> "):
            messages.append(line[2:].strip())
    return messages


# ---------------------------------------------------------------------------
# 5. render_section_html
# ---------------------------------------------------------------------------

_CALLOUT_LINE_RE = re.compile(r"^> \[!(warning|danger)\] ?(.*)$", re.IGNORECASE | re.MULTILINE)


def render_section_html(section: Section) -> str:
    """Convert section markdown to HTML, replacing blockquotes."""
    preprocessed = _preprocess_callouts(section.content)
    raw_html = md.markdown(preprocessed, extensions=["tables", "fenced_code"])
    return _replace_blockquotes(raw_html)


def _preprocess_callouts(content: str) -> str:
    """Convert > [!TYPE] lines to raw HTML before markdown parsing."""
    def _sub(m: re.Match) -> str:
        ctype = m.group(1).lower()
        text = m.group(2)
        return f'<div class="key-message key-message--{ctype}">{text}</div>'

    return _CALLOUT_LINE_RE.sub(_sub, content)


def _replace_blockquotes(html: str) -> str:
    """Replace <blockquote> with <div class='key-message'>."""
    html = html.replace("<blockquote>\n<p>", '<div class="key-message">')
    html = html.replace("<blockquote><p>", '<div class="key-message">')
    html = html.replace("</p>\n</blockquote>", "</div>")
    html = html.replace("</p></blockquote>", "</div>")
    html = html.replace("<blockquote>", '<div class="key-message">')
    return html.replace("</blockquote>", "</div>")


# ---------------------------------------------------------------------------
# 6. lint_markdown
# ---------------------------------------------------------------------------

class MarkdownLintError(ValueError):
    """Raised when markdown violates content rules."""


_FACT_PATTERN = re.compile(
    r"\d+/\d+\s*(테스트|통과|passed|failed)"
    r"|총\s*\d+\s*(개|건|명|회|번|항목|케이스|tests?|cases?)"
    r"|\d+개\s*(모두|전원|전체)"
    r"|커버리지\s*\d+"
    r"|\d+/\d+\s*tests?\s*(passed|failed)"
    r"|total\s*\d+"
    r"|coverage\s*\d+"
    r"|\d+\s*(tests?|cases?)\s*(passed|failed|total)"
)


def lint_markdown(text: str) -> list[str]:
    """Check markdown for content rule violations. Returns error messages."""
    errors: list[str] = []
    _lint_list_dash_separator(text, errors)
    _lint_blockquote_usage(text, errors)
    return errors


def fix_markdown(text: str) -> tuple[str, list[str]]:
    """Auto-fix markdown rule violations. Returns (fixed_text, fix_log)."""
    lines = text.split("\n")
    log: list[str] = []
    fixed = [_fix_line(i + 1, line, log) for i, line in enumerate(lines)]
    return "\n".join(fixed), log


def _fix_line(lineno: int, line: str, log: list[str]) -> str:
    stripped = line.strip()
    if re.match(r"^[-*]\s", stripped) and " — " in line:
        new_line = line.replace(" — ", ": ", 1)
        log.append(f"[줄 {lineno}] 리스트 구분자 ' — ' → ': ' 자동 수정")
        return new_line
    if stripped.startswith("> ") and _FACT_PATTERN.search(stripped[2:]):
        new_line = line.replace("> ", "", 1)
        log.append(
            f"[줄 {lineno}] blockquote 사실 나열 감지 → 일반 단락으로 변환 "
            f"(인사이트로 교체 권장)"
        )
        return new_line
    return line


def _lint_list_dash_separator(text: str, errors: list[str]) -> None:
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if re.match(r"^[-*]\s", stripped) and " — " in stripped:
            errors.append(
                f"[줄 {i}] 리스트 항목에 ' — ' 구분자 사용 금지 → ': ' 로 바꾸세요.\n"
                f"  문제: {stripped[:80]}"
            )


def _lint_blockquote_usage(text: str, errors: list[str]) -> None:
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("> ") and _FACT_PATTERN.search(line.strip()[2:]):
            errors.append(
                f"[줄 {i}] 인용 블록은 작성자 인사이트 전용입니다. "
                f"수치·사실 나열 금지.\n"
                f"  문제: {line.strip()[2:][:80]}"
            )


# ---------------------------------------------------------------------------
# 7. parse_markdown (orchestrator)
# ---------------------------------------------------------------------------

def parse_markdown(text: str) -> ReportData:
    """Parse full markdown text into a ReportData structure."""
    from papyrus._footnote_utils import render_sections_with_footnotes

    meta, body = parse_frontmatter(text)
    sections = split_sections(body)

    # Full-body rendering for global footnote numbering
    section_htmls, footnotes_html = render_sections_with_footnotes(sections)
    for section, html in zip(sections, section_htmls):
        section.html_content = html
        section.tables = parse_tables(section.content)
        section.key_messages = extract_key_messages(section.content)
        for sub in section.subsections:
            sub.tables = parse_tables(sub.content)
            sub.key_messages = extract_key_messages(sub.content)
            sub.html_content = render_section_html(sub)

    return ReportData(
        title=meta.get("title", ""),
        authors=meta.get("authors", ""),
        date=meta.get("date", ""),
        classification=meta.get("classification", ""),
        template_id=meta.get("template_id", ""),
        sections=sections,
        footnotes_html=footnotes_html,
    )
