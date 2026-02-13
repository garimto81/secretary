---
name: auto
description: 하이브리드 자율 워크플로우 - OMC+BKIT 통합 (Ralph + Ultrawork + PDCA 필수)
version: 17.0.0
triggers:
  keywords:
    - "/auto"
    - "auto"
    - "autopilot"
    - "ulw"
    - "ultrawork"
    - "ralph"
model_preference: opus
auto_trigger: true
omc_delegate: oh-my-claudecode:autopilot
omc_agents:
  - executor
  - executor-high
  - architect
  - planner
  - critic
bkit_agents:
  - gap-detector
  - pdca-iterator
  - code-analyzer
  - report-generator
---

# /auto - 하이브리드 자율 워크플로우 (v16.0 - OMC+BKIT 통합)

> **핵심**: `/auto "작업"` = **PDCA 문서화(필수)** + Ralph 루프 + Ultrawork 병렬 + **이중 검증**

## OMC + BKIT Integration

이 스킬은 OMC와 BKIT의 기능을 통합합니다.

### 사용되는 에이전트 (43개)

**OMC 에이전트** (실행력):
- `oh-my-claudecode:executor`: 기능 구현
- `oh-my-claudecode:architect`: 분석 및 검증
- `oh-my-claudecode:planner`: 계획 수립
- `oh-my-claudecode:critic`: 계획 검토
- `oh-my-claudecode:code-reviewer`: 코드 리뷰

**BKIT 에이전트** (체계성):
- `bkit:gap-detector`: 설계-구현 갭 분석 (90% 검증)
- `bkit:pdca-iterator`: Check-Act 반복 개선
- `bkit:code-analyzer`: 코드 품질 분석
- `bkit:report-generator`: 완료 보고서 생성

**Skill() 호출 형식**:
```
Skill(skill="oh-my-claudecode:autopilot", args="작업 설명")
```

**omc_delegate 필드**:
- YAML frontmatter의 `omc_delegate: oh-my-claudecode:autopilot`는 자동 위임 대상을 지정합니다.
- 호출 시 OMC 시스템이 자동으로 해당 스킬로 라우팅합니다.

**사용되는 OMC 에이전트**:
- `executor`: 일반 구현 작업
- `executor-high`: 복잡한 구현 작업
- `architect`: 분석 및 검증
- `planner`: 계획 수립
- `critic`: 계획 검토

## ⚠️ 필수 실행 규칙 (CRITICAL)

**이 스킬이 활성화되면 반드시 아래 워크플로우를 실행하세요!**

### Phase 0: PDCA 문서화 (필수 - BKIT 워크플로우)

**모든 작업은 PDCA 사이클을 따릅니다:**

```
┌─────────────────────────────────────────────────────────────┐
│                    PDCA 필수 워크플로우                       │
│                                                             │
│  Plan ──▶ Design ──▶ Do ──▶ Check ──▶ Act                  │
│   │         │        │        │        │                    │
│   ▼         ▼        ▼        ▼        ▼                    │
│ 계획문서  설계문서   구현    갭검증   개선반복               │
│                              │                              │
│                    ┌────────┴────────┐                     │
│                    │    병렬 검증     │                     │
│                    │ OMC Architect   │                     │
│                    │ BKIT gap-detector│                     │
│                    └─────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

**Step 0.1: Plan 문서 생성 (Ralplan 연동)**

**복잡도 점수 판단 (MANDATORY - 5점 만점):**

작업 설명을 분석하여 아래 5개 조건을 평가합니다. 각 조건 충족 시 1점.

| # | 조건 | 1점 기준 | 0점 기준 |
|:-:|------|---------|---------|
| 1 | **파일 범위** | 3개 이상 파일 수정 예상 | 1-2개 파일 |
| 2 | **아키텍처** | 새 패턴/구조 도입 | 기존 패턴 내 수정 |
| 3 | **의존성** | 새 라이브러리/서비스 추가 | 기존 의존성만 사용 |
| 4 | **모듈 영향** | 2개 이상 모듈/패키지 영향 | 단일 모듈 내 변경 |
| 5 | **사용자 명시** | `ralplan` 키워드 포함 | 키워드 없음 |

**판단 규칙:**
- **score >= 3** → Ralplan 실행 (Planner + Architect + Critic 합의)
- **score < 3** → Planner 단독 실행

**판단 로그 출력 (항상 필수):**
```
═══ 복잡도 판단 ═══
파일 범위: {0|1}점 ({근거})
아키텍처: {0|1}점 ({근거})
의존성:   {0|1}점 ({근거})
모듈 영향: {0|1}점 ({근거})
사용자 명시: {0|1}점
총점: {score}/5 → {Ralplan 실행|Planner 단독}
═══════════════════
```

**score >= 3: Ralplan 실행**

```
# Step A: Ralplan 실행 (Planner → Architect → Critic 합의)
# Critic은 반드시 기존 Plan 문서(docs/01-plan/)와의 범위 중복을 확인해야 합니다
Skill(skill="oh-my-claudecode:ralplan", args="작업 설명. Critic 추가 검증: docs/01-plan/ 내 기존 Plan과 범위 겹침 여부 확인 필수")

