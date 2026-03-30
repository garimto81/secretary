# Secretary v2.0 - 프로젝트 전문 비서 시스템

**Version**: 1.0.0
**Created**: 2026-02-13
**Status**: APPROVED (Ralplan 합의)
**관계**: `project-intelligence.plan.md` 확장 (대체 아님)

---

## 비전

각 프로젝트의 **모든 커뮤니케이션을 학습**하고, 새 메시지가 도착할 때마다 **축적된 지식을 기반으로 분석·대응**하는 프로젝트별 전문 비서 시스템.

현재 Secretary v1.0은 메시지를 **1회성으로 분석**합니다. v2.0은 프로젝트별 **지식을 축적**하고 **맥락을 기억**합니다.

### v1.0 vs v2.0

| 항목 | v1.0 (현재) | v2.0 (목표) |
|------|------------|------------|
| 분석 방식 | 메시지 단건 분석 | 축적된 지식 기반 분석 |
| 컨텍스트 | context_entries (수동) | 자동 학습된 Knowledge Base |
| 프로젝트 이해 | 키워드 매칭 | 히스토리 전체 이해 |
| 크로스채널 | 불가 | 이메일↔Slack 자동 연결 |
| 질문 응답 | 불가 | "EBS 벤더 중 가장 저렴한 곳?" 답변 가능 |
| 초안 품질 | 기본 프롬프트 | 프로젝트 맥락 + 과거 대화 반영 |

---

## 복잡도 점수: 5/5

| 조건 | 점수 | 근거 |
|------|:----:|------|
| 파일 범위 | 1 | 10+ 신규 파일, 5+ 기존 수정 |
| 아키텍처 | 1 | Knowledge Store, Embedding Pipeline 신규 |
| 의존성 | 1 | chromadb 또는 sqlite-vec, sentence-transformers |
| 모듈 영향 | 1 | intelligence/, gateway/, knowledge/ 3개 모듈 |
| 사용자 명시 | 1 | "ralplan" 키워드 포함 |

---

## 핵심 기능

### F1: 프로젝트별 Knowledge Store (핵심)
- 프로젝트별 이메일+Slack 전체 히스토리를 벡터 DB에 저장
- 초기 학습: 기존 이메일/Slack 히스토리 일괄 수집 (Bootstrap)
- Embedding: Ollama nomic-embed-text (768dim) 로컬 생성
- 메타데이터: project_id, source(slack/gmail), sender, date, thread_id

### F2: 실시간 Knowledge Ingestion
- Gateway Pipeline 처리 완료 후 자동으로 Knowledge Store에 추가
- 새 이메일 도착 → Embedding 생성 → Vector DB 저장
- 새 Slack 메시지 → Embedding 생성 → Vector DB 저장
- 비동기 처리 (Pipeline 블로킹 없음)

### F3: RAG 기반 맥락 분석 (Context-Aware Analysis)
- Ollama 분석 시 관련 과거 메시지를 Vector DB에서 검색
- 검색된 맥락을 프롬프트에 포함하여 분석 품질 향상
- 예: "SUN-FLY에서 새 견적 도착" → 과거 SUN-FLY 대화 자동 검색

### F4: 크로스채널 Entity 연결
- 같은 사람/프로젝트/주제가 이메일과 Slack에 걸쳐 논의될 때 자동 연결
- Entity 추출: 인명, 회사명, 금액, 날짜
- Thread linking: 같은 주제의 이메일 스레드 ↔ Slack 대화

### F5: 프로젝트 Expert 질의
- Slack에서 비서에게 프로젝트 질문 가능
- 예: "EBS 프로젝트에서 가장 저렴한 RFID 벤더는?"
- Knowledge Store 검색 → Ollama/Claude 답변 생성

### F6: 지능형 초안 생성 (Enhanced Draft)
- Claude Opus 초안 생성 시 RAG 컨텍스트 포함
- 과거 대화 톤/스타일 학습하여 일관된 응답
- "지난번에 논의한 가격 기준으로..." 등 맥락 참조

---

## 기존 Plan과의 관계

### `project-intelligence.plan.md` (Phase 0-7) → 완료됨
- 2-Tier LLM (Ollama + Claude Opus) ✅
- DedupFilter, ContextMatcher, DraftStore ✅
- PriorityQueue, Reporter ✅
- 130+ 테스트 ✅

