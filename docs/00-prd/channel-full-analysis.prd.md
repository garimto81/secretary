# 채널 완벽 분석 시스템 PRD

**버전**: 1.0.0 | **작성일**: 2026-02-20 | **상태**: Draft

---

## 배경 및 목적

### 문제
현재 채널 지식 문서(`config/channel_docs/{channel_id}.md`)가 다음 이유로 품질이 매우 낮음:

1. **TF-IDF 키워드 오염**: `mastery_analyzer.py`가 URL 파편(`com`, `https`), GitHub 사용자명(`garimto`), 이슈 URL 단어(`report`, `issues`, `invalid`)를 주요 토픽으로 추출
2. **Claude subprocess 실패 → fallback**: `channel_prd_writer._call_claude()`가 실패하면 `_build_fallback_prd()`가 위 오염된 키워드를 그대로 사용
3. **전체 메시지 미수집**: 현재는 `KnowledgeStore`에 저장된 일부 메시지만 분석. 채널의 실제 대화 맥락 반영 불가
4. **Chatbot 답변 품질 저하**: `_handle_chatbot_message()`가 빈약한 채널 컨텍스트 JSON으로 답변

### 목적
채널의 모든 메시지를 JSON으로 완전 수집 → Sonnet으로 의미 분석 → 고품질 채널 지식 문서 생성 → 이를 기반으로 Slack 메시지에 정확히 답변하는 시스템 구축

---

## 요구사항

### FR-01: 채널 전체 메시지 JSON 덤프
- `ChannelMessageDumper` 클래스 신규 생성
- 기존 `lib.slack.client.get_history_with_cursor()` 활용 (이미 존재)
- 채널의 전체 메시지를 페이지네이션으로 수집
- 저장 경로: `data/channel_dumps/{channel_id}.json`
- JSON 구조: `{ channel_id, channel_name, dump_date, total_messages, messages: [{ts, user, text, thread_ts, reactions}] }`
- 기존 덤프 있으면 증분 업데이트 (마지막 ts 이후 메시지만 추가)
- `force=True` 옵션으로 전체 재수집 가능

### FR-02: JSON → Sonnet 분석 → 채널 지식 문서 생성
- `ChannelPRDWriter.write_from_dump(channel_id, dump_path)` 메서드 추가
- 덤프 JSON에서 최근 N개(기본 2000개) 메시지를 청킹하여 Sonnet에 전달
- 메시지가 많을 경우 Map-Reduce: 청크별 요약 → 통합 분석
- Sonnet 프롬프트에 실제 대화 내용 포함 (TF-IDF 키워드 아님)
- 생성 항목: 채널 목적, 주요 논의 주제, 실제 Q&A 패턴, 의사결정 이력, 기술 스택, 멤버 역할, 커뮤니케이션 특성
- URL 불용어 필터: `com`, `https`, `github`, `garimto` 등 오염 패턴 차단
- 출력: `config/channel_docs/{channel_id}.md` (기존 경로 유지)

### FR-03: 채널 지식 문서 기반 Slack 답변
- `handler._load_channel_doc(channel_id)` 메서드 추가 (MD 파일 로드)
- `_handle_chatbot_message()`에서 기존 JSON 컨텍스트 + MD 문서 통합 사용
- MD 문서가 있으면 우선 사용, 없으면 기존 JSON 컨텍스트 fallback
- Sonnet 프롬프트에 채널 MD 문서를 "채널 지식베이스" 섹션으로 주입

### FR-04: 최초 분석 트리거
- Gateway 서버 시작 시 등록된 채널에 대해 덤프 파일 없으면 자동 실행
- 수동 CLI: `python scripts/knowledge/channel_message_dumper.py --channel {channel_id}`
- `config/channels.json`의 `enabled: true` 채널만 대상

---

## 기능 범위

### IN-SCOPE
- `scripts/knowledge/channel_message_dumper.py` 신규 생성
- `scripts/knowledge/channel_prd_writer.py` `write_from_dump()` 메서드 추가
- `scripts/intelligence/response/handler.py` MD 문서 로드 로직 추가
- `scripts/gateway/server.py` 시작 시 채널 덤프 자동 실행 훅
- `mastery_analyzer.py` URL 불용어 패턴 추가

### OUT-OF-SCOPE
- 기존 `write()` 메서드 삭제 (호환성 유지)
- 기존 `channel_contexts/*.json` 제거 (병행 사용)
- Telegram, Gmail 채널 (Slack만)

---

## 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| 성능 | 1000개 메시지 덤프 < 60초 (rate limiter 1.2초/요청) |
| 저장 | 덤프 JSON 최대 50MB 제한 (초과 시 최근 10000개만 유지) |
| 재사용 | 덤프 파일 있으면 Sonnet 재분석만 실행 (API 절약) |
| 안전 | 덤프는 로컬만 저장, 외부 전송 금지 |
| 호환 | 기존 `mastery_context` 기반 flow 유지 (점진적 전환) |

---

## 영향 파일

| 파일 | 변경 유형 |
|------|----------|
| `scripts/knowledge/channel_message_dumper.py` | **신규** |
| `scripts/knowledge/channel_prd_writer.py` | **수정** (write_from_dump 추가) |
| `scripts/intelligence/response/handler.py` | **수정** (_load_channel_doc 추가) |
| `scripts/gateway/server.py` | **수정** (시작 시 자동 덤프 훅) |
| `scripts/knowledge/mastery_analyzer.py` | **수정** (URL 불용어 추가) |
| `data/channel_dumps/` | **신규 디렉토리** |
| `tests/knowledge/test_channel_message_dumper.py` | **신규** |

---

## 우선순위

| 순위 | 항목 | 이유 |
|:----:|------|------|
| P0 | FR-01 덤프 수집 | 기반 데이터 없으면 나머지 불가 |
| P0 | FR-02 Sonnet 분석 | 핵심 품질 개선 |
| P1 | FR-03 MD 기반 답변 | 사용자 체감 효과 |
| P2 | FR-04 자동 트리거 | 편의성 |
| P2 | mastery_analyzer 불용어 | 기존 flow 품질 개선 |

---

## Changelog

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-02-20 | 1.0.0 | 최초 작성 |
