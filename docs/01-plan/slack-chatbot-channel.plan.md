# Slack Chatbot Channel 계획

## 배경

Secretary Gateway의 Intelligence 핸들러는 현재 모든 수신 메시지에 대해 프로젝트 매칭을 수행하고, 매칭 실패 시 `pending_match`로 저장 후 종료한다. `#claude-auto` 채널(C0985UXQN6Q)은 사용자가 AI 비서와 직접 대화하기 위한 채널이므로, 프로젝트 매칭 없이 Ollama가 즉시 응답을 생성하고 Slack thread reply로 자동 전송하는 chatbot 모드가 필요하다.

현재 문제점:
- `#claude-auto`에 메시지를 보내도 project_id 미매칭으로 `pending_match` 상태에 머물러 응답 없음
- 기존 `auto_send_disabled: true` 안전 규칙이 chatbot 채널에도 동일하게 적용되어 자동 전송 불가
- chatbot 전용 프롬프트 없이 프로젝트 분류 프롬프트만 존재

## 구현 범위

### 1. gateway.json — chatbot_channels 설정 추가

`config/gateway.json`의 `intelligence` 섹션에 `chatbot_channels` 배열 추가.

Acceptance Criteria:
- `chatbot_channels: ["C0985UXQN6Q"]` 기본값으로 설정
- 빈 배열 시 chatbot 모드 비활성화 (기존 동작 유지)
- JSON 스키마 변경 없이 기존 키 유지

### 2. handler.py — _process_message에 chatbot 분기 추가

`_process_message` 진입 직후 `message.channel_id`가 `chatbot_channels`에 포함되는지 확인하고, 포함된 경우 `_handle_chatbot_message`로 라우팅.

Acceptance Criteria:
- chatbot 채널 감지 시 Step 2(ContextMatcher), Step 4(_resolve_project), Step 5(pending_match) 건너뜀
- `_handle_chatbot_message`가 Ollama로 직접 응답 생성
- 생성된 응답을 `lib.slack.SlackClient.send_message(thread_ts=original_ts)`로 thread reply 전송
- chatbot_channels가 비어있거나 해당 채널이 아니면 기존 파이프라인 그대로 실행
- Rate limiting: `shared/rate_limiter.py`의 `ollama` bucket 사용 (10/min)

### 3. analyzer.py (또는 handler.py 내부) — chatbot 전용 Ollama 프롬프트

chatbot 모드는 프로젝트 분류가 아닌 대화 응답 생성이 목적이므로, 기존 `analyze_prompt.txt`와 별도 로직으로 Ollama 호출.

Acceptance Criteria:
- 프롬프트: "당신은 사용자의 질문에 직접 답하는 AI 비서입니다. 간결하고 도움이 되는 응답을 생성하세요."
- `OllamaAnalyzer.chatbot_respond(text, sender_name)` 메서드 또는 handler 내부 inline 호출
- 응답 최대 길이: 2000자 (Slack 메시지 제한 고려)
- Ollama 불가 시 fallback: "현재 AI 응답 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요."

### 4. ProjectIntelligenceHandler.__init__ — chatbot_channels 파라미터 수용

생성자에서 `chatbot_config` 또는 `chatbot_channels` 리스트를 받아 인스턴스 변수로 저장. `server.py`에서 `gateway.json`을 로드해 주입.

Acceptance Criteria:
- `self._chatbot_channels: list = chatbot_config.get("chatbot_channels", [])` 형태
- 기존 `ollama_config`, `claude_config` 파라미터와 독립적으로 동작
- `None` 전달 시 빈 리스트로 처리

### 5. Slack 자동 전송 구현

chatbot 채널 응답 전송 시 `lib.slack.SlackClient`를 직접 사용하거나 SlackAdapter를 통해 thread reply.

Acceptance Criteria:
- `thread_ts`를 원본 메시지의 Slack timestamp로 설정 (`message.raw_json` 파싱 또는 `reply_to_id` 활용)
- 전송 성공/실패 로그 출력
- 전송 실패 시 예외 전파하지 않음 (fire-and-forget)
- 기존 `auto_send_disabled` 설정과 무관하게 chatbot 채널만 자동 전송 허용

