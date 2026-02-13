# POC 검증 전략 - Project Intelligence v2

**Version**: 1.0.0
**Created**: 2026-02-10
**Parent Plan**: project-intelligence.plan.md v2.0.0
**Status**: DRAFT

---

## 1. 검증 목표

Project Intelligence v2의 핵심 기능이 실제 환경에서 동작함을 확인.
API key 사용 없이 Browser OAuth + claude -p만으로 전체 파이프라인 동작 검증.

**핵심 요구사항:**
- 모든 검증은 실행 가능한 PowerShell/Python 스크립트로 제공
- 외부 서비스 인증 여부에 따라 Phase 분리
- 각 검증은 독립 실행 가능하며 명확한 합격 기준 제시

## 2. 검증 대상 및 우선순위

7개 검증 영역을 P0(필수), P1(중요), P2(부가)로 분류:

### P0 - 필수 검증 (시스템 동작의 전제 조건)

| ID | 영역 | 검증 내용 | 파일 | 판정 기준 |
|----|------|----------|------|----------|
| V1 | IntelligenceStorage | DB 생성, CRUD, WAL mode | context_store.py | 4개 테이블 생성, CRUD 성공, 동시 접근 |
| V2 | ProjectRegistry | config 로드, 프로젝트 조회 | project_registry.py | projects.json → DB 동기화 |
| V3 | CLI 기본 동작 | register, stats, pending, drafts | cli.py | 모든 서브커맨드 정상 실행 |

### P1 - 중요 검증 (핵심 기능)

| ID | 영역 | 검증 내용 | 파일 | 판정 기준 |
|----|------|----------|------|----------|
| V4 | ContextMatcher | 3-tier 매칭 정확도 | context_matcher.py | Tier1: channel 0.9, Tier2: keyword 0.7, Tier3: sender 0.5, 미매칭 → pending |
| V5 | DraftGenerator | claude -p subprocess 동작 | draft_generator.py | claude -p 호출 성공, 응답 수신, rate limit 동작 |
| V6 | DraftStore | 파일 저장 + DB + Toast | draft_store.py | .md 파일 생성, DB 레코드 존재, Toast 팝업 |

### P2 - 부가 검증 (외부 연동)

| ID | 영역 | 검증 내용 | 파일 | 판정 기준 |
|----|------|----------|------|----------|
| V7 | lib.slack oldest | 증분 히스토리 조회 | lib/slack/client.py | oldest 파라미터로 이전 메시지 제외 |
| V8 | lib.gmail History | 증분 이메일 조회 | lib/gmail/client.py | historyId 기반 새 메시지만 반환 |
| V9 | SlackAdapter | polling + NormalizedMessage | adapters/slack.py | 연결 → 메시지 수신 → 정규화 |
| V10 | GmailAdapter | polling + NormalizedMessage | adapters/gmail.py | 연결 → 메시지 수신 → 정규화 |

## 3. 검증 방법

### 3.1 V1: IntelligenceStorage CRUD

**목적**: SQLite DB 생성, CRUD 동작, WAL mode 동시 접근 확인

```powershell
cd C:\claude\secretary
python -c "
import asyncio
from scripts.intelligence.context_store import IntelligenceStorage

async def test():
    storage = IntelligenceStorage()
    await storage.connect()

    # 1. 프로젝트 저장
    await storage.save_project({'id': 'test', 'name': 'Test Project'})
    p = await storage.get_project('test')
    assert p is not None, 'save/get failed'
    print('✅ V1-1: 프로젝트 CRUD 통과')

    # 2. 컨텍스트 항목 저장
    await storage.save_context_entry({
        'id': 'ctx_001', 'project_id': 'test',
        'source': 'slack', 'entry_type': 'message',
        'title': '테스트', 'content': '테스트 내용'
    })
    entries = await storage.get_context_entries('test')
    assert len(entries) > 0, 'context entry save failed'
    print('✅ V1-2: 컨텍스트 CRUD 통과')

    # 3. Draft 저장
    draft_id = await storage.save_draft({
        'source_channel': 'slack',
        'original_text': '테스트 메시지',
        'match_status': 'pending_match',
    })
    drafts = await storage.list_drafts()
    assert len(drafts) > 0, 'draft save failed'
    print('✅ V1-3: Draft CRUD 통과')

    # 4. 통계
    stats = await storage.get_stats()
    assert stats['projects'] >= 1
    print(f'✅ V1-4: 통계 통과 (projects={stats[\"projects\"]})')

    # 정리
    await storage.delete_project('test')
    await storage.close()
    print('\n✅ V1 전체 통과')

asyncio.run(test())
"
```

