---
name: daily-sync
deprecated: true
redirect: daily
deprecation_message: "/daily-sync는 /daily v3.0에 통합되었습니다. /daily를 사용하세요."
version: 1.4.0
triggers:
  keywords: []
model_preference: sonnet
auto_trigger: false
---

# Daily Sync Skill - WSOPTV 일일 동기화

WSOPTV 프로젝트의 업체 관리를 위한 AI 분석 기반 일일 동기화 스킬입니다.
Gmail/Slack 데이터를 Claude Code가 직접 분석하여 업체 현황을 파악합니다.

## 핵심 기능

| 기능 | 방식 | 설명 |
|------|------|------|
| **이메일 분석** | AI | 업체 메일에서 견적, 협상 상태, 긴급도 추론 |
| **Slack 분석** | AI | 팀 논의에서 의사결정, 액션 아이템 추출 |
| **견적 추출** | 하이브리드 | 정규식 → AI 폴백으로 비정형 금액 처리 |
| **첨부파일 분석** | 하이브리드 | Claude Read(≤20p) + pdfplumber(>20p) |
| **상태 추론** | AI | 이메일 톤 기반 협상 단계 판단 |
| **보고서 생성** | AI | 상황에 맞는 자연어 보고서 |

---

## 사용 방법

### 1. 기본 실행

```
/daily-sync
```

또는 자연어로:

```
업체 현황 분석해줘
견적 분석해줘
회신 필요한 메일 알려줘
```

### 2. 옵션

| 옵션 | 설명 | 예시 |
|------|------|------|
| `--vendor <name>` | 특정 업체만 분석 | `/daily-sync --vendor megazone` |
| `--days <n>` | 분석 기간 (기본 30일) | `/daily-sync --days 14` |
| `--quick` | 빠른 요약만 | `/daily-sync --quick` |

---

## 워크플로우

### Phase 1: Data Collection

Claude가 다음 명령을 실행하여 데이터를 수집합니다:

**Step 1: 라벨 기반 수집 (기존)**
```powershell
# Gmail 수집 (wsoptv 라벨)
cd C:\claude && python -m lib.gmail search "label:wsoptv" --limit 50
```

**Step 2: 도메인 기반 보완 수집 (NEW - 라벨 누락 방지)**
```powershell
# 업체 도메인으로 직접 검색 (라벨 없는 메일 포착)
cd C:\claude && python -m lib.gmail search "from:vimeo.com OR from:brightcove.com OR from:megazone.com OR from:jrmax.co.kr OR from:amazon.com newer_than:7d" --limit 50
```

**Step 3: 키워드 기반 보완 수집 (NEW - 새 스레드 포착)**
```powershell
# 견적/제안 관련 키워드 검색
cd C:\claude && python -m lib.gmail search "견적 OR quote OR pricing OR proposal newer_than:7d" --limit 20
```

**Step 4: Slack 메시지 수집**
```powershell
cd C:\claude && python -m lib.slack history C09TX3M1J2W --limit 100
```

수집 데이터:
- Gmail: wsoptv 라벨 이메일 (Step 1)
- Gmail: 업체 도메인 직접 검색 (Step 2) - **라벨 누락 방지**
- Gmail: 견적/제안 키워드 검색 (Step 3) - **새 스레드 포착**
- Slack: #wsoptv 채널의 최근 7일 메시지

**⚠️ 중요**: Step 1만으로는 업체가 새 스레드로 보낸 이메일을 놓칠 수 있음.
반드시 Step 2, 3을 병행하여 라벨이 없는 이메일도 포착해야 함.

### Phase 1.5: Attachment Download & Parse

Gmail 이메일에 첨부된 견적 관련 파일을 분석합니다.

#### Step 0: 인증 확인 (권장)

```powershell
# Gmail 인증 상태 확인
cd C:\claude && python -m lib.gmail status
```

#### Step 1: 견적 첨부파일 식별

이메일 목록에서 첨부파일 메타데이터 확인:
- PDF 파일 (mime_type: application/pdf)
- Excel 파일 (.xlsx, .xls)
- 파일명에 "견적", "quote", "proposal" 포함

