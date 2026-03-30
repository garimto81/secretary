# Knowledge Ingestion Worker Plan

**Version**: 1.0.0
**Created**: 2026-02-18
**Status**: PLANNED
**Complexity Score**: 3/5

---

## 배경

### 현재 상황

Secretary 프로젝트는 실시간 메시지 처리 파이프라인(Gateway)과 AI 분석 엔진(Intelligence)을 통해 메시지를 받아 분석하고 응답 초안을 생성합니다. 그러나 처리된 메시지들이 Knowledge Store(SQLite FTS5)에 자동으로 축적되지 않아, 다음 문제가 발생합니다:

1. **RAG 컨텍스트 부족**: Intelligence 분석 시 관련 과거 커뮤니케이션 히스토리를 활용하지 못함
2. **프로젝트 매칭 정확도 저하**: Ollama(Tier 1) 분석이 충분한 컨텍스트 없이 수행되어 project_id 매칭 정확도(confidence) 저하
3. **수동 Bootstrap만 가능**: 현재는 `bootstrap_from_gmail/slack` 함수로 과거 데이터만 일괄 로드 가능, 신규 메시지는 자동 축적 불가
4. **지식 활용 불가**: 프로젝트별 의사결정 히스토리, FAQ, 패턴 학습이 불가능

### Knowledge Store 현황

```
KnowledgeStore (scripts/knowledge/store.py)
├── SQLite FTS5 (unicode61 tokenizer)
├── 테이블: documents (id, project_id, source, sender_name, thread_id, content, metadata, created_at)
├── 트리거: documents INSERT/UPDATE/DELETE 시 FTS 자동 동기화
├── 메서드:
│   ├── ingest(doc: KnowledgeDocument) → 문서 저장 (UPSERT)
│   ├── search(query, project_id) → SearchResult 리스트
│   ├── search_by_thread(thread_id, project_id)
│   ├── search_by_sender(sender_name, project_id)
│   └── cleanup(retention_days=180) → 오래된 문서 삭제
```

현재 ingest는 외부에서 명시적으로 호출해야 하며, Gateway Pipeline과 연결되지 않은 상태입니다.

### 기존 Integration 계획

`response/handler.py`에서 RAG 컨텍스트 검색은 구현되어 있습니다:

- **Step 2.5** (Analyzer 전): Knowledge Store로 rule_hint 기반 검색
- **Step 7** (Draft 작성): 최종 project_id로 관련 문서 5건 검색

그러나 Knowledge Store에 신규 메시지가 축적되지 않아, 검색 결과가 과거 bootstrap 데이터에만 의존합니다.

---

## 목표

Gateway Pipeline에서 처리된 모든 메시지를 실시간으로 Knowledge Store에 축적하며, 동시에 Entity 추출을 통해 메타데이터를 태깅하고 RAG 성능을 향상시킨다.

### 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| **Knowledge 자동 축적률** | 처리 메시지의 70% 이상 Knowledge에 저장 | 일일 실행 후 `get_stats()` 통계 |
| **RAG 검색 효과** | Intelligence 분석 시 관련 컨텍스트 3건 이상 자동 검색 | `response/handler.py` 로그 분석 |
| **프로젝트 매칭 정확도 향상** | confidence >= 0.7 비율이 70% → 80%+ 달성 | Ollama 분석 결과 confidence 추적 |
| **Query 응답 시간** | FTS5 검색 <500ms (10건 리밋) | 성능 벤치마크 |
| **중복 방지** | 동일 메시지가 2번 이상 저장되지 않음 | ID 기반 UPSERT 검증 |

---

## 복잡도 분석

