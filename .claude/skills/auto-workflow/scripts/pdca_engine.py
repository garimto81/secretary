"""
pdca_engine.py - BKIT PDCA 워크플로우 자동화 엔진

/auto 실행 시 PDCA 문서화를 필수 작업으로 처리
Plan → Design → Do → Check → Act 자동 진행
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path
import json
from datetime import datetime


class PDCAPhase(Enum):
    """PDCA 사이클 단계"""
    PLAN = "plan"       # 계획 문서 생성
    DESIGN = "design"   # 설계 문서 생성
    DO = "do"           # 구현 실행
    CHECK = "check"     # gap-detector 검증
    ACT = "act"         # 개선 반복


class PDCAStatus(Enum):
    """PDCA 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ITERATING = "iterating"  # Check 실패 후 Act 반복 중


@dataclass
class PDCAConfig:
    """PDCA 설정"""
    # 임계값 설정
    gap_threshold_pass: int = 90      # 이상이면 통과
    gap_threshold_warn: int = 70      # 이상이면 경고
    max_iterations: int = 5           # 최대 반복 횟수

    # 문서 경로 설정
    plan_dir: str = "docs/01-plan"
    design_dir: str = "docs/02-design"
    analysis_dir: str = "docs/03-analysis"
    report_dir: str = "docs/04-report"

    # 필수 여부
    mandatory: bool = True            # PDCA 문서화 필수 여부


@dataclass
class PDCADocument:
    """PDCA 문서"""
    phase: PDCAPhase
    feature: str
    path: str
    content: str
    created_at: str = ""
    updated_at: str = ""


@dataclass
class GapAnalysisResult:
    """갭 분석 결과"""
    match_percentage: float
    verdict: str  # PASS, WARN, FAIL
    gaps: List[str] = field(default_factory=list)      # 설계에 있으나 구현에 없음
    extras: List[str] = field(default_factory=list)    # 구현에 있으나 설계에 없음
    recommendations: List[str] = field(default_factory=list)


@dataclass
class PDCAState:
    """PDCA 상태"""
    feature: str
    current_phase: PDCAPhase
    status: PDCAStatus
    iteration: int = 1
    documents: Dict[str, PDCADocument] = field(default_factory=dict)
    gap_results: List[GapAnalysisResult] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""


# =============================================================================
# PDCA 문서 템플릿 (BKIT 원본 기반)
# =============================================================================

PLAN_TEMPLATE = """# {feature} - Plan Document

**Feature**: {feature}
**Created**: {date}
**Status**: Draft

---

## 1. Overview

### 1.1 Background
<!-- 기능이 필요한 배경 설명 -->

### 1.2 Objectives
<!-- 달성하고자 하는 목표 -->

### 1.3 Success Criteria
<!-- 성공 기준 정의 -->

---

## 2. Requirements

### 2.1 Functional Requirements
| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-01 | | P0 | |
| FR-02 | | P1 | |

### 2.2 Non-Functional Requirements
| ID | Requirement | Metric | Target |
|----|-------------|--------|--------|
| NFR-01 | | | |

---

## 3. Scope

### 3.1 In Scope
-

### 3.2 Out of Scope
-

---

## 4. Constraints

### 4.1 Technical Constraints
-

### 4.2 Business Constraints
-

---

## 5. Assumptions

-

---

## 6. Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| | Low/Medium/High | Low/Medium/High | |

---

## 7. Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Plan | | This document |
| Design | | Design document |
| Do | | Implementation |
| Check | | Gap analysis |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | {date} | Auto-generated | Initial draft |
"""

