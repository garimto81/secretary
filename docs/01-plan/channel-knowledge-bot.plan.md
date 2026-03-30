# Channel Knowledge Bot — Auto-Response System Plan

**Version**: 1.0.0
**Created**: 2026-02-18
**Status**: PLANNED
**Complexity Score**: 4/5
**Depends On**: slack-channel-mastery.plan.md (CM-K01~K06)

---

## 배경 (Background)

### 요청 내용

채널 전체 히스토리를 Sonnet이 1회 분석하여 "채널 전문가 컨텍스트"를 JSON으로 저장하고, 이후 수신되는 신규 메시지는 Qwen(Ollama)이 처리하되 복잡도/confidence 기준 미달 시 Sonnet으로 에스컬레이션하는 자동 응대 봇 시스템 구축. Slack + Gmail 양 채널 대응.

### 해결하려는 문제

현재 시스템의 한계:

| 문제 | 현황 | 목표 |
|------|------|------|
| **초기 채널 컨텍스트 없음** | ChannelMasteryAnalyzer(CM-K04)는 TF-IDF 키워드만 생성, Sonnet의 자연어 요약 없음 | Sonnet이 채널 전체를 읽고 전문가 프로파일 JSON 생성 |
| **Qwen 단독 처리 한계** | 복잡 질문, 기술 심층 분석은 Qwen confidence 낮음 | 임계값 기반 자동 Sonnet 에스컬레이션 |
| **응답에 채널 컨텍스트 미반영** | chatbot_respond()가 RAG 결과만 활용, 채널 전문가 프로파일 미주입 | 채널 컨텍스트 JSON을 system prompt에 주입 |
| **Gmail 스레드 컨텍스트 없음** | Gmail도 Qwen 단독 처리, 스레드 히스토리 미분석 | Gmail 스레드별 Sonnet 초기 분석 + Qwen 증분 처리 |

### 기존 작업과의 관계

```
slack-channel-mastery.plan.md (CM-K01~K06)
    └── 전체 히스토리 수집 + TF-IDF 전문가 컨텍스트 구축
        ↓ (확장)
channel-knowledge-bot.plan.md (BOT-K01~K06)
    └── Sonnet 자연어 분석 레이어 추가 + 에스컬레이션 라우터 + 자동 응대 통합

slack-chatbot-channel.plan.md (이미 구현 완료)
    └── _handle_chatbot_message() → _send_chatbot_reply() — 기반 인프라 활용
```

---

## 구현 범위 (Scope)

### 포함 항목

- `BOT-K01`: 초기 채널 분석기 (Sonnet) — ChannelMasteryAnalyzer 확장
- `BOT-K02`: 에스컬레이션 라우터 (Qwen→Sonnet) — EscalationRouter
- `BOT-K03`: 채널 컨텍스트 주입 — ProjectChannelContext
- `BOT-K04`: Gmail 초기 분석 + 에스컬레이션
- `BOT-K05`: 자동 응대 봇 통합 — AutoResponseBot
- `BOT-K06`: 기존 문서 업데이트 (slack-channel-mastery.plan.md 등)

### 제외 항목

- Slack 메시지 자동 전송 (기존 chatbot_reply 인프라 그대로 사용, 신규 전송 로직 불필요)
- 다중 채널 동시 지원 (현재 `C0985UXQN6Q` + Gmail inbox 한정)
- 외부 웹 검색 통합 (기존 _get_realtime_context() 그대로 활용)
- 에스컬레이션 히스토리 UI/대시보드
- Knowledge Store 스키마 변경

---

## 구현 범위 상세 (Scope Detail)

### BOT-K01: 초기 채널 분석기 (Sonnet) — ChannelMasteryAnalyzer 확장

**목적**: CM-K04 `ChannelMasteryAnalyzer`가 생성한 TF-IDF 결과를 입력으로 받아, Sonnet subprocess로 자연어 전문가 프로파일을 생성하고 `config/channel_contexts/{channel_id}.json`에 저장.

**신규 파일**: `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py`