| 항목 | 점수 | 근거 |
|------|:----:|------|
| **파일 범위** | 1/2 | 4개 신규 파일 (`ingestion_handler.py`, `entity_extractor.py`, `noise_filter.py`, `knowledge_integration_test.py`) + 2개 기존 수정 |
| **아키텍처** | 1/2 | 단순 Pipeline 핸들러 + 모듈식 필터/추출기, 기존 KnowledgeStore 활용 |
| **의존성** | 0/1 | 기존 라이브러리 재활용, 신규 외부 의존성 없음 (NER은 규칙 기반 대체) |
| **모듈 영향** | 0/1 | Gateway pipeline, Intelligence handler에만 후킹, 기존 로직 변경 최소 |
| **비용 영향** | 1/1 | Ollama/Claude 호출 증가 없음, 로컬 FTS5 검색만 추가 |
| **Total** | **3/5** | 중간 복잡도: 구현 간단하나, 필터링 기준 설정과 Entity 추출 정확도가 key |

---

## 핵심 설계 결정

### 1. Pipeline Integration Point

**선택**: Stage 6 Custom Handler로 `ProjectIntelligenceHandler` 다음에 `KnowledgeIngestionHandler` 추가

**근거**:
- Intelligence 분석이 완료된 후에 인제스트하여 project_id, intent 등 메타데이터 활용 가능
- EnrichedMessage에 pipeline 분석 결과(priority, actions, project_id) 반영됨
- Draft 생성 전 Knowledge에 저장되므로, 다음 메시지 분석 시 RAG 효과 즉시 가능

```
Pipeline Stages:
1-5: 기존 (Priority, Action, Storage, Notification, Dispatch)
   6a: ProjectIntelligenceHandler (Ollama 분석)
   6b: KnowledgeIngestionHandler (✓ NEW - Knowledge에 저장)
   6c: (향후 추가 가능)
```

### 2. Noise Filtering Strategy

**필터링 기준** (다음 중 하나라도 해당되면 제외):

| 필터 | 제외 조건 | 예시 |
|------|----------|------|
| **길이** | < 20자 | "네", "감사합니다", "1" |
| **인사말** | 시작이 인사 키워드 | "안녕하세요", "Hi there" |
| **이모지 과다** | 이모지 > 30% | "😂😂😂ㅋㅋㅋ" |
| **반복 문자** | 같은 문자 3회 이상 연속 | "ㅋㅋㅋㅋㅋ", "aaaaaa" |
| **URL/코드만** | 유의미한 텍스트 없음 | "`function test() {}`" |

**구현**: `knowledge/noise_filter.py`에서 `is_worth_ingesting(text, sender_name)` 메서드

### 3. Entity Extraction (메타데이터 태깅)

**범위**: 규칙 기반 추출 (NER 라이브러리 의존 회피)

| 엔티티 | 추출 방법 | 예시 |
|--------|----------|------|
| **사람** | sender_name + 텍스트의 @mention | `@김철수`, `김철수 님` |
| **프로젝트** | rule_match.project_id + Ollama 분석 결과 | "secretary", "wsoptv" |
| **날짜** | Pipeline deadline 패턴 재활용 | "2월 20일", "내일", "이번 주" |
| **액션 아이템** | Pipeline action_keywords 재활용 | "검토 부탁", "마감 2/20" |
| **키워드** | 프로젝트 키워드 매칭 | 프로젝트 config에 정의된 키워드 |

**저장**: `metadata_json` 필드에 JSON으로 저장

```json
{
  "entities": {
    "people": ["김철수", "박영희"],
    "projects": ["secretary"],
    "dates": ["2026-02-20"],
    "actions": ["검토", "마감"],
    "keywords": ["배포", "일정"]
  },
  "extracted_at": "2026-02-18T10:30:00",
  "confidence": 0.85
}
```

### 4. Selective Ingestion (선택적 저장)

**원칙**: 모든 메시지가 아닌, 의미 있는 정보만 저장하여 FTS5 인덱스 크기 제어

**결정 로직**:

```
메시지 수신
  ↓
Noise Filter 통과? → NO: Skip
  ↓ YES
Project ID 확정? → NO: pending_match 저장만 (Intelligence 처리 결과만)
  ↓ YES
Intent가 '잡담'이 아닌가? → NO: 확률 50% 만 저장 (샘플링)
  ↓ YES
Knowledge에 저장 ✓
```

**의도**:
- 프로젝트 없는 메시지: 이미 pending_match로 추적 중이므로 Knowledge에서 제외
- 잡담: 샘플링으로 인덱스 증가 제어, 중요도 낮음
- 질문/요청/정보공유: 100% 저장 (RAG 컨텍스트로 매우 유용)

