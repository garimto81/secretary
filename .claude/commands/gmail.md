# /gmail - Gmail 관리 커맨드

Gmail 메일 읽기, 검색, 전송, 관리를 위한 통합 커맨드.

## 사용법

```
/gmail                      # 안 읽은 메일 확인
/gmail inbox                # 받은편지함 보기
/gmail search "from:boss"   # 메일 검색
/gmail send "to" "제목" "본문"  # 메일 전송
/gmail read <id>            # 메일 상세 보기
```

## 서브커맨드

| 서브커맨드 | 설명 | 예시 |
|-----------|------|------|
| (없음) | 안 읽은 메일 확인 | `/gmail` |
| `inbox` | 받은편지함 | `/gmail inbox` |
| `unread` | 안 읽은 메일 | `/gmail unread` |
| `search` | 메일 검색 | `/gmail search "from:client"` |
| `read` | 메일 상세 | `/gmail read <email_id>` |
| `send` | 메일 전송 | `/gmail send "to@example.com" "제목" "본문"` |
| `labels` | 라벨 목록 | `/gmail labels` |
| `archive` | 보관처리 | `/gmail archive <email_id>` |
| `trash` | 휴지통 이동 | `/gmail trash <email_id>` |

## 실행 워크플로우

### Step 1: 인증 확인

```bash
python -m lib.gmail status --json
```

- `authenticated: true, valid: true` → 계속 진행
- `authenticated: false` → 로그인 안내 출력

### Step 2: 요청 처리

**기본 (안 읽은 메일):**
```bash
python -m lib.gmail unread --limit 10 --json
```

**받은편지함:**
```bash
python -m lib.gmail inbox --limit 10 --json
```

**검색:**
```bash
python -m lib.gmail search "$ARGUMENTS" --limit 10 --json
```

**메일 상세:**
```bash
python -m lib.gmail read "$EMAIL_ID" --json
```

**메일 전송:**
```bash
python -m lib.gmail send "$TO" "$SUBJECT" "$BODY"
```

### Step 3: 결과 정리

JSON 출력을 파싱하여 사용자에게 보기 좋게 정리:

```
📬 안 읽은 메일 3개

1. **회의 안건** - boss@company.com (2026-02-01)
   > 내일 오후 3시 회의 참석...

2. **주간 보고** - team@company.com (2026-01-31)
   > 이번 주 진행 상황...
```

## 검색 쿼리 문법

| 조건 | 쿼리 예시 |
|------|----------|
| 발신자 | `from:example@gmail.com` |
| 수신자 | `to:me@gmail.com` |
| 제목 | `subject:meeting` |
| 첨부파일 | `has:attachment` |
| 안 읽음 | `is:unread` |
| 별표 | `is:starred` |
| 날짜 이후 | `after:2024/01/01` |
| 날짜 이전 | `before:2024/12/31` |
| 라벨 | `label:work` |

**복합 검색:**
```
/gmail search "from:client@example.com subject:invoice has:attachment"
```

## 자동 처리 시나리오

### 시나리오 1: 메일 분석 후 할일 추출

```
/gmail search "is:unread from:client"
```

→ 검색 결과를 분석하여:
- 요청사항 추출
- 우선순위 분류
- TODO 생성 제안

### 시나리오 2: 메일 응답 초안 작성

```
/gmail read <email_id>
```

→ 메일 내용을 분석하여:
- 핵심 질문 파악
- 응답 초안 생성
- 전송 확인 요청

### 시나리오 3: 자동 정리

```
/gmail inbox --limit 50
```

→ 받은편지함 분석하여:
- 중요 메일 하이라이트
- 스팸/광고 필터링 제안
- 보관 처리 제안

## 필수 규칙

| 규칙 | 설명 |
|------|------|
| ✅ 항상 `--json` 플래그 | 결과 파싱 용이 |
| ✅ 인증 먼저 확인 | status 명령 선행 |
| ✅ 결과 요약 제공 | 사용자 친화적 출력 |
| ❌ 토큰 파일 직접 접근 | 보안 위험 |
| ❌ WebFetch 사용 | OAuth 필요 |

## 관련 스킬

- `/auto --gmail`: Gmail 컨텍스트를 작업에 주입
- `.claude/skills/gmail/SKILL.md`: 상세 스킬 문서