#### Step 2: 첨부파일 다운로드

```powershell
# AttachmentDownloader 활용 (캐시 자동 적용)
cd C:\claude\wsoptv_ott && python -c "
from scripts.sync.collectors.attachment_downloader import AttachmentDownloader
from pathlib import Path
import json

downloader = AttachmentDownloader(cache_dir=Path('./attachments'))
attachments = downloader.get_quote_attachments('EMAIL_ID')
print(json.dumps([a.model_dump() for a in attachments], default=str))
"
```

#### Step 3: PDF 분석

**Case A: 20페이지 이하 PDF**
- Claude Read tool로 직접 읽기 (레이아웃 보존)
- Claude가 시각적으로 금액, 테이블 분석

**Case B: 20페이지 초과 PDF**
```powershell
cd C:\claude\wsoptv_ott && python -c "
from scripts.sync.parsers.pdf_parser import get_pdf_parser
from pathlib import Path
import json

parser = get_pdf_parser()
result = parser.extract_all(Path('PATH_TO_PDF'))
print(json.dumps({
    'page_count': result['page_count'],
    'text': result['text'][:5000],  # 토큰 절약
    'table_count': len(result['tables']),
}, ensure_ascii=False))
"
```

#### Step 4: Excel 분석

```powershell
cd C:\claude\wsoptv_ott && python -c "
from scripts.sync.parsers.excel_parser import get_excel_parser
from scripts.sync.extractors.quote_extractor import get_quote_extractor
from pathlib import Path
import json

parser = get_excel_parser()
sheets = parser.parse(Path('PATH_TO_EXCEL'))
extractor = get_quote_extractor()
quotes = extractor.extract_from_excel(sheets)
print(json.dumps([q.model_dump() for q in quotes], default=str))
"
```

#### Step 5: 결과 통합

- 본문에서 추출한 견적 + 첨부파일에서 추출한 견적 병합
- 중복 제거 (동일 금액)
- 신뢰도 높은 것 우선 (첨부파일 > 본문)

### Phase 2: AI Analysis

Claude Code가 수집된 JSON 데이터를 직접 분석합니다.

#### 2.1 이메일 분석

각 업체별 이메일 스레드에서:

1. **견적 정보 추출**
   - 정규식으로 1차 시도 (48억원, 6,600만원 등)
   - 실패 시 AI가 비정형 금액 추론 (약 50억 내외, 40~50억 사이 등)
   - **첨부파일 분석 결과 통합** (Phase 1.5에서 추출한 견적 포함)

2. **협상 상태 추론**
   - 이메일 내용과 톤 분석
   - 현재 단계 판단: initial_contact → rfp_sent → quote_waiting → quote_received → reviewing → negotiating → contract_review
   - 업체 관심도 평가 (HIGH/MEDIUM/LOW)

3. **회신 긴급도 판단**
   - 날짜 기반: 마지막 업체 메일로부터 경과 일수
   - 내용 기반: "ASAP", "빠른 답변", "마감일" 등 키워드
   - 종합 긴급도: CRITICAL (7일+), HIGH (3-7일), MEDIUM (1-3일), LOW (<1일)

#### 2.2 Slack 메시지 분석

팀 논의에서:
- 의사결정 사항 추출
- 액션 아이템 식별
- 업체 관련 언급 요약

### Phase 3: Output Generation

분석 결과를 자연어 보고서로 생성:

```
📊 **WSOPTV 일일 동기화 보고서** (2026-02-04)

### 🚨 즉시 조치 필요

**1. Brightcove** - RE: WSOPTV RFP Follow-up
- 긴급도: CRITICAL (12일 무응답)
- 업체 관심도: HIGH (상세 질문 제기)
- 권장 액션: 금일 중 회신 필요

### 💰 견적 현황

| 업체 | 금액 | 상태 |
|------|------|------|
| MegazoneCloud | 48억 + 15억/년 | 검토 중 |
| Brightcove | 미수령 | 견적 대기 |

### 📈 협상 진행 상황

**MegazoneCloud** - 최우선 검토 중
- 현재: reviewing → negotiating 예상
- 관심도: HIGH
- 평가: 기술적 적합성 높음, 가격 협상 여지

### 🔄 Slack Lists 업데이트 제안

다음 변경사항을 반영할까요?
1. MegazoneCloud: 견적 → "48억 + 15억/년"
2. Brightcove: 상태 → quote_waiting

[업데이트 적용] [건너뛰기]
```

