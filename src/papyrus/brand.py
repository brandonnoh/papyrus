"""Brand configuration — reads env vars, returns neutral defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrandConfig:
    """Immutable branding settings loaded from environment variables."""

    logo_path: Path | None
    color_primary: str
    color_primary_hover: str
    classification: str


def load_brand() -> BrandConfig:
    """Load branding from PAPYRUS_* env vars. Neutral defaults if unset."""
    raw_logo = os.environ.get("PAPYRUS_LOGO", "")
    logo = Path(raw_logo) if raw_logo else None
    return BrandConfig(
        logo_path=logo,
        color_primary=os.environ.get("PAPYRUS_COLOR_PRIMARY", "#09356E"),
        color_primary_hover=os.environ.get("PAPYRUS_COLOR_PRIMARY_HOVER", "#062845"),
        classification=os.environ.get("PAPYRUS_CLASSIFICATION", "Internal"),
    )
