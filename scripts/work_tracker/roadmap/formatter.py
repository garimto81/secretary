"""
Roadmap 포맷터 — Mermaid Gantt + ASCII 테이블 + Slack mrkdwn

DB에 저장된 Phase/Milestone/Task 데이터를 다양한 형식으로 변환한다.
"""

from __future__ import annotations

try:
    from scripts.work_tracker.roadmap.models import (
        RoadmapPhase, RoadmapMilestone, RoadmapTask,
        PhaseStatus, MilestoneStatus, TaskStatus,
    )
    from scripts.work_tracker.roadmap.storage import RoadmapStorage
except ImportError:
    try:
        from work_tracker.roadmap.models import (
            RoadmapPhase, RoadmapMilestone, RoadmapTask,
            PhaseStatus, MilestoneStatus, TaskStatus,
        )
        from work_tracker.roadmap.storage import RoadmapStorage
    except ImportError:
        from .models import (
            RoadmapPhase, RoadmapMilestone, RoadmapTask,
            PhaseStatus, MilestoneStatus, TaskStatus,
        )
        from .storage import RoadmapStorage


class RoadmapFormatter:
    """로드맵 보고서 포맷터 — Mermaid Gantt + ASCII + Slack"""

    # 상태별 Mermaid 표시 접두어
    STATUS_MAP = {
        TaskStatus.DONE: "done,",
        TaskStatus.IN_PROGRESS: "active,",
        TaskStatus.PENDING: "",
        TaskStatus.BLOCKED: "crit,",
    }

    # 마일스톤 상태별 Mermaid 표시
    MS_STATUS_MAP = {
        MilestoneStatus.COMPLETED: "done,",
        MilestoneStatus.ACTIVE: "active,",
        MilestoneStatus.PENDING: "",
    }

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def format_mermaid_gantt(self, project: str) -> str:
        """Mermaid Gantt 차트 생성

        DB에서 Phase/Milestone/Task를 읽어 Mermaid gantt 형식으로 변환한다.
        날짜가 없는 Task는 Gantt에서 제외된다.

        출력 예시:
            ```mermaid
            gantt
                title EBS 로드맵
                dateFormat YYYY-MM-DD
                axisFormat %m/%d

                section Phase 1-2 (2026)
                기획 확정     :done, 2026-01-26, 2026-02-09
                RFID POC     :active, 2026-03-19, 30d
            ```
        """
        async with RoadmapStorage() as storage:
            phases = await storage.get_phases(project)

            if not phases:
                return ""

            lines: list[str] = [
                "gantt",
                f"    title {project} 로드맵",
                "    dateFormat YYYY-MM-DD",
                "    axisFormat %m/%d",
                "",
            ]

            has_any_entry = False

            for phase in phases:
                milestones = await storage.get_milestones(phase.id)
                section_lines: list[str] = []

                for ms in milestones:
                    # 마일스톤에 날짜가 있으면 Gantt에 포함
                    if ms.target_date or ms.completed_date:
                        end_date = ms.completed_date or ms.target_date
                        # 시작일: target_date 기준으로 milestone duration 추정 (없으면 end - 14d)
                        start_date = _estimate_start(ms.target_date, ms.completed_date)
                        if start_date:
                            status_prefix = self.MS_STATUS_MAP.get(ms.status, "")
                            safe_name = _safe_mermaid(ms.name)
                            entry = f"    {safe_name} :{status_prefix} {start_date}, {end_date}"
                            section_lines.append(entry)
                            has_any_entry = True
                            continue

                    # 마일스톤에 날짜 없으면 Task에서 날짜 추출
                    tasks = await storage.get_tasks(ms.id)
                    for task in tasks:
                        if task.completed_date:
                            status_prefix = self.STATUS_MAP.get(task.status, "")
                            safe_name = _safe_mermaid(task.title)
                            # 날짜를 단일 날짜 + 1d 로 처리
                            entry = f"    {safe_name} :{status_prefix} {task.completed_date}, 1d"
                            section_lines.append(entry)
                            has_any_entry = True

                if section_lines:
                    lines.append(f"    section {_safe_mermaid(phase.name)}")
                    lines.extend(section_lines)
                    lines.append("")

            if not has_any_entry:
                return ""

            return "\n".join(lines).rstrip()

    async def format_ascii_status(self, project: str) -> str:
        """ASCII 테이블 상태 요약 (터미널 출력용)

        출력 예시:
            === EBS 로드맵 현황 ===

            Phase 1-2: RFID POC + GFX [ACTIVE]
            ├─ 기획 확정 [COMPLETED] ━━━━━━━━━━ 3/3
            │  ✓ 마스터 기획서 v5.5 확정 (W5)
            ├─ RFID POC [ACTIVE] ━━━━━░░░░░ 0/2
            │  ○ RFID 12대 리더 연결
            └─ GFX 엔진 + UI 3종 [PENDING] ░░░░░░░░░░ 0/4
               ○ Console 구현 (6화면)

            전체: 20 tasks | ✓ 14 done | ● 2 진행 중 | ○ 4 대기
        """
        lines: list[str] = []
        total_done = 0
        total_in_progress = 0
        total_pending = 0
        total_blocked = 0

        async with RoadmapStorage() as storage:
            phases = await storage.get_phases(project)

            if not phases:
                return f"=== {project} 로드맵 ===\n\n데이터 없음. `roadmap init --project {project}` 실행 필요."

            lines.append(f"=== {project} 로드맵 현황 ===")

            for phase in phases:
                phase_status_label = _phase_status_label(phase.status)
                lines.append(f"\n{phase.name} [{phase_status_label}]")

                milestones = await storage.get_milestones(phase.id)

                for ms_idx, ms in enumerate(milestones):
                    is_last_ms = ms_idx == len(milestones) - 1
                    ms_prefix = "└─" if is_last_ms else "├─"
                    task_indent = "   " if is_last_ms else "│  "

                    tasks = await storage.get_tasks(ms.id)
                    done_count = sum(1 for t in tasks if t.status == TaskStatus.DONE)
                    total_count = len(tasks)

                    # 카운터 누적
                    for t in tasks:
                        if t.status == TaskStatus.DONE:
                            total_done += 1
                        elif t.status == TaskStatus.IN_PROGRESS:
                            total_in_progress += 1
                        elif t.status == TaskStatus.BLOCKED:
                            total_blocked += 1
                        else:
                            total_pending += 1

                    ms_status_label = _ms_status_label(ms.status)
                    bar = self._progress_bar(done_count, total_count)
                    lines.append(
                        f"{ms_prefix} {ms.name} [{ms_status_label}] {bar} {done_count}/{total_count}"
                    )

                    for task in tasks:
                        icon = self._status_icon(task.status.value)
                        week_suffix = f" ({task.completed_week})" if task.completed_week else ""
                        lines.append(f"{task_indent}{icon} {task.title}{week_suffix}")

        total_all = total_done + total_in_progress + total_pending + total_blocked
        lines.append(
            f"\n전체: {total_all} tasks | "
            f"✓ {total_done} done | "
            f"● {total_in_progress} 진행 중 | "
            f"○ {total_pending} 대기"
            + (f" | ✗ {total_blocked} 차단" if total_blocked > 0 else "")
        )

        return "\n".join(lines)

    async def format_slack(self, project: str) -> str:
        """Slack mrkdwn 형식 요약

        출력 예시:
            :briefcase: *EBS 로드맵 현황*

            *Phase 1-2: RFID POC + GFX* `ACTIVE`
            • 기획 확정: ✅ 완료 (3/3)
            • RFID POC: 🔵 진행 중 (0/2)
            • GFX 엔진 + UI 3종: ⬜ 대기 (0/4)

            _전체: 20 tasks | ✅ 14 done | 🔵 2 진행 중 | ⬜ 4 대기_
        """
        lines: list[str] = []
        project_icons = {
            "EBS": ":briefcase:",
            "WSOPTV": ":tv:",
            "Secretary": ":robot_face:",
        }
        icon = project_icons.get(project, ":package:")

        lines.append(f"{icon} *{project} 로드맵 현황*")

        total_done = 0
        total_in_progress = 0
        total_pending = 0
        total_blocked = 0

        async with RoadmapStorage() as storage:
            phases = await storage.get_phases(project)

            if not phases:
                lines.append("\n데이터 없음.")
                return "\n".join(lines)

            for phase in phases:
                phase_status_label = _phase_status_label(phase.status)
                lines.append(f"\n*{phase.name}* `{phase_status_label}`")

                milestones = await storage.get_milestones(phase.id)

                for ms in milestones:
                    tasks = await storage.get_tasks(ms.id)
                    done_count = sum(1 for t in tasks if t.status == TaskStatus.DONE)
                    total_count = len(tasks)

                    for t in tasks:
                        if t.status == TaskStatus.DONE:
                            total_done += 1
                        elif t.status == TaskStatus.IN_PROGRESS:
                            total_in_progress += 1
                        elif t.status == TaskStatus.BLOCKED:
                            total_blocked += 1
                        else:
                            total_pending += 1

                    ms_emoji = _ms_slack_emoji(ms.status)
                    ms_label = _ms_status_label(ms.status)
                    lines.append(f"• {ms.name}: {ms_emoji} {ms_label} ({done_count}/{total_count})")

        total_all = total_done + total_in_progress + total_pending + total_blocked
        summary = (
            f"_전체: {total_all} tasks | "
            f"✅ {total_done} done | "
            f"🔵 {total_in_progress} 진행 중 | "
            f"⬜ {total_pending} 대기"
        )
        if total_blocked > 0:
            summary += f" | 🚫 {total_blocked} 차단"
        summary += "_"
        lines.append(f"\n{summary}")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _progress_bar(self, done: int, total: int, width: int = 10) -> str:
        """Unicode 진행 바: ━━━━━━━░░░"""
        if total == 0:
            return "░" * width
        filled = int(done / total * width)
        return "━" * filled + "░" * (width - filled)

    def _status_icon(self, status: str) -> str:
        """상태별 아이콘"""
        icons = {
            "done": "✓",
            "in_progress": "●",
            "pending": "○",
            "blocked": "✗",
        }
        return icons.get(status, "?")


