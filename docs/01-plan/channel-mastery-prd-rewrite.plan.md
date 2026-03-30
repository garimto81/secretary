# channel-mastery PRD 재작성 계획

**생성일**: 2026-02-18
**상태**: Active
**대상 파일**: `docs/prd/channel-mastery.prd.md` (415줄)

---

## 배경

기존 `docs/prd/channel-mastery.prd.md`는 코드베이스 탐색 기반의 기술 관찰 문서다. 기술적 사실은 정확하나 Product Requirements Document로서 6가지 구조적 결함이 확인되었다.

**확인된 결함:**

1. **Product가 없다** — "코드에 `_create_adapter()`가 하드코딩이다"는 기술적 관찰이지 사용자 고통이 아니다. "왜 지금 이걸 해야 하는가"가 없다.

2. **해결책이 문제보다 먼저** — Section 6 Technical Architecture에 `@dataclass HealthMetrics`, `BACKOFF_SCHEDULE = [5, 10, ...]`, `AdapterSupervisor` 코드 스니펫까지 포함됨. 이는 `docs/02-design/` 내용이다.

3. **Non-Goals가 면피용** — "Microsoft Teams / Discord 어댑터 구현", "메시지 암호화" 등은 누구도 이번에 하려 하지 않는 것들이다. 진정한 Non-Goal은 하기 유혹이 있지만 의도적으로 제외하는 항목이어야 한다.

4. **Success Metrics 전부 기술 지표** — "지원 채널 수 2→3", "테스트 커버리지 0%→80%"는 엔지니어링 지표다. 사용자가 체감하는 가치 지표(놓치는 메시지 수, 수동 재시작 횟수, 알림 지연)가 0개다.

5. **Target Users 형식 채우기** — 단일 사용자 개인 도구에 "개인 개발자/기획자", "자동화 운영자" 2행 표를 만들었다. 이 도구의 유일한 사용자는 도구 제작자 본인이다.

6. **Timeline 근거 없음** — "Phase 1: 1주, Phase 2: 1주, Phase 3: 2주"를 뒷받침하는 story point도 과거 속도 데이터도 없다.

---

## 구현 범위

### 1. PRD에서 유지할 것 (재활용 가능한 기술적 사실)

**Problem Statement 팩트 재활용** — P1~P7의 기술적 관찰은 정확하다. 단, 서술 방식을 "코드에 X가 없다" → "X가 없어서 나는 Y를 겪는다"로 전환한다.

| 기존 서술 | 재작성 방향 |
|-----------|------------|
| "SlackAdapter는 재연결 로직이 없어 listen 루프가 조용히 종료" | "Slack 연결이 끊기면 Gateway가 멈춘다. 나는 메시지를 받지 못하면서도 Gateway가 살아있다고 착각한다" |
| "`ChannelType.GITHUB`가 enum에 있지만 어댑터 구현체가 없다" | "GitHub Issues/PR 알림을 받으려면 매번 GitHub 웹을 열어야 한다. Intelligence가 이 채널을 전혀 학습하지 못한다" |
| "`_create_adapter()`가 slack/gmail을 하드코딩" | "새 채널을 연결하려면 소스코드를 수정해야 한다. 설정 파일 수정 후 서버 재시작으로 해결되어야 할 일이 PR 작업이 된다" |

**Goals (Feature Requirements)** — FR-01~FR-08의 기능 목록과 Acceptance Criteria는 유지한다. 다만 코드 스니펫은 제거하고 동작 설명으로 대체한다.

**Risks & Mitigations** — Section 9의 기술 위험 분석은 정확하다. Edge Case 3건도 유지한다.

**Dependencies** — Section 10의 내부/외부 의존성 목록은 유지한다.

**Acceptance Criteria**: 유지할 섹션들이 원본 415줄에서 150줄 이하로 압축됨.

### 2. PRD에서 제거할 것

| 제거 대상 | 이유 | 이동 위치 |
|-----------|------|----------|
| Section 6 Technical Architecture 전체 (아키텍처 다이어그램, 파일 변경 요약 표, `HealthMetrics` dataclass 코드, `AdapterSupervisor` 코드 스니펫) | Design 결정이지 Product 요구사항이 아님 | `docs/02-design/channel-mastery.design.md` 신규 생성 |
| Section 8 Timeline & Phases의 작업 표 전체 | 근거 없는 예측. 구현 계획은 `docs/01-plan/`에 이미 존재 | `docs/01-plan/channel-mastery.plan.md` (기존 파일 유지) |
| Target Users의 2행 표 | 단일 사용자 도구에 불필요한 페르소나 분류 | 1~2줄 서술로 대체 |
| Feature Requirements 내 코드 스니펫 전체 (FR-01의 `GitHubAdapter.__init__`, FR-04의 json 예시 블록 등) | 구현 상세이지 요구사항이 아님 | design.md로 이동 |

### 3. PRD에서 새로 작성할 것

#### 3-1. 사용자 고통 기반 Problem Statement

