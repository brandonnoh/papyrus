# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**Papyrus** — 마크다운을 브랜드 A4 HTML 보고서로 변환하는 MCP 도구.
GitHub: https://github.com/brandonnoh/papyrus

## 개발 명령어

```bash
uv sync                                    # 의존성 설치
uv run pytest tests/ -v                    # 전체 테스트
uv run pytest tests/test_parser.py -v      # 단일 테스트 파일
uv run pytest tests/ -k "test_name" -v     # 특정 테스트
uv run mcp dev src/papyrus/server.py       # MCP 개발 모드
```

## 패키지 구조

```
src/papyrus/
  server.py      # MCP 서버 — @mcp.tool() / @mcp.prompt() 정의
  brand.py       # BrandConfig — PAPYRUS_* 환경변수 로드
  parser.py      # parse_markdown() → ReportData, fix_markdown() 자동 수정
  renderer.py    # render_report() → HTML 문자열, save_report() → 파일
  catalog.py     # TemplateMeta — meta.yaml 디스커버리/로드
  validator.py   # StyleViolationError — CSS 규칙 위반 감지
  static/        # tokens.css (디자인 토큰), base.css (레이아웃), logo.png
  templates/     # executive-summary/, meeting-minutes/, _base/
    _base/       # base.html (공통 레이아웃), custom.html (커스텀 문서)
    <id>/        # meta.yaml + template.html + style.css
```

## 데이터 흐름

```
마크다운 텍스트
  → fix_markdown()         # ' — ' → ': ' 자동 수정, 사실형 blockquote 제거
  → _apply_frontmatter_defaults()  # date/authors 기본값 주입
  → parse_markdown()       # ReportData (sections, title, authors, classification)
  → render_report()        # Jinja2 렌더링, CSS 조립, brand 색상 패치
  → save_report()          # {output_dir}/papyrus/{filename}.html + .md
```

## 핵심 규칙

- `classification` (대외비/내부용/외부용) 없으면 `_require_classification()`에서 ValueError
- 로고는 `PAPYRUS_LOGO` 환경변수로만 — `_resolve_logo()`에 번들 fallback 없음
- `tokens.css`, `base.css` 직접 수정 금지 — 브랜드 색상은 `_patch_brand_colors()`로만 패치
- 마크다운 ## 섹션 = 한 페이지, ### 서브섹션 허용, #### 이상 렌더링 무시
- 리스트 항목 구분자: `: ` 사용, ` — ` 금지 (CSS가 자동으로 '—' 추가)
- blockquote (`>`) = 작성자 인사이트 전용, 수치/사실 나열 금지
- 파일 300줄 / 함수 20줄 제한

## 개발 시 절대 금지 사항

- **MCP 서버 프로세스 kill 금지** — `pkill`, `kill` 등으로 papyrus MCP 서버를 임의 종료하지 않는다.
  코드 변경 후 반영이 필요하면 사용자에게 `/mcp` 재연결을 안내하는 것에 그친다.
  서버를 죽이면 Claude Code MCP 연결이 끊어지고 사용자가 수동으로 재연결해야 한다.

## preview 모드 CSS 우선순위 규칙

- `preview.py`의 `_PREVIEW_CSS`는 `.page--body { background: transparent !important }` 를 적용한다.
- 특정 `.page--body` 하위 변형(예: `page--footnotes`)을 예외 처리하려면
  **복합 선택자** `.page--body.page--footnotes` 를 써서 특이도(specificity)를 높여야 한다.
  단순 `.page--footnotes` 선택자는 특이도가 같아 순서에만 의존하므로 신뢰할 수 없다.

## 템플릿 추가 방법

`src/papyrus/templates/<id>/` 디렉토리에 세 파일 생성:
- `meta.yaml` — id, name, description, keywords, sections, variables
- `template.html` — `_base/base.html` 상속 (`{% extends "_base/base.html" %}`)
- `style.css` — 템플릿 전용 스타일 (tokens.css 변수 사용)

## 배포 구조

- `uvx --from git+https://github.com/brandonnoh/papyrus.git papyrus` 로 설치
- 로컬 `.claude/settings.json`의 MCP 서버 설정: `uv run --directory . papyrus`
- 테스트(`tests/`), 내부 문서(`docs/`, `STYLE_AUTHORITY.md`), 생성 보고서(`/papyrus/`, `/output/`)는 gitignore 대상

## MCP 진입점

- **슬래시 명령어**: `/papyrus:start_report` (`@mcp.prompt()` 단일 노출)
- `start_report`는 보고서 작성 + 브랜딩 설정 두 가지 모두 처리
- `list_templates` → `get_template_guide_tool` → 마크다운 작성 → `generate_report_tool` 순서 필수
- `output_dir`는 현재 프로젝트 절대경로 전달 필수 (미전달 시 `~/papyrus-reports`)

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `PAPYRUS_LOGO` | 로고 절대경로 (.png) | 없음 (로고 미표시) |
| `PAPYRUS_COLOR_PRIMARY` | 브랜드 주색상 | `#09356E` |
| `PAPYRUS_COLOR_PRIMARY_HOVER` | hover 색상 | `#062845` |
| `PAPYRUS_DEFAULT_AUTHOR` | frontmatter authors 기본값 | 없음 |
| `PAPYRUS_OUTPUT_DIR` | 보고서 저장 경로 | `~/papyrus-reports` |
