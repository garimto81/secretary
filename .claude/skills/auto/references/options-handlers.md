# /auto 옵션 핸들러 — Phase 2.0 상세 워크플로우

> 이 파일은 `--mockup`, `--anno`, `--critic` 등 옵션 사용 시 로딩됩니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

> **GUARD**: 이 파일이 로딩되지 않은 상태에서 실행 옵션(--con, --mockup 등)을 처리하면 hallucination이 발생합니다. SKILL.md Step 0.1에서 반드시 Read 완료 후 처리할 것.

---

## Step 2.0: 옵션 처리 개요

옵션이 있으면 구현 진입 전에 처리. 실패 시 에러 출력 후 중단 (조용한 스킵 금지).

| 옵션 | 설명 | 위치 |
|------|------|------|
| `--mockup [파일]` | 3-Tier 자동 목업 생성 | 이 파일 |
| `--mockup-q` | Quasar White Minimal 목업 | 이 파일 |
| `--quasar` | Quasar Material Design 목업 | 이 파일 |
| `--anno [파일]` | Screenshot→HTML→Annotation | 이 파일 |
| `--critic` | 약점 분석 + 웹 리서치 3-Phase | 이 파일 |
| `--debate` | 3-AI 병렬 분석 합의 판정 | 이 파일 |
| `--research` | 코드베이스/외부 리서치 | 이 파일 |
| `--daily` | 일일 대시보드 9-Phase | 이 파일 |
| `--jira` | Jira 조회/분석 | 이 파일 |
| `--figma` | Figma 디자인 연동 | 이 파일 |
| `--gdocs` | Google Docs PRD 동기화 | 이 파일 |
| `--slack` | Slack 채널 분석 컨텍스트 | 이 파일 |
| `--gmail` | Gmail 분석 컨텍스트 | 이 파일 |
| `--interactive` | Phase 전환 시 사용자 확인 | 이 파일 |
| `--con` | Confluence 발행 | 이 파일 |
| `--skip-prd` | Phase 1.1 PRD 스킵 | 이 파일 |
| `--skip-analysis` | Phase 1.2 분석 스킵 | 이 파일 |
| `--no-issue` | Phase 1.5 이슈 연동 스킵 | 이 파일 |

---

## `--mockup [파일]` — 3-Tier 자동 목업 생성 (4-Step)

정본: `mockup-hybrid/SKILL.md` v2.1. 3-Tier 라우팅(Mermaid/HTML/Stitch)이 출력 형식을 자동 결정.

### Pre-step: ASCII Layout Approval (프로젝트 조건부)

프로젝트 CLAUDE.md에 "ASCII 목업" 또는 "UI Design Workflow" 규칙이 존재하면 자동 활성화:
1. Lead가 터미널에 ASCII 와이어프레임 직접 출력 (65자 폭 제한)
2. 사용자 승인 대기 (AskUserQuestion)
3. 승인 → Step 1 진행 / 거부 → ASCII 수정 후 재출력

### Step 1: 라우팅 + 기본 HTML 생성 (Lead 직접 Python 호출)

```python
import sys; sys.path.insert(0, 'C:/claude'); sys.path.insert(0, 'C:/claude/.claude')
from pathlib import Path
from lib.mockup_hybrid import MockupOptions
from skills.mockup_hybrid.core.router import MockupRouter

router = MockupRouter()
options = MockupOptions(bnw={bnw_flag})
# --quasar 옵션 시 Quasar Material Design, --mockup-q 시 White Minimal
if mockup_q_flag:
    options = MockupOptions(style="quasar-white")
elif quasar_flag:
    options = MockupOptions(style="quasar")
result = router.route(prompt="{prompt}", options=options)
# 산출물: docs/mockups/{name}.html
```

**Mode A: 문서 기반** (`--mockup docs/02-design/auth.design.md`)
```
target_doc = options.get("mockup")
# Read(target_doc) → 헤딩 기반 섹션 분리 → 키워드 매칭 (NEED/SKIP/EXIST)
# NEED 섹션 → 3-Tier 라우팅 (Mermaid/HTML/Stitch)
```

