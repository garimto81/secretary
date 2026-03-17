# Secretary Work Tracker PRD

## 개요

- **목적**: 34개 서브 레포(`C:\claude\*`) git 활동 자동 수집 → 일일/주간 업무 현황 Slack 공유
- **배경**: Q1 주간 보고서 작성 시 31개 Work Stream 중 9개 기간 불일치 발견. 수동 추적의 한계
- **범위**: git log 수집 → Work Stream 감지 → 성과 지표 → Slack 포맷팅 → 자동 전송

## Market Context

- **페인포인트**: 매일 어떤 업무를 했는지 자동 정리 시스템 부재. 주간 보고 시 git 히스토리 수동 조회 필요
- **비즈니스 Impact**: 보고서 정확도 향상 (기간 불일치 9건 → 0건 목표), 일일 보고 자동화로 작성 시간 30분 → 0분
- **Appetite**: Small (2주)

## 요구사항

### FR-1: 일일 Git 수집 (collector.py)

- `C:\claude\*\.git` 글로브로 모든 서브 레포 자동 탐색
- `git log --since={date} --until={date} --format="%H|%s|%an|%ai|%D" --stat` 파싱
- Conventional Commit 분류: `type(scope): message` → type, scope 추출
- `config/projects.json`의 `local_repo_mapping`으로 프로젝트(EBS/WSOPTV/Secretary/기타) 분류
- 출력: `List[DailyCommit]` (repo, hash, type, scope, message, author, timestamp, files_changed, insertions, deletions)

local_repo_mapping 예시:
```json
{
  "local_repo_mapping": {
    "ebs": {"project": "EBS", "category": "기획"},
    "ebs_reverse": {"project": "EBS", "category": "역공학"},
    "ebs_reverse_app": {"project": "EBS", "category": "앱 개발"},
    "ui_overlay": {"project": "EBS", "category": "UI 분석"},
    "figma": {"project": "EBS", "category": "디자인"},
    "wsoptv_ott": {"project": "WSOPTV", "category": "OTT"},
    "wsop_academy": {"project": "WSOPTV", "category": "Academy"},
    "secretary": {"project": "Secretary", "category": "자동화"},
    "task_manager": {"project": "Secretary", "category": "태스크"}
  }
}
```

### FR-2: Work Stream 감지 (stream_detector.py)

Work Stream = 여러 날에 걸친 연속 업무 단위. 감지 로직 4가지:

1. **브랜치명 패턴**: `feat/xxx`, `fix/xxx` → stream "xxx"
2. **Conventional Commit scope**: `docs(prd):`, `feat(overlay):` → scope를 stream 키로 추출
3. **문서 경로 연속성**: 같은 파일/디렉토리가 다주간 수정 → 동일 stream으로 그룹핑
4. **AI 키워드 클러스터링**: "역공학", "reverse", "reverse engineering" → 같은 stream (Ollama 활용)

Stream 상태:
- `active`: 최근 7일 내 커밋 있음
- `idle`: 7~30일 미활동
- `completed`: 브랜치 merged 또는 30일+ 미활동
- `new`: 오늘 최초 감지

출력: `List[WorkStream]` (name, project, repos, first_commit, last_commit, total_commits, status, duration_days)

### FR-3: 성과 지표 계산 (metrics.py)

일일 지표:
- 커밋 수 (전체 / 프로젝트별)
- 변경 라인 (insertions + deletions)
- 문서 변경 비율 (`.md` 파일 변경 / 전체)
- 프로젝트 배분율 (EBS 60% / WSOPTV 30% / Secretary 10% 등)
- 활성 Work Stream 수

주간 지표:
- velocity 트렌드: 최근 4주 커밋 수 비교 (↑/↓/→)
- 완료 stream 수 / 신규 stream 수
- 프로젝트별 주간 커밋 합계
- Top 3 활성 stream (커밋 수 기준)

### FR-4: Slack 공유 (formatter.py + reporter 통합)

채널: `C0985UXQN6Q` (claude-auto)

포맷: Slack mrkdwn (상세 메시지 예시는 "Slack 메시지 포맷" 섹션 참조)

