#!/usr/bin/env python3
"""
Unified State Manager - v14.0 통합 상태 관리

Context Manager, Phase Gate, Circuit Breaker를 단일 진입점으로 통합.
.omc/state/unified-session.json에 모든 상태를 저장.

v14.0 변경사항:
- Circuit Breaker 단일 소스화 (context_graph.json 참조)
- PDCA 단계 추적 추가
- 스키마 버전 필드 추가
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List
from enum import Enum


class PDCAPhase(Enum):
    """PDCA 사이클 단계"""
    PLAN = "plan"
    DESIGN = "design"
    DO = "do"
    CHECK = "check"
    ACT = "act"
    COMPLETE = "complete"


SCHEMA_VERSION = "2.0.0"

# 동적 프로젝트 루트 감지
def _get_project_root() -> Path:
    """프로젝트 루트 디렉토리를 동적으로 감지"""
    import os
    if env_root := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent.parent
    if (project_root / ".claude").exists():
        return project_root
    return Path.cwd()

PROJECT_ROOT = _get_project_root()
STATE_DIR = PROJECT_ROOT / ".omc" / "state"
UNIFIED_STATE_FILE = STATE_DIR / "unified-session.json"

# 레거시 상태 파일 경로
LEGACY_PATHS = {
    "context": PROJECT_ROOT / ".omc" / "context" / "context_graph.json",
    "phase": PROJECT_ROOT / ".omc" / "state" / "phase",  # 디렉토리
    "circuit_breaker": PROJECT_ROOT / ".omc" / "state" / "circuit-breaker.json",
}


class UnifiedStateManager:
    """통합 상태 관리자"""

    def __init__(self, session_id: Optional[str] = None):
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        self.session_id = session_id or f"unified_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 기본 상태 구조 (v2.0.0)
        self.state = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "components": {
                "context_manager": {"active": False, "file": str(LEGACY_PATHS["context"])},
                "phase_gate": {"active": False, "current_phase": None},
                # Circuit Breaker: context_graph.json을 단일 소스로 참조
                "circuit_breaker": {
                    "active": False,
                    "source": str(LEGACY_PATHS["context"]),  # 실제 데이터는 context_graph.json
                    "failures_ref": "circuit_breaker.failure_counts"  # 참조 경로
                },
                "verification": {"checks": []},  # v2.0: array 형식으로 통일
            },
            "workflow": {
                "mode": None,  # "auto", "ultrawork", "ralph", "ecomode"
                "iteration": 0,
                "max_iterations": 10,
                "status": "idle",  # "idle", "running", "paused", "completed", "failed"
            },
            # v2.0: PDCA 사이클 추적 추가
            "pdca": {
                "phase": None,  # "plan", "design", "do", "check", "act", "complete"
                "feature": None,  # 작업 중인 기능명
                "iteration": 0,
                "gap_percentage": None,  # 마지막 gap-detector 결과
                "documents": {
                    "plan": None,  # docs/01-plan/*.plan.md 경로
                    "design": None,  # docs/02-design/*.design.md 경로
                    "analysis": None,  # docs/03-analysis/*.analysis.md 경로
                    "report": None,  # docs/04-report/*.report.md 경로
                },
            },
            "metadata": {},
        }

        # 기존 세션이 있으면 로드, 없으면 기본 상태 사용
        self._load()

    def _load(self):
        """상태 파일 로드"""
        if UNIFIED_STATE_FILE.exists():
            try:
                with open(UNIFIED_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("session_id") == self.session_id:
                        # 기존 세션 복원: 전체 상태 덮어쓰기
                        self.state = data
            except (json.JSONDecodeError, OSError):
                pass
        # 새 세션이거나 로드 실패: 기본 상태를 파일로 저장
        else:
            self._save()

    def _save(self):
        """상태 파일 저장"""
        self.state["updated_at"] = datetime.now().isoformat()
        try:
            with open(UNIFIED_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"Warning: Failed to save unified state: {e}")

    # === 워크플로우 관리 ===

    def start_workflow(self, mode: str, max_iterations: int = 10):
        """워크플로우 시작"""
        self.state["workflow"] = {
            "mode": mode,
            "iteration": 0,
            "max_iterations": max_iterations,
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        self._save()

    def increment_iteration(self) -> int:
        """반복 횟수 증가"""
        self.state["workflow"]["iteration"] += 1
        self._save()
        return self.state["workflow"]["iteration"]

    def complete_workflow(self, success: bool = True):
        """워크플로우 완료"""
        self.state["workflow"]["status"] = "completed" if success else "failed"
        self.state["workflow"]["completed_at"] = datetime.now().isoformat()
        self._save()

    def pause_workflow(self):
        """워크플로우 일시정지"""
        self.state["workflow"]["status"] = "paused"
        self._save()

    def resume_workflow(self):
        """워크플로우 재개"""
        self.state["workflow"]["status"] = "running"
        self._save()

    # === 컴포넌트 상태 관리 ===

    def activate_component(self, component: str, **kwargs):
        """컴포넌트 활성화"""
        if component in self.state["components"]:
            self.state["components"][component]["active"] = True
            self.state["components"][component].update(kwargs)
            self._save()

    def deactivate_component(self, component: str):
        """컴포넌트 비활성화"""
        if component in self.state["components"]:
            self.state["components"][component]["active"] = False
            self._save()

    def update_component(self, component: str, **kwargs):
        """컴포넌트 상태 업데이트"""
        if component in self.state["components"]:
            self.state["components"][component].update(kwargs)
            self._save()

    # === Phase Gate 연동 ===

    def set_phase(self, phase: str):
        """현재 Phase 설정"""
        self.state["components"]["phase_gate"]["current_phase"] = phase
        self.state["components"]["phase_gate"]["active"] = True
        self.state["components"]["phase_gate"]["updated_at"] = datetime.now().isoformat()
        self._save()

    def get_phase(self) -> Optional[str]:
        """현재 Phase 조회"""
        return self.state["components"]["phase_gate"].get("current_phase")

    # === Circuit Breaker 연동 ===

    def record_circuit_failure(self, task_key: str) -> str:
        """Circuit Breaker 실패 기록"""
        cb = self.state["components"]["circuit_breaker"]
        cb["active"] = True

        if task_key not in cb["failures"]:
            cb["failures"][task_key] = 0
        cb["failures"][task_key] += 1

        count = cb["failures"][task_key]
        self._save()

        if count == 1:
            return "RETRY"
        elif count == 2:
            return "ALTERNATE_APPROACH"
        else:
            return "ESCALATE_TO_ARCHITECT"

    def reset_circuit(self, task_key: str):
        """Circuit Breaker 리셋"""
        cb = self.state["components"]["circuit_breaker"]
        if task_key in cb["failures"]:
            del cb["failures"][task_key]
            self._save()

    # === Verification 연동 (v2.0: array 형식) ===

    def record_check(self, check_type: str, passed: bool, evidence: str = ""):
        """검증 체크 기록 (v2.0: array 형식)"""
        checks = self.state["components"]["verification"]["checks"]

        # 기존 항목 업데이트 또는 새로 추가
        check_record = {
            "type": check_type,
            "passed": passed,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat(),
        }

        # 같은 타입의 기존 체크 제거 후 새로 추가
        if isinstance(checks, list):
            self.state["components"]["verification"]["checks"] = [
                c for c in checks if c.get("type") != check_type
            ]
            self.state["components"]["verification"]["checks"].append(check_record)
        else:
            # dict 형식(v1.0)에서 마이그레이션
            self.state["components"]["verification"]["checks"] = [check_record]

        self._save()

    def is_check_fresh(self, check_type: str, max_age_seconds: int = 300) -> bool:
        """검증 결과 freshness 확인"""
        checks = self.state["components"]["verification"]["checks"]

        # v2.0: array 형식
        if isinstance(checks, list):
            for check in checks:
                if check.get("type") == check_type:
                    timestamp = check.get("timestamp")
                    if timestamp:
                        check_time = datetime.fromisoformat(timestamp)
                        age = (datetime.now() - check_time).total_seconds()
                        return age < max_age_seconds
            return False

        # v1.0: dict 형식 (레거시 호환)
        if check_type not in checks:
            return False
        timestamp = checks[check_type].get("timestamp")
        if not timestamp:
            return False
        check_time = datetime.fromisoformat(timestamp)
        age = (datetime.now() - check_time).total_seconds()
        return age < max_age_seconds

    def get_latest_check(self, check_type: str) -> Optional[dict]:
        """최신 검증 결과 조회"""
        checks = self.state["components"]["verification"]["checks"]

        if isinstance(checks, list):
            for check in reversed(checks):  # 최신 항목부터
                if check.get("type") == check_type:
                    return check
            return None
        else:
            return checks.get(check_type)

    # === PDCA 사이클 관리 (v2.0) ===

    def start_pdca(self, feature: str, initial_phase: str = "plan"):
        """PDCA 사이클 시작"""
        self.state["pdca"] = {
            "phase": initial_phase,
            "feature": feature,
            "iteration": 0,
            "gap_percentage": None,
            "documents": {
                "plan": None,
                "design": None,
                "analysis": None,
                "report": None,
            },
            "started_at": datetime.now().isoformat(),
        }
        self._save()

    def set_pdca_phase(self, phase: str):
        """PDCA 단계 설정"""
        if "pdca" not in self.state:
            self.state["pdca"] = {}
        self.state["pdca"]["phase"] = phase
        self.state["pdca"]["updated_at"] = datetime.now().isoformat()
        self._save()

    def get_pdca_phase(self) -> Optional[str]:
        """현재 PDCA 단계 조회"""
        return self.state.get("pdca", {}).get("phase")

    def record_pdca_document(self, doc_type: str, path: str):
        """PDCA 문서 경로 기록"""
        if "pdca" not in self.state:
            self.state["pdca"] = {"documents": {}}
        if "documents" not in self.state["pdca"]:
            self.state["pdca"]["documents"] = {}
        self.state["pdca"]["documents"][doc_type] = path
        self._save()

    def record_gap_result(self, percentage: float):
        """gap-detector 결과 기록"""
        if "pdca" not in self.state:
            self.state["pdca"] = {}
        self.state["pdca"]["gap_percentage"] = percentage
        self.state["pdca"]["iteration"] = self.state["pdca"].get("iteration", 0) + 1
        self._save()

    def is_pdca_complete(self, threshold: float = 90.0) -> bool:
        """PDCA 완료 여부 (gap >= threshold)"""
        gap = self.state.get("pdca", {}).get("gap_percentage")
        if gap is None:
            return False
        return gap >= threshold

    def get_pdca_status(self) -> dict:
        """PDCA 상태 요약"""
        pdca = self.state.get("pdca", {})
        return {
            "phase": pdca.get("phase"),
            "feature": pdca.get("feature"),
            "iteration": pdca.get("iteration", 0),
            "gap_percentage": pdca.get("gap_percentage"),
            "is_complete": self.is_pdca_complete(),
            "documents": pdca.get("documents", {}),
        }

    # === 메타데이터 ===

    def set_metadata(self, key: str, value: Any):
        """메타데이터 설정"""
        self.state["metadata"][key] = value
        self._save()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """메타데이터 조회"""
        return self.state["metadata"].get(key, default)

    # === 상태 조회 ===

    def get_status(self) -> dict:
        """전체 상태 요약"""
        return {
            "session_id": self.session_id,
            "workflow": self.state["workflow"],
            "components": {
                name: {"active": comp.get("active", False)}
                for name, comp in self.state["components"].items()
            },
            "updated_at": self.state["updated_at"],
        }

    def get_full_state(self) -> dict:
        """전체 상태 반환"""
        return self.state.copy()

    def clear(self):
        """상태 초기화"""
        self.state = {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "components": {
                "context_manager": {"active": False},
                "phase_gate": {"active": False, "current_phase": None},
                "circuit_breaker": {"active": False, "failures": {}},
                "verification": {"checks": {}},
            },
            "workflow": {
                "mode": None,
                "iteration": 0,
                "max_iterations": 10,
                "status": "idle",
            },
            "metadata": {},
        }
        self._save()


# === 편의 함수 ===

def get_unified_state() -> Optional[UnifiedStateManager]:
    """현재 통합 상태 로드"""
    if UNIFIED_STATE_FILE.exists():
        try:
            with open(UNIFIED_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                session_id = data.get("session_id")
                if session_id:
                    return UnifiedStateManager(session_id)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def create_unified_state(session_id: Optional[str] = None) -> UnifiedStateManager:
    """새 통합 상태 생성"""
    return UnifiedStateManager(session_id)


if __name__ == "__main__":
    print("=== Unified State Manager Test ===\n")

    # 테스트 1: 상태 생성
    print("1. 상태 생성")
    state = UnifiedStateManager("test_unified")
    print(f"   Session ID: {state.session_id}")

    # 테스트 2: 워크플로우 시작
    print("\n2. 워크플로우 시작")
    state.start_workflow("auto", max_iterations=5)
    print(f"   Mode: {state.state['workflow']['mode']}")
    print(f"   Status: {state.state['workflow']['status']}")

    # 테스트 3: Phase 설정
    print("\n3. Phase 설정")
    state.set_phase("EXECUTE")
    print(f"   Current Phase: {state.get_phase()}")

    # 테스트 4: Circuit Breaker
    print("\n4. Circuit Breaker 테스트")
    result1 = state.record_circuit_failure("task_1")
    print(f"   1차 실패: {result1}")
    result2 = state.record_circuit_failure("task_1")
    print(f"   2차 실패: {result2}")
    result3 = state.record_circuit_failure("task_1")
    print(f"   3차 실패: {result3}")

    # 테스트 5: Verification
    print("\n5. Verification 테스트")
    state.record_check("BUILD", True, "npm run build 성공")
    print(f"   BUILD fresh: {state.is_check_fresh('BUILD')}")

    # 테스트 6: 상태 요약
    print("\n6. 상태 요약")
    status = state.get_status()
    print(f"   {json.dumps(status, indent=2, ensure_ascii=False)}")

    print("\n=== 테스트 완료 ===")
