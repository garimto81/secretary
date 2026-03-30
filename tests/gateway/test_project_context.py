"""
ProjectContextResolver 테스트 + 프로젝트별 Pipeline 통합 테스트
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gateway.models import ChannelType, NormalizedMessage
from scripts.gateway.pipeline import MessagePipeline
from scripts.gateway.project_context import ProjectContextResolver
from scripts.gateway.storage import UnifiedStorage

# --- Fixtures ---

@pytest.fixture
def projects_config(tmp_path):
    """테스트용 projects.json 생성"""
    config = {
        "projects": [
            {
                "id": "secretary",
                "name": "Secretary AI",
                "slack_channels": ["C_SECRETARY"],
                "gmail_queries": ["subject:(secretary OR daily report)"],
                "keywords": ["secretary", "비서", "리포트"],
                "pipeline_config": {
                    "urgent_keywords": ["서버다운", "장애"],
                    "action_keywords": ["배포", "릴리즈"],
                    "notification_rules": {"toast_enabled": True},
                    "rate_limit_overrides": {},
                },
            },
            {
                "id": "wsoptv",
                "name": "WSOP TV",
                "slack_channels": ["C_WSOPTV"],
                "gmail_queries": ["subject:(wsop OR 방송)"],
                "keywords": ["wsop", "방송", "자막"],
                "pipeline_config": {
                    "urgent_keywords": ["방송사고", "송출"],
                    "action_keywords": ["인코딩", "업로드"],
                    "notification_rules": {"toast_enabled": False},
                    "rate_limit_overrides": {},
                },
            },
        ]
    }
    config_path = tmp_path / "projects.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return config_path


@pytest.fixture
def resolver(projects_config):
    return ProjectContextResolver(projects_config)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def storage(temp_db):
    return UnifiedStorage(temp_db)


# --- ProjectContextResolver 단위 테스트 ---

class TestProjectContextResolver:
    """ProjectContextResolver 단위 테스트"""

    def test_resolve_slack_channel(self, resolver):
        """Slack channel_id로 프로젝트 매칭"""
        msg = NormalizedMessage(
            id="t1", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
            sender_id="u1", text="hello",
        )
        assert resolver.resolve(msg) == "secretary"

    def test_resolve_slack_channel_wsoptv(self, resolver):
        """WSOPTV Slack 채널 매칭"""
        msg = NormalizedMessage(
            id="t2", channel=ChannelType.SLACK, channel_id="C_WSOPTV",
            sender_id="u1", text="hello",
        )
        assert resolver.resolve(msg) == "wsoptv"

    def test_resolve_email_pattern(self, resolver):
        """Email query 패턴 매칭"""
        msg = NormalizedMessage(
            id="t3", channel=ChannelType.EMAIL, channel_id="inbox",
            sender_id="u1", text="secretary 프로젝트 업데이트",
        )
        assert resolver.resolve(msg) == "secretary"

    def test_resolve_email_wsoptv(self, resolver):
        """Email WSOP 패턴 매칭"""
        msg = NormalizedMessage(
            id="t4", channel=ChannelType.EMAIL, channel_id="inbox",
            sender_id="u1", text="WSOP 방송 관련 문의",
        )
        assert resolver.resolve(msg) == "wsoptv"

    def test_resolve_keyword_fallback(self, resolver):
        """키워드 fallback으로 매칭"""
        msg = NormalizedMessage(
            id="t5", channel=ChannelType.SLACK, channel_id="C_UNKNOWN",
            sender_id="u1", text="자막 작업 진행 중",
        )
        assert resolver.resolve(msg) == "wsoptv"

    def test_resolve_no_match(self, resolver):
        """매칭 실패 시 None"""
        msg = NormalizedMessage(
            id="t6", channel=ChannelType.SLACK, channel_id="C_UNKNOWN",
            sender_id="u1", text="점심 뭐 먹을까",
        )
        assert resolver.resolve(msg) is None

    def test_get_context(self, resolver):
        """프로젝트 컨텍스트 조회"""
        ctx = resolver.get_context("secretary")
        assert ctx is not None
        assert ctx.project_id == "secretary"
        assert "서버다운" in ctx.urgent_keywords
        assert "배포" in ctx.action_keywords

    def test_get_context_not_found(self, resolver):
        """존재하지 않는 프로젝트"""
        assert resolver.get_context("nonexistent") is None

    def test_missing_config_file(self, tmp_path):
        """설정 파일 없을 때 빈 resolver"""
        r = ProjectContextResolver(tmp_path / "missing.json")
        msg = NormalizedMessage(
            id="t7", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
            sender_id="u1", text="test",
        )
        assert r.resolve(msg) is None


# --- 프로젝트별 Pipeline 통합 테스트 ---

class TestProjectAwarePipeline:
    """파이프라인의 프로젝트별 동작 테스트"""

    @pytest.mark.asyncio
    async def test_stage_0_5_resolves_project(self, storage, resolver):
        """Stage 0.5에서 project_id가 결정되어 결과에 포함"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)
            msg = NormalizedMessage(
                id="p1", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
                sender_id="u1", text="테스트 메시지",
            )
            result = await pipeline.process(msg)
            assert result.project_id == "secretary"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_project_specific_urgent_keyword(self, storage, resolver):
        """프로젝트별 긴급 키워드가 적용"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)

            # "서버다운"은 secretary 프로젝트의 긴급 키워드
            msg = NormalizedMessage(
                id="p2", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
                sender_id="u1", text="서버다운 발생했습니다",
            )
            result = await pipeline.process(msg)
            assert result.priority == "urgent"
            assert result.project_id == "secretary"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_project_specific_urgent_not_cross_applied(self, storage, resolver):
        """다른 프로젝트의 긴급 키워드는 적용되지 않음"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)

            # "방송사고"는 wsoptv의 긴급 키워드인데, secretary 채널에서는 적용 안됨
            msg = NormalizedMessage(
                id="p3", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
                sender_id="u1", text="방송사고 같은 건 없겠죠",
            )
            result = await pipeline.process(msg)
            # secretary 프로젝트에는 "방송사고"가 긴급 키워드가 아님
            assert result.priority == "normal"
            assert result.project_id == "secretary"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_wsoptv_urgent_keyword(self, storage, resolver):
        """WSOPTV 프로젝트의 긴급 키워드 적용"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)

            msg = NormalizedMessage(
                id="p4", channel=ChannelType.SLACK, channel_id="C_WSOPTV",
                sender_id="u1", text="방송사고 발생!",
            )
            result = await pipeline.process(msg)
            assert result.priority == "urgent"
            assert result.project_id == "wsoptv"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_project_specific_action_keyword(self, storage, resolver):
        """프로젝트별 액션 키워드 감지"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)

            msg = NormalizedMessage(
                id="p5", channel=ChannelType.SLACK, channel_id="C_SECRETARY",
                sender_id="u1", text="v2.0 배포 준비 완료",
            )
            result = await pipeline.process(msg)
            assert result.has_action
            assert any("배포" in a for a in result.actions)
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_no_project_uses_defaults(self, storage, resolver):
        """프로젝트 매칭 안될 때 기본 키워드만 사용"""
        await storage.connect()
        try:
            pipeline = MessagePipeline(storage, project_resolver=resolver)

            msg = NormalizedMessage(
                id="p6", channel=ChannelType.SLACK, channel_id="C_UNKNOWN",
                sender_id="u1", text="긴급! 확인 필요",
            )
            result = await pipeline.process(msg)
            # "긴급"은 기본 urgent 키워드
            assert result.priority == "urgent"
            assert result.project_id is None
        finally:
            await storage.close()