### FR-5: CLI (cli.py)

```
python -m scripts.work_tracker.cli <command> [options]

Commands:
  collect [--date YYYY-MM-DD]     지정일 git 수집 (기본: 오늘)
  summary [--date YYYY-MM-DD]     일일 요약 출력
  streams [--status active|idle|completed|all]  Work Stream 목록
  metrics [--weekly] [--weeks N]  성과 지표 (기본: 일일, --weekly: 주간)
  post [--daily|--weekly] [--dry-run] [--confirm]  Slack 전송
```

- `--dry-run` (기본값): 메시지 미리보기만
- `--confirm`: 실제 전송 (첫 사용 시 필수)

### NFR-1: 기존 secretary 아키텍처 통합

| 패턴 | 원본 | 적용 |
|------|------|------|
| aiosqlite WAL | `scripts/gateway/storage.py` | `scripts/work_tracker/storage.py` |
| 3-way import | `storage.py` 상단 try/except | 동일 패턴 |
| paths 상수 | `scripts/shared/paths.py` | `WORK_TRACKER_DB` 추가 |
| SecretaryReporter | `scripts/reporter/reporter.py` | `send_work_summary()` 메서드 추가 |
| DigestReport | `scripts/reporter/digest.py` | work data 섹션 통합 |
| daily_report | `scripts/daily_report.py` | `--work` 옵션 + `analyze_work()` 단계 |
| rate_limiter | `scripts/shared/rate_limiter.py` | Slack 전송 제한 재사용 |
| projects.json | `config/projects.json` | `local_repo_mapping` 필드 추가 |

### NFR-2: AI 모델

| 티어 | 모델 | 용도 |
|------|------|------|
| Tier 1 (기본) | Qwen 3.5 9B (Ollama Docker) | 커밋 메시지 요약, Work Stream 자동 명명, 일일 하이라이트 생성 |
| Tier 2 (에스컬레이션) | Claude Sonnet (기존 `claude_draft` 패턴) | 복잡한 분석, 트렌드 해석 |

기존 gateway.json 설정:
- endpoint: `http://localhost:11434`
- 현재 모델: `qwen3:8b` → 업그레이드 대상: `qwen3.5:9b`
- escalation 기준: confidence < 0.6 또는 complexity > 0.7

### NFR-3: 안전

- `dry_run`: 기본값 `true` — 실수로 메시지 전송 방지
- `--confirm`: 첫 전송 시 필수 플래그
- rate_limiter: `scripts/shared/rate_limiter.py` 재사용 (분당 10건 제한)
- 개인 정보: 커밋 메시지만 수집, 파일 내용 미수집
- DB 백업: WAL 모드 + 주간 자동 vacuum

## 아키텍처

파일 구조:
```
scripts/work_tracker/
├── __init__.py
├── collector.py          # git log 수집 + Conventional Commit 파싱
├── stream_detector.py    # Work Stream 그룹핑 (4가지 감지 로직)
├── metrics.py            # 성과 지표 계산 (일일/주간)
├── storage.py            # SQLite (data/work_tracker.db, aiosqlite WAL)
├── formatter.py          # Slack mrkdwn 포맷팅
└── cli.py                # CLI 진입점
```

데이터 흐름:
```
C:\claude\*\.git → collector.py → storage.py (daily_commits)
                                        ↓
                              stream_detector.py → storage.py (work_streams)
                                        ↓
                                   metrics.py → storage.py (daily_summaries, weekly_summaries)
                                        ↓
                                  formatter.py → reporter.py → Slack
```

## DB 스키마

DB 파일: `C:\claude\secretary\data\work_tracker.db`

5개 테이블:

