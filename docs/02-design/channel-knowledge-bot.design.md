# Channel Knowledge Bot — Design Document

**Version**: 1.0.0
**Based on Plan**: channel-knowledge-bot.plan.md
**Status**: DESIGN
**Created**: 2026-02-18

---

## 1. 아키텍처 개요 (Architecture Overview)

### 1.1 전체 데이터 흐름

```
[초기 분석 흐름 — 1회성]
KnowledgeBootstrap.learn_slack()
    └── ChannelMasteryAnalyzer.build_mastery_context()   ← CM-K04 (기존)
            └── ChannelSonnetProfiler.build_profile()    ← BOT-K01 (신규)
                    └── config/channel_contexts/{channel_id}.json

KnowledgeBootstrap.learn_gmail()
    └── GmailThreadProfiler.build_thread_context()       ← BOT-K04 (신규)
            └── config/gmail_contexts/{thread_id}.json

[실시간 처리 흐름 — 메시지 수신마다]
Gateway (server.py)
    └── MessagePipeline (pipeline.py) — Stage 1-3: Priority, ActionDetect, Storage
            └── Stage 5: ActionDispatcher
                    └── Stage 6: ProjectIntelligenceHandler._handle_chatbot_message()
                            ├── _load_channel_context(channel_id) → channel_context
                            ├── OllamaAnalyzer.analyze()           → AnalysisResult (에스컬레이션 판단용)
                            ├── OllamaAnalyzer.chatbot_respond()   → qwen_response
                            ├── EscalationRouter.decide()          ← BOT-K02 (신규)
                            │       ├── should_escalate=False → qwen_response 전송
                            │       └── should_escalate=True
                            │               └── ClaudeCodeDraftWriter.chatbot_respond(channel_context=...)
                            │                       → sonnet_response (실패 시 qwen_response fallback)
                            └── _send_chatbot_reply(channel_id, response, thread_ts)

[채널 컨텍스트 주입 흐름]
handler._load_channel_context(channel_id)
    ├── config/channel_contexts/{channel_id}.json 존재 → 요약 문자열 반환
    │       fields: channel_summary + key_topics + response_guidelines
    └── 파일 없음 / 읽기 실패 → "" (graceful fallback, 파이프라인 중단 없음)

OllamaAnalyzer.chatbot_respond(text, sender_name, context, channel_context="")
    └── channel_context → system_prompt 앞에 주입
ClaudeCodeDraftWriter.chatbot_respond(text, sender_name, context, channel_context="")
    └── channel_context → prompt 앞에 주입
```

### 1.2 컴포넌트 의존 관계

```
config/channel_contexts/*.json ←── ChannelSonnetProfiler (BOT-K01)
config/gmail_contexts/*.json   ←── GmailThreadProfiler (BOT-K04)
         │
         ▼
handler._load_channel_context()      ← BOT-K03
         │
         ├──► OllamaAnalyzer.chatbot_respond(channel_context=...)   ← BOT-K03
         └──► ClaudeCodeDraftWriter.chatbot_respond(channel_context=...)   ← BOT-K03

EscalationRouter.decide() ←── BOT-K02
         ├── 입력: AnalysisResult (OllamaAnalyzer.analyze() 결과)
         └── 출력: EscalationDecision (should_escalate, reason, scores)

ProjectIntelligenceHandler._handle_chatbot_message()   ← BOT-K05
    통합: _load_channel_context + EscalationRouter + chatbot_respond
```

---

## 2. 컴포넌트 설계 (Component Design)

### 2.1 ChannelSonnetProfiler (BOT-K01)

**파일**: `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py`

#### 클래스 구조

