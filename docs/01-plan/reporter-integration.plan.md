# Reporter Integration Plan

**Version**: 1.0.0
**Created**: 2026-02-18
**Status**: PLANNED
**Ralplan 상태**: 대기 중

---

## 목표

Reporter 모듈을 Gateway Pipeline과 Intelligence 핸들러에 통합하여 자동 알림 시스템을 완성. Slack DM으로 실시간 긴급 메시지, 초안 생성 알림, 일일 종합 Digest를 자동 전송.

---

## 복잡도 점수: 3/5

| 조건 | 점수 | 근거 |
|------|:----:|------|
| 파일 범위 | 1 | 신규 3개, 기존 2개 수정 |
| 아키텍처 | 1 | Pipeline Handler 추가, 비동기 스케줄러 통합 |
| 의존성 | 0 | slack_sdk 이미 사용 중, 추가 의존성 없음 |
| 모듈 영향 | 1 | gateway/, intelligence/response/, reporter/ 3개 모듈 |
| 사용자 명시 | 0 | ralplan 키워드 없음 |

**총합: 3/5 (MEDIUM - Dev팀 단독 처리 가능)**

---

## 현재 상태 분석

### 기존 Reporter 구조

```
scripts/reporter/
├── __init__.py
├── reporter.py              ✓ SecretaryReporter 오케스트레이터 완성
├── alert.py                 ✓ UrgentAlert, DraftNotification 타입 정의
├── digest.py                ✓ DigestReport (통계 집계) 완성
└── channels/
    └── slack_dm.py          ✓ SlackDMChannel (Slack DM 전송) 완성
```

**상태**: Reporter 모듈은 이미 **완전히 구현**되어 있음. 필요한 기능:
- `SecretaryReporter.send_urgent_alert()` - 긴급 메시지 알림
- `SecretaryReporter.send_draft_notification()` - 초안 생성 알림
- `SecretaryReporter.send_daily_digest()` - 일일 요약 (매일 설정된 시간)
- `SecretaryReporter.start()` / `stop()` - 스케줄러 관리

### Gateway 현재 상태

**서버.py (lines 346-370)에서 Reporter 초기화 구현됨**:
```python
# Reporter 초기화 (gateway.json의 reporter 섹션)
reporter_config = self.config.get("reporter", {})
if reporter_config.get("enabled", False):
    reporter = SecretaryReporter(
        gateway_storage=self.storage,
        intel_storage=intel_storage,
        config=reporter_config,
    )
    await reporter.start()
    handler.set_reporter(reporter)
    self._reporter = reporter
```

**현재 문제점**:
1. ✗ Reporter는 초기화되지만 **Pipeline Handler로 등록되지 않음**
2. ✗ 긴급 메시지(URGENT priority) 감지 후 **Slack DM 알림이 자동 트리거되지 않음**
3. ✗ Intelligence가 초안 생성했을 때 **Reporter 알림이 호출되지 않음** (set_reporter는 있지만 사용처 없음)
4. ✗ Daily Digest는 스케줄되지만 **Gateway 시작 시에만 트리거 가능** (프로세스 유지 필수)

### Intelligence 현재 상태

**handler.py (line 94)에서 Reporter 참조 가능**:
```python
# Reporter (Phase 5에서 주입)
self._reporter = None
```

**현재 문제점**:
1. ✗ `set_reporter()` 메서드 없음 (server.py에서 호출 시도하지만 구현 안 됨)
2. ✗ 초안 생성 완료 후 `send_draft_notification()` 호출 없음
3. ✗ Project ID 해석 실패 시 pending_match에 저장하지만 알림 없음

---

## 핵심 기능

### 1. 긴급 메시지 알림 (URGENT Priority)

**트리거**: Pipeline에서 `priority=URGENT` 메시지 감지

**흐름**:
```
Message 수신
  ↓
Pipeline Stage 1: Priority Analysis (긴급 키워드 감지)
  ↓ [URGENT 판정]
  ↓
Pipeline Stage 4: Notification (Toast 알림)
  ↓
Stage 6: Custom Handler (ProjectIntelligenceHandler)
  ↓ [새 Handler: ReporterPipelineHandler]
Reporter.send_urgent_alert()
  ↓
Slack DM 전송 (사용자 지정 DM)
```