# Step B: 합의 결과를 PDCA Plan 문서로 기록
Task(
  subagent_type="oh-my-claudecode:executor",
  model="sonnet",
  description="[PDCA Plan] Ralplan 결과 문서화",
  prompt="Ralplan 합의 결과를 docs/01-plan/{feature}.plan.md에 기록하세요.

  포함 항목:
  - 복잡도 점수: {score}/5 (각 조건별 판단 근거)
  - 합의된 아키텍처 결정사항
  - 구현 범위 및 제외 항목
  - 예상 영향 파일 목록
  - 위험 요소 및 완화 방안
  - Planner/Architect/Critic 각 관점 요약
  - 관련 PRD: {PRD-NNNN 또는 '없음'}
  - 기존 Plan 중복 확인: {중복 없음 또는 겹치는 Plan 파일명}"
)
```
→ `docs/01-plan/{feature}.plan.md` 생성 (Ralplan 합의 결과 포함)

**score < 3: Planner 단독 실행**
```
Task(
  subagent_type="oh-my-claudecode:planner",
  model="opus",
  description="[PDCA Plan] 기능 계획",
  prompt="... (복잡도 점수: {score}/5, 판단 근거 포함)"
)
```
→ `docs/01-plan/{feature}.plan.md` 생성 (단독 Planner 결과)

**Step 0.2: Design 문서 생성 (Plan 게이트 검증 포함)**

**Plan→Design 전환 게이트 (MANDATORY):**
Design 생성 전 Plan 문서에 아래 4개 필수 섹션이 존재하는지 확인합니다.
누락 시 Plan 문서를 먼저 보완한 후 Design으로 진행합니다.

| # | 필수 섹션 | 확인 방법 |
|:-:|----------|----------|
| 1 | 배경/문제 정의 | `## 배경` 또는 `## 문제 정의` 헤딩 존재 |
| 2 | 구현 범위 | `## 구현 범위` 또는 `## 범위` 헤딩 존재 |
| 3 | 예상 영향 파일 | 파일 경로 목록 포함 (`.py`, `.ts`, `.md` 등) |
| 4 | 위험 요소 | `## 위험` 또는 `위험 요소` 헤딩 존재 |

```
# Plan 게이트 검증
plan_path = "docs/01-plan/{feature}.plan.md"
# Read plan_path → 4개 필수 섹션 존재 확인
# 누락 시 → executor로 Plan 보완 후 진행

Task(
  subagent_type="oh-my-claudecode:architect",
  model="opus",
  description="[PDCA Design] 기능 설계",
  prompt="docs/01-plan/{feature}.plan.md를 참조하여 설계 문서를 작성하세요.
  Plan Reference 필드에 Plan 문서 경로를 명시하세요."
)
```
→ `docs/02-design/{feature}.design.md` 생성

**Step 0.3: Do (구현)**
- 기존 /auto 워크플로우 (Ralplan + Ultrawork)

**Step 0.4: Check (이중 검증 - 병렬)**
```
# OMC + BKIT 병렬 검증
Task(subagent_type="oh-my-claudecode:architect", model="opus", ...)
Task(subagent_type="bkit:gap-detector", model="opus", ...)
```
- Architect: 기능 완성도 검증
- gap-detector: 설계-구현 90% 일치 검증

**Step 0.5: Act (자동 실행 - CRITICAL)**

**PDCA 완료 시 자동 실행 규칙 (Recommended 출력 금지):**