**예상 출력:**
```
✅ V1-1: 프로젝트 CRUD 통과
✅ V1-2: 컨텍스트 CRUD 통과
✅ V1-3: Draft CRUD 통과
✅ V1-4: 통계 통과 (projects=1)

✅ V1 전체 통과
```

### 3.2 V2: ProjectRegistry

**목적**: config/projects.json → DB 동기화, 검색 동작 확인

```powershell
cd C:\claude\secretary
python -c "
import asyncio
from scripts.intelligence.context_store import IntelligenceStorage
from scripts.intelligence.project_registry import ProjectRegistry

async def test():
    storage = IntelligenceStorage()
    await storage.connect()

    registry = ProjectRegistry(storage)
    count = await registry.load_from_config()
    print(f'로드된 프로젝트: {count}개')
    assert count >= 1, 'No projects loaded'

    projects = await registry.list_all()
    for p in projects:
        print(f'  - {p[\"id\"]}: {p[\"name\"]} (keywords: {p.get(\"keywords\", [])})')

    # 채널 검색
    result = await registry.find_by_channel('secretary-dev')
    print(f'채널 검색 결과: {result}')

    # 키워드 검색
    results = await registry.find_by_keyword('secretary AI 비서')
    print(f'키워드 검색 결과: {len(results)}개')
    assert len(results) >= 1, 'Keyword search failed'

    await storage.close()
    print('\n✅ V2 전체 통과')

asyncio.run(test())
"
```

**예상 출력:**
```
로드된 프로젝트: 3개
  - secretary: Secretary V2 - AI 비서 도구 (keywords: ['secretary', 'AI 비서', 'daily report'])
  - automation_hub: WSOP 방송 자동화 (keywords: ['WSOP', '방송', '자동화'])
  - archive-analyzer: 미디어 아카이브 분석 (keywords: ['MAM', '미디어', 'archive'])
채널 검색 결과: {'id': 'secretary', 'name': 'Secretary V2 - AI 비서 도구', ...}
키워드 검색 결과: 1개

✅ V2 전체 통과
```

### 3.3 V3: CLI 기본 동작

**목적**: CLI 서브커맨드 전체 정상 실행 확인

```powershell
# register (projects.json → DB 동기화)
cd C:\claude\secretary
python scripts\intelligence\cli.py register

# stats (통계 조회)
python scripts\intelligence\cli.py stats --json

# pending (미매칭 메시지 목록)
python scripts\intelligence\cli.py pending

# drafts (대기 중 초안 목록)
python scripts\intelligence\cli.py drafts
```

**예상 출력:**
```
# register
✅ 프로젝트 3개 등록 완료

# stats --json
{"projects": 3, "context_entries": 0, "drafts": 0, "pending_messages": 0}

# pending
미매칭 메시지 없음

# drafts
대기 중 초안 없음
```

### 3.4 V4: ContextMatcher 3-tier

**목적**: 3-tier 매칭 정확도 및 pending 저장 확인