### 6. 테스트 작성

`tests/intelligence/test_handler.py`에 chatbot 관련 테스트 추가.

Acceptance Criteria:
- `test_chatbot_channel_bypasses_project_matching`: chatbot 채널 메시지가 ContextMatcher, _resolve_project를 호출하지 않음
- `test_non_chatbot_channel_uses_existing_pipeline`: chatbot 채널 아닌 메시지는 기존 파이프라인 실행
- `test_chatbot_sends_slack_reply`: Ollama 응답 생성 후 Slack 전송 호출 확인
- `test_chatbot_ollama_failure_sends_fallback`: Ollama 실패 시 fallback 메시지 전송
- `test_chatbot_rate_limiting`: rate limit 초과 시 대기 후 처리

## 영향 파일

수정 대상:

| 파일 | 변경 내용 |
|------|----------|
| `C:\claude\secretary\config\gateway.json` | `intelligence.chatbot_channels` 배열 추가 |
| `C:\claude\secretary\scripts\intelligence\response\handler.py` | `_process_message` chatbot 분기, `_handle_chatbot_message` 메서드 추가, `__init__` 파라미터 확장 |
| `C:\claude\secretary\scripts\intelligence\response\analyzer.py` | `chatbot_respond(text, sender_name)` 메서드 추가 (Ollama 직접 호출, 대화 특화 프롬프트) |
| `C:\claude\secretary\tests\intelligence\test_handler.py` | chatbot 관련 테스트 5건 추가 |

신규 생성 없음 (기존 파일 확장만 수행).

확인된 실제 파일 경로:
- `C:\claude\secretary\config\gateway.json` (존재 확인)
- `C:\claude\secretary\scripts\intelligence\response\handler.py` (존재 확인, 487줄)
- `C:\claude\secretary\scripts\intelligence\response\analyzer.py` (존재 확인, 473줄)
- `C:\claude\secretary\tests\intelligence\test_handler.py` (존재 확인, 482줄)

## 위험 요소

### 기술적 위험

1. **Slack thread_ts 추출 실패**: `NormalizedMessage.raw_json`에 `{"ts": ..., "channel": ...}` 형태로 저장되어 있으나, thread reply를 위해서는 원본 메시지의 `ts` 값이 필요. `raw_json` 파싱 실패 또는 `ts` 키 누락 시 thread reply 대신 일반 메시지로 전송될 수 있다. 대응: `reply_to_id` 우선 사용, `raw_json` fallback, 둘 다 없으면 일반 메시지로 전송.

2. **lib.slack 접근 방식**: handler.py는 현재 Slack 직접 전송 기능이 없다. SlackAdapter는 server.py 레벨에서 관리되므로 handler에서 직접 `lib.slack.SlackClient`를 import해야 한다. `asyncio.to_thread()`로 동기 API 브릿지 필요 (SlackAdapter 패턴 동일하게 적용). lib.slack import 실패 시 전송 불가 처리 필요.

3. **Ollama chatbot 프롬프트 품질**: 기존 `analyze_prompt.txt`는 프로젝트 분류 특화 프롬프트이나, chatbot 응답은 다른 성격의 프롬프트가 필요. 인라인 프롬프트로 구현 시 유지보수 어려움. `scripts/intelligence/prompts/chatbot_prompt.txt` 별도 파일로 관리 권장하나, 파일 누락 시 fallback 프롬프트 하드코딩 필수.

### Edge Case

1. **봇이 자기 메시지에 응답**: Slack 봇 토큰으로 전송한 메시지를 Gateway가 다시 polling할 경우 무한 루프 발생 위험. `sender_id`가 봇 ID인 메시지는 chatbot 모드에서 건너뛰도록 처리 필요. `lib.slack.SlackClient`에서 봇 user ID를 조회하거나, 메시지 subtype이 `bot_message`인 경우 제외.