**Mode B: 단건** (`/auto "대시보드 화면" --mockup`)
```
# 3-Tier 라우팅 (키워드 기반) → HTML/Mermaid/Stitch 자동 선택
```

### Step 2: designer 스타일링 (HTML 선택 시)

```
if options.style == "quasar-white":
    Agent(subagent_type="designer", name="mockup-designer", description="Quasar White 목업 디자인", team_name="pdca-{feature}",
         prompt="[Mockup Quasar White] docs/mockups/{name}.html을 Quasar White Tone Minimal로 스타일링.
                 Quasar UMD 컴포넌트: q-toolbar, q-card flat bordered, q-input outlined, q-btn color='grey-8'.
                 self-closing 태그 금지 (<q-input /> → <q-input></q-input>).
                 Roboto 300/400/500/700. --q-primary: #374151, Page BG: #ffffff.
                 Header: bg-white text-dark + border-bottom. Card: flat bordered.
                 max-width: 720px, max-height: 1280px.
                 designer.md의 Quasar White Tone Minimal 섹션 참조.")
elif options.style == "quasar":
    Agent(subagent_type="designer", name="mockup-designer", description="Quasar 목업 디자인", team_name="pdca-{feature}",
         prompt="[Mockup Quasar] docs/mockups/{name}.html을 Quasar Material Design으로 스타일링.
                 Quasar UMD 컴포넌트: q-toolbar, q-card, q-input outlined, q-btn, q-table.
                 self-closing 태그 금지. Roboto 300/400/500/700.
                 max-width: 720px, max-height: 1280px.
                 designer.md의 Quasar Material Design 섹션 참조.")
else:
    Agent(subagent_type="designer", name="mockup-designer", description="목업 디자인", team_name="pdca-{feature}",
         prompt="[Mockup B&W] docs/mockups/{name}.html을 Refined Minimal B&W 스타일로 스타일링.
                 팔레트: #222326, #555555, #8a8a8a, #767676, #e5e5e5, #F4F5F8, #fff만.
                 emoji/SVG/icon font 금지. Inter 400/500/600 단일 서체.
                 max-width: 720px, max-height: 1280px.
                 designer.md의 B&W Refined Minimal 섹션 참조.")
SendMessage(type="message", recipient="mockup-designer", content="스타일링 시작.")
# Mermaid 선택 시 이 Step 스킵
```

### Step 3: PNG 캡처 (Lead 직접 Bash 실행)

```bash
python -c "
import sys; sys.path.insert(0, 'C:/claude')
from pathlib import Path
from lib.mockup_hybrid.export_utils import capture_screenshot, get_output_paths
html_path = Path('docs/mockups/{name}.html')
_, img_path = get_output_paths('{name}')
result = capture_screenshot(html_path, img_path, auto_size=True)
print(f'CAPTURED: {result}' if result else 'CAPTURE_FAILED')
"
```

### Step 4: 문서 삽입 (대상 문서가 있는 경우만)

- 캡처 성공: `![{name}](docs/images/mockups/{name}.png)` + `[HTML 원본](docs/mockups/{name}.html)`
- 캡처 실패: `[{name} 목업](docs/mockups/{name}.html)` + 경고 메시지
- 대상 문서 없음: 삽입 스킵

### 스타일 요약

| 옵션 | 스타일 | 팔레트 |
|------|--------|--------|
| 기본 | B&W Refined Minimal | #222326, #555555, #8a8a8a, #e5e5e5, #F4F5F8, #fff |
| `--quasar` | Quasar Material Design | Quasar 자체 색상 |
| `--mockup-q` | Quasar White Minimal | #374151 (primary), #fff (BG) |

**`--bnw`**: deprecated (파싱만, 무시됨). 기본이 B&W.

**에러 처리**: 실패 시 에러 메시지 출력 + Phase 2 BUILD 중단. 조용한 스킵 금지.

---

## `--anno [파일]` — Screenshot→HTML→Annotation 워크플로우 (5-Step)

pywinauto UIA 기반 annotation 한계(커스텀 컨트롤 30%+ 미검출, DPI drift) 우회. Vision AI + HTML 재현 방식.