```sql
-- 1. 일일 커밋 로그
CREATE TABLE IF NOT EXISTS daily_commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,              -- YYYY-MM-DD
    repo TEXT NOT NULL,              -- 레포 디렉토리명 (e.g., "ebs", "ui_overlay")
    project TEXT NOT NULL,           -- 프로젝트 분류 (EBS/WSOPTV/Secretary)
    category TEXT,                   -- 카테고리 (기획/역공학/UI 분석 등)
    commit_hash TEXT NOT NULL,
    commit_type TEXT,                -- feat/fix/docs/refactor/...
    commit_scope TEXT,               -- Conventional Commit scope
    message TEXT NOT NULL,
    author TEXT NOT NULL,
    timestamp TEXT NOT NULL,         -- ISO 8601
    files_changed INTEGER DEFAULT 0,
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    branch TEXT,
    UNIQUE(commit_hash)
);

-- 2. 문서 변경 추적
CREATE TABLE IF NOT EXISTS doc_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_id INTEGER REFERENCES daily_commits(id),
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,       -- added/modified/deleted
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0
);

-- 3. Work Stream
CREATE TABLE IF NOT EXISTS work_streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- stream 이름
    project TEXT NOT NULL,           -- EBS/WSOPTV/Secretary
    repos TEXT NOT NULL,             -- JSON array of repo names
    first_commit TEXT NOT NULL,      -- ISO 8601
    last_commit TEXT NOT NULL,       -- ISO 8601
    total_commits INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',    -- active/idle/completed/new
    duration_days INTEGER DEFAULT 0,
    detection_method TEXT,           -- branch/scope/path/keyword
    metadata TEXT,                   -- JSON (keywords, branches, etc.)
    updated_at TEXT NOT NULL
);

-- 4. 일일 요약
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,       -- YYYY-MM-DD
    total_commits INTEGER DEFAULT 0,
    total_insertions INTEGER DEFAULT 0,
    total_deletions INTEGER DEFAULT 0,
    doc_change_ratio REAL DEFAULT 0, -- 0.0~1.0
    project_distribution TEXT,       -- JSON {"EBS": 60, "WSOPTV": 30, ...}
    active_streams INTEGER DEFAULT 0,
    highlights TEXT,                 -- AI 생성 하이라이트 (JSON array)
    slack_message_id TEXT,           -- 전송된 Slack 메시지 ts
    created_at TEXT NOT NULL
);

-- 5. 주간 요약
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE, -- e.g., "W12 (3/10~3/16)"
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_commits INTEGER DEFAULT 0,
    velocity_trend TEXT,             -- JSON (last 4 weeks)
    completed_streams TEXT,          -- JSON array
    new_streams TEXT,                -- JSON array
    project_distribution TEXT,       -- JSON
    highlights TEXT,                 -- AI 생성 하이라이트
    slack_message_id TEXT,
    created_at TEXT NOT NULL
);
```

## 통합 지점

4개 기존 파일 수정 필요:

1. **`scripts/shared/paths.py`** — 추가:
```python
WORK_TRACKER_DB = DATA_DIR / "work_tracker.db"
```

2. **`config/projects.json`** — `local_repo_mapping` 필드 추가 (레포→프로젝트 매핑)

3. **`scripts/daily_report.py`** — `--work` 옵션 + `analyze_work()` 단계 추가:
```python
WORK_SCRIPT = SCRIPT_DIR / "work_tracker" / "cli.py"
# --work 옵션 시 work_tracker collect + summary 실행
```

4. **`scripts/reporter/reporter.py`** — `send_work_summary()` 메서드 추가:
```python
async def send_work_summary(self, summary_data: dict, channel: str = "C0985UXQN6Q"):
    """Work Tracker 일일/주간 요약 Slack 전송"""
```

## Slack 메시지 포맷

### 일일 요약 예시

```
:memo: *일일 업무 현황* — 2026-03-17 (월)

*:chart_with_upwards_trend: 오늘의 성과*
• 커밋: 12건 (EBS 8 / WSOPTV 3 / Secretary 1)
• 변경: +342 / -128 lines
• 문서 비율: 45%

*:briefcase: EBS*
• `ui_overlay` — overlay 분석 파이프라인 개선 (3 commits)
• `ebs` — GFX 탭 UI 컴포넌트 정리 (5 commits)

*:tv: WSOPTV*
• `wsoptv_ott` — 네비게이션 구조 리팩토링 (3 commits)

*:robot_face: Secretary*
• `secretary` — Work Tracker 모듈 초기 구현 (1 commit)

*:dart: 활성 Work Stream*
• ui_overlay 분석 (20일째, 진행 중)
• OTT 기획서 (전 기간, 진행 중)
• Work Tracker (1일째, 신규)

*:calendar: 다음 할 일*
• ui_overlay overlay-samples.html 재작성
• OTT Phase 3 스트리밍 인프라 설계
```