2. **Rate limit 초과 시 사용자 무응답**: Ollama 10/min rate limit 초과 시 `wait_if_needed()`가 대기 후 처리하나, 채팅 맥락에서 응답이 수 분 지연될 수 있다. chatbot 채널 전용 rate limit bucket `chatbot_ollama`를 별도 설정(5/min)하거나, 초과 시 즉시 "잠시 후 다시 시도해 주세요" 메시지 전송 후 스킵하는 방식 권장.

3. **handler가 Slack client 인스턴스 없이 초기화**: server.py에서 SlackAdapter와 handler가 독립적으로 초기화된다. chatbot 전송을 위해 handler가 별도 SlackClient를 생성하면 인증 토큰을 중복 로드한다. handler 초기화 시 slack_client 주입 파라미터를 추가하거나, handler 내부에서 lazy 초기화로 처리.

4. **chatbot_channels가 기존 intelligence 채널과 중복**: `gateway.json`의 `channels.slack.channels`에 이미 `C0985UXQN6Q`가 포함되어 있다. chatbot 모드가 활성화되면 해당 채널 메시지는 기존 intelligence 파이프라인 대신 chatbot 경로로만 처리된다. 이는 의도한 동작이나, 동일 채널에서 프로젝트 관련 메시지도 올 경우 intelligence 분석이 누락될 수 있음.

## 작업 순서

### Phase 1: 설정 및 기반 구조 (완료 기준: gateway.json 수정, handler 초기화 확장)

1. `config/gateway.json` — `intelligence.chatbot_channels: ["C0985UXQN6Q"]` 추가
2. `handler.py` — `__init__`에 `chatbot_channels` 파라미터 추가, `self._chatbot_channels` 저장
3. `handler.py` — `_is_chatbot_channel(channel_id)` 헬퍼 메서드 추가
4. `handler.py` — server.py에서 `chatbot_channels` 주입 경로 확인 (기존 초기화 코드 추적)

완료 기준: `handler.is_chatbot_channel("C0985UXQN6Q")` → `True` 반환

### Phase 2: Ollama chatbot 응답 생성 (완료 기준: chatbot 프롬프트로 Ollama 호출 성공)

5. `analyzer.py` — `chatbot_respond(text, sender_name, max_chars=2000)` 메서드 추가
   - 인라인 chatbot 프롬프트 사용 (프로젝트 분류 없이 대화 응답)
   - Ollama `/api/chat` 호출, `temperature=0.7` (창의적 응답)
   - 실패 시 `None` 반환
6. `handler.py` — `_handle_chatbot_message(message)` 메서드 추가
   - `self._analyzer.chatbot_respond()` 호출
   - 응답 없으면 fallback 문자열 사용

완료 기준: mock Ollama로 `chatbot_respond()` 호출 시 텍스트 반환

### Phase 3: Slack 자동 전송 (완료 기준: thread reply 전송 성공)

7. `handler.py` — `_send_chatbot_reply(channel_id, text, thread_ts)` 메서드 추가
   - `asyncio.to_thread(self._slack_client.send_message, channel=channel_id, text=text, thread_ts=thread_ts)`
   - `lib.slack.SlackClient` lazy 초기화
   - 전송 실패 로그 후 무시
8. `handler.py` — `_handle_chatbot_message`에서 `message.raw_json` 파싱하여 `thread_ts` 추출
   - 파싱 실패 시 `reply_to_id` 사용, 둘 다 없으면 `None`
9. `handler.py` — `_process_message`에 chatbot 분기 삽입 (Step 1 중복 체크 직후)

완료 기준: 실제 Slack `#claude-auto`에 메시지 전송 시 thread reply 수신

### Phase 4: 테스트 작성 (완료 기준: 5건 테스트 전부 PASS)

10. `tests/intelligence/test_handler.py` — 5건 테스트 추가
    - `test_chatbot_channel_bypasses_project_matching`
    - `test_non_chatbot_channel_uses_existing_pipeline`
    - `test_chatbot_sends_slack_reply`
    - `test_chatbot_ollama_failure_sends_fallback`
    - `test_chatbot_rate_limiting`
11. `pytest tests/intelligence/test_handler.py -v` 전체 PASS 확인

완료 기준: 기존 test 포함 전체 PASS, 새 5건 PASS