```powershell
cd C:\claude\secretary
python -c "
import asyncio
from scripts.intelligence.context_store import IntelligenceStorage
from scripts.intelligence.project_registry import ProjectRegistry
from scripts.intelligence.response.context_matcher import ContextMatcher

async def test():
    storage = IntelligenceStorage()
    await storage.connect()

    registry = ProjectRegistry(storage)
    await registry.load_from_config()

    matcher = ContextMatcher(registry, storage)

    # Tier 2: 키워드 매칭 (secretary 프로젝트 키워드)
    r = await matcher.match(
        channel_id='unknown-channel',
        text='secretary 프로젝트의 daily 리포트 확인 부탁합니다',
        sender_id='user123',
    )
    print(f'Tier2 키워드: matched={r.matched}, confidence={r.confidence}, tier={r.tier}')
    assert r.matched, 'Keyword match should succeed'
    assert r.confidence == 0.7
    print('✅ V4-1: Tier 2 키워드 매칭 통과')

    # 미매칭 → pending_match
    r2 = await matcher.match_and_store_pending(
        channel_id='random-channel',
        text='관련 없는 메시지입니다',
        sender_id='stranger',
        sender_name='Stranger',
        source_channel='slack',
    )
    assert not r2.matched, 'Should not match'
    pending = await storage.get_pending_messages()
    assert len(pending) >= 1, 'Pending message should be saved'
    print('✅ V4-2: 미매칭 → pending_match 통과')

    await storage.close()
    print('\n✅ V4 전체 통과')

asyncio.run(test())
"
```

**예상 출력:**
```
Tier2 키워드: matched=True, confidence=0.7, tier=keyword
✅ V4-1: Tier 2 키워드 매칭 통과
✅ V4-2: 미매칭 → pending_match 통과

✅ V4 전체 통과
```

### 3.5 V5: DraftGenerator (claude -p)

**목적**: claude CLI 존재 확인 및 실제 draft 생성 동작

```powershell
# 사전 조건: claude CLI 설치 확인
where.exe claude

# claude -p 기본 동작
claude -p --model haiku "Say OK"

# DraftGenerator 테스트
cd C:\claude\secretary
python -c "
import asyncio
from scripts.intelligence.response.draft_generator import ClaudeCodeDraftGenerator

async def test():
    gen = ClaudeCodeDraftGenerator(model='haiku')
    print(f'Claude CLI 경로: {gen.claude_path}')
    assert gen.is_available, 'Claude CLI not available'
    print('✅ V5-1: CLI 존재 확인')

    # 실제 draft 생성
    draft = await gen.generate_draft(
        project_name='Test Project',
        context='프로젝트 설명: AI 비서 도구',
        sender_name='홍길동',
        source_channel='slack',
        original_text='다음 릴리즈 일정이 어떻게 되나요?',
    )
    assert len(draft) > 0, 'Empty draft returned'
    print(f'생성된 draft ({len(draft)}자):')
    print(draft[:200])
    print('✅ V5-2: Draft 생성 성공')

asyncio.run(test())
"
```

**예상 출력:**
```
Claude CLI 경로: C:\Users\AidenKim\AppData\Local\Programs\Claude\claude.exe
✅ V5-1: CLI 존재 확인
생성된 draft (350자):
홍길동님 안녕하세요,

Test Project 프로젝트의 다음 릴리즈 일정에 대해 문의해 주셔서 감사합니다.

현재 프로젝트 컨텍스트를 확인한 결과, AI 비서 도구로서 개발 중이며...
✅ V5-2: Draft 생성 성공
```

### 3.6 V6: DraftStore (파일 + DB + Toast)

**목적**: Draft 파일 생성, DB 저장, Toast 알림, 승인/거부 워크플로우 확인