### 5. Deduplication (중복 방지)

**방식**: `(source, source_id)` 조합을 unique key로 사용

- Gmail: `source="gmail"`, `source_id=message_id` (Gmail API)
- Slack: `source="slack"`, `source_id=thread_ts + "-" + message_ts`

**구현**: KnowledgeStore의 `ingest(doc)` 메서드가 이미 UPSERT를 지원하므로, 동일 ID 재입수 시 자동 덮어쓰기

### 6. RAG Context 주입 (분석 성능 향상)

**시점**:
- **Step 2.5** (Analyzer 전): 규칙 기반 project_id 힌트 전 Knowledge 검색
- **Step 7** (Draft 작성): 최종 project_id로 관련 문서 5건 검색

**검색 전략**:

```python
# Step 2.5: rule_hint 생성 전, 빠른 컨텍스트 수집
rag_results = await store.search(
    query=text[:500],
    project_id=None,  # 힌트 없음, 일단 저장된 모든 문서에서 검색
    limit=3
)
rag_context = "\n".join([r.document.content[:200] for r in rag_results])

# Ollama analyzer에 RAG context 전달
analysis = await analyzer.analyze(
    text=text,
    ...,
    rag_context=rag_context  # 기존 인자로 이미 지원
)
```

**효과**:
- Ollama가 과거 관련 메시지 컨텍스트를 보고 project_id 매칭 confidence 향상
- 예: "배포 일정 있나요?" → Knowledge에서 "배포" 관련 과거 메시지 3건 검색 → Ollama가 secretary 프로젝트 확정 (confidence 0.9)

---

## 상세 구현 계획

### 파일 구조

```
scripts/knowledge/
├── store.py (기존 - 수정 없음)
├── models.py (기존 - 수정 없음)
├── ingestion_handler.py ✓ NEW
├── entity_extractor.py ✓ NEW
└── noise_filter.py ✓ NEW

scripts/gateway/
├── pipeline.py (수정: Stage 6에 핸들러 추가)
└── server.py (수정: 초기화 로직)

scripts/intelligence/response/
└── handler.py (수정: RAG 검색 강화)

tests/
└── knowledge/
    └── test_knowledge_ingestion.py ✓ NEW
```

---

### Task 1: `noise_filter.py` - Noise 필터링

**파일**: `C:\claude\secretary\scripts\knowledge\noise_filter.py` (신규)

**목적**: 메시지 텍스트의 의미도를 판단하여, noise 메시지는 Knowledge 저장 대상에서 제외

**구현 내용**:

```python
class NoiseFilter:
    """메시지 noise 판정"""

    async def is_worth_ingesting(
        self,
        text: str,
        sender_name: str,
        intent: str = "unknown",
        actions: List[str] = None,
    ) -> Tuple[bool, str]:
        """
        Returns:
            (is_meaningful: bool, reason: str)
        """
```

**필터 로직**:

1. **길이**: `len(text.strip()) < 20` → False ("너무 짧음")
2. **인사말**: `text.startswith(["안녕", "Hi", "Hello", "네", "감사"])` → False ("인사말만")
3. **이모지 과다**: `emoji_count / len(text) > 0.3` → False ("이모지 과다")
4. **반복 문자**: `re.search(r'(\w)\1{2,}', text)` → False ("반복 문자")
5. **URL/코드만**: `(url + code) / len(text) > 0.8 and other_text < 20` → False ("코드/URL만")
6. **Intent 샘플링**: `intent == "잡담"` and `random.random() > 0.5` → False (50% 확률)

**Acceptance Criteria**:
- [ ] "네" → False
- [ ] "안녕하세요. 좋은 아침입니다." → False
- [ ] "😂😂😂😂😂" → False
- [ ] "배포 일정 확인 부탁합니다." → True
- [ ] "의사결정: A vs B, B로 진행하겠습니다." → True

---

### Task 2: `entity_extractor.py` - Entity 추출 및 메타데이터 생성

