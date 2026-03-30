# Secretary Gateway + Intelligence 서버 워크플로우 설계

**Version**: 2.0 (Phase 0-5 구현 반영)
**Last Updated**: 2026-02-13

---

## 1. 서버 Lifecycle

### 1.1 시작 시퀀스

```
python scripts/gateway/server.py start [--port 8800]
        │
        ▼
SecretaryGateway.start()
        │
   ┌────┴────────────────────────────────────────────────────────────┐
   │  1. PID 파일 생성 (data/gateway.pid)                            │
   │  2. UnifiedStorage 초기화 (gateway.db, aiosqlite)               │
   │     └── 스키마 생성 + enrichments 컬럼 마이그레이션              │
   │  3. MessagePipeline 초기화                                      │
   │     └── urgent/action keywords, deadline 패턴 컴파일            │
   │  4. _connect_adapters()                                         │
   │     ├── gateway.json에서 enabled=true 채널만 어댑터 생성         │
   │     ├── SlackAdapter / GmailAdapter 동적 import                 │
   │     ├── 각 어댑터 connect()                                     │
   │     └── _register_intelligence_handler()                        │
   │         ├── IntelligenceStorage 연결 (intelligence.db, WAL)     │
   │         ├── ProjectRegistry.load_from_config()                  │
   │         ├── ProjectIntelligenceHandler 생성                     │
   │         │   ├── OllamaAnalyzer (qwen3:8b)                      │
   │         │   ├── ClaudeCodeDraftWriter (opus)                    │
   │         │   ├── DedupFilter (LRU 1000)                         │
   │         │   └── ContextMatcher (3-tier)                         │
   │         ├── pipeline.add_handler(handler.handle)                │
   │         ├── [TODO] SecretaryReporter 생성 + handler 주입        │
   │         └── [TODO] handler.start_worker() 호출                  │
   │  5. _running = True                                             │
   │  6. _message_loop() → 각 어댑터별 asyncio.Task 생성             │
   └─────────────────────────────────────────────────────────────────┘
```

### 1.2 운영 루프

```
[각 어댑터 독립 asyncio.Task]
        │
        ▼
_adapter_listen_loop(adapter)
        │
        ▼
async for message in adapter.listen():
    │
    ├── Slack: 5초 간격 폴링 (lib.slack)
    └── Gmail: 60초 간격 폴링 (lib.gmail)
        │
        ▼
    pipeline.process(message)
        │
        ▼
    PipelineResult 반환
    ├── error → 로그 출력
    └── priority='urgent' → 로그 출력
```

### 1.3 종료 시퀀스

```
Gateway.stop()
    │
    ├── 1. _running = False
    ├── 2. asyncio.Task 전부 cancel()
    ├── 3. 각 어댑터 disconnect()
    ├── 4. [TODO] Reporter.stop()
    ├── 5. [TODO] handler.stop_worker()
    ├── 6. [TODO] IntelligenceStorage.close()
    ├── 7. UnifiedStorage.close()
    └── 8. PID 파일 삭제
```

---

## 2. 메시지 처리 파이프라인 (6 Stages)

