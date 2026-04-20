"""Template catalog — discover and load template metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class TemplateMeta:
    id: str
    name: str
    description: str
    author: str
    version: str
    keywords: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    variables: list[dict] = field(default_factory=list)
    guide_notes: str = ""
    path: Path = field(default_factory=lambda: Path("."))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_templates(templates_dir: Path) -> list[TemplateMeta]:
    """Scan templates_dir for subdirectories containing meta.yaml."""
    results: list[TemplateMeta] = []
    for meta_file in sorted(templates_dir.glob("*/meta.yaml")):
        meta = _load_meta(meta_file)
        if meta is not None:
            results.append(meta)
    return results


def get_template(templates_dir: Path, template_id: str) -> TemplateMeta:
    """Load a single template by its ID. Raises FileNotFoundError."""
    meta_file = templates_dir / template_id / "meta.yaml"
    if not meta_file.exists():
        raise FileNotFoundError(f"Template '{template_id}' not found")
    meta = _load_meta(meta_file)
    if meta is None:
        raise FileNotFoundError(f"Template '{template_id}' has invalid meta")
    return meta


def get_section_pool(templates_dir: Path) -> list[dict]:
    """Collect sections from all templates into a flat pool."""
    pool: list[dict] = []
    for meta in discover_templates(templates_dir):
        for section in meta.sections:
            pool.append({
                "id": section["id"],
                "name": section["name"],
                "from_template": meta.id,
                "from_template_name": meta.name,
                "required_in_source": section.get("required", False),
            })
    return pool


def get_template_guide(meta: TemplateMeta) -> dict:
    """Return a guide dict summarizing template usage."""
    guide: dict = {
        "id": meta.id,
        "name": meta.name,
        "description": meta.description,
        "sections": meta.sections,
        "variables": meta.variables,
    }
    if meta.guide_notes:
        guide["guide_notes"] = meta.guide_notes
    return guide


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_meta(meta_file: Path) -> TemplateMeta | None:
    """Parse a meta.yaml file into a TemplateMeta instance."""
    raw = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "id" not in raw:
        return None
    return TemplateMeta(
        id=raw["id"],
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        author=raw.get("author", ""),
        version=raw.get("version", ""),
        keywords=raw.get("keywords", []),
        sections=raw.get("sections", []),
        variables=raw.get("variables", []),
        guide_notes=raw.get("guide_notes", ""),
        path=meta_file.parent,
    )
