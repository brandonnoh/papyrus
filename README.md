# Papyrus

마크다운을 브랜드 A4 HTML 보고서로 변환하는 MCP 도구.

Claude에게 "보고서 만들어줘"라고 하면 템플릿 선택부터 브라우저 미리보기까지 자동으로 진행됩니다.

---

## 설치

### 프로젝트에 추가 (권장)

사용하려는 프로젝트 루트에 `.mcp.json` 파일을 생성합니다.

```json
{
  "mcpServers": {
    "papyrus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/brandonnoh/papyrus.git", "papyrus"]
    }
  }
}
```

Claude Code가 프로젝트를 열면 `.mcp.json`을 자동으로 감지합니다.

### 전역 설치 (모든 프로젝트에서 사용)

`~/.claude/settings.json`의 `mcpServers` 블록에 추가합니다.

```json
{
  "mcpServers": {
    "papyrus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/brandonnoh/papyrus.git", "papyrus"]
    }
  }
}
```

설정 후 Claude Code를 재시작하면 적용됩니다.

---

## 브랜딩 설정

### 빠른 시작

설치 후 Claude에게 **"papyrus 설정해줘"** 라고 하면 아래 항목을 대화형으로 안내받습니다. 모든 항목은 선택사항입니다.

```
Claude: 로고 파일 경로를 알려주세요. (.png 절대경로, 없으면 Enter)
나:     /Users/me/assets/logo.png

Claude: 브랜드 주색상을 알려주세요. (기본값: #09356E)
나:     #1A3C6E

Claude: 보고서를 저장할 기본 경로를 알려주세요. (기본값: ~/papyrus-reports)
나:     (Enter)
```

설정이 끝나면 Claude가 완성된 MCP 설정 JSON을 출력합니다. 그걸 `settings.json`에 붙여넣으면 됩니다.

### 환경변수 직접 설정

대화형 설정 대신 `.mcp.json`에 `env` 블록으로 직접 지정할 수도 있습니다.

```json
{
  "mcpServers": {
    "papyrus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/brandonnoh/papyrus.git", "papyrus"],
      "env": {
        "PAPYRUS_LOGO": "/절대경로/logo.png",
        "PAPYRUS_COLOR_PRIMARY": "#1A3C6E",
        "PAPYRUS_COLOR_PRIMARY_HOVER": "#0F2A52",
        "PAPYRUS_DEFAULT_AUTHOR": "홍길동",
        "PAPYRUS_OUTPUT_DIR": "/Users/me/reports"
      }
    }
  }
}
```

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `PAPYRUS_LOGO` | 표지·워터마크 로고 절대경로 (.png) | 없음 (로고 미표시) |
| `PAPYRUS_COLOR_PRIMARY` | 브랜드 주색상 hex | `#09356E` |
| `PAPYRUS_COLOR_PRIMARY_HOVER` | 브랜드 hover 색상 hex | `#062845` |
| `PAPYRUS_DEFAULT_AUTHOR` | frontmatter `authors` 기본값 | 없음 |
| `PAPYRUS_OUTPUT_DIR` | 보고서 저장 기본 경로 | `~/papyrus-reports` |

현재 설정 상태는 Claude에게 **"papyrus 설정 확인해줘"** 라고 물으면 확인할 수 있습니다.

---

## 사용법

### 보고서 작성 플로우

Claude에게 **"보고서 만들어줘"** 또는 **"이거 문서로 만들어줘"** 라고 하면 아래 순서로 진행됩니다.

**1단계 — 문서 등급 확인**

```
Claude: 문서 등급을 선택해주세요.
        - 대외비: 외부 공개 불가, 기밀
        - 내부용: 사내 열람용
        - 외부용: 고객·파트너 공유 가능
```

**2단계 — 템플릿 추천**

```
Claude: 내용을 보니 경영진 보고 문서에 가깝습니다.
        → executive-summary (요약보고서) 를 추천합니다.
           proposal (제안서), status-report (업무 보고),
           retrospective (회고), meeting-minutes (회의록) 도 선택 가능합니다.
        어떤 템플릿으로 진행할까요?
```

**3단계 — 마크다운 작성 및 보고서 생성**

템플릿 확정 후 Claude가 내용을 마크다운으로 작성하고 `generate_report_tool`을 호출합니다.
생성 즉시 로컬 브라우저가 열리며 미리보기가 시작됩니다.

---

### 미리보기 기능

보고서가 생성되면 `http://127.0.0.1:{PORT}/`에서 인터랙티브 미리보기가 열립니다.

| 기능 | 방법 |
|------|------|
| **텍스트 편집** | 섹션을 클릭하면 바로 편집 가능 |
| **저장** | `Cmd+S` (Mac) / `Ctrl+S` (Windows) 또는 상단 툴바 저장 버튼 |
| **섹션 순서 변경** | 섹션 왼쪽 ⠇ 핸들을 드래그해서 위아래 이동 |
| **인쇄** | 툴바 인쇄 버튼 또는 `Cmd+P` — 미리보기 UI는 인쇄에서 자동 제거 |
| **A4 페이지 단위** | 화면에서 A4 용지 단위로 분리되어 표시됨 |

편집 후 저장하면 원본 HTML 파일에 반영됩니다.