```python
class ChannelSonnetProfiler:
    """Sonnet subprocess로 채널 전문가 컨텍스트 JSON 생성 (1회성 초기 분석)"""

    CONTEXT_DIR = Path(r"C:\claude\secretary\config\channel_contexts")
    PROMPT_PATH = Path(r"C:\claude\secretary\scripts\intelligence\prompts\channel_profile_prompt.txt")
    SONNET_TIMEOUT = 120  # seconds

    def __init__(self):
        self.claude_path: str  # shutil.which("claude")

    async def build_profile(
        self,
        channel_id: str,
        mastery_context: dict,       # CM-K04 build_mastery_context() 결과
        channel_profile: dict,       # CM-K03 ChannelProfile (dict 직렬화)
        sample_messages: list,       # 최근 100건 메시지 (dict 목록)
        force: bool = False,         # True면 기존 파일 덮어쓰기
    ) -> dict:
        """채널 전문가 프로파일 생성 및 저장"""

    def _load_profile(self, channel_id: str) -> Optional[dict]:
        """기존 프로파일 로드. 없으면 None."""

    def _save_profile(self, channel_id: str, profile: dict) -> Path:
        """config/channel_contexts/{channel_id}.json 저장"""

    def _build_prompt(
        self,
        mastery_context: dict,
        channel_profile: dict,
        sample_messages: list,
    ) -> str:
        """Sonnet 호출용 프롬프트 생성"""

    async def _call_sonnet(self, prompt: str) -> str:
        """claude -p subprocess 실행 → 텍스트 반환"""

    def _parse_sonnet_output(self, output: str, channel_id: str) -> dict:
        """Sonnet 출력 JSON 파싱. 실패 시 mastery_context 기반 fallback dict 반환"""

    def _fallback_profile(
        self,
        channel_id: str,
        mastery_context: dict,
    ) -> dict:
        """Sonnet 호출 실패 시 최소 JSON 생성"""
```

#### Sonnet subprocess 호출 방식

`ClaudeCodeDraftWriter._run_claude_async()` 패턴을 동일하게 적용:

```python
process = await asyncio.create_subprocess_exec(
    self.claude_path, "-p", "--model", "sonnet", prompt,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await asyncio.wait_for(
    process.communicate(),
    timeout=self.SONNET_TIMEOUT,
)
```

#### 출력 JSON 스키마 (channel_contexts/{channel_id}.json)

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

#### 단독 실행 지원

```bash
python -m scripts.knowledge.channel_sonnet_profiler C0985UXQN6Q [--force]
```

#### stale 방지 로직

```
build_profile(force=False)
    ├── _load_profile() → 기존 파일 존재 → return 기존 dict (스킵)
    └── 파일 없음 → Sonnet 호출 → 저장 → return 신규 dict
```

`--force` 플래그 또는 `force=True` 파라미터 시에만 재생성.

---

### 2.2 EscalationRouter (BOT-K02)

**파일**: `C:\claude\secretary\scripts\intelligence\response\escalation_router.py`

#### EscalationDecision dataclass

```python
@dataclass
class EscalationDecision:
    should_escalate: bool
    reason: str          # "low_confidence" | "high_complexity" | "technical_deep_dive" | "long_input"
    confidence_score: float   # AnalysisResult.confidence 그대로
    complexity_score: float   # 정적 분석 계산값 (0.0~1.0)
```

#### EscalationRouter 클래스

```python
class EscalationRouter:
    """Qwen 결과 기반 Sonnet 에스컬레이션 판단"""

    # 기본 임계값 (gateway.json escalation 섹션으로 override 가능)
    DEFAULT_CONFIDENCE_THRESHOLD = 0.6
    DEFAULT_COMPLEXITY_THRESHOLD = 0.7
    DEFAULT_TOKEN_COUNT_THRESHOLD = 500

    ESCALATION_INTENTS = frozenset({
        "technical_deep_dive",
        "architecture_review",
        "debug_investigation",
    })

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        complexity_threshold: float = DEFAULT_COMPLEXITY_THRESHOLD,
        token_count_threshold: int = DEFAULT_TOKEN_COUNT_THRESHOLD,
    ):
        self.confidence_threshold = confidence_threshold
        self.complexity_threshold = complexity_threshold
        self.token_count_threshold = token_count_threshold

    def decide(
        self,
        analysis: AnalysisResult,
        original_text: str,
    ) -> EscalationDecision:
        """OR 조건 — 하나라도 해당 시 에스컬레이션"""
```

#### decide() 메서드 로직 흐름