---

## AI 분석 프롬프트

스킬 실행 시 Claude는 다음 프롬프트를 참조합니다:

### 이메일 분석 프롬프트

`.claude/skills/daily-sync/prompts/email_analysis.md` 참조

분석 항목:
- quotes: 금액, 통화, 옵션, 조건
- negotiation_status: 현재 단계, 신뢰도, 근거
- urgency: 긴급도, 요인, 권장 액션
- vendor_interest: 관심도, 지표, 응답 품질

### 상태 추론 프롬프트

`.claude/skills/daily-sync/prompts/status_inference.md` 참조

협상 단계:
- initial_contact: 초기 접촉 (인사, 소개)
- rfp_sent: RFP 발송됨 (요구사항 전달)
- quote_waiting: 견적 대기 (응답 대기)
- quote_received: 견적 수령 (금액 확인)
- reviewing: 검토 중 (내부 검토)
- negotiating: 협상 중 (가격/조건 조율)
- contract_review: 계약 검토 (법무 검토)
- on_hold: 보류 (일시 중단)
- excluded: 제외 (탈락)

---

## 견적 추출 하이브리드 전략

### Step 1: 정규식 추출 (기존 로직)

```python
# 처리 가능한 패턴
"48억원" → 4,800,000,000원
"6,600만원" → 66,000,000원
"50억" → 5,000,000,000원
```

### Step 2: AI 추론 (정규식 실패 시)

```
# AI가 처리하는 패턴
"40~50억 사이" → 범위: 40억~50억
"기본 30억, 풀옵션 시 50억" → 옵션A: 30억, 옵션B: 50억
"대략 50억 내외" → 약 50억 (±10%)
"초기 20억 + 연간 유지비 3억" → 초기: 20억, 연간: 3억
```

---

## 업체 매핑

wsoptv_sync_config.yaml에 정의된 업체:

| 업체 | 주 도메인 | 관련 도메인 | Slack Lists Row |
|------|----------|------------|-----------------|
| MegazoneCloud | @megazone.com | @mz.co.kr | row_001 |
| Brightcove | @brightcove.com | - | row_002 |
| Vimeo OTT | @vimeo.com | @jrmax.co.kr (한국 대리점) | row_003 |
| MalgumSoft | @malgum.com | - | row_004 |
| AWS (파트너 연결) | @amazon.com | - | - (직접 관리 아님) |

**⚠️ 주의**: 업체가 새 스레드로 이메일을 보내면 `wsoptv` 라벨이 없을 수 있음.
반드시 Phase 1의 3단계 검색(라벨 → 도메인 → 키워드)을 모두 수행해야 함.

---

## Slack Lists 업데이트

분석 후 Slack Lists 업데이트를 제안합니다.
사용자 확인 후 기존 `scripts/sync/lists_sync.py`를 통해 업데이트합니다.

```powershell
# 사용자 확인 후 실행
cd C:\claude\wsoptv_ott && python scripts/sync/lists_sync.py update --vendor "MegazoneCloud" --field "견적" --value "48억 + 15억/년"
```

---

## Phase 4: Gmail Housekeeping

Phase 1~3 완료 후, Gmail 라벨 관리 및 INBOX 정리를 자동 수행합니다.

### 4a. 라벨 자동 적용 (자동 실행)

Phase 1의 Step 2/3에서 발견된 업체 이메일 중 WSOPTV 라벨이 없는 것을 자동으로 라벨링합니다.

