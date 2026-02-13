# Plan: 필터 로직 적합성 개선 (filter-logic-fix)

## 배경

Secretary 프로젝트의 Gateway Pipeline, Intelligence Handler, ContextMatcher, ProjectRegistry,
Gmail/Slack Adapter, ActionDispatcher 전반에 걸친 필터 로직에 구조적 결함이 발견됨.

Architect 심층 분석 결과 18건의 문제가 식별됨:
- CRITICAL 2건: DedupFilter 비결정적 eviction, Ollama fallback 시 Opus 호출 폭주
- HIGH 7건: substring 기반 키워드 매칭 거짓 양성, Gmail 라벨 비결정적 선택 등
- MEDIUM 6건: resolve_project 우선순위 역전, seen_ids 무한 증가 등
- LOW 3건: 주석 불일치, low priority 미반환 등

## 문제 정의

### 핵심 구조적 문제 3가지
1. **substring matching 남용**: 단어 경계 없이 `in` 연산자로 키워드 매칭 → 체계적 거짓 양성
2. **set 자료구조 순서 의존**: DedupFilter, Gmail 라벨이 set→list 변환 후 순서에 의존 → 비결정적
3. **안전하지 않은 fallback 기본값**: Ollama 실패 시 needs_response=True → 비용 폭주

## 구현 범위

### 수정 대상 파일 (7개)
| 파일 | 수정 내용 | 심각도 |
|------|----------|--------|
| `scripts/intelligence/response/handler.py` | DedupFilter OrderedDict, Ollama fallback, resolve_project, mark_processed 타이밍 | CRITICAL+MEDIUM |
| `scripts/gateway/pipeline.py` | 긴급/액션 키워드 정규식 전환, break 제거, 질문 패턴 개선 | HIGH |
| `scripts/intelligence/project_registry.py` | 키워드 단어 경계 정규식 적용 | HIGH |
| `scripts/gateway/adapters/gmail.py` | 라벨 정렬 안정화, seen_ids eviction | HIGH+MEDIUM |
| `scripts/gateway/action_dispatcher.py` | 한국어 상대 날짜 Calendar 연동 | HIGH |
| `scripts/gateway/adapters/slack.py` | is_mention 정규식 개선 | MEDIUM |
| `scripts/intelligence/response/context_matcher.py` | 주석-코드 confidence 불일치 수정 | LOW |

### 제외 항목
- LOW 심각도 중 low priority 미반환 (기능 변경, 향후 별도 기획)
- find_by_channel 다중 매칭 (현재 config에서 문제 없음)

## 위험 요소

| 위험 | 영향 | 완화 |
|------|------|------|
| 정규식 전환 시 기존 동작 변경 | 기존에 감지되던 패턴이 누락될 수 있음 | 기존 substring 매칭 사례를 정규식이 포함하도록 설계 |
| DedupFilter 자료구조 변경 | 메모리 사용 패턴 변경 | OrderedDict은 dict과 유사한 메모리 사용 |
| Ollama fallback 변경 | needs_response=False로 변경 시 응답 필요 메시지 누락 | 로깅 강화로 모니터링 |

## 복잡도 점수

- 파일 범위: 1점 (7개 파일 수정)
- 아키텍처: 0점 (기존 패턴 내 수정)
- 의존성: 0점 (표준 라이브러리만 추가)
- 모듈 영향: 1점 (gateway + intelligence)
- 사용자 명시: 0점
- **총점: 2/5 → Planner 단독**