**파일**: `C:\claude\secretary\scripts\knowledge\entity_extractor.py` (신규)

**목적**: 메시지에서 사람, 프로젝트, 날짜, 액션 등을 추출하여 metadata_json에 저장

**구현 내용**:

```python
class EntityExtractor:
    """메시지에서 엔티티 추출"""

    def __init__(self, project_registry: ProjectRegistry):
        self.registry = project_registry

    def extract_entities(
        self,
        text: str,
        sender_name: str,
        project_id: Optional[str],
        intent: str,
        actions: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns:
            {
                "people": ["김철수"],
                "projects": ["secretary"],
                "dates": ["2026-02-20"],
                "actions": ["검토", "배포"],
                "keywords": ["배포", "일정"],
                "confidence": 0.85,
                "extracted_at": "2026-02-18T10:30:00"
            }
        """
```

**추출 전략**:

1. **사람**:
   - sender_name 추가
   - 텍스트에서 `@\w+` 추출
   - `\w+ 님`, `\w+ 이`, 등록된 팀원 이름 매칭

2. **프로젝트**:
   - `project_id` 직접 사용
   - 텍스트에서 프로젝트 키워드 매칭 (fallback)

3. **날짜**:
   - Pipeline deadline 패턴 재활용: `/(\d{1,2})[/.](\d{1,2})/`, `/이번\s*주/`, `/내일/`
   - 추출된 텍스트를 정규화 (2026-02-20 형식)

4. **액션**:
   - Pipeline action_keywords 재활용
   - actions 파라미터에서 "action_request:검토" → "검토" 추출

5. **키워드**:
   - 프로젝트 registry의 키워드와 텍스트 매칭
   - TF-IDF 대신 단순 부분 문자열 매칭

**Acceptance Criteria**:
- [ ] "김철수님이 @박영희에게 배포 일정을 2월 20일까지 검토 부탁했습니다." → 모든 엔티티 추출
- [ ] 프로젝트 없으면 빈 list 반환
- [ ] confidence가 0.0-1.0 범위

---

### Task 3: `ingestion_handler.py` - Pipeline 핸들러

**파일**: `C:\claude\secretary\scripts\knowledge\ingestion_handler.py` (신규)

**목적**: Gateway Pipeline Stage 6 Custom Handler로, 메시지를 Knowledge Store에 저장

**구현 내용**:

```python
class KnowledgeIngestionHandler:
    """Gateway Pipeline Stage 6 핸들러"""

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        entity_extractor: EntityExtractor,
        noise_filter: NoiseFilter,
        sampling_rate: float = 1.0,  # 1.0 = 100% 저장
    ):
        self.knowledge_store = knowledge_store
        self.entity_extractor = entity_extractor
        self.noise_filter = noise_filter
        self.sampling_rate = sampling_rate

    async def handle(self, enriched_message, result) -> None:
        """
        Pipeline handler entry point.

        Args:
            enriched_message: EnrichedMessage (priority, actions, project_id 포함)
            result: PipelineResult
        """
```

**처리 흐름**:

```
1. EnrichedMessage에서 원본 NormalizedMessage 추출
2. Noise Filter: is_worth_ingesting() 호출
   → False: 로그 기록 후 반환
   → True: 계속

3. Project ID 결정
   - Intelligence 분석 완료된 경우: enriched_message에서 project_id 추출
   - 미완료: pending 상태로 저장 (프로젝트 정보 없이 content만)

4. Entity 추출
   - extractor.extract_entities() 호출
   - metadata_json 생성

5. KnowledgeDocument 생성
   - id = f"{source}_{source_id}"
   - source_id = message.id (Slack) 또는 message.id (Gmail)
   - content = message.text
   - metadata = entity 추출 결과

6. Knowledge Store에 저장
   - store.ingest(doc) 호출
   - 동일 ID면 UPSERT로 자동 덮어쓰기

7. 로그 기록
   - logger.info(f"Ingested: {doc.id}, project={project_id}, entities_count={...}")
```

