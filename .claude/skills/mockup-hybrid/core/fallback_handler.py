"""
폴백 핸들러

Stitch API 실패 시 HTML로 자동 폴백을 처리합니다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from lib.mockup_hybrid import MockupBackend, MockupOptions


@dataclass
class FallbackDecision:
    """폴백 결정"""
    should_fallback: bool
    fallback_backend: Optional[MockupBackend]
    reason: str


class FallbackHandler:
    """폴백 핸들러"""

    def __init__(self, rules_path: Optional[Path] = None):
        """
        폴백 핸들러 초기화

        Args:
            rules_path: 선택 규칙 YAML 파일 경로
        """
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "config" / "selection_rules.yaml"

        self.rules = self._load_rules(rules_path)

    def _load_rules(self, path: Path) -> dict:
        """선택 규칙 로드"""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        else:
            return {
                "fallback": {
                    "enabled": True,
                    "from": "stitch",
                    "to": "html",
                    "reason": "Stitch 실패 → HTML 폴백",
                }
            }

    def handle_failure(
        self,
        original_backend: MockupBackend,
        error_message: Optional[str],
        prompt: str,
        options: MockupOptions,
    ) -> FallbackDecision:
        """
        실패 처리 및 폴백 결정

        Args:
            original_backend: 원래 선택된 백엔드
            error_message: 에러 메시지
            prompt: 사용자 프롬프트
            options: 목업 옵션

        Returns:
            FallbackDecision 객체
        """
        fallback_config = self.rules.get("fallback", {})

        # 폴백 비활성화 확인
        if not fallback_config.get("enabled", True):
            return FallbackDecision(
                should_fallback=False,
                fallback_backend=None,
                reason="폴백이 비활성화되어 있습니다.",
            )

        # 폴백 대상 확인
        from_backend = fallback_config.get("from", "stitch")
        if original_backend.value != from_backend:
            return FallbackDecision(
                should_fallback=False,
                fallback_backend=None,
                reason=f"{original_backend.value}는 폴백 대상이 아닙니다.",
            )

        # 강제 옵션 확인 (--force-hifi 시 폴백 불가)
        if options.force_hifi:
            return FallbackDecision(
                should_fallback=False,
                fallback_backend=None,
                reason="--force-hifi 옵션으로 폴백이 비활성화됩니다.",
            )

        # 폴백 결정
        to_backend = fallback_config.get("to", "html")
        fallback_reason = fallback_config.get("reason", "자동 폴백")

        return FallbackDecision(
            should_fallback=True,
            fallback_backend=MockupBackend(to_backend),
            reason=fallback_reason,
        )

    def should_retry(
        self,
        error_message: Optional[str],
        attempt_count: int,
        max_retries: int = 2,
    ) -> bool:
        """
        재시도 여부 결정

        Args:
            error_message: 에러 메시지
            attempt_count: 현재 시도 횟수
            max_retries: 최대 재시도 횟수

        Returns:
            재시도 여부
        """
        if attempt_count >= max_retries:
            return False

        # Rate limit 에러는 재시도하지 않음
        if error_message and "rate" in error_message.lower():
            return False

        # 네트워크 에러는 재시도
        if error_message and any(
            k in error_message.lower()
            for k in ["timeout", "connection", "network"]
        ):
            return True

        return False

    def log_fallback(
        self,
        original_backend: MockupBackend,
        fallback_backend: MockupBackend,
        error_message: Optional[str],
        prompt: str,
    ) -> None:
        """
        폴백 로그 기록

        Args:
            original_backend: 원래 백엔드
            fallback_backend: 폴백 백엔드
            error_message: 에러 메시지
            prompt: 프롬프트
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.warning(
            f"폴백 발생: {original_backend.value} → {fallback_backend.value}\n"
            f"  에러: {error_message}\n"
            f"  프롬프트: {prompt[:50]}..."
        )