```powershell
cd C:\claude\secretary
python -c "
import asyncio
from pathlib import Path
from scripts.intelligence.context_store import IntelligenceStorage
from scripts.intelligence.response.draft_store import DraftStore

async def test():
    storage = IntelligenceStorage()
    await storage.connect()

    # 테스트 프로젝트 생성
    await storage.save_project({'id': 'test-draft', 'name': 'Draft Test'})

    store = DraftStore(storage)
    result = await store.save(
        project_id='test-draft',
        source_channel='slack',
        source_message_id='msg_001',
        sender_id='user1',
        sender_name='홍길동',
        original_text='테스트 메시지입니다',
        draft_text='이것은 테스트 응답 초안입니다.',
        match_confidence=0.9,
        match_tier='channel',
    )

    print(f'Draft ID: {result[\"draft_id\"]}')
    print(f'Draft 파일: {result[\"draft_file\"]}')

    # 파일 존재 확인
    assert Path(result['draft_file']).exists(), 'Draft file not created'
    print('✅ V6-1: 파일 저장 확인')

    # DB 레코드 확인
    draft = await storage.get_draft(result['draft_id'])
    assert draft is not None, 'Draft not in DB'
    assert draft['status'] == 'pending'
    print('✅ V6-2: DB 레코드 확인')

    # 승인/거부 워크플로우
    await storage.update_draft_status(result['draft_id'], 'approved', '테스트 승인')
    updated = await storage.get_draft(result['draft_id'])
    assert updated['status'] == 'approved'
    print('✅ V6-3: 승인 워크플로우 확인')

    # 정리
    await storage.delete_project('test-draft')
    await storage.close()
    print('\n✅ V6 전체 통과')

asyncio.run(test())
"
```

**예상 출력:**
```
Draft ID: draft_20260210_140530_001
Draft 파일: C:\claude\secretary\output\drafts\test-draft\draft_20260210_140530_001.md
✅ V6-1: 파일 저장 확인
✅ V6-2: DB 레코드 확인
✅ V6-3: 승인 워크플로우 확인

✅ V6 전체 통과
```

**Toast 알림**: 스크립트 실행 시 Windows Toast 알림 팝업 표시 확인

### 3.7 V7: lib.slack oldest 파라미터

**목적**: Slack 증분 히스토리 조회 동작 확인

**사전 조건**: Slack OAuth 인증 완료 필요
```powershell
cd C:\claude
python -m lib.slack login
```

**검증 스크립트:**
```powershell
cd C:\claude
python -c "
from lib.slack import SlackClient

client = SlackClient()
if client.validate_token():
    # oldest 없이 전체 조회
    msgs = client.get_history('C0XXXXXX', limit=5)
    print(f'전체 메시지: {len(msgs)}개')

    if msgs:
        # oldest로 증분 조회
        last_ts = msgs[0].ts
        newer = client.get_history('C0XXXXXX', limit=5, oldest=last_ts)
        print(f'oldest={last_ts} 이후: {len(newer)}개')
        print('✅ V7: oldest 파라미터 동작 확인')
else:
    print('⚠️ Slack 인증 필요: python -m lib.slack login')
"
```

**예상 출력:**
```
전체 메시지: 5개
oldest=1707561600.123456 이후: 0개
✅ V7: oldest 파라미터 동작 확인
```

### 3.8 V8: lib.gmail History API

**목적**: Gmail 증분 조회 (History API) 동작 확인

**사전 조건**: Gmail OAuth 인증 완료 (자동)

**검증 스크립트:**
```powershell
cd C:\claude
python -c "
from lib.gmail import GmailClient

client = GmailClient()
profile = client.get_profile()
history_id = profile.get('historyId')
print(f'현재 historyId: {history_id}')

if history_id:
    history = client.list_history(str(history_id))
    new_id = history.get('historyId')
    records = history.get('history', [])
    print(f'새 historyId: {new_id}, 기록: {len(records)}건')
    print('✅ V8: History API 동작 확인')
"
```

**예상 출력:**
```
현재 historyId: 123456
새 historyId: 123460, 기록: 0건
✅ V8: History API 동작 확인
```

### 3.9 V9: SlackAdapter (Gateway)

**목적**: Gateway Slack Adapter polling + 메시지 정규화 확인

**사전 조건**:
1. Slack OAuth 인증 완료
2. Gateway 서버 시작

```powershell
# Gateway 시작
cd C:\claude\secretary
python scripts\gateway\server.py start
```

**검증 방법**:
- Slack 채널에 테스트 메시지 전송
- Gateway 로그에서 메시지 수신 확인
- DB에 NormalizedMessage 저장 확인

**수동 검증 체크리스트:**
- [ ] Slack 메시지 전송 → Gateway 로그에 "Received message" 출력
- [ ] DB `context_entries` 테이블에 레코드 생성
- [ ] NormalizedMessage 필드 정확성: source='slack', sender_id, timestamp