```
decide(analysis, original_text)
    │
    ├─ complexity_score = _calc_complexity_score(original_text)
    │
    ├─ 조건 1: analysis.confidence < confidence_threshold (0.6)
    │       → EscalationDecision(True, "low_confidence", ...)
    │
    ├─ 조건 2: complexity_score > complexity_threshold (0.7)
    │       → EscalationDecision(True, "high_complexity", ...)
    │
    ├─ 조건 3: analysis.intent in ESCALATION_INTENTS
    │       → EscalationDecision(True, "technical_deep_dive", ...)
    │
    ├─ 조건 4: len(original_text.split()) > token_count_threshold (500)
    │       → EscalationDecision(True, "long_input", ...)
    │
    └─ 모두 해당 없음
            → EscalationDecision(False, "no_escalation", ...)
```

#### complexity_score 계산 알고리즘

```python
def _calc_complexity_score(self, text: str) -> float:
    score = 0.0
    words = text.split()

    # 코드 블록 포함: +0.3
    if "```" in text:
        score += 0.3

    # 500자 이상: +0.2
    if len(text) > 500:
        score += 0.2

    # 기술 용어 밀도: +0~0.3
    TECH_TERMS = {
        "api", "gateway", "pipeline", "async", "sqlite", "llm",
        "webhook", "oauth", "jwt", "docker", "kubernetes", "nginx",
        "redis", "celery", "fastapi", "websocket", "endpoint",
    }
    term_density = len(set(w.lower() for w in words) & TECH_TERMS) / max(len(words), 1)
    score += min(term_density * 3.0, 0.3)

    # 전각/반각 물음표 3개 이상: +0.1
    # text.count("?") + text.count("\uff1f") >= 3
    if text.count("?") + text.count("\uff1f") >= 3:
        score += 0.1

    # 영어 단어 비율 > 30%: +0.1
    english_words = [w for w in words if w.isascii() and w.isalpha()]
    if words and len(english_words) / len(words) > 0.3:
        score += 0.1

    return min(score, 1.0)
```

**전각 물음표(`？`, U+FF1F) 처리**: `text.count("\uff1f")` — 한국어 IME 입력 물음표 포함하여 3개 이상 시 +0.1 가산.

---

### 2.3 채널 컨텍스트 주입 (BOT-K03)

#### _load_channel_context() 구현 (handler.py 추가)

```python
async def _load_channel_context(self, channel_id: str) -> str:
    """
    config/channel_contexts/{channel_id}.json 로드 → 요약 문자열 반환.

    파일 없거나 읽기 실패 시 "" 반환 (파이프라인 중단 없음).
    추출 필드: channel_summary + key_topics(8개) + response_guidelines
    """
    import json as _json
    ctx_path = (
        Path(r"C:\claude\secretary\config\channel_contexts")
        / f"{channel_id}.json"
    )
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

토큰 절약을 위해 `channel_summary`, `key_topics`(최대 8개), `response_guidelines` 3개 필드만 추출. `key_decisions`, `member_profiles`, `escalation_hints`는 주입하지 않음.

#### chatbot_respond() 시그니처 변경

**OllamaAnalyzer (analyzer.py)**:

```python
# 변경 전
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    max_chars: int = 2000,
    context: str = "",
) -> Optional[str]:

# 변경 후 (channel_context 파라미터 추가)
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    max_chars: int = 2000,
    context: str = "",
    channel_context: str = "",   # BOT-K03 신규
) -> Optional[str]:
```

`channel_context` 주입 위치: `system_prompt` 문자열 앞에 prepend:

```python
if channel_context:
    system_prompt = f"## 채널 컨텍스트\n{channel_context}\n\n{system_prompt}"
```

**ClaudeCodeDraftWriter (draft_writer.py)**:

```python
# 변경 전
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    context: str = "",
) -> Optional[str]:

# 변경 후
async def chatbot_respond(
    self,
    text: str,
    sender_name: str,
    context: str = "",
    channel_context: str = "",   # BOT-K03 신규
) -> Optional[str]:
```

`channel_context` 주입 위치: prompt 문자열 선두에 추가:

```python
ctx_section = f"## 채널 컨텍스트\n{channel_context}\n\n" if channel_context else ""
prompt = f"""{ctx_section}Slack 채널에서 받은 메시지에 답변하세요.
...
"""
```

#### 신규 디렉토리