```
┌─────────────────────────────────────────────────────────────┐
│              Act Phase 자동 실행 로직                         │
│                                                             │
│   Check 결과                      자동 실행                  │
│   ─────────────────────────────────────────────────────────  │
│   gap < 90%         →  bkit:pdca-iterator (최대 5회 반복)    │
│   gap >= 90%        →  bkit:report-generator (자동 호출)     │
│   Architect REJECT  →  oh-my-claudecode:executor (수정)     │
│   모든 조건 충족     →  완료 보고서 자동 생성                  │
│                                                             │
│   ⚠️ "Recommended: ..." 출력 후 종료 = 금지                  │
│   ⚠️ 자동 실행 후 결과 출력 = 필수                            │
└─────────────────────────────────────────────────────────────┘
```

**Case 1: gap < 90%**
```
Task(
  subagent_type="bkit:pdca-iterator",
  model="sonnet",
  description="[PDCA Act] 갭 자동 개선",
  prompt="설계-구현 갭을 90% 이상으로 개선하세요. 최대 5회 반복."
)
```

**Case 2: gap >= 90%**
```
Task(
  subagent_type="bkit:report-generator",
  model="haiku",
  description="[PDCA Report] 완료 보고서 생성",
  prompt="PDCA 사이클 완료 보고서를 생성하세요.

  포함 항목:
  - Plan 요약: docs/01-plan/{feature}.plan.md
  - Design 요약: docs/02-design/{feature}.design.md
  - 구현 결과 및 변경 파일 목록
  - Check 결과 (gap-detector 점수, Architect 판정)
  - 교훈 및 개선 사항

  출력 위치: docs/04-report/{feature}.report.md"
)
```

**Case 3: Architect REJECT**
```
Task(
  subagent_type="oh-my-claudecode:executor",
  model="sonnet",
  description="[PDCA Act] Architect 피드백 반영",
  prompt="Architect 거부 사유를 해결하세요: {rejection_reason}"
)
# 해결 후 Check Phase 재실행
```

**자동 실행 후 출력 형식:**
```
═══════════════════════════════════════════════════
 ✅ PDCA 사이클 완료
═══════════════════════════════════════════════════
 Check 결과: gap 94% (≥90% 통과)
 Act 실행: report-generator → docs/04-report/{feature}.report.md

 📄 보고서 생성 완료
═══════════════════════════════════════════════════
```

**❌ 금지 패턴:**
```
# 이렇게 출력하고 끝내면 안됨!
💡 Recommended: /pdca report vercel-bp-integration (완료 리포트 자동화)
```

→ Recommended가 있으면 **즉시 자동 실행** 후 결과 출력

### Phase 1: 옵션 라우팅 (있을 경우)

| 옵션 | 실행할 스킬 | 설명 |
|------|-------------|------|
| `--gdocs` | `Skill(skill="prd-sync")` | Google Docs PRD 동기화 |
| `--mockup` | `Skill(skill="mockup-hybrid", args="...")` | 목업 생성 |
| `--debate` | `Skill(skill="ultimate-debate", args="...")` | 3AI 토론 |
| `--research` | `Skill(skill="research", args="...")` | 리서치 모드 |
| `--slack <채널>` | Slack 채널 분석 후 컨텍스트 주입 | 채널 히스토리 기반 작업 |
| `--gmail` | Gmail 메일 분석 후 컨텍스트 주입 | 메일 기반 작업 |
| `--daily` | `Skill(skill="daily")` | daily v3.0 9-Phase Pipeline (Config Bootstrap 내장) |
| `--daily --slack` | `Skill(skill="daily")` | 동일 Pipeline + Phase 6 Slack Lists 갱신 |
| `--interactive` | 각 Phase 전환 시 사용자 승인 요청 | 단계적 승인 모드 |

**옵션 체인 예시:**
```
/auto --gdocs --mockup "화면명"
→ Step 1: Skill(skill="prd-sync")
→ Step 2: Skill(skill="mockup-hybrid", args="화면명")

/auto --slack C09N8J3UJN9 "EBS 프로젝트"
→ Step 1: Slack 채널 히스토리 수집
→ Step 2: 메시지 분석 및 컨텍스트 생성
→ Step 3: 컨텍스트 기반 메인 워크플로우 실행

/auto --gmail "클라이언트 메일 분석 후 응답 초안 작성"
→ Step 1: Gmail 인증 확인
→ Step 2: 안 읽은 메일 또는 검색 결과 수집
→ Step 3: 메일 분석 및 컨텍스트 생성
→ Step 4: 컨텍스트 기반 메인 워크플로우 실행
```

