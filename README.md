# Papyrus

마크다운을 브랜드 A4 HTML 보고서로 변환하는 MCP 도구.

## 설치

프로젝트의 `.claude/settings.json` 또는 전역 `~/.claude/settings.json`에 추가:

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

Claude를 재시작하면 적용됩니다.

---

## 브랜딩 설정

설치 후 Claude에게 **"papyrus 설정해줘"** 라고 하면 대화형으로 설정을 안내받을 수 있습니다.

Claude가 아래 항목을 순서대로 질문하고, 완성된 MCP 설정 JSON을 생성해줍니다:

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `PAPYRUS_LOGO` | 워터마크·표지에 사용할 로고 절대경로 (.png) | 없음 |
| `PAPYRUS_COLOR_PRIMARY` | 브랜드 주색상 (hex) | `#09356E` |
| `PAPYRUS_COLOR_PRIMARY_HOVER` | 브랜드 주색상 hover (hex) | `#062845` |
| `PAPYRUS_DEFAULT_AUTHOR` | frontmatter authors 기본값 | 없음 |
| `PAPYRUS_OUTPUT_DIR` | 보고서 저장 기본 경로 | `~/papyrus-reports` |

모든 항목은 선택사항입니다.

---

## 사용법

**보고서 작성**: Claude에게 "보고서 만들어줘" 라고 하면 아래 순서로 진행됩니다:

1. **문서 등급 확인** — 대외비 / 내부용 / 외부용
2. **템플릿 추천** — 사용자 의도에 맞는 템플릿 제안 및 확인
3. **가이드 확인 → 마크다운 작성 → 보고서 생성**

생성된 보고서는 `{output_dir}/papyrus/`에 `.html` + `.md` 쌍으로 저장됩니다.

---

## 템플릿

| ID | 이름 | 용도 |
|----|------|------|
| `executive-summary` | 대표보고 요약 | 경영진 대상 핵심 사안 보고. A4 2~4페이지 |
| `meeting-minutes` | 회의록 | 논의·결정·액션아이템 기록. A4 3~5페이지 |
| `custom` | 커스텀 | 섹션 풀에서 자유 조합 |

---

## MCP 도구

| 도구 | 설명 |
|------|------|
| `list_templates` | 보고서 작성 진입점. 템플릿 목록 + 워크플로우 안내 반환 |
| `get_template_guide_tool` | 선택한 템플릿의 섹션 구조·필수 변수·작성 예시 반환 |
| `get_section_pool_tool` | 커스텀 문서 구성 시 섹션 풀 반환 |
| `generate_report_tool` | 마크다운 → A4 HTML 보고서 변환. `file://` URI 반환 |
| `get_report_source` | 저장된 보고서의 원본 마크다운 반환 |
| `list_reports` | 저장된 보고서 목록 반환 |
| `get_config_status` | 현재 환경변수 설정 상태 반환 |

---

## frontmatter

```markdown
---
title: 보고서 제목
authors: 작성자
date: 2026-04-19
classification: 대외비        # 대외비 / 내부용 / 외부용 (필수)
template: executive-summary   # 생략 시 기본 템플릿 적용
---
```

`classification` 미입력 시 보고서 생성이 차단됩니다.