- `C:\claude\secretary\config\channel_contexts\` — git 추적 여부 사용자 확인 필요 (민감 정보 포함 가능성)
- `C:\claude\secretary\config\gmail_contexts\` — 동일

---

### 2.4 NormalizedMessage thread_id (BOT-K04)

#### models.py 변경 내역 — 방안 A (권장)

**변경 위치**: `C:\claude\secretary\scripts\gateway\models.py`

`NormalizedMessage` dataclass에 `thread_id` 필드 추가:

```python
@dataclass
class NormalizedMessage:
    # ... 기존 필드 ...
    reply_to_id: Optional[str] = None     # 기존: Slack thread_ts / 답장 대상 ID
    thread_id: Optional[str] = None       # BOT-K04 신규: Gmail threadId 전용
    # ... 기존 필드 ...
```

`to_dict()` 메서드에 직렬화 추가:

```python
def to_dict(self) -> dict:
    return {
        # ... 기존 필드 ...
        "reply_to_id": self.reply_to_id,
        "thread_id": self.thread_id,      # BOT-K04 신규
        # ... 기존 필드 ...
    }
```

#### GmailAdapter thread_id 매핑 방식

Gmail API 응답의 `threadId` → `NormalizedMessage.thread_id` 매핑:

```python
# adapters/gmail.py 내부 (신규 코드 아님, 설계 명세)
msg = NormalizedMessage(
    id=message_data["id"],
    channel=ChannelType.EMAIL,
    # ...
    reply_to_id=message_data.get("replyToId"),   # 기존 유지
    thread_id=message_data.get("threadId"),      # BOT-K04 신규 매핑
)
```

방안 B(`reply_to_id` 재활용)는 필드 의미 혼용 위험으로 채택하지 않음.

---

### 2.5 AutoResponseBot 통합 흐름 (BOT-K05)

**수정 파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py`

#### _handle_chatbot_message() 확장 순서도

```
_handle_chatbot_message(message, source_channel)
    │
    │ [0] 봇 자기 메시지 방지 (기존 로직 유지)
    │   subtype in ('bot_message', ...) → return
    │
    │ [1] 채널 컨텍스트 로드 (BOT-K03 신규)
    ├── channel_context = await _load_channel_context(message.channel_id)
    │   logger.info(f"[Chatbot] Channel context injected: {len(channel_context)} chars")  (비어있지 않을 때)
    │
    │ [2] 에스컬레이션 판단용 Ollama 분석 (BOT-K05 옵션 B)
    ├── analysis = await _analyzer.analyze(text, sender_name, source_channel, ...)
    │   (project_id는 무시, confidence + intent만 사용)
    │
    │ [3] Qwen chatbot 응답 생성 (기존 로직 — channel_context 파라미터 추가)
    ├── qwen_response = await _analyzer.chatbot_respond(
    │       text, sender_name, context, channel_context=channel_context
    │   )
    │
    │ [4] 에스컬레이션 판단 (BOT-K02 신규)
    ├── decision = escalation_router.decide(analysis, original_text)
    │
    │ [5] 분기
    ├── decision.should_escalate == False
    │       └── response_text = qwen_response
    │
    └── decision.should_escalate == True
            logger.info(f"[Chatbot] Escalating to Sonnet: reason={decision.reason}")
            ├── sonnet_response = await _draft_writer.chatbot_respond(
            │       text, sender_name, context, channel_context=channel_context
            │   )
            ├── 성공: response_text = sonnet_response
            └── 실패 (exception): response_text = qwen_response  (fallback)

    │ [6] fallback 처리 (기존 로직 유지)
    │   response_text None → "현재 AI 응답 서비스를 이용할 수 없습니다..."
    │
    │ [7] 처리 시간 로그
    │   logger.info(f"[Chatbot] Processed in {elapsed_ms}ms ({'sonnet' if escalated else 'qwen'})")
    │
    └── await _send_chatbot_reply(channel_id, response_text, thread_ts)
```

#### OllamaAnalyzer 이중 호출 처리 (옵션 B)

에스컬레이션 판단을 위해 `analyze()` 1회 + `chatbot_respond()` 1회 총 2번 Ollama 호출 발생. 이는 설계 단순성 우선 결정이며, 이후 최적화는 별도 태스크로 분리.