**대상 스크린샷 (6장):**
```
gfx1_live.png, gfx2_live.png, gfx3_live.png,
sources_live.png, outputs_live.png, system_live.png
경로: C:\claude\ui_overlay\docs\03-analysis\
```

### Step 1: Vision AI 분석 (Lead 직접)

```
# Claude Vision API로 스크린샷 분석
# 출력: UI 요소 리스트 (name, group, approximate position, control_type)
# 그룹핑: 기능적 연관성 기준 (예: "Player Stats", "Board Cards")
```

### Step 2: designer HTML 생성

```python
Agent(subagent_type="designer", name="anno-designer", description="Anno HTML 생성", team_name="pdca-{feature}",
     prompt="""[Anno HTML] {tab_name}_live.png 스크린샷을 참조하여 구조 중심 HTML 생성.

     필수 규칙:
     1. 모든 UI 요소에 data-element-id (고유 정수), data-element-name (영문), data-element-group (소속 그룹) 속성 필수
     2. viewport = 원본 스크린샷 해상도와 동일 (PIL.Image.open으로 확인)
     3. CSS absolute positioning 기반 (bbox 정확도 최우선)
     4. 레이아웃/배치/크기: 원본과 정확히 일치. 색상/폰트: 근사치 허용
     5. 출력: html_reproductions/{tab_name}_live.html

     Step 1 분석 결과: {vision_analysis}""")
SendMessage(type="message", recipient="anno-designer", content="HTML 생성 시작.")
```

### Step 2.5: 배치 모드 자동 감지 (NEW — 반복 프롬프트 분석 2026-03-25)

```python
# --anno 인자가 디렉토리인 경우 → 해당 디렉토리 내 *.png 전수 처리
# --anno 인자 없음 → docs/mockups/ 또는 docs/03-analysis/ 자동 탐색
# --anno 인자가 파일인 경우 → 기존 단일 파일 처리

import os
anno_arg = options.get("anno", "")
if os.path.isdir(anno_arg):
    screenshots = [os.path.join(anno_arg, f) for f in os.listdir(anno_arg) if f.endswith(".png")]
elif not anno_arg:
    # 프로젝트 내 docs/mockups/ 자동 탐색
    for candidate in ["docs/mockups/", "docs/03-analysis/"]:
        if os.path.isdir(candidate):
            screenshots = [os.path.join(candidate, f) for f in os.listdir(candidate) if f.endswith(".png")]
            break
else:
    screenshots = [anno_arg]  # 단일 파일

# 각 스크린샷에 대해 Step 1-5 반복 실행
for screenshot in screenshots:
    # Step 1: Vision AI 분석 → Step 2: designer HTML → Step 3-5: anno_workflow.py
    pass
```

### Step 3-5: anno_workflow.py 실행 (Lead Bash)

```bash
# 단일 탭
python C:/claude/ui_overlay/scripts/anno_workflow.py --screenshot C:/claude/ui_overlay/docs/03-analysis/{tab}_live.png

# 전체 6장
python C:/claude/ui_overlay/scripts/anno_workflow.py --all
```

내부 동작:
- Step 3-4: `html_to_elements.py` — Playwright viewport=스크린샷 해상도 → `querySelectorAll('[data-element-id]')` → bbox JSON
- Step 5: `annotate_screenshot.py` — JSON + 원본 PNG → annotated PNG (overview + detail)

**에러 처리:**
- `data-element-id` 없는 HTML: exit code 1
- Playwright 미설치: `playwright install chromium` 안내
- 스크린샷/HTML 미존재: SKIP + 다음 탭 진행

**산출물:**
- `html_reproductions/{tab}_live.html`
- `elements/{tab}_live.json` (element_schema v1.2)
- annotated PNG (overview + detail)

---

## `--critic` — 약점/문제점 분석 + 웹 리서치 (3-Phase)

> **파이프라인**: Phase A (Critic 분석) → Phase B (웹 리서치) → Phase C (솔루션 보고서)

### Phase A: Critic 분석