```python
class ChannelSonnetProfiler:
    """Sonnet으로 채널 전문가 컨텍스트 JSON 생성 (1회성 초기 분석)"""

    async def build_profile(
        self,
        channel_id: str,
        mastery_context: dict,      # CM-K04 build_mastery_context() 결과
        channel_profile: ChannelProfile,  # CM-K03 ChannelProfile
        sample_messages: list,      # 최근 100건 메시지 샘플
    ) -> dict:
        """
        Returns (저장 경로: config/channel_contexts/{channel_id}.json):
        {
            "channel_id": "C0985UXQN6Q",
            "built_at": "2026-02-18T...",
            "channel_summary": "이 채널은 AI 비서 secretary 프로젝트의 ...",
            "communication_style": "기술적/비공식적/결정 중심",
            "key_topics": ["gateway 개선", "intelligence 2-tier", ...],
            "key_decisions": ["...", ...],
            "member_profiles": {
                "U040EUZ6JRY": {
                    "role_summary": "백엔드 개발 담당, 배포/릴리즈 주도",
                    "communication_style": "간결/기술적"
                }
            },
            "response_guidelines": "응답 시 기술 용어 사용 가능, 한국어 선호, ...",
            "escalation_hints": ["복잡한 아키텍처 질문", "버그 원인 분석", ...]
        }
        """
```

Sonnet 호출 방식: 기존 `ClaudeCodeDraftWriter`의 subprocess 패턴 동일하게 적용 (`claude -p prompt --output-format text`).

프롬프트 파일 경로: `C:\claude\secretary\scripts\intelligence\prompts\channel_profile_prompt.txt`

저장 경로: `C:\claude\secretary\config\channel_contexts\{channel_id}.json`

**Acceptance Criteria**:
- [ ] `build_profile()` 실행 후 `config/channel_contexts/C0985UXQN6Q.json` 파일 생성
- [ ] JSON에 `channel_summary`, `key_topics`, `response_guidelines` 필드 포함
- [ ] 이미 파일이 존재하면 `--force` 없이 재생성 스킵 (stale 방지)
- [ ] Sonnet 호출 실패 시 mastery_context 기반 최소 JSON 저장 (fallback)
- [ ] 단독 실행 지원: `python -m scripts.knowledge.channel_sonnet_profiler C0985UXQN6Q`

---

### BOT-K02: 에스컬레이션 라우터 (Qwen→Sonnet) — EscalationRouter

**목적**: Qwen 분석 결과(`AnalysisResult`)를 평가하여 Sonnet 에스컬레이션 여부를 결정하는 라우터. `handler._handle_chatbot_message()` 내부에 주입.

**신규 파일**: `C:\claude\secretary\scripts\intelligence\response\escalation_router.py`

```python
@dataclass
class EscalationDecision:
    should_escalate: bool
    reason: str                # "low_confidence", "high_complexity", "technical_deep_dive", "long_input"
    confidence_score: float
    complexity_score: float    # 추정값 (0.0~1.0)

class EscalationRouter:
    """Qwen 결과 기반 Sonnet 에스컬레이션 판단"""

    # 에스컬레이션 임계값 (gateway.json escalation 섹션에서 주입 가능)
    CONFIDENCE_THRESHOLD = 0.6    # Qwen confidence < 0.6 → 에스컬레이션
    COMPLEXITY_THRESHOLD = 0.7    # complexity_score > 0.7 → 에스컬레이션
    TOKEN_COUNT_THRESHOLD = 500   # 입력 토큰 추정 > 500 → 에스컬레이션

    ESCALATION_INTENTS = {
        "technical_deep_dive",   # Qwen이 분류한 intent가 기술 심층 분석
        "architecture_review",
        "debug_investigation",
    }

    def decide(
        self,
        analysis: AnalysisResult,
        original_text: str,
    ) -> EscalationDecision:
        """
        판단 기준 (OR 조건 — 하나라도 해당 시 에스컬레이션):
        1. analysis.confidence < CONFIDENCE_THRESHOLD (0.6)
        2. complexity_score > COMPLEXITY_THRESHOLD (0.7)
           - complexity_score 추정: 코드블록 포함 여부, 문장 길이, 기술 용어 밀도
        3. analysis.intent in ESCALATION_INTENTS
        4. len(original_text.split()) > TOKEN_COUNT_THRESHOLD (500 단어 추정)
        """
```