```
NormalizedMessage (불변 원본)
         │
         ▼
pipeline.process(message)
         │
    ┌────┴─────────────────────────────────────────────────┐
    │  EnrichedMessage 래퍼 생성                            │
    │  enriched = EnrichedMessage(original=message)         │
    └──────────────────────────────────────────────────────┘
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 1: Priority Analysis
    ═════╪═══════════════════════════════════════════════════
         │
         ├── 긴급 키워드 감지 (단어 경계 + 부정 컨텍스트 제외)
         │   "긴급", "urgent", "ASAP", "지금", "바로", "즉시"
         │   제외: "지금까지", "바로가기" 등
         │
         ├── 멘션 감지 (is_mention=True → 'high')
         │
         ├── 마감일 감지 ("2/10 까지", "오늘 중" 등)
         │
         └── → result.priority + enriched.priority 기록
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 2: Action Detection
    ═════╪═══════════════════════════════════════════════════
         │
         ├── 액션 키워드 ("해주세요", "부탁", "요청" 등)
         │   완료형 제외: "확인했", "처리됐"
         │
         ├── 마감일 패턴 추출
         │
         ├── 질문 패턴 감지 (URL/코드블록 제외)
         │
         └── → result.actions + enriched.actions 기록
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 3: Storage (원본 저장)
    ═════╪═══════════════════════════════════════════════════
         │
         └── gateway.db에 NormalizedMessage 저장
             (INSERT OR REPLACE, 원본 불변 보장)
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 4: Notification (Toast)
    ═════╪═══════════════════════════════════════════════════
         │
         ├── priority='urgent' 또는 'high'일 때만
         ├── Rate limit: 분당 10건 (슬라이딩 윈도우)
         └── winotify Toast 알림 (Windows 전용)
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 5: Action Dispatch
    ═════╪═══════════════════════════════════════════════════
         │
         ├── has_action=True일 때만
         ├── ActionDispatcher 실행
         │   ├── deadline → TODO 파일 + Calendar dry-run
         │   ├── action_request → TODO 파일 생성
         │   └── question → 로그만
         └── 실패해도 파이프라인 중단 안 함
         │
    ═════╪═══════════════════════════════════════════════════
    Stage 6: Custom Handlers (Intelligence)
    ═════╪═══════════════════════════════════════════════════
         │
         └── for handler in self.handlers:
                 await handler(enriched, result)
                 │
                 └── ProjectIntelligenceHandler.handle()
                     (아래 섹션 3 참조)
```

---

## 3. Intelligence 2-Tier LLM 워크플로우

### 3.1 전체 흐름

```
ProjectIntelligenceHandler.handle(enriched, result)
         │
         ├── PriorityQueue 활성화? ─── YES → 큐에 삽입 (priority_val, counter)
         │                              │     urgent=0, high=1, normal=2, low=3
         │                              └── _process_loop()에서 순서대로 처리
         │
         └── NO → _process_message() 직접 호출
                   │
    ┌──────────────┴──────────────────────────────────────────┐
    │                                                         │
    │  Step 1: DedupFilter                                    │
    │  ├── 메모리 캐시 (LRU, 1000개) 체크                      │
    │  └── DB fallback (intelligence.db) 체크                  │
    │  → 중복이면 즉시 return                                  │
    │                                                         │
    │  Step 2: ContextMatcher (규칙 기반 3-tier)               │
    │  ├── Tier 1: Channel Match (confidence 0.9)             │
    │  │   Slack 채널 ID → 프로젝트 매핑                       │
    │  ├── Tier 2: Keyword Match (confidence 0.6~0.8)         │
    │  │   텍스트에 프로젝트명/키워드 포함                       │
    │  └── Tier 3: Sender Match (confidence 0.5)              │
    │      발신자 → 프로젝트 연락처 매핑                        │
    │                                                         │
    │  Step 3: Ollama 분석 (분기)                              │
    │  ├── [FAST-TRACK] urgent + rule_match                   │
    │  │   → Ollama 건너뛰기                                  │
    │  │   → AnalysisResult 직접 생성                         │
    │  │     (needs_response=True, project_id=rule의 것)       │
    │  │                                                      │
    │  └── [NORMAL] OllamaAnalyzer.analyze()                  │
    │      → 자유 추론 프롬프트 (analyze_prompt.txt)            │
    │      → temperature=0.3, num_predict=2048                │
    │      → retry: max 2회, 2초 delay                        │
    │      → 마커 추출: [RESPONSE_NEEDED] / [NO_RESPONSE]     │
    │      → reasoning에 전체 추론 텍스트 보존                  │
    │                                                         │
    │  Step 4: _resolve_project()                             │
    │  ├── Ollama confidence >= 0.7 → Ollama project_id      │
    │  ├── Rule confidence >= 0.6 → Rule project_id          │
    │  ├── Ollama confidence >= 0.3 → Ollama project_id      │
    │  └── 모두 실패 → None                                   │
    │                                                         │
    │  Step 5: project_id = None?                             │
    │  └── YES → pending_match로 DB 저장 → 종료               │
    │                                                         │
    │  Step 6: needs_response = False?                        │
    │  └── YES → 종료 (분석만 기록)                            │
    │                                                         │
    │  Step 7: Claude Opus 초안 생성 (Tier 2)                  │
    │  ├── 프로젝트 컨텍스트 조합 (DB context_entries)          │
    │  ├── draft_prompt.txt에 ollama_reasoning 포함            │
    │  ├── claude -p --model opus subprocess                  │
    │  │   (timeout 120초, retry 1회/5초 delay)               │
    │  └── DraftStore.save()                                  │
    │      ├── data/drafts/{id}.md 파일 저장                  │
    │      ├── intelligence.db에 draft_responses INSERT       │
    │      └── Toast 알림                                     │
    │                                                         │
    │  Step 8: dedup.mark_processed()                         │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
```