### 본 Plan → Phase 0-7 위에 구축
- 기존 코드 **유지** (대체하지 않음)
- handler.py의 `_build_context()`를 **RAG로 확장**
- context_store.py의 context_entries를 **Knowledge Store로 보강**
- 새 모듈: `scripts/knowledge/` 추가

---

## 아키텍처 방향

### Critic 합의: 점진적 접근

**Phase 1 (MVP)**: SQLite FTS5 전문검색 + 메타데이터 필터
- 현재 2개 프로젝트에 Vector DB는 과잉
- SQLite FTS5로 한국어+영어 전문검색 먼저 구현
- 충분하지 않으면 Phase 2에서 Vector DB 도입

**Phase 2 (확장)**: Vector DB (ChromaDB) + Embedding
- 검색 품질이 FTS5로 부족할 때만 진행
- ChromaDB: 로컬 실행, Python 네이티브, Windows 호환
- Ollama nomic-embed-text embedding

**Phase 3 (고도화)**: Entity 추출 + 크로스채널 연결
- NER (Named Entity Recognition) 추가
- 이메일-Slack 자동 연결

---

## 기술 결정사항 (Ralplan 합의)

### TD-1: 저장소 전략 (점진적)
- Phase 1: SQLite FTS5 (`data/knowledge.db`)
- Phase 2: ChromaDB (`data/chroma/`) + SQLite 메타데이터 유지
- 이유: 2개 프로젝트에 Vector DB는 과잉 (Critic 합의)

### TD-2: Embedding 모델
- Ollama nomic-embed-text (768dim, 로컬)
- 한국어 성능: 보통 (영어 최적화 모델이지만 기본 검색은 동작)
- 대안: multilingual-e5-base (한국어 전용 시)

### TD-3: Knowledge Ingestion 위치
- Gateway Pipeline의 **별도 Worker** (inline 아님)
- Pipeline Stage 6 완료 후 비동기 큐로 전달
- 이유: Embedding 생성은 느릴 수 있음 (CPU: ~200ms/문서)

### TD-4: Bootstrap (초기 학습)
- CLI 명령: `cli.py learn --project ebs --source gmail --label ebs`
- Gmail 라벨 전체 수집 → 본문 추출 → Chunk → 저장
- Slack 채널 히스토리 전체 수집 → 저장
- 1회성 작업 (이후 실시간 Ingestion)

### TD-5: 컨텍스트 윈도우 관리
- Ollama (32K): 원본 메시지(2K) + RAG 결과(6K) + 프롬프트(2K) = ~10K chars
- Claude Opus: 원본(2K) + Ollama 추론(3K) + RAG 결과(4K) + 프로젝트 컨텍스트(3K) = ~12K chars

### TD-6: 자동 전송 금지 유지
- 기존 안전 정책 100% 유지
- Expert 질의 응답도 draft 형태로만 생성

---

## 실행 계획 (5 Phase)

### Phase 1: Knowledge Store MVP (SQLite FTS5)
**목표**: 프로젝트별 메시지 축적 + 전문검색

| Task | 내용 | 예상 |
|------|------|------|
| T1 | `scripts/knowledge/__init__.py`, `store.py` 모듈 생성 | 신규 |
| T2 | SQLite FTS5 스키마 (knowledge.db) | 신규 |
| T3 | Bootstrap CLI: `cli.py learn --project X --source gmail` | 확장 |
| T4 | Bootstrap CLI: `cli.py learn --project X --source slack` | 확장 |
| T5 | handler.py `_build_context()` → Knowledge Store 검색으로 교체 | 수정 |
| T6 | analyze_prompt.txt에 RAG 컨텍스트 섹션 추가 | 수정 |
| T7 | 테스트: FTS5 검색 정확도, Bootstrap 동작 | 신규 |

**검증**: `cli.py learn --project ebs --source gmail --label ebs` 실행 후 "RFID" 검색 시 관련 이메일 반환

### Phase 2: 실시간 Knowledge Ingestion
**목표**: 새 메시지 도착 시 자동으로 Knowledge Store 업데이트