complexity_score 추정 로직 (정적 분석, LLM 비호출):
- 코드 블록(` ``` `) 포함: +0.3
- 500자 이상: +0.2
- 기술 용어 밀도 (도메인 키워드 목록과 교집합 / 전체 단어): +0~0.3
- `?` 또는 `？`(전각) 합산 3개 이상: +0.1 (`text.count("?") + text.count("\uff1f") >= 3`)
- 영어 단어 비율 > 30%: +0.1

gateway.json에 `escalation` 섹션 추가:
```json
"escalation": {
    "confidence_threshold": 0.6,
    "complexity_threshold": 0.7,
    "token_count_threshold": 500
}
```

**Acceptance Criteria**:
- [ ] `decide()` — confidence 0.4 입력 시 `should_escalate=True, reason="low_confidence"` 반환
- [ ] `decide()` — 코드 블록 포함 500자+ 메시지 → `should_escalate=True, reason="high_complexity"` 반환
- [ ] `decide()` — confidence 0.8, 단순 인사 메시지 → `should_escalate=False` 반환
- [ ] 임계값이 gateway.json에서 주입 가능 (하드코딩 없음)
- [ ] 순수 함수 (외부 의존 없음, 단위 테스트 용이)
- [ ] 전각 물음표(？) 3개 이상 메시지에서 complexity_score가 0.1 증가함을 확인

---

### BOT-K03: 채널 컨텍스트 주입 — ProjectChannelContext

**목적**: `config/channel_contexts/{channel_id}.json`을 로드하여 chatbot 응답 생성 시 system prompt로 주입. `OllamaAnalyzer.chatbot_respond()` 및 `ClaudeCodeDraftWriter.chatbot_respond()`에 `channel_context` 파라미터 추가.

**수정 파일**: `C:\claude\secretary\scripts\intelligence\response\analyzer.py`

```python
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    context: str = "",
    channel_context: str = "",   # BOT-K03 신규 파라미터
) -> Optional[str]:
    """
    channel_context가 있으면 system prompt 앞에 주입:
    "당신은 {channel_id} 채널 전문가입니다.\n{channel_context}\n\n당신은 사용자의 질문에..."
    """
```

**수정 파일**: `C:\claude\secretary\scripts\intelligence\response\draft_writer.py`

```python
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    context: str = "",
    channel_context: str = "",   # BOT-K03 신규 파라미터
) -> Optional[str]:
```

**수정 파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py`

`_handle_chatbot_message()` 내부에 채널 컨텍스트 로드 로직 추가:

```python
async def _load_channel_context(self, channel_id: str) -> str:
    """config/channel_contexts/{channel_id}.json 로드 → 요약 문자열 반환"""
    import json as _json
    ctx_path = Path(r"C:\claude\secretary\config\channel_contexts") / f"{channel_id}.json"
    if not ctx_path.exists():
        return ""
    try:
        data = _json.loads(ctx_path.read_text(encoding="utf-8"))
        parts = []
        if data.get("channel_summary"):
            parts.append(f"채널 개요: {data['channel_summary']}")
        if data.get("key_topics"):
            parts.append(f"주요 토픽: {', '.join(data['key_topics'][:8])}")
        if data.get("response_guidelines"):
            parts.append(f"응답 지침: {data['response_guidelines']}")
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"채널 컨텍스트 로드 실패 {channel_id}: {e}")
        return ""
```

**신규 경로**: `C:\claude\secretary\config\channel_contexts\` (디렉토리, git 추적)

**Acceptance Criteria**:
- [ ] `channel_contexts/C0985UXQN6Q.json` 존재 시 chatbot_respond에 컨텍스트 주입
- [ ] JSON 없거나 읽기 실패 시 빈 문자열로 graceful fallback (파이프라인 중단 없음)
- [ ] Sonnet escalation 시에도 동일 channel_context 주입
- [ ] `channel_summary` + `key_topics` + `response_guidelines` 3개 필드만 추출 (토큰 절약)

---

### BOT-K04: Gmail 초기 분석 + 에스컬레이션

**목적**: Gmail 스레드별 Sonnet 초기 분석 컨텍스트(`config/gmail_contexts/{thread_id}.json`)를 생성하고, 신규 Gmail 메시지 처리 시 EscalationRouter로 Qwen/Sonnet 라우팅.

**신규 파일**: `C:\claude\secretary\scripts\knowledge\gmail_thread_profiler.py`

```python
class GmailThreadProfiler:
    """Gmail 스레드 Sonnet 초기 분석 및 컨텍스트 저장"""

    CONTEXT_DIR = Path(r"C:\claude\secretary\config\gmail_contexts")

    async def build_thread_context(
        self,
        thread_id: str,
        messages: list,   # KnowledgeDocument list (bootstrap.learn_gmail 결과)
    ) -> dict:
        """
        Returns (저장 경로: config/gmail_contexts/{thread_id}.json):
        {
            "thread_id": "...",
            "built_at": "...",
            "thread_summary": "스레드 주제 + 현재 상태",
            "participants": ["sender1@...", "sender2@..."],
            "pending_action": "상대방이 요청한 액션 또는 null",
            "tone": "formal/informal/urgent",
            "response_guidelines": "이 스레드에서 응답 시 고려사항"
        }
        """
