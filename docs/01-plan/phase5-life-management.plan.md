# Secretary Phase 5: Life Management Integration Plan

**Version**: 1.0.0
**Created**: 2026-02-02
**Status**: DRAFT
**Prerequisites**: Phase 1-3 Complete (Gmail, Calendar, GitHub, Slack, LLM, Actions)

---

## 1. Vision and Goals

### 1.1 Project Vision

Secretary를 **업무 분석 도구**에서 **통합 생활 관리 비서**로 확장한다. MS To Do 연동, 생활 이벤트 리마인더, 법인 세무 자동화를 통해 업무와 개인 일정을 하나의 시스템에서 관리한다.

### 1.2 Core Goals

| Goal | Description | Success Metric |
|------|-------------|----------------|
| **MS To Do 연동** | Push-only 동기화로 TODO 자동 생성 | 중복 없이 항목 생성 |
| **Life Event 관리** | 명절/기념일 자동 리마인더 | D-14, D-7, D-3 단계별 알림 |
| **세무 자동화** | 법인 정기 세무 일정 자동 생성 | Calendar 반복 일정 생성 |
| **통합 뷰** | 업무 + 개인 일정 통합 대시보드 | 단일 리포트로 확인 |

### 1.3 Non-Goals (Phase 5에서 제외)

- MS To Do 양방향 동기화 (선택: Push-only)
- 복잡한 충돌 해결 로직
- 실시간 알림 (Toast 기반 유지)
- 모바일 앱 개발

---

## 2. Architecture Design

### 2.1 High-Level Architecture

```
                    +---------------------------------------------------+
                    |              Secretary Phase 5                     |
                    |           Life Management Layer                    |
                    +---------------------------------------------------+
                                          |
        +----------------+----------------+----------------+
        |                |                |                |
        v                v                v                v
+---------------+  +---------------+  +---------------+  +---------------+
|  MS To Do     |  |  Life Event   |  |  Tax Calendar |  |  Unified      |
|  Adapter      |  |  Manager      |  |  Automation   |  |  Dashboard    |
+---------------+  +---------------+  +---------------+  +---------------+
        |                |                |                |
        v                v                v                v
+---------------+  +---------------+  +---------------+  +---------------+
| Microsoft     |  | Config Files  |  | Google        |  | Daily Report  |
| Graph API     |  | (JSON)        |  | Calendar API  |  | Integration   |
+---------------+  +---------------+  +---------------+  +---------------+
```

### 2.2 Component Design

#### 2.2.1 MS To Do Adapter

```python
# scripts/integrations/mstodo_adapter.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum

class TodoList(Enum):
    PERSONAL = "personal"
    BUSINESS = "business"

@dataclass
class TodoItem:
    """MS To Do 항목 데이터 모델"""
    title: str
    body: Optional[str] = None
    due_date: Optional[datetime] = None
    importance: str = "normal"  # low, normal, high
    list_type: TodoList = TodoList.PERSONAL

    # Duplicate detection fields
    source: str = "secretary"  # 출처 식별
    source_id: Optional[str] = None  # 원본 ID (이메일 ID 등)

class MSTodoAdapter:
    """
    MS To Do Push-only Adapter

    Features:
    - Browser OAuth 인증 (Graph API)
    - 리스트별 항목 추가 (개인/법인)
    - 중복 체크 (제목 + 날짜 기반)
    """

    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    SCOPES = ["Tasks.ReadWrite", "User.Read"]

    async def push_todo(self, item: TodoItem) -> dict:
        """
        TODO 항목 추가 (Push-only)

        1. 중복 체크 (제목 + 날짜)
        2. 중복 아니면 생성
        3. 결과 반환
        """
        pass

    async def check_duplicate(self, item: TodoItem) -> bool:
        """제목 + 날짜 기반 중복 체크"""
        pass

    async def get_lists(self) -> List[dict]:
        """사용자의 To Do 리스트 조회"""
        pass
```

#### 2.2.2 Life Event Manager

