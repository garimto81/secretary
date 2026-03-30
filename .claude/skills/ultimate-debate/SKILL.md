---
name: ultimate-debate
description: >
  3-Agent parallel analysis and consensus judgment using Claude Agent Teams.
  Triggers on "debate", "토론", "의사결정", "합의". Use when facing complex
  architectural or strategic decisions that benefit from multiple perspectives.
version: 3.0.0
triggers:
  keywords:
    - "토론"
    - "debate"
    - "합의"
    - "다중 관점"
    - "3-Agent 분석"
    - "교차 검토"
  file_patterns:
    - ".claude/debates/**/*.md"
  context:
    - "복잡한 설계 결정"
    - "여러 관점 필요"
    - "아키텍처 결정"
    - "전략 수립"

auto_trigger: false
---

# Ultimate Debate Skill v3.0

**Type**: Agent Teams 기반 3-관점 합의 판정
**Status**: v3.0 — Python 의존 제거, Agent Teams 전환

## 개요

3개 Claude 에이전트가 서로 다른 관점으로 병렬 분석 → 교차 검토 → 합의 판정하는 스킬입니다.
외부 API(GPT/Gemini) 의존을 완전 제거하고, Agent Teams 패턴만으로 동작합니다.

## v2 → v3 변경점

| 항목 | v2 (레거시) | v3 (현재) |
|------|-----------|----------|
| 실행 방식 | Python 스크립트 + 외부 API | Agent Teams 패턴 |
| AI 모델 | Claude + GPT + Gemini | Claude 3종 에이전트 |
| 인증 | API 키 / OAuth 토큰 | 불필요 |
| 의존성 | pip install, TokenStore | 없음 |
| 관점 다양성 | 모델 차이 | 역할 차이 (architect/reviewer/researcher) |

## 3-Agent 구성

| 에이전트 | subagent_type | 관점 | 분석 초점 |
|---------|---------------|------|----------|
| perspective-structure | architect | 구조적 관점 | 아키텍처, 확장성, 의존성, 장기 유지보수 |
| perspective-quality | code-reviewer | 품질/보안 관점 | 버그, 보안, 코드 품질, 테스트 커버리지 |
| perspective-external | researcher | 외부 사례 관점 | 베스트 프랙티스, 커뮤니티 패턴, 대안 비교 |

## 실행 워크플로우

```
Phase 1: 3-Agent 병렬 분석
    ↓
Phase 2: Lead 합의 판정 (공통/불일치 분류)
    ↓ (80%+ 합의?)
    ├─ YES → Phase 5: 최종 판정
    └─ NO  → Phase 3: 재토론 (max 2회)
                ↓
             Phase 4: 재판정
                ↓
             Phase 5: 최종 판정
```

## Agent Teams 실행 패턴

### Phase 1: 병렬 분석

```
TeamCreate(team_name="debate-{topic}")

Agent(subagent_type="architect", name="perspective-structure",
      description="구조적 관점 분석", team_name="debate-{topic}",
      prompt="[관점: 아키텍처/구조] 아래 주제를 구조적 관점에서 분석하라.

              주제: {topic}

              분석 항목:
              1. 아키텍처 적합성 (현재 시스템과의 정합성)
              2. 확장성 (향후 요구사항 수용 가능성)
              3. 의존성 리스크 (외부/내부 의존 복잡도)
              4. 장기 유지보수 비용

              출력 형식:
              ## 구조적 분석
              ### 결론: [1줄 요약]
              ### 근거:
              1. [근거 1]
              2. [근거 2]
              3. [근거 3]
              ### 리스크: [주요 리스크 1-2개]
              ### 추천: [구체적 행동 제안]")

Agent(subagent_type="code-reviewer", name="perspective-quality",
      description="품질/보안 관점 분석", team_name="debate-{topic}",
      prompt="[관점: 품질/보안/유지보수] 아래 주제를 품질 관점에서 분석하라.

              주제: {topic}

              분석 항목:
              1. 코드 품질 영향 (복잡도, 가독성, 테스트 용이성)
              2. 보안 리스크 (OWASP Top 10 관련)
              3. 에러 핸들링 완전성
              4. 기술 부채 증감

              출력 형식:
              ## 품질/보안 분석
              ### 결론: [1줄 요약]
              ### 근거:
              1. [근거 1]
              2. [근거 2]
              3. [근거 3]
              ### 리스크: [주요 리스크 1-2개]
              ### 추천: [구체적 행동 제안]")

Agent(subagent_type="researcher", name="perspective-external",
      description="외부 사례/패턴 분석", team_name="debate-{topic}",
      prompt="[관점: 외부 사례/베스트 프랙티스] 아래 주제를 외부 관점에서 분석하라.

              주제: {topic}

              분석 항목:
              1. 업계 베스트 프랙티스 비교
              2. 유사 오픈소스 프로젝트의 접근 방식
              3. 대안 비교 (최소 2가지)
              4. 커뮤니티 컨센서스

              출력 형식:
              ## 외부 사례 분석
              ### 결론: [1줄 요약]
              ### 근거:
              1. [근거 1]
              2. [근거 2]
              3. [근거 3]
              ### 대안: [대안 A vs B 비교]
              ### 추천: [구체적 행동 제안]")
```