DESIGN_TEMPLATE = """# {feature} - Design Document

**Feature**: {feature}
**Created**: {date}
**Status**: Draft
**Plan Reference**: {plan_path}

---

## 1. Architecture Overview

### 1.1 System Context
<!-- 시스템 전체 구조에서의 위치 -->

### 1.2 Component Diagram
```
┌─────────────────────────────────────────────┐
│                                             │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 2. Data Model

### 2.1 Entities
| Entity | Description | Attributes |
|--------|-------------|------------|
| | | |

### 2.2 Relationships
```
Entity1 ──1:N──> Entity2
```

---

## 3. API Design

### 3.1 Endpoints
| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| GET | | | | |
| POST | | | | |

### 3.2 Response Format
```json
{{
  "data": {{}},
  "meta": {{}}
}}
```

### 3.3 Error Codes
| Code | Description |
|------|-------------|
| VALIDATION_ERROR | |
| NOT_FOUND | |

---

## 4. UI Design

### 4.1 Screen List
| Screen | Description | Components |
|--------|-------------|------------|
| | | |

### 4.2 User Flow
```
Screen A → Screen B → Screen C
```

---

## 5. Implementation Details

### 5.1 File Structure
```
src/
├── components/
├── services/
└── utils/
```

### 5.2 Key Functions
| Function | File | Description |
|----------|------|-------------|
| | | |

---

## 6. Testing Strategy

### 6.1 Unit Tests
-

### 6.2 Integration Tests
-

### 6.3 E2E Tests
-

---

## 7. Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| | | |

---

## 8. Security Considerations

-

---

## 9. Performance Considerations

-

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | {date} | Auto-generated | Initial draft |
"""

ANALYSIS_TEMPLATE = """# {feature} - Gap Analysis Report

**Feature**: {feature}
**Analyzed**: {date}
**Iteration**: {iteration}

---

## Analysis Overview

- **Design Document**: {design_path}
- **Implementation Path**: {implementation_path}
- **Analysis Date**: {date}

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | {match_percentage}% | {status_emoji} |
| Threshold | {threshold}% | - |

---

## Differences Found

### 🔴 Missing Features (Design ✓, Implementation ✗)
{missing_list}

### 🟡 Extra Features (Design ✗, Implementation ✓)
{extra_list}

---

## Recommendations

{recommendations}

---

## Next Steps

{next_steps}

---

## Version History

| Version | Date | Match % | Notes |
|---------|------|---------|-------|
| {iteration} | {date} | {match_percentage}% | {notes} |
"""

REPORT_TEMPLATE = """# {feature} - Completion Report

**Feature**: {feature}
**Completed**: {date}
**Total Iterations**: {total_iterations}

---

## Summary

PDCA 사이클이 성공적으로 완료되었습니다.

---

## PDCA Cycle Overview

| Phase | Status | Document |
|-------|:------:|----------|
| Plan | ✅ | {plan_path} |
| Design | ✅ | {design_path} |
| Do | ✅ | Implementation completed |
| Check | ✅ | {analysis_path} |
| Act | ✅ | {iteration_count} iteration(s) |

---

## Final Gap Analysis

- **Match Percentage**: {final_match}%
- **Threshold**: {threshold}%
- **Verdict**: ✅ PASS

---

## Documents Created

| Document | Path | Created |
|----------|------|---------|
| Plan | {plan_path} | {plan_date} |
| Design | {design_path} | {design_date} |
| Analysis | {analysis_path} | {analysis_date} |

---

## Recommendations for Future

{future_recommendations}

---

Generated by /auto PDCA Engine
"""


