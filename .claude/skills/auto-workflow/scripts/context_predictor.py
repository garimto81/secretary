"""
Context Predictor - 작업 수행 전 Context 오버플로우 예측

작업별 예상 Context 소모량을 기반으로 오버플로우를 사전에 감지하고
체크포인트/정리 시점을 제안합니다.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

# 커맨드별 예상 Context 소모량 (%)
COMMAND_ESTIMATES: Dict[str, float] = {
    "/debug": 15.0,
    "/check --fix": 10.0,
    "/check --security": 8.0,
    "/commit": 5.0,
    "/issue fix": 20.0,
    "/pr auto": 12.0,
    "/tdd": 25.0,
    "/research": 8.0,
    "/audit quick": 5.0,
}

# 에이전트별 예상 Context 소모량 (%)
AGENT_ESTIMATES: Dict[str, float] = {
    "architect": 10.0,
    "architect-medium": 7.0,
    "architect-low": 4.0,
    "executor": 8.0,
    "executor-high": 12.0,
    "executor-low": 4.0,
    "explore": 3.0,
    "explore-medium": 5.0,
    "explore-high": 8.0,
    "designer": 10.0,
    "writer": 5.0,
    "researcher": 8.0,
    "qa-tester": 10.0,
    "build-fixer": 6.0,
    "security-reviewer": 8.0,
    "tdd-guide": 10.0,
    "planner": 12.0,
    "critic": 8.0,
}


@dataclass
class TaskEstimate:
    """작업 예상치"""
    task: str
    estimated_cost: float
    can_proceed: bool
    reason: str


def predict_and_decide(current_usage: float, task: str, threshold: float = 20.0) -> TaskEstimate:
    """작업 수행 가능 여부 결정

    Args:
        current_usage: 현재 Context 사용량 (0-100)
        task: 수행할 작업
        threshold: 남은 여유 임계값 (%)

    Returns:
        TaskEstimate with decision
    """
    predictor = ContextPredictor(current_usage)
    cost = predictor.estimate_cost(task)
    remaining = 100.0 - current_usage

    can_proceed = cost <= remaining - threshold

    if can_proceed:
        reason = f"충분한 여유 ({remaining:.1f}% 남음, {cost:.1f}% 필요)"
    else:
        reason = f"Context 부족 ({remaining:.1f}% 남음, {cost:.1f}% + {threshold:.1f}% 여유 필요)"

    return TaskEstimate(
        task=task,
        estimated_cost=cost,
        can_proceed=can_proceed,
        reason=reason
    )


@dataclass
class ContextPrediction:
    """Context 예측 결과"""
    current_usage: float
    estimated_cost: float
    predicted_total: float
    will_overflow: bool
    recommendation: str

    def __str__(self) -> str:
        status = "OVERFLOW" if self.will_overflow else "OK"
        return (
            f"[{status}] Current: {self.current_usage:.1f}% + "
            f"Cost: {self.estimated_cost:.1f}% = "
            f"Total: {self.predicted_total:.1f}%\n"
            f"→ {self.recommendation}"
        )


class ContextPredictor:
    """Context 사용량 예측 및 관리"""

    WARNING_THRESHOLD = 80.0
    EMERGENCY_THRESHOLD = 90.0
    SAFE_THRESHOLD = 70.0

    def __init__(self, current_usage: float = 0.0):
        """
        Args:
            current_usage: 현재 Context 사용량 (0-100)
        """
        self.current_usage = current_usage

    def estimate_cost(self, task: str) -> float:
        """작업의 예상 Context 비용 반환

        Args:
            task: 커맨드명 또는 에이전트명

        Returns:
            예상 Context 소모량 (%)
        """
        if task in COMMAND_ESTIMATES:
            return COMMAND_ESTIMATES[task]
        if task in AGENT_ESTIMATES:
            return AGENT_ESTIMATES[task]
        return 10.0  # 기본값

    def predict(self, task: str) -> ContextPrediction:
        """작업 수행 시 Context 상태 예측

        Args:
            task: 수행할 작업 (커맨드 또는 에이전트)

        Returns:
            예측 결과
        """
        cost = self.estimate_cost(task)
        total = self.current_usage + cost
        overflow = total > self.EMERGENCY_THRESHOLD

        if total > self.EMERGENCY_THRESHOLD:
            recommendation = "EMERGENCY: checkpoint → clear → resume"
        elif total > self.WARNING_THRESHOLD:
            recommendation = "WARNING: 작업 완료 후 정리 권장"
        else:
            recommendation = "SAFE: 계속 진행"

        return ContextPrediction(
            current_usage=self.current_usage,
            estimated_cost=cost,
            predicted_total=total,
            will_overflow=overflow,
            recommendation=recommendation
        )

    def should_checkpoint(self, next_task: str) -> bool:
        """체크포인트 필요 여부

        Args:
            next_task: 다음 수행할 작업

        Returns:
            True if checkpoint recommended
        """
        prediction = self.predict(next_task)
        return prediction.predicted_total > self.WARNING_THRESHOLD

    def should_emergency_clear(self) -> bool:
        """긴급 정리 필요 여부

        Returns:
            True if emergency clear needed
        """
        return self.current_usage >= self.EMERGENCY_THRESHOLD

    def get_safe_tasks(self) -> List[str]:
        """현재 Context로 안전하게 수행 가능한 작업 목록

        Returns:
            안전한 작업 목록 (비용 낮은 순)
        """
        safe = []
        remaining = self.SAFE_THRESHOLD - self.current_usage

        for task, cost in {**COMMAND_ESTIMATES, **AGENT_ESTIMATES}.items():
            if cost <= remaining:
                safe.append(task)

        return sorted(safe, key=lambda t: self.estimate_cost(t))

    def update_usage(self, new_usage: float) -> None:
        """현재 사용량 업데이트

        Args:
            new_usage: 새로운 사용량 (0-100)
        """
        self.current_usage = new_usage


# CLI 인터페이스
if __name__ == "__main__":
    import sys
    import io

    # Windows cp949 인코딩 문제 해결
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) < 3:
        print("Usage: python context_predictor.py <current_usage> <task>")
        print("\nExample:")
        print("  python context_predictor.py 65 /tdd")
        print("  python context_predictor.py 85 architect")
        sys.exit(1)

    current = float(sys.argv[1])
    task = sys.argv[2]

    predictor = ContextPredictor(current_usage=current)
    prediction = predictor.predict(task)

    print(prediction)
    print()

    if predictor.should_emergency_clear():
        print("WARNING: EMERGENCY - Context 긴급 정리 필요")
    elif predictor.should_checkpoint(task):
        print("WARNING: 작업 전 체크포인트 권장")

    safe_tasks = predictor.get_safe_tasks()[:5]
    print(f"\n안전한 작업: {', '.join(safe_tasks)}")