**기준**:
- 긴급 키워드 포함: "긴급", "urgent", "ASAP", "지금", "바로" 등 (gateway.json의 pipeline.urgent_keywords 참조)
- 부정 컨텍스트 제외 (예: "지금까지", "바로가기")

**알림 포맷** (Slack DM):
```
:rotating_light: *[긴급]* 새 메시지
*발신자:* john (slack)
*내용:* 이 버그 지금 바로 확인해주세요!
```

**SLA**: 메시지 수신 후 **30초 이내** 알림 도착

---

### 2. 초안 생성 알림

**트리거**: Intelligence가 `needs_response=true`로 판정하고 Claude Opus로 초안 작성 완료

**흐움**:
```
Message 분석
  ↓
OllamaAnalyzer (Tier 1): needs_response, project_id 판정
  ↓ [needs_response=true]
  ↓
ClaudeCodeDraftWriter (Tier 2): 초안 작성
  ↓
DraftStore: DB에 저장
  ↓
Reporter.send_draft_notification()
  ↓
Slack DM 전송
```

**포함 정보**:
- 프로젝트 ID
- 발신자 이름 및 채널
- 신뢰도 점수 및 매칭 방식 (Ollama/Rule-based)
- CLI 승인 명령어

**알림 포맷** (Slack DM):
```
:memo: *새 응답 초안*
*프로젝트:* claude-secretary
*발신자:* sarah (gmail)
*신뢰도:* 0.92 (Ollama)
*CLI:* `python scripts/intelligence/cli.py drafts approve 42`
```

**SLA**: 초안 저장 완료 후 **1분 이내** 알림 도착

---

### 3. Daily Digest 자동화

**트리거**: 매일 `gateway.json의 reporter.digest_time` (기본값: 18:00) 에 자동 실행

**수집 데이터**:
- 메시지 통계 (총 수, 긴급, 높음)
- 초안 통계 (생성, 대기, 승인)
- 미매칭 메시지 수 (pending_match)
- 감지된 액션 수 (TODO, 마감일 등)

**알림 포맷** (Slack DM):
```
:clipboard: *일일 요약* (02/18)
- 총 메시지: 42건 (긴급 3, 높음 8)
- 생성 초안: 7건 (대기 2, 승인 5)
- 미매칭: 1건
- 감지 액션: 12건
```

**SLA**: 설정 시간 **±1분 이내** 전송

**예약 실행**: `asyncio.sleep()` 기반 정확한 시간 지정

---

## 구현 범위

### 신규 파일 (3개)

#### 1. `scripts/gateway/reporters.py` (또는 reporter_handler.py)

**목적**: Pipeline에서 URGENT 메시지를 감지하면 자동으로 Reporter에 전달

**클래스**:
```python
class ReporterPipelineHandler:
    """Pipeline Stage 6 Custom Handler"""

    def __init__(self, reporter: SecretaryReporter):
        self.reporter = reporter

    async def handle(self, enriched: EnrichedMessage, result: PipelineResult) -> None:
        """
        Pipeline에서 호출되는 핸들러

        - URGENT 메시지면 즉시 UrgentAlert 전송
        """
        if result.priority == "urgent" and self.reporter.is_active:
            alert = UrgentAlert(
                message_id=enriched.original.id,
                sender_name=enriched.original.sender_name,
                source_channel=enriched.original.channel.value,
                channel_id=enriched.original.channel_id,
                text_preview=enriched.original.text[:200]
            )
            await self.reporter.send_urgent_alert(alert)
```

**역할**:
- Pipeline이 Stage 6 Custom Handler로 호출
- URGENT 메시지를 즉시 감지
- Reporter의 `send_urgent_alert()` 호출
- 예외 처리: Reporter 비활성 시 무시

---

#### 2. `scripts/intelligence/response/reporter_bridge.py`

**목적**: Intelligence Handler에서 초안 생성 완료 시 Reporter 알림

**클래스**:
```python
class IntelligenceReporterBridge:
    """Intelligence → Reporter 통신 브릿지"""

    def __init__(self, reporter: Optional[SecretaryReporter] = None):
        self.reporter = reporter

    async def notify_draft_created(
        self,
        draft_id: int,
        project_id: str,
        message: NormalizedMessage,
        match_confidence: float,
        match_tier: str,  # 'ollama', 'rule_based'
    ) -> bool:
        """초안 생성 알림"""
        if not self.reporter or not self.reporter.is_active:
            return False

        notification = DraftNotification(
            draft_id=draft_id,
            project_id=project_id,
            sender_name=message.sender_name,
            source_channel=message.channel.value,
            match_confidence=match_confidence,
            match_tier=match_tier,
        )
        return await self.reporter.send_draft_notification(notification)
```