```
Agent(subagent_type="critic", name="critic-analyst", description="약점/문제점 adversarial 분석", team_name="pdca-{feature}",
     prompt="[Critic Mode] 아래 대상을 adversarial하게 분석하여 약점과 문제점을 찾아라.
             대상: {사용자가 지정한 문서/코드/설계 경로 또는 내용}

             Attack Vectors:
             A1: Logical Gaps — 논리적 빈틈, 근거 없는 가정
             A2: Failure Scenarios — 실패 시나리오, 미처리 엣지 케이스
             A3: Ambiguity & Vagueness — 모호한 표현, 측정 불가 기준
             A4: Contradictions — 내부 모순, 기존 아키텍처 충돌
             A5: Missing Context — 누락된 의존성/참조/이해관계자
             A6: Overengineering — 불필요한 복잡성, 범위 초과
             A7: OOP Design Violations — 제어 결합도(3+), God Module, 순환 의존성, DIP 위반, Fat Interface

             출력 형식:
             VERDICT: DESTROYED | QUESTION | SURVIVED

             ## Weaknesses Found
             ### [W1] {제목}
             - **Vector**: A1-A7
             - **Severity**: Critical | Major | Minor
             - **Problem**: 구체적 문제 설명
             - **Impact**: 방치 시 결과
             - **Search Query**: 솔루션 검색 키워드 (영문)")
SendMessage(type="message", recipient="critic-analyst", content="Critic 분석 시작.")
```

### Phase B: 웹 리서치

```
Agent(subagent_type="researcher", name="solution-researcher", description="약점별 웹 솔루션 리서치", team_name="pdca-{feature}",
     prompt="[Solution Research] critic 분석에서 발견된 약점별로 웹 리서치를 수행하라.
             ## Critic 분석 결과:
             {Phase A critic-analyst의 결과 전문}

             ## 리서치 지침:
             1. Critical/Major severity 약점만 리서치 (Minor는 스킵)
             2. 각 weakness의 Search Query를 사용하여 WebSearch + WebFetch 실행
             3. 공식 문서, GitHub 이슈, Stack Overflow, 기술 블로그 우선
             4. 각 약점별 최소 2개 솔루션 후보 제시

             ## 출력 형식:
             ### [W1] {약점 제목}
             #### Solution A: {솔루션명}
             - **출처**: {URL}
             - **핵심**: 솔루션 요약 (3줄 이내)
             - **적용성**: HIGH | MEDIUM | LOW
             - **트레이드오프**: 장단점
             #### Recommendation: Solution {A|B} 선택 이유")
SendMessage(type="message", recipient="solution-researcher", content="웹 리서치 시작.")
```

### Phase C: 최종 보고서 (Lead 직접)

```
# critic 결과 + 리서치 솔루션을 우선순위별 테이블로 정렬:
#
# | # | 약점 | 심각도 | 추천 솔루션 | 출처 |
# |---|------|--------|-----------|------|
# | W1 | {제목} | Critical | {솔루션 요약} | {URL} |
#
# Critical → Major 순 정렬. Minor는 별도 축약 목록.
```

**특수 처리:**
- QUESTION: Phase B 스킵 → 질문 목록을 사용자에게 전달 → 응답 후 Phase A 재실행
- SURVIVED: Phase B 스킵 → "의미 있는 약점이 발견되지 않았습니다" 보고

---

## `--debate` — 3-Agent 병렬 분석 합의 판정 (Agent Teams)

> **v3.0**: Python 스크립트 의존 제거. Agent Teams 패턴으로 3개 Claude 에이전트가 병렬 분석.