# -------------------------------------------------------------------------
# Module-level helpers
# -------------------------------------------------------------------------

def _safe_mermaid(text: str) -> str:
    """Mermaid 노드 레이블에서 콜론/세미콜론 이스케이프"""
    return text.replace(":", " ").replace(";", " ")


def _estimate_start(target_date: str | None, completed_date: str | None) -> str | None:
    """마일스톤 시작일 추정 — 완료일 또는 목표일에서 14일 전"""
    from datetime import datetime, timedelta

    ref = completed_date or target_date
    if not ref:
        return None
    try:
        dt = datetime.strptime(ref[:10], "%Y-%m-%d")
        start = dt - timedelta(days=14)
        return start.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _phase_status_label(status: PhaseStatus) -> str:
    labels = {
        PhaseStatus.PLANNED: "PLANNED",
        PhaseStatus.ACTIVE: "ACTIVE",
        PhaseStatus.COMPLETED: "COMPLETED",
    }
    return labels.get(status, status.value.upper())


def _ms_status_label(status: MilestoneStatus) -> str:
    labels = {
        MilestoneStatus.PENDING: "PENDING",
        MilestoneStatus.ACTIVE: "ACTIVE",
        MilestoneStatus.COMPLETED: "COMPLETED",
    }
    return labels.get(status, status.value.upper())


def _ms_slack_emoji(status: MilestoneStatus) -> str:
    emojis = {
        MilestoneStatus.COMPLETED: "✅",
        MilestoneStatus.ACTIVE: "🔵",
        MilestoneStatus.PENDING: "⬜",
    }
    return emojis.get(status, "❓")