```python
# scripts/life/event_manager.py
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from enum import Enum

class EventType(Enum):
    LUNAR_HOLIDAY = "lunar_holiday"  # 명절 (음력)
    ANNIVERSARY = "anniversary"       # 기념일 (양력)
    BIRTHDAY = "birthday"            # 생일 (양력/음력)

@dataclass
class LifeEvent:
    """생활 이벤트 데이터 모델"""
    name: str
    event_type: EventType
    month: int
    day: int
    is_lunar: bool = False
    reminder_days: List[int] = None  # [14, 7, 3] = D-14, D-7, D-3

    def __post_init__(self):
        if self.reminder_days is None:
            self.reminder_days = [14, 7, 3]

class LifeEventManager:
    """
    생활 이벤트 관리자

    Features:
    - 음력/양력 변환 (korean_lunar_calendar)
    - 명절 자동 감지 (설날, 추석)
    - 기념일 설정 파일 로드
    - D-N 리마인더 생성
    """

    # 고정 명절 (음력)
    KOREAN_HOLIDAYS = [
        LifeEvent("설날", EventType.LUNAR_HOLIDAY, 1, 1, is_lunar=True),
        LifeEvent("추석", EventType.LUNAR_HOLIDAY, 8, 15, is_lunar=True),
    ]

    def get_upcoming_events(self, days: int = 30) -> List[dict]:
        """앞으로 N일 내 이벤트 조회"""
        pass

    def lunar_to_solar(self, year: int, month: int, day: int) -> date:
        """음력 -> 양력 변환"""
        pass

    def get_reminder_dates(self, event: LifeEvent, target_year: int) -> List[date]:
        """이벤트의 리마인더 날짜 목록 반환"""
        pass
```

#### 2.2.3 Tax Calendar Automation

```python
# scripts/life/tax_calendar.py
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from enum import Enum

class TaxEventFrequency(Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

@dataclass
class TaxEvent:
    """세무 이벤트 데이터 모델"""
    name: str
    frequency: TaxEventFrequency
    day: int  # 매월/분기/연도의 N일
    month: Optional[int] = None  # 연간 이벤트용
    quarter_months: Optional[List[int]] = None  # 분기별 이벤트용 [1,4,7,10]
    reminder_days: List[int] = None

    def __post_init__(self):
        if self.reminder_days is None:
            self.reminder_days = [7, 3, 1]

class TaxCalendarManager:
    """
    법인 세무 일정 관리자

    Features:
    - 월별 정기 일정 (원천세, 4대보험)
    - 분기별 일정 (부가세)
    - 연간 일정 (법인세)
    - Google Calendar 반복 일정 생성
    """

    # 법인 세무 일정 (한국 기준)
    CORPORATE_TAX_EVENTS = [
        # 월별
        TaxEvent("원천세 신고/납부", TaxEventFrequency.MONTHLY, 10),
        TaxEvent("4대보험 납부", TaxEventFrequency.MONTHLY, 10),

        # 분기별
        TaxEvent("부가세 신고/납부", TaxEventFrequency.QUARTERLY, 25,
                 quarter_months=[1, 4, 7, 10]),

        # 연간
        TaxEvent("법인세 신고/납부", TaxEventFrequency.YEARLY, 31, month=3),
        TaxEvent("지방소득세 신고/납부", TaxEventFrequency.YEARLY, 30, month=4),
    ]

    def generate_calendar_events(self, year: int) -> List[dict]:
        """연간 세무 일정 생성"""
        pass

    def create_recurring_event(self, event: TaxEvent) -> dict:
        """Google Calendar 반복 일정 생성"""
        pass
```

### 2.3 Data Flow

```
+------------------------------------------------------------------------+
|                          PHASE 5 DATA FLOW                              |
+------------------------------------------------------------------------+

1. MS To Do Push Flow
   +------------+    +---------------+    +---------------+    +----------+
   | Daily      |--->| TODO          |--->| MS To Do      |--->| Graph    |
   | Report     |    | Generator     |    | Adapter       |    | API      |
   +------------+    +---------------+    +---------------+    +----------+
                           |                    |
                           v                    v
                     +-----------+        +-----------+
                     | Duplicate |        | List      |
                     | Check     |        | Selector  |
                     +-----------+        +-----------+

2. Life Event Reminder Flow
   +------------+    +---------------+    +---------------+    +----------+
   | Config     |--->| Life Event    |--->| Reminder      |--->| Toast    |
   | (JSON)     |    | Manager       |    | Generator     |    | Notifier |
   +------------+    +---------------+    +---------------+    +----------+
        |                  |
        v                  v
   +-----------+     +-----------+
   | User      |     | Lunar     |
   | Events    |     | Converter |
   +-----------+     +-----------+

3. Tax Calendar Automation Flow
   +------------+    +---------------+    +---------------+    +----------+
   | Tax Event  |--->| Tax Calendar  |--->| Calendar      |--->| Google   |
   | Config     |    | Manager       |    | Creator       |    | Calendar |
   +------------+    +---------------+    +---------------+    +----------+
                           |
                           v
                     +-----------+
                     | Recurring |
                     | Event Gen |
                     +-----------+
```

