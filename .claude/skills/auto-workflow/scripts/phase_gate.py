#!/usr/bin/env python3
"""
Phase Gate Manager - 세션 복원력을 위한 파일 기반 Phase 핸드오프

세션 복원력을 위한 Phase 관리:
- Phase 파일: .omc/state/phase/{session_id}.json
- 상태 저장: 현재 Phase, 완료된 작업, 다음 작업
- 세션 복원: 이전 세션에서 Phase 자동 복구

Phase 정의:
- INIT: 작업 분석
- PLAN: 계획 수립 (Ralplan 사용 시)
- EXECUTE: 실행
- VERIFY: Architect 검증
- COMPLETE: 완료
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# 동적 프로젝트 루트 감지
def _get_project_root() -> Path:
    """프로젝트 루트 디렉토리를 동적으로 감지"""
    if env_root := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent.parent
    if (project_root / ".claude").exists():
        return project_root
    return Path.cwd()


PROJECT_ROOT = _get_project_root()
STATE_DIR = PROJECT_ROOT / ".omc" / "state" / "phase"


class Phase(Enum):
    """워크플로우 Phase 정의"""
    INIT = "init"           # 작업 분석
    PLAN = "plan"           # 계획 수립
    EXECUTE = "execute"     # 실행
    VERIFY = "verify"       # Architect 검증
    COMPLETE = "complete"   # 완료
    FAILED = "failed"       # 실패
    PAUSED = "paused"       # 일시정지


# Phase 전이 규칙 (현재 Phase → 허용되는 다음 Phase)
PHASE_TRANSITIONS = {
    Phase.INIT: [Phase.PLAN, Phase.EXECUTE, Phase.FAILED],
    Phase.PLAN: [Phase.EXECUTE, Phase.INIT, Phase.FAILED, Phase.PAUSED],
    Phase.EXECUTE: [Phase.VERIFY, Phase.PLAN, Phase.FAILED, Phase.PAUSED],
    Phase.VERIFY: [Phase.COMPLETE, Phase.EXECUTE, Phase.FAILED],
    Phase.COMPLETE: [],  # 종료 상태
    Phase.FAILED: [Phase.INIT],  # 재시작 가능
    Phase.PAUSED: [Phase.INIT, Phase.PLAN, Phase.EXECUTE],  # 재개 가능
}


@dataclass
class PhaseTask:
    """Phase 내 작업"""
    id: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhaseTask":
        return cls(**data)


@dataclass
class PhaseState:
    """Phase 상태"""
    session_id: str
    current_phase: Phase
    original_request: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tasks: dict[str, list[PhaseTask]] = field(default_factory=dict)
    phase_history: list[dict] = field(default_factory=list)
    context_hint: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "current_phase": self.current_phase.value,
            "original_request": self.original_request,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tasks": {
                phase: [t.to_dict() for t in tasks]
                for phase, tasks in self.tasks.items()
            },
            "phase_history": self.phase_history,
            "context_hint": self.context_hint,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhaseState":
        tasks = {}
        for phase, task_list in data.get("tasks", {}).items():
            tasks[phase] = [PhaseTask.from_dict(t) for t in task_list]

        return cls(
            session_id=data["session_id"],
            current_phase=Phase(data["current_phase"]),
            original_request=data["original_request"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            tasks=tasks,
            phase_history=data.get("phase_history", []),
            context_hint=data.get("context_hint", ""),
            metadata=data.get("metadata", {}),
        )


class PhaseGateManager:
    """Phase Gate 관리 클래스"""

    def __init__(self, session_id: Optional[str] = None):
        """
        Args:
            session_id: 세션 ID (None이면 새 세션 생성)
        """
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        if session_id:
            self.session_id = session_id
        else:
            self.session_id = f"phase_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.state_file = STATE_DIR / f"{self.session_id}.json"
        self.state: Optional[PhaseState] = None

        if self.state_file.exists():
            self._load_state()

    def _load_state(self):
        """상태 파일 로드"""
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.state = PhaseState.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            print(f"Warning: Failed to load state: {e}")
            self.state = None

    def _save_state(self):
        """상태 파일 저장"""
        if not self.state:
            return

        self.state.updated_at = datetime.now().isoformat()
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"Warning: Failed to save state: {e}")

    def initialize(self, original_request: str, metadata: Optional[dict] = None) -> PhaseState:
        """
        새 세션 초기화

        Args:
            original_request: 원본 요청
            metadata: 추가 메타데이터

        Returns:
            PhaseState 객체
        """
        self.state = PhaseState(
            session_id=self.session_id,
            current_phase=Phase.INIT,
            original_request=original_request,
            metadata=metadata or {},
        )
        self._save_state()
        return self.state

    def can_transition(self, to_phase: Phase) -> bool:
        """
        Phase 전이 가능 여부 확인

        Args:
            to_phase: 목표 Phase

        Returns:
            전이 가능 여부
        """
        if not self.state:
            return False

        allowed = PHASE_TRANSITIONS.get(self.state.current_phase, [])
        return to_phase in allowed

    def transition(self, to_phase: Phase, reason: str = "") -> bool:
        """
        Phase 전이 수행

        Args:
            to_phase: 목표 Phase
            reason: 전이 사유

        Returns:
            전이 성공 여부
        """
        if not self.state:
            return False

        if not self.can_transition(to_phase):
            print(
                f"Warning: Invalid transition {self.state.current_phase.value} -> {to_phase.value}"
            )
            return False

        # 히스토리 기록
        self.state.phase_history.append({
            "from": self.state.current_phase.value,
            "to": to_phase.value,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

        self.state.current_phase = to_phase
        self._save_state()
        return True

    def add_task(self, phase: Phase, task_id: str, description: str) -> PhaseTask:
        """
        Phase에 작업 추가

        Args:
            phase: 대상 Phase
            task_id: 작업 ID
            description: 작업 설명

        Returns:
            생성된 PhaseTask
        """
        if not self.state:
            raise ValueError("Session not initialized")

        task = PhaseTask(id=task_id, description=description)

        phase_key = phase.value
        if phase_key not in self.state.tasks:
            self.state.tasks[phase_key] = []

        self.state.tasks[phase_key].append(task)
        self._save_state()
        return task

    def update_task(
        self,
        phase: Phase,
        task_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> Optional[PhaseTask]:
        """
        작업 상태 업데이트

        Args:
            phase: 대상 Phase
            task_id: 작업 ID
            status: 새 상태
            result: 결과 (선택)
            error: 에러 메시지 (선택)

        Returns:
            업데이트된 PhaseTask 또는 None
        """
        if not self.state:
            return None

        phase_key = phase.value
        tasks = self.state.tasks.get(phase_key, [])

        for task in tasks:
            if task.id == task_id:
                task.status = status
                if status == "in_progress" and not task.started_at:
                    task.started_at = datetime.now().isoformat()
                if status in ["completed", "failed"]:
                    task.completed_at = datetime.now().isoformat()
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error

                self._save_state()
                return task

        return None

    def get_phase_tasks(self, phase: Phase) -> list[PhaseTask]:
        """Phase의 모든 작업 조회"""
        if not self.state:
            return []

        return self.state.tasks.get(phase.value, [])

    def get_pending_tasks(self, phase: Optional[Phase] = None) -> list[PhaseTask]:
        """미완료 작업 조회"""
        if not self.state:
            return []

        pending = []
        phases_to_check = [phase.value] if phase else self.state.tasks.keys()

        for phase_key in phases_to_check:
            for task in self.state.tasks.get(phase_key, []):
                if task.status in ["pending", "in_progress"]:
                    pending.append(task)

        return pending

    def set_context_hint(self, hint: str):
        """컨텍스트 힌트 설정 (세션 복원용)"""
        if self.state:
            self.state.context_hint = hint
            self._save_state()

    def get_resume_info(self) -> dict:
        """
        세션 복원 정보 조회

        Returns:
            {
                "session_id": str,
                "current_phase": str,
                "original_request": str,
                "context_hint": str,
                "pending_tasks": list,
                "phase_history": list,
                "can_resume": bool
            }
        """
        if not self.state:
            return {"can_resume": False, "error": "No state found"}

        pending = self.get_pending_tasks()

        return {
            "session_id": self.session_id,
            "current_phase": self.state.current_phase.value,
            "original_request": self.state.original_request,
            "context_hint": self.state.context_hint,
            "pending_tasks": [
                {"id": t.id, "description": t.description, "status": t.status}
                for t in pending
            ],
            "phase_history": self.state.phase_history,
            "can_resume": self.state.current_phase not in [Phase.COMPLETE, Phase.FAILED],
            "metadata": self.state.metadata,
        }

    def get_summary(self) -> str:
        """세션 요약 문자열 생성"""
        if not self.state:
            return "세션 상태 없음"

        pending = self.get_pending_tasks()

        summary = f"""