### 주간 롤업 예시

```
:bar_chart: *주간 업무 롤업* — W12 (3/10~3/16)

*:chart_with_upwards_trend: Velocity*
W9: ██████░░░░ 28
W10: ████████░░ 35
W11: █████████░ 42
W12: ██████████ 48  ↑14%

*:briefcase: 프로젝트별*
• EBS: 28 commits (+8 vs W11)
• WSOPTV: 15 commits (+2 vs W11)
• Secretary: 5 commits (신규)

*:checkered_flag: 완료 Stream*
• EBS UI Design v3 (6일, 15 commits)
• Flutter 앱 포팅 (2일, 8 commits)

*:construction: 진행 중 Stream*
• ui_overlay 분석 (20일째)
• OTT 기획서 (전 기간)

*:chart_with_downwards_trend: Idle Stream (7일+ 미활동)*
• 하드웨어 기획서 (마지막: 2/5)
```

## Work Stream 감지 검증 데이터

아래는 실제 Git 데이터로 검증된 Work Stream 목록. Work Tracker의 `stream_detector.py`가 이와 동일한 결과를 추출해야 함:

**EBS 프로젝트:**

| Work Stream | 검증된 기간 | 커밋 수 | 레포 | 감지 방법 |
|---|---|---|---|---|
| 마스터 기획서 | 1/22~1/30 (9일) | ~10 | ebs | scope + path |
| 하드웨어 기획서 | 1/29~2/5 (8일) | ~8 | ebs | scope + path |
| 업체 RFI/견적 | 2/4~2/9 (6일) | ~5 | ebs | keyword |
| 역공학 기획서 | 2/13~2/26 (14일) | 40 | ebs_reverse | branch + scope |
| GFX 탭 UI 요소 | 2/20~2/26 (7일) | ~10 | ebs | scope + path |
| ui_overlay 분석 | 2/23~3/14 (20일) | ~20 | ui_overlay | repo + path |
| EBS UI Design v3 | 3/5~3/11 (6일) | ~15 | ebs | branch + scope |
| Flutter 앱 포팅 | 3/3~3/4 (2일) | 8 | ebs_reverse_app | repo + branch |

**WSOPTV 프로젝트:**

| Work Stream | 검증된 기간 | 커밋 수 | 레포 | 감지 방법 |
|---|---|---|---|---|
| OTT 기획서 | 1/19~3/13 (전 기간) | ~40 | wsoptv_ott | repo + scope |
| MVP 앱 | 1/23~2/9 (18일) | ~15 | wsoptv_ott | branch + keyword |
| 스트리밍 벤더 | 2/2~2/13 (12일) | ~8 | wsoptv_ott | keyword |
| 네비게이션 | 2/16~3/1 (14일) | ~5 | wsoptv_ott | scope + path |
| Academy 홈페이지 | 3/9~3/13 (5일) | 6 | wsop_academy | repo |

## 구현 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| PRD 작성 | 완료 | 현재 문서 |
| collector.py | 예정 | FR-1 |
| stream_detector.py | 예정 | FR-2 |
| metrics.py | 예정 | FR-3 |
| storage.py | 예정 | DB 스키마 |
| formatter.py | 예정 | FR-4 |
| cli.py | 예정 | FR-5 |
| paths.py 통합 | 예정 | NFR-1 |
| projects.json 확장 | 예정 | NFR-1 |
| daily_report.py 통합 | 예정 | NFR-1 |
| reporter.py 통합 | 예정 | NFR-1 |
| 단위 테스트 | 예정 | - |
| E2E 테스트 | 예정 | - |

## Changelog

| 날짜 | 버전 | 변경 내용 | 변경 유형 | 결정 근거 |
|------|------|-----------|----------|----------|
| 2026-03-17 | v1.0 | 최초 작성 | - | Q1 보고서 Work Stream 기간 불일치 9건 해결 필요 |
