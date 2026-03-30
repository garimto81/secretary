# Daily 4-Phase Pipeline (상세 참조)

> 이 문서는 `daily` 스킬 v4.0의 4-Phase Pipeline 상세 가이드입니다.

## Phase 0: Snapshot Check

스냅샷 DB 존재 여부 확인 → 없으면 자동 생성.

```bash
# 1. JSON 출력으로 스냅샷 확인
cd C:\claude\secretary
python -m scripts.work_tracker summary --json --date {today}
# → snapshots 배열이 비어있으면 스냅샷 생성 필요

# 2. 스냅샷 생성 (최초 1회, 이후 주 1회 권장)
python -m scripts.work_tracker snapshot
# → 전체 레포 스캔 + GitHub 수집 → DB 저장
# → 출력: 프로젝트별 진행률, PRD 건수, 문서 건수

# 3. 특정 프로젝트만 갱신
python -m scripts.work_tracker snapshot --project EBS
```

스냅샷 데이터 구조:
- `project`: 프로젝트명 (EBS, WSOPTV, Secretary 등)
- `repos`: 관련 레포 목록
- `github_open_issues`: 오픈 이슈 목록
- `github_open_prs`: 오픈 PR 목록
- `github_attention`: 주의 필요 항목
- `prd_status`: PRD 파일별 완료/진행 중/예정 현황
- `estimated_progress`: PRD 기반 진행률 (0-100%)
- `active_branches`: 활성 브랜치 목록

갱신 주기:
- 7일+ 경과 시 "스냅샷 갱신 권장" 알림
- 자동 갱신은 하지 않음 (수동 `snapshot` 명령)

## Phase 1: Delta Collection

당일 커밋만 증분 수집.

```bash
# 당일 커밋 수집 → DB 저장
python -m scripts.work_tracker collect --date {today}
# → stdout: "{N}건 수집, {M}건 신규"
# → Stream 자동 감지 포함
```

수집 데이터:
- `daily_commits`: 당일 커밋 (repo, hash, type, scope, message, author, timestamp, stats)
- `work_streams`: 감지된 Work Stream (branch/scope/path 기반)

## Phase 2: Claude Analysis

Claude Code가 스냅샷 + 당일 delta를 직접 분석합니다.

```bash
# JSON 데이터 로드 (Claude Code가 읽을 데이터)
python -m scripts.work_tracker summary --json --date {today}
```

JSON 출력 구조:
```json
{
  "summary": {
    "date": "2026-03-18",
    "total_commits": 5,
    "total_insertions": 200,
    "total_deletions": 50,
    "project_distribution": {"EBS": 60, "WSOPTV": 40},
    "progress_by_project": {"EBS": 75, "WSOPTV": 40}
  },
  "commits": [...],
  "streams": [...],
  "snapshots": [
    {
      "project": "EBS",
      "estimated_progress": 75,
      "prd_status": [...],
      "github_open_issues": [...],
      "github_open_prs": [...],
      "active_branches": [...]
    }
  ]
}
```

### Claude Code 분석 항목

| # | 항목 | 소스 | 개수 |
|---|------|------|------|
| 1 | 하이라이트 | 당일 커밋 기반 주요 성과 | 3개 |
| 2 | 프로젝트별 진행률 | 스냅샷 baseline + 당일 delta | 프로젝트 수 |
| 3 | 다음 주 예측 | 활성 브랜치 + 최근 패턴 | 3개 |
| 4 | 다음 할 일 | 오픈 이슈 + 미완료 스트림 | 3개 |
| 5 | GitHub 주의 항목 | attention 배열 | 최대 5개 |

### 분석 결과 저장

```bash
# 프로젝트별 분석 결과를 DB에 저장
python -m scripts.work_tracker update-analysis \
  --project EBS \
  --progress 80 \
  --summary "PRD 4/5 완료, Flutter 앱 포팅 진행 중"
```

## Phase 3: Report + State Update

Slack 포맷 생성 + 전송 + 수집 커서 갱신.

```bash
# 미리보기 (dry-run, 기본)
python -m scripts.work_tracker post

# 실제 Slack 전송
python -m scripts.work_tracker post --confirm

# 주간 롤업
python -m scripts.work_tracker post --weekly --confirm
```

### 출력 형식

```
:memo: *일일 업무 현황* — 2026-03-18 (화)

*:chart_with_upwards_trend: 오늘의 성과*
• 커밋: 12건 (EBS 8 / WSOPTV 3 / Secretary 1)
• 변경: +342 / -128 lines
• 문서 비율: 45%

*:briefcase: EBS*
• `ui_overlay` — overlay 분석 파이프라인 개선 (3 commits)
• `ebs` — GFX 탭 UI 컴포넌트 정리 (5 commits)

*:bar_chart: 프로젝트 진행률*
• EBS: ████████░░ 80%
• WSOPTV: ████░░░░░░ 40%

*:sparkles: 하이라이트*
• EBS UI overlay 분석 파이프라인 리팩토링 완료
• WSOPTV OTT Phase 3 네비게이션 구조 설계
• Secretary Work Tracker Snapshot+Delta 전환

*:dart: 활성 Work Stream*
• ui_overlay 분석 (20일째, 진행 중)
• OTT 기획서 (전 기간, 진행 중)

*:calendar: 다음 할 일*
• ui_overlay overlay-samples.html 재작성
• OTT Phase 3 스트리밍 인프라 설계
• Work Tracker E2E 테스트 작성

*:crystal_ball: 다음 주 예측*
• EBS Flutter 앱 포팅 완료 예상
• WSOPTV Academy 홈페이지 1차 배포
• Secretary daily v4.0 안정화

총 커밋: 12건 | 프로젝트: 3개 | 활성 스트림: 5개
```
