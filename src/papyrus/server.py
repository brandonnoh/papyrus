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
from .preview import open_dashboard_in_browser, open_preview

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
    guide = get_template_guide(meta)
    footnote_section = (
        "\n### 각주 (출처·보충 설명)\n"
        "인라인 참조: `[^id]` 형태로 본문에 삽입합니다.\n"
        "각주 정의: `[^id]: 내용` 을 해당 섹션 끝에 작성합니다.\n"
        "출처 표기와 보충 설명 모두 가능합니다.\n"
        "각주는 자동으로 문서 마지막 '참고문헌' 페이지에 모아 표시됩니다.\n\n"
        "예시:\n"
        "```\n"
        "시장 규모는 연 12% 성장 중[^src1]이며, 국내는 8%[^src2] 수준입니다.\n\n"
        "[^src1]: McKinsey Global Report, 2024\n"
        "[^src2]: 한국IDC 연간 보고서, Q3 2024\n"
        "```\n"
    )
    guide["guide_notes"] = guide.get("guide_notes", "") + footnote_section
    return guide


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
    _preview_server = open_preview(saved)
    _try_generate_thumbnail(saved, _preview_server.port)
    url = _preview_server.url
    notices = []
    if saved.name != output_filename:
        notices.append(f"[파일명 변경] '{output_filename}' 이미 존재 → '{saved.name}'으로 저장")
    if fix_log:
        notices.append("[자동 수정됨]\n" + "\n".join(f"  • {f}" for f in fix_log))
    if notices:
        return url + "\n\n" + "\n".join(notices)
    return url


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


def _try_generate_thumbnail(html_path, port: int) -> None:
    """Generate thumbnail in background thread (best-effort)."""
    import threading
    from ._thumbnail import generate_thumbnail

    def _run() -> None:
        try:
            generate_thumbnail(html_path, port)
        except Exception:
            pass  # non-critical -- skip silently

    threading.Thread(target=_run, daemon=True).start()


@mcp.tool()
def open_dashboard(output_dir: str = "") -> str:
    """저장된 보고서 목록을 대시보드로 엽니다.

    Args:
        output_dir: 보고서 디렉토리. 미지정 시 generate_report_tool과 동일한 fallback.

    Returns:
        대시보드 URL
    """
    out_dir = _resolve_output_dir(output_dir)
    srv = open_dashboard_in_browser(out_dir)
    return f"대시보드를 열었습니다: http://127.0.0.1:{srv.port}/dashboard"


@mcp.prompt()
def start_report() -> str:
    """보고서 작성 시작점."""
    templates = discover_templates(TEMPLATES_DIR)

    template_opts = []
    for t in templates:
        template_opts.append(
            f'    {{"label": "{t.name}", "description": "{t.description}"}}'
        )
    template_opts.append(
        '    {"label": "커스텀", "description": "자유 형식으로 직접 섹션 구성"}'
    )
    template_opts_str = ",\n".join(template_opts)

    return f"""사용자가 Papyrus 보고서 작성을 시작합니다.

**첫 번째 행동으로 반드시 AskUserQuestion 도구를 아래 파라미터로 호출하세요.**
설명하거나 안내 텍스트를 먼저 출력하지 마세요. 도구 호출이 첫 행동입니다.

```
AskUserQuestion(
  questions=[
    {{
      "question": "문서 등급을 선택하세요.",
      "header": "문서 등급",
      "multiSelect": false,
      "options": [
        {{"label": "대외비", "description": "외부 공개 불가 — 기밀 문서"}},
        {{"label": "내부용", "description": "사내 열람용 — 팀·조직 공유"}},
        {{"label": "외부용", "description": "고객·파트너 공유 가능"}}
      ]
    }},
    {{
      "question": "보고서 유형을 선택하세요.",
      "header": "템플릿",
      "multiSelect": false,
      "options": [
{template_opts_str}
      ]
    }},
    {{
      "question": "사용할 구성 요소를 선택하세요. (복수 선택 가능)",
      "header": "구성 요소",
      "multiSelect": true,
      "options": [
        {{"label": "칼아웃", "description": "> [!warning] / > [!danger] — 경고·위험 강조 박스"}},
        {{"label": "각주", "description": "[^id] — 출처·보충 설명, 마지막 페이지 참고문헌 자동 생성"}},
        {{"label": "표", "description": "파이프 테이블 — 데이터 비교·정리"}},
        {{"label": "이미지", "description": "![alt](path) — 시각 자료 삽입"}},
        {{"label": "차트", "description": "<!-- chart:bar|line|pie|gantt --> — 표를 Chart.js 차트로 시각화"}}
      ]
    }}
  ]
)
```

AskUserQuestion 응답을 받은 후:
1. 등급 → frontmatter `classification:` 값으로 저장
2. 템플릿 → `get_template_guide_tool(template_id)` 호출
3. 선택된 구성 요소만 마크다운에 포함 (아래 "구성 요소별 작성 지침" 참조)
4. 마크다운 작성
5. `generate_report_tool(markdown_content, template_id, output_dir=<cwd>)` 호출

커스텀 선택 시: `get_section_pool_tool()` 호출 후 섹션 조합 제안 → 사용자 확인 → 마크다운 작성

---

## 구성 요소별 작성 지침

선택한 요소만 사용하세요. 선택하지 않은 요소는 마크다운에 포함하지 마세요.

**칼아웃 선택 시:**
- 경고(주황): `> [!warning] 주의가 필요한 내용`
- 위험(빨강): `> [!danger] 즉각 조치가 필요한 내용`
- 한 줄만 지원 — 여러 줄이면 칼아웃을 각각 따로 작성

**각주 선택 시:**
- 인라인 참조: `시장 점유율 35%[^src1]`
- 섹션 끝 정의: `[^src1]: 출처 내용`
- 모든 각주는 자동으로 마지막 "참고문헌" 페이지에 모임

**표 선택 시:**
- 파이프 테이블로 비교·수치 데이터 표현
- 첫 번째 열은 자동으로 라벨 스타일(볼드, 중앙정렬) 적용

**이미지 선택 시:**
- `![설명](경로)` 형태로 삽입, figure/figcaption 자동 적용
- 경로를 모르면 사용자에게 요청

**차트 선택 시:**
- 표 바로 다음 줄에 주석 한 줄 추가:
  - `<!-- chart:bar -->` — 비교·순위 (멀티 열 자동 grouped bar)
  - `<!-- chart:line -->` — 추이·트렌드
  - `<!-- chart:pie -->` — 비율·구성 (열 1개면 pie, 2개+ 면 doughnut)
  - `<!-- chart:gantt -->` — 일정 (열 순서: 항목 | 시작(주) | 기간(주))
- 예시:
  | 월 | 매출 |
  |---|---|
  | 1월 | 5000 |
  <!-- chart:bar -->

---

## 마크다운 공통 규칙

- `##` = 섹션 (한 페이지 단위), `###` = 서브섹션 (선택, 2~4개), `####` 이상 금지
- 리스트 구분자: `: ` 사용, ` — ` 금지 (CSS가 자동으로 '—' 추가)
- `>` 인용 블록: 작성자 인사이트·판단·시사점 전용, 사실 나열 금지

## generate_report_tool 필수 사항

- `output_dir`: 현재 작업 디렉토리(cwd) 절대경로 필수
- 모를 경우 사용자에게 `pwd` 결과를 요청
- `get_report_source`, `list_reports` 호출 시에도 동일한 `output_dir` 전달

## 절대 하지 않을 것

- tokens.css / base.css 스타일 오버라이드
- CSS 커스터마이징 옵션 제공
- output_dir 없이 generate_report_tool 호출
- 선택하지 않은 구성 요소 사용"""