### 3.10 V10: GmailAdapter (Gateway)

**목적**: Gateway Gmail Adapter polling + 메시지 정규화 확인

**사전 조건**:
1. Gmail OAuth 인증 완료
2. Gateway 서버 시작

**검증 방법**:
- Gmail 수신함에 테스트 이메일 전송
- Gateway 로그에서 이메일 수신 확인
- DB에 NormalizedMessage 저장 확인

**수동 검증 체크리스트:**
- [ ] Gmail 수신 → Gateway 로그에 "Received email" 출력
- [ ] DB `context_entries` 테이블에 레코드 생성
- [ ] NormalizedMessage 필드 정확성: source='gmail', sender_id, timestamp

## 4. End-to-End 시나리오

### E2E-1: 전체 파이프라인 (Storage → Matcher → Generator → Store)

**목적**: 인증 없이 핵심 파이프라인 전체 동작 확인

```powershell
cd C:\claude\secretary
python -c "
import asyncio
from scripts.intelligence.context_store import IntelligenceStorage
from scripts.intelligence.project_registry import ProjectRegistry
from scripts.intelligence.response.context_matcher import ContextMatcher
from scripts.intelligence.response.draft_generator import ClaudeCodeDraftGenerator
from scripts.intelligence.response.draft_store import DraftStore

async def e2e():
    # Setup
    storage = IntelligenceStorage()
    await storage.connect()
    registry = ProjectRegistry(storage)
    await registry.load_from_config()
    matcher = ContextMatcher(registry, storage)
    generator = ClaudeCodeDraftGenerator(model='haiku')
    store = DraftStore(storage)

    # 1. 매칭
    result = await matcher.match(
        channel_id='secretary-dev',
        text='secretary 프로젝트 빌드 에러 발생',
        sender_id='dev1',
    )
    print(f'매칭: {result.matched}, project={result.project_id}, tier={result.tier}')

    if result.matched:
        # 2. 컨텍스트 조회
        entries = await storage.get_context_entries(result.project_id, limit=5)
        context = '\n'.join(e.get('content', '')[:200] for e in entries) or '(컨텍스트 없음)'

        # 3. Draft 생성
        draft_text = await generator.generate_draft(
            project_name=result.project_name,
            context=context,
            sender_name='Developer',
            source_channel='slack',
            original_text='secretary 프로젝트 빌드 에러 발생',
        )
        print(f'Draft: {draft_text[:200]}')

        # 4. 저장
        saved = await store.save(
            project_id=result.project_id,
            source_channel='slack',
            source_message_id='e2e_001',
            sender_id='dev1',
            sender_name='Developer',
            original_text='secretary 프로젝트 빌드 에러 발생',
            draft_text=draft_text,
            match_confidence=result.confidence,
            match_tier=result.tier,
        )
        print(f'저장: draft_id={saved[\"draft_id\"]}, file={saved[\"draft_file\"]}')

    await storage.close()
    print('\n✅ E2E-1: 전체 파이프라인 통과')

asyncio.run(e2e())
"
```

**예상 출력:**
```
매칭: True, project=secretary, tier=channel
Draft: Developer님 안녕하세요,

secretary 프로젝트의 빌드 에러에 대해 문의해 주셔서 감사합니다.

현재 프로젝트 컨텍스트를 확인한 결과...
저장: draft_id=draft_20260210_141530_002, file=C:\claude\secretary\output\drafts\secretary\draft_20260210_141530_002.md

✅ E2E-1: 전체 파이프라인 통과
```

## 5. 검증 실행 순서

### Phase 1: 기반 검증 (인증 불필요)

**시간**: 약 5분

```
V1 (Storage CRUD)
  → V2 (ProjectRegistry)
  → V3 (CLI 기본 동작)
  → V4 (ContextMatcher)
  → V6 (DraftStore)
```

**실행 방법**: 위 섹션 3.1~3.4, 3.6의 PowerShell 스크립트 순서대로 실행

### Phase 2: LLM 연동 검증 (claude CLI 필요)

**시간**: 약 2분

