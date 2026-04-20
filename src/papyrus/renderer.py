"""HTML report renderer — pure functions, Jinja2-based."""

from __future__ import annotations

import base64
from pathlib import Path

import jinja2

from papyrus.brand import BrandConfig, load_brand
from papyrus.catalog import TemplateMeta, get_template
from papyrus.parser import ReportData
from papyrus.validator import StyleViolationError, validate_style


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEMPLATES_DIR_NAME = "templates"
_STATIC_DIR_NAME = "static"
_PKG_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

def create_jinja_env(templates_dir: Path) -> jinja2.Environment:
    """Create a Jinja2 Environment rooted at templates_dir."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=False,
    )


# ---------------------------------------------------------------------------
# CSS helpers
# ---------------------------------------------------------------------------

def load_static_css(static_dir: Path) -> dict[str, str]:
    """Read tokens.css and base.css from static_dir."""
    return {
        "css_tokens": _read_text(static_dir / "tokens.css"),
        "css_base": _read_text(static_dir / "base.css"),
    }


def inline_logo(
    static_dir: Path, brand_logo: Path | None = None,
) -> str:
    """Encode logo as a data URI. brand_logo takes priority over static."""
    logo_path = _resolve_logo(static_dir, brand_logo)
    if logo_path is None or not logo_path.exists():
        return ""
    raw = logo_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _resolve_logo(
    static_dir: Path, brand_logo: Path | None,
) -> Path | None:
    """Pick brand logo only if explicitly set via PAPYRUS_LOGO."""
    if brand_logo is not None and brand_logo.exists():
        return brand_logo
    return None


def prepare_css(
    static_dir: Path, template_meta: TemplateMeta,
) -> dict[str, str]:
    """Assemble all CSS: tokens (brand-patched), base, template."""
    brand = load_brand()
    css = load_static_css(static_dir)
    css["css_tokens"] = _patch_brand_colors(css["css_tokens"], brand)
    logo_uri = inline_logo(static_dir, brand.logo_path)
    css["css_base"] = _patch_watermark(css["css_base"], logo_uri)
    css["css_template"] = _read_text(template_meta.path / "style.css")
    return css


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_pages(report_data: ReportData) -> list[dict]:
    """Cover page entry only; body sections rendered via sections variable."""
    return [{"is_cover": True}]


# ---------------------------------------------------------------------------
# Render orchestrator
# ---------------------------------------------------------------------------

def render_report(
    report_data: ReportData,
    template_id: str,
    *,
    templates_dir: Path | None = None,
    static_dir: Path | None = None,
) -> str:
    """Render a ReportData into a full HTML string."""
    templates_dir = templates_dir or _PKG_DIR / _TEMPLATES_DIR_NAME
    static_dir = static_dir or _PKG_DIR / _STATIC_DIR_NAME

    is_custom = template_id == "custom"
    if is_custom:
        meta = _custom_meta()
        css = _prepare_css_custom(static_dir)
    else:
        meta = get_template(templates_dir, template_id)
        css = prepare_css(static_dir, meta)

    pages = build_pages(report_data)
    env = create_jinja_env(templates_dir)
    tmpl_path = (
        "_base/custom.html" if is_custom
        else f"{template_id}/template.html"
    )
    tmpl = env.get_template(tmpl_path)
    html = _render_template(tmpl, report_data, pages, css)
    _check_violations(html, report_data.sections, meta)
    return html


def _custom_meta() -> TemplateMeta:
    """Return a minimal TemplateMeta for custom documents."""
    return TemplateMeta(
        id="custom",
        name="커스텀",
        description="자유 형식 문서",
        author="",
        version="1.0",
        sections=[],
        variables=[],
    )


def _prepare_css_custom(static_dir: Path) -> dict[str, str]:
    """Assemble CSS for custom documents (no template CSS)."""
    brand = load_brand()
    css = load_static_css(static_dir)
    css["css_tokens"] = _patch_brand_colors(css["css_tokens"], brand)
    logo_uri = inline_logo(static_dir, brand.logo_path)
    css["css_base"] = _patch_watermark(css["css_base"], logo_uri)
    css["css_template"] = ""
    return css


def _render_template(
    tmpl: jinja2.Template,
    report_data: ReportData,
    pages: list[dict],
    css: dict[str, str],
) -> str:
    """Render a Jinja2 template with standard context."""
    return tmpl.render(
        title=report_data.title,
        authors=report_data.authors,
        date=report_data.date,
        classification=report_data.classification or "대외비",
        pages=pages,
        sections=report_data.sections,
        **css,
    )


def _check_violations(
    html: str, sections: list, meta: TemplateMeta,
) -> None:
    """Run style validation and raise on errors."""
    content_html = "\n".join(s.html_content for s in sections)
    violations = validate_style(content_html, meta, full_html=html)
    errors = [v for v in violations if v.severity == "error"]
    if errors:
        raise StyleViolationError(errors)


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def _resolve_output_path(output_path: Path) -> Path:
    """파일이 이미 존재하면 suffix 번호를 붙여 중복 방지."""
    if not output_path.exists():
        return output_path
    stem = output_path.stem
    suffix = output_path.suffix
    parent = output_path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def save_report(html: str, output_path: Path) -> Path:
    """Write rendered HTML to a file. Returns the resolved path."""
    output_path = output_path.resolve()
    output_path = _resolve_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    """Read a text file, returning empty string if missing."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _patch_brand_colors(css: str, brand: BrandConfig) -> str:
    """Replace default brand colors with values from BrandConfig."""
    css = css.replace(
        "--color-primary: #2c2c2c",
        f"--color-primary: {brand.color_primary}",
    )
    css = css.replace(
        "--color-primary-hover: #1a1a1a",
        f"--color-primary-hover: {brand.color_primary_hover}",
    )
    return css


def _patch_watermark(css_tokens: str, logo_uri: str) -> str:
    """Replace the watermark background URL with logo data URI."""
    if not logo_uri:
        return css_tokens
    return css_tokens.replace(
        "url('logo.png')",
        f"url('{logo_uri}')",
    )