```

**NormalizedMessage thread_id 처리 방안**:

`models.py` 확인 결과 `NormalizedMessage`에 `thread_id` 전용 필드가 없고 `reply_to_id: Optional[str] = None`만 존재함. 아래 두 방안 중 하나를 구현 시 선택:

- **방안 A (권장)**: `NormalizedMessage`에 `thread_id: Optional[str] = None` 필드 추가 (`models.py` 수정). GmailAdapter가 Gmail API의 `threadId`를 이 필드에 매핑.
- **방안 B**: `reply_to_id`를 Gmail thread_id 용도로 재활용. GmailAdapter가 `message.reply_to_id = thread_data["threadId"]`로 설정. 필드 의미 혼용 가능성 있으므로 주석 필수.

기본 구현은 방안 A 채택 (명확성 우선). `to_dict()`에 `thread_id` 직렬화 추가 필요.

**Gmail 에스컬레이션 연동**:

`handler._process_message()` 내부에서 `source_channel == "gmail"` 이고 `needs_response=True`일 때 EscalationRouter를 적용:
- 에스컬레이션 미해당: 기존 ClaudeCodeDraftWriter 초안 작성 (현재 동작 유지)
- 에스컬레이션 해당 + thread_id 있음: `gmail_contexts/{thread_id}.json` 주입하여 Sonnet 초안 작성

수정 파일: `C:\claude\secretary\scripts\intelligence\response\handler.py`의 `_generate_draft()` 메서드

**Acceptance Criteria**:
- [ ] `config/gmail_contexts/` 디렉토리에 스레드별 JSON 저장
- [ ] `_generate_draft()` 내부에서 EscalationRouter 결과에 따라 컨텍스트 주입 여부 결정
- [ ] thread_context 없으면 기존 초안 생성 로직 그대로 실행 (backward-compatible)
- [ ] `GmailThreadProfiler.build_thread_context()` 단독 실행 지원
- [ ] GmailAdapter가 thread_id를 NormalizedMessage에 올바르게 매핑함을 확인
- [ ] `_generate_draft()` 내 Gmail 에스컬레이션 분기는 `source_channel == "gmail"` 조건으로 guard되어 Slack 메시지에는 실행되지 않음

---

### BOT-K05: 자동 응대 봇 통합 — AutoResponseBot

**목적**: BOT-K01~K04를 통합하여 chatbot 메시지 처리 흐름을 완성. `handler._handle_chatbot_message()`를 확장하여 EscalationRouter + 채널 컨텍스트 주입 + Sonnet 에스컬레이션 분기를 통합.

**수정 파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py`

```
_handle_chatbot_message(message, source_channel)
    │
    ├─ 1. _load_channel_context(channel_id) → channel_context
    │
    ├─ 2. Qwen 응답 생성:
    │      _analyzer.chatbot_respond(text, sender_name, context, channel_context)
    │      → qwen_response
    │
    ├─ 3. EscalationRouter.decide(qwen_analysis, original_text)
    │      │
    │      ├─ should_escalate=False → qwen_response 전송
    │      │
    │      └─ should_escalate=True
    │             ├─ _draft_writer.chatbot_respond(text, sender_name, context, channel_context)
    │             │    → sonnet_response
    │             └─ sonnet_response 전송 (실패 시 qwen_response fallback)
    │
    └─ 4. _send_chatbot_reply(channel_id, response, thread_ts)
```

**OllamaAnalyzer 변경**: `chatbot_respond()`가 에스컬레이션 판단에 필요한 `AnalysisResult` 스타일 메타데이터를 반환해야 함. 현재 `str`만 반환하므로 아래 중 하나 선택:

옵션 A: `chatbot_respond()`를 `(response_text, analysis_meta)` 튜플 반환으로 변경
옵션 B: 에스컬레이션을 위한 별도 분석 호출 (`analyze()` 재활용)

