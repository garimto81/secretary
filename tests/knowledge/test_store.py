"""
KnowledgeStore TDD 테스트

SQLite FTS5 기반 프로젝트별 지식 저장소 테스트.
실제 aiosqlite DB를 사용한 통합 테스트.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest
import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.knowledge.models import KnowledgeDocument, SearchResult

pytestmark = pytest.mark.asyncio


# ==========================================
# Fixtures
# ==========================================


@pytest.fixture
async def store(tmp_path):
    """임시 DB로 KnowledgeStore 생성"""
    from scripts.knowledge.store import KnowledgeStore

    db_path = tmp_path / "test_knowledge.db"
    s = KnowledgeStore(db_path=db_path)
    await s.init_db()
    yield s
    await s.close()


@pytest.fixture
def sample_doc():
    """테스트용 KnowledgeDocument"""
    return KnowledgeDocument(
        id="gmail:msg001",
        project_id="ebs",
        source="gmail",
        source_id="msg001",
        content="SUN-FLY에서 RFID 칩 가격 견적을 보냈습니다. 단가 $2.50입니다.",
        sender_name="Susie Park",
        sender_id="susie@sunfly.com",
        subject="RFID 칩 견적서",
        thread_id="thread001",
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_docs():
    """다양한 프로젝트/소스의 테스트 문서 목록"""
    now = datetime.now()
    return [
        KnowledgeDocument(
            id="gmail:msg001",
            project_id="ebs",
            source="gmail",
            source_id="msg001",
            content="SUN-FLY에서 RFID 칩 가격 견적을 보냈습니다. 단가 $2.50입니다.",
            sender_name="Susie Park",
            sender_id="susie@sunfly.com",
            subject="RFID 칩 견적서",
            thread_id="thread001",
            created_at=now - timedelta(hours=3),
        ),
        KnowledgeDocument(
            id="slack:msg002",
            project_id="ebs",
            source="slack",
            source_id="msg002",
            content="EBS 방송 일정이 변경되었습니다. 다음 주 월요일로 연기합니다.",
            sender_name="James Lee",
            sender_id="U_james",
            subject="",
            thread_id="thread002",
            created_at=now - timedelta(hours=2),
        ),
        KnowledgeDocument(
            id="gmail:msg003",
            project_id="wsoptv",
            source="gmail",
            source_id="msg003",
            content="WSOP Main Event broadcast schedule has been finalized.",
            sender_name="Alex Kim",
            sender_id="alex@wsop.com",
            subject="WSOP Schedule",
            thread_id="thread003",
            created_at=now - timedelta(hours=1),
        ),
        KnowledgeDocument(
            id="slack:msg004",
            project_id="ebs",
            source="slack",
            source_id="msg004",
            content="RFID 리더기 펌웨어 업데이트 완료했습니다.",
            sender_name="Susie Park",
            sender_id="susie@sunfly.com",
            subject="",
            thread_id="thread001",
            created_at=now,
        ),
    ]


# ==========================================
# 1. DB 초기화
# ==========================================


class TestInitDb:
    """init_db() 테이블 생성 검증"""

    async def test_init_db_creates_tables(self, tmp_path):
        """init_db() 호출 후 documents, documents_fts, ingestion_state 테이블 존재 확인"""
        from scripts.knowledge.store import KnowledgeStore

        db_path = tmp_path / "test_init.db"
        s = KnowledgeStore(db_path=db_path)
        await s.init_db()

        try:
            # WAL mode 확인
            async with s._connection.execute("PRAGMA journal_mode") as cursor:
                row = await cursor.fetchone()
                assert row[0] == "wal"

            # sqlite_master에서 테이블/가상 테이블 조회
            async with s._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()
                names = [row[0] for row in rows]

            assert "documents" in names, f"documents 테이블 없음. 존재: {names}"
            assert "ingestion_state" in names, f"ingestion_state 테이블 없음. 존재: {names}"

            # FTS5 가상 테이블 존재 확인
            fts_tables = [n for n in names if "fts" in n.lower()]
            assert len(fts_tables) > 0, f"FTS5 테이블 없음. 존재: {names}"
        finally:
            await s.close()


# ==========================================
# 2-3. Ingest & Upsert
# ==========================================


class TestIngest:
    """문서 ingest 및 upsert 검증"""

    async def test_ingest_document(self, store, sample_doc):
        """문서 하나 ingest 후 검색으로 확인"""
        await store.ingest(sample_doc)

        # FTS5 검색으로 확인
        results = await store.search("RFID", project_id="ebs")
        assert len(results) >= 1

        found = results[0]
        assert isinstance(found, SearchResult)
        assert found.document.id == "gmail:msg001"
        assert found.document.project_id == "ebs"
        assert found.document.source == "gmail"
        assert found.document.sender_name == "Susie Park"
        assert "RFID" in found.document.content
        assert found.score != 0  # FTS5 rank score

    async def test_ingest_duplicate_upsert(self, store, sample_doc):
        """같은 id로 두 번 ingest -> 1건만 존재, 내용은 업데이트됨"""
        # 첫 ingest
        await store.ingest(sample_doc)

        # 같은 id로 내용 변경
        updated_doc = KnowledgeDocument(
            id="gmail:msg001",
            project_id="ebs",
            source="gmail",
            source_id="msg001",
            content="SUN-FLY 견적 수정: RFID 칩 단가 $2.00으로 변경되었습니다.",
            sender_name="Susie Park",
            sender_id="susie@sunfly.com",
            subject="RFID 칩 견적서 (수정)",
            thread_id="thread001",
            created_at=datetime.now(),
        )
        await store.ingest(updated_doc)

        # documents 테이블에 1건만 존재
        async with store._connection.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE id = ?",
            ("gmail:msg001",),
        ) as cursor:
            row = await cursor.fetchone()
            assert row["cnt"] == 1

        # 내용이 업데이트되었는지 확인
        async with store._connection.execute(
            "SELECT content, subject FROM documents WHERE id = ?",
            ("gmail:msg001",),
        ) as cursor:
            row = await cursor.fetchone()
            assert "$2.00" in row["content"]
            assert "수정" in row["subject"]

        # FTS도 업데이트된 내용으로 검색 가능 (FTS-friendly 검색어 사용)
        results = await store.search("단가", project_id="ebs")
        assert len(results) >= 1
        assert results[0].document.id == "gmail:msg001"


# ==========================================
# 4-5. FTS5 검색 (한국어/영어)
# ==========================================


class TestFtsSearch:
    """FTS5 전문검색 검증"""

    async def test_search_fts5_korean(self, store, sample_docs):
        """한국어 텍스트 검색 ("RFID" 등)"""
        for doc in sample_docs:
            await store.ingest(doc)

        # "RFID" 검색 - ebs 프로젝트 내 2건 (msg001, msg004)
        results = await store.search("RFID", project_id="ebs")
        assert len(results) >= 1
        doc_ids = {r.document.id for r in results}
        assert "gmail:msg001" in doc_ids  # "RFID 칩 가격 견적"
        assert "slack:msg004" in doc_ids  # "RFID 리더기 펌웨어"

    async def test_search_fts5_english(self, store, sample_docs):
        """영어 텍스트 검색"""
        for doc in sample_docs:
            await store.ingest(doc)

        # "broadcast schedule" 검색
        results = await store.search("broadcast schedule", project_id="wsoptv")
        assert len(results) >= 1
        doc_ids = {r.document.id for r in results}
        assert "gmail:msg003" in doc_ids  # WSOP broadcast schedule


# ==========================================
# 6-9. 필터 검색
# ==========================================


class TestFilteredSearch:
    """project_id, source, sender, thread 필터 검증"""

    async def test_search_by_project_filter(self, store, sample_docs):
        """다른 project_id의 문서는 검색 안 됨"""
        for doc in sample_docs:
            await store.ingest(doc)

        # project_id="ebs"로 검색 -> wsoptv 문서 제외
        results = await store.search("RFID", project_id="ebs")
        assert all(r.document.project_id == "ebs" for r in results)

        # wsoptv 프로젝트에서 RFID 검색 -> 결과 없음
        results_wsop = await store.search("RFID", project_id="wsoptv")
        assert len(results_wsop) == 0

    async def test_search_by_source_filter(self, store, sample_docs):
        """source="gmail" 필터 시 slack 문서 제외"""
        for doc in sample_docs:
            await store.ingest(doc)

        # source="gmail"로 필터, ebs 프로젝트 내에서 검색
        results = await store.search("RFID", project_id="ebs", source="gmail")
        assert len(results) >= 1
        assert all(r.document.source == "gmail" for r in results)

        # slack 문서가 포함되지 않음
        sources = {r.document.source for r in results}
        assert "slack" not in sources

    async def test_search_by_sender(self, store, sample_docs):
        """sender_name으로 검색 (search_by_sender 메서드)"""
        for doc in sample_docs:
            await store.ingest(doc)

        # sender_name="Susie Park", project_id="ebs" 필터
        results = await store.search_by_sender("Susie Park", project_id="ebs")
        assert len(results) >= 1
        assert all(r.sender_name == "Susie Park" for r in results)

        # Susie Park 문서는 msg001, msg004
        doc_ids = {r.id for r in results}
        assert "gmail:msg001" in doc_ids
        assert "slack:msg004" in doc_ids

    async def test_search_by_thread(self, store, sample_docs):
        """thread_id로 같은 스레드 문서 조회 (search_by_thread 메서드)"""
        for doc in sample_docs:
            await store.ingest(doc)

        # thread_id="thread001" 필터 -> msg001, msg004
        results = await store.search_by_thread("thread001", project_id="ebs")
        assert len(results) == 2
        doc_ids = {r.id for r in results}
        assert doc_ids == {"gmail:msg001", "slack:msg004"}


# ==========================================
# 10. get_recent
# ==========================================


class TestGetRecent:
    """최근 문서 조회 검증"""

    async def test_get_recent(self, store, sample_docs):
        """최근 문서 limit 개 반환, 정렬 확인"""
        for doc in sample_docs:
            await store.ingest(doc)

        # ebs 프로젝트에서 limit=2로 최근 2건 조회
        recent = await store.get_recent(project_id="ebs", limit=2)
        assert len(recent) == 2

        # KnowledgeDocument 인스턴스 반환
        assert isinstance(recent[0], KnowledgeDocument)
        assert isinstance(recent[1], KnowledgeDocument)

        # 최신순 정렬 (created_at DESC)
        # ebs 문서 중 가장 최근 = msg004 (now), 그 다음 = msg002 (now - 2h)
        assert recent[0].id == "slack:msg004"
        assert recent[1].id == "slack:msg002"

    async def test_get_recent_with_source_filter(self, store, sample_docs):
        """get_recent에 source 필터 적용"""
        for doc in sample_docs:
            await store.ingest(doc)

        # ebs 프로젝트, source="gmail" 필터
        recent = await store.get_recent(project_id="ebs", source="gmail", limit=10)
        assert len(recent) == 1
        assert recent[0].id == "gmail:msg001"
        assert recent[0].source == "gmail"

    async def test_get_recent_empty_store(self, store):
        """빈 store에서 get_recent 호출 시 빈 리스트 반환"""
        recent = await store.get_recent(project_id="ebs", limit=10)
        assert recent == []


# ==========================================
# 11. get_stats
# ==========================================


class TestGetStats:
    """통계 조회 검증"""

    async def test_get_stats(self, store, sample_docs):
        """프로젝트별 문서 수, 소스별 분포"""
        for doc in sample_docs:
            await store.ingest(doc)

        stats = await store.get_stats()

        # 전체 문서 수
        assert stats["total_documents"] == 4

        # 프로젝트별 문서 수
        assert "by_project" in stats
        assert stats["by_project"]["ebs"] == 3
        assert stats["by_project"]["wsoptv"] == 1

        # 소스별 분포
        assert "by_source" in stats
        assert stats["by_source"]["gmail"] == 2
        assert stats["by_source"]["slack"] == 2

    async def test_get_stats_with_project_filter(self, store, sample_docs):
        """프로젝트 필터가 적용된 통계"""
        for doc in sample_docs:
            await store.ingest(doc)

        stats = await store.get_stats(project_id="ebs")
        assert stats["total_documents"] == 3
        assert stats["by_source"]["gmail"] == 1
        assert stats["by_source"]["slack"] == 2

    async def test_get_stats_empty_store(self, store):
        """빈 store의 통계"""
        stats = await store.get_stats()
        assert stats["total_documents"] == 0
        assert stats["by_source"] == {}


# ==========================================
# 12. cleanup
# ==========================================


class TestCleanup:
    """오래된 문서 삭제 검증"""

    async def test_cleanup_old_documents(self, store):
        """180일 이전 문서 삭제, 최근 문서 유지"""
        now = datetime.now()

        # 오래된 문서 (200일 전)
        old_doc = KnowledgeDocument(
            id="gmail:old001",
            project_id="ebs",
            source="gmail",
            source_id="old001",
            content="오래된 메일입니다.",
            sender_name="Old User",
            sender_id="old@test.com",
            created_at=now - timedelta(days=200),
        )
        await store.ingest(old_doc)

        # 최근 문서 (1일 전)
        recent_doc = KnowledgeDocument(
            id="gmail:new001",
            project_id="ebs",
            source="gmail",
            source_id="new001",
            content="최근 메일입니다.",
            sender_name="New User",
            sender_id="new@test.com",
            created_at=now - timedelta(days=1),
        )
        await store.ingest(recent_doc)

        # cleanup 실행 (180일 기준)
        deleted_count = await store.cleanup(retention_days=180)

        # 200일 전 문서는 삭제됨
        assert deleted_count >= 1

        # 최근 문서는 유지
        async with store._connection.execute(
            "SELECT id FROM documents WHERE id = ?", ("gmail:new001",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "최근 문서가 삭제되면 안 됨"

        # 200일 전 문서는 삭제됨
        async with store._connection.execute(
            "SELECT id FROM documents WHERE id = ?", ("gmail:old001",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None, "오래된 문서가 삭제되어야 함"

    async def test_cleanup_returns_deleted_count(self, store):
        """cleanup이 삭제된 문서 수를 정확히 반환"""
        now = datetime.now()

        # 오래된 문서 3건
        for i in range(3):
            doc = KnowledgeDocument(
                id=f"gmail:old{i:03d}",
                project_id="ebs",
                source="gmail",
                source_id=f"old{i:03d}",
                content=f"오래된 메일 {i}",
                created_at=now - timedelta(days=200),
            )
            await store.ingest(doc)

        # 최근 문서 2건
        for i in range(2):
            doc = KnowledgeDocument(
                id=f"gmail:new{i:03d}",
                project_id="ebs",
                source="gmail",
                source_id=f"new{i:03d}",
                content=f"최근 메일 {i}",
                created_at=now - timedelta(days=10),
            )
            await store.ingest(doc)

        deleted = await store.cleanup(retention_days=180)
        assert deleted == 3

        # 남은 문서 확인
        async with store._connection.execute(
            "SELECT COUNT(*) as cnt FROM documents"
        ) as cursor:
            row = await cursor.fetchone()
            assert row["cnt"] == 2


# ==========================================
# Edge Cases
# ==========================================


class TestEdgeCases:
    """경계 조건 및 예외 상황 테스트"""

    async def test_search_no_results(self, store, sample_doc):
        """매칭 결과 없는 검색"""
        await store.ingest(sample_doc)

        results = await store.search("absolutely_nonexistent_term_xyz", project_id="ebs")
        assert results == []

    async def test_ingest_minimal_document(self, store):
        """최소 필드만 있는 문서 ingest"""
        doc = KnowledgeDocument(
            id="test:minimal001",
            project_id="test",
            source="test",
            source_id="minimal001",
            content="Minimal content",
        )
        await store.ingest(doc)

        results = await store.search("Minimal", project_id="test")
        assert len(results) == 1
        assert results[0].document.id == "test:minimal001"

    async def test_ingest_unicode_content(self, store):
        """유니코드 포함 문서 ingest 및 검색"""
        doc = KnowledgeDocument(
            id="test:unicode001",
            project_id="test",
            source="slack",
            source_id="unicode001",
            content="긴급 알림: 서버 점검이 예정되어 있습니다. Check the dashboard!",
        )
        await store.ingest(doc)

        # 영어 검색
        results = await store.search("dashboard", project_id="test")
        assert len(results) >= 1

    async def test_search_with_limit(self, store, sample_docs):
        """검색 결과 개수 제한"""
        for doc in sample_docs:
            await store.ingest(doc)

        results = await store.search("RFID", project_id="ebs", limit=1)
        assert len(results) == 1

    async def test_close_and_reopen(self, tmp_path):
        """close 후 재접속해도 데이터 유지"""
        from scripts.knowledge.store import KnowledgeStore

        db_path = tmp_path / "test_reopen.db"

        # 첫 세션: 문서 ingest
        s1 = KnowledgeStore(db_path=db_path)
        await s1.init_db()
        doc = KnowledgeDocument(
            id="test:persist001",
            project_id="test",
            source="test",
            source_id="persist001",
            content="Persistence test document",
        )
        await s1.ingest(doc)
        await s1.close()

        # 두 번째 세션: 데이터 확인
        s2 = KnowledgeStore(db_path=db_path)
        await s2.init_db()
        results = await s2.search("Persistence", project_id="test")
        assert len(results) == 1
        assert results[0].document.id == "test:persist001"
        await s2.close()

    async def test_context_manager_lifecycle(self, tmp_path):
        """async with context manager 라이프사이클"""
        from scripts.knowledge.store import KnowledgeStore

        db_path = tmp_path / "test_ctx.db"

        async with KnowledgeStore(db_path=db_path) as s:
            # 연결 상태 확인
            assert s._connection is not None

            doc = KnowledgeDocument(
                id="test:ctx001",
                project_id="test",
                source="test",
                source_id="ctx001",
                content="Context manager test",
            )
            await s.ingest(doc)
            results = await s.search("Context", project_id="test")
            assert len(results) == 1

        # Context 종료 후 연결 닫힘
        assert s._connection is None

    async def test_ensure_connected_raises_if_not_connected(self, tmp_path):
        """init_db() 없이 메서드 호출 시 RuntimeError 발생"""
        from scripts.knowledge.store import KnowledgeStore

        db_path = tmp_path / "test_noconnect.db"
        s = KnowledgeStore(db_path=db_path)

        doc = KnowledgeDocument(
            id="test:fail001",
            project_id="test",
            source="test",
            source_id="fail001",
            content="Should fail",
        )
        with pytest.raises(RuntimeError, match="not connected"):
            await s.ingest(doc)