**옵션 실패 시**: 에러 메시지 출력하고 **절대 조용히 스킵하지 않음**

### `--slack` 옵션 워크플로우

Slack 채널의 모든 메시지를 분석하여 프로젝트 컨텍스트로 활용합니다.

**Step 1: 인증 확인**
```bash
cd C:\claude && python -m lib.slack status --json
```
- `"authenticated": false` → 에러 출력 후 중단

**Step 2: 채널 히스토리 수집**
```bash
python -m lib.slack history "<채널ID>" --limit 100 --json
```
- 메시지 100개 단위로 수집
- 필요 시 페이지네이션 (oldest 파라미터)

**Step 3: 메시지 분석 (Analyst Agent)**
```
Task(
  subagent_type="oh-my-claudecode:analyst",
  model="opus",
  prompt="SLACK CHANNEL ANALYSIS

채널: <채널ID>
메시지 수: <N>개

분석 항목:
1. 주요 토픽 및 프로젝트 목표
2. 핵심 결정사항 및 합의점
3. 공유된 문서 링크 정리
4. 참여자 역할 및 책임
5. 미해결 이슈 및 질문
6. 기술 스택 및 도구 언급

출력: 구조화된 컨텍스트 문서"
)
```

**Step 4: 컨텍스트 파일 생성**

`.omc/slack-context/<채널ID>.md` 생성:
```markdown
# Slack Channel Context: <채널명>

## 프로젝트 개요
[분석된 프로젝트 목표]

## 핵심 결정사항
[주요 합의점 목록]

## 관련 문서
[Google Docs 등 링크 목록]

## 기술 스택
[언급된 기술 목록]

## 미해결 이슈
[추적 필요한 항목]

## 원본 메시지 (최근 50개)
[타임스탬프별 메시지]
```

**Step 5: 메인 워크플로우 실행**
- 생성된 컨텍스트 파일을 Read하여 Ralplan에 전달
- 작업 실행 시 Slack 컨텍스트 참조

### `--gmail` 옵션 워크플로우

Gmail 메일을 분석하여 프로젝트 컨텍스트로 활용합니다.

**사용 형식:**
```bash
/auto --gmail                           # 안 읽은 메일 분석
/auto --gmail "검색어"                   # Gmail 검색 쿼리로 필터링
/auto --gmail "작업 설명"                # 메일 기반 작업 실행
/auto --gmail "from:client" "응답 초안"  # 검색 + 작업 조합
```

**Step 1: 인증 확인 (MANDATORY)**
```bash
cd C:\claude && python -m lib.gmail status --json
```
- `"authenticated": true, "valid": true` → 계속 진행
- `"authenticated": false` → **에러 출력 후 중단**:
  ```
  ❌ Gmail 인증이 필요합니다.
  실행: python -m lib.gmail login
  ```

**Step 2: 메일 수집**

| 입력 패턴 | 실행 명령 |
|----------|----------|
| `--gmail` (검색어 없음) | `python -m lib.gmail unread --limit 20 --json` |
| `--gmail "from:..."` | `python -m lib.gmail search "from:..." --limit 20 --json` |
| `--gmail "subject:..."` | `python -m lib.gmail search "subject:..." --limit 20 --json` |
| `--gmail "newer_than:7d"` | `python -m lib.gmail search "newer_than:7d" --limit 20 --json` |

**Gmail 검색 쿼리 문법:**
| 조건 | 예시 |
|------|------|
| 발신자 | `from:boss@company.com` |
| 제목 | `subject:meeting` |
| 최근 N일 | `newer_than:7d` |
| 첨부파일 | `has:attachment` |
| 안 읽음 | `is:unread` |
| 라벨 | `label:work` |

**Step 3: 메일 분석 (Analyst Agent)**
```
Task(
  subagent_type="oh-my-claudecode:analyst",
  model="opus",
  prompt="GMAIL ANALYSIS

메일 수: <N>개
메일 데이터:
<JSON 메일 목록>

분석 항목:
1. 주요 요청사항 및 할일 추출
2. 중요 발신자 및 우선순위 분류
3. 회신 필요한 메일 식별 (긴급도 표시)
4. 첨부파일 목록 및 처리 필요 여부
5. 키워드 및 프로젝트 연관성 분석
6. 잠재적 이슈 및 리스크 식별

출력: 구조화된 이메일 분석 문서 (마크다운)"
)
```

