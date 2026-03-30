# Channel Mastery 전체 데이터 수집 PRD

**문서 버전**: 1.0.0
**작성일**: 2026-02-19
**대상 채널**: C0985UXQN6Q (#general)
**상태**: Draft

---

## 배경/목적

Slack 채널 #general(C0985UXQN6Q)의 채널 지식 문서(`config/channel_docs/C0985UXQN6Q.md`)와 AI 전문가 프로파일(`config/channel_contexts/C0985UXQN6Q.json`)이 Claude subprocess 실패로 인해 fallback 최소값으로 생성되어 있다.

현재 문서의 문제점:
- `channel_summary`: "채널 C0985UXQN6Q 분석 결과" — 실제 채널 내용이 반영되지 않은 기본값
- `member_profiles`: `{}` — 빈 객체 (Sonnet 분석 미수행)
- `커뮤니케이션 특성`: "추후 업데이트됩니다" — 실제 분석 없음
- `run_mastery()` 실행 기록 없음 — Slack 전체 히스토리 미수집 가능성

이 PRD는 다음을 목표로 한다:
1. `run_mastery()`를 통한 #general 채널 전체 히스토리 수집 및 Knowledge DB 저장
2. Claude subprocess 실패 원인 파악 및 수정
3. 채널 지식 문서(`C0985UXQN6Q.md`) 재생성 (AI 분석 기반)
4. AI 전문가 프로파일(`C0985UXQN6Q.json`) 재생성 (Sonnet 기반)

---

## 요구사항 목록

### 1. run_mastery() 실행 — Slack 전체 히스토리 수집

**파일**: `scripts/knowledge/bootstrap.py`

**현황**:
- `learn_slack_full()` 함수는 cursor-based pagination으로 전체 히스토리 수집을 지원한다
- `run_mastery()`는 learn_slack_full() → thread replies → 채널 메타데이터 수집 3단계를 오케스트레이션한다
- `_run_subprocess()`의 `cwd`가 `C:\claude`로 고정되어 있어 secretary 프로젝트의 `lib.slack`을 찾지 못할 수 있다

**요구사항**:
- 채널 C0985UXQN6Q에 대해 `run_mastery(project_id="general", channel_id="C0985UXQN6Q")`를 실행한다
- 전체 메시지(page_size=100, cursor pagination)를 수집하고 `data/knowledge.db`에 저장한다
- thread replies(reply_count > 0인 parent)를 포함하여 수집한다
- 채널 메타데이터(channel_name, topic, purpose, members, pins)를 수집한다
- 수집 완료 후 ingestion_state 체크포인트를 저장한다

**수락 기준**:
- `total_fetched` > 0 (실제 메시지 수집 확인)
- `total_ingested` > 0 (Knowledge DB 저장 확인)
- 오류 없이 완료되거나, 발생 오류가 보고되어야 함

---

### 2. Claude subprocess 실패 원인 파악 및 수정

**파일**: `scripts/knowledge/channel_prd_writer.py`, `scripts/knowledge/channel_sonnet_profiler.py`

**현황**:
- `ChannelPRDWriter._call_claude()`와 `ChannelSonnetProfiler._call_sonnet()`이 실패하여 fallback이 호출됨
- `shutil.which("claude")`로 claude 실행 파일 경로를 탐지하며, 실패 시 `None`이 반환됨
- 실패 원인은 다음 중 하나로 추정됨:
  - (a) `claude` 실행 파일이 PATH에 없음
  - (b) Claude subprocess 실행 시 환경 변수 누락 (인증 컨텍스트 미상속)
  - (c) subprocess가 비동기 timeout 내 응답하지 않음 (현재 PRDWriter: 180초, Profiler: 120초)
  - (d) subprocess 출력이 빈 문자열이거나 JSON 파싱 불가 포맷

**요구사항**:
- claude 실행 파일 경로를 직접 확인하고 로그에 기록한다
- subprocess 실패 시 stderr 전체를 로그에 출력한다 (현재 200자 또는 300자로 절삭)
- 실패 원인을 `returncode`, `stderr`, `timeout` 구분하여 진단 정보를 반환한다
- claude CLI 명령어에 `--no-verbose` 또는 적절한 flag를 추가하여 불필요한 출력을 제거한다
- 진단 후 실제 원인에 맞는 수정을 적용한다

**수락 기준**:
- 실패 원인이 로그에 명확히 기록됨
- 수정 후 재실행 시 claude subprocess가 정상 응답을 반환함

---

### 3. 정상적인 PRD 마크다운 재생성 (force=True)

**파일**: `scripts/knowledge/channel_prd_writer.py`
**출력**: `config/channel_docs/C0985UXQN6Q.md`

**현황**:
- 현재 파일은 fallback `_build_fallback_prd()`로 생성된 최소 내용을 포함
- `channel_summary`가 실제 채널 목적을 반영하지 않음
- `커뮤니케이션 특성` 섹션이 "추후 업데이트됩니다"로 미작성 상태

**요구사항**:
- `KnowledgeBootstrap.run_mastery()` 완료 후 수집된 mastery_context를 활용하여 재생성한다
- `ChannelPRDWriter.write(channel_id, mastery_context, force=True)`로 기존 파일을 덮어쓴다
- Claude subprocess가 정상 작동하는 경우 AI 분석 기반 내용을 생성한다
- Claude subprocess 실패가 지속되는 경우 수집된 실제 데이터 기반 fallback을 생성한다 (현재보다 풍부한 내용)
- 최소 포함 항목:
  - 채널 개요 (실제 목적 반영)
  - 주요 토픽 (TF-IDF 기반 키워드)
  - 핵심 의사결정 (패턴 매칭 추출)
  - 멤버 역할 (발언 패턴 분석)
  - 커뮤니케이션 특성 (실제 분석 결과)

**수락 기준**:
- `config/channel_docs/C0985UXQN6Q.md`에 "추후 업데이트됩니다" 문구 없음
- 실제 채널 데이터(키워드, 의사결정, 멤버 역할)가 반영됨
- 파일 크기가 fallback 기본값(36줄)보다 유의미하게 증가

---

### 4. 정상적인 AI 전문가 프로파일 재생성 (force=True)

**파일**: `scripts/knowledge/channel_sonnet_profiler.py`
**출력**: `config/channel_contexts/C0985UXQN6Q.json`

**현황**:
- 현재 파일은 fallback `_build_fallback()`로 생성된 최소 JSON
- `channel_summary`: "채널 C0985UXQN6Q 분석 결과" — 기본값 그대로
- `member_profiles`: `{}` — 멤버 프로파일 분석 없음
- `response_guidelines`: 채널 특성이 반영되지 않은 기본값

**요구사항**:
- `ChannelSonnetProfiler.build_profile(channel_id, mastery_context, force=True)`로 재생성한다
- Claude subprocess 정상 작동 시 Sonnet 분석 기반 JSON을 생성한다
- 최소 포함 항목:
  - `channel_summary`: 실제 채널 목적 요약 (2-3문장)
  - `communication_style`: 채널 대화 스타일 (기술적/비공식적 등)
  - `key_topics`: 실제 분석된 주요 토픽 목록
  - `key_decisions`: 실제 의사결정 내역
  - `member_profiles`: 주요 멤버 역할 정보
  - `response_guidelines`: 채널 특성 반영 응답 지침
  - `escalation_hints`: 실제 채널 컨텍스트 기반 에스컬레이션 기준

**수락 기준**:
- `channel_summary` 값이 "채널 C0985UXQN6Q 분석 결과"와 다름
- `member_profiles`가 실제 멤버 정보를 포함
- `key_topics`가 8개 이상이며 실제 채널 토픽을 반영

---

## 기능 범위

### In Scope

| 기능 | 설명 |
|------|------|
| Slack 전체 히스토리 수집 | `learn_slack_full()` cursor pagination, thread replies 포함 |
| 채널 메타데이터 수집 | channel info, members, pinned messages |
| Claude subprocess 진단 | 실패 원인 파악, 로그 개선, 수정 |
| 채널 지식 문서 재생성 | `C0985UXQN6Q.md` force=True 재생성 |
| AI 전문가 프로파일 재생성 | `C0985UXQN6Q.json` force=True 재생성 |
| Knowledge DB 저장 | `data/knowledge.db` ingestion 상태 체크포인트 |

### Out of Scope

| 기능 | 제외 이유 |
|------|-----------|
| 다른 채널 데이터 수집 | 이번 PRD는 C0985UXQN6Q 단일 채널 대상 |
| Gmail 히스토리 수집 | 별도 bootstrap 작업 |
| Gateway 파이프라인 변경 | 기존 실시간 수집 로직과 무관 |
| ChannelMasteryAnalyzer 로직 변경 | 분석 알고리즘 수정 불포함 |

---

## 비기능 요구사항

| 항목 | 요구사항 |
|------|---------|
| Rate Limiting | Slack API rate limit 준수: page 간 sleep 1.2초 (`learn_slack_full` 기본값) |
| 재시작 가능성 | cursor checkpoint 저장으로 중단 후 재실행 시 이어받기 지원 |
| 오류 내성 | 단일 메시지 처리 실패가 전체 수집을 중단시키지 않아야 함 |
| 타임아웃 | Claude subprocess: PRDWriter 180초, Sonnet Profiler 120초 |
| 멱등성 | 동일 메시지 재수집 시 `INSERT OR IGNORE` 중복 건너뜀 |
| 로그 | 각 단계별 진행 상황을 stdout에 출력 (page 단위, 완료 요약) |

---

## 제약사항

| 제약 | 내용 |
|------|------|
| 자동 전송 금지 | 수집/분석 결과를 자동으로 Slack에 전송하지 않음 |
| 운영 DB 직접 수정 금지 | `data/knowledge.db`는 KnowledgeStore API를 통해서만 접근 |
| `--confirm` 없는 Calendar 생성 금지 | 이번 작업에서 Calendar 연동 없음 |
| cwd 경로 | `_run_subprocess()`의 cwd가 `C:\claude`로 설정되어 있으므로 `lib.slack` 모듈 접근 가능 여부 사전 확인 필요 |
| Windows 환경 | Toast 알림(`test_actions.py`) 제외, 나머지 테스트는 mock 기반으로 실행 가능 |

---

## 우선순위

| 순위 | 요구사항 | 이유 |
|:----:|----------|------|
| P0 | 2. Claude subprocess 실패 원인 파악 및 수정 | 이후 모든 단계의 AI 분석 품질에 직접적 영향 |
| P1 | 1. run_mastery() 실행 — Slack 전체 히스토리 수집 | 분석 기반 데이터 없으면 P2/P3가 fallback에 의존 |
| P2 | 3. PRD 마크다운 재생성 (force=True) | 데이터 수집 완료 후 즉시 실행 |
| P2 | 4. AI 전문가 프로파일 재생성 (force=True) | 데이터 수집 완료 후 즉시 실행 |

**실행 순서**: P0 → P1 → P2(3번 + 4번 병렬 실행 가능)

---

## 실행 명령어 참조

```bash
# 1. run_mastery 실행 (전체 히스토리 수집)
cd C:\claude\secretary
python -m scripts.knowledge.bootstrap mastery C0985UXQN6Q --project general --page-size 100

# 2. Claude subprocess 진단
claude --version
which claude

# 3. PRD 재생성 (force=True)은 mastery 완료 후 별도 스크립트 또는 CLI 통해 실행

# 4. 테스트 실행 (전체, test_actions.py 제외)
pytest tests/ --ignore=tests/test_actions.py -v
```

---

*이 PRD는 Channel Mastery 재수집 및 AI 문서 재생성 작업의 실행 기준 문서입니다.*