단일 사용자(도구 제작자 본인)의 실제 마찰을 1인칭으로 서술한다.

```
"Gateway를 밤새 켜놨는데 아침에 Slack 연결이 끊겨 있다.
 언제 끊겼는지도 모른다. 놓친 메시지가 몇 개인지도 모른다.
 GitHub PR에 리뷰 요청이 왔는데 Slack에서 알림을 받기 전까지
 나는 모른다. Intelligence는 GitHub 채널을 아예 학습하지 못한다."
```

이 서술에서 추출되는 고통 3가지:
- **연결 실패 무음 종료**: Gateway가 죽었는데 나는 모른다
- **GitHub 채널 공백**: Intelligence가 GitHub 컨텍스트 없이 분석한다
- **채널 추가 장벽**: 새 채널 연결이 소스코드 수정 작업이 된다

#### 3-2. 사용자 가치 기반 Success Metrics

| 지표 | 현재 | 목표 | 측정 방법 |
|------|:----:|:----:|----------|
| 연결 실패 후 수동 재시작 필요 횟수 | 측정 안 됨(수동) | 0회/주 (자동 복구) | Gateway 로그의 `[RECONNECTED]` vs `[MANUAL_RESTART]` 횟수 |
| Gateway 연결 실패 인지 지연 | 알 수 없음 | 즉시 (status CLI로 확인 가능) | `python server.py status` 출력에 각 채널 마지막 수신 시간 표시 |
| GitHub 이벤트가 Intelligence에 도달하는 비율 | 0% | 100% (수신된 이벤트 기준) | intelligence.db의 `source="github"` 레코드 존재 여부 |
| 새 채널 추가에 소스코드 수정 필요 여부 | 필요 (server.py) | 불필요 (gateway.json만) | PR diff에 `scripts/gateway/*.py` 변경 없음 |

기술 지표(테스트 커버리지, 채널 수)는 보조 지표로 내리고 위 4개를 Primary Metrics로 설정한다.

#### 3-3. 진정한 Non-Goals

하기 유혹이 있는 항목만 Non-Goal로 명시한다:

- **Slack Socket Mode를 기본값으로 전환** — 실시간성이 매력적이나, polling으로 충분하고 Socket Mode는 방화벽 문제가 있다. 기본값 변경은 이번 범위 밖.
- **재연결 실패 시 Slack DM 알림 전송** — 자동화 욕구가 생기지만, Reporter를 통한 알림은 Gateway 자체 안정화 이후 단계다.
- **채널별 health 데이터 DB 영구 저장** — 모니터링 시스템처럼 만들고 싶어지지만, 메모리 기반으로 충분하다. 재시작하면 초기화되어도 무방하다.
- **GitHub webhook 방식 구현** — Push 기반이 polling보다 실시간이지만, 공인 IP 없는 로컬 환경에서 webhook 수신은 ngrok 의존성이 생긴다.

#### 3-4. 단일 사용자 도구에 맞는 간결한 형식

- Target Users: 표 제거, 2줄 서술 ("이 도구의 사용자는 나 자신이다. 개인 AI 비서를 상시 운영하는 개발자이며 동시에 구현자다.")
- Timeline: 주 단위 예측 제거, "Phase별 Acceptance Criteria 달성 순서로 진행" 서술로 대체
- Executive Summary: 기술 개선 프로젝트 소개 대신 "무엇이 불편했고 무엇이 달라지는가" 1단락

### 4. design.md 분리 계획

`docs/02-design/channel-mastery.design.md` 신규 생성. PRD에서 제거한 내용을 이동한다.

| design.md 포함 섹션 | 원본 위치 |
|---------------------|----------|
| 개선된 아키텍처 다이어그램 | PRD Section 6 |
| 파일 변경 요약 표 | PRD Section 6 |
| `HealthMetrics` dataclass 정의 | PRD Section 6 |
| `AdapterSupervisor` 재연결 전략 코드 | PRD Section 6 |
| `PluginAdapterRegistry` `importlib` 예시 | PRD FR-04 AC |
| `GitHubAdapter.__init__` 인터페이스 예시 | PRD FR-01 AC |
| `gateway.json` 설정 예시 JSON | PRD FR-04 AC |

**Acceptance Criteria**: design.md 생성 후 PRD에서 위 항목 제거, PRD에 design.md 링크 추가.

---

## 영향 파일

### 수정 파일

| 파일 | 변경 내용 |
|------|---------|
| `C:/claude/secretary/docs/prd/channel-mastery.prd.md` | PRD 전면 재작성 (415줄 → 약 150줄 목표) |

### 신규 생성 파일

| 파일 | 내용 |
|------|------|
| `C:/claude/secretary/docs/02-design/channel-mastery.design.md` | PRD에서 분리된 Technical Architecture 내용 |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `C:/claude/secretary/docs/01-plan/channel-mastery.plan.md` | 구현 계획은 정확하다. PRD와 별도로 유지 |
| `C:/claude/secretary/scripts/gateway/` 전체 | 문서 재작성이므로 소스코드 수정 없음 |