**Acceptance Criteria**:
- [ ] Pipeline에서 add_handler()로 핸들러 등록 가능
- [ ] 메시지 처리 완료 후 Knowledge에 저장됨
- [ ] project_id 없으면 저장 안 함 (또는 별도 pending 테이블에 저장)
- [ ] 중복 메시지는 UPSERT로 처리
- [ ] 성능: 핸들러 실행 <100ms (Knowledge 저장 로직 최소화)

---

### Task 4: `response/handler.py` - RAG 검색 강화

**파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py` (수정)

**수정 범위**: `_analyze_message()` 메서드에서 RAG 검색 로직 추가

**현황**:
- 기존 Step 2.5에서 RAG 검색은 구현되어 있음 (handler.py line 142-163)
- 그러나 Knowledge Store가 비어있으므로 검색 결과 없음

**추가 사항**:

1. **검색 strategy 개선**: rule_match 없을 때도 일반 검색 수행

```python
# 기존: rule_match.project_id가 있을 때만 검색
# 변경: project_id 없으면 프로젝트 지정 없이 전역 검색
if self._knowledge_store and original_text:
    hint_project_id = None  # 명시적으로 None (프로젝트 제한 없음)
    if rule_match.matched:
        hint_project_id = rule_match.project_id

    results = await self._knowledge_store.search(
        query=original_text[:500],
        project_id=hint_project_id,
        limit=5,
    )
```

**Acceptance Criteria**:
- [ ] Knowledge Store에 문서 축적 후 검색 결과 자동 반영
- [ ] Ollama 프롬프트에 RAG context 주입됨
- [ ] 성능 영향 없음 (FTS5 검색 <100ms)

---

### Task 5: `pipeline.py`, `server.py` - Pipeline 통합

**파일**: `C:\claude\secretary\scripts\gateway\pipeline.py`, `server.py` (수정)

**수정 내용**:

#### pipeline.py

```python
# 기존: Stage 6 custom handlers
for handler in self.handlers:
    await handler(enriched, result)

# 변경: KnowledgeIngestionHandler를 항상 마지막에 추가
# (Intelligence Handler 후 실행)
```

**구현**:
- `server.py`에서 pipeline 초기화 시, KnowledgeIngestionHandler를 add_handler()로 등록
- 순서: ProjectIntelligenceHandler → KnowledgeIngestionHandler

#### server.py

```python
# __init__ 또는 start() 메서드에서:

from scripts.knowledge.store import KnowledgeStore
from scripts.knowledge.ingestion_handler import KnowledgeIngestionHandler
from scripts.knowledge.entity_extractor import EntityExtractor
from scripts.knowledge.noise_filter import NoiseFilter

# ...

knowledge_store = KnowledgeStore()
await knowledge_store.init_db()

entity_extractor = EntityExtractor(self.registry)
noise_filter = NoiseFilter()

ingestion_handler = KnowledgeIngestionHandler(
    knowledge_store=knowledge_store,
    entity_extractor=entity_extractor,
    noise_filter=noise_filter,
)

self.pipeline.add_handler(ingestion_handler.handle)
```

**Acceptance Criteria**:
- [ ] Gateway 서버 시작 시 KnowledgeIngestionHandler 초기화됨
- [ ] 메시지 처리 후 Knowledge에 저장됨
- [ ] Pipeline 성능 영향 <50ms

---

### Task 6: 테스트 작성

**파일**: `C:\claude\secretary\tests\knowledge\test_knowledge_ingestion.py` (신규)

**테스트 케이스**:

```python
# Test NoiseFilter
def test_noise_filter_short_text():
    assert not filter.is_worth_ingesting("네", "sender")

def test_noise_filter_greeting():
    assert not filter.is_worth_ingesting("안녕하세요", "sender")

def test_noise_filter_meaningful():
    assert filter.is_worth_ingesting("배포 일정 확인 부탁합니다", "sender")

# Test EntityExtractor
def test_entity_extraction_people():
    entities = extractor.extract_entities(
        text="김철수님이 @박영희에게 전달했습니다",
        sender_name="김철수",
        project_id="secretary",
        intent="정보공유"
    )
    assert "김철수" in entities["people"]
    assert "박영희" in entities["people"]

