"""
ChannelWatcher - channels.json 변경 감지 → 새 채널 자동 처리

channels.json 파일을 주기적으로 폴링하여 새로운 채널이 추가되면
KnowledgeBootstrap → ChannelPRDWriter → ChannelSonnetProfiler 전체 파이프라인을 실행합니다.
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS_PATH = Path(r"C:\claude\secretary\config\channels.json")
DEFAULT_POLL_INTERVAL = 30  # 초


class ChannelWatcher:
    """channels.json 변경 감지 → 새 채널 자동 처리"""

    def __init__(
        self,
        channels_path: Path = DEFAULT_CHANNELS_PATH,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ):
        self.channels_path = channels_path
        self.poll_interval = poll_interval
        self._known_channel_ids: set[str] = set()
        self._channel_projects: dict[str, str] = {}  # channel_id → project_id
        self._running = False
        self._watch_task: asyncio.Task | None = None
        self._initialized = False

    async def start(self) -> None:
        """감시 시작 (백그라운드 태스크)"""
        if self._running:
            return
        self._running = True
        # 초기 채널 목록 로드 (처음엔 새 채널 트리거 안 함)
        self._known_channel_ids = self._load_channel_ids()
        self._initialized = True
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info(f"ChannelWatcher 시작: {len(self._known_channel_ids)}개 채널 감시 중")

    async def stop(self) -> None:
        """감시 중지"""
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
        logger.info("ChannelWatcher 중지됨")

    async def _watch_loop(self) -> None:
        """폴링 루프"""
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                current_ids = self._load_channel_ids()
                new_ids = current_ids - self._known_channel_ids
                if new_ids:
                    logger.info(f"새 채널 감지: {new_ids}")
                    for channel_id in new_ids:
                        asyncio.create_task(self._run_full_pipeline(channel_id))
                    self._known_channel_ids = current_ids
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ChannelWatcher 루프 오류: {e}")

    def _load_channel_ids(self) -> set[str]:
        """channels.json에서 채널 ID 목록 로드"""
        if not self.channels_path.exists():
            return set()
        try:
            data = json.loads(self.channels_path.read_text(encoding="utf-8"))
            # channels 배열 형식 또는 단순 ID 목록 모두 지원
            channels = data.get("channels", data if isinstance(data, list) else [])
            ids = set()
            for ch in channels:
                if isinstance(ch, dict):
                    ch_id = ch.get("id") or ch.get("channel_id")
                    project_id = ch.get("project_id", ch_id)
                elif isinstance(ch, str):
                    ch_id = ch
                    project_id = ch
                else:
                    continue
                if ch_id:
                    ids.add(ch_id)
                    self._channel_projects[ch_id] = project_id
            return ids
        except Exception as e:
            logger.error(f"channels.json 로드 실패: {e}")
            return set()

    async def _run_full_pipeline(self, channel_id: str) -> None:
        """새 채널 등록 시 전체 자동 처리 파이프라인"""
        print(f"\n[ChannelWatcher] 새 채널 감지: {channel_id}")
        print("[ChannelWatcher] 전체 파이프라인 시작...")

        try:
            # Step 1: KnowledgeBootstrap.run_mastery() — 전체 수집
            mastery_summary = await self._run_mastery(channel_id)
            print(f"[ChannelWatcher] Mastery 완료: {mastery_summary}")

            # Step 2: ChannelPRDWriter.write() — PRD 생성
            await self._write_prd(channel_id, mastery_summary)

            # Step 3: ChannelSonnetProfiler.build_profile() — AI 프로파일
            await self._build_profile(channel_id, mastery_summary)

        except Exception as e:
            logger.error(f"ChannelWatcher 파이프라인 실패 ({channel_id}): {e}")

    async def _run_mastery(self, channel_id: str) -> dict:
        """KnowledgeBootstrap.run_mastery() 실행"""
        import sys
        try:
            if r"C:\claude\secretary" not in sys.path:
                sys.path.insert(0, r"C:\claude\secretary")

            try:
                from scripts.knowledge.bootstrap import KnowledgeBootstrap
                from scripts.knowledge.store import KnowledgeStore
            except ImportError:
                from knowledge.bootstrap import KnowledgeBootstrap
                from knowledge.store import KnowledgeStore

            async with KnowledgeStore() as store:
                bootstrap = KnowledgeBootstrap(store)
                project_id = self._channel_projects.get(channel_id, channel_id)
                return await bootstrap.run_mastery(
                    project_id=project_id,
                    channel_id=channel_id,
                )
        except Exception as e:
            logger.error(f"run_mastery 실패 ({channel_id}): {e}")
            return {"channel_id": channel_id, "error": str(e)}

    async def _write_prd(self, channel_id: str, mastery_summary: dict) -> None:
        """ChannelPRDWriter.write() 실행"""
        try:
            try:
                from scripts.knowledge.channel_prd_writer import ChannelPRDWriter
            except ImportError:
                from knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            path = await writer.write(channel_id, mastery_summary)
            print(f"[ChannelWatcher] PRD 생성 완료: {path}")
        except Exception as e:
            logger.error(f"PRD 생성 실패 ({channel_id}): {e}")

    async def _build_profile(self, channel_id: str, mastery_summary: dict) -> None:
        """ChannelSonnetProfiler.build_profile() 실행"""
        try:
            try:
                from scripts.knowledge.channel_sonnet_profiler import ChannelSonnetProfiler
            except ImportError:
                from knowledge.channel_sonnet_profiler import ChannelSonnetProfiler

            profiler = ChannelSonnetProfiler()
            await profiler.build_profile(channel_id, mastery_summary, pinned_messages=[])
            print(f"[ChannelWatcher] AI 프로파일 생성 완료: {channel_id}")
        except Exception as e:
            logger.error(f"AI 프로파일 생성 실패 ({channel_id}): {e}")
