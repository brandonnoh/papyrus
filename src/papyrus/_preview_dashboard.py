"""Dashboard HTML generator for Papyrus reports."""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path


def build_html(reports_dir: Path) -> str:
    """Build a self-contained dashboard HTML page.

    Scans ``reports_dir`` for ``*.html`` files (excluding ``*.thumb.png``),
    checks for matching thumbnails, and returns a full HTML page string.
    """
    entries = _collect_entries(reports_dir)
    cards_html = _build_cards(entries) if entries else _empty_state()
    return _wrap_page(cards_html)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _collect_entries(reports_dir: Path) -> list[dict]:
    """Return report metadata sorted by modification time (newest first)."""
    if not reports_dir.exists():
        return []
    entries: list[dict] = []
    for p in reports_dir.glob("*.html"):
        thumb = p.parent / f"{p.stem}.thumb.png"
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        entries.append({
            "filename": p.name,
            "title": _extract_title(p),
            "date": mtime.strftime("%Y-%m-%d %H:%M"),
            "has_thumb": thumb.exists(),
            "thumb_name": f"{p.stem}.thumb.png",
            "size_kb": round(stat.st_size / 1024, 1),
        })
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def _extract_title(html_path: Path) -> str:
    """Extract <title> text from HTML, falling back to filename."""
    try:
        text = html_path.read_text(encoding="utf-8")
        start = text.find("<title>")
        end = text.find("</title>")
        if start != -1 and end != -1:
            return text[start + 7:end].strip() or html_path.stem
    except OSError:
        pass
    return html_path.stem


def _build_cards(entries: list[dict]) -> str:
    """Generate card HTML for each report."""
    items: list[str] = []
    for e in entries:
        fname = html.escape(e["filename"])
        title = html.escape(e["title"])
        date = html.escape(e["date"])
        size = e["size_kb"]

        if e["has_thumb"]:
            thumb_html = (
                f'<img src="/thumbnail/{html.escape(e["thumb_name"])}"'
                f' alt="{title}" class="card-thumb">'
            )
        else:
            thumb_html = _placeholder_svg()

        items.append(
            f'<div class="card" onclick="location.href=\'/{fname}\'">'
            f'  <div class="card-img">{thumb_html}'
            f'    <div class="card-overlay">열기</div>'
            f'  </div>'
            f'  <div class="card-info">'
            f'    <div class="card-title">{title}</div>'
            f'    <div class="card-meta">{date} / {size} KB</div>'
            f'  </div>'
            f'</div>'
        )
    return "\n".join(items)


def _empty_state() -> str:
    return (
        '<div class="empty-state">'
        '<p>아직 생성된 보고서가 없습니다</p>'
        '</div>'
    )


def _placeholder_svg() -> str:
    """Document-icon SVG placeholder with brand color background."""
    primary = os.environ.get("PAPYRUS_COLOR_PRIMARY", "#09356E")
    return (
        f'<div class="card-thumb placeholder"'
        f' style="background:{primary}">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="#fff"'
        ' stroke-width="1.5" width="48" height="48">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2'
        ' 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/>'
        '<line x1="10" y1="9" x2="8" y2="9"/>'
        '</svg></div>'
    )


def _wrap_page(body: str) -> str:
    """Wrap card HTML in a full self-contained page."""
    primary = os.environ.get("PAPYRUS_COLOR_PRIMARY", "#09356E")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Papyrus 보고서</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',system-ui,sans-serif;
  background:#f5f6f8;color:#1a1a1a}}
.header{{background:{primary};color:#fff;
  padding:16px 24px;display:flex;
  align-items:center;justify-content:space-between}}
.header h1{{font-size:18px;font-weight:600}}
.view-toggle{{display:flex;gap:4px}}
.view-toggle button{{background:rgba(255,255,255,0.15);
  border:none;color:#fff;padding:6px 12px;
  border-radius:6px;cursor:pointer;font-size:13px}}
.view-toggle button.active{{background:rgba(255,255,255,0.35)}}
.container{{max-width:1200px;margin:24px auto;padding:0 24px}}
.grid{{display:grid;
  grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
  gap:20px}}
.card{{background:#fff;border-radius:10px;
  overflow:hidden;cursor:pointer;
  box-shadow:0 1px 4px rgba(0,0,0,0.08);
  transition:box-shadow .2s,transform .15s}}
.card:hover{{box-shadow:0 4px 16px rgba(0,0,0,0.13);
  transform:translateY(-2px)}}
.card-img{{position:relative;
  width:100%;aspect-ratio:210/297;
  overflow:hidden;background:#e8ecf0}}
.card-thumb{{width:100%;height:100%;object-fit:cover}}
.card-thumb.placeholder{{display:flex;align-items:center;
  justify-content:center;width:100%;height:100%}}
.card-overlay{{position:absolute;inset:0;
  background:rgba(9,53,110,0.6);color:#fff;
  display:flex;align-items:center;justify-content:center;
  font-size:15px;font-weight:600;opacity:0;
  transition:opacity .2s}}
.card:hover .card-overlay{{opacity:1}}
.card-info{{padding:10px 12px}}
.card-title{{font-size:13px;font-weight:600;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.card-meta{{font-size:11px;color:#888;margin-top:4px}}
.list .grid{{display:flex;flex-direction:column;gap:8px}}
.list .card{{display:flex;flex-direction:row;
  border-radius:8px}}
.list .card-img{{width:60px;min-width:60px;
  aspect-ratio:210/297}}
.list .card-info{{display:flex;flex-direction:column;
  justify-content:center;padding:8px 14px}}
.empty-state{{text-align:center;padding:80px 24px;
  color:#888;font-size:15px}}
</style>
</head>
<body>
<div class="header">
  <h1>Papyrus 보고서</h1>
  <div class="view-toggle">
    <button class="active" onclick="setView('grid',this)">그리드</button>
    <button onclick="setView('list',this)">리스트</button>
  </div>
</div>
<div class="container" id="main">
  <div class="grid">{body}</div>
</div>
<script>
function setView(mode,btn){{
  var c=document.getElementById('main');
  c.className=mode==='list'?'container list':'container';
  document.querySelectorAll('.view-toggle button').forEach(
    function(b){{b.className=b===btn?'active':''}}
  );
}}
</script>
</body>
</html>"""