```
# Phase 1: 3-Agent 병렬 분석
TeamCreate(team_name="debate-{topic}")

Agent(subagent_type="architect", name="perspective-structure",
      description="구조적 관점 분석", team_name="debate-{topic}",
      prompt="[관점: 아키텍처/구조] {사용자 요청 내용}을 구조적 관점에서 분석.
              분석: 아키텍처 적합성, 확장성, 의존성 리스크, 유지보수 비용.
              출력: ## 구조적 분석 → 결론/근거/리스크/추천 형식.")

Agent(subagent_type="code-reviewer", name="perspective-quality",
      description="품질/보안 관점 분석", team_name="debate-{topic}",
      prompt="[관점: 품질/보안] {사용자 요청 내용}을 품질 관점에서 분석.
              분석: 코드 품질 영향, 보안 리스크, 에러 핸들링, 기술 부채.
              출력: ## 품질/보안 분석 → 결론/근거/리스크/추천 형식.")

Agent(subagent_type="researcher", name="perspective-external",
      description="외부 사례/패턴 분석", team_name="debate-{topic}",
      prompt="[관점: 외부 사례] {사용자 요청 내용}을 외부 관점에서 분석.
              분석: 베스트 프랙티스, 오픈소스 접근 방식, 대안 비교.
              출력: ## 외부 사례 분석 → 결론/근거/대안/추천 형식.")

# Phase 2: Lead 합의 판정 (3개 결과 수집 후)
# 공통 결론 추출 (agreed) + 불일치 항목 식별 (disputed)
# 합의율 = agreed / (agreed + disputed) × 100
# 80%+ → 최종 판정 / 미달 → 재토론 (SendMessage, max 2회)

# Phase 5: 최종 판정
# Write(".claude/debates/{topic}/FINAL.md", final_report)
TeamDelete()
```

> **전제조건 없음**: 외부 API 키/패키지 설치 불필요. Agent Teams만으로 동작.
> **상세 워크플로우**: `.claude/skills/ultimate-debate/SKILL.md` v3.0 참조.

---

## `--research` — 코드베이스/외부 리서치

```
Agent(subagent_type="researcher", name="researcher", description="리서치 실행", team_name="pdca-{feature}",
     prompt="[Research] {사용자 요청} 관련 리서치 수행.
             서브커맨드: code (코드 분석) | web (외부 검색) | plan (구현 계획) | review (코드 리뷰)
             결과 요약을 5줄 이내로 보고.")
SendMessage(type="message", recipient="researcher", content="리서치 시작.")
# 리서치 결과를 Phase 1 사전 분석에 반영
```

---

## `--gdocs` — Google Docs PRD 동기화

```
Agent(subagent_type="executor-high", name="prd-syncer", description="PRD 동기화", team_name="pdca-{feature}",
     prompt="[PRD Sync] .claude/commands/prd-sync.md 워크플로우 실행.
             Google Docs의 PRD를 docs/00-prd/ 로컬에 동기화.
             google-workspace 스킬의 OAuth 2.0 인증 사용.")
SendMessage(type="message", recipient="prd-syncer", content="PRD 동기화 시작.")
# 동기화된 PRD 파일을 Phase 1에 반영
```

---

## `--daily` — 일일 대시보드 (9-Phase Pipeline)

```
Agent(subagent_type="executor-high", name="daily-runner", description="일일 대시보드 생성", team_name="pdca-{feature}",
     prompt="[Daily] daily 스킬의 9-Phase Pipeline 전체 실행 (Phase 0-8 순차).
             Design Reference: docs/02-design/daily-redesign.design.md
             3소스: Gmail/Slack/GitHub 증분 수집 → AI 크로스소스 분석 → 액션 추천.
             결과: 대시보드 요약 + 액션 추천 목록 (최대 10건).")
SendMessage(type="message", recipient="daily-runner", content="Daily 파이프라인 시작.")
```

---

## `--jira <command> <target>` — Jira 조회/분석

서브커맨드: `epics <board_id>` | `project <key>` | `board <id>` | `search "<jql>"` | `issue <key>`

```python
jira_command = options.get("jira_command")
jira_target = options.get("jira_target")

Agent(subagent_type="executor", name="jira-runner", description="Jira 조회 실행", team_name="pdca-{feature}",
     prompt="[Jira] --jira {jira_command} {jira_target} 실행.
             실행: cd C:\\claude && python lib/jira/jira_client.py {jira_command} {jira_target}
             결과를 구조화된 분석으로 보고.
             epics 커맨드 시 Epic별 Story/Sub-task 구조 분석 포함.
             인증은 스크립트가 Windows User 환경변수에서 자동 로드.")
SendMessage(type="message", recipient="jira-runner", content="Jira 조회 시작.")
```

