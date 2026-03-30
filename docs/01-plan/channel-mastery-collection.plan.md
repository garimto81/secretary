# Channel Mastery 수집 작업 계획

**문서 버전**: 1.0.0
**작성일**: 2026-02-19
**대상 채널**: C0985UXQN6Q (#general)
**우선순위**: P0 → P1 → P2(병렬)

---

## 배경 (Background)

`config/channel_docs/C0985UXQN6Q.md`와 `config/channel_contexts/C0985UXQN6Q.json`이
Claude subprocess 실패로 인해 fallback 최소값으로 생성된 상태다.

현재 파일의 문제점:
- `channel_summary`: "채널 C0985UXQN6Q 분석 결과" (기본값)
- `member_profiles`: `{}` (빈 객체, Sonnet 분석 미수행)
- `커뮤니케이션 특성`: "추후 업데이트됩니다" (실제 분석 없음)
- `key_topics` 8개만 존재 (PRD 요구: 8개 이상 실제 채널 토픽 반영)

**선행 조사 결과 (Lead 제공)**:
- `shutil.which("claude")` 정상 반환 — 경로 문제 아님
- 실패 원인 후보: JSON 이외 텍스트 혼입, stdin 없어 대화 모드 시도, 텍스트 출력 파싱 실패
- `python -m scripts.knowledge.bootstrap mastery C0985UXQN6Q --project general` 실행 확인됨

---

## 구현 범위 (Scope)

### 포함 항목

| 작업 | 대상 |
|------|------|
| Claude subprocess 실패 진단 | 직접 CLI 실행으로 출력 패턴 확인 |
| `_call_claude()` / `_call_sonnet()` 수정 | stdout JSON 추출, stdin 명시적 닫기 |
| `run_mastery()` 실행 | 전체 히스토리 수집 → knowledge.db 저장 |
| `C0985UXQN6Q.md` 재생성 (force=True) | Claude 성공 시 AI 분석, 실패 시 rich fallback |
| `C0985UXQN6Q.json` 재생성 (force=True) | Sonnet 성공 시 AI 프로파일, 실패 시 rich fallback |

### 제외 항목

- 다른 채널 수집 (이번 PRD는 C0985UXQN6Q 단일 채널)
- Gmail 히스토리 수집
- Gateway 파이프라인 변경
- ChannelMasteryAnalyzer 알고리즘 수정

---

## 영향 파일 (Affected Files)

### 수정 예정 파일

```
C:\claude\secretary\scripts\knowledge\channel_prd_writer.py     (L166-191 _call_claude)
C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py (L77-100 _call_sonnet)
```

### 재생성 파일 (force=True)

```
C:\claude\secretary\config\channel_docs\C0985UXQN6Q.md
C:\claude\secretary\config\channel_contexts\C0985UXQN6Q.json
```

### 데이터 파일 (자동 갱신)

```
C:\claude\secretary\data\knowledge.db       (ingestion 추가)
```

---

## 위험 요소 (Risks)

### Risk 1: Claude CLI 출력 형식 불일치

`claude -p "..." --output-format text` 실행 시 실제 stdout에:
- thinking 블록 (`<thinking>...</thinking>`) 이 포함될 수 있음
- 안내 텍스트 (`Note: ...`, `Claude 3.x ...`) 가 앞에 붙을 수 있음
- PRDWriter는 전체 stdout을 마크다운으로 저장하므로 노이즈 텍스트가 섞일 수 있음
- SonnetProfiler는 `output.find("{")` → `output.rfind("}")` 으로 JSON 추출하므로 비교적 안전하나, thinking 블록 내부에 `{}` 가 있으면 오추출 가능

### Risk 2: subprocess stdin 문제

`asyncio.create_subprocess_exec()` 시 `stdin` 파라미터 미지정 → 부모 프로세스의 stdin 상속
→ claude CLI가 대화형 입력을 기다리며 멈출 수 있음 (특히 Windows 환경)

현재 코드:
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    # stdin 미지정 → 상속됨
)
```

수정 필요: `stdin=asyncio.subprocess.DEVNULL` 명시

### Risk 3: run_mastery() 실행 중 rate limit

- Slack API: 페이지 간 1.2초 sleep 적용됨 (안전)
- 메시지 수가 많을 경우 수분 이상 소요 가능
- cursor checkpoint로 재시작 가능하므로 중단 시 재실행 가능

### Risk 4: bootstrap.py의 _run_subprocess cwd 경로

`cwd=str(Path(r"C:\claude"))` 고정 → `lib.slack`이 `C:\claude\lib\slack\` 에 존재해야 함
→ secretary 프로젝트의 `scripts/knowledge/` 모듈과 경로 불일치 가능성

---

## 태스크 목록 (Tasks)

---

### Task P0: Claude subprocess 실패 원인 진단

**목표**: 실제 claude CLI 실행 출력을 확인하고 실패 원인을 확정한다.

**수행 방법**:

```bash
# 1. claude 경로 확인
where claude

