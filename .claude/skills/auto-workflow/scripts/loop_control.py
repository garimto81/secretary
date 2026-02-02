from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path
import json
from datetime import datetime

class LoopStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    EMERGENCY = "emergency"
    ABORTED = "aborted"

class TerminationReason(Enum):
    MAX_ITERATIONS = "max_iterations"
    PROMISE_OUTPUT = "promise_output"
    CONTEXT_EMERGENCY = "context_emergency"
    USER_PAUSE = "user_pause"
    USER_ABORT = "user_abort"
    NO_WORK_FOUND = "no_work_found"
    ARCHITECT_APPROVED = "architect_approved"

@dataclass
class DiscoveryState:
    current_tier: int = 1
    last_discovery: str = ""
    pending_commands: List[str] = field(default_factory=list)
    completed_commands: List[str] = field(default_factory=list)
    no_work_count: int = 0  # Tier 4+ 발견 없음 카운터

@dataclass
class ContextState:
    usage_percent: float = 0.0
    last_checkpoint: Optional[str] = None
    estimated_next_task_cost: float = 10.0

@dataclass
class OMCDelegationState:
    ralplan_complete: bool = False
    ultrawork_active: bool = False
    ralph_iteration: int = 0

@dataclass
class AutoSession:
    session_id: str
    mode: str = "auto"
    iteration: int = 0
    max_iterations: int = 10
    status: LoopStatus = LoopStatus.IDLE
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    termination_reason: Optional[TerminationReason] = None

    discovery: DiscoveryState = field(default_factory=DiscoveryState)
    context: ContextState = field(default_factory=ContextState)
    omc_delegation: OMCDelegationState = field(default_factory=OMCDelegationState)

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화용 딕셔너리 변환"""
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "termination_reason": self.termination_reason.value if self.termination_reason else None,
            "discovery": asdict(self.discovery),
            "context": asdict(self.context),
            "omc_delegation": asdict(self.omc_delegation),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoSession":
        """딕셔너리에서 AutoSession 생성"""
        return cls(
            session_id=data["session_id"],
            mode=data.get("mode", "auto"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 10),
            status=LoopStatus(data.get("status", "idle")),
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at"),
            termination_reason=TerminationReason(data["termination_reason"]) if data.get("termination_reason") else None,
            discovery=DiscoveryState(**data.get("discovery", {})),
            context=ContextState(**data.get("context", {})),
            omc_delegation=OMCDelegationState(**data.get("omc_delegation", {})),
        )


class LoopController:
    """루프 제어 및 세션 관리"""

    SESSION_FILE = Path("C:/claude/.omc/state/auto-session.json")
    CHECKPOINT_DIR = Path("C:/claude/.omc/checkpoints")

    NO_WORK_THRESHOLD = 3  # Tier 4+ 발견 없음 허용 횟수
    CONTEXT_WARNING = 80.0
    CONTEXT_EMERGENCY = 90.0

    def __init__(self):
        self.session: Optional[AutoSession] = None
        self._ensure_directories()

    def _ensure_directories(self):
        """필요한 디렉토리 생성"""
        self.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def _generate_session_id(self) -> str:
        """세션 ID 생성"""
        return f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def start_session(self, max_iterations: int = 10) -> AutoSession:
        """새 세션 시작"""
        self.session = AutoSession(
            session_id=self._generate_session_id(),
            max_iterations=max_iterations,
            status=LoopStatus.RUNNING,
            started_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self.save_session()
        return self.session

    def load_session(self) -> Optional[AutoSession]:
        """기존 세션 로드"""
        if self.SESSION_FILE.exists():
            with open(self.SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.session = AutoSession.from_dict(data)
                return self.session
        return None

    def save_session(self):
        """세션 저장"""
        if self.session:
            self.session.updated_at = datetime.now().isoformat()
            with open(self.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(self.session.to_dict(), f, indent=2, ensure_ascii=False)

    def delete_session(self):
        """세션 파일 삭제 (완료 시)"""
        if self.SESSION_FILE.exists():
            self.SESSION_FILE.unlink()
        self.session = None

    def increment_iteration(self):
        """반복 횟수 증가"""
        if self.session:
            self.session.iteration += 1
            self.save_session()

    def check_termination(self, context_usage: float, work_found: bool) -> Optional[TerminationReason]:
        """종료 조건 확인"""
        if not self.session:
            return None

        # Context 90%+ Emergency
        if context_usage >= self.CONTEXT_EMERGENCY:
            self.session.status = LoopStatus.EMERGENCY
            return TerminationReason.CONTEXT_EMERGENCY

        # Max iterations 도달
        if self.session.iteration >= self.session.max_iterations:
            self.session.status = LoopStatus.COMPLETED
            return TerminationReason.MAX_ITERATIONS

        # Tier 4+ 발견 없음 카운터 업데이트
        if not work_found:
            self.session.discovery.no_work_count += 1
            if self.session.discovery.no_work_count >= self.NO_WORK_THRESHOLD:
                self.session.status = LoopStatus.COMPLETED
                return TerminationReason.NO_WORK_FOUND
        else:
            self.session.discovery.no_work_count = 0

        self.save_session()
        return None

    def should_checkpoint(self, context_usage: float, next_task_cost: float) -> bool:
        """체크포인트 필요 여부"""
        predicted = context_usage + next_task_cost
        return predicted > self.CONTEXT_WARNING

    def create_checkpoint(self) -> str:
        """체크포인트 생성"""
        if not self.session:
            return ""

        checkpoint_id = f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checkpoint_file = self.CHECKPOINT_DIR / f"{checkpoint_id}.json"

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(self.session.to_dict(), f, indent=2, ensure_ascii=False)

        self.session.context.last_checkpoint = checkpoint_id
        self.save_session()
        return checkpoint_id

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[AutoSession]:
        """체크포인트에서 복원"""
        checkpoint_file = self.CHECKPOINT_DIR / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.session = AutoSession.from_dict(data)
                self.session.status = LoopStatus.RUNNING
                self.save_session()
                return self.session
        return None

    def pause(self):
        """세션 일시정지"""
        if self.session:
            self.create_checkpoint()
            self.session.status = LoopStatus.PAUSED
            self.session.termination_reason = TerminationReason.USER_PAUSE
            self.save_session()

    def abort(self):
        """세션 중단"""
        if self.session:
            self.session.status = LoopStatus.ABORTED
            self.session.termination_reason = TerminationReason.USER_ABORT
            self.save_session()
            self.delete_session()

    def complete(self, reason: TerminationReason = TerminationReason.ARCHITECT_APPROVED):
        """세션 완료"""
        if self.session:
            self.session.status = LoopStatus.COMPLETED
            self.session.termination_reason = reason
            self.save_session()
            self.delete_session()

    def get_status_summary(self) -> str:
        """상태 요약 문자열"""
        if not self.session:
            return "No active session"

        return f"""Session: {self.session.session_id}
Status: {self.session.status.value}
Iteration: {self.session.iteration}/{self.session.max_iterations}
Context: {self.session.context.usage_percent:.1f}%
Discovery Tier: {self.session.discovery.current_tier}
No-Work Count: {self.session.discovery.no_work_count}/{self.NO_WORK_THRESHOLD}"""


def get_loop_controller() -> LoopController:
    return LoopController()


if __name__ == "__main__":
    controller = LoopController()

    # 새 세션 시작
    session = controller.start_session(max_iterations=5)
    print(f"Started: {session.session_id}")

    # 상태 확인
    print(controller.get_status_summary())

    # 종료 조건 테스트
    reason = controller.check_termination(context_usage=45.0, work_found=True)
    print(f"Termination: {reason}")

    # 정리
    controller.delete_session()
