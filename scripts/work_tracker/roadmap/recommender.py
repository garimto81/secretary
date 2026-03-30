"""
Task Recommender — 오늘 할 Task 추천 엔진

pending/in_progress Task를 우선순위/의존성/effort 기반으로 점수화하여
오늘 집중해야 할 Task 목록을 추천합니다.
"""

import json
from typing import Optional

# 3-way import
try:
    from scripts.work_tracker.roadmap.models import (
        RoadmapTask, RoadmapPhase, RoadmapMilestone,
        TaskStatus, TaskPriority, TaskEffort,
    )
    from scripts.work_tracker.roadmap.storage import RoadmapStorage
except ImportError:
    try:
        from work_tracker.roadmap.models import (
            RoadmapTask, RoadmapPhase, RoadmapMilestone,
            TaskStatus, TaskPriority, TaskEffort,
        )
        from work_tracker.roadmap.storage import RoadmapStorage
    except ImportError:
        from .models import (
            RoadmapTask, RoadmapPhase, RoadmapMilestone,
            TaskStatus, TaskPriority, TaskEffort,
        )
        from .storage import RoadmapStorage


# 우선순위 점수 테이블
_PRIORITY_SCORE: dict[TaskPriority, int] = {
    TaskPriority.HIGH: 10,
    TaskPriority.MEDIUM: 5,
    TaskPriority.LOW: 2,
}

# effort 점수 테이블 (작을수록 빨리 끝남 → 높은 점수)
_EFFORT_SCORE: dict[TaskEffort, int] = {
    TaskEffort.SMALL: 3,
    TaskEffort.MEDIUM: 1,
    TaskEffort.LARGE: 0,
}


class TaskRecommender:
    """오늘 할 Task 추천 엔진"""

    async def recommend(self, project: str, top_n: int = 5) -> list[dict]:
        """우선순위 기반 추천 Task 리스트 반환

        추천 로직:
        1. pending + in_progress Task만 대상 (blocked 제외)
        2. 점수 = priority_score + dependency_score + effort_score
           - high priority: +10, medium: +5, low: +2
           - 의존 Task 모두 완료: +5 / 미완료 의존 있음: -10
           - small effort: +3 (빨리 끝낼 수 있음)
        3. 상위 top_n개 반환

        반환 형식:
        [
            {
                "task_id": 1,
                "title": "...",
                "priority": "high",
                "effort": "small",
                "phase": "Phase 1-2",
                "milestone": "기획 확정",
                "reason": "높은 우선순위 + 의존 없음",
                "score": 18
            }
        ]
        """
        async with RoadmapStorage() as storage:
            # 활성 Task 조회 (pending + in_progress)
            pending = await storage.get_tasks_by_project(project, status="pending")
            in_progress = await storage.get_tasks_by_project(project, status="in_progress")
            active_tasks = in_progress + pending  # in_progress 우선

            if not active_tasks:
                return []

            # 완료된 Task ID 집합 (의존성 검사용)
            done_tasks = await storage.get_tasks_by_project(project, status="done")
            done_ids: set[int] = {t.id for t in done_tasks if t.id is not None}

            # Phase/Milestone 인덱스 구성 (task_id → 이름 조회)
            phase_ms_index = await self._build_phase_milestone_index(storage, project)

            # 점수 계산
            scored: list[tuple[int, RoadmapTask, str]] = []
            for task in active_tasks:
                score, reason = self._score_task(task, done_ids)
                scored.append((score, task, reason))

            # 점수 내림차순 정렬
            scored.sort(key=lambda x: -x[0])

            # 상위 top_n 변환
            results = []
            for score, task, reason in scored[:top_n]:
                ms_info = phase_ms_index.get(task.milestone_id, {})
                priority_str = (
                    task.priority.value
                    if isinstance(task.priority, TaskPriority)
                    else str(task.priority)
                )
                effort_str = self._effort_label(task.effort)
                results.append({
                    "task_id": task.id,
                    "title": task.title,
                    "priority": priority_str,
                    "effort": effort_str,
                    "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
                    "phase": ms_info.get("phase_name", ""),
                    "milestone": ms_info.get("milestone_name", ""),
                    "related_repo": task.related_repo,
                    "reason": reason,
                    "score": score,
                })

            return results

    def _score_task(
        self,
        task: RoadmapTask,
        done_ids: set[int],
    ) -> tuple[int, str]:
        """Task 점수 계산 및 추천 이유 생성

        반환: (score, reason_str)
        """
        score = 0
        reasons = []

        # 1. 우선순위 점수
        priority = (
            task.priority
            if isinstance(task.priority, TaskPriority)
            else TaskPriority(task.priority)
        )
        p_score = _PRIORITY_SCORE.get(priority, 5)
        score += p_score
        if priority == TaskPriority.HIGH:
            reasons.append("높은 우선순위")
        elif priority == TaskPriority.LOW:
            reasons.append("낮은 우선순위")

        # 2. in_progress 보너스 (이미 시작한 작업 우선)
        task_status = (
            task.status
            if isinstance(task.status, TaskStatus)
            else TaskStatus(task.status)
        )
        if task_status == TaskStatus.IN_PROGRESS:
            score += 4
            reasons.append("진행 중")

        # 3. 의존성 점수
        depends_on = self._parse_json_list(task.depends_on)
        if not depends_on:
            score += 5
            reasons.append("의존 없음")
        else:
            unresolved = [dep_id for dep_id in depends_on if dep_id not in done_ids]
            if unresolved:
                score -= 10
                reasons.append(f"미완료 의존 {len(unresolved)}개")
            else:
                score += 5
                reasons.append("의존 완료")

        # 4. effort 점수 (작은 작업 우선)
        effort = (
            task.effort
            if isinstance(task.effort, TaskEffort)
            else TaskEffort(int(task.effort))
        )
        e_score = _EFFORT_SCORE.get(effort, 1)
        score += e_score
        if effort == TaskEffort.SMALL:
            reasons.append("빠른 완료 가능")
        elif effort == TaskEffort.LARGE:
            reasons.append("대형 작업")

        return score, " + ".join(reasons) if reasons else "일반"

    def _parse_json_list(self, raw: str) -> list[int]:
        """JSON 배열 문자열 → int 리스트 (파싱 실패 시 빈 리스트)"""
        if not raw or raw == "[]":
            return []
        try:
            items = json.loads(raw)
            return [int(i) for i in items if str(i).isdigit() or isinstance(i, int)]
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def _effort_label(self, effort) -> str:
        """TaskEffort → 사람이 읽기 좋은 레이블"""
        if isinstance(effort, TaskEffort):
            return {
                TaskEffort.SMALL: "small",
                TaskEffort.MEDIUM: "medium",
                TaskEffort.LARGE: "large",
            }.get(effort, "medium")
        try:
            return {1: "small", 2: "medium", 4: "large"}.get(int(effort), "medium")
        except (ValueError, TypeError):
            return "medium"

    async def _build_phase_milestone_index(
        self,
        storage: RoadmapStorage,
        project: str,
    ) -> dict[int, dict]:
        """milestone_id → {phase_name, milestone_name} 인덱스 구성"""
        index: dict[int, dict] = {}
        try:
            phases = await storage.get_phases(project)
            for phase in phases:
                if phase.id is None:
                    continue
                milestones = await storage.get_milestones(phase.id)
                for ms in milestones:
                    if ms.id is None:
                        continue
                    index[ms.id] = {
                        "phase_name": phase.name,
                        "milestone_name": ms.name,
                    }
        except Exception:
            pass
        return index