---

## `--figma <url> [connect|rules|capture|auth]` — Figma 디자인 연동

### Step 0: 인증 검증 (MANDATORY — 모든 모드 공통)

```python
# mcp__plugin_figma_figma__whoami() 호출
# 실패 시 "Figma MCP 서버 미연결" 에러 출력 후 즉시 중단
```

### Step 1: 모드 판별 + URL 파싱

```python
figma_args = options.get("figma_args", "")
figma_variant = "implement"  # 기본값

if figma_args == "auth":
    figma_variant = "auth"
elif figma_args == "rules":
    figma_variant = "rules"
elif figma_args.startswith("capture"):
    figma_variant = "capture"
elif figma_args.startswith("connect "):
    figma_variant = "connect"
    figma_url = figma_args.split("connect ", 1)[1].strip()
else:
    figma_variant = "implement"
    figma_url = figma_args.strip()

# URL 파싱: cd C:\claude && python lib/figma/url_parser.py '{figma_url}'
# 반환: {"file_key": str, "node_id": str|None, "url_type": "design"|"branch"|"board"|"make"}
# url_type == "board" → get_figjam 사용 (FigJam)
```

### implement 모드 (기본)

```
Agent(subagent_type="designer", name="figma-designer", description="Figma 디자인 구현", team_name="pdca-{feature}",
     prompt="[Figma] implement 모드 실행.
             URL: {figma_url} | file_key={file_key}, node_id={node_id}, url_type={url_type}

             절차:
             1. 인증 확인: mcp__plugin_figma_figma__whoami()
             2. url_type에 따라 MCP 도구 선택:
                - board → mcp__plugin_figma_figma__get_figjam(fileKey, nodeId)
                - 기타 → mcp__plugin_figma_figma__get_design_context(fileKey, nodeId)
             3. 필요 시: get_screenshot, get_variable_defs, get_metadata
             4. Code Connect 스니펫 → 기존 컴포넌트 직접 사용
             5. 프로젝트 기존 컴포넌트/패턴과 매칭하여 코드 생성")
SendMessage(type="message", recipient="figma-designer", content="Figma 디자인 구현 시작.")
```

### connect 모드

```
Agent(subagent_type="executor-high", name="figma-connector", description="Figma 컴포넌트 연결", team_name="pdca-{feature}",
     prompt="[Figma] connect 모드.
             1. 인증 확인 (seat=Full 필수)
             2. 기존 매핑 확인: get_code_connect_map(fileKey, nodeId)
             3. AI 매핑 제안: get_code_connect_suggestions(fileKey, nodeId)
             4. 사용자 검토 요청 (AskUserQuestion)
             5. 승인된 매핑 저장: send_code_connect_mappings(fileKey, nodeId, mappings)")
```

### rules 모드

```
Agent(subagent_type="executor", name="figma-rules", description="디자인 시스템 규칙 생성", team_name="pdca-{feature}",
     prompt="[Figma] rules 모드.
             1. 인증 확인
             2. 프로젝트 프레임워크 감지 (package.json, tsconfig)
             3. create_design_system_rules(clientFrameworks, clientLanguages) 호출
             4. 반환된 규칙을 .claude/rules/ 에 저장")
```

### capture 모드 (Lead 직접 실행 — interactive)

```python
# Step 1: outputMode 결정 → AskUserQuestion
#   선택지: newFile (planKey 필요), existingFile (fileKey 필요), clipboard
# Step 2: captureId 발급
#   generate_figma_design(outputMode="newFile", fileName="...", planKey="...")
# Step 3: 캡처 대상 준비
#   a. <script src="https://mcp.figma.com/.../capture.js" async></script> 주입
#   b. body: margin:0, padding:0, background:transparent, display:inline-block
#   c. HTTP 서버: python -m http.server {port}
#   d. Headless 캡처: capture_url('http://localhost:{port}/{page}#figmacapture={captureId}&...')
# Step 4: 폴링 (5초 간격, max 10회)
#   status == "completed" → Figma 파일 URL 반환
#   10회 초과 → "캡처 실패" 에러
```