```python
# Gmail API로 직접 라벨 추가
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

token_path = Path('C:/claude/json/token_gmail.json')
token_data = json.loads(token_path.read_text())
creds = Credentials(
    token=token_data['token'],
    refresh_token=token_data['refresh_token'],
    token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
    client_id=token_data['client_id'],
    client_secret=token_data['client_secret'],
    scopes=token_data.get('scopes', ['https://mail.google.com/'])
)
if creds.expired:
    creds.refresh(Request())

service = build('gmail', 'v1', credentials=creds)
WSOPTV_LABEL_ID = 'Label_8829124364241731876'
```

**필터 규칙:**

| 대상 | 처리 |
|------|------|
| 업체 담당자 이메일 (도메인 매칭) | WSOPTV 라벨 추가 |
| `vimeo@vimeo.com` (시스템 알림) | 제외 |
| `noreply`, `no-reply` 주소 | 제외 |
| `drive-shares` (Google Docs 공유) | 제외 |
| `notifications@` 주소 | 제외 |

**검증 쿼리:**
```python
# 30일 내 업체 도메인 이메일 중 라벨 없는 것 전체 점검
queries = [
    'from:vimeo.com newer_than:30d -label:WSOPTV',
    'from:brightcove.com newer_than:30d -label:WSOPTV',
    'from:megazone.com OR from:mz.co.kr newer_than:30d -label:WSOPTV',
    'from:jrmax.co.kr newer_than:30d -label:WSOPTV',
    'from:amazon.com newer_than:30d -label:WSOPTV',
]
```

### 4b. INBOX 정리 (사용자 확인 후 실행)

WSOPTV 라벨이 적용된 메일을 INBOX에서 제거하여 WSOPTV 폴더에서만 보이도록 합니다.

```python
# WSOPTV + INBOX에 있는 이메일 찾기
result = service.users().messages().list(
    userId='me',
    q='label:WSOPTV label:INBOX',
    maxResults=100
).execute()

# 사용자 확인 후 INBOX 라벨 제거 (archive)
for msg_info in messages:
    service.users().messages().modify(
        userId='me',
        id=msg_info['id'],
        body={'removeLabelIds': ['INBOX']}
    ).execute()
```

**안전장치:**

| 조건 | 동작 |
|------|------|
| UNREAD 메일 | AskUserQuestion으로 사용자 확인 필수 |
| READ 메일 | `--auto-archive` 시 자동 이동, 기본은 확인 |
| `--keep-inbox` 플래그 | Phase 4b 완전 건너뛰기 |

### 4c. 결과 보고

보고서 마지막에 Gmail 정리 결과를 추가합니다:

```
### Gmail 정리
- WSOPTV 라벨 적용: 3건 (Vimeo 2, Brightcove 1)
- INBOX → WSOPTV 이동: 3건
- 건너뛴 시스템 메일: 45건 (Vimeo 업로드 알림)
```

### Phase 4 옵션

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--no-label` | false | Phase 4a 건너뛰기 (라벨 적용 안함) |
| `--auto-archive` | false | Phase 4b 사용자 확인 없이 자동 이동 |
| `--keep-inbox` | false | Phase 4b 완전 건너뛰기 (INBOX 유지) |

---

### Phase 5: Slack Lists 갱신 (`--slack` 옵션 시)

`/auto --daily --slack` 실행 시, Phase 1~4 완료 후 Slack Lists 업체 현황을 자동 갱신합니다.

**트리거**: `/auto --daily --slack` 또는 `.project-sync.yaml`의 `daily.sources.slack_lists.enabled: true`

#### 5a. 분석 결과 → Slack Lists 업데이트

Phase 2 AI 분석 결과를 기반으로 업체별 필드를 업데이트합니다.

```python
# ListsSyncManager로 업체별 업데이트
from scripts.sync.lists_sync import ListsSyncManager

manager = ListsSyncManager()
manager.update_item('Vimeo OTT',
    status='협상 중',
    quote='Fixed $115K/yr + Infra $10K-$275K/yr',
    last_contact='2026-02-06',
    next_action='수정 견적 대기')