```
V5 (DraftGenerator with claude -p)
  → E2E-1 (전체 파이프라인)
```

**실행 방법**: 섹션 3.5, 4.1의 PowerShell 스크립트 실행

### Phase 3: 외부 서비스 검증 (OAuth 인증 필요)

**시간**: 약 10분 (인증 포함)

```
V7 (lib.slack oldest)
  → V8 (lib.gmail History)
  → V9 (SlackAdapter)
  → V10 (GmailAdapter)
```

**실행 방법**:
1. Slack 인증: `python -m lib.slack login`
2. Gmail 인증: 자동 (첫 실행 시)
3. Gateway 시작: `python scripts\gateway\server.py start`
4. 섹션 3.7~3.10의 검증 수행

## 6. 합격 기준

| 등급 | 조건 | 판정 |
|------|------|------|
| **POC 통과** | V1~V6 전부 통과 + E2E-1 통과 | 핵심 파이프라인 동작 확인 |
| **통합 통과** | POC + V7~V10 통과 | 실서비스 연동 가능 |
| **완전 통과** | 통합 + Gateway 24시간 안정 가동 | 프로덕션 투입 가능 |

### POC 통과 상세 조건

| 검증 | 필수 조건 |
|------|----------|
| V1 | 4개 서브테스트 모두 ✅ |
| V2 | projects.json에 정의된 프로젝트 전부 DB 동기화 |
| V3 | 4개 CLI 서브커맨드 모두 에러 없이 실행 |
| V4 | Tier2 키워드 매칭 성공 + pending 저장 성공 |
| V5 | claude -p 호출 성공 + draft 텍스트 200자+ |
| V6 | 파일 생성 + DB 저장 + 승인 워크플로우 동작 |
| E2E-1 | 4단계 파이프라인 모두 성공 |

### 통합 통과 상세 조건

POC 통과 조건 + 아래 추가:

| 검증 | 필수 조건 |
|------|----------|
| V7 | oldest 파라미터로 이전 메시지 필터링 확인 |
| V8 | historyId 기반 증분 조회 동작 |
| V9 | Slack 메시지 → NormalizedMessage → DB 저장 |
| V10 | Gmail 메시지 → NormalizedMessage → DB 저장 |

## 7. 알려진 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| claude -p 인증 만료 | Draft 생성 실패 | Gateway 내 재시도 + 에러 격리 |
| Slack OAuth 토큰 갱신 | 메시지 수신 중단 | lib.slack 자동 refresh |
| Gmail historyId 만료 | 증분 조회 실패 | fallback: messages.list |
| SQLite 동시 쓰기 | WAL 충돌 | 단일 writer 보장 (Gateway만) |
| Windows Toast 미표시 | 알림 실패 | 로그 기록 + DB 레코드로 대체 |
| claude CLI 경로 변경 | DraftGenerator 동작 중단 | PATH 기반 fallback |

### 리스크별 대응 시나리오

#### R1: claude -p 인증 만료
```
증상: subprocess TimeoutError 또는 빈 응답
대응:
1. claude logout → claude login
2. DraftGenerator 재시도 (최대 3회)
3. 실패 시 draft 상태를 'generation_failed'로 저장
```

#### R2: Slack OAuth 토큰 갱신
```
증상: lib.slack.SlackApiError: invalid_auth
대응:
1. lib.slack 내부 auto-refresh 동작
2. 실패 시 python -m lib.slack login 재실행
```

#### R3: Gmail historyId 만료
```
증상: Gmail API 404 Not Found (historyId invalid)
대응:
1. GmailAdapter가 자동으로 messages.list fallback
2. 새 historyId 획득 후 다음 poll부터 증분 조회 재개
```

#### R4: SQLite 동시 쓰기
```
증상: sqlite3.OperationalError: database is locked
대응:
1. WAL mode 활성화 (기본 설정)
2. 단일 Gateway 프로세스만 writer 역할 보장
3. CLI는 reader 전용
```

## 8. 검증 체크리스트

### Phase 1 (기반 검증) 체크리스트

