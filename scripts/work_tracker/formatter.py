"""
Slack mrkdwn 포맷터

DailySummary / WeeklySummary / DailyCommit / WorkStream 데이터를
Slack mrkdwn 형식의 문자열로 변환한다.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime

from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    DailySummary,
    StreamStatus,
    WeeklySummary,
    WorkStream,
)


class SlackFormatter:
    """Slack mrkdwn 포맷터"""

    # 프로젝트별 아이콘
    PROJECT_ICONS: dict[str, str] = {
        "EBS": ":briefcase:",
        "WSOPTV": ":tv:",
        "Secretary": ":robot_face:",
    }
    DEFAULT_ICON = ":package:"

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def format_daily(
        self,
        summary: DailySummary,
        commits: list[DailyCommit],
        streams: list[WorkStream],
    ) -> str:
        """일일 요약 Slack mrkdwn 포맷"""
        weekday = self._weekday_korean(summary.date)
        lines: list[str] = []

        # 헤더
        lines.append(f":memo: *일일 업무 현황* — {summary.date} ({weekday})")
        lines.append("")

        # 성과 섹션
        lines.append("*:chart_with_upwards_trend: 오늘의 성과*")
        if summary.total_commits == 0:
            lines.append("• 오늘 커밋 없음")
        else:
            dist = summary.project_distribution or {}
            dist_parts = " / ".join(
                f"{proj} {cnt}" for proj, cnt in dist.items() if cnt > 0
            )
            commit_line = f"• 커밋: {summary.total_commits}"
            if dist_parts:
                commit_line += f" ({dist_parts})"
            lines.append(commit_line)
            lines.append(
                f"• 변경: +{summary.total_insertions} / -{summary.total_deletions} lines"
            )
            ratio = round(summary.doc_change_ratio * 100, 1)
            lines.append(f"• 문서 비율: {ratio}%")
        lines.append("")

        # 프로젝트별 커밋 그룹핑
        if commits:
            grouped = self._group_commits_by_project(commits)
            for project, repos in grouped.items():
                icon = self.PROJECT_ICONS.get(project, self.DEFAULT_ICON)
                lines.append(f"*{icon} {project}*")
                for repo, repo_commits in repos.items():
                    summary_text = self._summarize_repo_commits(repo_commits)
                    lines.append(
                        f"• `{repo}` — {summary_text} ({len(repo_commits)} commits)"
                    )
                lines.append("")

        # 활성 Work Stream 섹션
        active_streams = [
            s
            for s in streams
            if s.status in (StreamStatus.ACTIVE, StreamStatus.NEW)
        ]
        if active_streams:
            lines.append("*:dart: 활성 Work Stream*")
            for stream in active_streams:
                status_text = self._format_stream_status(stream)
                lines.append(
                    f"• {stream.name} ({stream.duration_days}일째, {status_text})"
                )
        else:
            lines.append("*:dart: 활성 Work Stream*")
            lines.append("• 활성 스트림 없음")

        return "\n".join(lines).rstrip()

    def format_weekly(
        self,
        summary: WeeklySummary,
        streams: list[WorkStream],
    ) -> str:
        """주간 롤업 Slack mrkdwn 포맷"""
        lines: list[str] = []

        # 헤더
        lines.append(f":bar_chart: *주간 업무 롤업* — {summary.week_label}")
        lines.append("")

        # Velocity 섹션
        lines.append("*:chart_with_upwards_trend: Velocity*")
        if summary.velocity_trend:
            lines.append(self._velocity_bar_chart(summary.velocity_trend))
        else:
            lines.append("• 데이터 없음")
        lines.append("")

        # 프로젝트별 섹션
        lines.append("*:briefcase: 프로젝트별*")
        dist = summary.project_distribution or {}
        if dist:
            items = list(dist.items())
            for i, (proj, cnt) in enumerate(items):
                # 마지막 항목에 전주 대비 증감 표시 시도
                change_str = ""
                if summary.velocity_trend and len(summary.velocity_trend) >= 2:
                    weeks = list(summary.velocity_trend.keys())
                    vals = list(summary.velocity_trend.values())
                    if len(vals) >= 2:
                        diff = vals[-1] - vals[-2]
                        sign = "+" if diff >= 0 else ""
                        last_week = weeks[-2] if len(weeks) >= 2 else "이전 주"
                        change_str = f" ({sign}{diff} vs {last_week})"
                lines.append(f"• {proj}: {cnt} commits{change_str if i == len(items) - 1 else ''}")
        else:
            lines.append("• 데이터 없음")
        lines.append("")

        # 완료 Stream
        completed = [s for s in streams if s.status == StreamStatus.COMPLETED]
        if completed:
            lines.append("*:checkered_flag: 완료 Stream*")
            for stream in completed:
                lines.append(
                    f"• {stream.name} ({stream.duration_days}일, {stream.total_commits} commits)"
                )
            lines.append("")

        # 진행 중 Stream
        active = [
            s
            for s in streams
            if s.status in (StreamStatus.ACTIVE, StreamStatus.NEW)
        ]
        if active:
            lines.append("*:construction: 진행 중 Stream*")
            for stream in active:
                lines.append(f"• {stream.name} ({stream.duration_days}일째)")
            lines.append("")

        # Idle Stream
        idle = [s for s in streams if s.status == StreamStatus.IDLE]
        if idle:
            lines.append("*:chart_with_downwards_trend: Idle Stream (7일+ 미활동)*")
            for stream in idle:
                last_date = stream.last_commit[:10] if stream.last_commit else "알 수 없음"
                lines.append(f"• {stream.name} (마지막: {last_date})")

        return "\n".join(lines).rstrip()

    def format_json(
        self,
        summary: DailySummary | WeeklySummary,
        commits: list[DailyCommit] | None = None,
        streams: list[WorkStream] | None = None,
    ) -> str:
        """JSON 형식 출력 (--json 옵션용)"""
        data: dict = {"summary": summary.to_dict()}
        if commits is not None:
            data["commits"] = [c.to_dict() for c in commits]
        if streams is not None:
            data["streams"] = [s.to_dict() for s in streams]
        return json.dumps(data, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _velocity_bar_chart(self, velocity: dict[str, int]) -> str:
        """Velocity 바 차트 생성 (최대값 기준 10칸 정규화)

        W9:  ██████░░░░ 28
        W10: ████████░░ 35
        W11: █████████░ 42
        W12: ██████████ 48  ↑14%

        채움: █ (U+2588), 빈칸: ░ (U+2591)
        """
        if not velocity:
            return ""

        items = list(velocity.items())
        max_val = max(v for _, v in items) if items else 1
        if max_val == 0:
            max_val = 1

        # 레이블 최대 길이 (정렬용)
        max_label_len = max(len(label) for label, _ in items)

        chart_lines: list[str] = []
        for i, (label, val) in enumerate(items):
            filled = round((val / max_val) * 10)
            bar = "█" * filled + "░" * (10 - filled)
            padded_label = label.ljust(max_label_len)

            # 마지막 주에 전주 대비 증감율 표시
            suffix = ""
            if i == len(items) - 1 and i > 0:
                prev_val = items[i - 1][1]
                if prev_val > 0:
                    pct = round((val - prev_val) / prev_val * 100)
                    arrow = "↑" if pct >= 0 else "↓"
                    suffix = f"  {arrow}{abs(pct)}%"

            chart_lines.append(f"{padded_label}: {bar} {val}{suffix}")

        return "\n".join(chart_lines)

    def _group_commits_by_project(
        self, commits: list[DailyCommit]
    ) -> dict[str, dict[str, list[DailyCommit]]]:
        """프로젝트 → 레포 → 커밋 그룹핑"""
        result: dict[str, dict[str, list[DailyCommit]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for commit in commits:
            result[commit.project][commit.repo].append(commit)
        # defaultdict → 일반 dict으로 변환
        return {proj: dict(repos) for proj, repos in result.items()}

    def _summarize_repo_commits(self, commits: list[DailyCommit]) -> str:
        """레포 커밋 요약 (가장 많은 commit_type의 scope/message 기반)"""
        if not commits:
            return "커밋 없음"

        # 가장 많은 commit_type 추출
        type_counter: Counter[CommitType] = Counter(c.commit_type for c in commits)
        dominant_type, _ = type_counter.most_common(1)[0]

        # dominant_type의 커밋들 중 scope 또는 message 사용
        dominant_commits = [c for c in commits if c.commit_type == dominant_type]

        # scope가 있는 경우 scope 기반 요약
        scopes = [c.commit_scope for c in dominant_commits if c.commit_scope]
        if scopes:
            unique_scopes = list(dict.fromkeys(scopes))  # 순서 유지 중복 제거
            scope_str = ", ".join(unique_scopes[:3])
            if len(unique_scopes) > 3:
                scope_str += f" 외 {len(unique_scopes) - 3}개"
            return f"{dominant_type.value}({scope_str})"

        # scope 없으면 첫 커밋 메시지 사용
        first_msg = dominant_commits[0].message
        if len(first_msg) > 40:
            first_msg = first_msg[:40] + "…"
        return f"{dominant_type.value}: {first_msg}"

    def _format_stream_status(self, stream: WorkStream) -> str:
        """Stream 상태 한글 텍스트"""
        status_map = {
            StreamStatus.NEW: "신규",
            StreamStatus.ACTIVE: "진행 중",
            StreamStatus.IDLE: "미활동",
            StreamStatus.COMPLETED: "완료",
        }
        return status_map.get(stream.status, stream.status.value)

    def _weekday_korean(self, date_str: str) -> str:
        """요일 한글 변환: 0=월, 1=화, ..., 6=일"""
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return weekdays[dt.weekday()]
        except ValueError:
            return ""
