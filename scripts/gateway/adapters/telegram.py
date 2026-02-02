"""
Telegram Bot API Adapter

Telegram Bot API를 통한 메시지 수신/발신 어댑터.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, List, Set

# Telegram 라이브러리 (선택적 import)
try:
    from telegram import Update, Bot
    from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None
    Bot = None
    Application = None

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import NormalizedMessage, OutboundMessage, ChannelType, MessageType
    from scripts.gateway.adapters.base import ChannelAdapter, SendResult
except ImportError:
    try:
        from gateway.models import NormalizedMessage, OutboundMessage, ChannelType, MessageType
        from gateway.adapters.base import ChannelAdapter, SendResult
    except ImportError:
        from ..models import NormalizedMessage, OutboundMessage, ChannelType, MessageType
        from .base import ChannelAdapter, SendResult


logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    """
    Telegram Bot API 어댑터

    python-telegram-bot 라이브러리를 사용하여 메시지 수신/발신 구현.

    Config:
        bot_token: Telegram Bot Token (BotFather로 생성)
        allowed_users: 허용된 사용자 ID 목록 (빈 리스트면 모든 사용자 허용)
        webhook_url: 웹훅 URL (선택, polling 대신 사용)

    Example:
        >>> config = {
        ...     "bot_token": "123456:ABC-DEF...",
        ...     "allowed_users": [12345678, 87654321],
        ... }
        >>> adapter = TelegramAdapter(config)
        >>> await adapter.connect()
        >>> async for message in adapter.listen():
        ...     print(message.text)
    """

    def __init__(self, config: dict):
        """
        어댑터 초기화

        Args:
            config: 설정 딕셔너리
                - bot_token: Telegram Bot Token
                - allowed_users: 허용된 사용자 ID 목록
                - webhook_url: 웹훅 URL (선택)
        """
        super().__init__(config)
        self.channel_type = ChannelType.TELEGRAM

        # 설정 추출
        self.bot_token = config.get("bot_token", "")
        self.allowed_users: Set[int] = set(config.get("allowed_users", []))
        self.webhook_url = config.get("webhook_url")

        # 내부 상태
        self._application: Optional["Application"] = None
        self._bot: Optional["Bot"] = None
        self._message_queue: asyncio.Queue[NormalizedMessage] = asyncio.Queue()
        self._listen_task: Optional[asyncio.Task] = None
        self._running = False

        # 초안 저장 경로
        self._draft_dir = Path(config.get("draft_dir", r"C:\claude\secretary\output\drafts\telegram"))

    def _check_telegram_available(self) -> bool:
        """Telegram 라이브러리 사용 가능 여부 확인"""
        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot 라이브러리가 설치되지 않았습니다. pip install python-telegram-bot>=21.0")
            return False
        return True

    def _is_user_allowed(self, user_id: int) -> bool:
        """
        사용자 허용 여부 확인

        Args:
            user_id: Telegram 사용자 ID

        Returns:
            허용 여부 (allowed_users가 비어있으면 모든 사용자 허용)
        """
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    async def connect(self) -> bool:
        """
        Telegram Bot 연결

        Returns:
            연결 성공 여부
        """
        if not self._check_telegram_available():
            return False

        if not self.bot_token:
            logger.error("Telegram bot_token이 설정되지 않았습니다")
            return False

        try:
            # Application 빌드
            self._application = Application.builder().token(self.bot_token).build()
            self._bot = self._application.bot

            # 메시지 핸들러 등록
            self._application.add_handler(
                MessageHandler(filters.ALL, self._handle_message)
            )

            # Application 초기화
            await self._application.initialize()

            # Bot 정보 확인
            bot_info = await self._bot.get_me()
            logger.info(f"Telegram Bot 연결 성공: @{bot_info.username}")

            self._connected = True
            return True

        except Exception as e:
            logger.error(f"Telegram Bot 연결 실패: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Telegram Bot 연결 해제"""
        self._running = False

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._application:
            try:
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                logger.warning(f"Application 종료 중 오류: {e}")
            self._application = None

        self._bot = None
        self._connected = False
        logger.info("Telegram Bot 연결 해제됨")

    async def _handle_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """
        수신 메시지 처리 (내부 핸들러)

        Args:
            update: Telegram Update 객체
            context: Handler context
        """
        if not update.message:
            return

        message = update.message
        user = message.from_user

        if not user:
            return

        # 사용자 허용 확인
        if not self._is_user_allowed(user.id):
            logger.warning(f"허용되지 않은 사용자: {user.id} ({user.username})")
            return

        # NormalizedMessage로 변환
        normalized = self._telegram_to_normalized(update)

        # 큐에 추가
        await self._message_queue.put(normalized)
        logger.debug(f"메시지 수신: {normalized.id} from {normalized.sender_name}")

    def _telegram_to_normalized(self, update: "Update") -> NormalizedMessage:
        """
        Telegram Update를 NormalizedMessage로 변환

        Args:
            update: Telegram Update 객체

        Returns:
            NormalizedMessage
        """
        message = update.message
        user = message.from_user
        chat = message.chat

        # 메시지 타입 결정
        message_type = MessageType.TEXT
        media_urls: List[str] = []
        text = message.text or message.caption or ""

        if message.photo:
            message_type = MessageType.IMAGE
            # 가장 큰 사이즈의 사진 URL (file_id만 저장)
            media_urls = [message.photo[-1].file_id]
        elif message.document:
            message_type = MessageType.FILE
            media_urls = [message.document.file_id]
        elif message.voice:
            message_type = MessageType.VOICE
            media_urls = [message.voice.file_id]
        elif message.location:
            message_type = MessageType.LOCATION
            text = f"위치: {message.location.latitude}, {message.location.longitude}"

        # 멘션 확인 (봇 멘션 또는 reply)
        is_mention = False
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    is_mention = True
                    break

        # 원본 JSON (디버깅용)
        try:
            raw_json = json.dumps(update.to_dict(), ensure_ascii=False, default=str)
        except Exception:
            raw_json = None

        return NormalizedMessage(
            id=str(message.message_id),
            channel=ChannelType.TELEGRAM,
            channel_id=str(chat.id),
            sender_id=str(user.id),
            sender_name=user.full_name or user.username or str(user.id),
            text=text,
            message_type=message_type,
            timestamp=message.date or datetime.now(),
            is_group=chat.type in ("group", "supergroup"),
            is_mention=is_mention,
            reply_to_id=str(message.reply_to_message.message_id) if message.reply_to_message else None,
            media_urls=media_urls,
            raw_json=raw_json,
        )

    async def listen(self) -> AsyncIterator[NormalizedMessage]:
        """
        메시지 수신 (비동기 제너레이터)

        polling 방식으로 Telegram 서버에서 메시지 수신.

        Yields:
            NormalizedMessage: 정규화된 메시지
        """
        if not self._connected:
            logger.error("연결되지 않은 상태에서 listen 호출")
            return

        self._running = True

        # Polling 시작 (별도 태스크로)
        async def start_polling():
            try:
                await self._application.start()
                await self._application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=["message"]
                )
                # Polling 유지
                while self._running:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Polling 오류: {e}")
                self._running = False

        self._listen_task = asyncio.create_task(start_polling())

        # 메시지 큐에서 yield
        try:
            while self._running:
                try:
                    # 타임아웃을 두어 주기적으로 running 상태 확인
                    message = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=1.0
                    )
                    yield message
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
        finally:
            self._running = False

    async def send(self, message: OutboundMessage) -> SendResult:
        """
        메시지 전송

        confirmed=True일 때만 실제 전송, False면 초안만 생성.

        Args:
            message: 발신 메시지

        Returns:
            SendResult: 전송 결과
        """
        if not self._bot:
            return SendResult(
                success=False,
                error="Bot이 연결되지 않았습니다"
            )

        # 확인 없이 전송하면 초안만 생성
        if not message.confirmed:
            return await self._save_draft(message)

        try:
            # 실제 전송
            chat_id = message.to
            reply_to = int(message.reply_to) if message.reply_to else None

            sent_message = await self._bot.send_message(
                chat_id=chat_id,
                text=message.text,
                reply_to_message_id=reply_to,
            )

            logger.info(f"Telegram 메시지 전송 완료: {sent_message.message_id}")

            return SendResult(
                success=True,
                message_id=str(sent_message.message_id),
                sent_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Telegram 메시지 전송 실패: {e}")
            return SendResult(
                success=False,
                error=str(e)
            )

    async def _save_draft(self, message: OutboundMessage) -> SendResult:
        """
        초안 저장

        Args:
            message: 발신 메시지

        Returns:
            SendResult: 저장 결과
        """
        try:
            # 디렉토리 생성
            self._draft_dir.mkdir(parents=True, exist_ok=True)

            # 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            draft_path = self._draft_dir / f"draft_{message.to}_{timestamp}.json"

            # 초안 저장
            draft_data = {
                "channel": message.channel.value,
                "to": message.to,
                "text": message.text,
                "reply_to": message.reply_to,
                "created_at": datetime.now().isoformat(),
            }

            draft_path.write_text(
                json.dumps(draft_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            logger.info(f"Telegram 초안 저장: {draft_path}")

            return SendResult(
                success=True,
                draft_path=str(draft_path),
            )

        except Exception as e:
            logger.error(f"Telegram 초안 저장 실패: {e}")
            return SendResult(
                success=False,
                error=str(e)
            )

    async def get_status(self) -> dict:
        """
        어댑터 상태 반환

        Returns:
            상태 딕셔너리
        """
        status = {
            "connected": self._connected,
            "channel": self.channel_type.value,
            "running": self._running,
            "queue_size": self._message_queue.qsize(),
            "allowed_users_count": len(self.allowed_users),
        }

        if self._bot and self._connected:
            try:
                bot_info = await self._bot.get_me()
                status["bot_username"] = f"@{bot_info.username}"
                status["bot_id"] = bot_info.id
            except Exception as e:
                status["bot_error"] = str(e)

        return status


class MockTelegramAdapter(TelegramAdapter):
    """
    테스트용 Mock Telegram 어댑터

    실제 Telegram API 호출 없이 동작 테스트.
    """

    def __init__(self, config: dict):
        # 부모 __init__의 telegram import 체크를 우회
        ChannelAdapter.__init__(self, config)
        self.channel_type = ChannelType.TELEGRAM

        self.bot_token = config.get("bot_token", "mock_token")
        self.allowed_users: Set[int] = set(config.get("allowed_users", []))

        self._message_queue: asyncio.Queue[NormalizedMessage] = asyncio.Queue()
        self._running = False
        self._draft_dir = Path(config.get("draft_dir", r"C:\claude\secretary\output\drafts\telegram"))

        # Mock 전용
        self._sent_messages: List[OutboundMessage] = []
        self._mock_messages: List[NormalizedMessage] = []

    def _check_telegram_available(self) -> bool:
        """Mock은 항상 True"""
        return True

    async def connect(self) -> bool:
        """Mock 연결"""
        if not self.bot_token:
            return False
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Mock 연결 해제"""
        self._running = False
        self._connected = False

    async def listen(self) -> AsyncIterator[NormalizedMessage]:
        """Mock 메시지 수신"""
        if not self._connected:
            return

        self._running = True

        # Mock 메시지 먼저 yield
        for msg in self._mock_messages:
            if self._running:
                yield msg

        # 큐에서 추가 메시지 yield
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=0.1
                )
                yield message
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def send(self, message: OutboundMessage) -> SendResult:
        """Mock 메시지 전송"""
        if not self._connected:
            return SendResult(success=False, error="Not connected")

        if not message.confirmed:
            return await self._save_draft(message)

        self._sent_messages.append(message)

        return SendResult(
            success=True,
            message_id=f"mock_{len(self._sent_messages)}",
            sent_at=datetime.now(),
        )

    async def get_status(self) -> dict:
        """Mock 상태"""
        return {
            "connected": self._connected,
            "channel": self.channel_type.value,
            "running": self._running,
            "queue_size": self._message_queue.qsize(),
            "allowed_users_count": len(self.allowed_users),
            "sent_count": len(self._sent_messages),
            "bot_username": "@mock_bot",
        }

    def add_mock_message(self, message: NormalizedMessage) -> None:
        """테스트용 Mock 메시지 추가"""
        self._mock_messages.append(message)

    async def inject_message(self, message: NormalizedMessage) -> None:
        """실행 중 메시지 주입"""
        await self._message_queue.put(message)