**권장**: 옵션 B — 기존 `chatbot_respond()` 시그니처 유지, 에스컬레이션 판단은 `analyze()` 결과 활용 (중복 Ollama 호출이지만 단순성 우선).

**Acceptance Criteria**:
- [ ] chatbot 메시지 수신 시 항상 Qwen 먼저 처리 후 에스컬레이션 판단
- [ ] 에스컬레이션 발생 시 로그: `[Chatbot] Escalating to Sonnet: reason={reason}`
- [ ] Sonnet 응답 실패 시 Qwen 응답으로 fallback
- [ ] channel_context 주입 성공 시 로그: `[Chatbot] Channel context injected: {len} chars`
- [ ] 전체 처리 시간 로그: `[Chatbot] Processed in {ms}ms (qwen/sonnet)`

---

### BOT-K06: 기존 문서 업데이트

**목적**: 세 가지 문서 동기화 — (1) CM-K 연계 관계 명확화, (2) CLAUDE.md 파이프라인 Stage 현행화, (3) CLAUDE.md Intelligence Tier 2 모델명 수정.

#### 1. `slack-channel-mastery.plan.md` — BOT-K 연계 주석

**수정 파일**: `C:\claude\secretary\docs\01-plan\slack-channel-mastery.plan.md`

추가 내용:
- CM-K04 Acceptance Criteria에 "BOT-K01에서 Sonnet 분석 레이어를 추가로 적용함" 주석
- CM-K05 Acceptance Criteria에 "채널 컨텍스트 주입은 BOT-K03에서 확장함" 주석
- "참고 문서" 섹션에 channel-knowledge-bot.plan.md 링크 추가

#### 2. `CLAUDE.md` — 파이프라인 Stage 현행화

**수정 파일**: `C:\claude\secretary\CLAUDE.md`

**현황**: `아키텍처 > 전체 데이터 흐름` 섹션의 파이프라인 설명이 Stage 4 "Toast 알림"을 포함하고 있으나, 코드에서 완전 제거됨.

변경 전:
```
├─ Stage 1-4: 우선순위 분석, 액션 탐지, DB 저장, Toast 알림
├─ Stage 5: ActionDispatcher → ...
└─ Stage 6: ProjectIntelligenceHandler
```

변경 후:
```
├─ Stage 1-3: 우선순위 분석, 액션 탐지, DB 저장
├─ Stage 5: ActionDispatcher → ...
└─ Stage 6: ProjectIntelligenceHandler
```

또한 `### 2. Gateway` 섹션의 `MessagePipeline (pipeline.py) — 6단계 처리` 설명에서 Stage 4 언급 제거:
```
│   ├── Stage 1-3: Priority, Action Detection, Storage
│   ├── Stage 5: ActionDispatcher (action_dispatcher.py)
│   └── Stage 6: Custom Handlers (Intelligence)
```

#### 3. `CLAUDE.md` — Intelligence Tier 2 모델명 수정

**현황**: `### 3. Intelligence` 섹션에서 Tier 2를 "Claude Opus"로 표기하고 있으나 실제는 Claude Sonnet으로 변경됨.

변경 전 (모듈 docstring 및 CLAUDE.md):
```
- Tier 2 (Claude Opus): needs_response=true일 때만 초안 작성
```

변경 후:
```
- Tier 2 (Claude Sonnet): needs_response=true일 때만 초안 작성
```

적용 위치:
- `C:\claude\secretary\CLAUDE.md` — "Intelligence (2-Tier LLM 분석)" 섹션 설명
- `C:\claude\secretary\CLAUDE.md` — "전체 데이터 흐름" 다이어그램 주석

**Acceptance Criteria**:
- [ ] slack-channel-mastery.plan.md에 BOT-K 계획과의 관계 명시
- [ ] 두 계획의 중복 구현 없음 — CM-K는 데이터 수집/TF-IDF, BOT-K는 LLM 분석/라우팅으로 역할 분리
- [ ] CLAUDE.md 파이프라인 설명에 Stage 4 (Toast 알림) 언급 없음
- [ ] CLAUDE.md Intelligence 섹션에서 "Opus" 대신 "Sonnet" 표기
- [ ] CLAUDE.md 변경 후 실제 코드(`pipeline.py`, `handler.py`, `gateway.json`)와 불일치 없음

---

## 영향 파일 (Impacted Files)

### 수정 예정 파일