def test_entity_extraction_projects():
    entities = extractor.extract_entities(
        text="배포 일정 확인",
        sender_name="sender",
        project_id="secretary",
        intent="요청"
    )
    assert "secretary" in entities["projects"]

# Test IngestionHandler
@pytest.mark.asyncio
async def test_ingestion_handler_stores_message():
    handler = KnowledgeIngestionHandler(
        knowledge_store=store,
        entity_extractor=extractor,
        noise_filter=noise_filter,
    )

    enriched = EnrichedMessage(original=test_message)
    enriched.project_id = "secretary"
    result = PipelineResult(message_id=test_message.id)

    await handler.handle(enriched, result)

    # Knowledge Store에서 조회 확인
    docs = await store.get_recent("secretary", limit=1)
    assert len(docs) > 0
    assert docs[0].content == test_message.text

@pytest.mark.asyncio
async def test_ingestion_handler_skips_noise():
    await handler.handle(enriched_greeting, result)
    # Knowledge Store에 저장되지 않음
    stats = await store.get_stats("secretary")
    # noise 메시지는 카운트 안 됨
```

**Acceptance Criteria**:
- [ ] 모든 테스트 통과
- [ ] 기존 테스트 영향 없음

---

## 구현 순서 (Task Sequence)

```
Task 1: NoiseFilter 구현 (독립적)
  ↓
Task 2: EntityExtractor 구현 (ProjectRegistry 필요)
  ↓
Task 3: IngestionHandler 구현 (Task 1, 2에 의존)
  ↓
Task 4: response/handler.py RAG 검색 강화 (선택적, Task 3과 병렬 가능)
  ↓
Task 5: Pipeline/Server 통합 (Task 3에 의존)
  ↓
Task 6: 테스트 작성 (마지막)
```

---

## 위험 요소 및 완화 방안

| 위험 | 영향 | 가능성 | 완화 방안 |
|------|------|--------|----------|
| **FTS5 인덱스 크기 증가** | 검색 성능 저하 | HIGH | Noise filter + sampling 으로 70% 메시지만 저장, cleanup 30일마다 실행 |
| **Entity 추출 정확도 저하** | 메타데이터 품질 저하 | MEDIUM | 규칙 기반 추출로 confidence < 0.6이면 저장 금지 |
| **Pipeline 성능 영향** | 메시지 처리 지연 | LOW | async 처리, <100ms 보장, 실패 시 무시 |
| **Knowledge Store와 Intelligence 간 순환 의존** | 설계 복잡도 | LOW | Intelligence Handler → Knowledge Handler 순서 강제 |
| **RAG 검색 결과 부족 (초기)** | RAG 효과 없음 | HIGH | 초기 bootstrap 후 시작, 1주일 누적 필요 |
| **중복 저장** | 인덱스 낭비 | LOW | UPSERT로 자동 처리 |

---

## 성공 기준

### Phase 1: 기초 구현 (Week 1)

- [ ] NoiseFilter, EntityExtractor, IngestionHandler 구현 완료
- [ ] 모든 테스트 통과
- [ ] Pipeline에 핸들러 등록 완료

### Phase 2: 통합 및 검증 (Week 1-2)

- [ ] 실시간 메시지 처리 시 Knowledge 자동 저장 확인
- [ ] 일일 실행 후 통계: 처리 메시지의 70%+ 저장됨
- [ ] RAG 검색 결과 자동 반영 확인

### Phase 3: 성능 최적화 (Week 2)

- [ ] FTS5 검색 성능 벤치마크 (대상: <500ms for 10 results)
- [ ] Noise filter와 sampling으로 인덱스 크기 제어
- [ ] Pipeline 처리 시간 증가 <50ms 확인

### Phase 4: 효과 측정 (Week 3+)

- [ ] 프로젝트 매칭 정확도 향상 (confidence >= 0.7 비율)
- [ ] Intelligence 분석 수렴 시간 단축 확인
- [ ] 사용자 피드백 수집

---

## 배포 전략

### Stage 1: 로컬 검증 (1-2일)

```bash
# Knowledge Store bootstrap
python -c "
import asyncio
from scripts.knowledge.store import KnowledgeStore
async def main():
    async with KnowledgeStore() as store:
        await store.bootstrap_from_gmail()
        await store.bootstrap_from_slack()
        stats = await store.get_stats()
        print(stats)
