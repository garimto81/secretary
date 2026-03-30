"""
Work Stream 감지 모듈

Git 커밋 목록에서 연속 업무 단위(Work Stream)를 자동으로 감지하고
기존 DB stream과 병합하여 상태를 관리합니다.
"""

import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 3-way import
try:
    from scripts.work_tracker.models import (
        DailyCommit,
        DetectionMethod,
        StreamStatus,
        WorkStream,
    )
    from scripts.work_tracker.storage import WorkTrackerStorage
except ImportError:
    try:
        from work_tracker.models import (
            DailyCommit,
            DetectionMethod,
            StreamStatus,
            WorkStream,
        )
        from work_tracker.storage import WorkTrackerStorage
    except ImportError:
        from .models import (
            DailyCommit,
            DetectionMethod,
            StreamStatus,
            WorkStream,
        )
        from .storage import WorkTrackerStorage

# 스킵할 브랜치명
_SKIP_BRANCHES = {"main", "master", "HEAD", "origin/main", "origin/master"}

# 브랜치 prefix 패턴
_BRANCH_PREFIXES = ("feat/", "fix/", "refactor/", "chore/", "docs/", "test/", "perf/")

# DetectionMethod 우선순위 (높을수록 우선)
_DETECTION_PRIORITY = {
    DetectionMethod.BRANCH: 4,
    DetectionMethod.SCOPE: 3,
    DetectionMethod.PATH: 2,
    DetectionMethod.KEYWORD: 1,
}


def _parse_iso(ts: str) -> datetime:
    """ISO 8601 문자열 → datetime (UTC-naive)"""
    # aiosqlite rows may have timezone suffix — strip it for simple comparison
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        # fallback: truncate to seconds
        return datetime.fromisoformat(ts[:19])


def _stream_key(stream: WorkStream) -> tuple[str, str]:
    return (stream.name.lower().strip(), stream.project.lower().strip())