---

## `--slack` 옵션 워크플로우

**Step 1: 인증 확인**
```bash
cd C:\claude && python -m lib.slack status --json
# "authenticated": false → 에러 출력 후 중단
```

**Step 2: 채널 히스토리 수집**
```bash
python -m lib.slack history "<채널ID>" --limit 100 --json
```

**Step 3: 메시지 분석 (Analyst Teammate)**
```
Agent(subagent_type="analyst", name="slack-analyst", description="Slack 분석", team_name="pdca-{feature}",
     prompt="SLACK CHANNEL ANALYSIS
     채널: <채널ID>
     분석 항목: 주요 토픽, 핵심 결정사항, 공유 문서 링크, 참여자 역할, 미해결 이슈, 기술 스택
     출력: 구조화된 컨텍스트 문서")
SendMessage(type="message", recipient="slack-analyst", content="Slack 채널 분석 요청.")
```

**Step 4: 컨텍스트 파일 생성**
`.claude/context/slack/<채널ID>.md` 생성

**Step 5: 메인 워크플로우 실행**
- 생성된 컨텍스트 파일을 Read하여 Phase 1 (PLAN)에 전달

---

## `--gmail` 옵션 워크플로우

```bash
/auto --gmail                           # 안 읽은 메일 분석
/auto --gmail "검색어"                   # Gmail 검색 쿼리로 필터링
/auto --gmail "작업 설명"                # 메일 기반 작업 실행
/auto --gmail "from:client" "응답 초안"  # 검색 + 작업 조합
```

**Step 1: 인증 확인 (MANDATORY)**
```bash
cd C:\claude && python -m lib.gmail status --json
# "authenticated": false → "Gmail 인증 실패. python -m lib.gmail login 실행 필요." 에러 후 중단
```

**Step 2: 메일 수집**

| 입력 패턴 | 실행 명령 |
|----------|----------|
| `--gmail` (검색어 없음) | `python -m lib.gmail unread --limit 20 --json` |
| `--gmail "from:..."` | `python -m lib.gmail search "from:..." --limit 20 --json` |
| `--gmail "newer_than:7d"` | `python -m lib.gmail search "newer_than:7d" --limit 20 --json` |

**Step 3: 메일 분석 (Analyst Teammate)**
```
Agent(subagent_type="analyst", name="gmail-analyst", description="Gmail 분석", team_name="pdca-{feature}",
     prompt="GMAIL ANALYSIS
     분석 항목: 요청사항/할일 추출, 발신자 우선순위, 회신 필요 메일, 첨부파일, 키워드 연관성, 리스크
     출력: 구조화된 이메일 분석 문서 (마크다운)")
SendMessage(type="message", recipient="gmail-analyst", content="Gmail 분석 요청.")
```

**Step 4: 컨텍스트 파일 생성**
`.claude/context/gmail/<timestamp>.md` 생성

**Step 5: 후속 작업 분기**

| 사용자 요청 | 실행 |
|------------|------|
| 검색만 | 분석 결과 출력 후 종료 |
| "응답 초안" | 각 메일에 대한 회신 초안 생성 |
| "할일 생성" | TaskCreate로 TODO 항목 생성 |
| 구체적 작업 | 메인 워크플로우 실행 (메일 컨텍스트 포함) |

---

## `--interactive` 옵션 워크플로우

각 PDCA Phase 전환 시 사용자에게 확인을 요청합니다.

| Phase 전환 | 선택지 | 기본값 |
|-----------|--------|:------:|
| Phase 1 → Phase 2 BUILD | 진행 / 수정 / 건너뛰기 | 진행 |
| Phase 2 → Phase 3 VERIFY | 진행 / 수정 | 진행 |
| Phase 3 → Phase 4 CLOSE | 자동 개선 / 수동 수정 / 완료 | 자동 개선 |

