"""
Daily Updater — 일일 커밋 → Task 매칭 업데이터

오늘(또는 지정일) 커밋을 기존 Task와 매칭하여 상태를 자동 업데이트합니다.
매칭 전략: 레포 일치 + 커밋 메시지 키워드 유사도 + Conventional Commit scope.
"""

import json
import re
from datetime import datetime
from pathlib import Path

# 3-way import — roadmap 모델/스토리지
try:
    from scripts.work_tracker.roadmap.models import (
        RoadmapTask, TaskStatus,
    )
    from scripts.work_tracker.roadmap.storage import RoadmapStorage
except ImportError:
    try:
        from work_tracker.roadmap.models import (
            RoadmapTask, TaskStatus,
        )
        from work_tracker.roadmap.storage import RoadmapStorage
    except ImportError:
        from .models import (
            RoadmapTask, TaskStatus,
        )
        from .storage import RoadmapStorage

# 3-way import — 기존 work_tracker 스토리지 (커밋 데이터 조회)
try:
    from scripts.work_tracker.storage import WorkTrackerStorage
except ImportError:
    try:
        from work_tracker.storage import WorkTrackerStorage
    except ImportError:
        from ..storage import WorkTrackerStorage


class DailyUpdater:
    """일일 커밋 → Task 매칭 업데이터"""

    # Conventional Commit scope 추출 정규식
    _SCOPE_RE = re.compile(r"^\w+\(([^)]+)\)")

    # 매칭에 제외할 짧은 불용어
    _STOP_WORDS = frozenset({
        "fix", "add", "update", "change", "remove", "refactor",
        "feat", "docs", "test", "chore", "style", "perf",
        "and", "the", "a", "an", "in", "on", "of", "to", "for",
        "수정", "추가", "변경", "삭제", "리팩토링", "개선",
    })

    def __init__(self):
        self._repo_mapping = self._load_repo_mapping()

    def _load_repo_mapping(self) -> dict:
        """projects.json에서 local_repo_mapping 로드"""
        config_path = Path(r"C:\claude\secretary\config\projects.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("local_repo_mapping", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _get_project_repos(self, project: str) -> list[str]:
        """프로젝트에 속한 레포명 리스트"""
        return [
            name
            for name, info in self._repo_mapping.items()
            if info.get("project", "").lower() == project.lower()
        ]

    def _tokenize(self, text: str) -> set[str]:
        """텍스트를 소문자 토큰 집합으로 변환 (불용어 제거)"""
        tokens = re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())
        return {t for t in tokens if len(t) > 1 and t not in self._STOP_WORDS}

    def _extract_scope(self, commit_msg: str) -> str | None:
        """Conventional Commit scope 추출: feat(ebs): ... → 'ebs'"""
        m = self._SCOPE_RE.match(commit_msg.strip())
        return m.group(1).strip() if m else None

    def _match_commit_to_task(
        self,
        commit_msg: str,
        commit_repo: str,
        tasks: list[RoadmapTask],
    ) -> RoadmapTask | None:
        """커밋과 가장 관련성 높은 Task 찾기

        매칭 점수:
        - repo 일치: +3점
        - 제목 키워드 2개+ 매칭: +5점
        - 제목 키워드 1개 매칭: +2점
        - scope 일치 (related_repo 또는 scope 포함): +2점

        최고 점수 Task 반환 (3점 미만이면 None)
        """
        commit_tokens = self._tokenize(commit_msg)
        commit_scope = self._extract_scope(commit_msg)
        best_task: RoadmapTask | None = None
        best_score = 0

        for task in tasks:
            score = 0

            # repo 일치
            if task.related_repo and task.related_repo == commit_repo:
                score += 3

            # 제목 키워드 매칭
            task_tokens = self._tokenize(task.title)
            overlap = commit_tokens & task_tokens
            if len(overlap) >= 2:
                score += 5
            elif len(overlap) == 1:
                score += 2

            # scope 일치
            if commit_scope:
                scope_lower = commit_scope.lower()
                if task.related_repo and scope_lower in task.related_repo.lower():
                    score += 2
                elif scope_lower in task.title.lower():
                    score += 2

            if score > best_score:
                best_score = score
                best_task = task

        return best_task if best_score >= 3 else None

    async def update(self, project: str, date: str | None = None) -> dict:
        """오늘(또는 지정일) 커밋을 Task와 매칭하여 상태 업데이트

        흐름:
        1. WorkTrackerStorage에서 해당 날짜 커밋 조회
        2. RoadmapStorage에서 pending/in_progress Task 조회
        3. 커밋-Task 매칭 수행
        4. 매칭된 Task 상태 업데이트 (pending→in_progress, feat→done 등)
        5. 통계 반환

        반환: {"matched": N, "updated": N, "new_commits": N}
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        stats = {"matched": 0, "updated": 0, "new_commits": 0, "date": target_date}

        # Step 1: 해당 날짜 커밋 조회
        commits = await self._load_commits(project, target_date)
        stats["new_commits"] = len(commits)

        if not commits:
            print(f"[DailyUpdater] {target_date}: 커밋 없음 (project={project})")
            return stats

        print(f"[DailyUpdater] {target_date}: {len(commits)}건 커밋 처리 시작")

        # Step 2: 활성 Task 조회
        async with RoadmapStorage() as storage:
            pending_tasks = await storage.get_tasks_by_project(project, status="pending")
            in_progress_tasks = await storage.get_tasks_by_project(project, status="in_progress")
            active_tasks = pending_tasks + in_progress_tasks

            if not active_tasks:
                print(f"[DailyUpdater] 활성 Task 없음 (project={project})")
                return stats

            # Step 3: 커밋-Task 매칭
            for commit in commits:
                commit_msg = commit.get("message", "")
                commit_repo = commit.get("repo", "")
                commit_type = commit.get("commit_type", "")

                matched_task = self._match_commit_to_task(
                    commit_msg, commit_repo, active_tasks
                )

                if matched_task is None or matched_task.id is None:
                    continue

                stats["matched"] += 1

                # Step 4: 상태 업데이트
                new_status = self._determine_new_status(
                    matched_task.status, commit_type, commit_msg
                )

                if new_status != matched_task.status:
                    completed_date = (
                        target_date if new_status == TaskStatus.DONE else None
                    )
                    await storage.update_task_status(
                        matched_task.id, new_status, completed_date
                    )
                    stats["updated"] += 1
                    print(
                        f"   Task 업데이트: '{matched_task.title[:50]}' "
                        f"{matched_task.status.value} → {new_status.value}"
                    )

                    # active_tasks 내 상태 동기화 (중복 업데이트 방지)
                    for t in active_tasks:
                        if t.id == matched_task.id:
                            t.status = new_status
                            break

        print(
            f"[DailyUpdater] 완료: 매칭 {stats['matched']}건, "
            f"업데이트 {stats['updated']}건"
        )
        return stats

    def _determine_new_status(
        self,
        current_status: TaskStatus,
        commit_type: str,
        commit_msg: str,
    ) -> TaskStatus:
        """커밋 타입/메시지 기반으로 새 Task 상태 결정

        규칙:
        - fix/feat 타입 커밋: 완료 가능성 높음 → done
        - chore/docs/test 타입: 진행 중 → in_progress
        - 메시지에 "완료", "done", "finish" 포함 → done
        - 그 외: pending → in_progress (첫 번째 관련 커밋 감지)
        """
        commit_type_lower = (commit_type or "").lower()
        msg_lower = commit_msg.lower()

        # 완료 키워드
        done_keywords = ["완료", "done", "finish", "complete", "closes", "fix"]
        if any(kw in msg_lower for kw in done_keywords):
            return TaskStatus.DONE

        # feat/fix 타입은 완료로 간주
        if commit_type_lower in ("feat", "fix"):
            return TaskStatus.DONE

        # 그 외 커밋은 진행 중으로 전환
        if current_status == TaskStatus.PENDING:
            return TaskStatus.IN_PROGRESS

        return current_status

    async def _load_commits(self, project: str, date: str) -> list[dict]:
        """WorkTrackerStorage에서 해당 프로젝트/날짜 커밋 조회

        WorkTrackerStorage가 없거나 DB에 데이터가 없으면 빈 리스트 반환.
        """
        try:
            async with WorkTrackerStorage() as wt_storage:
                commits_raw = await wt_storage.get_commits_by_date(date)
                # 프로젝트 필터링
                project_repos = set(self._get_project_repos(project))
                return [
                    {
                        "repo": c.repo,
                        "message": c.message,
                        "commit_type": c.commit_type.value if c.commit_type else "",
                        "commit_scope": c.commit_scope,
                        "hash": c.commit_hash,
                    }
                    for c in commits_raw
                    if c.repo in project_repos
                ]
        except Exception as exc:
            print(f"[DailyUpdater] WorkTrackerStorage 조회 실패: {exc}")
            return []