class StreamDetector:
    """Git 커밋 목록에서 Work Stream을 감지하고 DB와 통합하는 클래스"""

    def __init__(self, storage: WorkTrackerStorage, ai_analyzer=None):
        self.storage = storage
        self.ai_analyzer = ai_analyzer  # WorkTrackerAIAnalyzer | None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect_streams(self, commits: list[DailyCommit]) -> list[WorkStream]:
        """커밋 목록에서 Work Stream 후보 감지 + 기존 stream과 병합.

        1. 3가지 규칙 기반 감지 메서드로 후보 수집
        2. AI 키워드 클러스터링으로 KEYWORD 후보 추가 (Gap 1)
        3. _merge_candidates로 중복 제거
        4. reconcile_with_existing으로 기존 stream 업데이트
        5. AI 스트림 명명 (Gap 4)
        6. update_stream_statuses로 상태 업데이트
        """
        if not commits:
            return []

        # 1. 규칙 기반 후보 수집
        candidates: list[WorkStream] = []
        candidates.extend(self._detect_by_branch(commits))
        candidates.extend(self._detect_by_scope(commits))
        candidates.extend(self._detect_by_path(commits))

        # 2. AI 키워드 클러스터링 (Gap 1, graceful degradation)
        if self.ai_analyzer:
            ai_streams = await self._detect_by_ai_keywords(commits)
            candidates.extend(ai_streams)

        if not candidates:
            return []

        # 3. 중복 제거
        merged = self._merge_candidates(candidates)

        # 4. 기존 DB stream과 통합
        reconciled = await self.reconcile_with_existing(merged)

        # 5. AI 스트림 명명 (Gap 4, graceful degradation)
        if self.ai_analyzer:
            await self._apply_ai_stream_names(reconciled)

        # 6. 상태 업데이트 — reference_date는 커밋 중 가장 최근 날짜
        reference_date = max(c.date for c in commits)
        return self.update_stream_statuses(reconciled, reference_date)

    async def _detect_by_ai_keywords(
        self, commits: list[DailyCommit]
    ) -> list[WorkStream]:
        """AI 키워드 클러스터링으로 KEYWORD 스트림 감지 (Gap 1)"""
        try:
            clusters = await self.ai_analyzer.cluster_keywords(commits)
            if not clusters:
                return []

            # commit_hash → commit 매핑
            hash_map = {c.commit_hash[:7]: c for c in commits}

            streams: list[WorkStream] = []
            for cluster_name, hashes in clusters.items():
                matched_commits = [
                    hash_map[h] for h in hashes if h in hash_map
                ]
                if len(matched_commits) < 2:
                    continue

                repos = sorted({c.repo for c in matched_commits})
                timestamps = [c.timestamp for c in matched_commits]
                project = matched_commits[0].project

                streams.append(
                    WorkStream(
                        name=cluster_name,
                        project=project,
                        repos=repos,
                        first_commit=min(timestamps),
                        last_commit=max(timestamps),
                        total_commits=len(matched_commits),
                        status=StreamStatus.NEW,
                        detection_method=DetectionMethod.KEYWORD,
                    )
                )
            return streams

        except Exception as e:
            logger.warning(f"AI keyword detection failed: {e}")
            return []

    async def _apply_ai_stream_names(
        self, streams: list[WorkStream]
    ) -> None:
        """AI 스트림 명명 적용 (Gap 4, in-place 수정)"""
        try:
            name_map = await self.ai_analyzer.generate_stream_names(streams)
            if not name_map:
                return

            for stream in streams:
                if stream.name in name_map:
                    new_name = name_map[stream.name]
                    if new_name and new_name.strip():
                        # metadata에 원래 이름 보존
                        if stream.metadata is None:
                            stream.metadata = {}
                        stream.metadata["original_name"] = stream.name
                        stream.name = new_name.strip()

        except Exception as e:
            logger.warning(f"AI stream naming failed: {e}")

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _detect_by_branch(self, commits: list[DailyCommit]) -> list[WorkStream]:
        """브랜치명 패턴 감지.

        feat/xxx, fix/xxx → stream name "xxx"
        같은 branch의 커밋을 그룹핑.
        detection_method = BRANCH
        """
        branch_groups: dict[tuple[str, str], list[DailyCommit]] = defaultdict(list)

        for commit in commits:
            branch = (commit.branch or "").strip()
            if not branch:
                continue
            # 스킵 대상 브랜치
            if branch in _SKIP_BRANCHES:
                continue
            # prefix 제거 → stream name 추출
            stream_name = None
            for prefix in _BRANCH_PREFIXES:
                if branch.lower().startswith(prefix):
                    stream_name = branch[len(prefix):]
                    break
            if stream_name is None:
                # prefix 없는 브랜치는 브랜치명 자체를 이름으로 사용
                # (단, main/master/HEAD 이미 스킵됨)
                stream_name = branch

            key = (stream_name, commit.project)
            branch_groups[key].append(commit)

        return self._groups_to_streams(branch_groups, DetectionMethod.BRANCH)

    def _detect_by_scope(self, commits: list[DailyCommit]) -> list[WorkStream]:
        """Conventional Commit scope 감지.

        commit_scope가 같은 커밋을 그룹핑.
        scope가 None 또는 빈 문자열 → 스킵.
        detection_method = SCOPE
        """
        scope_groups: dict[tuple[str, str], list[DailyCommit]] = defaultdict(list)

        for commit in commits:
            scope = (commit.commit_scope or "").strip()
            if not scope:
                continue
            key = (scope, commit.project)
            scope_groups[key].append(commit)

        return self._groups_to_streams(scope_groups, DetectionMethod.SCOPE)

    def _detect_by_path(self, commits: list[DailyCommit]) -> list[WorkStream]:
        """문서 경로 연속성 감지.

        같은 project 내에서 같은 repo의 커밋을 그룹핑.
        (scope/branch가 없는 커밋용 fallback)
        detection_method = PATH
        """
        # 이미 branch/scope로 감지된 커밋은 제외 (fallback 역할)
        path_groups: dict[tuple[str, str], list[DailyCommit]] = defaultdict(list)

        for commit in commits:
            # branch 또는 scope가 있으면 다른 method가 처리 → 스킵
            has_branch = bool((commit.branch or "").strip()) and (
                (commit.branch or "").strip() not in _SKIP_BRANCHES
            )
            has_scope = bool((commit.commit_scope or "").strip())
            if has_branch or has_scope:
                continue

            # repo 이름을 stream name으로 사용
            key = (commit.repo, commit.project)
            path_groups[key].append(commit)

        return self._groups_to_streams(path_groups, DetectionMethod.PATH)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _groups_to_streams(
        self,
        groups: dict[tuple[str, str], list[DailyCommit]],
        method: DetectionMethod,
    ) -> list[WorkStream]:
        """그룹핑된 커밋 딕셔너리 → WorkStream 리스트 변환"""
        streams: list[WorkStream] = []
        for (name, project), group_commits in groups.items():
            if not group_commits:
                continue
            repos = sorted({c.repo for c in group_commits})
            timestamps = [c.timestamp for c in group_commits]
            first = min(timestamps)
            last = max(timestamps)
            streams.append(
                WorkStream(
                    name=name,
                    project=project,
                    repos=repos,
                    first_commit=first,
                    last_commit=last,
                    total_commits=len(group_commits),
                    status=StreamStatus.NEW,
                    detection_method=method,
                )
            )
        return streams

    def _merge_candidates(self, candidates: list[WorkStream]) -> list[WorkStream]:
        """중복 후보 병합.

        project + repos 겹침 70%+ AND 이름 유사 → 같은 stream으로 병합.
        우선순위: BRANCH > SCOPE > PATH > KEYWORD
        병합 시 name은 우선순위 높은 것 사용.
        total_commits, repos, first/last_commit 합산.

        이름 유사 기준 (둘 중 하나 충족 시 병합 허용):
        - 이름이 동일 (case-insensitive)
        - 한 이름이 다른 이름의 부분 문자열 (e.g., "overlay" vs "overlay-analysis")
        - 두 이름 모두 같은 검출 방식으로 동일한 이름을 가지는 경우
        """
        if not candidates:
            return []

        # 우선순위 기준 정렬 (높은 순)
        sorted_candidates = sorted(
            candidates,
            key=lambda s: _DETECTION_PRIORITY.get(s.detection_method, 0),
            reverse=True,
        )

        merged: list[WorkStream] = []

        for candidate in sorted_candidates:
            matched = False
            for existing in merged:
                if existing.project != candidate.project:
                    continue
                # repos 겹침 계산
                set_a = set(existing.repos)
                set_b = set(candidate.repos)
                if not set_a and not set_b:
                    # 둘 다 비어있으면 name으로만 비교
                    if existing.name.lower() == candidate.name.lower():
                        matched = True
                        _absorb(existing, candidate)
                        break
                    continue
                denom = max(len(set_a), len(set_b))
                overlap = len(set_a & set_b) / denom if denom > 0 else 0.0
                if overlap >= 0.7 and _names_similar(existing.name, candidate.name):
                    matched = True
                    _absorb(existing, candidate)
                    break
            if not matched:
                # 깊은 복사 방지 — 새 객체로 추가
                merged.append(
                    WorkStream(
                        name=candidate.name,
                        project=candidate.project,
                        repos=list(candidate.repos),
                        first_commit=candidate.first_commit,
                        last_commit=candidate.last_commit,
                        total_commits=candidate.total_commits,
                        status=candidate.status,
                        detection_method=candidate.detection_method,
                        metadata=dict(candidate.metadata) if candidate.metadata else None,
                    )
                )

        return merged

    async def reconcile_with_existing(
        self, new_streams: list[WorkStream]
    ) -> list[WorkStream]:
        """기존 DB stream과 신규 감지 stream 통합.

        1. DB에서 기존 streams 로드
        2. 같은 name+project → 기존 stream에 last_commit, total_commits 업데이트
        3. 새로운 name+project → NEW status로 추가
        """
        existing_streams = await self.storage.get_streams()
        existing_index: dict[tuple[str, str], WorkStream] = {
            _stream_key(s): s for s in existing_streams
        }

        result: list[WorkStream] = []

        for new_s in new_streams:
            key = _stream_key(new_s)
            if key in existing_index:
                existing = existing_index[key]
                # 기존 stream 업데이트
                # last_commit: 더 최신인 것
                if new_s.last_commit > existing.last_commit:
                    existing.last_commit = new_s.last_commit
                # first_commit: 더 오래된 것
                if new_s.first_commit and (
                    not existing.first_commit or new_s.first_commit < existing.first_commit
                ):
                    existing.first_commit = new_s.first_commit
                # total_commits는 신규 감지 수만큼 더함
                # (중복 방지를 위해 단순히 max로 처리하는 것이 안전)
                existing.total_commits = max(
                    existing.total_commits, new_s.total_commits
                )
                # repos 합산
                existing.repos = sorted(set(existing.repos) | set(new_s.repos))
                result.append(existing)
                # 처리된 항목 제거 (남은 기존 stream 추적)
                del existing_index[key]
            else:
                # 신규 stream — NEW status
                new_s.status = StreamStatus.NEW
                result.append(new_s)

        # DB에만 있고 새로 감지되지 않은 기존 stream도 포함 (상태 갱신을 위해)
        for leftover in existing_index.values():
            result.append(leftover)

        return result

    def update_stream_statuses(
        self, streams: list[WorkStream], reference_date: str
    ) -> list[WorkStream]:
        """Stream 상태 업데이트.

        reference_date 기준:
        - last_commit이 오늘 && 이전에 없었음 → NEW
        - last_commit이 7일 이내 → ACTIVE
        - last_commit이 7~30일 → IDLE
        - last_commit이 30일+ → COMPLETED

        duration_days = (last_commit - first_commit).days + 1
        """
        try:
            ref_dt = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            # ISO 8601 timestamp 형식인 경우
            ref_dt = _parse_iso(reference_date).date()

        for stream in streams:
            # duration_days 계산
            if stream.first_commit and stream.last_commit:
                try:
                    first_dt = _parse_iso(stream.first_commit).date()
                    last_dt = _parse_iso(stream.last_commit).date()
                    stream.duration_days = (last_dt - first_dt).days + 1
                except (ValueError, AttributeError):
                    stream.duration_days = 1
            else:
                stream.duration_days = 1

            # 상태 업데이트 — NEW는 유지 (reconcile에서 이미 NEW로 설정됨)
            if stream.status == StreamStatus.NEW:
                # NEW는 그대로 유지
                pass
            else:
                # 기존 stream의 활동 여부 판단
                if stream.last_commit:
                    try:
                        last_dt = _parse_iso(stream.last_commit).date()
                        delta = (ref_dt - last_dt).days
                    except (ValueError, AttributeError):
                        delta = 0

                    if delta <= 7:
                        stream.status = StreamStatus.ACTIVE
                    elif delta <= 30:
                        stream.status = StreamStatus.IDLE
                    else:
                        stream.status = StreamStatus.COMPLETED

        return streams


def _names_similar(name_a: str, name_b: str) -> bool:
    """두 stream 이름이 같은 스트림을 나타내는지 판단.

    기준 (둘 중 하나 충족):
    - 이름이 동일 (case-insensitive)
    - 한 이름이 다른 이름의 부분 문자열 (e.g., "overlay" in "overlay-analysis")
    """
    a = name_a.lower().strip()
    b = name_b.lower().strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    return False


def _absorb(target: WorkStream, source: WorkStream) -> None:
    """source의 정보를 target에 병합.

    우선순위: target이 이미 높은 우선순위 → name 유지.
    repos, commits, 날짜 범위를 합산.
    """
    # repos 합산
    target.repos = sorted(set(target.repos) | set(source.repos))

    # total_commits 합산 (중복 커밋이 있을 수 있으므로 단순 합산은 과대평가 가능)
    # 스펙에 따라 합산
    target.total_commits += source.total_commits

    # first_commit: 더 오래된 것
    if source.first_commit and (
        not target.first_commit or source.first_commit < target.first_commit
    ):
        target.first_commit = source.first_commit

    # last_commit: 더 최신인 것
    if source.last_commit and (
        not target.last_commit or source.last_commit > target.last_commit
    ):
        target.last_commit = source.last_commit