`analyze()` 결과에서 사용하는 필드:
- `confidence` → EscalationRouter.decide() 입력
- `intent` → ESCALATION_INTENTS 비교

사용하지 않는 필드:
- `project_id` — 챗봇 채널은 프로젝트 분류 불필요

#### EscalationRouter 초기화 위치

`ProjectIntelligenceHandler.__init__()` 내에서 gateway.json `escalation` 섹션을 읽어 초기화:

```python
escalation_config = config.get("intelligence", {}).get("escalation", {})
self._escalation_router = EscalationRouter(
    confidence_threshold=escalation_config.get("confidence_threshold", 0.6),
    complexity_threshold=escalation_config.get("complexity_threshold", 0.7),
    token_count_threshold=escalation_config.get("token_count_threshold", 500),
)
```

---

### 2.6 CLAUDE.md 업데이트 항목 (BOT-K06)

#### 변경 위치 1: 전체 데이터 흐름 다이어그램

파일: `C:\claude\secretary\CLAUDE.md` — "아키텍처 > 전체 데이터 흐름" 섹션

```
# 변경 전
├─ Stage 1-4: 우선순위 분석, 액션 탐지, DB 저장, Toast 알림
├─ Stage 5: ActionDispatcher → ...
└─ Stage 6: ProjectIntelligenceHandler

# 변경 후
├─ Stage 1-3: 우선순위 분석, 액션 탐지, DB 저장
├─ Stage 5: ActionDispatcher → ...
└─ Stage 6: ProjectIntelligenceHandler
```

#### 변경 위치 2: Gateway MessagePipeline 설명

```
# 변경 전
│   ├── Stage 1-4: Priority, Action Detection, Storage, Notification
│   ├── Stage 5: ActionDispatcher (action_dispatcher.py)

# 변경 후
│   ├── Stage 1-3: Priority, Action Detection, Storage
│   ├── Stage 5: ActionDispatcher (action_dispatcher.py)
```

#### 변경 위치 3: Intelligence Tier 2 모델명

파일: `C:\claude\secretary\CLAUDE.md` — "### 3. Intelligence" 섹션

```
# 변경 전
- Tier 2 (Claude Opus): needs_response=true일 때만 초안 작성
# 및 handler.py docstring

# 변경 후
- Tier 2 (Claude Sonnet): needs_response=true일 때만 초안 작성
```

근거: `config/gateway.json`의 `claude_draft.model: "sonnet"` 및 `draft_writer.py`의 실제 subprocess 호출 모델이 sonnet으로 운영 중.

---

## 3. 인터페이스 명세 (Interface Specification)

### 3.1 gateway.json 신규 섹션

`C:\claude\secretary\config\gateway.json`의 `intelligence` 객체 내부에 추가:

```json
{
  "intelligence": {
    "enabled": true,
    "chatbot_channels": ["C0985UXQN6Q"],
    "ollama": { ... },
    "claude_draft": { ... },
    "escalation": {
      "confidence_threshold": 0.6,
      "complexity_threshold": 0.7,
      "token_count_threshold": 500
    }
  }
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `confidence_threshold` | float | 0.6 | Qwen confidence 미만 시 에스컬레이션 |
| `complexity_threshold` | float | 0.7 | complexity_score 초과 시 에스컬레이션 |
| `token_count_threshold` | int | 500 | 단어 수 초과 시 에스컬레이션 |

### 3.2 channel_contexts/{channel_id}.json 스키마

저장 경로: `C:\claude\secretary\config\channel_contexts\{channel_id}.json`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | string | Y | Slack 채널 ID (예: `C0985UXQN6Q`) |
| `built_at` | string (ISO8601) | Y | 프로파일 생성 시각 |
| `source_version` | string | Y | 생성에 사용한 Sonnet 버전 |
| `channel_summary` | string | Y | 채널 목적 및 주요 활동 자연어 요약 |
| `communication_style` | string | N | 소통 스타일 (예: "기술적/한국어/결정 중심") |
| `key_topics` | string[] | Y | 주요 논의 주제 목록 (최대 10개) |
| `key_decisions` | string[] | N | 주요 의사결정 목록 (날짜 포함) |
| `member_profiles` | object | N | user_id → { role_summary, communication_style } |
| `response_guidelines` | string | Y | 응답 생성 시 고려할 지침 |
| `escalation_hints` | string[] | N | 에스컬레이션 권장 질문 유형 |

응답 주입 시 사용 필드: `channel_summary`, `key_topics`, `response_guidelines` (토큰 절약).

### 3.3 gmail_contexts/{thread_id}.json 스키마

저장 경로: `C:\claude\secretary\config\gmail_contexts\{thread_id}.json`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `thread_id` | string | Y | Gmail 스레드 ID |
| `built_at` | string (ISO8601) | Y | 컨텍스트 생성 시각 |
| `thread_summary` | string | Y | 스레드 주제 및 현재 상태 요약 |
| `participants` | string[] | Y | 참여자 이메일 목록 |
| `pending_action` | string \| null | N | 상대방이 요청한 액션 또는 null |
| `tone` | string | Y | 스레드 어조: `formal` \| `informal` \| `urgent` |
| `response_guidelines` | string | Y | 이 스레드 응답 시 고려사항 |

### 3.4 Gmail 에스컬레이션 분기 (handler._generate_draft())

Gmail `needs_response=true` 처리 시 추가 분기:

```python
async def _generate_draft(self, message, source_channel, project_id, analysis, rule_match):
    # ... 기존 로직 ...

    # BOT-K04: Gmail 에스컬레이션 분기
    if source_channel == "gmail":   # Slack 메시지에는 실행 금지
        thread_id = getattr(message, "thread_id", None)
        if thread_id:
            gmail_context = await _load_gmail_thread_context(thread_id)
            # EscalationRouter로 판단
            # 에스컬레이션 해당 → gmail_context 주입하여 Sonnet 초안 작성
        # thread_id 없거나 context 없음 → 기존 초안 생성 로직 실행 (backward-compatible)
```

---

## 4. 테스트 계획 (Test Plan)

### 4.1 단위 테스트

#### test_escalation_router.py
**파일**: `C:\claude\secretary\tests\intelligence\test_escalation_router.py`

| # | 테스트 케이스 | 입력 | 예상 결과 |
|---|-------------|------|----------|
| 1 | 낮은 confidence 에스컬레이션 | `confidence=0.4`, 단순 텍스트 | `should_escalate=True, reason="low_confidence"` |
| 2 | 코드블록 + 500자+ 메시지 에스컬레이션 | ` ``` ` 포함 500자+ 텍스트 | `should_escalate=True, reason="high_complexity"` |
| 3 | 단순 인사 미에스컬레이션 | `confidence=0.8`, "안녕하세요" | `should_escalate=False` |
| 4 | 전각 물음표 3개 이상 복잡도 증가 | `？？？` 포함 텍스트 | `complexity_score` 0.1 증가 확인 |
| 5 | 임계값 주입 (gateway.json 시뮬레이션) | `confidence_threshold=0.8` 주입, `confidence=0.7` | `should_escalate=True` (0.7 < 0.8) |

모두 외부 의존 없음 — 순수 함수 테스트.

#### test_channel_sonnet_profiler.py
**파일**: `C:\claude\secretary\tests\knowledge\test_channel_sonnet_profiler.py`

| # | 테스트 케이스 | 방식 |
|---|-------------|------|
| 1 | build_profile() 기존 파일 존재 시 스킵 | tmp_path에 JSON 생성 후 force=False 호출 → Sonnet 미호출 확인 |
| 2 | build_profile() 신규 파일 생성 | mock subprocess → JSON 파일 생성 확인 |
| 3 | Sonnet 실패 시 fallback profile 생성 | mock subprocess 에러 → mastery_context 기반 dict 반환 확인 |
| 4 | _parse_sonnet_output() 유효 JSON 파싱 | 샘플 Sonnet 출력 → dict 필드 검증 |
| 5 | _calc_channel_context_str() 토큰 절약 | channel_summary + key_topics + response_guidelines 3개 필드만 포함 확인 |

mock 기반 — `subprocess.run` 또는 `asyncio.create_subprocess_exec` patch.

### 4.2 통합 테스트

#### handler.py + EscalationRouter 연동 테스트

**파일**: `C:\claude\secretary\tests\intelligence\test_handler_escalation.py`