---

## 3. Detailed Specifications

### 3.1 MS To Do Integration

#### 3.1.1 Authentication Flow

```
+------------------------------------------------------------------+
|                    MS To Do OAuth Flow                            |
+------------------------------------------------------------------+

1. First Run (No Token)
   +--------+    +---------------+    +---------------+    +--------+
   | User   |--->| Browser OAuth |--->| Microsoft     |--->| Token  |
   | CLI    |    | (localhost)   |    | Login         |    | Save   |
   +--------+    +---------------+    +---------------+    +--------+

2. Subsequent Runs (Token Exists)
   +--------+    +---------------+    +---------------+    +--------+
   | User   |--->| Load Token    |--->| Refresh if    |--->| API    |
   | CLI    |    | from file     |    | Expired       |    | Call   |
   +--------+    +---------------+    +---------------+    +--------+

Token Location: C:\claude\json\token_mstodo.json
```

#### 3.1.2 API Endpoints

| Operation | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| Get Lists | GET | `/me/todo/lists` | 사용자 리스트 조회 |
| Get Tasks | GET | `/me/todo/lists/{id}/tasks` | 리스트 내 태스크 조회 |
| Create Task | POST | `/me/todo/lists/{id}/tasks` | 태스크 생성 |
| Get Task | GET | `/me/todo/lists/{id}/tasks/{taskId}` | 개별 태스크 조회 |

#### 3.1.3 Duplicate Detection Algorithm

```python
def check_duplicate(self, item: TodoItem) -> bool:
    """
    중복 체크 알고리즘:

    1. 동일 리스트 내 태스크 조회
    2. 제목 정규화 (소문자, 공백 제거)
    3. 날짜 비교 (due_date 동일)
    4. 둘 다 일치하면 중복으로 판단

    Returns:
        True if duplicate exists, False otherwise
    """
    existing_tasks = await self.get_tasks(item.list_type)

    normalized_title = normalize_title(item.title)

    for task in existing_tasks:
        if (normalize_title(task['title']) == normalized_title and
            task.get('dueDateTime', {}).get('dateTime') == item.due_date.isoformat()):
            return True

    return False

def normalize_title(title: str) -> str:
    """제목 정규화: 소문자 변환, 연속 공백 제거"""
    return ' '.join(title.lower().split())
```

#### 3.1.4 List Configuration

```json
// config/mstodo.json
{
  "enabled": true,
  "lists": {
    "personal": {
      "name": "Secretary - 개인",
      "id": null,  // 첫 실행 시 자동 생성 후 저장
      "auto_create": true
    },
    "business": {
      "name": "Secretary - 법인",
      "id": null,
      "auto_create": true
    }
  },
  "default_list": "personal",
  "duplicate_check": true,
  "importance_mapping": {
    "high": "high",
    "medium": "normal",
    "low": "low"
  }
}
```

### 3.2 Life Event Management

#### 3.2.1 Event Configuration Schema

```json
// config/life_events.json
{
  "events": [
    {
      "name": "어머니 생신",
      "type": "birthday",
      "month": 5,
      "day": 15,
      "is_lunar": true,
      "reminder_days": [14, 7, 3],
      "actions": ["toast", "calendar", "todo"]
    },
    {
      "name": "결혼기념일",
      "type": "anniversary",
      "month": 10,
      "day": 20,
      "is_lunar": false,
      "reminder_days": [14, 7, 3, 1],
      "actions": ["toast", "calendar"]
    }
  ],
  "holidays": {
    "seollal": {
      "enabled": true,
      "reminder_days": [14, 7, 3]
    },
    "chuseok": {
      "enabled": true,
      "reminder_days": [14, 7, 3]
    }
  },
  "default_reminder_days": [14, 7, 3]
}
```