| 파일 | 변경 내용 | 관련 태스크 |
|------|----------|------------|
| `C:\claude\secretary\scripts\intelligence\response\handler.py` | `_handle_chatbot_message()` EscalationRouter + 채널 컨텍스트 주입 통합, `_load_channel_context()` 추가, `_generate_draft()` Gmail 에스컬레이션 분기 추가 (`source_channel == 'gmail'` 가드 적용 — Slack 메시지에 실행 금지) | BOT-K03, K04, K05 |
| `C:\claude\secretary\scripts\gateway\models.py` | `NormalizedMessage`에 `thread_id: Optional[str] = None` 필드 추가, `to_dict()` 직렬화 포함 (Gmail thread_id 매핑 명시) | BOT-K04 |
| `C:\claude\secretary\scripts\intelligence\response\analyzer.py` | `chatbot_respond()` — `channel_context` 파라미터 추가 | BOT-K03 |
| `C:\claude\secretary\scripts\intelligence\response\draft_writer.py` | `chatbot_respond()` — `channel_context` 파라미터 추가 | BOT-K03 |
| `C:\claude\secretary\config\gateway.json` | `intelligence.escalation` 섹션 추가 | BOT-K02 |
| `C:\claude\secretary\docs\01-plan\slack-channel-mastery.plan.md` | BOT-K 연계 주석 추가 | BOT-K06 |
| `C:\claude\secretary\CLAUDE.md` | 파이프라인 Stage 4 제거 반영, Tier 2 모델명 Opus→Sonnet 수정 | BOT-K06 |

### 신규 생성 파일