# 2. 직접 실행 — 출력 패턴 확인
"C:\Users\AidenKim\.local\bin\claude.EXE" -p "JSON으로만 응답: {\"test\": true}" --output-format text

# 3. stdin DEVNULL 방식으로 실행 (subprocess 환경 시뮬레이션)
python -c "
import subprocess, sys
result = subprocess.run(
    [r'C:\Users\AidenKim\.local\bin\claude.EXE', '-p', '{\"test\": true}', '--output-format', 'text'],
    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30
)
print('returncode:', result.returncode)
print('stdout:', repr(result.stdout[:500]))
print('stderr:', repr(result.stderr[:300]))
"
```

**판단 기준**:
- returncode != 0 → stderr 내용으로 원인 확정
- returncode == 0, stdout에 JSON 이외 텍스트 존재 → 파싱 필터 추가 필요
- returncode == 0, stdout 비어있음 → 출력 형식 flag 문제
- 프로세스가 응답 없이 멈춤 → stdin DEVNULL 미적용 확인

**Acceptance Criteria**:
- 실패 원인이 4가지 후보 중 하나로 확정됨
- 실행 결과 (returncode, stdout, stderr)가 plan 문서 또는 로그에 기록됨

---

### Task P0-Fix: subprocess 코드 수정 (진단 결과 적용)

**목표**: 진단 결과에 따라 `_call_claude()` 와 `_call_sonnet()` 를 수정한다.

**공통 수정 사항** (진단 결과와 무관하게 적용):

파일: `C:\claude\secretary\scripts\knowledge\channel_prd_writer.py` (L172-191)
파일: `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py` (L80-100)

```python
# 수정 전 (두 파일 공통 문제)
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)

# 수정 후 — stdin 명시적 닫기
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.DEVNULL,   # 추가
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**stderr 전체 로그 출력 수정**:

```python
# 수정 전 (channel_prd_writer.py L186)
err_msg = stderr.decode(errors="replace")[:300]   # 300자 절삭

# 수정 후
err_msg = stderr.decode(errors="replace")          # 전체 출력
logger.error(f"Claude subprocess stderr 전체:\n{err_msg}")
```

```python
# 수정 전 (channel_sonnet_profiler.py L92)
raise RuntimeError(f"Claude subprocess 실패: {stderr.decode()[:200]}")   # 200자 절삭

# 수정 후
err_full = stderr.decode(errors="replace")
logger.error(f"Claude subprocess stderr 전체:\n{err_full}")
raise RuntimeError(f"Claude subprocess 실패 (returncode={proc.returncode}): {err_full[:500]}")
```

**PRDWriter stdout 노이즈 제거** (진단에서 노이즈 텍스트 확인 시 추가):

```python
# channel_prd_writer.py _call_claude() 반환 직전
output = stdout.decode(errors="replace").strip()
# thinking 블록 제거
import re
output = re.sub(r'<thinking>.*?</thinking>', '', output, flags=re.DOTALL).strip()
if not output:
    return None
return output
```

**Acceptance Criteria**:
- 두 파일 모두 `stdin=asyncio.subprocess.DEVNULL` 적용됨
- stderr 전체가 로그에 출력됨 (절삭 없음)
- 수정 후 `python -c "import asyncio; ..."` 로 직접 _call_claude 호출 시 returncode/stderr 출력 확인

---

### Task P1: run_mastery() 실행 — 전체 히스토리 수집

**목표**: #general 채널 전체 히스토리를 knowledge.db에 저장한다.

**실행 명령어**:

```bash
cd C:\claude\secretary
python -m scripts.knowledge.bootstrap mastery C0985UXQN6Q --project general --page-size 100
```

**실행 흐름**:
```
  bootstrap mastery C0985UXQN6Q
       |
  [1/3] learn_slack_full()
       | cursor-based pagination (page_size=100, sleep=1.2s)
       | INSERT OR IGNORE → knowledge.db
       | cursor checkpoint 저장 (재시작 가능)
       |
  [2/3] _fetch_thread_replies()
       | parent_ts_list 순회 (reply_count > 0인 thread)
       | INSERT OR IGNORE → knowledge.db
       |
  [3/3] _collect_channel_metadata()
       | lib.slack info, members, pins 호출
       | 결과 summary dict 반환
       |
  완료 출력: total_fetched, total_ingested, threads, replies
```

**확인 항목**:
```bash
# 수집 결과 확인
python -c "
import asyncio
async def check():
    from scripts.knowledge.store import KnowledgeStore
    async with KnowledgeStore() as store:
        docs = await store.get_recent(project_id='general', limit=100, source='slack')
        print(f'knowledge.db slack 문서: {len(docs)}건')
asyncio.run(check())
"
```

**Acceptance Criteria**:
- `total_fetched` > 0 (실제 Slack 메시지 수집)
- `total_ingested` > 0 (knowledge.db 저장)
- 오류 없이 완료 또는 발생 오류가 stdout에 출력됨

---

### Task P2-A: 채널 지식 문서 재생성 (C0985UXQN6Q.md)