### Phase 2: 합의 판정 (Lead 직접 수행)

3개 에이전트 결과를 수집한 후 Lead가 직접 판정:

1. **공통 결론 추출** (agreed items): 3개 분석에서 동일 방향의 결론
2. **불일치 항목 식별** (disputed items): 상충하는 의견
3. **합의율 계산**: `agreed / (agreed + disputed) × 100`

| 합의율 | 판정 | 다음 액션 |
|:------:|------|----------|
| 80%+ | CONSENSUS | Phase 5 (최종 판정) |
| 50-79% | PARTIAL | Phase 3 (재토론, 불일치 항목만) |
| < 50% | NO_CONSENSUS | Phase 3 (재토론, 전체) |

### Phase 3: 재토론 (max 2회)

불일치 항목만 추출하여 3개 에이전트에게 재분석 요청:

```
# 각 에이전트에게 SendMessage로 불일치 항목 전달
SendMessage(type="message", recipient="perspective-structure",
    content="[재토론] 다음 항목에서 불일치가 발생했습니다.
             불일치 항목: {disputed_items}
             다른 관점의 근거: {other_perspectives}
             기존 입장을 유지하거나 수정하되, 근거를 강화하세요.")
# perspective-quality, perspective-external에도 동일 패턴
```

### Phase 4-5: 최종 판정

```
# Lead가 최종 합의안 작성
# 결과 저장
Write(".claude/debates/{topic}/FINAL.md", final_report)

TeamDelete()
```

## FINAL.md 출력 형식

```markdown
# Debate: {topic}
**날짜**: {YYYY-MM-DD}
**합의율**: {N}%
**라운드**: {round_count}

## 합의 항목
1. {agreed_item_1}
2. {agreed_item_2}

## 최종 추천
{recommendation}

## 관점별 요약
### 구조적 관점 (architect)
{summary}

### 품질/보안 관점 (code-reviewer)
{summary}

### 외부 사례 관점 (researcher)
{summary}

## 불일치 → 해결
| 항목 | 구조 | 품질 | 외부 | 해결 |
|------|------|------|------|------|
| {item} | {position} | {position} | {position} | {resolution} |
```

## /auto 통합 동작

`--debate` 옵션이 `/auto`에 전달되면 **Step 2.0 (옵션 처리)** 단계에서 실행:

1. 토론 주제 파라미터 파싱
2. Agent Teams 패턴으로 3-Agent 병렬 분석 실행
3. Lead가 합의 판정 수행
4. 최종 합의안을 `.claude/debates/{topic}/FINAL.md`에 저장
5. 결과를 후속 Phase 판단에 컨텍스트로 반영

**옵션 실패 시: 에러 출력, 절대 조용히 스킵 금지.**

## code-reviewer 자동 트리거

`code-reviewer.md`의 Comprehensive 모드 (200줄+ diff)에서 자동 트리거:
- 4-병렬 리뷰에서 CRITICAL/HIGH 이슈 3개+ 발견 시
- Debate 주제 = "코드 리뷰 불일치 해결: {이슈 요약}"
- 합의 결과를 최종 리뷰 판정에 반영

## 레거시 코드

`scripts/` 디렉토리의 Python 코드는 레거시로 보존합니다 (삭제 안 함).
Core Engine (`packages/ultimate-debate/`)도 참조용으로 유지합니다.

---

**Last Updated**: 2026-03-24
**License**: MIT
