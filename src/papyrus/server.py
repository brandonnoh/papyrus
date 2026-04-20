"""MCP server — tools and prompts for papyrus."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .catalog import (
    discover_templates,
    get_section_pool,
    get_template,
    get_template_guide,
)
from .parser import fix_markdown, parse_markdown
from .renderer import render_report, save_report

mcp = FastMCP("papyrus")

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _resolve_output_dir(output_dir: str) -> Path:
    """출력 디렉토리 결정: 인자/papyrus → PAPYRUS_OUTPUT_DIR → ~/papyrus-reports."""
    import os
    if output_dir:
        return Path(output_dir).expanduser().resolve() / "papyrus"
    env = os.environ.get("PAPYRUS_OUTPUT_DIR", "")
    if env:
        return Path(env).expanduser().resolve() / "papyrus"
    return Path.home() / "papyrus-reports"


@mcp.tool()
def list_templates() -> list[dict]:
    """보고서 작성 시작점. 사용자가 보고서/문서 작성을 요청하면 반드시 이 도구를 가장 먼저 호출하세요.

    ## 호출 후 필수 진행 순서 (절대 건너뛰지 마세요)
    1. 사용자에게 문서 등급을 먼저 질문합니다:
       - 대외비 (외부 공개 불가, 기밀)
       - 내부용 (사내 열람용)
       - 외부용 (고객·파트너 공유 가능)
    2. 반환된 템플릿 목록의 keywords와 사용자 의도를 비교해 적합한 템플릿을 추천합니다.
       가장 적합한 것에 → 화살표 강조. 맨 아래 '커스텀 — 자유 형식' 옵션 항상 포함.
    3. 사용자 확인을 받습니다.
    4. get_template_guide_tool(template_id) 호출합니다.
    5. 마크다운을 작성합니다.
    6. generate_report_tool을 호출합니다.

    이 순서를 지키지 않으면 등급 없는 보고서가 생성되거나 엉뚱한 템플릿이 사용됩니다."""
    templates = discover_templates(TEMPLATES_DIR)
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "keywords": t.keywords,
        }
        for t in templates
    ]


@mcp.tool()
def get_template_guide_tool(template_id: str) -> dict:
    """선택된 템플릿의 작성 가이드를 반환합니다. list_templates → 사용자 등급 확인 → 템플릿 확정 이후에만 호출하세요.
    섹션 구조, 필수 변수, 마크다운 작성 예시를 포함합니다."""
    meta = get_template(TEMPLATES_DIR, template_id)
    return get_template_guide(meta)


@mcp.tool()
def get_section_pool_tool() -> list[dict]:
    """커스텀 문서 구성 시 사용할 섹션 풀 반환.
    모든 템플릿에서 섹션을 수집하여 조합 후보로 제공합니다."""
    return get_section_pool(TEMPLATES_DIR)


_VALID_CLASSIFICATIONS = {"대외비", "내부용", "외부용"}


def _require_classification(classification: str) -> None:
    """classification 필드가 유효한 값인지 확인. 없으면 ValueError."""
    if classification.strip() not in _VALID_CLASSIFICATIONS:
        raise ValueError(
            f"문서 등급(classification)을 frontmatter에 명시해야 합니다.\n"
            f"허용값: {' / '.join(sorted(_VALID_CLASSIFICATIONS))}\n"
            f"예: classification: 내부용"
        )


def _apply_frontmatter_defaults(text: str) -> str:
    """YAML frontmatter의 누락된 date/authors에 기본값 주입."""
    import re, os, yaml
    from datetime import date as _date
    yaml_match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not yaml_match:
        return text
    try:
        meta = yaml.safe_load(yaml_match.group(1)) or {}
    except yaml.YAMLError:
        return text
    changed = False
    if not meta.get("date"):
        meta["date"] = str(_date.today())
        changed = True
    if not meta.get("authors"):
        default_author = os.environ.get("PAPYRUS_DEFAULT_AUTHOR", "")
        if default_author:
            meta["authors"] = default_author
            changed = True
    if not changed:
        return text
    new_yaml = yaml.dump(meta, allow_unicode=True, default_flow_style=False)
    return f"---\n{new_yaml}---\n{text[yaml_match.end():]}"


@mcp.tool()
def generate_report_tool(
    markdown_content: str,
    template_id: str = "executive-summary",
    output_filename: str = "report.html",
    output_dir: str = "",
) -> str:
    """마크다운 콘텐츠를 브랜드 A4 HTML 보고서로 변환합니다.

    ## 호출 전 필수 체크 (모두 완료된 경우에만 호출하세요)
    - [ ] list_templates를 호출했는가
    - [ ] 사용자에게 문서 등급(대외비/내부용/외부용)을 확인했는가
    - [ ] 템플릿을 사용자와 함께 확정했는가
    - [ ] get_template_guide_tool로 가이드를 확인했는가
    - [ ] markdown_content frontmatter에 classification 필드가 있는가
    - [ ] output_dir에 현재 프로젝트의 절대경로를 전달했는가

    Args:
        markdown_content: 보고서 마크다운 텍스트
        template_id: 템플릿 ID (기본: executive-summary)
        output_filename: 출력 파일명 (기본: report.html)
        output_dir: 저장 디렉토리 절대경로. 미지정 시 PAPYRUS_OUTPUT_DIR 환경변수 →
                    ~/papyrus-reports 순으로 fallback.
                    Claude Code 사용 시 현재 프로젝트 루트를 전달하세요.

    Returns:
        file:// URI (Ctrl+클릭으로 브라우저에서 바로 열 수 있는 형태)
    """
    markdown_content, fix_log = fix_markdown(markdown_content)
    markdown_content = _apply_frontmatter_defaults(markdown_content)
    report_data = parse_markdown(markdown_content)
    _require_classification(report_data.classification)
    if report_data.template_id:
        template_id = report_data.template_id
    html = render_report(report_data, template_id)
    out_dir = _resolve_output_dir(output_dir)
    saved = save_report(html, out_dir / output_filename)
    md_path = saved.with_suffix(".md")
    md_path.write_text(markdown_content, encoding="utf-8")
    uri = f"file://{saved.resolve()}"
    notices = []
    if saved.name != output_filename:
        notices.append(f"[파일명 변경] '{output_filename}' 이미 존재 → '{saved.name}'으로 저장")
    if fix_log:
        notices.append("[자동 수정됨]\n" + "\n".join(f"  • {f}" for f in fix_log))
    if notices:
        return uri + "\n\n" + "\n".join(notices)
    return uri


@mcp.tool()
def get_report_source(filename: str, output_dir: str = "") -> str:
    """저장된 보고서의 원본 마크다운을 반환합니다.

    Args:
        filename: .md 또는 .html 파일명 (예: 'report.md' 또는 'report.html')
        output_dir: 보고서를 저장했던 디렉토리. generate_report_tool과 동일한 값 전달.

    Returns:
        원본 마크다운 텍스트
    """
    out_dir = _resolve_output_dir(output_dir)
    path = out_dir / filename
    if path.suffix == ".html":
        path = path.with_suffix(".md")
    if not path.exists():
        raise FileNotFoundError(
            f"'{path.name}' 없음 ({out_dir}). generate_report_tool로 먼저 생성하세요."
        )
    return path.read_text(encoding="utf-8")


@mcp.tool()
def get_config_status() -> dict:
    """현재 Papyrus 환경변수 설정 상태를 반환합니다. setup 프롬프트에서 사용합니다."""
    import os
    def _status(key: str) -> str:
        return os.environ.get(key, "")

    return {
        "PAPYRUS_LOGO": _status("PAPYRUS_LOGO"),
        "PAPYRUS_COLOR_PRIMARY": _status("PAPYRUS_COLOR_PRIMARY"),
        "PAPYRUS_COLOR_PRIMARY_HOVER": _status("PAPYRUS_COLOR_PRIMARY_HOVER"),
        "PAPYRUS_DEFAULT_AUTHOR": _status("PAPYRUS_DEFAULT_AUTHOR"),
        "PAPYRUS_OUTPUT_DIR": _status("PAPYRUS_OUTPUT_DIR"),
    }


@mcp.tool()
def list_reports(output_dir: str = "") -> list[dict]:
    """저장된 보고서 목록을 반환합니다.

    Args:
        output_dir: 조회할 디렉토리. 미지정 시 generate_report_tool과 동일한 fallback 적용.
    """
    out_dir = _resolve_output_dir(output_dir)
    if not out_dir.exists():
        return []
    reports = []
    for html_path in sorted(out_dir.glob("*.html")):
        md_path = html_path.with_suffix(".md")
        reports.append({
            "filename": html_path.name,
            "has_source": md_path.exists(),
            "size_kb": round(html_path.stat().st_size / 1024, 1),
        })
    return reports


def _setup_instructions() -> list[str]:
    """setup 안내 텍스트 블록 (start_report 프롬프트 내에서 참조)."""
    return [
        "## 브랜딩 설정 (사용자가 설정을 요청한 경우)",
        "get_config_status()를 호출해 현재 상태를 확인한 후 아래 항목을 순서대로 질문합니다.",
        "",
        "① **로고 경로** (PAPYRUS_LOGO): 절대경로 PNG. 없으면 생략.",
        "② **브랜드 색상** (PAPYRUS_COLOR_PRIMARY): hex 코드. 기본값 #09356E.",
        "③ **Hover 색상** (PAPYRUS_COLOR_PRIMARY_HOVER): hex 코드. 기본값 #062845.",
        "④ **기본 작성자** (PAPYRUS_DEFAULT_AUTHOR): 없으면 생략.",
        "⑤ **저장 경로** (PAPYRUS_OUTPUT_DIR): 기본값 ~/papyrus-reports.",
        "",
        "답변 완료 후 아래 형식으로 MCP 설정 JSON을 생성합니다 (빈 값 제외):",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "papyrus": {',
        '      "command": "uvx",',
        '      "args": ["--from", "git+https://github.com/brandonnoh/papyrus.git", "papyrus"],',
        '      "env": { "PAPYRUS_LOGO": "...", "..." : "..." }',
        "    }",
        "  }",
        "}",
        "```",
        "적용 위치: 이 프로젝트만 → .claude/settings.json / 전체 → ~/.claude/settings.json",
        "설정 후 Claude 재시작 필요.",
    ]


@mcp.prompt()
def start_report() -> str:
    """보고서 작성 또는 브랜딩 설정 시작점."""
    templates = discover_templates(TEMPLATES_DIR)
    lines = [
        "사용자가 Papyrus를 호출했습니다.",
        "",
        "**사용자 의도를 먼저 파악하세요:**",
        "- '설정' / '세팅' / 'setup' 언급 → 아래 '브랜딩 설정' 섹션을 따르세요.",
        "- 그 외 → 아래 '보고서 작성' 섹션을 따르세요.",
        "",
        "---",
        "",
        "## 보고서 작성 진행 순서",
        "1. **문서 등급 확인** — 아래 옵션 중 하나를 선택하도록 먼저 물어봅니다:",
        "   - 대외비 (외부 공개 불가, 기밀)",
        "   - 내부용 (사내 열람용)",
        "   - 외부용 (고객·파트너 공유 가능)",
        "   선택된 등급은 YAML frontmatter `classification:` 필드와 페이지 머릿말에 사용됩니다.",
        "2. 사용자의 요청 의도와 아래 템플릿의 keywords를 비교하여 유사도순 정렬",
        "3. 가장 적합한 템플릿에 -> 화살표로 강조",
        "4. 맨 아래에 '커스텀 -- 자유 형식' 옵션 항상 포함",
        "5. 사용자 확인 후 get_template_guide -> 마크다운 작성 -> generate_report",
        "",
        "## 보유 템플릿",
    ]
    for t in templates:
        kw = ", ".join(t.keywords) if t.keywords else ""
        lines.append(f"- **{t.name}** (`{t.id}`) -- {t.description}")
        if kw:
            lines.append(f"  키워드: {kw}")
    lines.append("- **커스텀** -- 자유 형식으로 직접 구성")
    lines.extend([
        "",
        "## 커스텀 문서 진행 시",
        "",
        "사용자가 커스텀을 선택하거나 보유 템플릿이 맞지 않을 때:",
        "1. 사용자 의도 파악",
        "2. get_section_pool()로 기존 섹션 풀 조회",
        "3. 섹션 조합 규칙:",
        "   - 첫 섹션: 항상 표지",
        "   - 마지막: 결론/기대효과 류",
        "   - 중간: 풀에서 매칭도 높은 것 우선",
        "   - 총 섹션 수: 3~7개",
        "   - 스타일: h2, h3, p, table, ul, ol, "
        ".key-message, figure 등 base.css만 사용",
        "4. 구조 제안 -> 사용자 컨펌 -> 마크다운 작성 "
        "-> generate_report(template_id=\"custom\")",
        "",
        "## 마크다운 작성 규칙",
        "### 제목 계층 구조",
        "- ## : 메인 섹션 제목 (필수, 각 섹션이 한 페이지)",
        "- ### : 서브섹션 제목 (선택, 한 섹션 안에서 2~4개 소주제로 나눌 때)",
        "  서브섹션 사용 예: 비교 분석, 케이스별 설명, 단계별 구분",
        "- #### 이상: 사용 금지 (렌더링에서 무시됨)",
        "",
        "- 리스트 항목(- )은 CSS가 자동으로 '—' 를 붙입니다.",
        "  항목명과 설명을 구분할 때는 '—' 대신 ': ' 를 사용하세요.",
        "  올바른 예: `- parser.py: YAML frontmatter + Markdown 파싱`",
        "  잘못된 예: `- parser.py — YAML frontmatter + Markdown 파싱`",
        "",
        "- 인용 블록( > )은 **작성자의 인사이트·판단·시사점**을 담는 영역입니다.",
        "  단순 사실 요약이나 본문 반복은 금지합니다.",
        "  섹션에서 가장 중요한 한 가지 결론 또는 작성자의 관점을 1~2문장으로 작성하세요.",
        "  올바른 예: `> 보통참여 수준의 리소스로 적극참여의 성과를 낼 수 있는 구조입니다.`",
        "  잘못된 예: `> 총 56개 테스트가 모두 통과되었습니다.` (사실 나열 — 인사이트 아님)",
        "",
        "## generate_report_tool 호출 시 필수 사항",
        "- **output_dir는 현재 작업 디렉토리(cwd) 절대경로를 전달하세요.**",
        "  Claude Code 환경에서는 세션의 primary working directory가 프로젝트 루트입니다.",
        "  모를 경우 사용자에게 'pwd 결과를 알려주세요'라고 요청하세요.",
        "- get_report_source, list_reports 호출 시에도 동일한 output_dir 전달.",
        "",
        "## 절대 하지 않을 것",
        "- 절대 스타일(tokens.css + base.css) 오버라이드",
        "- 사용자에게 CSS/스타일 커스터마이징 옵션 제공",
        "- output_dir 없이 generate_report_tool 호출",
    ])
    lines += ["", "---", ""] + _setup_instructions()
    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")
