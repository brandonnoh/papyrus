# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**Papyrus** — 마크다운을 브랜드 A4 HTML 보고서로 변환하는 MCP 도구.
GitHub: https://github.com/brandonnoh/papyrus

## 개발 명령어

```bash
uv sync                                    # 의존성 설치
uv run python -m pytest tests/ -v          # 전체 테스트
uv run python -m pytest tests/test_parser.py -v      # 단일 테스트 파일
uv run python -m pytest tests/ -k "test_name" -v     # 특정 테스트
uv run mcp dev src/papyrus/server.py       # MCP 개발 모드
```

## 패키지 구조

```
src/papyrus/
  server.py              # MCP 서버 — @mcp.tool() / @mcp.prompt() 정의
  brand.py               # BrandConfig — PAPYRUS_* 환경변수 로드, 차트 팔레트 자동 생성
  parser.py              # parse_markdown() → ReportData, fix_markdown() 자동 수정
  renderer.py            # render_report() → HTML, save_report() → 파일
  _chart_renderer.py     # Chart.js canvas/script 생성 — renderer.py에서 분리
  _image_utils.py        # embed_images() — layout block 처리, base64 인라인 임베딩
  _footnote_utils.py     # render_sections_with_footnotes() — 전역 각주 번호 일관성
  _writing_rules.py      # SYNTAX_REFERENCE — 파서 구문 레퍼런스 단일 소스
  catalog.py             # TemplateMeta — meta.yaml 디스커버리/로드
  validator.py           # StyleViolationError — 6종 CSS·구조 규칙 위반 감지
  preview.py             # PreviewServer — 스레드 HTTP 서버, 브라우저 자동 오픈
  _preview_css_js.py     # PREVIEW_CSS / PREVIEW_JS 상수 (preview.py 줄수 분리)
  _preview_dashboard.py  # build_html() — 대시보드 HTML 생성
  _preview_pdf.py        # render_pdf() — Playwright로 PDF 바이트 반환
  _thumbnail.py          # generate_thumbnail() — Playwright로 첫 페이지 PNG 캡처
  static/                # tokens.css (디자인 토큰), base.css (레이아웃), logo.png
  templates/             # executive-summary/, meeting-minutes/, proposal/, status-report/, retrospective/, _base/
    _base/          # base.html (공통 레이아웃), custom.html (커스텀 문서)
    <id>/           # meta.yaml + template.html + style.css
```

## MCP 도구 목록

| 도구 | 역할 |
|------|------|
| `list_templates()` | 템플릿 목록 반환 — 보고서 생성 첫 단계 |
| `get_template_guide_tool(template_id)` | 템플릿별 섹션·변수·가이드 + 파서 구문 레퍼런스 반환 (프리훅) |
| `get_section_pool_tool()` | 커스텀 문서용 전체 섹션 풀 |
| `generate_report_tool(...)` | 마크다운 → 구문 검증 → HTML 저장 + 미리보기 서버 실행 |
| `get_report_source(filename, output_dir)` | 저장된 .md 원본 반환 |
| `get_config_status()` | PAPYRUS_* 환경변수 현재값 확인 |
| `list_reports(output_dir)` | 저장된 보고서 목록 (파일명·크기) |
| `open_dashboard(output_dir)` | 대시보드 브라우저 오픈 |

**프롬프트**: `start_report` (보고서 작성 위저드), `setup` (환경변수 설정 위저드)

## 데이터 흐름

```
마크다운 텍스트
  → fix_markdown()                  # ' — ' → ': ', 사실형 blockquote 제거
  → lint_markdown()                 # 구문 오류 감지 → 에러 시 조기 반환
  → _apply_frontmatter_defaults()   # date/authors 기본값 주입
  → parse_markdown()
      → render_sections_with_footnotes()  # 전역 각주 번호 통합 렌더링
      → ReportData (sections, title, authors, classification, footnotes_html)
  → render_report()                 # Jinja2 렌더링, CSS 조립, brand 색상 패치
      → _inject_section_charts()    # 차트 표를 Chart.js canvas로 교체
      → inject_mermaid_diagrams()   # ```mermaid 코드블록 → Mermaid.js SVG
      → embed_images()              # layout block → grid div, 이미지 → base64
  → save_report()                   # {output_dir}/papyrus/{filename}.html + .md
  → open_preview()                  # 새 PreviewServer(랜덤 포트) 시작 + 브라우저 오픈
  → generate_thumbnail() (백그라운드 스레드)