#### 3.2.2 Lunar Calendar Conversion

```python
# korean_lunar_calendar 라이브러리 사용
from korean_lunar_calendar import KoreanLunarCalendar

def lunar_to_solar(year: int, month: int, day: int) -> date:
    """
    음력 -> 양력 변환

    Args:
        year: 양력 연도 (해당 연도의 음력 날짜를 양력으로 변환)
        month: 음력 월
        day: 음력 일

    Returns:
        양력 date 객체
    """
    calendar = KoreanLunarCalendar()
    calendar.setLunarDate(year, month, day, False)  # False = 윤달 아님

    return date(
        calendar.solarYear,
        calendar.solarMonth,
        calendar.solarDay
    )

# 예시: 2026년 설날 (음력 1월 1일)
seollal_2026 = lunar_to_solar(2026, 1, 1)
# 결과: 2026-02-17 (양력)
```

#### 3.2.3 Reminder Generation Logic

```python
def get_reminders_for_today(self) -> List[dict]:
    """
    오늘 발송해야 할 리마인더 목록 생성

    Logic:
    1. 모든 이벤트 로드 (설정 파일 + 명절)
    2. 각 이벤트의 올해 날짜 계산 (음력 변환 포함)
    3. 오늘과의 D-day 계산
    4. reminder_days에 포함되면 리마인더 생성
    """
    reminders = []
    today = date.today()
    current_year = today.year

    for event in self.get_all_events():
        # 이벤트 날짜 계산
        if event.is_lunar:
            event_date = self.lunar_to_solar(current_year, event.month, event.day)
        else:
            event_date = date(current_year, event.month, event.day)

        # D-day 계산
        days_until = (event_date - today).days

        # 리마인더 체크
        if days_until in event.reminder_days:
            reminders.append({
                "event": event.name,
                "date": event_date.isoformat(),
                "days_until": days_until,
                "message": f"{event.name} D-{days_until}"
            })

    return reminders
```

### 3.3 Tax Calendar Automation

#### 3.3.1 Tax Event Definitions

| 이벤트 | 빈도 | 기준일 | 설명 |
|--------|------|--------|------|
| 원천세 신고/납부 | 월별 | 매월 10일 | 전월분 |
| 4대보험 납부 | 월별 | 매월 10일 | 당월분 |
| 부가세 신고/납부 | 분기별 | 1/4/7/10월 25일 | 전분기분 |
| 법인세 신고/납부 | 연간 | 3월 31일 | 전년도분 (12월 결산법인) |
| 지방소득세 신고/납부 | 연간 | 4월 30일 | 법인세 연동 |

#### 3.3.2 Configuration Schema

```json
// config/tax_calendar.json
{
  "enabled": true,
  "company_type": "corporation",  // corporation, sole_proprietor
  "fiscal_year_end": 12,  // 결산월
  "events": {
    "withholding_tax": {
      "enabled": true,
      "name": "원천세 신고/납부",
      "frequency": "monthly",
      "day": 10,
      "reminder_days": [7, 3, 1],
      "calendar_color": "#FF6B6B"
    },
    "social_insurance": {
      "enabled": true,
      "name": "4대보험 납부",
      "frequency": "monthly",
      "day": 10,
      "reminder_days": [7, 3, 1],
      "calendar_color": "#4ECDC4"
    },
    "vat": {
      "enabled": true,
      "name": "부가세 신고/납부",
      "frequency": "quarterly",
      "day": 25,
      "quarter_months": [1, 4, 7, 10],
      "reminder_days": [14, 7, 3, 1],
      "calendar_color": "#45B7D1"
    },
    "corporate_tax": {
      "enabled": true,
      "name": "법인세 신고/납부",
      "frequency": "yearly",
      "month": 3,
      "day": 31,
      "reminder_days": [30, 14, 7, 3, 1],
      "calendar_color": "#96CEB4"
    },
    "local_income_tax": {
      "enabled": true,
      "name": "지방소득세 신고/납부",
      "frequency": "yearly",
      "month": 4,
      "day": 30,
      "reminder_days": [14, 7, 3, 1],
      "calendar_color": "#FFEAA7"
    }
  },
  "calendar_settings": {
    "calendar_name": "Secretary - 세무",
    "default_reminder_minutes": [1440, 60],  // 하루 전, 1시간 전
    "all_day_event": true
  }
}
```