| Task | 내용 | 예상 |
|------|------|------|
| T8 | Knowledge Ingestion Worker (비동기 큐) | 신규 |
| T9 | Pipeline → Ingestion Worker 연결 | 수정 |
| T10 | 중복 Ingestion 방지 (message_id 기반) | 신규 |
| T11 | server.py Worker lifecycle 관리 | 수정 |
| T12 | 테스트: 실시간 Ingestion 동작 검증 | 신규 |

**검증**: Slack 메시지 수신 → 5초 내 Knowledge Store 반영 확인

### Phase 3: Vector DB 도입 (조건부)
**조건**: Phase 1-2 결과 FTS5 검색 품질이 불충분할 때만 진행

| Task | 내용 | 예상 |
|------|------|------|
| T13 | ChromaDB 통합 (`scripts/knowledge/vector_store.py`) | 신규 |
| T14 | Ollama nomic-embed-text Embedding 생성 | 신규 |
| T15 | FTS5 → ChromaDB 마이그레이션 유틸 | 신규 |
| T16 | Hybrid Search (FTS5 + Vector 결합) | 신규 |
| T17 | 테스트: Embedding 품질, 검색 정확도 비교 | 신규 |

### Phase 4: Expert Query (프로젝트 질의)
**목표**: Slack에서 비서에게 프로젝트 관련 질문

| Task | 내용 | 예상 |
|------|------|------|
| T18 | 질의 감지 (봇 멘션 + 질문 패턴) | 신규 |
| T19 | Knowledge Store 검색 → Ollama 답변 생성 | 신규 |
| T20 | Slack 응답 (draft 또는 직접 - 설정 가능) | 신규 |
| T21 | 대화 이력 관리 (멀티턴) | 신규 |

### Phase 5: 크로스채널 + Entity 연결
**목표**: 이메일-Slack 자동 연결, 엔티티 추출

| Task | 내용 | 예상 |
|------|------|------|
| T22 | Entity 추출 (인명, 회사명, 금액) | 신규 |
| T23 | Thread Linking (이메일↔Slack 주제 연결) | 신규 |
| T24 | Knowledge Graph 시각화 (CLI) | 신규 |

---

## 위험 요소

| 위험 | 심각도 | 완화 |
|------|:------:|------|
| FTS5 한국어 토큰화 부정확 | MEDIUM | ICU tokenizer 또는 형태소 분석기 |
| Ollama Embedding CPU 성능 | MEDIUM | 배치 처리 + 비동기 Worker |
| ChromaDB Windows 호환성 | LOW | pip install chromadb 테스트 완료 |
| Knowledge 폭발 (연간 25K+) | MEDIUM | 90일 retention + 요약 압축 |
| 기존 Phase 0-7 코드 충돌 | LOW | 기존 코드 유지, 새 모듈만 추가 |
| Ollama 다운 시 학습/검색 불가 | HIGH | FTS5 fallback (Embedding 없이도 검색) |

---

## MVP 정의 (Phase 1 완료 시)

**최소 기능**:
1. ✅ Gmail 라벨별 이메일 일괄 학습
2. ✅ Slack 채널별 메시지 일괄 학습
3. ✅ FTS5 기반 프로젝트별 검색
4. ✅ Ollama 분석 시 관련 과거 메시지 자동 포함
5. ✅ CLI: `cli.py learn`, `cli.py search`

**MVP 가치**: "EBS 프로젝트에서 SUN-FLY가 제시한 RFID 칩 가격이 얼마였지?" → FTS5 검색 → 관련 이메일 반환

---

## Critic 검토 결과

### 승인된 결정
1. ✅ SQLite FTS5 우선 (Vector DB 후순위) - 과잉 방지
2. ✅ 기존 코드 유지 + 확장 방식 - Phase 0-7 보존
3. ✅ 별도 Worker로 Ingestion - Pipeline 블로킹 방지
4. ✅ 자동 전송 금지 유지 - 안전 정책 보존

### 경고 사항
1. ⚠️ nomic-embed-text 한국어 성능 미검증 → Phase 2 진입 전 벤치마크 필수
2. ⚠️ Expert Query(F5)는 Phase 4 → MVP에 미포함 (과도한 범위)
3. ⚠️ Entity 추출은 Ollama qwen3:8b로 충분한지 검증 필요