**목표**: `config/channel_docs/C0985UXQN6Q.md` 를 force=True로 재생성한다.

**실행 방법**:

```bash
cd C:\claude\secretary
python -c "
import asyncio
from scripts.knowledge.store import KnowledgeStore
from scripts.knowledge.channel_profile import ChannelProfileStore
from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer
from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

async def run():
    async with KnowledgeStore() as store:
        profile_store = ChannelProfileStore(store._connection)
        analyzer = ChannelMasteryAnalyzer(store, profile_store)
        mastery = await analyzer.build_mastery_context('general', 'C0985UXQN6Q')
        print('mastery_context:', list(mastery.keys()))
        print('keywords:', mastery.get('top_keywords', [])[:5])
        writer = ChannelPRDWriter()
        path = await writer.write('C0985UXQN6Q', mastery, force=True)
        print('저장 완료:', path)

asyncio.run(run())
"
```

**Acceptance Criteria**:
- `config/channel_docs/C0985UXQN6Q.md` 파일이 갱신됨
- "추후 업데이트됩니다" 문구가 파일에 없음
- 파일 라인 수 > 36 (현재 fallback 기본값 36줄)
- 실제 키워드, 의사결정, 멤버 역할이 반영됨

---

### Task P2-B: AI 전문가 프로파일 재생성 (C0985UXQN6Q.json)

**목표**: `config/channel_contexts/C0985UXQN6Q.json` 을 force=True로 재생성한다.

**실행 방법**:

```bash
cd C:\claude\secretary
python -c "
import asyncio
from scripts.knowledge.store import KnowledgeStore
from scripts.knowledge.channel_profile import ChannelProfileStore
from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer
from scripts.knowledge.channel_sonnet_profiler import ChannelSonnetProfiler

async def run():
    async with KnowledgeStore() as store:
        profile_store = ChannelProfileStore(store._connection)
        analyzer = ChannelMasteryAnalyzer(store, profile_store)
        mastery = await analyzer.build_mastery_context('general', 'C0985UXQN6Q')
        profiler = ChannelSonnetProfiler()
        result = await profiler.build_profile('C0985UXQN6Q', mastery, force=True)
        print('channel_summary:', result.get('channel_summary'))
        print('key_topics count:', len(result.get('key_topics', [])))
        print('member_profiles count:', len(result.get('member_profiles', {})))

asyncio.run(run())
"
```

**Acceptance Criteria**:
- `config/channel_contexts/C0985UXQN6Q.json` 파일이 갱신됨
- `channel_summary` 값이 "채널 C0985UXQN6Q 분석 결과"와 다름
- `key_topics` 8개 이상
- `member_profiles`에 실제 멤버 정보 포함 (Claude 성공 시)

**P2-A/P2-B 병렬 실행 가능**: run_mastery() 완료 후 독립 실행 가능

---

## 실행 순서 (Execution Order)

```
  +---------------------+
  | P0: 진단            |
  | claude CLI 직접 실행 |
  | stdout/stderr 확인   |
  +----------+----------+
             |
             v
  +---------------------+
  | P0-Fix: 코드 수정   |
  | stdin=DEVNULL        |
  | stderr 전체 로그     |
  | stdout 노이즈 제거   |
  +----------+----------+
             |
             v
  +---------------------+
  | P1: run_mastery()   |
  | 전체 히스토리 수집   |
  | knowledge.db 저장   |
  +-------+------+------+
          |      |
   (완료 후 병렬)
          |      |
     +----+  +---+
     |          |
     v          v
  +------+  +------+
  | P2-A |  | P2-B |
  | .md  |  | .json|
  | 재생성|  | 재생성|
  +------+  +------+
```

---

## 커밋 전략 (Commit Strategy)

```
fix(knowledge): Claude subprocess stdin DEVNULL 설정 및 stderr 전체 로그 출력

- channel_prd_writer.py: stdin=DEVNULL, stderr 전체 로그
- channel_sonnet_profiler.py: stdin=DEVNULL, stderr 전체 로그
```

```
feat(knowledge): C0985UXQN6Q 채널 mastery 수집 완료 및 문서 재생성

- config/channel_docs/C0985UXQN6Q.md: AI 분석 기반 재생성
- config/channel_contexts/C0985UXQN6Q.json: Sonnet 프로파일 재생성
```

---

## 참조 파일

| 파일 | 역할 |
|------|------|
| `C:\claude\secretary\scripts\knowledge\bootstrap.py` | run_mastery() 진입점, L612-690 |
| `C:\claude\secretary\scripts\knowledge\channel_prd_writer.py` | _call_claude(), L166-191 |
| `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py` | _call_sonnet(), L77-100 |
| `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` | build_mastery_context(), L76-141 |
| `C:\claude\secretary\config\channel_docs\C0985UXQN6Q.md` | 현재 fallback 상태 (36줄) |
| `C:\claude\secretary\config\channel_contexts\C0985UXQN6Q.json` | 현재 fallback 상태 |
| `C:\claude\secretary\data\knowledge.db` | Knowledge DB (수집 대상) |