**Step 4: 컨텍스트 파일 생성**

`.omc/gmail-context/<timestamp>.md` 생성:
```markdown
# Gmail Context: <날짜>

## 📊 요약
- 총 메일: N개
- 긴급 회신 필요: N개
- 할일 추출: N개

## 🔴 긴급 (회신 필요)
| 발신자 | 제목 | 날짜 | 요청사항 |
|--------|------|------|----------|
| ... | ... | ... | ... |

## 📋 할일 추출
- [ ] 항목 1 (발신자, 제목, 기한)
- [ ] 항목 2

## 📬 메일 목록 (우선순위순)
### 높음
- **제목** from 발신자 (날짜)
  > 스니펫...

### 보통
- ...

## 📎 첨부파일
- filename.pdf (발신자, 제목)

## 🔗 관련 링크
- [링크명](URL)
```

**Step 5: 후속 작업 분기**

| 사용자 요청 | 실행 |
|------------|------|
| 검색만 | 분석 결과 출력 후 종료 |
| "응답 초안" | 각 메일에 대한 회신 초안 생성 |
| "할일 생성" | TaskCreate로 TODO 항목 생성 |
| "요약 전송" | 분석 결과를 이메일로 전송 |
| 구체적 작업 | 메인 워크플로우 실행 (메일 컨텍스트 포함) |

**예시 실행:**
```
/auto --gmail "from:client newer_than:3d" "각 메일에 응답 초안 작성"

→ Step 1: 인증 확인 ✓
→ Step 2: python -m lib.gmail search "from:client newer_than:3d" --limit 20 --json
→ Step 3: Analyst 에이전트가 메일 분석
→ Step 4: .omc/gmail-context/2026-02-02.md 생성
→ Step 5: 각 메일별 응답 초안 생성
→ 결과 출력
```

### `--daily` 옵션 워크플로우 (v3.0)

`/auto --daily`는 daily v3.0 스킬을 직접 호출합니다. 모든 로직(Config Bootstrap, 증분 수집, AI 분석, 액션 추천)은 daily 스킬 내부에서 처리됩니다.

**사용 형식:**
```bash
/auto --daily                    # 9-Phase Pipeline 전체 실행
/auto --daily --slack            # 동일 + Phase 6 Slack Lists 갱신
/auto --daily ebs                # EBS 전용 브리핑
```

**라우팅:**
```
/auto --daily
    │
    └─► Skill(skill="daily") 직접 호출
        └─► daily v3.0 Phase 0~8 자체 실행
            Phase 0: Config Bootstrap (auto-generate .project-sync.yaml)
            Phase 1: Expert Context Loading (프로젝트 전문가 학습)
            Phase 2: Incremental Collection (Gmail/Slack/GitHub 증분)
            Phase 3: Attachment Analysis (PDF/Excel AI 분석)
            Phase 4: Cross-Source Analysis (크로스소스 연결)
            Phase 5: Action Recommendation (액션 초안 생성)
            Phase 6: Project-Specific Ops (vendor/dev 타입별)
            Phase 7: Gmail Housekeeping (라벨/정리)
            Phase 8: State Update (커서/캐시 저장)
```

**상세 워크플로우:** `.claude/skills/daily/SKILL.md` (v3.0) 참조

### `--interactive` 옵션 워크플로우

각 PDCA Phase 전환 시 사용자에게 확인을 요청하여 단계적 승인을 받습니다.

**사용 형식:**
```bash
/auto --interactive "작업 설명"        # 모든 Phase에서 승인 요청
/auto --interactive --skip-plan "작업"  # Plan 건너뛰고 Design부터 시작
```

**동작 방식:**

각 Phase 전환 시 `AskUserQuestion`을 호출하여 사용자 선택을 받습니다:

| Phase 전환 | 선택지 | 기본값 |
|-----------|--------|:------:|
| Plan 완료 → Design | 진행 / 수정 / 건너뛰기 | 진행 |
| Design 완료 → Do | 진행 / 수정 / 건너뛰기 | 진행 |
| Do 완료 → Check | 진행 / 수정 | 진행 |
| Check 결과 → Act | 자동 개선 / 수동 수정 / 완료 | 자동 개선 |

