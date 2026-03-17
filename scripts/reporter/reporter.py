"""
SecretaryReporter - 보고 시스템 오케스트레이터

Slack DM으로:
1. 초안 생성 즉시 알림
2. 긴급 메시지 즉시 알림
3. 하루 1회 Digest 요약
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from .alert import DraftNotification, UrgentAlert
from .channels.slack_dm import SlackDMChannel
from .digest import DigestReport

logger = logging.getLogger(__name__)


class SecretaryReporter:
    """보고 시스템 오케스트레이터"""

    def __init__(
        self,
        gateway_storage=None,
        intel_storage=None,
        config: dict[str, Any] | None = None,
    ):
        """
        Args:
            gateway_storage: UnifiedStorage 인스턴스
            intel_storage: IntelligenceStorage 인스턴스
            config: reporter 설정 (gateway.json의 reporter 섹션)
        """
        self.gateway_storage = gateway_storage
        self.intel_storage = intel_storage
        self.config = config or {}

        self._digest = DigestReport(gateway_storage, intel_storage)
        self._slack_dm: SlackDMChannel | None = None
        self._digest_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Reporter 시작 (Digest 스케줄러 포함)"""
        if not self.config.get("enabled", False):
            logger.info("Reporter 비활성화됨")
            return

        # Slack DM 채널 초기화
        slack_config = self.config.get("channels", {}).get("slack_dm", {})
        if slack_config.get("enabled", False):
            user_id = slack_config.get("user_id", "")
            if user_id:
                self._slack_dm = SlackDMChannel(user_id)
                connected = await self._slack_dm.connect()
                if connected:
                    logger.info("Reporter: Slack DM 연결 성공")
                else:
                    logger.warning("Reporter: Slack DM 연결 실패, 알림 비활성화")
                    self._slack_dm = None
            else:
                logger.warning("Reporter: slack_dm.user_id 미설정")

        # Digest 스케줄러 시작
        digest_time = self.config.get("digest_time", "18:00")
        self._running = True
        self._digest_task = asyncio.create_task(
            self._digest_scheduler(digest_time)
        )

        logger.info(f"Reporter 시작 (digest: 매일 {digest_time})")

    async def stop(self) -> None:
        """Reporter 중지"""
        self._running = False
        if self._digest_task:
            self._digest_task.cancel()
            try:
                await self._digest_task
            except asyncio.CancelledError:
                pass
        logger.info("Reporter 중지")

    async def send_urgent_alert(self, alert: UrgentAlert) -> bool:
        """
        긴급 메시지 알림 전송

        Args:
            alert: 긴급 알림 데이터

        Returns:
            전송 성공 여부
        """
        if not self._slack_dm:
            return False

        try:
            return await self._slack_dm.send(alert.format_slack())
        except Exception as e:
            logger.error(f"긴급 알림 전송 실패: {e}")
            return False

    async def send_draft_notification(self, notification: DraftNotification) -> bool:
        """
        초안 생성 알림 전송

        Args:
            notification: 초안 알림 데이터

        Returns:
            전송 성공 여부
        """
        if not self._slack_dm:
            return False

        try:
            return await self._slack_dm.send(notification.format_slack())
        except Exception as e:
            logger.error(f"초안 알림 전송 실패: {e}")
            return False

    async def send_daily_digest(self, project_id: str | None = None) -> bool:
        """일일 Digest 전송 (project_id로 필터 가능)"""
        if not self._slack_dm:
            return False

        try:
            data = await self._digest.generate(project_id=project_id)
            text = self._digest.format_slack(data)
            return await self._slack_dm.send(text)
        except Exception as e:
            logger.error(f"Digest 전송 실패: {e}")
            return False

    async def send_work_summary(self, summary_data: dict, channel: str = "C0985UXQN6Q") -> bool:
        """Work Tracker 일일/주간 요약 Slack 전송

        Args:
            summary_data: format_daily() 또는 format_weekly()의 결과 텍스트 또는 dict
            channel: Slack 채널 ID (기본: claude-auto)

        Returns:
            전송 성공 여부
        """
        if not self._slack_dm:
            return False

        try:
            if isinstance(summary_data, dict):
                # dict인 경우 간단한 텍스트 변환
                text = summary_data.get("text", str(summary_data))
            else:
                text = str(summary_data)

            return await self._slack_dm.send(text)
        except Exception as e:
            logger.error(f"Work summary 전송 실패: {e}")
            return False

    async def _digest_scheduler(self, digest_time: str) -> None:
        """
        매일 지정 시간에 Digest 전송

        Args:
            digest_time: "HH:MM" 형식 (예: "18:00")
        """
        try:
            hour, minute = map(int, digest_time.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 18, 0

        while self._running:
            try:
                now = datetime.now()
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if target <= now:
                    target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()
                logger.debug(f"Digest 대기: {wait_seconds:.0f}초 ({target.isoformat()})")

                await asyncio.sleep(wait_seconds)

                if self._running:
                    await self.send_daily_digest()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Digest 스케줄러 오류: {e}")
                await asyncio.sleep(60)

    @property
    def is_active(self) -> bool:
        """활성 상태"""
        return self._running and self._slack_dm is not None