```markdown
- [ ] V1-1: 프로젝트 CRUD 통과
- [ ] V1-2: 컨텍스트 CRUD 통과
- [ ] V1-3: Draft CRUD 통과
- [ ] V1-4: 통계 통과
- [ ] V2: ProjectRegistry 전체 통과
- [ ] V3: CLI register 정상 실행
- [ ] V3: CLI stats --json 정상 실행
- [ ] V3: CLI pending 정상 실행
- [ ] V3: CLI drafts 정상 실행
- [ ] V4-1: Tier 2 키워드 매칭 통과
- [ ] V4-2: 미매칭 → pending_match 통과
- [ ] V6-1: 파일 저장 확인
- [ ] V6-2: DB 레코드 확인
- [ ] V6-3: 승인 워크플로우 확인
```

### Phase 2 (LLM 연동) 체크리스트

```markdown
- [ ] claude CLI 설치 확인 (where.exe claude)
- [ ] V5-1: CLI 존재 확인
- [ ] V5-2: Draft 생성 성공 (200자 이상)
- [ ] E2E-1: 매칭 단계 성공
- [ ] E2E-1: 컨텍스트 조회 성공
- [ ] E2E-1: Draft 생성 성공
- [ ] E2E-1: 저장 단계 성공
```

### Phase 3 (외부 서비스) 체크리스트

```markdown
- [ ] Slack OAuth 인증 완료
- [ ] Gmail OAuth 인증 완료
- [ ] V7: lib.slack oldest 파라미터 동작 확인
- [ ] V8: lib.gmail History API 동작 확인
- [ ] Gateway 서버 시작 성공
- [ ] V9: Slack 메시지 수신 확인
- [ ] V9: NormalizedMessage 정규화 확인
- [ ] V9: DB 저장 확인
- [ ] V10: Gmail 수신 확인
- [ ] V10: NormalizedMessage 정규화 확인
- [ ] V10: DB 저장 확인
```

## 9. 문제 해결 가이드

### 일반적인 오류 및 해결 방법

| 오류 메시지 | 원인 | 해결 |
|------------|------|------|
| `ModuleNotFoundError: No module named 'scripts.intelligence'` | PYTHONPATH 미설정 | `cd C:\claude\secretary` 실행 후 재시도 |
| `sqlite3.OperationalError: no such table: projects` | DB 초기화 안 됨 | `IntelligenceStorage().connect()` 실행 (자동 생성) |
| `FileNotFoundError: config/projects.json` | 설정 파일 누락 | 섹션 3.2의 projects.json 생성 |
| `subprocess.TimeoutError` (V5) | claude CLI 응답 느림 | timeout 30초로 증가 또는 --model haiku 사용 |
| `AssertionError: Claude CLI not available` | claude 미설치 | `winget install Anthropic.Claude` |

### 디버그 모드 실행

```powershell
# 전체 로그 출력
$env:DEBUG = "1"
python -c "import asyncio; ..."

# SQLite 쿼리 로그
$env:SQL_DEBUG = "1"
python scripts\intelligence\cli.py stats
```

## 10. 검증 자동화 (향후 계획)

### 전체 검증 스크립트 (POC)

```powershell
# 파일: scripts/intelligence/verify_poc.ps1
cd C:\claude\secretary

Write-Host "=== Phase 1: 기반 검증 ===" -ForegroundColor Cyan
python scripts\intelligence\verify_poc.py --phase 1

Write-Host "=== Phase 2: LLM 연동 ===" -ForegroundColor Cyan
python scripts\intelligence\verify_poc.py --phase 2

Write-Host "=== Phase 3: 외부 서비스 ===" -ForegroundColor Yellow
Write-Host "수동 인증 필요" -ForegroundColor Yellow
```

### CI/CD 통합 (GitHub Actions)

```yaml
# 파일: .github/workflows/poc-verify.yml
name: POC Verification

on: [push, pull_request]

jobs:
  phase1:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python scripts/intelligence/verify_poc.py --phase 1
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0.0 | 2026-02-10 | 초안 작성 (10개 검증 영역, 3 Phase 구조) |