| 파일 | 목적 | 관련 태스크 |
|------|------|------------|
| `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py` | Sonnet으로 채널 전문가 프로파일 생성 | BOT-K01 |
| `C:\claude\secretary\scripts\intelligence\response\escalation_router.py` | Qwen→Sonnet 에스컬레이션 판단 | BOT-K02 |
| `C:\claude\secretary\scripts\knowledge\gmail_thread_profiler.py` | Gmail 스레드 Sonnet 분석 | BOT-K04 |
| `C:\claude\secretary\scripts\intelligence\prompts\channel_profile_prompt.txt` | Sonnet 채널 프로파일 생성 프롬프트 | BOT-K01 |
| `C:\claude\secretary\config\channel_contexts\` | 채널별 전문가 컨텍스트 JSON 저장 디렉토리 | BOT-K01, K03 |
| `C:\claude\secretary\config\gmail_contexts\` | Gmail 스레드 컨텍스트 JSON 저장 디렉토리 | BOT-K04 |
| `C:\claude\secretary\tests\intelligence\test_escalation_router.py` | EscalationRouter 단위 테스트 | BOT-K02 |
| `C:\claude\secretary\tests\knowledge\test_channel_sonnet_profiler.py` | ChannelSonnetProfiler 단위/통합 테스트 | BOT-K01 |

---

## 에스컬레이션 판단 기준 (Escalation Decision Criteria)

EscalationRouter는 OR 조건으로 판단한다. 하나라도 해당 시 Sonnet 에스컬레이션.

| 조건 | 임계값 | 이유 |
|------|--------|------|
| `analysis.confidence < 0.6` | 0.6 미만 | Qwen이 응답 품질을 스스로 낮게 평가 |
| `complexity_score > 0.7` | 0.7 초과 | 코드 블록, 긴 입력, 기술 용어 고밀도 |
| `intent == "technical_deep_dive"` | 정확 일치 | 아키텍처/디버깅 질문 감지 |
| `len(original_text.split()) > 500` | 500 단어 초과 | 긴 입력은 Qwen context 한계 도달 가능성 |

complexity_score 계산 (정적 분석):

```
score = 0.0
if "```" in text: score += 0.3
if len(text) > 500: score += 0.2
tech_terms = {"api", "gateway", "pipeline", "async", "sqlite", "llm", ...}
term_density = len(words ∩ tech_terms) / max(len(words), 1)
score += min(term_density * 3.0, 0.3)
if text.count("?") + text.count("\uff1f") >= 3: score += 0.1
if english_ratio > 0.3: score += 0.1
score = min(score, 1.0)
```

---

## 채널 컨텍스트 저장 구조 (Context Storage Structure)

### Slack 채널 컨텍스트

저장 경로: `C:\claude\secretary\config\channel_contexts\{channel_id}.json`

```json
{
    "channel_id": "C0985UXQN6Q",
    "built_at": "2026-02-18T10:00:00",
    "source_version": "sonnet-20250219",
    "channel_summary": "secretary AI 비서 프로젝트 주 개발 채널. Gateway 파이프라인, Intelligence 2-tier LLM 개선 논의가 주를 이룸.",
    "communication_style": "기술적/한국어 혼용/결정 중심",
    "key_topics": ["gateway 개발", "intelligence 개선", "knowledge store", "배포 일정"],
    "key_decisions": [
        "2026-02-15: Intelligence를 2-Tier LLM(Qwen+Sonnet)으로 재설계",
        "2026-02-10: Knowledge Store FTS5 기반으로 확정"
    ],
    "member_profiles": {
        "U040EUZ6JRY": {
            "role_summary": "프로젝트 오너, 주요 의사결정",
            "communication_style": "간결/기술적"
        }
    },
    "response_guidelines": "기술 용어 그대로 사용 가능. 한국어 우선. 코드 예시 환영. 과도한 설명 지양.",
    "escalation_hints": ["아키텍처 설계 질문", "버그 원인 분석", "성능 최적화"]
}
```

### Gmail 스레드 컨텍스트

저장 경로: `C:\claude\secretary\config\gmail_contexts\{thread_id}.json`

```json
{
    "thread_id": "...",
    "built_at": "...",
    "thread_summary": "클라이언트가 API 연동 지원 요청. 현재 인증 이슈 해결 대기 중.",
    "participants": ["client@example.com", "aiden@company.com"],
    "pending_action": "OAuth 토큰 갱신 방법 안내 필요",
    "tone": "formal",
    "response_guidelines": "공식 어조 유지. 기술 용어는 영어로. 답변 끝에 다음 단계 명시."
}
```

---

## 위험 요소 (Risks)

| 위험 | 영향 | 가능성 | 완화 방안 |
|------|------|--------|----------|
| **Sonnet 호출 비용 증가** | 에스컬레이션 빈번 시 Claude API 비용 급증 | MEDIUM | 에스컬레이션 임계값을 gateway.json에서 조정 가능하게 설계. 초기 보수적 설정(confidence_threshold=0.6). 일별 에스컬레이션 횟수 로그 추적. |
| **이중 Ollama 호출** | BOT-K05 옵션 B 채택 시 chatbot_respond + analyze() 중복 호출 → 지연 2배 | MEDIUM | 에스컬레이션 판단을 chatbot_respond() 이전에 analyze() 1회로 통합하는 리팩토링 검토. 단, 이는 별도 태스크로 분리. |
| **채널 컨텍스트 파일 stale** | JSON이 오래되면 채널 변화 미반영 응답 생성 | LOW | `built_at` 필드 기준 30일 초과 시 재생성 경고 로그 출력. CLI로 수동 재생성 가능. |
| **Gmail thread_id 불일치** | Gmail 수신 시 thread_id가 없거나 context JSON과 불일치 | MEDIUM | `gmail_contexts/` 로드 실패 시 context 없이 기존 방식 실행 (graceful degradation 필수). |
| **config/ 디렉토리 git 추적** | channel_contexts/*.json이 민감 정보 포함 가능성 | LOW | `.gitignore`에 `config/channel_contexts/`, `config/gmail_contexts/` 추가 여부 사용자와 확인 필요. |
| **EscalationRouter 오분류** | complexity_score가 단순 메시지를 과도하게 에스컬레이션 | MEDIUM | 임계값 조정 용이한 구조로 설계. 에스컬레이션 로그를 7일간 모니터링 후 임계값 조정 권고. |

### Edge Case

1. **채널 컨텍스트 빌드 전 chatbot 메시지 수신**: `config/channel_contexts/C0985UXQN6Q.json` 없는 상태에서 메시지 수신. `_load_channel_context()` 빈 문자열 반환 → 기존 chatbot 동작 유지. 비기능 저하이므로 에러 처리 불필요.

2. **Sonnet 에스컬레이션 후 타임아웃**: Sonnet subprocess 60s 타임아웃 초과 시 Qwen 응답을 fallback으로 사용. 이미 생성된 qwen_response를 메모리에 보유하고 있어야 함 — `_handle_chatbot_message()`가 qwen_response 변수를 에스컬레이션 전에 저장.

3. **Qwen 분석과 에스컬레이션 판단의 `AnalysisResult` 재활용**: BOT-K05 옵션 B에서 `analyze()` 호출이 chatbot 메시지에 project_id 분류를 시도하여 불필요한 프로젝트 매칭 발생. `analyze()`의 응답에서 `confidence`와 `intent`만 추출하고 `project_id`는 무시하도록 처리.

4. **Gmail contexts 디렉토리 미생성**: `GmailThreadProfiler.build_thread_context()` 최초 실행 시 `config/gmail_contexts/` 없으면 FileNotFoundError. `Path.mkdir(parents=True, exist_ok=True)` 선행 필수.

---

## 구현 순서 (Implementation Order)

```
BOT-K02 (EscalationRouter)                ← 독립 모듈, 외부 의존 없음 → 먼저 구현
    │
    ▼
