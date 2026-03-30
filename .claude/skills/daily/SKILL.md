---
name: daily
description: >
  일일 업무 현황 대시보드. Triggers on "daily", "데일리", "업무 현황", "브리핑". 3시제(과거/현재/미래) 관점으로 업무 브리핑 생성.
version: 5.0.0

triggers:
  keywords:
    - "daily"
    - "오늘 현황"
    - "일일 대시보드"
    - "프로젝트 진행률"
    - "전체 현황"
    - "데일리 브리핑"
    - "morning briefing"
    - "아침 브리핑"
    - "일일 동기화"
    - "일일 보고"
  file_patterns:
    - "**/daily/**"
    - "**/work_tracker/**"
  context:
    - "업무 현황"
    - "프로젝트 관리"

auto_trigger: true
---

# Daily Skill v5.0 — 3시제 아침 브리핑

로컬 레포 git log + GitHub 증분 수집 → Claude Code 3시제 분석 → Slack 아침 브리핑.

**패러다임**: Snapshot(정적 학습 데이터) + Delta(당일 증분) → Claude Code 3시제 분석

## 실행 규칙 (CRITICAL)

**이 스킬이 활성화되면 반드시 아래 4-Phase Pipeline을 순차 실행하세요!**

```
Phase 0 → Phase 1 → Phase 2 → Phase 3
Snapshot   Delta     Claude    Report +
Check      Collect   Analysis  State Update
```

## 4-Phase Pipeline 요약

| Phase | 이름 | 핵심 동작 | 에러 처리 |
|:-----:|------|----------|----------|
| 0 | Snapshot Check | DB 스냅샷 확인 → 없으면 자동 생성 | 생성 실패 시 스냅샷 없이 진행 |
| 1 | Delta Collection | git log(당일) + GitHub 신규 이슈/PR | 수집 0건이면 "커밋 없음" 보고 |
| 2 | Claude Analysis | 스냅샷 + delta → 하이라이트/진행률/예측/할 일 | 스냅샷 없으면 delta만으로 분석 |
| 3 | Report + State Update | Slack 포맷 + 전송 + DB 저장 | 전송 실패 → 로컬 출력만 |

## Phase 실행 상세

### Phase 0: Snapshot Check

```bash
cd C:\claude\secretary
python -m scripts.work_tracker summary --json --date {today}
```

JSON 결과에 `snapshots` 배열 확인:
- 존재 → Phase 1로 진행
- 없음 → 스냅샷 자동 생성:
  ```bash
  python -m scripts.work_tracker snapshot
  ```
- 7일+ 경과 → "스냅샷 갱신 권장" 알림

### Phase 1: Delta Collection

**Step 1.1**: git log 수집 (기존)
```bash
python -m scripts.work_tracker collect --date {today}
```

stdout에서 수집 결과 확인:
- `{N}건 수집, {M}건 신규` → Step 1.2로
- `커밋 없음` → Step 1.2로 (fs 변경만으로도 활동 감지 가능)

**Step 1.2**: 파일시스템 변경 감지 (신규)
```bash
python -m scripts.work_tracker changes --days 1
```

git 없는 디렉토리(ebs_ui, figma 등)도 파일 크기/수정시간 변화로 활동 감지.
결과를 Phase 2 분석에 포함하여 **전체 프로젝트 활동** 파악.

### Phase 2: Claude 분석 — 3시제 점검

Phase 1 이후 JSON 데이터 로드:
```bash
python -m scripts.work_tracker summary --json --date {today}
```

Claude Code가 JSON을 읽고 **3시제 관점**으로 분석:

**과거 — 어제까지 한 일 정리**
- 최근 일주일 커밋을 프로젝트별로 그룹핑
- 각 프로젝트에서 **무엇을 달성했는지** 한 줄로 요약 (커밋 수/lines 아닌 성과 중심)
- 완료된 work stream, merge된 브랜치 정리

**현재 — 오늘 할 일 제안**
- 활성 브랜치 중 다음 커밋이 필요한 작업 우선순위 지정
- 미해결 이슈 중 **오늘 해결 가능한 것** 제안 (이슈 본문 분석 → 해결책 + 승인 요청)
- 어제 시작했지만 미완료인 작업 재시작 제안

**미래 — 앞으로 할 일 대비**
- 다음 주 시작될 작업/마일스톤 알림
- 현재 속도로 병목이 예상되는 프로젝트 경고
- idle stream (14일+ 미활동) 재시작 또는 폐기 결정 요청

### Phase 3: 핵심 보고서 + Slack 전송

**Step 3.1**: Phase 2의 분석 결과를 Slack mrkdwn 포맷으로 조립하여 **터미널에 출력**:

```
*아침 브리핑* — {date} ({weekday})

*어제까지*
• {project A}: {성과 한 줄} (예: RFID 프로토콜 구현 완료, 테스트 통과)
• {project B}: {성과 한 줄}
• {완료된 stream이 있으면: ":checkered_flag: {stream} 완료"}

*오늘 할 일*
1. {최우선: 구체적 행동 + 이유}
2. {차선: 구체적 행동}
3. {해결 가능 이슈: "#N — {해결책 제안}. 진행할까요?"}

*앞으로 대비*
• {다음 주 마일스톤/일정}
• {병목 경고 시: ":warning: {project}에 시간 부족 — 우선순위 조정 필요?"}
• {idle 경고 시: ":zzz: {stream} N일 멈춤 — 재시작? 폐기?"}
```

**Step 3.2**: 동일한 Slack mrkdwn 보고서를 파일로 저장:

```bash
# Claude가 Write 도구로 보고서 저장
# 경로: C:\claude\secretary\data\daily_report_{date}.md
```

**Step 3.3**: 저장된 보고서 파일로 Slack 전송 (자동):

```bash
cd C:\claude\secretary
python -m scripts.work_tracker post --confirm --report-file "C:\claude\secretary\data\daily_report_{date}.md"
```

> `--report-file` 옵션: Claude 분석 보고서를 SlackFormatter 대신 사용.
> 파일이 없으면 SlackFormatter fallback으로 자동 전환.

**Step 3.4**: 로드맵 시각화 (선택):

```bash
cd C:\claude\secretary
python -m scripts.work_tracker roadmap --render --slack
```

> 프로젝트별 Mermaid gantt 차트를 PNG로 렌더링하여 Slack에 업로드.
> 특정 프로젝트만: `--project EBS`

## 서브커맨드

| 커맨드 | 설명 |
|--------|------|
| `/daily` | 전체 대시보드 (4-Phase 전체) |
| `/daily ebs` | EBS 브리핑: `cd C:\claude\ebs\tools\morning-automation && python main.py --post` |

## /auto --daily 연동

`/auto --daily` 실행 시 4-Phase Pipeline 실행 → 결과를 /auto Phase 1 계획에 반영.

## 자동 실행

매일 아침 9시 자동 실행 스크립트: `C:\claude\secretary\scripts\morning_briefing.py`
Task Scheduler 등록: `C:\claude\secretary\scripts\setup_morning_scheduler.ps1`

## 상세 참조

> Phase 0-3 상세 설명, 스냅샷 구조, 분석 프롬프트 가이드, 출력 형식:
> **Read `references/daily-phases.md`**