#### 3.3.3 Google Calendar Recurring Event

```python
def create_recurring_tax_event(self, event: TaxEvent, year: int) -> dict:
    """
    Google Calendar 반복 일정 생성

    RRULE 예시:
    - 월별: RRULE:FREQ=MONTHLY;BYMONTHDAY=10
    - 분기별: RRULE:FREQ=YEARLY;BYMONTH=1,4,7,10;BYMONTHDAY=25
    - 연간: RRULE:FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=31
    """
    calendar_event = {
        "summary": event.name,
        "description": f"Secretary 자동 생성 - {event.frequency.value}",
        "start": {
            "date": self._get_first_occurrence(event, year),
            "timeZone": "Asia/Seoul"
        },
        "end": {
            "date": self._get_first_occurrence(event, year),
            "timeZone": "Asia/Seoul"
        },
        "recurrence": [self._build_rrule(event)],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": d * 24 * 60}
                for d in event.reminder_days
            ]
        },
        "colorId": self._get_color_id(event)
    }

    return calendar_event

def _build_rrule(self, event: TaxEvent) -> str:
    """RRULE 문자열 생성"""
    if event.frequency == TaxEventFrequency.MONTHLY:
        return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={event.day}"
    elif event.frequency == TaxEventFrequency.QUARTERLY:
        months = ",".join(map(str, event.quarter_months))
        return f"RRULE:FREQ=YEARLY;BYMONTH={months};BYMONTHDAY={event.day}"
    elif event.frequency == TaxEventFrequency.YEARLY:
        return f"RRULE:FREQ=YEARLY;BYMONTH={event.month};BYMONTHDAY={event.day}"
```

---

## 4. Implementation Plan

### Phase 5.1: MS To Do Adapter (Week 1)

**Goal**: Microsoft Graph API 연동 및 Push-only 동기화 구현

#### Tasks

| ID | Task | Complexity | Hours |
|----|------|------------|-------|
| 5.1.1 | Azure AD 앱 등록 (Graph API 권한) | LOW | 2 |
| 5.1.2 | MSAL 인증 플로우 구현 (Browser OAuth) | HIGH | 8 |
| 5.1.3 | MSTodoAdapter 기본 구조 | MEDIUM | 4 |
| 5.1.4 | 리스트 조회/생성 API | MEDIUM | 4 |
| 5.1.5 | 태스크 생성 API | MEDIUM | 4 |
| 5.1.6 | 중복 체크 로직 구현 | MEDIUM | 4 |
| 5.1.7 | 리스트 분리 (개인/법인) | LOW | 2 |
| 5.1.8 | CLI 인터페이스 | LOW | 2 |
| 5.1.9 | 단위 테스트 | MEDIUM | 4 |

**Deliverables**:
- `scripts/integrations/mstodo_adapter.py`
- `scripts/integrations/mstodo_auth.py`
- `config/mstodo.json`
- `tests/test_mstodo_adapter.py`

#### Azure AD App Configuration

```
1. Azure Portal > Azure Active Directory > App registrations
2. New registration:
   - Name: Secretary MS To Do
   - Supported account types: Personal Microsoft accounts only
   - Redirect URI: http://localhost:8400 (Web)
3. API permissions:
   - Microsoft Graph > Delegated > Tasks.ReadWrite
   - Microsoft Graph > Delegated > User.Read
4. Client secret 생성 (불필요 - Public client로 설정)
5. Authentication > Allow public client flows: Yes
```

---

### Phase 5.2: Life Event Manager (Week 2)

**Goal**: 음력 변환 및 생활 이벤트 리마인더 시스템 구현

#### Tasks