시나리오:
1. `_handle_chatbot_message()` 호출 시 `analyze()` + `chatbot_respond()` 모두 mock
2. `decision.should_escalate=True` 케이스 → `_draft_writer.chatbot_respond()` 호출 확인
3. Sonnet 실패 시 Qwen response fallback 확인
4. `channel_context` 주입 시 `chatbot_respond()` 호출 인자 검증

외부 의존: OllamaAnalyzer, ClaudeCodeDraftWriter 모두 mock/patch — 즉시 실행 가능.

---

## 5. 구현 체크리스트

### BOT-K01: ChannelSonnetProfiler

- [ ] `scripts/knowledge/channel_sonnet_profiler.py` 파일 생성
- [ ] `build_profile()` 실행 후 `config/channel_contexts/C0985UXQN6Q.json` 생성
- [ ] JSON에 `channel_summary`, `key_topics`, `response_guidelines` 필드 포함
- [ ] `force=False` 시 기존 파일 재생성 스킵
- [ ] Sonnet 실패 시 mastery_context 기반 fallback JSON 저장
- [ ] 단독 실행 지원: `python -m scripts.knowledge.channel_sonnet_profiler C0985UXQN6Q`
- [ ] `scripts/intelligence/prompts/channel_profile_prompt.txt` 프롬프트 파일 생성

### BOT-K02: EscalationRouter

- [ ] `scripts/intelligence/response/escalation_router.py` 파일 생성
- [ ] `EscalationDecision` dataclass 구현 (4개 필드)
- [ ] `decide()` — confidence 0.4 입력 시 `should_escalate=True, reason="low_confidence"` 반환
- [ ] `decide()` — 코드블록 포함 500자+ 메시지 → `should_escalate=True`
- [ ] `decide()` — confidence 0.8, 단순 인사 → `should_escalate=False`
- [ ] 임계값이 gateway.json에서 주입 가능 (생성자 파라미터)
- [ ] 전각 물음표(？) 3개 이상 → `complexity_score` +0.1 확인
- [ ] `tests/intelligence/test_escalation_router.py` 5개 테스트 통과

### BOT-K03: 채널 컨텍스트 주입

- [ ] `handler._load_channel_context()` 구현
- [ ] JSON 없거나 읽기 실패 시 `""` 반환 (graceful fallback)
- [ ] `OllamaAnalyzer.chatbot_respond()` — `channel_context` 파라미터 추가
- [ ] `ClaudeCodeDraftWriter.chatbot_respond()` — `channel_context` 파라미터 추가
- [ ] Sonnet 에스컬레이션 시에도 동일 `channel_context` 주입
- [ ] `config/channel_contexts/` 디렉토리 생성 (빈 `.gitkeep` 또는 첫 JSON)
- [ ] 주입 시 로그: `[Chatbot] Channel context injected: {N} chars`

### BOT-K04: Gmail 초기 분석 + 에스컬레이션

- [ ] `scripts/knowledge/gmail_thread_profiler.py` 파일 생성
- [ ] `config/gmail_contexts/` 디렉토리 생성 (`Path.mkdir(parents=True, exist_ok=True)`)
- [ ] `NormalizedMessage.thread_id: Optional[str] = None` 필드 추가
- [ ] `NormalizedMessage.to_dict()` 에 `thread_id` 직렬화 포함
- [ ] GmailAdapter가 Gmail API `threadId` → `NormalizedMessage.thread_id` 매핑
- [ ] `_generate_draft()` 내 `source_channel == "gmail"` 조건 guard 추가
- [ ] thread_context 없으면 기존 초안 생성 로직 실행 (backward-compatible)
- [ ] `GmailThreadProfiler.build_thread_context()` 단독 실행 지원

### BOT-K05: AutoResponseBot 통합

- [ ] `_handle_chatbot_message()` — `_load_channel_context()` 호출 추가
- [ ] `_handle_chatbot_message()` — `analyze()` 호출 추가 (에스컬레이션 판단용)
- [ ] `_handle_chatbot_message()` — `EscalationRouter.decide()` 호출 추가
- [ ] 에스컬레이션 발생 시 로그: `[Chatbot] Escalating to Sonnet: reason={reason}`
- [ ] Sonnet 실패 시 Qwen response fallback 동작
- [ ] 전체 처리 시간 로그: `[Chatbot] Processed in {ms}ms (qwen/sonnet)`
- [ ] `ProjectIntelligenceHandler.__init__()` — EscalationRouter 초기화 추가