```

## 핵심 규칙

- `classification` (대외비/내부용/외부용) 없으면 `_require_classification()`에서 ValueError
- 로고는 `PAPYRUS_LOGO` 환경변수로만 — `_resolve_logo()`에 번들 fallback 없음
- `tokens.css`, `base.css` 직접 수정 금지 — 브랜드 색상은 `_patch_brand_colors()`로만 패치
- 마크다운 ## = 섹션 구분, ### = 서브섹션 허용, #### 이상 렌더링 무시 (페이지 분할은 내용 높이 기준 자동)
- 리스트 항목 구분자: `: ` 사용, ` — ` 금지 (CSS가 자동으로 '—' 추가)
- 칼아웃: `> [!info|tip|warning|danger] 본문` — 4종, 한 줄 전용, 인라인 마크다운 지원
- blockquote (`>`) = 작성자 인사이트 전용, 수치/사실 나열 금지
- 이미지: `![캡션](경로)` 전체 너비, `<!-- img:left/right -->...<img>...텍스트...<!-- /img -->` 2컬럼 레이아웃
- 이미지 경로는 output_dir 기준 상대경로 또는 절대경로, URL(https://) 지원
- 다이어그램: ` ```mermaid ` 코드블록 → Mermaid.js SVG 렌더링 (flowchart, sequenceDiagram, mindmap)
- 차트: 표 + `<!-- chart:bar|line|pie|gantt -->` → Chart.js canvas 렌더링
- 파일 300줄 / 함수 20줄 제한

## validator.py — 6종 검사

| 검사 | 심각도 | 내용 |
|------|--------|------|
| `no-hardcoded-color` | error | `<style>` 내 하드코딩 hex 색상 |
| `no-inline-style` | error | `style=` 인라인 속성 |
| `image-structure` | error | `<img>`가 `<figure>` 또는 `.img-layout` 밖에 위치 |
| `required-section` | error | meta.yaml의 required 섹션 누락 |
| `allowed-fonts` | warning | 허용 목록 외 font-family 사용 |
| `table-caption` | warning | `<caption>` 없는 `<table>` |

## preview 서버 구조

- `generate_report_tool` 호출마다 `PreviewServer` 인스턴스를 새로 생성 (OS 랜덤 포트)
- 서버는 daemon 스레드로 실행 — 프로세스 종료 시 자동 정리
- `/` → 가장 최근 보고서, `/{filename}.html` → 특정 파일, `/dashboard` → 대시보드
- `/export-pdf` → Playwright PDF 렌더링, `/thumbnail/{file}` → 썸네일 PNG
- `/save` (POST) → contenteditable 편집 내용 파일에 저장

## preview 모드 CSS 우선순위 규칙

- `_preview_css_js.py`의 `PREVIEW_CSS`는 `.page--body { background: transparent !important }` 를 적용한다.
- 특정 `.page--body` 하위 변형(예: `page--footnotes`)을 예외 처리하려면
  **복합 선택자** `.page--body.page--footnotes` 를 써서 특이도(specificity)를 높여야 한다.
  단순 `.page--footnotes` 선택자는 특이도가 같아 순서에만 의존하므로 신뢰할 수 없다.

## 개발 시 절대 금지 사항

- **MCP 서버 프로세스 kill 금지** — `pkill`, `kill` 등으로 papyrus MCP 서버를 임의 종료하지 않는다.
  코드 변경 후 반영이 필요하면 사용자에게 `/mcp` 재연결을 안내하는 것에 그친다.
  서버를 죽이면 Claude Code MCP 연결이 끊어지고 사용자가 수동으로 재연결해야 한다.

## 템플릿 추가 방법

`src/papyrus/templates/<id>/` 디렉토리에 세 파일 생성:
- `meta.yaml` — id, name, description, keywords, sections, variables
- `template.html` — `_base/base.html` 상속 (`{% extends "_base/base.html" %}`)
- `style.css` — 템플릿 전용 스타일 (tokens.css 변수 사용)
- 차트: 표 + `<!-- chart:bar|line|pie|gantt -->` 주석 → Chart.js 렌더링
- 다이어그램: ` ```mermaid ` 코드블록 → Mermaid.js 렌더링 (flowchart, sequenceDiagram, mindmap)

## 배포 구조

- `uvx --from git+https://github.com/brandonnoh/papyrus.git papyrus` 로 설치
- 로컬 `.claude/settings.json`의 MCP 서버 설정: `uv run --directory . papyrus`
- 테스트(`tests/`), 내부 문서(`docs/`, `STYLE_AUTHORITY.md`), 생성 보고서(`/papyrus/`, `/output/`)는 gitignore 대상

## MCP 진입점

- **슬래시 명령어**: `/papyrus:start_report` (`@mcp.prompt()` 단일 노출)
- `start_report`는 보고서 작성 위저드, `setup`은 환경변수 설정 위저드
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
