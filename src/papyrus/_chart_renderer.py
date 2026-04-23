"""Chart rendering helpers — Chart.js canvas/script generation."""

from __future__ import annotations

import json
import re
import uuid

from papyrus.parser import TableData


_CHART_STYLE_COMMON = {
    "font_family": "'Noto Sans KR', sans-serif",
    "font_size": 11,
    "grid_color": "#eeeeee",
    "grid_line_width": 1,
    "axis_border_color": "#ddd",
    "tick_color": "#666",
    "legend_box_width": 12,
    "legend_padding": 12,
}


def _chart_id() -> str:
    return f"chart-{uuid.uuid4().hex[:8]}"


def _num(val: str) -> float | int:
    cleaned = val.replace(",", "").replace("%", "").strip()
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except (ValueError, OverflowError):
        return 0


def _scale_style() -> dict:
    s = _CHART_STYLE_COMMON
    return {
        "grid": {"color": s["grid_color"], "lineWidth": s["grid_line_width"]},
        "border": {"color": s["axis_border_color"]},
        "ticks": {"color": s["tick_color"]},
    }


def _legend_plugin() -> dict:
    s = _CHART_STYLE_COMMON
    return {
        "legend": {
            "labels": {
                "boxWidth": s["legend_box_width"],
                "padding": s["legend_padding"],
            },
        },
    }


def _axis_options() -> dict:
    return {
        "scales": {"x": _scale_style(), "y": _scale_style()},
        "plugins": _legend_plugin(),
    }


def _build_bar_config(table: TableData, palette: list[str]) -> dict:
    labels = [row[0] for row in table.rows]
    datasets = [
        {
            "label": table.headers[ci],
            "data": [_num(row[ci]) for row in table.rows],
            "backgroundColor": palette[(ci - 1) % len(palette)],
            "borderRadius": 4,
        }
        for ci in range(1, len(table.headers))
    ]
    return {"type": "bar", "data": {"labels": labels, "datasets": datasets}, "options": _axis_options()}


def _build_line_config(table: TableData, palette: list[str]) -> dict:
    labels = [row[0] for row in table.rows]
    datasets = [
        {
            "label": table.headers[ci],
            "data": [_num(row[ci]) for row in table.rows],
            "borderColor": palette[(ci - 1) % len(palette)],
            "backgroundColor": palette[(ci - 1) % len(palette)],
            "fill": False,
            "tension": 0.3,
            "pointRadius": 4,
        }
        for ci in range(1, len(table.headers))
    ]
    return {"type": "line", "data": {"labels": labels, "datasets": datasets}, "options": _axis_options()}


def _build_pie_config(table: TableData, palette: list[str]) -> dict:
    labels = [row[0] for row in table.rows]
    data_cols = len(table.headers) - 1
    chart_type = "pie" if data_cols <= 1 else "doughnut"
    data_values = [_num(row[1]) for row in table.rows]
    colors = [palette[i % len(palette)] for i in range(len(labels))]
    return {
        "type": chart_type,
        "data": {"labels": labels, "datasets": [{"data": data_values, "backgroundColor": colors}]},
        "options": {"plugins": _legend_plugin()},
    }


def _build_gantt_config(table: TableData, palette: list[str]) -> dict:
    labels = [row[0] for row in table.rows]
    starts = [_num(row[1]) for row in table.rows]
    durations = [_num(row[2]) for row in table.rows]
    start_label = table.headers[1] if len(table.headers) > 1 else "Start"
    dur_label = table.headers[2] if len(table.headers) > 2 else "Duration"
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": start_label, "data": starts, "backgroundColor": "transparent"},
                {
                    "label": dur_label,
                    "data": durations,
                    "backgroundColor": [palette[i % len(palette)] for i in range(len(labels))],
                    "borderRadius": 4,
                },
            ],
        },
        "options": {
            "indexAxis": "y",
            "scales": {"x": {"stacked": True, **_scale_style()}, "y": {"stacked": True, **_scale_style()}},
            "plugins": _legend_plugin(),
        },
    }


_CONFIG_BUILDERS = {
    "bar": _build_bar_config,
    "line": _build_line_config,
    "pie": _build_pie_config,
    "gantt": _build_gantt_config,
}


def render_chart_html(table: TableData, palette: list[str]) -> str:
    """Return <canvas> + <script> HTML for a single chart table."""
    builder = _CONFIG_BUILDERS.get(table.chart_type or "")
    if builder is None:
        return ""
    cid = _chart_id()
    config = builder(table, palette)
    s = _CHART_STYLE_COMMON
    # Inject animation.onComplete to pre-render print image (timing-safe)
    options = config.setdefault("options", {})
    options["animation"] = {
        "onComplete": f"__PAPYRUS_ONCOMPLETE_{cid}__",
    }
    config_json = json.dumps(config, ensure_ascii=False).replace(
        f'"__PAPYRUS_ONCOMPLETE_{cid}__"',
        f'function(){{var pi=document.getElementById("{cid}-print");if(pi)pi.src=ctx.toDataURL("image/png");}}',
    )
    data_json = json.dumps(
        {"headers": table.headers, "rows": table.rows}, ensure_ascii=False
    )
    icon = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14"'
        ' viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<line x1="3" y1="9" x2="21" y2="9"/>'
        '<line x1="3" y1="15" x2="21" y2="15"/>'
        '<line x1="9" y1="3" x2="9" y2="21"/>'
        '</svg>'
    )
    return (
        f'<div class="papyrus-chart-wrap">'
        f'<canvas id="{cid}" data-chart="true"></canvas>'
        f'<img id="{cid}-print" class="chart-print-img" alt="차트">'
        f'<button class="chart-edit-btn no-print"'
        f' onclick="__papyrusOpenPanel(\'{cid}\')" title="데이터 편집">{icon}</button>'
        f'</div>\n'
        f"<script>\n(function(){{\n"
        f"  var ctx=document.getElementById('{cid}');\n"
        f"  Chart.defaults.font.family={json.dumps(s['font_family'])};\n"
        f"  Chart.defaults.font.size={s['font_size']};\n"
        f"  var ch=new Chart(ctx,{config_json});\n"
        f"  (window.__papyrusCharts=window.__papyrusCharts||[])['{cid}']=ch;\n"
        f"  (window.__papyrusChartData=window.__papyrusChartData||[])['{cid}']={data_json};\n"
        f"}})();\n</script>"
    )


def _table_matches(html_table: str, table: TableData) -> bool:
    for header in table.headers:
        if header not in html_table:
            return False
    if table.rows and table.rows[0]:
        for cell in table.rows[0]:
            if cell not in html_table:
                return False
    return True


def _find_table_html(html: str, table: TableData) -> str | None:
    for m in re.finditer(r"<table>.*?</table>", html, re.DOTALL):
        if _table_matches(m.group(), table):
            return m.group()
    return None


def inject_charts_into_html(html: str, tables: list[TableData], palette: list[str]) -> str:
    """Replace <table> blocks that have chart_type with canvas."""
    for table in tables:
        if table.chart_type is None:
            continue
        table_html = _find_table_html(html, table)
        if table_html:
            html = html.replace(table_html, render_chart_html(table, palette), 1)
    return html