## Phase Gate 세션: {self.session_id}

### 원본 요청
{self.state.original_request}

### 현재 Phase
{self.state.current_phase.value.upper()}

### 진행 상황
"""

        for phase in Phase:
            tasks = self.get_phase_tasks(phase)
            if tasks:
                completed = sum(1 for t in tasks if t.status == "completed")
                total = len(tasks)
                summary += f"- {phase.value}: {completed}/{total} 완료\n"

        if pending:
            summary += f"\n### 미완료 작업 ({len(pending)}개)\n"
            for task in pending[:5]:
                summary += f"- [{task.status}] {task.description}\n"
            if len(pending) > 5:
                summary += f"- ... 외 {len(pending) - 5}개\n"

        if self.state.context_hint:
            summary += f"\n### 컨텍스트 힌트\n{self.state.context_hint}\n"

        return summary.strip()

    def complete(self, summary: Optional[str] = None):
        """세션 완료"""
        if self.state and self.can_transition(Phase.COMPLETE):
            self.transition(Phase.COMPLETE, summary or "Session completed")

    def fail(self, error: str):
        """세션 실패"""
        if self.state:
            self.state.metadata["error"] = error
            self.transition(Phase.FAILED, error)

    def pause(self, reason: str = "Manual pause"):
        """세션 일시정지"""
        if self.state and self.can_transition(Phase.PAUSED):
            self.transition(Phase.PAUSED, reason)


# === 편의 함수 ===

def get_active_sessions() -> list[str]:
    """활성 세션 목록 조회"""
    if not STATE_DIR.exists():
        return []

    sessions = []
    for f in STATE_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                phase = data.get("current_phase", "")
                if phase not in ["complete", "failed"]:
                    sessions.append(f.stem)
        except (json.JSONDecodeError, OSError):
            pass

    return sessions


def restore_session(session_id: str) -> Optional[PhaseGateManager]:
    """
    세션 복원

    Args:
        session_id: 복원할 세션 ID

    Returns:
        PhaseGateManager 또는 None
    """
    manager = PhaseGateManager(session_id)
    if manager.state:
        return manager
    return None


def create_session(original_request: str, session_id: Optional[str] = None) -> PhaseGateManager:
    """
    새 세션 생성

    Args:
        original_request: 원본 요청
        session_id: 세션 ID (선택)

    Returns:
        PhaseGateManager
    """
    manager = PhaseGateManager(session_id)
    manager.initialize(original_request)
    return manager


if __name__ == "__main__":
    print("=== Phase Gate Manager Test ===\n")

    # 테스트 1: 새 세션 생성
    print("1. 새 세션 생성")
    manager = PhaseGateManager()
    manager.initialize("API 인증 기능 구현", metadata={"priority": "high"})
    print(f"   Session ID: {manager.session_id}")
    print(f"   Current Phase: {manager.state.current_phase.value}")

    # 테스트 2: 작업 추가
    print("\n2. 작업 추가")
    manager.add_task(Phase.INIT, "analyze-1", "요구사항 분석")
    manager.add_task(Phase.INIT, "analyze-2", "기존 코드 조사")
    manager.add_task(Phase.EXECUTE, "impl-1", "핸들러 구현")
    manager.add_task(Phase.EXECUTE, "impl-2", "테스트 작성")
    print(f"   INIT 작업: {len(manager.get_phase_tasks(Phase.INIT))}개")
    print(f"   EXECUTE 작업: {len(manager.get_phase_tasks(Phase.EXECUTE))}개")

    # 테스트 3: 작업 상태 업데이트
    print("\n3. 작업 상태 업데이트")
    manager.update_task(Phase.INIT, "analyze-1", "completed", result="요구사항 5개 확인")
    manager.update_task(Phase.INIT, "analyze-2", "in_progress")
    pending = manager.get_pending_tasks()
    print(f"   미완료 작업: {len(pending)}개")

    # 테스트 4: Phase 전이
    print("\n4. Phase 전이")
    print(f"   INIT -> PLAN 가능: {manager.can_transition(Phase.PLAN)}")
    print(f"   INIT -> VERIFY 가능: {manager.can_transition(Phase.VERIFY)}")

    manager.transition(Phase.PLAN, "분석 완료")
    print(f"   현재 Phase: {manager.state.current_phase.value}")

    manager.transition(Phase.EXECUTE, "계획 수립 완료")
    print(f"   현재 Phase: {manager.state.current_phase.value}")

    # 테스트 5: 컨텍스트 힌트
    print("\n5. 컨텍스트 힌트 설정")
    manager.set_context_hint("JWT 토큰 방식 선택, src/auth/handler.py 수정 중")
    print(f"   힌트: {manager.state.context_hint}")

    # 테스트 6: 복원 정보
    print("\n6. 복원 정보")
    resume_info = manager.get_resume_info()
    print(f"   복원 가능: {resume_info['can_resume']}")
    print(f"   미완료 작업: {len(resume_info['pending_tasks'])}개")
    print(f"   Phase 히스토리: {len(resume_info['phase_history'])}개 전이")

    # 테스트 7: 요약
    print("\n7. 세션 요약")
    print(manager.get_summary())

    # 테스트 8: 세션 복원
    print("\n8. 세션 복원 테스트")
    restored = restore_session(manager.session_id)
    if restored:
        print(f"   복원 성공: {restored.session_id}")
        print(f"   Phase: {restored.state.current_phase.value}")
    else:
        print("   복원 실패")

    # 테스트 9: 활성 세션 목록
    print("\n9. 활성 세션 목록")
    active = get_active_sessions()
    print(f"   활성 세션: {len(active)}개")

    print("\n=== 테스트 완료 ===")