---

## 템플릿

| ID | 이름 | 용도 | 페이지 수 |
|----|------|------|-----------|
| `executive-summary` | 요약보고서 | 경영진·대표 대상 핵심 사안, 의사결정 보고 | A4 3~5쪽 |
| `meeting-minutes` | 회의록 | 논의 내용, 결정 사항, 액션아이템 기록 | A4 3~5쪽 |
| `proposal` | 제안서 | 새 프로젝트·이니셔티브 승인 요청 | A4 4~6쪽 |
| `status-report` | 업무 보고 | 주간·월간 업무 현황 공유 | A4 3~4쪽 |
| `retrospective` | 회고 | 프로젝트·분기 종료 후 사후 분석 | A4 4~6쪽 |
| `custom` | 커스텀 | 섹션 풀에서 자유 조합 | 제한 없음 |

---

## 마크다운 작성 규칙

Papyrus는 일반 마크다운과 거의 동일하지만 아래 규칙이 있습니다.

### 섹션 구조

- `##` 헤딩 하나 = 본문 섹션 하나
- `###` 서브섹션 허용
- `####` 이상은 렌더링 무시

```markdown
## 1. 현황 분석

본문 내용...

### 세부 항목

세부 내용...
```

### 리스트 구분자

리스트 항목에서 ` — ` 대신 `: ` 를 사용합니다. CSS가 자동으로 `—` 기호를 앞에 붙입니다.

```markdown
<!-- 올바른 예 -->
- 항목명: 설명 내용

<!-- 잘못된 예 — papyrus가 자동으로 수정하지만 권장하지 않음 -->
- 항목명 — 설명 내용
```

### 인용구 (blockquote)

`>` 인용구는 **작성자 인사이트 전용**입니다. 수치나 사실 나열에는 사용하지 않습니다.

```markdown
> 이번 참여는 적자가 예상되지만, 전략적 투자 관점에서 판단했습니다.
```

### 차트

표 바로 아래 줄에 `<!-- chart:TYPE -->` 주석을 추가하면 Chart.js 차트로 렌더링됩니다.

```markdown
| 월 | 매출 | 비용 |
|---|---|---|
| 1월 | 5000 | 3000 |
| 2월 | 6000 | 3500 |
<!-- chart:bar -->
```

| 타입 | 용도 |
|------|------|
| `chart:bar` | 비교·순위 (멀티 열은 grouped bar 자동 적용) |
| `chart:line` | 추이·트렌드 |
| `chart:pie` | 비율·구성 (열 1개: pie, 2개+: doughnut) |
| `chart:gantt` | 프로젝트 일정 (열: 항목 \| 시작(주) \| 기간(주)) |

차트 색상은 `PAPYRUS_COLOR_PRIMARY` 기반으로 자동 생성됩니다.

### 이미지

로컬 파일 또는 URL 이미지를 보고서에 삽입합니다.

**전체 너비 (기본)**
```markdown
![제품 스크린샷](./assets/screenshot.png)
![로고](https://example.com/logo.png)
```

**좌측 이미지 + 우측 텍스트**
```markdown
<!-- img:left -->
![제품 다이어그램](./diagram.png)
다이어그램 우측에 표시될 설명입니다.
여러 단락도 지원합니다.
<!-- /img -->
```

**우측 이미지 + 좌측 텍스트**
```markdown
<!-- img:right -->
![스크린샷](./screen.png)
이미지 좌측에 표시될 설명입니다.
<!-- /img -->
```

이미지는 base64로 인라인 임베딩되어 PDF 및 인쇄에서도 정상 표시됩니다.

### frontmatter

모든 보고서는 frontmatter로 시작합니다. `classification`은 필수입니다.

```markdown
---
title: 보고서 제목
authors: 홍길동, 김철수
date: 2026-04-20
classification: 내부용        # 대외비 / 내부용 / 외부용 (필수)
template: executive-summary   # 생략 시 자동 감지
---
```

---

## MCP 도구 레퍼런스

Claude가 내부적으로 사용하는 도구 목록입니다. 직접 호출할 필요는 없습니다.

| 도구 | 설명 |
|------|------|
| `list_templates` | 보고서 작성 진입점. 템플릿 목록 반환 |
| `get_template_guide_tool` | 선택한 템플릿의 섹션 구조·변수·작성 예시 반환 |
| `get_section_pool_tool` | 커스텀 문서 구성용 섹션 풀 반환 |
| `generate_report_tool` | 마크다운 → A4 HTML 변환 + 미리보기 서버 기동 |
| `get_report_source` | 저장된 보고서의 원본 마크다운 반환 |
| `list_reports` | 저장된 보고서 목록 반환 |
| `get_config_status` | 현재 환경변수 설정 상태 반환 |

---

## 출력 파일

보고서는 `{PAPYRUS_OUTPUT_DIR}/papyrus/` 에 `.html` + `.md` 쌍으로 저장됩니다.

```
~/papyrus-reports/papyrus/
  보고서제목.html    ← 브라우저에서 열거나 인쇄
  보고서제목.md      ← 원본 마크다운 (수정·재생성용)
```

같은 파일명이 이미 존재하면 자동으로 `_2`, `_3` 접미사가 붙습니다.