```

**업데이트 필드 매핑:**

| AI 분석 결과 | Slack Lists 필드 | 규칙 |
|-------------|-----------------|------|
| 협상 상태 | `status` | `wsoptv_sync_config.yaml` status_options 매핑 |
| 견적 금액 | `quote` | QuoteFormatter 3줄 이내 |
| 마지막 연락일 | `last_contact` | 최신 이메일 날짜 |
| 권장 액션 | `next_action` | AI 권장 사항 |

**안전장치:**

| 조건 | 동작 |
|------|------|
| status가 부정 방향 (on_hold, excluded) | AskUserQuestion 확인 필수 |
| 견적 금액 변경 | 기존 → 새 값 비교 출력 후 적용 |
| 새 업체 발견 | 자동 추가 안함, 사용자 확인 |

#### 5b. 요약 메시지 Slack 채널 포스팅

```python
manager.generate_summary_message()
manager.post_summary()
```

#### 5c. 결과 보고

```
### Slack Lists 갱신 결과
- Vimeo OTT: status → "협상 중", quote 업데이트
- Brightcove: last_contact → "2026-02-06"
- 요약 메시지: #wsoptv 채널에 포스팅 완료
```

---

## 토큰 효율성

### 증분 분석

- 이전 분석 결과를 `.sync_state.json`에 캐시
- 새로운 이메일/메시지만 분석
- 2회차부터 약 70% 토큰 절감

### 배치 그룹핑

- 업체별로 이메일을 그룹화
- 한 번의 분석으로 업체당 모든 정보 추출

---

## 관련 파일

| 파일 | 용도 |
|------|------|
| `wsoptv_sync_config.yaml` | 업체 매핑, 설정 |
| `docs/management/.sync_state.json` | 동기화 상태 |
| `scripts/sync/lists_sync.py` | Slack Lists 업데이트 |
| `lib/gmail/` | Gmail API 래퍼 |
| `lib/slack/` | Slack API 래퍼 |

---

## 트러블슈팅

### Gmail 인증 오류

```powershell
cd C:\claude && python -m lib.gmail login
```

### Slack 토큰 만료

```powershell
cd C:\claude && python -m lib.slack login
```

### 분석 결과가 부정확한 경우

1. `--days 7`로 짧은 기간 테스트
2. 특정 업체만 `--vendor <name>`으로 분석
3. 원본 이메일 확인 후 피드백

---

## 변경 로그

### v1.4.0 (2026-02-06)

- Phase 5: Slack Lists 자동 갱신 추가 (--slack 옵션 연동)
- `.project-sync.yaml` 기반 Project Context Discovery 연동
- ListsSyncManager를 통한 업체 상태/견적/next_action 자동 업데이트
- 안전장치: 부정 상태 변경 시 사용자 확인, 견적 변경 비교 출력

### v1.3.0 (2026-02-06)

- Phase 4: Gmail Housekeeping 추가
- 4a: 업체 이메일 WSOPTV 라벨 자동 적용 (시스템 메일 필터링)
- 4b: INBOX → WSOPTV 폴더 이동 (사용자 확인 후)
- 4c: 라벨/이동 결과 보고서 추가
- 옵션: `--no-label`, `--auto-archive`, `--keep-inbox`

### v1.2.0 (2026-02-05)

- QuoteFormatter 시스템 추가 (상황 적응형 포맷)
- USD 기준 통화 통일 (환율 1,375원/USD 고정)
- 예산 비교는 요약 메시지에서만 표시
- Slack Lists quote 필드 3줄 이내 최적화
- 업체별 자동 포맷 전략 선택 (decision/negotiation/hybrid)

### v1.1.0 (2026-02-04)

- Phase 1.5 첨부파일 분석 추가
- PDF 분석: Claude Read (≤20p) + pdfplumber (>20p) 하이브리드
- Excel 분석: QuoteExtractor 통합
- 견적 추출 신뢰도 향상: 첨부파일 > 본문 우선

### v1.0.0 (2026-02-04)

- 초기 릴리스
- Gmail/Slack 데이터 수집
- AI 기반 견적 추출 (하이브리드)
- AI 기반 협상 상태 추론
- AI 기반 긴급도 판단
- 자연어 보고서 생성
- Slack Lists 업데이트 제안