### BOT-K06: 문서 업데이트

- [ ] `CLAUDE.md` — Stage 1-4 → Stage 1-3 (Toast 알림 제거)
- [ ] `CLAUDE.md` — Intelligence Tier 2 "Opus" → "Sonnet"
- [ ] `docs/01-plan/slack-channel-mastery.plan.md` — BOT-K 연계 주석 추가
- [ ] 변경 후 코드(`pipeline.py`, `handler.py`, `gateway.json`)와 불일치 없음 확인

---

## 6. 위험 및 엣지 케이스 대응

### 6.1 위험 목록

| 위험 | 영향 | 완화 방안 |
|------|------|----------|
| Sonnet 호출 비용 증가 | API 비용 급증 | 임계값 gateway.json 조정 가능, 초기 보수적 설정, 일별 에스컬레이션 횟수 로그 |
| 이중 Ollama 호출 지연 | chatbot 응답 2배 지연 | 단순성 우선 채택, 최적화는 별도 태스크 |
| 채널 컨텍스트 stale | 채널 변화 미반영 | `built_at` 기준 30일 초과 시 재생성 경고 로그 |
| Gmail thread_id 불일치 | context JSON 미매칭 | `gmail_contexts/` 로드 실패 시 기존 방식 실행 |
| EscalationRouter 오분류 | 단순 메시지 과도 에스컬레이션 | 임계값 조정, 7일 모니터링 후 재조정 |

### 6.2 엣지 케이스 처리

| 케이스 | 처리 방식 |
|--------|----------|
| 채널 컨텍스트 미빌드 상태 chatbot 메시지 수신 | `_load_channel_context()` → `""` → 기존 chatbot 동작 유지 |
| Sonnet 에스컬레이션 후 60s 타임아웃 | `qwen_response` 변수 fallback (에스컬레이션 전 저장 필수) |
| `analyze()` 결과의 `project_id` 무시 | chatbot 채널에서 project_id 필드 무시, `confidence` + `intent`만 사용 |
| `gmail_contexts/` 디렉토리 최초 미생성 | `Path.mkdir(parents=True, exist_ok=True)` 선행 실행 |
| `config/channel_contexts/` git 추적 여부 | 민감 정보 포함 가능성 — `.gitignore` 추가 여부 사용자 확인 필요 |

---

## 7. 구현 순서 권고

```
Phase 1 (독립 모듈):
    BOT-K02: EscalationRouter + 단위 테스트  ← 완전 독립

Phase 2 (병렬 구현 가능):
    BOT-K01: ChannelSonnetProfiler           ← CM-K04 완료 후
    BOT-K04: GmailThreadProfiler             ← BOT-K02 완료 후

Phase 3 (순차):
    BOT-K03: 채널 컨텍스트 주입             ← BOT-K01 완료 후
    BOT-K05: AutoResponseBot 통합           ← BOT-K02, K03, K04 완료 후
    BOT-K06: 문서 업데이트                  ← BOT-K05 완료 후
```

---

## 참고 파일

| 파일 | 역할 |
|------|------|
| `C:\claude\secretary\scripts\intelligence\response\handler.py` L395-568 | `_handle_chatbot_message()`, `_send_chatbot_reply()` 기반 |
| `C:\claude\secretary\scripts\intelligence\response\analyzer.py` L398-520 | `OllamaAnalyzer.chatbot_respond()` 현재 구현 |
| `C:\claude\secretary\scripts\intelligence\response\draft_writer.py` L178-201 | `ClaudeCodeDraftWriter.chatbot_respond()` 현재 구현 |
| `C:\claude\secretary\scripts\gateway\models.py` L46-117 | `NormalizedMessage` 현재 구조 |
| `C:\claude\secretary\config\gateway.json` | `intelligence.escalation` 섹션 추가 위치 |
| `C:\claude\secretary\docs\01-plan\channel-knowledge-bot.plan.md` | 원본 계획 문서 |
