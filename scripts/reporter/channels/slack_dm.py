"""
Slack DM 채널 - lib.slack을 통한 DM 전송
"""

import logging

logger = logging.getLogger(__name__)


class SlackDMChannel:
    """Slack DM 전송 채널"""

    def __init__(self, user_id: str):
        """
        Args:
            user_id: Slack 사용자 ID (DM 대상)
        """
        self.user_id = user_id
        self._client = None
        self._dm_channel_id: str | None = None

    async def connect(self) -> bool:
        """Slack 클라이언트 초기화"""
        try:
            from lib.slack import SlackClient
            self._client = SlackClient()
            if not self._client.validate_token():
                logger.error("Slack 토큰 검증 실패")
                return False

            # DM 채널 열기
            self._dm_channel_id = self._client.open_dm(self.user_id)
            if not self._dm_channel_id:
                logger.error(f"DM 채널 열기 실패: user_id={self.user_id}")
                return False

            logger.info(f"Slack DM 채널 연결: user={self.user_id}, channel={self._dm_channel_id}")
            return True
        except ImportError:
            logger.error("lib.slack 모듈을 찾을 수 없습니다")
            return False
        except Exception as e:
            logger.error(f"Slack DM 연결 실패: {e}")
            return False

    async def send(self, text: str) -> bool:
        """
        Slack DM 전송

        Args:
            text: 전송할 메시지 (Slack mrkdwn 포맷)

        Returns:
            전송 성공 여부
        """
        if not self._client or not self._dm_channel_id:
            logger.warning("Slack DM 미연결 상태에서 전송 시도")
            return False

        try:
            result = self._client.send_message(
                channel=self._dm_channel_id,
                text=text,
            )
            return result is not None
        except Exception as e:
            logger.error(f"Slack DM 전송 실패: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        """연결 상태"""
        return self._client is not None and self._dm_channel_id is not None