**역할**:
- Intelligence Handler에 주입되는 브릿지
- 초안 저장 완료 후 호출
- Slack DM 알림 전송
- 실패해도 파이프라인 중단 안 함 (best-effort)

---

### 기존 파일 수정 (2개)

#### 1. `scripts/gateway/server.py` 수정

**변경 사항**:

**A. Reporter Pipeline Handler 등록 (line ~371)**
```python
# Intelligence 등록 후, Reporter 핸들러도 등록
if self._reporter:
    from scripts.gateway.reporters import ReporterPipelineHandler
    reporter_handler = ReporterPipelineHandler(self._reporter)
    self.pipeline.add_handler(reporter_handler.handle)
    print(f"  - Reporter 핸들러 등록 (긴급 메시지 자동 알림)")
```

**위치**: `_register_intelligence_handler()` 메서드 내, line 371 이후 (Intelligence 핸들러 등록 직후)

---

#### 2. `scripts/intelligence/response/handler.py` 수정

**변경 사항**:

**A. set_reporter() 메서드 추가 (line ~94)**
```python
def set_reporter(self, reporter) -> None:
    """Reporter 인스턴스 주입"""
    self._reporter = reporter
    if reporter:
        self._reporter_bridge = IntelligenceReporterBridge(reporter)
```

**위치**: `__init__()` 메서드 직후

**B. 초안 생성 완료 후 Reporter 알림 (ClaudeCodeDraftWriter 호출 후)**

현재 코드 위치: `_process_message()` 메서드 내, draft_writer.generate() 호출 후

```python
# Draft 저장
if draft_id:
    # Reporter 알림 (비동기, 실패해도 무시)
    if self._reporter_bridge:
        asyncio.create_task(
            self._reporter_bridge.notify_draft_created(
                draft_id=draft_id,
                project_id=project_id,
                message=message,
                match_confidence=confidence,
                match_tier=match_tier,
            )
        )
```

**위치**: `draft_store.save()` 호출 직후

---

## 설정 파일 (gateway.json)

### 필수 섹션 추가

```json
{
  "reporter": {
    "enabled": true,
    "digest_time": "18:00",
    "channels": {
      "slack_dm": {
        "enabled": true,
        "user_id": "U12345"  // 알림 수신 사용자의 Slack User ID
      }
    }
  }
}
```

**설정 항목**:
- `reporter.enabled`: Reporter 활성화 여부 (기본값: false)
- `reporter.digest_time`: 일일 Digest 전송 시간 (HH:MM 형식, 기본값: "18:00")
- `reporter.channels.slack_dm.enabled`: Slack DM 채널 활성화
- `reporter.channels.slack_dm.user_id`: 알림 수신자의 Slack User ID

**User ID 확인 방법**:
```bash
python -m lib.slack channels  # 채널 목록에서 확인 가능
# 또는 Slack 앱에서 프로필 → "Copy user ID"
```

---

## 위험 요소 및 완화 방안

| 위험 | 영향 | 심각도 | 완화 방안 |
|------|------|:-------:|----------|
| Slack DM Rate Limit (1/sec) | 알림 전송 지연 | 중간 | Queue 기반 rate limiting (10/min) 적용 |
| 서버 크래시 시 Digest 스케줄 유실 | 그날 Digest 미전송 | 낮음 | 로그 기록 + 수동 복구 가능 |
| Reporter 초기화 실패 | 알림 비활성화 | 낮음 | try-except, is_active 체크 |
| 과도한 알림으로 사용자 피로감 | 알림 피로 | 중간 | 설정으로 활성화 제어, Digest만 일일 1회 |
| Intelligence Handler 오류 시 Reporter도 중단 | 알림 중단 | 낮음 | asyncio.create_task()로 비동기 처리, 예외 격리 |

**완화 전략**:
1. **Rate Limiting**: `gateway.json`의 `safety.rate_limit_per_minute` 적용 (기존 Pipeline과 동일)
2. **Error Isolation**: 모든 Reporter 호출을 try-except로 보호
3. **Graceful Degradation**: Reporter 비활성 시 다른 기능에 영향 없음
4. **Logging**: 모든 알림 전송/실패 기록 (logging 모듈)

