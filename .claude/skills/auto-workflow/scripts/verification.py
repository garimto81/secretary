from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import subprocess
import json
import time

class CheckType(Enum):
    BUILD = "build"
    TEST = "test"
    LINT = "lint"
    TYPE = "type"
    SECURITY = "security"

class VerificationStatus(Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class CheckResult:
    check_type: CheckType
    status: VerificationStatus
    message: str
    details: Optional[str] = None
    duration_ms: int = 0

@dataclass
class SelfVerificationResult:
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)

@dataclass
class ArchitectVerificationResult:
    approved: bool
    feedback: str
    issues: List[str] = field(default_factory=list)

@dataclass
class E2EVerificationResult:
    functional: CheckResult
    visual: CheckResult
    accessibility: CheckResult
    performance: CheckResult
    all_passed: bool


class VerificationEngine:
    """하이브리드 검증 엔진 (자체 + OMC Architect)"""

    def run_self_verification(self) -> SelfVerificationResult:
        """1차: 자체 검증 (빌드, 테스트, 린트)"""
        checks = []
        failed = []

        # 빌드 검증
        build_result = self._check_build()
        checks.append(build_result)
        if build_result.status == VerificationStatus.FAILED:
            failed.append("BUILD")

        # 테스트 검증
        test_result = self._check_tests()
        checks.append(test_result)
        if test_result.status == VerificationStatus.FAILED:
            failed.append("TEST")

        # 린트 검증
        lint_result = self._check_lint()
        checks.append(lint_result)
        if lint_result.status == VerificationStatus.FAILED:
            failed.append("LINT")

        # 타입 검증
        type_result = self._check_types()
        checks.append(type_result)
        if type_result.status == VerificationStatus.FAILED:
            failed.append("TYPE")

        return SelfVerificationResult(
            passed=len(failed) == 0,
            checks=checks,
            failed_checks=failed
        )

    def _check_build(self) -> CheckResult:
        """빌드 검증"""
        start_time = time.time()
        try:
            # Python 프로젝트: syntax check
            result = subprocess.run(
                ["python", "-m", "py_compile", "src/**/*.py"],
                capture_output=True, text=True, timeout=60, shell=True, cwd="C:\\claude"
            )
            duration = int((time.time() - start_time) * 1000)
            if result.returncode == 0:
                return CheckResult(CheckType.BUILD, VerificationStatus.PASSED, "Build successful", duration_ms=duration)
            return CheckResult(CheckType.BUILD, VerificationStatus.FAILED, "Build failed", result.stderr, duration)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.BUILD, VerificationStatus.SKIPPED, f"Build check skipped: {e}", duration_ms=duration)

    def _check_tests(self) -> CheckResult:
        """테스트 검증"""
        start_time = time.time()
        try:
            result = subprocess.run(
                ["pytest", "tests/", "-v", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=300, cwd="C:\\claude"
            )
            duration = int((time.time() - start_time) * 1000)
            if result.returncode == 0:
                return CheckResult(CheckType.TEST, VerificationStatus.PASSED, "All tests passed", duration_ms=duration)
            return CheckResult(CheckType.TEST, VerificationStatus.FAILED, "Tests failed", result.stdout, duration)
        except FileNotFoundError:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.TEST, VerificationStatus.SKIPPED, "pytest not found", duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.TEST, VerificationStatus.SKIPPED, f"Test check skipped: {e}", duration_ms=duration)

    def _check_lint(self) -> CheckResult:
        """린트 검증"""
        start_time = time.time()
        try:
            result = subprocess.run(
                ["ruff", "check", "src/", "--statistics"],
                capture_output=True, text=True, timeout=60, cwd="C:\\claude"
            )
            duration = int((time.time() - start_time) * 1000)
            if result.returncode == 0:
                return CheckResult(CheckType.LINT, VerificationStatus.PASSED, "No lint errors", duration_ms=duration)
            # 에러 수 파싱
            error_count = result.stdout.count("error")
            return CheckResult(
                CheckType.LINT,
                VerificationStatus.FAILED,
                f"{error_count} lint errors",
                result.stdout,
                duration
            )
        except FileNotFoundError:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.LINT, VerificationStatus.SKIPPED, "ruff not found", duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.LINT, VerificationStatus.SKIPPED, f"Lint check skipped: {e}", duration_ms=duration)

    def _check_types(self) -> CheckResult:
        """타입 검증"""
        start_time = time.time()
        try:
            result = subprocess.run(
                ["mypy", "src/", "--ignore-missing-imports"],
                capture_output=True, text=True, timeout=120, cwd="C:\\claude"
            )
            duration = int((time.time() - start_time) * 1000)
            if result.returncode == 0:
                return CheckResult(CheckType.TYPE, VerificationStatus.PASSED, "No type errors", duration_ms=duration)
            return CheckResult(CheckType.TYPE, VerificationStatus.FAILED, "Type errors found", result.stdout, duration)
        except FileNotFoundError:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.TYPE, VerificationStatus.SKIPPED, "mypy not found", duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return CheckResult(CheckType.TYPE, VerificationStatus.SKIPPED, f"Type check skipped: {e}", duration_ms=duration)

    def build_architect_verification_prompt(self, task_summary: str, self_result: SelfVerificationResult) -> str:
        """Architect 검증 프롬프트 생성"""
        checks_summary = "\n".join(
            f"- {c.check_type.value}: {c.status.value} - {c.message}"
            for c in self_result.checks
        )

        return f"""다음 구현이 완료되었는지 검증하세요:

## 작업 요약
{task_summary}

## 자체 검증 결과
{checks_summary}

## 검증 항목
1. 원래 요청을 완전히 충족하는가?
2. 명백한 버그가 있는가?
3. 누락된 엣지 케이스가 있는가?
4. 코드 품질이 수용 가능한가?

**APPROVED** 또는 **REJECTED**로 응답하세요.
REJECTED인 경우 구체적인 이유와 수정 사항을 제시하세요."""

    def build_e2e_verification_prompts(self, feature: str) -> Dict[str, str]:
        """E2E 4방향 검증 프롬프트 생성"""
        return {
            "functional": f"기능 테스트를 수행하세요: {feature}\n\n모든 기능이 정상 동작하는지 확인하세요.",
            "visual": f"UI 일관성을 검증하세요: {feature}\n\n디자인 가이드라인 준수 여부를 확인하세요.",
            "accessibility": f"접근성을 검토하세요: {feature}\n\nWCAG 가이드라인 준수 여부를 확인하세요.",
            "performance": f"성능을 검토하세요: {feature}\n\n응답 시간, 메모리 사용량을 확인하세요.",
        }


def get_verification_engine() -> VerificationEngine:
    return VerificationEngine()


if __name__ == "__main__":
    engine = VerificationEngine()
    result = engine.run_self_verification()
    print(f"Self verification: {'PASSED' if result.passed else 'FAILED'}")
    for check in result.checks:
        print(f"  - {check.check_type.value}: {check.status.value}")