| ID | Task | Complexity | Hours |
|----|------|------------|-------|
| 5.2.1 | korean_lunar_calendar 라이브러리 통합 | LOW | 2 |
| 5.2.2 | LifeEvent 데이터 모델 | LOW | 2 |
| 5.2.3 | LifeEventManager 구현 | MEDIUM | 6 |
| 5.2.4 | 음력/양력 변환 로직 | MEDIUM | 4 |
| 5.2.5 | 명절 자동 감지 (설날, 추석) | MEDIUM | 4 |
| 5.2.6 | 기념일 설정 파일 파싱 | LOW | 2 |
| 5.2.7 | D-N 리마인더 생성 로직 | MEDIUM | 4 |
| 5.2.8 | Toast 알림 연동 | LOW | 2 |
| 5.2.9 | CLI 인터페이스 | LOW | 2 |
| 5.2.10 | 단위 테스트 | MEDIUM | 4 |

**Deliverables**:
- `scripts/life/event_manager.py`
- `scripts/life/lunar_converter.py`
- `config/life_events.json`
- `tests/test_life_events.py`

---

### Phase 5.3: Tax Calendar Automation (Week 3)

**Goal**: 법인 세무 일정 자동화 및 Calendar 반복 일정 생성

#### Tasks

| ID | Task | Complexity | Hours |
|----|------|------------|-------|
| 5.3.1 | TaxEvent 데이터 모델 | LOW | 2 |
| 5.3.2 | TaxCalendarManager 구현 | MEDIUM | 6 |
| 5.3.3 | RRULE 생성 로직 | HIGH | 6 |
| 5.3.4 | Google Calendar 반복 일정 생성 | HIGH | 6 |
| 5.3.5 | calendar_creator.py 확장 | MEDIUM | 4 |
| 5.3.6 | 세무 일정 설정 파일 | LOW | 2 |
| 5.3.7 | CLI 인터페이스 | LOW | 2 |
| 5.3.8 | 단위 테스트 | MEDIUM | 4 |

**Deliverables**:
- `scripts/life/tax_calendar.py`
- `config/tax_calendar.json`
- `tests/test_tax_calendar.py`

---

### Phase 5.4: Integration & Testing (Week 4)

**Goal**: 전체 시스템 통합 및 Daily Report 연동

#### Tasks

| ID | Task | Complexity | Hours |
|----|------|------------|-------|
| 5.4.1 | daily_report.py Phase 5 연동 | MEDIUM | 6 |
| 5.4.2 | 통합 대시보드 섹션 추가 | MEDIUM | 4 |
| 5.4.3 | todo_generator.py MS To Do 연동 | MEDIUM | 4 |
| 5.4.4 | 초기 설정 마법사 (CLI) | MEDIUM | 4 |
| 5.4.5 | E2E 테스트 | HIGH | 8 |
| 5.4.6 | 문서화 (CLAUDE.md 업데이트) | LOW | 2 |
| 5.4.7 | 버그 수정 및 최적화 | MEDIUM | 4 |

**Deliverables**:
- `scripts/daily_report.py` (업데이트)
- `scripts/actions/todo_generator.py` (업데이트)
- `scripts/setup_phase5.py` (초기 설정)
- `docs/PHASE5_SETUP.md`

---

## 5. File Structure

```
C:\claude\secretary\
+-- scripts/
|   +-- integrations/
|   |   +-- __init__.py
|   |   +-- mstodo_adapter.py      # MS To Do Push Adapter
|   |   +-- mstodo_auth.py         # MSAL OAuth 인증
|   +-- life/
|   |   +-- __init__.py
|   |   +-- event_manager.py       # Life Event Manager
|   |   +-- lunar_converter.py     # 음력/양력 변환
|   |   +-- tax_calendar.py        # Tax Calendar Automation
|   +-- actions/
|   |   +-- todo_generator.py      # (업데이트) MS To Do 연동
|   |   +-- calendar_creator.py    # (업데이트) 반복 일정 지원
|   +-- daily_report.py            # (업데이트) Phase 5 통합
|   +-- setup_phase5.py            # 초기 설정 마법사
+-- config/
|   +-- mstodo.json                # MS To Do 설정
|   +-- life_events.json           # 생활 이벤트 설정
|   +-- tax_calendar.json          # 세무 일정 설정
+-- tests/
|   +-- test_mstodo_adapter.py
|   +-- test_life_events.py
|   +-- test_tax_calendar.py
|   +-- test_phase5_integration.py
+-- docs/
|   +-- 01-plan/
|   |   +-- phase5-life-management.plan.md  # This file
|   +-- PHASE5_SETUP.md            # 설정 가이드
```

