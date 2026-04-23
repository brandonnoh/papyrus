"""Brand configuration — reads env vars, returns neutral defaults."""

from __future__ import annotations

import colorsys
import os
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Chart palette generation
# ---------------------------------------------------------------------------

_HUE_OFFSETS = (0, 35, 65, 150, 210, 270, 180)
_SAT_MIN, _SAT_MAX = 0.50, 0.80
_LIT_MIN, _LIT_MAX = 0.30, 0.55


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' to (h, s, l) in 0..1 range."""
    h_str = hex_color.lstrip("#")
    r, g, b = (int(h_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert (h, s, l) in 0..1 range to '#RRGGBB'."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(
        int(round(r * 255)),
        int(round(g * 255)),
        int(round(b * 255)),
    )


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def generate_chart_palette(primary_hex: str) -> list[str]:
    """Generate a 7-color chart palette from *primary_hex*.

    The first colour is always the original primary. Remaining colours
    rotate hue by predefined offsets while clamping saturation and
    lightness into print-friendly ranges.
    """
    base_h, base_s, base_l = _hex_to_hsl(primary_hex)
    palette: list[str] = [primary_hex.upper()]
    for offset in _HUE_OFFSETS[1:]:
        h = (base_h + offset / 360.0) % 1.0
        s = _clamp(base_s, _SAT_MIN, _SAT_MAX)
        l = _clamp(base_l, _LIT_MIN, _LIT_MAX)
        palette.append(_hsl_to_hex(h, s, l))
    return palette


# ---------------------------------------------------------------------------
# BrandConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BrandConfig:
    """Immutable branding settings loaded from environment variables."""

    logo_path: Path | None
    color_primary: str
    color_primary_hover: str
    classification: str
    chart_palette: tuple[str, ...]


def load_brand() -> BrandConfig:
    """Load branding from PAPYRUS_* env vars. Neutral defaults if unset."""
    raw_logo = os.environ.get("PAPYRUS_LOGO", "")
    logo = Path(raw_logo) if raw_logo else None
    color_primary = os.environ.get("PAPYRUS_COLOR_PRIMARY", "#09356E")
    return BrandConfig(
        logo_path=logo,
        color_primary=color_primary,
        color_primary_hover=os.environ.get(
            "PAPYRUS_COLOR_PRIMARY_HOVER", "#062845",
        ),
        classification=os.environ.get("PAPYRUS_CLASSIFICATION", "Internal"),
        chart_palette=tuple(generate_chart_palette(color_primary)),
    )