**Phase 전환 시 출력 형식:**
```
===================================================
 Phase {N} {이름} 완료 -> Phase {N+1} {이름} 진입 대기
===================================================
 산출물: {파일 경로}
 소요 teammates: {agent (model)}
 핵심 결정: [1줄 요약]
===================================================
```

**--interactive 미사용 시**: 모든 Phase를 자동으로 진행합니다.

---

## `--con` 옵션 워크플로우

### Step 0: 인증 사전 체크 (NEW — 반복 프롬프트 분석 2026-03-25)

`--con` 실행 전 Confluence 인증 상태를 자동 확인합니다. "인증처리되어 있다고" 반복 3회 해소.

```python
# --con 감지 시 즉시 실행 (발행 로직 전)
import subprocess
auth_result = subprocess.run(
    ["python", "C:/claude/lib/gws/gws_auth.py", "status"],
    capture_output=True, text=True, timeout=10
)
if "expired" in auth_result.stdout.lower() or auth_result.returncode != 0:
    # 자동 갱신 시도
    refresh = subprocess.run(
        ["python", "C:/claude/lib/gws/gws_auth.py", "refresh"],
        capture_output=True, text=True, timeout=15
    )
    if refresh.returncode != 0:
        # 갱신 실패 → 사용자 안내 후 중단
        AskUserQuestion("Confluence 인증이 만료되었습니다. `/auth google` 로 재인증 후 다시 시도하세요.")
        return  # --con 처리 중단
# 인증 유효 → 아래 발행 로직 진행
```

Markdown 파일을 Confluence Storage Format으로 변환하여 지정 페이지에 발행합니다.

```bash
/auto "기능 구현" --con <page_id>           # PRD/Plan 문서 자동 발행
/auto "기능 구현" --con <page_id> <file.md>  # 지정 파일 발행
```

**변환 파이프라인:**
```
MD 파일 읽기 → Mermaid 블록 추출 → mmdc PNG 렌더링
→ pandoc MD→HTML 변환 → HTML 후처리 (ac:image, table auto-width, p-wrap)
→ 첨부파일 업로드 → 페이지 본문 업데이트 (version +1)
```

**HTML 후처리 규칙:**

| 변환 | 설명 |
|------|------|
| `<img>` → `<ac:image>` | `<ri:attachment ri:filename="..."/>` 매크로 |
| 이미지 720px 제한 | 원본 너비 > 720px 시 `ac:width="720"` 추가 |
| `<table>` | `data-layout="default"` auto-width |
| `<th>/<td>` 내용 | `<p>` 태그 래핑 (Confluence 필수) |

**실행 스크립트:**
```bash
python lib/confluence/md2confluence.py <file.md> <page_id>
python lib/confluence/md2confluence.py <file.md> <page_id> --dry-run
```

**통합 처리 흐름:**
```python
page_id = options.get("con")
target = explicit_file if explicit_file else f"docs/00-prd/{feature}.prd.md"
# python lib/confluence/md2confluence.py <target> <page_id>
```

**에러 처리:**

| 에러 | 처리 |
|------|------|
| 인증 실패 (401) | 환경변수 확인 안내 + 중단 |
| 페이지 미존재 (404) | page_id 확인 안내 + 중단 |
| mmdc 미설치 | Mermaid 블록을 코드 블록으로 유지 + 경고 |
| pandoc 실패 | 에러 메시지 출력 + 중단 |

> **인증**: 스크립트가 Windows User 환경변수에서 자동 로드 (winreg fallback).

---

## Phase 0 스킵 플래그

```python
# --skip-prd: Phase 1 Step 1.1 PRD 스킵
if "--skip-prd" in options:
    # Step 1.1 건너뛰기 → Step 1.2 사전 분석부터 시작
    # 이유 기록 필수 (규칙 13-requirements-prd 준수)

# --skip-analysis: Phase 1 Step 1.2 사전 분석 스킵
if "--skip-analysis" in options:
    # Step 1.2 건너뛰기 → Step 1.3 계획 수립부터 시작

# --no-issue: Phase 1 Step 1.5 이슈 연동 스킵
if "--no-issue" in options:
    # Step 1.5 건너뛰기 (GitHub 이슈 생성/코멘트 안 함)
```