@mcp.prompt()
def setup() -> str:
    """Papyrus 환경변수(브랜딩·경로·작성자) 설정 wizard."""
    return """사용자가 Papyrus 환경변수 설정을 시작합니다.

**첫 번째 행동으로 `get_config_status()`를 호출해 현재 설정값을 확인하세요.**
확인 후 아래 AskUserQuestion을 호출합니다.

**반드시 아래 5개 질문을 모두 포함해야 합니다 (하나도 생략 금지):**
1. 브랜드 주색상 (PAPYRUS_COLOR_PRIMARY)
2. Hover 색상 (PAPYRUS_COLOR_PRIMARY_HOVER)
3. 로고 (PAPYRUS_LOGO)
4. 기본 작성자 (PAPYRUS_DEFAULT_AUTHOR)
5. 저장 경로 (PAPYRUS_OUTPUT_DIR)

```
AskUserQuestion(
  questions=[
    {
      "question": "브랜드 주색상을 설정하세요.",
      "header": "브랜드 주색상 (PAPYRUS_COLOR_PRIMARY)",
      "multiSelect": false,
      "options": [
        {"label": "기본값 유지", "description": "#09356E (네이비)"},
        {"label": "직접 입력", "description": "hex 코드를 입력합니다"}
      ]
    },
    {
      "question": "Hover 색상을 설정하세요.",
      "header": "Hover 색상 (PAPYRUS_COLOR_PRIMARY_HOVER)",
      "multiSelect": false,
      "options": [
        {"label": "기본값 유지", "description": "#062845"},
        {"label": "직접 입력", "description": "hex 코드를 입력합니다"}
      ]
    },
    {
      "question": "로고 이미지를 설정하세요.",
      "header": "로고 (PAPYRUS_LOGO)",
      "multiSelect": false,
      "options": [
        {"label": "설정 안 함", "description": "로고 없이 진행"},
        {"label": "경로 입력", "description": "PNG 파일 절대경로를 입력합니다"}
      ]
    },
    {
      "question": "기본 작성자를 설정하세요.",
      "header": "기본 작성자 (PAPYRUS_DEFAULT_AUTHOR)",
      "multiSelect": false,
      "options": [
        {"label": "설정 안 함", "description": "frontmatter에 직접 입력"},
        {"label": "직접 입력", "description": "보고서 frontmatter authors 기본값"}
      ]
    },
    {
      "question": "보고서 저장 경로를 설정하세요.",
      "header": "저장 경로 (PAPYRUS_OUTPUT_DIR)",
      "multiSelect": false,
      "options": [
        {"label": "기본값 유지", "description": "~/papyrus-reports"},
        {"label": "직접 입력", "description": "절대경로를 입력합니다"}
      ]
    }
  ]
)
```

응답 수집 후:
- "직접 입력" 선택 항목만 값을 추가로 질문합니다.
- "기본값 유지" / "설정 안 함" 항목은 env 블록에서 제외합니다.
- 변경할 항목만 포함한 MCP 설정 JSON을 아래 형식으로 안내합니다:

```json
{
  "mcpServers": {
    "papyrus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/brandonnoh/papyrus.git", "papyrus"],
      "env": {
        "PAPYRUS_COLOR_PRIMARY": "#...",
        "PAPYRUS_LOGO": "/absolute/path/logo.png"
      }
    }
  }
}
```

적용 위치: 이 프로젝트만 → `.claude/settings.json` / 전체 → `~/.claude/settings.json`
설정 후 Claude 재시작 필요."""


def main():
    mcp.run(transport="stdio")