### 경로 검증

- `docs/prd/channel-mastery.prd.md` — 존재 확인 (415줄)
- `docs/01-plan/channel-mastery.plan.md` — 존재 확인 (113줄)
- `docs/02-design/` — 디렉토리 존재 여부 미확인, 신규 생성 필요할 수 있음
- `scripts/gateway/adapters/` — base.py, slack.py, gmail.py 존재 확인 (github.py 없음)

---

## 위험 요소

**위험 1: PRD 재작성이 사실상 신규 문서 작성이 되어 기존 plan.md와 내용 충돌**

PRD의 Feature Requirements (FR-01~FR-08)와 plan.md의 작업 목록 (CM-01~CM-11)은 현재 1:1 대응이다. PRD 재작성 시 FR 번호나 내용이 변경되면 plan.md도 수정이 필요하다.

완화: PRD의 FR 번호와 목록은 유지하되, 코드 스니펫만 제거하고 텍스트 내용은 보존한다.

**Edge Case 1: PRD에서 Technical Architecture를 제거했는데 구현자가 design.md를 보지 않는 경우**

PRD만 읽은 구현자가 `HealthMetrics` dataclass 구조를 모르고 임의 설계할 수 있다. 완화: PRD의 FR Acceptance Criteria에 "설계 상세는 `docs/02-design/channel-mastery.design.md` 참조" 링크를 명시한다.

**Edge Case 2: `docs/02-design/` 디렉토리가 없을 경우**

`docs/02-design/` 경로는 plan.md 기준 추정이며, 실제 존재하지 않을 수 있다. 완화: design.md 생성 전 디렉토리 존재 여부 확인 후 없으면 생성한다.

---

## 작업 순서

### 단계 1: PRD 섹션 분류 (제거/유지/신규 확정)

- 기존 415줄을 섹션별로 분류표 작성
- "제거 → design.md" / "유지" / "신규 작성" 3분류
- **완료 기준**: 분류표 완성, 재작성 후 예상 줄 수 확인

### 단계 2: design.md 생성 (PRD 분리 내용 이동)

- `docs/02-design/channel-mastery.design.md` 생성
- PRD Section 6 전체 + FR 내 코드 스니펫 이동
- **완료 기준**: design.md 파일 생성, 이동된 내용 누락 없음

### 단계 3: PRD 재작성

재작성 순서:

1. **Executive Summary 교체** — 기술 프로젝트 소개 → "무엇이 불편했고 무엇이 달라지는가" 1단락
2. **Problem Statement 재서술** — "코드에 없다" → "이것 때문에 나는 이런 불편을 겪는다"
3. **Target Users 교체** — 표 제거, 2줄 서술
4. **Success Metrics 교체** — 기술 지표 → 사용자 가치 지표 4개 Primary
5. **Non-Goals 재작성** — 면피용 → 유혹이 있는 항목 4개
6. **Feature Requirements 정리** — 코드 스니펫 제거, design.md 링크 추가
7. **Timeline 교체** — 주 단위 예측 → Phase별 완료 기준 서술
8. **Risks 유지** — 변경 없음
9. **Dependencies 유지** — 변경 없음

**완료 기준**:
- 재작성된 PRD 길이 200줄 이하
- 6가지 결함(Product 없음, 해결책 선행, Non-Goals 면피, 기술 지표, 형식 채우기, 근거 없는 Timeline) 모두 해소
- design.md 링크 포함

### 단계 4: plan.md 일관성 확인

- plan.md의 CM-01~CM-11이 재작성된 PRD의 FR 번호와 일치하는지 확인
- 불일치 시 plan.md의 PRD 참조 링크만 업데이트 (내용 변경 없음)
- **완료 기준**: plan.md에서 PRD 참조가 유효함

---

## PRD 재작성 후 예상 구조 (섹션 목차)

```
# Channel Mastery PRD

## 1. 한 줄 요약
## 2. 배경: 무엇이 불편했나
   - 연결 실패 무음 종료 (사용자 경험 서술)
   - GitHub 채널 공백
   - 채널 추가 장벽
## 3. 이 도구를 쓰는 사람
   - 2줄 서술 (표 없음)
## 4. 목표와 제외 범위
   ### Goals (FR-01~FR-08 요약)
   ### Non-Goals (유혹 있는 것 4개)
## 5. 기능 요구사항
   - P0: FR-01, FR-02, FR-03
   - P1: FR-04, FR-05, FR-06
   - P2: FR-07, FR-08
   (코드 스니펫 없음, design.md 링크)
## 6. 성공 지표
   - Primary: 사용자 가치 지표 4개
   - Secondary: 기술 지표 (테스트 커버리지 등)
## 7. 위험 요소
   (기존 Section 9 유지)
## 8. 의존성
   (기존 Section 10 유지)
```

총 예상 길이: 150~200줄 (기존 415줄 대비 50% 이상 감소)