---

## 성공 지표

### 기능 검증

| 지표 | 기준 | 검증 방법 |
|------|------|----------|
| 긴급 메시지 알림 | 수신 후 30초 이내 Slack DM 도착 | 테스트 메시지 전송 후 확인 |
| 초안 생성 알림 | 저장 후 1분 이내 알림 도착 | Intelligence 테스트 케이스 |
| Daily Digest | 매일 18:00 ±1분에 자동 전송 | 시간 설정 변경 후 확인 |
| 서버 시작/종료 | Reporter 정상 초기화/정리 | 로그에서 "Reporter 시작/중지" 메시지 확인 |
| 에러 격리 | Reporter 실패 시 Pipeline 계속 실행 | Reporter 비활성화 후 다른 기능 작동 확인 |

### 성능 지표

| 지표 | 목표 |
|------|------|
| 긴급 메시지 알림 지연 | < 30초 |
| 초안 알림 지연 | < 1분 |
| Slack DM 전송 성공률 | > 95% (rate limit 제외) |
| Gateway 메모리 증가 | < 10MB (Reporter 추가) |

### 무중단 운영

- Reporter 비활성화 시에도 Gateway, Intelligence 정상 작동
- 기존 Pipeline 성능 저하 없음 (Handler는 비동기로 병렬 실행)

---

## 구현 순서 (권장 5단계)

### Phase 1: 기반 준비
1. `scripts/gateway/reporters.py` 신규 작성
2. `scripts/intelligence/response/reporter_bridge.py` 신규 작성
3. gateway.json에 reporter 섹션 추가

### Phase 2: Gateway 통합
1. server.py에 Reporter Pipeline Handler 등록 코드 추가
2. 테스트: URGENT 메시지 → Slack DM 알림 확인

### Phase 3: Intelligence 통합
1. handler.py에 set_reporter() 메서드 추가
2. handler.py에 초안 생성 후 Reporter 알림 호출 추가
3. 테스트: 초안 생성 → Slack DM 알림 확인

### Phase 4: 스케줄러 검증
1. server.py 시작 → Reporter 스케줄러 시작 확인
2. 설정 시간에 Daily Digest 자동 전송 확인
3. 로그 메시지 검증

### Phase 5: 통합 테스트
1. 전체 Gateway + Intelligence + Reporter 흐름 테스트
2. 에러 케이스 (Reporter 비활성화, Slack 연결 실패 등)
3. 성능 테스트 (메모리, CPU, 지연)

---

## 테스트 계획

### 단위 테스트

**tests/reporter/test_pipeline_handler.py**:
```python
async def test_urgent_message_triggers_alert():
    """URGENT 메시지 → Reporter.send_urgent_alert() 호출"""
    reporter = Mock()
    handler = ReporterPipelineHandler(reporter)

    enriched = create_test_message(priority="urgent")
    result = PipelineResult(message_id="1", priority="urgent")

    await handler.handle(enriched, result)

    reporter.send_urgent_alert.assert_called_once()

async def test_draft_notification():
    """초안 생성 → Reporter.send_draft_notification() 호출"""
    reporter = Mock()
    bridge = IntelligenceReporterBridge(reporter)

    result = await bridge.notify_draft_created(
        draft_id=42,
        project_id="claude-secretary",
        message=create_test_message(),
        match_confidence=0.92,
        match_tier="ollama",
    )

    assert result is True
    reporter.send_draft_notification.assert_called_once()
```

### 통합 테스트

**tests/integration/test_reporter_integration.py**:
```python
async def test_full_flow_urgent_message():
    """
    실제 Gateway + Pipeline + Reporter 통합 테스트
    1. Slack 어댑터 → URGENT 메시지 수신
    2. Pipeline → Priority 분석
    3. Reporter Handler → Slack DM 전송
    """
    async with Gateway() as gateway:
        # Mock Slack 어댑터로 URGENT 메시지 주입
        # Reporter Slack DM 수신 확인

async def test_daily_digest_scheduling():
    """Daily Digest 스케줄러 검증"""
    reporter = SecretaryReporter(config={"digest_time": "12:00"})
    await reporter.start()

    # 12:00 도래까지 대기 또는 시간 mock
    # Digest 생성 확인

    await reporter.stop()
```