asyncio.run(main())
"

# IngestionHandler 테스트
pytest tests/knowledge/test_knowledge_ingestion.py -v
```

### Stage 2: 프로덕션 배포 (1일)

```bash
# 기존 production 서버 상태 백업
cp data/knowledge.db data/knowledge.db.backup-20260218

# 새 코드 배포
git commit -m "feat(knowledge): implement ingestion handler for real-time knowledge accumulation"
git push

# Gateway 서버 재시작
python scripts/gateway/server.py stop
python scripts/gateway/server.py start
```

### Stage 3: 모니터링 (1주일)

```bash
# 일일 통계 조회
python -c "
import asyncio
from scripts.knowledge.store import KnowledgeStore
async def main():
    async with KnowledgeStore() as store:
        stats = await store.get_stats()
        print(f'총 문서: {stats[\"total_documents\"]}')
        print(f'소스별: {stats[\"by_source\"]}')
asyncio.run(main())
" > logs/knowledge_stats.log

# Intelligence 분석 결과 모니터링
grep "Knowledge Store RAG" logs/intelligence.log | wc -l
```

---

## 영향받는 파일

### 신규 파일

| 파일 | 목적 |
|------|------|
| `scripts/knowledge/noise_filter.py` | Noise 메시지 필터링 |
| `scripts/knowledge/entity_extractor.py` | 엔티티 추출 및 메타데이터 생성 |
| `scripts/knowledge/ingestion_handler.py` | Pipeline 핸들러 |
| `tests/knowledge/test_knowledge_ingestion.py` | 통합 테스트 |

### 수정 파일

| 파일 | 수정 범위 | 영향도 |
|------|----------|--------|
| `scripts/gateway/pipeline.py` | custom handler 등록 로직 (1-2줄) | LOW |
| `scripts/gateway/server.py` | KnowledgeIngestionHandler 초기화 (5-10줄) | LOW |
| `scripts/intelligence/response/handler.py` | RAG 검색 강화 (기존 코드 유지, 개선만) | LOW |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `scripts/knowledge/store.py` | ingest() 메서드 이미 완벽하게 구현됨 |
| `scripts/knowledge/models.py` | KnowledgeDocument 모델 완벽함 |
| `scripts/gateway/models.py` | NormalizedMessage, EnrichedMessage 충분함 |

---

## Commit Strategy

| 순서 | 메시지 | 파일 |
|------|--------|------|
| 1 | `feat(knowledge): add noise filter and entity extractor` | `noise_filter.py`, `entity_extractor.py` |
| 2 | `feat(knowledge): implement ingestion handler for gateway pipeline` | `ingestion_handler.py`, `pipeline.py`, `server.py` |
| 3 | `feat(intelligence): enhance RAG search in handler` | `response/handler.py` |
| 4 | `test(knowledge): add integration tests for ingestion` | `test_knowledge_ingestion.py` |

---

## 참고 문서

- **Knowledge Store**: `scripts/knowledge/store.py` (현황 및 API)
- **Gateway Pipeline**: `scripts/gateway/pipeline.py` (Stage 구조)
- **Intelligence Handler**: `scripts/intelligence/response/handler.py` (RAG 검색 위치)
- **Project Registry**: `scripts/intelligence/project_registry.py` (프로젝트 정보)

---

## 다음 단계 (미래 계획)

### Phase 2: Advanced Entity Recognition (미래)

- Konlpy 또는 KoGPT2 기반 NER 모델 통합
- 더 정교한 엔티티 추출 (조직, 역할, 상태 등)

### Phase 3: Knowledge Graph (미래)

- 엔티티 간 관계 그래프 구성
- 그래프 기반 유사 메시지 검색 (시맨틱 검색)

### Phase 4: Knowledge Summarization (미래)

- 프로젝트별 요약본 자동 생성
- 정기 리포트에 Knowledge 요약 포함