BOT-K01 (ChannelSonnetProfiler)            ← CM-K04 완료 후 (ChannelMasteryAnalyzer 필요)
    │
    ▼
BOT-K03 (채널 컨텍스트 주입)               ← BOT-K01 완료 후 (channel_contexts/*.json 필요)
    │
BOT-K04 (Gmail 분석 + 에스컬레이션)        ← BOT-K02 완료 후 병렬 구현 가능
    │
    ▼
BOT-K05 (AutoResponseBot 통합)             ← BOT-K02, K03, K04 모두 완료 후
    │
    ▼
BOT-K06 (문서 업데이트)                    ← BOT-K05 완료 후
```

**병렬 구현 가능 그룹**:
- Group A: BOT-K02 (EscalationRouter) — 완전 독립
- Group B: BOT-K01 (ChannelSonnetProfiler) + BOT-K04 (GmailThreadProfiler) — 각각 독립 파일
- Group C: BOT-K03 (컨텍스트 주입), BOT-K05 (통합), BOT-K06 (문서) — 순차 진행

**선행 조건**: slack-channel-mastery.plan.md의 CM-K04 (`ChannelMasteryAnalyzer`) 구현 완료 후 BOT-K01 진행 가능.

---

## 커밋 전략 (Commit Strategy)

| 순서 | Conventional Commit 메시지 | 포함 파일 |
|------|--------------------------|----------|
| 1 | `feat(intelligence): add EscalationRouter for Qwen→Sonnet escalation` | `escalation_router.py`, `tests/intelligence/test_escalation_router.py` |
| 2 | `feat(intelligence): add gateway.json escalation config section` | `config/gateway.json` |
| 3 | `feat(knowledge): add ChannelSonnetProfiler for Sonnet channel analysis` | `channel_sonnet_profiler.py`, `prompts/channel_profile_prompt.txt` |
| 4 | `feat(intelligence): inject channel context into chatbot_respond` | `analyzer.py`, `draft_writer.py`, `handler.py` (BOT-K03) |
| 5 | `feat(knowledge): add GmailThreadProfiler for thread context building` | `gmail_thread_profiler.py` |
| 6 | `feat(intelligence): integrate escalation router and channel context in AutoResponseBot` | `handler.py` (BOT-K05) |
| 7 | `test(knowledge): add ChannelSonnetProfiler unit tests` | `tests/knowledge/test_channel_sonnet_profiler.py` |
| 8 | `docs: sync CLAUDE.md pipeline stages and intelligence tier model name` | `CLAUDE.md` |
| 9 | `docs: link channel-knowledge-bot plan to channel-mastery plan` | `docs/01-plan/slack-channel-mastery.plan.md` |

---

## 참고 문서

- **기반 chatbot 구현**: `C:\claude\secretary\scripts\intelligence\response\handler.py` (line 395-568, `_handle_chatbot_message`, `_send_chatbot_reply`)
- **Qwen 분석기**: `C:\claude\secretary\scripts\intelligence\response\analyzer.py` (line 50~)
- **Claude 초안 생성기**: `C:\claude\secretary\scripts\intelligence\response\draft_writer.py`
- **CM-K04 MasteryAnalyzer**: `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` (BOT-K01 입력으로 활용)
- **채널 컨텍스트 관련 계획**: `C:\claude\secretary\docs\01-plan\slack-channel-mastery.plan.md` (CM-K03~K05)
- **Chatbot 기반 계획**: `C:\claude\secretary\docs\01-plan\slack-chatbot-channel.plan.md` (이미 구현 완료)
- **gateway.json 현재 구조**: `C:\claude\secretary\config\gateway.json`