### E2E 테스트 (수동)

1. Gateway 시작 → Reporter 활성화 확인 (로그)
2. Slack에 "이거 긴급 해주세요" 메시지 전송 → DM 수신 확인
3. Intelligence가 초안 생성 → DM 수신 확인 (cli approve 명령 포함)
4. 18:00 도래 → Daily Digest DM 자동 수신 확인
5. Gateway 중지 → Reporter 정리 확인 (로그)

---

## 안전 규칙

### 자동 전송 금지

Reporter는 **절대 자동으로 Slack 메시지를 전송하지 않음**:
- ✓ 알림 (UrgentAlert, DraftNotification) - OK
- ✓ Digest (일일 요약) - OK
- ✗ 실제 응답 메시지 자동 전송 - **금지**

초안(`draft_responses`)은 사용자가 `cli.py drafts approve`로 수동 승인 후 Slack 적절한 채널에 전송.

### Rate Limiting

모든 Reporter 알림은 Pipeline의 rate limiting 적용:
- `gateway.json`의 `safety.rate_limit_per_minute` (기본값: 10)
- URGENT 메시지는 이 제한에 포함됨

### Error Handling

모든 Reporter 호출은 try-except로 보호:
```python
try:
    await self.reporter.send_urgent_alert(alert)
except Exception as e:
    logger.error(f"Reporter 알림 실패: {e}")
    # Pipeline 계속 진행
```

---

## 마이그레이션 및 롤백

### 활성화 (첫 배포)

1. gateway.json의 `reporter.enabled`를 `false`로 시작
2. 기능 검증 완료 후 `true`로 변경
3. 실제 사용자 DM 알림 시작

### 긴급 롤백

Reporter를 즉시 비활성화:
```bash
# gateway.json
{
  "reporter": {
    "enabled": false
  }
}
```

Gateway 재시작 → Reporter 비활성화 (다른 기능은 정상 작동)

---

## 참고 자료

### 현재 구현 파일
- `scripts/reporter/reporter.py` - SecretaryReporter 오케스트레이터
- `scripts/reporter/alert.py` - UrgentAlert, DraftNotification 타입
- `scripts/reporter/digest.py` - DigestReport 통계 집계
- `scripts/gateway/server.py` - Gateway 메인 서버 (Reporter 초기화 코드 이미 있음)
- `scripts/gateway/pipeline.py` - MessagePipeline (Stage 6 Custom Handler 지원)
- `scripts/intelligence/response/handler.py` - ProjectIntelligenceHandler

### 설정 참고
- `config/gateway.json` - Gateway 전체 설정 (reporter 섹션 추가 필요)
- `config/projects.json` - Intelligence 프로젝트 정의

### 관련 문서
- `CLAUDE.md` - 프로젝트 개요 및 아키텍처
- `docs/01-plan/project-intelligence.plan.md` - Intelligence 기능 상세

---

## FAQ

**Q1. Reporter 비활성화 시 다른 기능은 작동하나?**
A. 네, Reporter는 독립적인 모듈입니다. 비활성화해도 Gateway, Intelligence, Pipeline 모두 정상 작동합니다.

**Q2. Daily Digest 시간을 변경하려면?**
A. `gateway.json`의 `reporter.digest_time`을 "20:00" 형식으로 변경 후 Gateway 재시작.

**Q3. Slack DM을 받을 사용자를 변경하려면?**
A. `gateway.json`의 `reporter.channels.slack_dm.user_id`를 새 User ID로 변경 후 Gateway 재시작.

**Q4. Reporter 알림이 오지 않으면?**
A. 다음 체크:
- `reporter.enabled` = true 확인
- `slack_dm.enabled` = true 확인
- Slack 토큰이 유효한지 확인 (`python -m lib.slack validate`)
- 서버 로그에서 "Reporter 시작" 메시지 확인
- Slack DM이 수신 거부 설정은 아닌지 확인

**Q5. 과도한 알림을 받으면?**
A. 다음 옵션:
- `reporter.enabled`를 `false`로 설정
- 또는 특정 채널/프로젝트만 활성화하도록 설정 추가 (향후 기능)

---

**다음 단계**: Ralplan 검토 및 개발팀 의견 수렴

