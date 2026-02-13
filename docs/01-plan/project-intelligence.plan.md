# Project Intelligence - PDCA Plan Document

**Version**: 2.0.0
**Created**: 2026-02-10
**Status**: APPROVED (Ralplan 합의 - Iteration 2/5)
**Ralplan 결과**: Planner + Architect + Critic 3자 합의 달성

---

## 목표

프로젝트를 완벽하게 이해한 뒤, Slack과 Gmail에서 해당 프로젝트 관련 사항을 실시간으로 대응하는 시스템

## 복잡도 점수: 4/5

| 조건 | 점수 | 근거 |
|------|:----:|------|
| 파일 범위 | 1 | 25+ 신규 파일, 6개 기존 파일 수정 |
| 아키텍처 | 1 | 증분 분석 엔진, 프로젝트 컨텍스트 저장소 신규 |
| 의존성 | 1 | slack-sdk 직접 사용, Gmail History API 신규 |
| 모듈 영향 | 1 | intelligence/, gateway/, config/, core/ 4개 모듈 |
| 사용자 명시 | 0 | ralplan 키워드 없음 |

## 핵심 결정사항 (Ralplan 합의)

1. **Slack 증분 조회**: `lib.slack` wrapper 우회, `slack_sdk.WebClient` 직접 사용 (oldest 미지원 이슈)
2. **Gmail 증분 조회**: History API 사용 (기존 코드에 없는 신규 구현, fallback 포함)
3. **동기/비동기 브릿지**: 모든 동기 라이브러리 호출에 `asyncio.to_thread()` 사용
4. **LLM Token Budget**: max 4000 tokens (12000 chars), truncation: recent_first
5. **자동 전송 금지**: 모든 send()는 draft 파일 생성만 (절대 자동 전송 안 함)

## 상세 계획

Ralplan 합의된 전체 실행 계획은 `.omc/plans/project-intelligence.md` 참조

### 5 Phase 구조

| Phase | 내용 | Task 수 |
|:-----:|------|:-------:|
| 1 | Project Context Engine (DB, Registry, Collector) | T1-T3.5 |
| 2 | Incremental Analysis Engine (State, Trackers, Runner) | T4-T6 |
| 3 | Gateway Adapters (Slack, Gmail) | T7-T8 |
| 4 | Response Pipeline (Matcher, Generator, Store) | T9-T11 |
| 5 | Integration (Pipeline, CLI, Config) | T12-T14 |

### 위험 요소

| 위험 | 영향 | 완화 |
|------|------|------|
| Gmail historyId 만료 | 증분 조회 실패 | messages.list fallback |
| Slack rate limit | polling 지연 | 5초 간격 + backoff |
| LLM API 비용 | 비용 증가 | rate limit 5/min |
| SQLite concurrent write | DB lock | WAL mode |

## Critic 검토 결과

- Iteration 1: REJECT (5 Critical + 5 Minor 이슈)
- Iteration 2: OKAY (모든 이슈 해결 확인)
