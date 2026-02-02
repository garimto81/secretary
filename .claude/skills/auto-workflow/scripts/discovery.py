"""
Discovery Layer - 5계층 우선순위 작업 발견 시스템

5-Tier Priority System:
- Tier 0: Context 관리 (90%+ Emergency, 80%+ Warning)
- Tier 1: 명시적 지시 (사용자 요청)
- Tier 2: 긴급 (테스트 실패, 린트 에러 10+, 빌드 실패, 보안 취약점)
- Tier 3: 작업 처리 (변경 100줄+, 열린 이슈, PR 대기)
- Tier 4: 개발 지원 (새 기능 요청, 코드 분석, 복잡한 디버깅)
- Tier 5: 자율 발견 (품질, 커버리지, 문서화, 리팩토링, 의존성, 성능)
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, List, Dict
import subprocess
import json
import os
from pathlib import Path


class Tier(IntEnum):
    """작업 우선순위 계층"""
    CONTEXT = 0      # Context 관리 (최우선)
    EXPLICIT = 1     # 명시적 지시
    URGENT = 2       # 긴급 작업
    WORK = 3         # 작업 처리
    SUPPORT = 4      # 개발 지원
    AUTONOMOUS = 5   # 자율 발견


@dataclass
class DiscoveredTask:
    """발견된 작업 정보"""
    tier: Tier
    command: str
    description: str
    omc_agent: Optional[str] = None
    priority: float = 1.0
    metadata: Optional[Dict] = None

    def __repr__(self) -> str:
        agent_info = f" (agent: {self.omc_agent})" if self.omc_agent else ""
        return f"[T{self.tier}] {self.command}: {self.description}{agent_info} (priority={self.priority:.1f})"


class DiscoveryEngine:
    """작업 발견 엔진"""

    def __init__(
        self,
        context_usage: float = 0.0,
        user_request: Optional[str] = None,
        workspace: str = "C:\\claude"
    ):
        """
        Args:
            context_usage: Context 사용률 (0.0 ~ 100.0)
            user_request: 사용자 요청 문자열
            workspace: 작업 디렉토리 경로
        """
        self.context_usage = context_usage
        self.user_request = user_request
        self.workspace = Path(workspace)

    def discover(self) -> Optional[DiscoveredTask]:
        """5계층 우선순위로 다음 작업 발견"""
        # Tier 0: Context 관리 (최우선)
        task = self._check_tier0_context()
        if task:
            return task

        # Tier 1: 명시적 지시
        task = self._check_tier1_explicit()
        if task:
            return task

        # Tier 2: 긴급 작업
        task = self._check_tier2_urgent()
        if task:
            return task

        # Tier 3: 작업 처리
        task = self._check_tier3_work()
        if task:
            return task

        # Tier 4: 개발 지원
        task = self._check_tier4_support()
        if task:
            return task

        # Tier 5: 자율 발견
        task = self._check_tier5_autonomous()
        if task:
            return task

        return None

    # ==================== Tier 0: Context 관리 ====================

    def _check_tier0_context(self) -> Optional[DiscoveredTask]:
        """Tier 0: Context 사용률 기반 관리"""
        if self.context_usage >= 90:
            return DiscoveredTask(
                tier=Tier.CONTEXT,
                command="checkpoint",
                description="Context 90%+ Emergency: checkpoint + clear",
                priority=100.0,
                metadata={"usage": self.context_usage}
            )

        if self.context_usage >= 80:
            return DiscoveredTask(
                tier=Tier.CONTEXT,
                command="checkpoint",
                description="Context 80%+ Warning: checkpoint recommended",
                priority=90.0,
                metadata={"usage": self.context_usage}
            )

        return None

    # ==================== Tier 1: 명시적 지시 ====================

    def _check_tier1_explicit(self) -> Optional[DiscoveredTask]:
        """Tier 1: 사용자 요청 분석"""
        if not self.user_request:
            return None

        req = self.user_request.lower()

        # 명시적 커맨드 매핑
        command_map = {
            "debug": ("/debug", "Debug 요청", "oh-my-claudecode:architect"),
            "test": ("/tdd", "TDD 워크플로우", "oh-my-claudecode:tdd-guide"),
            "security": ("/check --security", "보안 검사", "oh-my-claudecode:security-reviewer"),
            "commit": ("/commit", "Commit 생성", None),
            "pr": ("/pr auto", "PR 생성", None),
            "issue": ("/issue fix", "이슈 처리", None),
            "research": ("/research", "Research 작업", "oh-my-claudecode:researcher"),
            "audit": ("/audit quick", "Quick Audit", "oh-my-claudecode:architect-low"),
        }

        for keyword, (cmd, desc, agent) in command_map.items():
            if keyword in req:
                return DiscoveredTask(
                    tier=Tier.EXPLICIT,
                    command=cmd,
                    description=f"사용자 요청: {desc}",
                    omc_agent=agent,
                    priority=95.0,
                    metadata={"request": self.user_request}
                )

        return None

    # ==================== Tier 2: 긴급 작업 ====================

    def _check_tier2_urgent(self) -> Optional[DiscoveredTask]:
        """Tier 2: 긴급 상황 감지"""
        # 2.1: 테스트 실패 확인
        task = self._check_test_failures()
        if task:
            return task

        # 2.2: 린트 에러 10+ 확인
        task = self._check_lint_errors()
        if task:
            return task

        # 2.3: 빌드 실패 확인
        task = self._check_build_failures()
        if task:
            return task

        # 2.4: 보안 취약점 확인
        task = self._check_security_issues()
        if task:
            return task

        return None

    def _check_test_failures(self) -> Optional[DiscoveredTask]:
        """테스트 실패 감지"""
        try:
            result = subprocess.run(
                ["pytest", "--collect-only", "-q"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )
            # pytest 수집 실패 시 긴급
            if result.returncode != 0:
                return DiscoveredTask(
                    tier=Tier.URGENT,
                    command="/debug",
                    description="테스트 수집 실패 감지",
                    omc_agent="oh-my-claudecode:architect",
                    priority=85.0,
                    metadata={"error": result.stderr[:200]}
                )
        except Exception:
            pass  # pytest 없으면 스킵

        return None

    def _check_lint_errors(self) -> Optional[DiscoveredTask]:
        """린트 에러 10+ 감지"""
        try:
            result = subprocess.run(
                ["ruff", "check", "src/", "--quiet"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                error_count = len(result.stdout.strip().split('\n')) if result.stdout else 0
                if error_count >= 10:
                    return DiscoveredTask(
                        tier=Tier.URGENT,
                        command="/check --fix",
                        description=f"린트 에러 {error_count}개 감지",
                        omc_agent="oh-my-claudecode:executor-low",
                        priority=80.0,
                        metadata={"error_count": error_count}
                    )
        except Exception:
            pass  # ruff 없으면 스킵

        return None

    def _check_build_failures(self) -> Optional[DiscoveredTask]:
        """빌드 실패 감지 (TypeScript)"""
        tsconfig = self.workspace / "tsconfig.json"
        if tsconfig.exists():
            try:
                result = subprocess.run(
                    ["tsc", "--noEmit"],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    return DiscoveredTask(
                        tier=Tier.URGENT,
                        command="/debug",
                        description="TypeScript 빌드 실패",
                        omc_agent="oh-my-claudecode:build-fixer",
                        priority=85.0,
                        metadata={"error": result.stderr[:200]}
                    )
            except Exception:
                pass

        return None

    def _check_security_issues(self) -> Optional[DiscoveredTask]:
        """보안 취약점 확인 (간단한 패턴 검사)"""
        # TODO: 실제 보안 스캐너 통합 (bandit, safety 등)
        # 여기서는 예시로 .env 파일 존재만 체크
        env_file = self.workspace / ".env"
        if env_file.exists():
            try:
                content = env_file.read_text(encoding="utf-8")
                if "API_KEY" in content or "SECRET" in content:
                    return DiscoveredTask(
                        tier=Tier.URGENT,
                        command="/check --security",
                        description="보안 취약점 가능성 감지 (.env 파일)",
                        omc_agent="oh-my-claudecode:security-reviewer",
                        priority=90.0,
                        metadata={"file": ".env"}
                    )
            except Exception:
                pass

        return None

    # ==================== Tier 3: 작업 처리 ====================

    def _check_tier3_work(self) -> Optional[DiscoveredTask]:
        """Tier 3: 작업 처리"""
        # 3.1: 변경 100줄+ 확인
        task = self._check_large_changes()
        if task:
            return task

        # 3.2: 열린 이슈 확인
        task = self._check_open_issues()
        if task:
            return task

        # 3.3: PR 대기 확인
        task = self._check_pending_pr()
        if task:
            return task

        return None

    def _check_large_changes(self) -> Optional[DiscoveredTask]:
        """100줄+ 변경사항 감지"""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                if lines:
                    # 마지막 줄에서 총 변경 라인 수 파싱
                    summary = lines[-1]
                    if "insertions" in summary or "deletions" in summary:
                        # 간단한 파싱: "N files changed, X insertions(+), Y deletions(-)"
                        parts = summary.split(',')
                        total_changes = 0
                        for part in parts:
                            if "insertion" in part or "deletion" in part:
                                num = ''.join(filter(str.isdigit, part))
                                if num:
                                    total_changes += int(num)

                        if total_changes >= 100:
                            return DiscoveredTask(
                                tier=Tier.WORK,
                                command="/commit",
                                description=f"{total_changes}줄 변경 감지 - 커밋 권장",
                                priority=70.0,
                                metadata={"lines_changed": total_changes}
                            )
        except Exception:
            pass

        return None

    def _check_open_issues(self) -> Optional[DiscoveredTask]:
        """열린 이슈 확인"""
        # TODO: GitHub API 연동
        # 여기서는 로컬 .omc/state/issues.json 체크
        issues_file = self.workspace / ".omc" / "state" / "issues.json"
        if issues_file.exists():
            try:
                with open(issues_file, 'r', encoding='utf-8') as f:
                    issues = json.load(f)
                if issues and len(issues) > 0:
                    return DiscoveredTask(
                        tier=Tier.WORK,
                        command="/issue fix",
                        description=f"{len(issues)}개 열린 이슈 발견",
                        omc_agent="oh-my-claudecode:executor",
                        priority=65.0,
                        metadata={"issue_count": len(issues)}
                    )
            except Exception:
                pass

        return None

    def _check_pending_pr(self) -> Optional[DiscoveredTask]:
        """PR 대기 확인"""
        # TODO: GitHub API 연동
        # 현재 브랜치가 main이 아니고 커밋이 있으면 PR 제안
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=5
            )
            if branch_result.returncode == 0:
                branch = branch_result.stdout.strip()
                if branch not in ("main", "master"):
                    return DiscoveredTask(
                        tier=Tier.WORK,
                        command="/pr auto",
                        description=f"브랜치 '{branch}'에서 PR 생성 가능",
                        priority=60.0,
                        metadata={"branch": branch}
                    )
        except Exception:
            pass

        return None

    # ==================== Tier 4: 개발 지원 ====================

    def _check_tier4_support(self) -> Optional[DiscoveredTask]:
        """Tier 4: 개발 지원"""
        # 4.1: 새 기능 요청
        if self.user_request and any(kw in self.user_request.lower() for kw in ["add", "create", "implement"]):
            return DiscoveredTask(
                tier=Tier.SUPPORT,
                command="/tdd",
                description="새 기능 구현 - TDD 워크플로우 권장",
                omc_agent="oh-my-claudecode:tdd-guide",
                priority=50.0
            )

        # 4.2: 코드 분석 요청
        if self.user_request and any(kw in self.user_request.lower() for kw in ["analyze", "explain", "understand"]):
            return DiscoveredTask(
                tier=Tier.SUPPORT,
                command="/research",
                description="코드 분석 작업",
                omc_agent="oh-my-claudecode:architect",
                priority=45.0
            )

        # 4.3: 복잡한 디버깅
        if self.user_request and any(kw in self.user_request.lower() for kw in ["why", "how", "trace"]):
            return DiscoveredTask(
                tier=Tier.SUPPORT,
                command="/debug",
                description="복잡한 디버깅 작업",
                omc_agent="oh-my-claudecode:architect",
                priority=55.0
            )

        return None

    # ==================== Tier 5: 자율 발견 ====================

    def _check_tier5_autonomous(self) -> Optional[DiscoveredTask]:
        """Tier 5: 자율 발견"""
        # 5.1: 테스트 커버리지 확인
        task = self._check_coverage()
        if task:
            return task

        # 5.2: 문서화 확인
        task = self._check_documentation()
        if task:
            return task

        # 5.3: 코드 품질 확인
        task = self._check_code_quality()
        if task:
            return task

        # 5.4: 의존성 업데이트 확인
        task = self._check_dependencies()
        if task:
            return task

        # 5.5: 리팩토링 기회
        task = self._check_refactoring()
        if task:
            return task

        return None

    def _check_coverage(self) -> Optional[DiscoveredTask]:
        """테스트 커버리지 확인"""
        coverage_file = self.workspace / ".coverage"
        if coverage_file.exists():
            # 간단한 체크: 커버리지 파일이 오래되었으면 재실행 제안
            import time
            age_seconds = time.time() - coverage_file.stat().st_mtime
            if age_seconds > 86400:  # 1일 이상
                return DiscoveredTask(
                    tier=Tier.AUTONOMOUS,
                    command="/tdd",
                    description="테스트 커버리지 업데이트 필요",
                    omc_agent="oh-my-claudecode:qa-tester",
                    priority=30.0,
                    metadata={"age_days": age_seconds / 86400}
                )

        return None

    def _check_documentation(self) -> Optional[DiscoveredTask]:
        """문서화 확인"""
        readme = self.workspace / "README.md"
        if not readme.exists():
            return DiscoveredTask(
                tier=Tier.AUTONOMOUS,
                command="/audit quick",
                description="README.md 누락",
                omc_agent="oh-my-claudecode:writer",
                priority=20.0
            )

        return None

    def _check_code_quality(self) -> Optional[DiscoveredTask]:
        """코드 품질 확인"""
        try:
            result = subprocess.run(
                ["ruff", "check", "src/", "--statistics"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                error_count = len(result.stdout.strip().split('\n')) if result.stdout else 0
                if 0 < error_count < 10:  # 10개 미만은 자율 발견
                    return DiscoveredTask(
                        tier=Tier.AUTONOMOUS,
                        command="/check --fix",
                        description=f"코드 품질 개선 가능 ({error_count}개 이슈)",
                        omc_agent="oh-my-claudecode:executor-low",
                        priority=25.0,
                        metadata={"error_count": error_count}
                    )
        except Exception:
            pass

        return None

    def _check_dependencies(self) -> Optional[DiscoveredTask]:
        """의존성 업데이트 확인"""
        # Python requirements.txt 확인
        requirements = self.workspace / "requirements.txt"
        if requirements.exists():
            import time
            age_seconds = time.time() - requirements.stat().st_mtime
            if age_seconds > 2592000:  # 30일 이상
                return DiscoveredTask(
                    tier=Tier.AUTONOMOUS,
                    command="/audit quick",
                    description="의존성 업데이트 확인 권장",
                    priority=15.0,
                    metadata={"age_days": age_seconds / 86400}
                )

        return None

    def _check_refactoring(self) -> Optional[DiscoveredTask]:
        """리팩토링 기회 확인"""
        # 간단한 휴리스틱: 100줄 이상 함수 찾기
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", "^def ", "src/"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=5
            )
            # TODO: 실제로는 AST 분석 필요
            # 여기서는 단순히 함수 개수만 체크
            if result.returncode == 0:
                function_count = len(result.stdout.strip().split('\n'))
                if function_count > 100:
                    return DiscoveredTask(
                        tier=Tier.AUTONOMOUS,
                        command="/research",
                        description="리팩토링 기회 분석 권장",
                        omc_agent="oh-my-claudecode:architect",
                        priority=10.0,
                        metadata={"function_count": function_count}
                    )
        except Exception:
            pass

        return None


# ==================== 테스트 및 데모 ====================

def demo():
    """Discovery Engine 데모"""
    print("=== Discovery Engine Demo ===\n")

    # 시나리오 1: Context Emergency
    print("1. Context Emergency (90%+)")
    engine = DiscoveryEngine(context_usage=92.0)
    task = engine.discover()
    print(f"   {task}\n")

    # 시나리오 2: 명시적 요청
    print("2. 명시적 요청 (debug)")
    engine = DiscoveryEngine(context_usage=40.0, user_request="debug this error")
    task = engine.discover()
    print(f"   {task}\n")

    # 시나리오 3: 자율 발견
    print("3. 자율 발견 (문서 없음)")
    engine = DiscoveryEngine(context_usage=30.0)
    task = engine.discover()
    print(f"   {task}\n")

    # 시나리오 4: 작업 없음
    print("4. 작업 없음")
    engine = DiscoveryEngine(context_usage=20.0, workspace="C:\\claude\\nonexistent")
    task = engine.discover()
    print(f"   {task}\n")


if __name__ == "__main__":
    demo()