class PDCAEngine:
    """PDCA 자동화 엔진"""

    def __init__(self, config: Optional[PDCAConfig] = None):
        self.config = config or PDCAConfig()
        self.state: Optional[PDCAState] = None

    # -------------------------------------------------------------------------
    # 디렉토리 생성
    # -------------------------------------------------------------------------

    def ensure_directories(self, base_path: str = ".") -> Dict[str, Path]:
        """PDCA 문서 디렉토리 생성"""
        dirs = {
            "plan": Path(base_path) / self.config.plan_dir,
            "design": Path(base_path) / self.config.design_dir,
            "analysis": Path(base_path) / self.config.analysis_dir,
            "report": Path(base_path) / self.config.report_dir,
        }

        for name, path in dirs.items():
            path.mkdir(parents=True, exist_ok=True)

        return dirs

    # -------------------------------------------------------------------------
    # PDCA 사이클 시작
    # -------------------------------------------------------------------------

    def start_cycle(self, feature: str) -> PDCAState:
        """새 PDCA 사이클 시작"""
        self.state = PDCAState(
            feature=feature,
            current_phase=PDCAPhase.PLAN,
            status=PDCAStatus.IN_PROGRESS,
            iteration=1,
            started_at=datetime.now().isoformat()
        )
        return self.state

    # -------------------------------------------------------------------------
    # Phase 1: Plan
    # -------------------------------------------------------------------------

    def generate_plan_document(self, feature: str, base_path: str = ".") -> str:
        """Plan 문서 생성"""
        dirs = self.ensure_directories(base_path)
        date = datetime.now().strftime("%Y-%m-%d")

        content = PLAN_TEMPLATE.format(
            feature=feature,
            date=date
        )

        # 파일명 생성 (kebab-case)
        filename = f"{self._to_kebab_case(feature)}.plan.md"
        path = dirs["plan"] / filename

        # 파일 저장
        path.write_text(content, encoding="utf-8")

        # 상태 업데이트
        if self.state:
            self.state.documents["plan"] = PDCADocument(
                phase=PDCAPhase.PLAN,
                feature=feature,
                path=str(path),
                content=content,
                created_at=date
            )

        return str(path)

    # -------------------------------------------------------------------------
    # Phase 2: Design
    # -------------------------------------------------------------------------

    def generate_design_document(
        self,
        feature: str,
        plan_path: str,
        base_path: str = "."
    ) -> str:
        """Design 문서 생성"""
        dirs = self.ensure_directories(base_path)
        date = datetime.now().strftime("%Y-%m-%d")

        content = DESIGN_TEMPLATE.format(
            feature=feature,
            date=date,
            plan_path=plan_path
        )

        filename = f"{self._to_kebab_case(feature)}.design.md"
        path = dirs["design"] / filename

        path.write_text(content, encoding="utf-8")

        if self.state:
            self.state.documents["design"] = PDCADocument(
                phase=PDCAPhase.DESIGN,
                feature=feature,
                path=str(path),
                content=content,
                created_at=date
            )
            self.state.current_phase = PDCAPhase.DESIGN

        return str(path)

    # -------------------------------------------------------------------------
    # Phase 3: Do (구현 - 외부에서 처리)
    # -------------------------------------------------------------------------

    def mark_do_started(self) -> None:
        """Do 단계 시작 표시"""
        if self.state:
            self.state.current_phase = PDCAPhase.DO

    def mark_do_completed(self) -> None:
        """Do 단계 완료 표시"""
        if self.state:
            self.state.current_phase = PDCAPhase.CHECK

    # -------------------------------------------------------------------------
    # Phase 4: Check (gap-detector)
    # -------------------------------------------------------------------------

    def generate_analysis_document(
        self,
        feature: str,
        design_path: str,
        implementation_path: str,
        gap_result: GapAnalysisResult,
        base_path: str = "."
    ) -> str:
        """Gap Analysis 문서 생성"""
        dirs = self.ensure_directories(base_path)
        date = datetime.now().strftime("%Y-%m-%d")
        iteration = self.state.iteration if self.state else 1

        # 상태 이모지
        if gap_result.verdict == "PASS":
            status_emoji = "✅"
        elif gap_result.verdict == "WARN":
            status_emoji = "⚠️"
        else:
            status_emoji = "❌"

        # 누락 항목 목록
        if gap_result.gaps:
            missing_list = "\n".join(f"- {g}" for g in gap_result.gaps)
        else:
            missing_list = "- 없음"

        # 추가 항목 목록
        if gap_result.extras:
            extra_list = "\n".join(f"- {e}" for e in gap_result.extras)
        else:
            extra_list = "- 없음"

        # 권장사항
        if gap_result.recommendations:
            recommendations = "\n".join(f"- {r}" for r in gap_result.recommendations)
        else:
            recommendations = "- 추가 조치 불필요"

        # 다음 단계
        if gap_result.verdict == "PASS":
            next_steps = "- ✅ PDCA 사이클 완료\n- 완료 보고서 생성"
        else:
            next_steps = "- 🔄 Act 단계로 진입하여 개선 수행\n- gap-detector 재검증 예정"

        content = ANALYSIS_TEMPLATE.format(
            feature=feature,
            date=date,
            iteration=iteration,
            design_path=design_path,
            implementation_path=implementation_path,
            match_percentage=gap_result.match_percentage,
            threshold=self.config.gap_threshold_pass,
            status_emoji=status_emoji,
            missing_list=missing_list,
            extra_list=extra_list,
            recommendations=recommendations,
            next_steps=next_steps,
            notes=gap_result.verdict
        )

        filename = f"{self._to_kebab_case(feature)}.analysis.md"
        path = dirs["analysis"] / filename

        path.write_text(content, encoding="utf-8")

        if self.state:
            self.state.documents["analysis"] = PDCADocument(
                phase=PDCAPhase.CHECK,
                feature=feature,
                path=str(path),
                content=content,
                created_at=date
            )
            self.state.gap_results.append(gap_result)
            self.state.current_phase = PDCAPhase.CHECK

        return str(path)

    def check_gap_result(self, gap_result: GapAnalysisResult | int | float) -> bool:
        """Gap 결과가 통과 기준 충족하는지 확인

        Args:
            gap_result: GapAnalysisResult 객체 또는 퍼센트 값 (int/float)
        """
        if isinstance(gap_result, (int, float)):
            return gap_result >= self.config.gap_threshold_pass
        return gap_result.match_percentage >= self.config.gap_threshold_pass

    # -------------------------------------------------------------------------
    # Phase 5: Act (개선 반복)
    # -------------------------------------------------------------------------

    def start_iteration(self) -> int:
        """새 개선 반복 시작"""
        if self.state:
            self.state.iteration += 1
            self.state.status = PDCAStatus.ITERATING
            self.state.current_phase = PDCAPhase.ACT
            return self.state.iteration
        return 1

    def can_iterate(self) -> bool:
        """추가 반복 가능 여부"""
        if self.state:
            return self.state.iteration < self.config.max_iterations
        return True

    # -------------------------------------------------------------------------
    # 완료 보고서
    # -------------------------------------------------------------------------

    def generate_report(
        self,
        feature: str,
        base_path: str = "."
    ) -> str:
        """완료 보고서 생성"""
        dirs = self.ensure_directories(base_path)
        date = datetime.now().strftime("%Y-%m-%d")

        plan_doc = self.state.documents.get("plan") if self.state else None
        design_doc = self.state.documents.get("design") if self.state else None
        analysis_doc = self.state.documents.get("analysis") if self.state else None

        final_gap = self.state.gap_results[-1] if self.state and self.state.gap_results else None

        content = REPORT_TEMPLATE.format(
            feature=feature,
            date=date,
            total_iterations=self.state.iteration if self.state else 1,
            plan_path=plan_doc.path if plan_doc else "N/A",
            design_path=design_doc.path if design_doc else "N/A",
            analysis_path=analysis_doc.path if analysis_doc else "N/A",
            iteration_count=self.state.iteration if self.state else 1,
            final_match=final_gap.match_percentage if final_gap else 0,
            threshold=self.config.gap_threshold_pass,
            plan_date=plan_doc.created_at if plan_doc else "N/A",
            design_date=design_doc.created_at if design_doc else "N/A",
            analysis_date=analysis_doc.created_at if analysis_doc else "N/A",
            future_recommendations="- 정기적인 설계-구현 동기화 검토 권장\n- 새 기능 추가 시 PDCA 사이클 적용"
        )

        filename = f"{self._to_kebab_case(feature)}.report.md"
        path = dirs["report"] / filename

        path.write_text(content, encoding="utf-8")

        if self.state:
            self.state.status = PDCAStatus.COMPLETED
            self.state.completed_at = datetime.now().isoformat()

        return str(path)

    # -------------------------------------------------------------------------
    # 상태 저장/복원
    # -------------------------------------------------------------------------

    def save_state(self, path: str = ".omc/pdca-state.json") -> None:
        """PDCA 상태 저장"""
        if not self.state:
            return

        state_path = Path(path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        state_dict = {
            "feature": self.state.feature,
            "current_phase": self.state.current_phase.value,
            "status": self.state.status.value,
            "iteration": self.state.iteration,
            "started_at": self.state.started_at,
            "completed_at": self.state.completed_at,
            "documents": {
                k: {"phase": v.phase.value, "path": v.path, "created_at": v.created_at}
                for k, v in self.state.documents.items()
            },
            "gap_results": [
                {
                    "match_percentage": r.match_percentage,
                    "verdict": r.verdict,
                    "gaps": r.gaps,
                    "extras": r.extras
                }
                for r in self.state.gap_results
            ]
        }

        state_path.write_text(json.dumps(state_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_state(self, path: str = ".omc/pdca-state.json") -> Optional[PDCAState]:
        """PDCA 상태 복원"""
        state_path = Path(path)
        if not state_path.exists():
            return None

        state_dict = json.loads(state_path.read_text(encoding="utf-8"))

        self.state = PDCAState(
            feature=state_dict["feature"],
            current_phase=PDCAPhase(state_dict["current_phase"]),
            status=PDCAStatus(state_dict["status"]),
            iteration=state_dict["iteration"],
            started_at=state_dict.get("started_at", ""),
            completed_at=state_dict.get("completed_at", "")
        )

        # 문서 복원
        for k, v in state_dict.get("documents", {}).items():
            self.state.documents[k] = PDCADocument(
                phase=PDCAPhase(v["phase"]),
                feature=self.state.feature,
                path=v["path"],
                content="",  # 내용은 파일에서 읽어야 함
                created_at=v.get("created_at", "")
            )

        # 갭 결과 복원
        for r in state_dict.get("gap_results", []):
            self.state.gap_results.append(GapAnalysisResult(
                match_percentage=r["match_percentage"],
                verdict=r["verdict"],
                gaps=r.get("gaps", []),
                extras=r.get("extras", [])
            ))

        return self.state

    # -------------------------------------------------------------------------
    # Task 호출 코드 생성 (Claude Code 연동)
    # -------------------------------------------------------------------------

    def build_full_pdca_workflow(self, feature: str, base_path: str = ".") -> str:
        """전체 PDCA 워크플로우 호출 코드 생성"""
        return f'''# ============================================================
# PDCA 자동화 워크플로우: {feature}
# ============================================================

# Phase 1: Plan 문서 생성
# → docs/01-plan/{self._to_kebab_case(feature)}.plan.md

Task(
    subagent_type="oh-my-claudecode:planner",
    model="opus",
    description="[PDCA Plan] {feature} 계획 문서",
    prompt="""다음 기능에 대한 Plan 문서를 작성하세요:

기능: {feature}

## 작성 항목
1. Overview (배경, 목표, 성공 기준)
2. Requirements (기능/비기능 요구사항)
3. Scope (범위 내/외)
4. Constraints (기술/비즈니스 제약)
5. Assumptions (가정)
6. Risks (위험 및 완화)
7. Timeline (일정)

## 출력
마크다운 형식의 Plan 문서"""
)

# Phase 2: Design 문서 생성
# → docs/02-design/{self._to_kebab_case(feature)}.design.md

Task(
    subagent_type="oh-my-claudecode:architect",
    model="opus",
    description="[PDCA Design] {feature} 설계 문서",
    prompt="""다음 기능에 대한 Design 문서를 작성하세요:

기능: {feature}
Plan 문서: docs/01-plan/{self._to_kebab_case(feature)}.plan.md

## 작성 항목
1. Architecture Overview (시스템 구조)
2. Data Model (엔티티, 관계)
3. API Design (엔드포인트, 요청/응답)
4. UI Design (화면, 흐름)
5. Implementation Details (파일 구조, 주요 함수)
6. Testing Strategy (단위/통합/E2E)
7. Security/Performance 고려사항

## 출력
마크다운 형식의 Design 문서"""
)

# Phase 3: Do (구현)
# → 기존 /auto 워크플로우 실행

Task(
    subagent_type="oh-my-claudecode:executor",
    model="sonnet",
    description="[PDCA Do] {feature} 구현",
    prompt="""Design 문서를 기반으로 기능을 구현하세요:

Design 문서: docs/02-design/{self._to_kebab_case(feature)}.design.md

## 구현 규칙
1. Design 문서의 API/데이터 모델 정확히 따름
2. 모든 엔드포인트 구현
3. 에러 처리 포함
4. 테스트 코드 작성

## 완료 조건
- 빌드 성공
- 테스트 통과"""
)

# Phase 4: Check (gap-detector)
# → docs/03-analysis/{self._to_kebab_case(feature)}.analysis.md

Task(
    subagent_type="bkit:gap-detector",
    model="opus",
    description="[PDCA Check] {feature} 갭 분석",
    prompt="""설계와 구현의 일치도를 검증하세요:

Design 문서: docs/02-design/{self._to_kebab_case(feature)}.design.md
구현 경로: src/

## 검증 항목
1. 설계에 명시된 기능 구현 여부
2. API 엔드포인트 일치
3. 데이터 모델 일치
4. 에러 처리 일치

## 임계값
통과 기준: {self.config.gap_threshold_pass}%

## 출력
- match_percentage: 0-100
- verdict: PASS/WARN/FAIL
- gaps: [누락 항목]
- extras: [추가 항목]
- recommendations: [권장사항]"""
)

# Phase 5: Act (조건부 - Check 실패 시)
# → pdca-iterator로 자동 개선

# gap < {self.config.gap_threshold_pass}% 인 경우:
Task(
    subagent_type="bkit:pdca-iterator",
    model="sonnet",
    description="[PDCA Act] {feature} 개선",
    prompt="""Gap 분석 결과를 기반으로 구현을 개선하세요:

Analysis: docs/03-analysis/{self._to_kebab_case(feature)}.analysis.md

## 개선 규칙
1. gaps 목록의 누락 기능 구현
2. 불필요한 extras 제거 또는 설계 문서 업데이트
3. recommendations 반영

## 완료 조건
- match_percentage >= {self.config.gap_threshold_pass}%
- 최대 {self.config.max_iterations}회 반복"""
)

# 완료 보고서 생성 (Check 통과 시)
# → docs/04-report/{self._to_kebab_case(feature)}.report.md
'''

    def build_check_only_workflow(self, feature: str, design_path: str, impl_path: str) -> str:
        """Check 단계만 실행하는 워크플로우"""
        return f'''# ============================================================
# PDCA Check Only: {feature}
# ============================================================

# OMC Architect + BKIT gap-detector 병렬 검증

Task(
    subagent_type="oh-my-claudecode:architect",
    model="opus",
    description="[OMC] Architect 검증",
    prompt="""설계 문서: {design_path}
구현 경로: {impl_path}

검증 항목:
1. 요청 충족 여부
2. 버그 여부
3. 엣지 케이스
4. 코드 품질

APPROVED 또는 REJECTED 응답"""
)

Task(
    subagent_type="bkit:gap-detector",
    model="opus",
    description="[BKIT] 갭 분석",
    prompt="""설계 문서: {design_path}
구현 경로: {impl_path}

임계값: {self.config.gap_threshold_pass}%

출력:
- match_percentage
- verdict
- gaps/extras
- recommendations"""
)
'''

    # -------------------------------------------------------------------------
    # 유틸리티
    # -------------------------------------------------------------------------

    def _to_kebab_case(self, text: str) -> str:
        """텍스트를 kebab-case로 변환"""
        # 공백, 언더스코어를 하이픈으로
        result = text.lower().replace(" ", "-").replace("_", "-")
        # 연속 하이픈 제거
        while "--" in result:
            result = result.replace("--", "-")
        # 한글/특수문자 제거 (영문만 유지)
        result = "".join(c for c in result if c.isalnum() or c == "-")
        return result.strip("-")


# =============================================================================
# 편의 함수
# =============================================================================

def get_pdca_engine(config: Optional[PDCAConfig] = None) -> PDCAEngine:
    """PDCAEngine 인스턴스 반환"""
    return PDCAEngine(config)


def create_pdca_config(
    gap_threshold: int = 90,
    max_iterations: int = 5,
    mandatory: bool = True
) -> PDCAConfig:
    """PDCA 설정 생성"""
    return PDCAConfig(
        gap_threshold_pass=gap_threshold,
        max_iterations=max_iterations,
        mandatory=mandatory
    )


# =============================================================================
# 테스트/실행
# =============================================================================

if __name__ == "__main__":
    engine = get_pdca_engine()

    # PDCA 사이클 시작
    state = engine.start_cycle("로그인 기능")
    print(f"PDCA 사이클 시작: {state.feature}")
    print(f"현재 단계: {state.current_phase.value}")

    # 디렉토리 생성
    dirs = engine.ensure_directories()
    print(f"\n생성된 디렉토리:")
    for name, path in dirs.items():
        print(f"  - {name}: {path}")

    # 전체 워크플로우 출력
    print("\n=== 전체 PDCA 워크플로우 ===")
    print(engine.build_full_pdca_workflow("로그인 기능"))
