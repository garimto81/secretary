"""Channel Mastery 단위/통합 테스트"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.knowledge.channel_profile import ChannelProfileStore
from scripts.knowledge.models import ChannelProfile, KnowledgeDocument
from scripts.knowledge.store import KnowledgeStore

pytestmark = pytest.mark.asyncio


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
async def store(tmp_path):
    """임시 DB로 KnowledgeStore 생성"""
    db_path = tmp_path / "test_knowledge.db"
    s = KnowledgeStore(db_path=db_path)
    await s.init_db()
    yield s
    await s.close()


@pytest.fixture
async def profile_store(tmp_path):
    """임시 DB로 ChannelProfileStore 생성"""
    db_path = tmp_path / "test_profile.db"
    ps = ChannelProfileStore(db_path=db_path)
    await ps.init_db()
    yield ps
    await ps.close()


@pytest.fixture
def sample_profile():
    """테스트용 ChannelProfile"""
    return ChannelProfile(
        channel_id="C0985UXQN6Q",
        channel_name="secretary-dev",
        topic="AI 비서 개발",
        purpose="secretary 프로젝트 개발 채널",
        created=datetime(2025, 1, 15),
        members=[
            {"id": "U001", "name": "alice"},
            {"id": "U002", "name": "bob"},
            {"id": "U003", "name": "charlie"},
        ],
        pinned_messages=[
            {"ts": "1700000000.000000", "text": "프로젝트 가이드라인"},
        ],
        collected_at=datetime.now(),
        total_messages=1500,
        total_threads=200,
    )


@pytest.fixture
def sample_slack_docs():
    """mastery analyzer 테스트용 Slack 문서"""
    now = datetime.now()
    return [
        KnowledgeDocument(
            id="slack:1001", project_id="secretary", source="slack",
            source_id="1001", content="gateway 배포 완료했습니다. 모든 테스트 통과.",
            sender_name="alice", sender_id="U001",
            thread_id="", content_type="message",
            created_at=now - timedelta(hours=5),
        ),
        KnowledgeDocument(
            id="slack:1002", project_id="secretary", source="slack",
            source_id="1002", content="intelligence 분석 모듈 리뷰 부탁합니다. PR 올렸어요.",
            sender_name="bob", sender_id="U002",
            thread_id="", content_type="message",
            created_at=now - timedelta(hours=4),
        ),
        KnowledgeDocument(
            id="slack:1003", project_id="secretary", source="slack",
            source_id="1003", content="gateway 재연결 로직 검토 결정했습니다. exponential backoff로 진행하기로 했습니다.",
            sender_name="alice", sender_id="U001",
            thread_id="", content_type="message",
            created_at=now - timedelta(hours=3),
        ),
        KnowledgeDocument(
            id="slack:1004", project_id="secretary", source="slack",
            source_id="1004", content="knowledge store FTS5 인덱스 최적화 확정. unicode61 tokenizer 유지.",
            sender_name="charlie", sender_id="U003",
            thread_id="", content_type="message",
            created_at=now - timedelta(hours=2),
        ),
        KnowledgeDocument(
            id="slack:1005", project_id="secretary", source="slack",
            source_id="1005", content="오늘 deploy 일정 확인해주세요?",
            sender_name="bob", sender_id="U002",
            thread_id="", content_type="message",
            created_at=now - timedelta(hours=1),
        ),
    ]


# ==========================================
# 1. ChannelProfile 모델 테스트
# ==========================================

class TestChannelProfile:
    """ChannelProfile dataclass 테스트"""

    def test_create_profile(self, sample_profile):
        """ChannelProfile 생성"""
        assert sample_profile.channel_id == "C0985UXQN6Q"
        assert sample_profile.channel_name == "secretary-dev"
        assert len(sample_profile.members) == 3
        assert sample_profile.total_messages == 1500

    def test_create_minimal_profile(self):
        """최소 필드로 생성"""
        p = ChannelProfile(channel_id="C123", channel_name="test")
        assert p.topic == ""
        assert p.members == []
        assert p.total_messages == 0


# ==========================================
# 2. ChannelProfileStore 테스트
# ==========================================

class TestChannelProfileStore:
    """ChannelProfileStore SQLite CRUD"""

    async def test_save_and_get(self, profile_store, sample_profile):
        """save → get 라운드트립"""
        await profile_store.save(sample_profile)
        loaded = await profile_store.get("C0985UXQN6Q")

        assert loaded is not None
        assert loaded.channel_id == "C0985UXQN6Q"
        assert loaded.channel_name == "secretary-dev"
        assert loaded.topic == "AI 비서 개발"
        assert loaded.purpose == "secretary 프로젝트 개발 채널"
        assert len(loaded.members) == 3
        assert len(loaded.pinned_messages) == 1
        assert loaded.total_messages == 1500

    async def test_get_nonexistent(self, profile_store):
        """존재하지 않는 채널 조회 → None"""
        result = await profile_store.get("C_NONEXISTENT")
        assert result is None

    async def test_upsert(self, profile_store, sample_profile):
        """같은 channel_id로 두 번 저장 → 업데이트"""
        await profile_store.save(sample_profile)

        updated = ChannelProfile(
            channel_id="C0985UXQN6Q",
            channel_name="secretary-dev-v2",
            topic="Updated topic",
            total_messages=2000,
        )
        await profile_store.save(updated)

        loaded = await profile_store.get("C0985UXQN6Q")
        assert loaded.channel_name == "secretary-dev-v2"
        assert loaded.topic == "Updated topic"
        assert loaded.total_messages == 2000

    async def test_context_manager(self, tmp_path):
        """async with 라이프사이클"""
        db_path = tmp_path / "test_ctx.db"
        async with ChannelProfileStore(db_path=db_path) as ps:
            p = ChannelProfile(channel_id="C100", channel_name="test-ch")
            await ps.save(p)
            loaded = await ps.get("C100")
            assert loaded is not None
        assert ps._connection is None


# ==========================================
# 3. ChannelMasteryAnalyzer 테스트
# ==========================================

class TestChannelMasteryAnalyzer:
    """전문가 컨텍스트 생성 테스트"""

    async def test_build_mastery_context(self, store, profile_store, sample_slack_docs, sample_profile):
        """build_mastery_context 기본 실행"""
        from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer

        # 데이터 준비
        for doc in sample_slack_docs:
            await store.ingest(doc)
        await profile_store.save(sample_profile)

        analyzer = ChannelMasteryAnalyzer(store, profile_store)
        result = await analyzer.build_mastery_context(
            project_id="secretary",
            channel_id="C0985UXQN6Q",
        )

        assert isinstance(result, dict)
        assert "channel_summary" in result
        assert "top_keywords" in result
        assert "key_decisions" in result
        assert "member_roles" in result
        assert "active_topics" in result

        # 키워드가 추출됨
        assert len(result["top_keywords"]) >= 3

        # 의사결정이 추출됨 ("결정", "확정" 포함 메시지)
        assert len(result["key_decisions"]) >= 1

        # 멤버 역할 할당됨
        assert len(result["member_roles"]) >= 1

    async def test_empty_channel(self, store, profile_store):
        """빈 채널에서 빈 dict 반환"""
        from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer

        analyzer = ChannelMasteryAnalyzer(store, profile_store)
        result = await analyzer.build_mastery_context(
            project_id="empty_project",
            channel_id="C_EMPTY",
        )

        assert result["channel_summary"] == ""
        assert result["top_keywords"] == []
        assert result["key_decisions"] == []
        assert result["member_roles"] == {}
        assert result["active_topics"] == []

    def test_tokenize(self):
        """한국어+영어 토큰화"""
        from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer
        analyzer = ChannelMasteryAnalyzer.__new__(ChannelMasteryAnalyzer)
        tokens = analyzer._tokenize("gateway 배포 완료했습니다 intelligence 모듈")
        assert "gateway" in tokens
        assert "intelligence" in tokens
        assert "배포" in tokens
        assert "완료했습니다" in tokens

    def test_extract_keywords(self, sample_slack_docs):
        """TF-IDF 키워드 추출"""
        from scripts.knowledge.mastery_analyzer import ChannelMasteryAnalyzer
        analyzer = ChannelMasteryAnalyzer.__new__(ChannelMasteryAnalyzer)
        keywords = analyzer._extract_keywords(sample_slack_docs, top_n=10)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # gateway가 여러 문서에 출현하므로 상위에 있을 것
        assert "gateway" in keywords[:10]


# ==========================================
# 4. Bootstrap learn_slack_full 테스트 (mock)
# ==========================================

class TestLearnSlackFull:
    """learn_slack_full cursor pagination 테스트"""

    async def test_learn_slack_full_single_page(self, store):
        """단일 페이지 수집 (next_cursor 없음)"""
        from scripts.knowledge.bootstrap import KnowledgeBootstrap

        bootstrap = KnowledgeBootstrap(store)

        mock_response = {
            "messages": [
                {"ts": "1700000001.000000", "text": "Hello world", "user": "U001"},
                {"ts": "1700000002.000000", "text": "Gateway 배포합니다", "user": "U002"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch.object(bootstrap, '_run_subprocess', return_value=mock_response):
            result = await bootstrap.learn_slack_full(
                project_id="test",
                channel_id="C123",
                page_size=100,
                rate_limit_sleep=0,
            )

        assert result.total_fetched == 2
        assert result.total_ingested == 2
        assert result.errors == 0

    async def test_learn_slack_full_multi_page(self, store):
        """멀티 페이지 수집 (cursor pagination)"""
        from scripts.knowledge.bootstrap import KnowledgeBootstrap

        bootstrap = KnowledgeBootstrap(store)

        page1 = {
            "messages": [
                {"ts": "1700000001.000000", "text": "Page 1 message", "user": "U001"},
            ],
            "response_metadata": {"next_cursor": "cursor_page2"},
        }
        page2 = {
            "messages": [
                {"ts": "1700000002.000000", "text": "Page 2 message", "user": "U002"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        call_count = 0
        def mock_subprocess(args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1
            return page2

        with patch.object(bootstrap, '_run_subprocess', side_effect=mock_subprocess):
            result = await bootstrap.learn_slack_full(
                project_id="test",
                channel_id="C123",
                page_size=1,
                rate_limit_sleep=0,
            )

        assert result.total_fetched == 2
        assert result.total_ingested == 2
        assert call_count == 2

    async def test_fetch_thread_replies(self, store):
        """thread replies 수집"""
        from scripts.knowledge.bootstrap import KnowledgeBootstrap

        bootstrap = KnowledgeBootstrap(store)

        mock_replies = {
            "messages": [
                {"ts": "1700000001.000000", "text": "Parent message", "user": "U001"},  # parent는 skip
                {"ts": "1700000001.000100", "text": "Reply 1", "user": "U002"},
                {"ts": "1700000001.000200", "text": "Reply 2", "user": "U003"},
            ],
        }

        with patch.object(bootstrap, '_run_subprocess', return_value=mock_replies):
            count = await bootstrap._fetch_thread_replies(
                project_id="test",
                channel_id="C123",
                thread_ts="1700000001.000000",
                rate_limit_sleep=0,
            )

        assert count == 2  # parent 제외

    async def test_learn_slack_full_subprocess_failure(self, store):
        """subprocess 실패 시 에러 처리"""
        from scripts.knowledge.bootstrap import KnowledgeBootstrap

        bootstrap = KnowledgeBootstrap(store)

        with patch.object(bootstrap, '_run_subprocess', return_value=None):
            result = await bootstrap.learn_slack_full(
                project_id="test",
                channel_id="C123",
                rate_limit_sleep=0,
            )

        assert result.errors >= 1
        assert result.total_ingested == 0


# ==========================================
# 5. Handler 채널 전문가 컨텍스트 주입 테스트
# ==========================================

class TestHandlerMasteryInjection:
    """handler.py _build_context에 mastery 컨텍스트 주입 테스트"""

    async def test_build_context_with_mastery(self):
        """mastery_analyzer 설정 시 컨텍스트에 채널 전문가 섹션 포함"""
        from scripts.intelligence.response.handler import ProjectIntelligenceHandler

        # Mock 의존성
        mock_storage = AsyncMock()
        mock_storage.get_context_entries = AsyncMock(return_value=[])

        mock_registry = AsyncMock()
        mock_registry.get = AsyncMock(return_value={"name": "secretary", "description": "AI 비서"})

        mock_mastery = AsyncMock()
        mock_mastery.build_mastery_context = AsyncMock(return_value={
            "channel_summary": "#secretary-dev | 목적: AI 비서 개발",
            "top_keywords": ["gateway", "intelligence", "배포"],
            "key_decisions": ["2026-02-15: exponential backoff로 결정"],
            "member_roles": {"alice": "실행 담당", "bob": "요청자"},
            "active_topics": ["gateway 개발"],
        })

        handler = ProjectIntelligenceHandler(
            storage=mock_storage,
            registry=mock_registry,
            knowledge_store=None,
            mastery_analyzer=mock_mastery,
        )

        result = await handler._build_context("secretary", query_text="gateway")
        # _build_context가 tuple을 반환하는 경우 처리
        context = result[0] if isinstance(result, tuple) else result

        assert "채널 전문가 컨텍스트" in context
        assert "gateway" in context
        assert "intelligence" in context

    async def test_build_context_without_mastery(self):
        """mastery_analyzer 미설정 시 기존 동작 유지"""
        from scripts.intelligence.response.handler import ProjectIntelligenceHandler

        mock_storage = AsyncMock()
        mock_storage.get_context_entries = AsyncMock(return_value=[])

        mock_registry = AsyncMock()
        mock_registry.get = AsyncMock(return_value={"name": "secretary"})

        handler = ProjectIntelligenceHandler(
            storage=mock_storage,
            registry=mock_registry,
        )

        result = await handler._build_context("secretary")
        context = result[0] if isinstance(result, tuple) else result
        assert "채널 전문가 컨텍스트" not in context
