# 채널 마스터리 분석 실행 계획

**작성**: 2026-02-20 | **복잡도**: LIGHT 1/5 | **담당**: Executor

---

## 배경 (Background)

C0985UXQN6Q(#general) 채널에 대해 이미 수집된 100개의 Slack 메시지를 바탕으로 TF-IDF 마스터리 분석을 실행하고, 그 결과를 채널 지식 문서(PRD)와 AI 응답 컨텍스트(JSON)로 재생성하는 일회성 분석 작업입니다.

**현황**:
- data/knowledge.db: 100개 Slack 문서 수집 완료 (project=general, source=slack)
- data/knowledge.db channel_profiles: C0985UXQN6Q 프로파일 저장됨
- config/channel_docs/C0985UXQN6Q.md: fallback 마크다운 존재
- config/channel_contexts/C0985UXQN6Q.json: fallback JSON 존재

**목표**: 최신 mastery 분석을 반영하여 채널 지식 문서와 컨텍스트를 재생성

---

## 구현 범위 (Scope)

### 포함 항목 (In Scope)

1. **ChannelMasteryAnalyzer 실행**
   - build_mastery_context(project_id='general', channel_id='C0985UXQN6Q') 호출
   - TF-IDF 키워드 추출 (상위 20개)
   - 의사결정 패턴 매칭 (정규식 6개)
   - 멤버 역할 분류 (발언량, 액션, 요청 패턴)
   - 활성 토픽 추출 (최근 30일 공출현 분석)
   - 결과: mastery_context 딕셔너리 생성

2. **ChannelPRDWriter 재생성**
   - force=True로 호출하여 기존 파일 덮어쓰기
   - config/channel_docs/C0985UXQN6Q.md 재생성
   - Claude Sonnet 호출 시도 → fallback 마크다운 생성

3. **ChannelSonnetProfiler 재생성**
   - force=True로 호출하여 기존 파일 덮어쓰기
   - config/channel_contexts/C0985UXQN6Q.json 재생성
   - Claude Sonnet 호출 시도 → fallback JSON 생성

### 제외 항목 (Out of Scope)

- 새로운 Slack 메시지 수집 (이미 수집된 100개만 사용)
- 채널 멤버 프로파일 업데이트 (기존 profile 기반)
- 다른 채널에 대한 마스터리 분석
- 분석 결과 검증 또는 수정

---

## 영향 파일 (Affected Files)

### 수정 예정 파일

| 파일 경로 | 변경 유형 | 설명 |
|----------|----------|------|
| `C:\claude\secretary\config\channel_docs\C0985UXQN6Q.md` | 덮어쓰기 | PRD 마크다운 재생성 |
| `C:\claude\secretary\config\channel_contexts\C0985UXQN6Q.json` | 덮어쓰기 | 채널 컨텍스트 JSON 재생성 |

### 읽기 전용 파일

| 파일 경로 | 사용 목적 |
|----------|----------|
| `C:\claude\secretary\data\knowledge.db` | 100개 Slack 메시지 로드 |
| `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` | TF-IDF 분석 알고리즘 |
| `C:\claude\secretary\scripts\knowledge\channel_prd_writer.py` | PRD 생성 로직 |
| `C:\claude\secretary\scripts\knowledge\channel_sonnet_profiler.py` | 컨텍스트 JSON 생성 로직 |

---

## 위험 요소 (Risks)

### Risk 1: Claude CLI Subprocess Hang (중소)
**설명**: `ChannelPRDWriter._call_claude()` 및 `ChannelSonnetProfiler._call_sonnet()`에서 Claude CLI subprocess가 hang될 가능성

**발생 가능성**: 40% (Claude Code 환경에서 CLAUDECODE 환경변수 제거 이후 실패 사례 존재)

**영향도**: 중소 (fallback 로직이 자동으로 작동하여 최소 마크다운/JSON 생성)

**완화 조치**:
- Timeout 180초 설정 (channel_prd_writer.py:19)
- Timeout 120초 설정 (channel_sonnet_profiler.py:22)
- 예외 발생 시 mastery_context 기반 fallback 자동 생성
- 로그 기록: "Claude subprocess 타임아웃", "Claude subprocess 호출 실패"

**검증 방법**:
- 생성된 파일이 존재하는지 확인
- fallback 마크다운/JSON에는 "분석 데이터" 텍스트 포함 여부 확인

---

### Risk 2: 부정확한 의사결정 패턴 매칭 (중소)
**설명**: DECISION_PATTERNS 정규식(6개)이 실제 의사결정을 모두 포착하지 못할 수 있음

**발생 가능성**: 20% (채널 특수 표현이 있을 경우)

**영향도**: 낮음 (의사결정 추출은 선택 분석, 필수 아님)

**완화 조치**:
- 의사결정 추출 실패 시 빈 리스트 반환 (mastery_analyzer.py:105-111)
- 폴백 PRD에서 "(확정된 결정사항 없음)"으로 표시

---

### Risk 3: 멤버 역할 분류 오류 (낮음)
**설명**: 액션 키워드 비율(15%) 또는 요청 패턴 비율(20%) 임계값이 데이터에 맞지 않을 수 있음

**발생 가능성**: 15% (100개 메시지로는 충분한 통계량)

**영향도**: 낮음 (역할은 힌트용, 정확성 필수 아님)

**검증 방법**:
- 생성된 member_roles에 3명 이상의 멤버 역할이 추출되었는지 확인

---

## 태스크 목록 (Tasks)

### T1: 분석 환경 준비

**설명**: Python 런타임, 필수 모듈(KnowledgeStore, ChannelProfileStore, ChannelMasteryAnalyzer) 검증

**수행 방법**:
```bash
# C:\claude\secretary에서 실행
cd C:\claude\secretary
python -c "from scripts.knowledge.store import KnowledgeStore; from scripts.knowledge.channel_profile import ChannelProfileStore; print('OK')"
```

**Acceptance Criteria**:
- [ ] 스크립트 실행 시 "OK" 출력
- [ ] ModuleNotFoundError 발생 없음
- [ ] requirements.txt 검증 완료 (aiosqlite, sqlite3 설치됨)

---

### T2: ChannelMasteryAnalyzer 실행

**설명**: build_mastery_context(project_id='general', channel_id='C0985UXQN6Q') 호출하여 mastery 분석 수행

**수행 방법**:
```python
# scripts/knowledge/test_mastery_run.py (임시 테스트 스크립트)
import asyncio
from scripts.knowledge.store import KnowledgeStore
from scripts.knowledge.channel_profile import ChannelProfileStore
from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer

async def main():
    store = KnowledgeStore()
    profile_store = ChannelProfileStore()
    analyzer = ChannelMasteryAnalyzer(store, profile_store)

    result = await analyzer.build_mastery_context(
        project_id='general',
        channel_id='C0985UXQN6Q'
    )

    print("=== Mastery Context ===")
    print(f"Keywords: {result['top_keywords'][:5]}")
    print(f"Decisions: {len(result['key_decisions'])}")
    print(f"Members: {list(result['member_roles'].keys())}")

    return result

result = asyncio.run(main())
```

**실행 위치**: `C:\claude\secretary`

**Acceptance Criteria**:
- [ ] mastery_context 딕셔너리 생성 성공
- [ ] top_keywords 최소 5개 이상 추출
- [ ] member_roles 최소 1명 이상
- [ ] key_decisions 최소 0개 이상 (빈 리스트도 허용)
- [ ] 로그에 exception 없음

---

### T3: ChannelPRDWriter 재생성

**설명**: force=True로 ChannelPRDWriter.write()를 호출하여 config/channel_docs/C0985UXQN6Q.md 파일 덮어쓰기

**수행 방법**:
```python
# 위 T2의 결과를 이어받아
from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

async def write_prd():
    writer = ChannelPRDWriter(model="claude-sonnet-4-5", timeout=180)
    output_path = await writer.write(
        channel_id='C0985UXQN6Q',
        mastery_context=result,
        force=True
    )
    print(f"PRD 저장: {output_path}")
    return output_path

prd_path = asyncio.run(write_prd())
```

**실행 위치**: `C:\claude\secretary`

**Acceptance Criteria**:
- [ ] `config/channel_docs/C0985UXQN6Q.md` 파일 생성/업데이트
- [ ] 파일 크기 > 500 bytes
- [ ] 마크다운 구조 검증:
  - `# {channel_name} 지식 문서` 헤더 존재
  - `## 채널 개요`, `## 주요 토픽`, `## 핵심 의사결정`, `## 멤버 역할` 섹션 존재
- [ ] 파일 인코딩: UTF-8

---

### T4: ChannelSonnetProfiler 재생성

**설명**: force=True로 ChannelSonnetProfiler.build_profile()을 호출하여 config/channel_contexts/C0985UXQN6Q.json 파일 덮어쓰기

**수행 방법**:
```python
# 위 T2의 결과를 이어받아
from scripts.knowledge.channel_sonnet_profiler import ChannelSonnetProfiler

async def build_context():
    profiler = ChannelSonnetProfiler(model="claude-sonnet-4-5", timeout=120)
    result_json = await profiler.build_profile(
        channel_id='C0985UXQN6Q',
        mastery_context=result,
        force=True
    )
    print(f"Context JSON: {result_json}")
    return result_json

context_json = asyncio.run(build_context())
```

**실행 위치**: `C:\claude\secretary`

**Acceptance Criteria**:
- [ ] `config/channel_contexts/C0985UXQN6Q.json` 파일 생성/업데이트
- [ ] 파일 크기 > 500 bytes
- [ ] JSON 구조 검증:
  - `channel_id`, `channel_summary`, `communication_style` 필드 존재
  - `key_topics` 배열 최소 3개 항목
  - `response_guidelines`, `escalation_hints` 필드 존재
- [ ] JSON 유효성 검증 (`json.load()` 가능)
- [ ] 파일 인코딩: UTF-8

---

### T5: 생성 결과 검증

**설명**: 재생성된 파일들의 일관성 및 품질 확인

**수행 방법**:
```bash
# 파일 존재 확인
ls -l C:\claude\secretary\config\channel_docs\C0985UXQN6Q.md
ls -l C:\claude\secretary\config\channel_contexts\C0985UXQN6Q.json

# JSON 유효성 검증
python -c "import json; json.load(open('C:\claude\secretary\config\channel_contexts\C0985UXQN6Q.json'))"

# 마크다운 헤더 검증
grep "^## " C:\claude\secretary\config\channel_docs\C0985UXQN6Q.md
```

**Acceptance Criteria**:
- [ ] 두 파일 모두 존재, 크기 > 500 bytes
- [ ] JSON 파일 유효성 검증 통과 ("OK" 출력)
- [ ] 마크다운 파일에서 최소 4개의 ## 섹션 헤더 발견
- [ ] 두 파일의 channel_id 일치 (C0985UXQN6Q)
- [ ] 생성 타임스탬프 최신 (2026-02-20 이후)

---

## 커밋 전략 (Commit Strategy)

### 커밋 1: 채널 마스터리 분석 재생성 (force=true)

**Conventional Commit 형식**:
```
feat(knowledge): 채널 C0985UXQN6Q 마스터리 분석 재실행 (TF-IDF + 의사결정)

- ChannelMasteryAnalyzer: 100개 메시지 기반 TF-IDF 분석 완료
- ChannelPRDWriter: config/channel_docs/C0985UXQN6Q.md 재생성 (force=true)
- ChannelSonnetProfiler: config/channel_contexts/C0985UXQN6Q.json 재생성 (force=true)
- TF-IDF 상위 키워드: 20개 추출
- 멤버 역할 분류: 3명 식별
- Claude 호출 실패 시 fallback 마크다운/JSON 자동 생성

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

**포함 파일**:
- `config/channel_docs/C0985UXQN6Q.md`
- `config/channel_contexts/C0985UXQN6Q.json`

**Scope**: git add (해당 파일만)

---

## 부록: 동작 검증 스크립트

**파일**: `C:\claude\secretary\scripts\knowledge\test_mastery_run.py` (선택사항 — 구현 후 삭제)

```python
"""테스트: 채널 C0985UXQN6Q 마스터리 분석 재실행"""
import asyncio
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_channel_mastery():
    """
    1. ChannelMasteryAnalyzer 실행
    2. ChannelPRDWriter로 PRD 재생성
    3. ChannelSonnetProfiler로 JSON 재생성
    4. 파일 검증
    """
    try:
        from scripts.knowledge.store import KnowledgeStore
        from scripts.knowledge.channel_profile import ChannelProfileStore
        from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter
        from scripts.knowledge.channel_sonnet_profiler import ChannelSonnetProfiler
    except ImportError:
        from knowledge.store import KnowledgeStore
        from knowledge.channel_profile import ChannelProfileStore
        from knowledge.mastery_analyzer import ChannelMasteryAnalyzer
        from knowledge.channel_prd_writer import ChannelPRDWriter
        from knowledge.channel_sonnet_profiler import ChannelSonnetProfiler

    channel_id = "C0985UXQN6Q"
    project_id = "general"

    # Step 1: Mastery Analysis
    logger.info(f"Step 1: ChannelMasteryAnalyzer 실행 ({channel_id})")
    store = KnowledgeStore()
    profile_store = ChannelProfileStore()
    analyzer = ChannelMasteryAnalyzer(store, profile_store)

    mastery_context = await analyzer.build_mastery_context(
        project_id=project_id,
        channel_id=channel_id,
        top_n_keywords=20
    )

    logger.info(f"  ✓ Keywords: {mastery_context['top_keywords'][:5]}")
    logger.info(f"  ✓ Decisions: {len(mastery_context['key_decisions'])} items")
    logger.info(f"  ✓ Members: {list(mastery_context['member_roles'].keys())}")

    # Step 2: PRD Writer
    logger.info(f"Step 2: ChannelPRDWriter.write() (force=true)")
    writer = ChannelPRDWriter(timeout=180)
    prd_path = await writer.write(
        channel_id=channel_id,
        mastery_context=mastery_context,
        force=True
    )
    logger.info(f"  ✓ PRD 저장: {prd_path}")
    logger.info(f"  ✓ 파일 크기: {prd_path.stat().st_size} bytes")

    # Step 3: Sonnet Profiler
    logger.info(f"Step 3: ChannelSonnetProfiler.build_profile() (force=true)")
    profiler = ChannelSonnetProfiler(timeout=120)
    context_json = await profiler.build_profile(
        channel_id=channel_id,
        mastery_context=mastery_context,
        force=True
    )
    logger.info(f"  ✓ JSON 생성 완료")
    logger.info(f"  ✓ channel_summary: {context_json.get('channel_summary', '')[:50]}...")

    # Step 4: Validation
    logger.info(f"Step 4: 파일 검증")

    context_path = Path(__file__).resolve().parent.parent.parent / "config" / "channel_contexts" / f"{channel_id}.json"
    if context_path.exists():
        with open(context_path) as f:
            json_data = json.load(f)
        logger.info(f"  ✓ JSON 유효성 검증 완료")
        logger.info(f"  ✓ key_topics: {json_data.get('key_topics', [])[:3]}")
    else:
        logger.warning(f"  ✗ JSON 파일 찾기 실패: {context_path}")

    if prd_path.exists():
        logger.info(f"  ✓ PRD 파일 존재 확인")
        prd_content = prd_path.read_text(encoding="utf-8")
        sections = [s for s in ["## 채널 개요", "## 주요 토픽", "## 핵심 의사결정"] if s in prd_content]
        logger.info(f"  ✓ 마크다운 섹션: {len(sections)}/3 발견")
    else:
        logger.warning(f"  ✗ PRD 파일 찾기 실패: {prd_path}")

    logger.info("=== 모든 작업 완료 ===")

if __name__ == "__main__":
    asyncio.run(run_channel_mastery())
```

---

## 요약

| 항목 | 상세 |
|------|------|
| **작업 유형** | 데이터 분석 및 문서 재생성 |
| **예상 시간** | 3-5분 (Claude API 대기 제외) |
| **복잡도** | LIGHT 1/5 |
| **태스크 수** | 5개 |
| **위험도** | 중소 (fallback 로직으로 안정화) |
| **결과물** | 2개 파일 재생성 (PRD + JSON) |
| **롤백 전략** | git checkout — config/channel_docs/C0985UXQN6Q.md config/channel_contexts/C0985UXQN6Q.json |