**Phase 전환 시 출력 형식:**

```
═══════════════════════════════════════════════════
 Phase [현재] 완료 → Phase [다음] 진입 대기
═══════════════════════════════════════════════════
 산출물: docs/01-plan/{feature}.plan.md
 소요 에이전트: planner (opus), critic (opus)
 핵심 결정: [1줄 요약]
═══════════════════════════════════════════════════
```

**--interactive 미사용 시** (기본 동작): 모든 Phase를 자동으로 진행합니다.

## Ralph 루프 워크플로우 (CRITICAL)

**autopilot = Ralplan + Ultrawork + Ralph 루프**

### 실행 흐름

```
Ralplan (계획 합의)
       │
       ▼
Ultrawork (병렬 실행)
       │
       ▼
Architect 검증
       │
       ▼
┌──────────────────────────────────────┐
│         Ralph 루프 (5개 조건)          │
│                                      │
│  조건 1: TODO == 0                   │
│  조건 2: 기능 동작                    │
│  조건 3: 테스트 통과                  │
│  조건 4: 에러 == 0                   │
│  조건 5: Architect 승인              │
│                                      │
│  ANY 실패? ──YES──▶ 자동 재시도       │
│              NO ──▶ 완료 선언         │
└──────────────────────────────────────┘
```

**5개 조건 모두 충족될 때까지 자동으로 반복합니다.**

### Phase 2: 메인 워크플로우 (Ralph + Ultrawork + Team Coordinator)

**작업이 주어지면 (`/auto "작업내용"`):**

**Step 2.0: 복잡도 기반 라우팅 (10점 만점 확장)**

Step 0.1의 5점 만점 복잡도 점수를 10점으로 확장합니다:

| 점수 (10점) | 라우팅 경로 | 설명 |
|:-----------:|------------|------|
| 0-3 | 기존 경로 | Ralplan/Planner 단독 |
| 4-5 | Team Coordinator → Dev 단독 | 단일 기능 구현 |
| 6-7 | Team Coordinator → Dev + Quality | 기능 + 품질 검증 |
| 8-9 | Team Coordinator → Dev + Quality + Research | 복잡한 기능 + 조사 |
| 10 | Team Coordinator → 4팀 전체 | 대규모 프로젝트 |

**5점 → 10점 변환**: `score_10 = score_5 * 2` (기본). `"teamwork"` 키워드 포함 시 자동 10점.

**score < 4 (기존 경로 보존):**

1. **Ralplan 호출** (score >= 3인 경우):
   ```
   Skill(skill="oh-my-claudecode:ralplan", args="작업내용")
   ```
   - Planner → Architect → Critic 합의 도달까지 반복

2. **Ultrawork 모드 활성화**:
   - 모든 독립적 작업은 **병렬 실행**
   - Task tool에 `run_in_background: true` 사용
   - 10+ 동시 에이전트 허용

3. **에이전트 라우팅**:

   | 작업 유형 | 에이전트 | 모델 |
   |----------|----------|------|
   | 간단한 조회 | `oh-my-claudecode:explore` | haiku |
   | 기능 구현 | `oh-my-claudecode:executor` | sonnet |
   | 복잡한 분석 | `oh-my-claudecode:architect` | opus |
   | UI 작업 | `oh-my-claudecode:designer` | sonnet |
   | 테스트 | `oh-my-claudecode:qa-tester` | sonnet |
   | 빌드 에러 | `oh-my-claudecode:build-fixer` | sonnet |

**score >= 4 (Team Coordinator):**

```python
from src.agents.teams import Coordinator

coordinator = Coordinator()
result = coordinator.run("작업 설명")
```

또는 OMC 에이전트로 위임:
```
Task(
  subagent_type="oh-my-claudecode:executor-high",
  model="opus",
  prompt="Team Coordinator를 통해 멀티팀 워크플로우를 실행하세요.
  프로젝트: {작업 설명}
  복잡도: {score}/10
  투입 팀: {teams}"
)
```

**인과관계 보존**: Team Coordinator는 Tier 3 WORK의 하위에서 동작합니다. 기존 Tier 0-5 Discovery는 그대로 유지.