# --- Storage project_id 테스트 ---

class TestStorageProjectId:
    """Storage의 project_id 컬럼 테스트"""

    @pytest.mark.asyncio
    async def test_save_with_project_id(self, storage):
        """project_id와 함께 메시지 저장"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="s1", channel=ChannelType.SLACK, channel_id="C_TEST",
                sender_id="u1", text="test",
            )
            await storage.save_message(msg, project_id="secretary")

            saved = await storage.get_message("s1")
            assert saved is not None
            assert saved.project_id == "secretary"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_save_without_project_id(self, storage):
        """project_id 없이 저장 (NULL)"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="s2", channel=ChannelType.SLACK, channel_id="C_TEST",
                sender_id="u1", text="test",
            )
            await storage.save_message(msg)

            saved = await storage.get_message("s2")
            assert saved is not None
            assert saved.project_id is None
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_filter_by_project_id(self, storage):
        """project_id로 메시지 필터링"""
        await storage.connect()
        try:
            for i, pid in enumerate(["secretary", "wsoptv", "secretary"]):
                msg = NormalizedMessage(
                    id=f"s3-{i}", channel=ChannelType.SLACK, channel_id="C_TEST",
                    sender_id="u1", text=f"test {i}",
                )
                await storage.save_message(msg, project_id=pid)

            secretary_msgs = await storage.get_recent_messages(project_id="secretary")
            assert len(secretary_msgs) == 2

            wsoptv_msgs = await storage.get_recent_messages(project_id="wsoptv")
            assert len(wsoptv_msgs) == 1
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_migration_idempotent(self, storage):
        """마이그레이션 멱등성 확인"""
        await storage.connect()
        # 두 번째 connect는 이미 컬럼이 있으므로 에러 없이 통과해야 함
        await storage.close()
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="s4", channel=ChannelType.SLACK, channel_id="C_TEST",
                sender_id="u1", text="test",
            )
            await storage.save_message(msg, project_id="secretary")
            saved = await storage.get_message("s4")
            assert saved.project_id == "secretary"
        finally:
            await storage.close()