### 3.2 2-Tier LLM Chain-of-Thought 패턴

```
┌───────────────────────────────────────────────────────────────┐
│  Tier 1: Ollama (qwen3:8b) - 자유 추론 엔진                   │
│                                                               │
│  입력:                                                        │
│    - 원본 메시지 텍스트 (max 12000자)                          │
│    - 등록된 프로젝트 목록 (ID, 키워드, 설명)                    │
│    - 규칙 매칭 힌트 (있는 경우)                                │
│                                                               │
│  처리:                                                        │
│    - thinking 모드 활성화 (temperature=0.3)                    │
│    - 5가지 분석 질문에 대해 자유 추론                           │
│      1. 맥락과 의도                                           │
│      2. 관련 프로젝트                                         │
│      3. 발신자 기대사항                                       │
│      4. 응답 필요 여부 + 적절한 톤                             │
│      5. 긴급성                                               │
│                                                               │
│  출력:                                                        │
│    - 전체 추론 텍스트 (reasoning 필드, max 3000자로 전달)       │
│    - 마지막 줄 결정 마커:                                      │
│      [RESPONSE_NEEDED] project_id=secretary confidence=0.85   │
│      또는                                                     │
│      [NO_RESPONSE] project_id=wsoptv confidence=0.90          │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     │ needs_response=true?
                     │
                     ▼
┌───────────────────────────────────────────────────────────────┐
│  Tier 2: Claude Opus 4.6 - 맥락 인지 대응 생성기               │
│                                                               │
│  입력:                                                        │
│    1. 프로젝트 컨텍스트 (DB context_entries, max 12000자)      │
│    2. Ollama 추론 전체 텍스트 (analysis.reasoning, max 3000자) │
│    3. 원본 메시지 + 발신자 정보 (max 2000자)                   │
│                                                               │
│  프롬프트 구조:                                                │
│    "당신은 프로젝트 {name}의 전문 비서입니다."                   │
│    + 프로젝트 컨텍스트                                        │
│    + "AI 분석관의 추론" (= Ollama reasoning)                   │
│    + 수신 메시지                                              │
│    + 응답 작성 지침 (5조항)                                    │
│                                                               │
│  출력:                                                        │
│    - 한국어 응답 초안 (전문적 + 맥락 인지)                      │
│    - DraftStore에 저장 → CLI로 approve/reject                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. 데이터 흐름 종합

```
[Slack Adapter]          [Gmail Adapter]
  5초 폴링                 60초 폴링
      │                       │
      └──────────┬────────────┘
                 │
                 ▼
        NormalizedMessage (불변)
                 │
    ┌────────────┴────────────┐
    │    MessagePipeline      │
    │                         │
    │  Stage 1: Priority      │ ──▶ EnrichedMessage.priority
    │  Stage 2: Actions       │ ──▶ EnrichedMessage.actions
    │  Stage 3: Storage       │ ──▶ [gateway.db] messages
    │  Stage 4: Toast         │ ──▶ [winotify] Windows
    │  Stage 5: Actions       │ ──▶ [tasks/] TODO 파일
    │  Stage 6: Intelligence  │
    └────────────┬────────────┘
                 │
    ┌────────────┴────────────────────────────────────────────────┐
    │        ProjectIntelligenceHandler                            │
    │                                                              │
    │  ┌─────────────┐    ┌───────────────┐                       │
    │  │ DedupFilter  │    │ContextMatcher │                       │
    │  │ LRU 1000     │    │ 3-tier 규칙   │                       │
    │  └──────┬───────┘    └──────┬────────┘                       │
    │         │                   │                                 │
    │    [중복?] ─YES─▶ 종료      │                                 │
    │         │                   │                                 │
    │         NO                  │                                 │
    │         │                   │                                 │
    │    ┌────┴───────────────────┴──────────┐                     │
    │    │                                    │                     │
    │    │  urgent + rule_match?              │                     │
    │    │  ├── YES → [FAST-TRACK]           │                     │
    │    │  │   AnalysisResult 직접 생성      │                     │
    │    │  │                                 │                     │
    │    │  └── NO → Ollama API              │                     │
    │    │      ┌─────────────────────────┐   │                     │
    │    │      │ qwen3:8b 자유 추론      │   │                     │
    │    │      │ temperature=0.3         │   │                     │
    │    │      │ num_predict=2048        │   │                     │
    │    │      │ retry: max 2 / 2s      │   │                     │
    │    │      │ rate: 10/min           │   │                     │
    │    │      └──────────┬──────────────┘   │                     │
    │    │                 │                   │                     │
    │    │      마커 추출:                      │                     │
    │    │      [RESPONSE_NEEDED] / [NO_RESPONSE]                   │
    │    │                 │                   │                     │
    │    └────────────────┬───────────────────┘                     │
    │                     │                                         │
    │    ┌────────────────┴────────────────────┐                    │
    │    │ _resolve_project()                   │                    │
    │    │ Ollama(0.7+) > Rule(0.6+) > Ollama(0.3+)               │
    │    └────────────────┬────────────────────┘                    │
    │                     │                                         │
    │         ┌───────────┼──────────────┐                          │
    │         │           │              │                          │
    │    [project=None]  [no_response]  [needs_response]            │
    │         │           │              │                          │
    │         ▼           ▼              ▼                          │
    │   pending_match   종료      Claude Opus 초안                   │
    │   DB 저장                  ┌────────────────────┐             │
    │                            │ claude -p --model   │             │
    │                            │ opus subprocess     │             │
    │                            │ timeout: 120s       │             │
    │                            │ retry: 1회/5s       │             │
    │                            │ rate: 5/min         │             │
    │                            └────────┬───────────┘             │
    │                                     │                         │
    │                              DraftStore.save()                │
    │                              ├── data/drafts/*.md             │
    │                              ├── intelligence.db              │
    │                              └── Toast 알림                   │
    │                                                               │
    └───────────────────────────────────────────────────────────────┘

[Reporter (미통합)]
    │
    ├── 긴급 알림 → Slack DM 즉시 전송
    ├── 초안 알림 → Slack DM 즉시 전송
    └── Digest → 매일 18:00 Slack DM 전송
```

---

## 5. 에러 처리 및 Fallback 경로

### 5.1 Fallback 체인

| 실패 지점 | Fallback | 영향 |
|-----------|----------|------|
| Adapter 수신 실패 | 로그 출력, 루프 계속 | 해당 채널만 |
| Pipeline 전체 실패 | `result.error`에 기록 | 단일 메시지만 |
| Toast 알림 실패 | 무시 (`except: pass`) | 없음 |
| Action Dispatch 실패 | 로그만, 파이프라인 계속 | 없음 |
| Intelligence 등록 실패 | ImportError → 무시 | 분석 없이 운영 |
| Ollama 비활성화 | `needs_response=False` | 초안 미생성 |
| Ollama 분석 실패 | `needs_response=False` | 초안 미생성 |
| 마커 미발견 | `needs_response=False`, confidence=0.0 | 초안 미생성 |
| project_id 미매칭 | `pending_match` DB 저장 | 수동 매칭 필요 |
| Claude CLI 미설치 | `_draft_writer=None` | `awaiting_draft` 상태 |
| Claude 초안 실패 | `awaiting_draft` 전환 | CLI 수동 생성 |
| Claude rate limit | RuntimeError → `awaiting_draft` | 대기 후 재시도 |

### 5.2 Rate Limiting

| 컴포넌트 | 제한 | 초과 시 동작 |
|---------|------|-------------|
| Pipeline Toast | 분당 10건 | 알림 생략 (대기 없음) |
| OllamaAnalyzer | 분당 10건 | asyncio.sleep 대기 |
| ClaudeCodeDraftWriter | 분당 5건 | RuntimeError 즉시 발생 |

### 5.3 Retry

| 컴포넌트 | max_retries | base_delay | backoff | 대상 에러 |
|---------|:-----------:|:----------:|:-------:|----------|
| Ollama | 2 | 2.0초 | 2.0x | httpx 에러 |
| Claude | 1 | 5.0초 | 2.0x | RuntimeError |

---

## 6. 미통합 지점 및 TODO

### 6.1 Reporter 통합 (Phase 5 잔여)

`server.py`의 `_register_intelligence_handler()`에 추가 필요:

```python
# Reporter 생성 및 주입
reporter_config = self.config.get("reporter", {})
if reporter_config.get("enabled", False):
    from scripts.reporter.reporter import SecretaryReporter
    reporter = SecretaryReporter(
        gateway_storage=self.storage,
        intel_storage=intel_storage,
        config=reporter_config,
    )
    await reporter.start()
    handler.set_reporter(reporter)
    self._reporter = reporter  # stop() 시 종료용
```

`gateway.json`에 `reporter` 섹션 추가 필요:

```json
"reporter": {
    "enabled": true,
    "digest_time": "18:00",
    "channels": {
        "slack_dm": {
            "enabled": true,
            "user_id": "<SLACK_USER_ID>"
        }
    }
}
```

### 6.2 PriorityQueue 워커 활성화

`_register_intelligence_handler()`에서 `handler.start_worker()` 호출 필요.
`stop()`에서 `handler.stop_worker()` 호출 필요.

### 6.3 IntelligenceStorage 종료

`stop()`에서 `intel_storage.close()` 호출 필요.
현재 WAL mode SQLite의 `-wal`/`-shm` 파일이 정리되지 않음.

---

## 7. 설정 구조 (gateway.json)

```json
{
    "enabled": true,
    "port": 8800,
    "data_dir": "C:\\claude\\secretary\\data",
    "channels": {
        "slack": {
            "enabled": true,
            "channels": ["C0985UXQN6Q"]
        },
        "gmail": {
            "enabled": false
        }
    },
    "pipeline": {
        "urgent_keywords": ["긴급", "urgent", "ASAP", ...],
        "action_keywords": ["해주세요", "부탁", ...]
    },
    "notifications": {
        "toast_enabled": true
    },
    "safety": {
        "auto_send_disabled": true,
        "rate_limit_per_minute": 10
    },
    "intelligence": {
        "enabled": true,
        "ollama": {
            "enabled": true,
            "model": "qwen3:8b",
            "endpoint": "http://localhost:11434",
            "timeout": 90
        },
        "claude_draft": {
            "enabled": true,
            "model": "opus",
            "timeout": 120
        }
    },
    "reporter": {
        "enabled": true,
        "digest_time": "18:00",
        "channels": {
            "slack_dm": {
                "enabled": true,
                "user_id": "<USER_ID>"
            }
        }
    }
}
```

---

## 8. CLI 인터페이스

| 명령 | 용도 |
|------|------|
| `python server.py start` | Gateway 시작 |
| `python server.py stop` | Gateway 중지 |
| `python server.py status` | 상태 확인 |
| `python server.py channels` | 채널 목록 |
| `python cli.py analyze` | 수동 메시지 분석 |
| `python cli.py pending` | 미매칭 메시지 조회 |
| `python cli.py drafts` | 초안 목록 조회 |
| `python cli.py drafts approve <id>` | 초안 승인 |
| `python cli.py drafts reject <id>` | 초안 거부 |
| `python cli.py stats` | 통계 조회 |