4. **Architect 검증** (완료 전 필수):
   ```
   Task(subagent_type="oh-my-claudecode:architect", model="opus",
        prompt="구현 완료 검증: [작업 설명]")
   ```

5. **완료 조건**:
   - Architect 승인 받음
   - 모든 TODO 완료
   - 빌드/테스트 통과 확인 (fresh evidence)

### Phase 3: 자율 발견 모드 (`/auto` 단독 실행)

작업이 명시되지 않으면 5계층 발견 시스템 실행:

| Tier | 이름 | 발견 대상 | 실행 |
|:----:|------|----------|------|
| 0 | CONTEXT | context >= 90% | 체크포인트 생성 |
| 1 | EXPLICIT | 사용자 지시 | 해당 작업 실행 |
| 2 | URGENT | 빌드/테스트 실패 | `/debug` 실행 |
| 3 | WORK | pending TODO, 이슈 | 작업 처리 |
| 4 | SUPPORT | staged 파일, 린트 에러 | `/commit`, `/check` |
| 5 | AUTONOMOUS | 코드 품질 개선 | 리팩토링 제안 |

### Phase 4: /work --loop 통합 (장기 계획)

> **상태**: 설계 완료, 구현 예정 (2026-03 목표)

`/work --loop`의 자율 반복 기능을 `/auto --work`로 흡수합니다.

**통합 매핑:**

| 기존 | 신규 | 동작 |
|------|------|------|
| `/work --loop` | `/auto --work` | PDCA 없이 빠른 자율 반복 실행 |
| `/work "작업"` | `/work "작업"` | 단일 작업 실행 (변경 없음) |

**`/auto --work` 모드:**
- PDCA 문서화 생략 (빠른 실행)
- Ralplan 대신 단순 Planner 호출
- Ralph 루프 5개 조건 검증 유지
- Context 90% 임계값 관리 유지

**마이그레이션:**
1. `/work --loop` 사용 시 `/auto --work`로 자동 redirect
2. 기존 /work 커맨드는 단일 작업 실행으로 역할 유지
3. `.claude/rules/08-skill-routing.md` 인과관계 그래프 업데이트

## 세션 관리

```bash
/auto status    # 현재 상태 확인
/auto stop      # 중지 (상태 저장)
/auto resume    # 재개
```

## 금지 사항

- ❌ 옵션 실패 시 조용히 스킵
- ❌ Architect 검증 없이 완료 선언
- ❌ 증거 없이 "완료됨" 주장
- ❌ 테스트 삭제로 문제 해결

## 상세 워크플로우

추가 세부사항: `.claude/commands/auto.md`

## 변경 이력

### v18.0.0 (daily v3.0 - 9-Phase Pipeline)

| 기능 | 설명 | 활성화 |
|------|------|:------:|
| **daily v3.0 통합** | 9-Phase Pipeline으로 --daily 전면 재설계 | ✅ |
| **Secretary 의존 제거** | Gmail/Slack/GitHub 직접 수집으로 교체 | ✅ |
| **Project Context Discovery 내부화** | Config Bootstrap이 daily v3.0 Phase 0으로 이전 | ✅ |
| **daily-sync deprecated** | daily v3.0에 기능 흡수, redirect 설정 | ✅ |
| **--daily 섹션 간소화** | 상세 로직을 daily/SKILL.md로 이전 | ✅ |

### v16.2.0 (Act Phase 자동 실행)

| 기능 | 설명 | 활성화 |
|------|------|:------:|
| **Act 자동 실행** | "Recommended" 출력 금지, 즉시 자동 실행 | ✅ 필수 |
| **bkit Hook 연동** | session-start.js Auto-Execute 규칙 | ✅ 필수 |
| **완료 보고서 자동** | gap >= 90% 시 report-generator 자동 호출 | ✅ 기본 |

### v16.0 (OMC + BKIT 통합)

| 기능 | 설명 | 활성화 |
|------|------|:------:|
| **PDCA 문서화** | Plan→Design→Do→Check→Act 자동 | ✅ 필수 |
| **이중 검증** | OMC Architect + BKIT gap-detector 병렬 | ✅ 기본 |
| **43 에이전트** | OMC 32개 + BKIT 11개 통합 | ✅ |
| **병렬 비교** | 동일 도메인 OMC/BKIT 결과 비교 | ✅ |
