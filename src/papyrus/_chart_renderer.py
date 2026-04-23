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
    config_json = json.dumps(config, ensure_ascii=False)
    return (
        f'<div class="papyrus-chart-wrap">'
        f'<canvas id="{cid}" data-chart="true"></canvas></div>\n'
        f"<script>\n(function(){{\n"
        f"  var ctx=document.getElementById('{cid}');\n"
        f"  Chart.defaults.font.family={json.dumps(s['font_family'])};\n"
        f"  Chart.defaults.font.size={s['font_size']};\n"
        f"  new Chart(ctx,{config_json});\n"
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