---

## 6. Dependencies

### 6.1 New Python Libraries

```
# requirements.txt 추가
msal>=1.24.0                    # Microsoft Authentication Library
korean-lunar-calendar>=0.3.1    # 음력/양력 변환
```

### 6.2 External Services

| Service | Purpose | Setup Required |
|---------|---------|----------------|
| Azure AD | MS Graph API 인증 | App registration |
| Microsoft Graph | MS To Do API | API permissions |
| Google Calendar | 기존 (Phase 3) | - |

---

## 7. Safety Considerations

### 7.1 MS To Do Safety Rules

| Rule | Implementation |
|------|----------------|
| Push-only | 읽기 후 덮어쓰기 금지, 추가만 허용 |
| 중복 체크 | 동일 항목 중복 생성 방지 |
| 삭제 금지 | MS To Do 항목 삭제 API 미사용 |
| 완료 처리 금지 | Secretary가 완료 상태 변경 안함 |

### 7.2 Calendar Safety Rules

| Rule | Implementation |
|------|----------------|
| --confirm 필수 | 실제 생성 시 명시적 확인 (기존 규칙 유지) |
| 별도 캘린더 | Secretary 전용 캘린더 사용 권장 |
| 반복 일정 주의 | 반복 일정 생성 전 dry-run 필수 |

---

## 8. Success Criteria

### 8.1 Phase 5 Complete Criteria

| Criterion | Measurement | Target |
|-----------|-------------|--------|
| MS To Do 연동 | 항목 생성 성공률 | > 99% |
| 중복 방지 | 중복 생성 건수 | 0건 |
| 음력 변환 | 변환 정확도 | 100% |
| 리마인더 발송 | D-N 정시 발송률 | > 95% |
| 세무 일정 | Calendar 생성 성공률 | > 99% |

### 8.2 Code Quality

| Metric | Target |
|--------|--------|
| Test Coverage | >= 80% |
| Type Hints | 100% (public API) |
| Documentation | 모든 public 함수 docstring |
| Linting | ruff clean |

---

## 9. Timeline Summary

```
Week 1  | Phase 5.1: MS To Do Adapter
        |   - Azure AD 설정
        |   - MSAL 인증 구현
        |   - Push-only 동기화

Week 2  | Phase 5.2: Life Event Manager
        |   - 음력 변환 구현
        |   - 명절/기념일 관리
        |   - D-N 리마인더

Week 3  | Phase 5.3: Tax Calendar Automation
        |   - 세무 일정 정의
        |   - RRULE 생성
        |   - Calendar 반복 일정

Week 4  | Phase 5.4: Integration & Testing
        |   - Daily Report 연동
        |   - E2E 테스트
        |   - 문서화
```

**Total Duration**: 4 weeks
**Estimated Hours**: ~120 hours

---

## 10. CLI Commands (Proposed)

```powershell
# MS To Do
python scripts/integrations/mstodo_adapter.py login       # OAuth 인증
python scripts/integrations/mstodo_adapter.py lists       # 리스트 조회
python scripts/integrations/mstodo_adapter.py push --title "제목" --list personal

# Life Events
python scripts/life/event_manager.py upcoming --days 30   # 앞으로 30일 이벤트
python scripts/life/event_manager.py reminders            # 오늘의 리마인더
python scripts/life/event_manager.py add --name "이벤트" --date "5-15" --lunar

# Tax Calendar
python scripts/life/tax_calendar.py generate --year 2026  # 연간 일정 생성 (dry-run)
python scripts/life/tax_calendar.py generate --year 2026 --confirm  # 실제 생성
python scripts/life/tax_calendar.py list                  # 설정된 세무 일정 목록

# Daily Report with Phase 5
python scripts/daily_report.py --all --life              # Life 섹션 포함
python scripts/daily_report.py --life-only               # Life 섹션만
```

---

## 11. Next Steps

1. **Immediate**: 이 계획 문서 리뷰 및 승인
2. **Azure AD 설정**: MS Graph API 앱 등록
3. **Phase 5.1 착수**: MS To Do Adapter 구현 시작
4. **테스트 데이터 준비**: 생활 이벤트 샘플 JSON 작성

---

**Document End**
