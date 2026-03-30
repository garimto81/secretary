"""
IntelligenceStorage 통합 테스트

실제 aiosqlite DB를 사용한 통합 테스트.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.context_store import IntelligenceStorage


class TestIntelligenceStorageIntegration:
    """IntelligenceStorage DB 통합 테스트"""

    @pytest.fixture
    async def storage(self, tmp_path):
        """실제 aiosqlite DB를 tmp_path에 생성"""
        db_path = tmp_path / "test_intelligence.db"
        s = IntelligenceStorage(db_path=db_path)
        await s.connect()
        yield s
        await s.close()

    # ==========================================
    # 연결 및 스키마
    # ==========================================

    @pytest.mark.asyncio
    async def test_connect_creates_schema(self, tmp_path):
        """connect()가 스키마 초기화하고 WAL mode 설정"""
        db_path = tmp_path / "test.db"
        storage = IntelligenceStorage(db_path=db_path)

        await storage.connect()

        # WAL mode 확인
        async with storage._connection.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "wal"

        # 테이블 존재 확인
        async with storage._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]
            assert "projects" in tables
            assert "context_entries" in tables
            assert "analysis_state" in tables
            assert "draft_responses" in tables

        await storage.close()

    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(self, tmp_path):
        """async with context manager 라이프사이클"""
        db_path = tmp_path / "test_ctx.db"

        async with IntelligenceStorage(db_path=db_path) as storage:
            # 연결 상태 확인
            assert storage._connection is not None

            # 간단한 쿼리 실행
            async with storage._connection.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                assert row[0] == 1

        # Context 종료 후 연결 닫힘
        # storage._connection.execute()는 실패해야 하지만, connection 자체는 None일 수 있음

    @pytest.mark.asyncio
    async def test_ensure_connected_raises_if_not_connected(self, tmp_path):
        """_ensure_connected()가 연결 전에 RuntimeError 발생"""
        db_path = tmp_path / "test.db"
        storage = IntelligenceStorage(db_path=db_path)

        # 연결 없이 메서드 호출 시 RuntimeError
        with pytest.raises(RuntimeError, match="Storage not connected"):
            await storage.save_project({"id": "test", "name": "Test"})

    # ==========================================
    # Projects CRUD
    # ==========================================

    @pytest.mark.asyncio
    async def test_save_and_get_project(self, storage):
        """프로젝트 저장 및 조회"""
        project = {
            "id": "test-project",
            "name": "Test Project",
            "description": "Test Description",
            "github_repos": ["org/repo1", "org/repo2"],
            "slack_channels": ["general", "dev"],
            "gmail_queries": ["from:test@example.com"],
            "keywords": ["urgent", "deadline"],
            "contacts": ["user1", "user2"],
            "config": {"priority": "high"},
        }

        # 저장
        project_id = await storage.save_project(project)
        assert project_id == "test-project"

        # 조회
        retrieved = await storage.get_project("test-project")
        assert retrieved is not None
        assert retrieved["id"] == "test-project"
        assert retrieved["name"] == "Test Project"
        assert retrieved["description"] == "Test Description"
        assert retrieved["github_repos"] == ["org/repo1", "org/repo2"]
        assert retrieved["slack_channels"] == ["general", "dev"]
        assert retrieved["gmail_queries"] == ["from:test@example.com"]
        assert retrieved["keywords"] == ["urgent", "deadline"]
        assert retrieved["contacts"] == ["user1", "user2"]
        assert retrieved["config"] == {"priority": "high"}

    @pytest.mark.asyncio
    async def test_upsert_project(self, storage):
        """프로젝트 upsert (수정)"""
        project = {
            "id": "proj1",
            "name": "Original Name",
            "description": "Original",
            "github_repos": ["repo1"],
        }
        await storage.save_project(project)

        # 동일 ID로 다시 저장
        updated = {
            "id": "proj1",
            "name": "Updated Name",
            "description": "Updated",
            "github_repos": ["repo1", "repo2"],
        }
        await storage.save_project(updated)

        # 조회
        retrieved = await storage.get_project("proj1")
        assert retrieved["name"] == "Updated Name"
        assert retrieved["description"] == "Updated"
        assert retrieved["github_repos"] == ["repo1", "repo2"]

    @pytest.mark.asyncio
    async def test_list_projects(self, storage):
        """전체 프로젝트 목록 조회"""
        # 3개 프로젝트 생성
        for i in range(3):
            await storage.save_project({
                "id": f"proj{i}",
                "name": f"Project {i}",
            })

        # 목록 조회
        projects = await storage.list_projects()
        assert len(projects) == 3
        assert {p["id"] for p in projects} == {"proj0", "proj1", "proj2"}

    @pytest.mark.asyncio
    async def test_delete_project(self, storage):
        """프로젝트 삭제"""
        await storage.save_project({"id": "proj-del", "name": "Delete Me"})

        # 삭제
        result = await storage.delete_project("proj-del")
        assert result is True

        # 조회 불가
        retrieved = await storage.get_project("proj-del")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_none(self, storage):
        """존재하지 않는 프로젝트 조회 시 None 반환"""
        retrieved = await storage.get_project("nonexistent")
        assert retrieved is None

    # ==========================================
    # Context Entries
    # ==========================================

    @pytest.mark.asyncio
    async def test_save_and_get_context_entry(self, storage):
        """컨텍스트 항목 저장 및 조회"""
        # 프로젝트 먼저 생성
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        entry = {
            "id": "entry1",
            "project_id": "proj1",
            "source": "slack",
            "source_id": "msg123",
            "entry_type": "message",
            "title": "Test Message",
            "content": "Hello World",
            "metadata": {"channel": "general"},
        }

        # 저장
        entry_id = await storage.save_context_entry(entry)
        assert entry_id == "entry1"

        # 조회
        entries = await storage.get_context_entries("proj1")
        assert len(entries) == 1
        assert entries[0]["id"] == "entry1"
        assert entries[0]["project_id"] == "proj1"
        assert entries[0]["source"] == "slack"
        assert entries[0]["source_id"] == "msg123"
        assert entries[0]["entry_type"] == "message"
        assert entries[0]["title"] == "Test Message"
        assert entries[0]["content"] == "Hello World"
        assert entries[0]["metadata"] == {"channel": "general"}

    @pytest.mark.asyncio
    async def test_get_context_entries_with_filters(self, storage):
        """get_context_entries의 필터링 (source, entry_type, limit)"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # 다양한 항목 생성
        entries = [
            {"id": "e1", "project_id": "proj1", "source": "slack", "entry_type": "message", "title": "Slack Msg"},
            {"id": "e2", "project_id": "proj1", "source": "gmail", "entry_type": "email", "title": "Gmail Email"},
            {"id": "e3", "project_id": "proj1", "source": "slack", "entry_type": "thread", "title": "Slack Thread"},
            {"id": "e4", "project_id": "proj1", "source": "github", "entry_type": "issue", "title": "GitHub Issue"},
        ]
        for entry in entries:
            await storage.save_context_entry(entry)

        # source 필터
        slack_entries = await storage.get_context_entries("proj1", source="slack")
        assert len(slack_entries) == 2
        assert {e["id"] for e in slack_entries} == {"e1", "e3"}

        # entry_type 필터
        message_entries = await storage.get_context_entries("proj1", entry_type="message")
        assert len(message_entries) == 1
        assert message_entries[0]["id"] == "e1"

        # source + entry_type
        slack_messages = await storage.get_context_entries("proj1", source="slack", entry_type="message")
        assert len(slack_messages) == 1
        assert slack_messages[0]["id"] == "e1"

        # limit
        limited = await storage.get_context_entries("proj1", limit=2)
        assert len(limited) == 2

    # ==========================================
    # Analysis State
    # ==========================================

    @pytest.mark.asyncio
    async def test_save_and_get_analysis_state(self, storage):
        """분석 상태 체크포인트 저장 및 조회"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # 저장
        await storage.save_analysis_state(
            project_id="proj1",
            source="gmail",
            checkpoint_key="last_message_id",
            checkpoint_value="msg123",
            entries_collected=10,
            error_message=None,
        )

        # 조회
        state = await storage.get_analysis_state("proj1", "gmail", "last_message_id")
        assert state is not None
        assert state["project_id"] == "proj1"
        assert state["source"] == "gmail"
        assert state["checkpoint_key"] == "last_message_id"
        assert state["checkpoint_value"] == "msg123"
        assert state["entries_collected"] == 10
        assert state["error_message"] is None

    @pytest.mark.asyncio
    async def test_analysis_state_upsert(self, storage):
        """분석 상태 upsert (unique constraint)"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # 첫 저장
        await storage.save_analysis_state(
            project_id="proj1",
            source="slack",
            checkpoint_key="last_ts",
            checkpoint_value="100.0",
            entries_collected=5,
        )

        # 동일 키로 업데이트
        await storage.save_analysis_state(
            project_id="proj1",
            source="slack",
            checkpoint_key="last_ts",
            checkpoint_value="200.0",
            entries_collected=10,
        )

        # 조회 - 최신 값만 존재
        state = await storage.get_analysis_state("proj1", "slack", "last_ts")
        assert state["checkpoint_value"] == "200.0"
        assert state["entries_collected"] == 10

    @pytest.mark.asyncio
    async def test_get_nonexistent_analysis_state_returns_none(self, storage):
        """존재하지 않는 분석 상태 조회 시 None 반환"""
        state = await storage.get_analysis_state("nonexistent", "slack", "last_ts")
        assert state is None

    # ==========================================
    # Draft Responses
    # ==========================================

    @pytest.mark.asyncio
    async def test_save_and_get_draft(self, storage):
        """응답 초안 저장 및 조회"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        draft = {
            "project_id": "proj1",
            "source_channel": "slack",
            "source_message_id": "msg123",
            "sender_id": "U123",
            "sender_name": "Alice",
            "original_text": "Can you help?",
            "draft_text": "Sure, I can help with that.",
            "draft_file": "drafts/draft1.md",
            "match_confidence": 0.9,
            "match_tier": "ollama",
            "match_status": "matched",
            "status": "pending",
        }

        # 저장 - lastrowid 반환 확인
        draft_id = await storage.save_draft(draft)
        assert isinstance(draft_id, int)
        assert draft_id > 0

        # 조회
        retrieved = await storage.get_draft(draft_id)
        assert retrieved is not None
        assert retrieved["id"] == draft_id
        assert retrieved["project_id"] == "proj1"
        assert retrieved["source_channel"] == "slack"
        assert retrieved["source_message_id"] == "msg123"
        assert retrieved["sender_id"] == "U123"
        assert retrieved["sender_name"] == "Alice"
        assert retrieved["original_text"] == "Can you help?"
        assert retrieved["draft_text"] == "Sure, I can help with that."
        assert retrieved["draft_file"] == "drafts/draft1.md"
        assert retrieved["match_confidence"] == 0.9
        assert retrieved["match_tier"] == "ollama"
        assert retrieved["match_status"] == "matched"
        assert retrieved["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_drafts_filtering(self, storage):
        """list_drafts의 필터링 (status, match_status, project_id)"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})
        await storage.save_project({"id": "proj2", "name": "Project 2"})

        # 다양한 초안 생성
        drafts = [
            {"project_id": "proj1", "source_channel": "slack", "status": "pending", "match_status": "matched"},
            {"project_id": "proj1", "source_channel": "slack", "status": "approved", "match_status": "matched"},
            {"project_id": "proj2", "source_channel": "slack", "status": "pending", "match_status": "pending_match"},
            {"project_id": "proj2", "source_channel": "slack", "status": "rejected", "match_status": "matched"},
        ]
        for draft in drafts:
            await storage.save_draft(draft)

        # status 필터
        pending = await storage.list_drafts(status="pending")
        assert len(pending) == 2

        # match_status 필터
        pending_match = await storage.list_drafts(match_status="pending_match")
        assert len(pending_match) == 1
        assert pending_match[0]["project_id"] == "proj2"

        # project_id 필터
        proj1_drafts = await storage.list_drafts(project_id="proj1")
        assert len(proj1_drafts) == 2

        # 복합 필터
        proj1_pending = await storage.list_drafts(status="pending", project_id="proj1")
        assert len(proj1_pending) == 1

        # limit
        limited = await storage.list_drafts(limit=2)
        assert len(limited) == 2

    @pytest.mark.asyncio
    async def test_update_draft_status(self, storage):
        """초안 상태 업데이트 (approve/reject)"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        draft_id = await storage.save_draft({
            "project_id": "proj1",
            "source_channel": "slack",
            "status": "pending",
        })

        # 상태 업데이트
        result = await storage.update_draft_status(draft_id, "approved", "Looks good!")
        assert result is True

        # 확인
        retrieved = await storage.get_draft(draft_id)
        assert retrieved["status"] == "approved"
        assert retrieved["reviewer_note"] == "Looks good!"
        assert retrieved["reviewed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_draft_sent(self, storage):
        """전송 성공 기록"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        draft_id = await storage.save_draft({
            "project_id": "proj1",
            "source_channel": "slack",
            "status": "approved",
        })

        # 전송 성공
        result = await storage.update_draft_sent(draft_id, message_id="sent123")
        assert result is True

        # 확인
        retrieved = await storage.get_draft(draft_id)
        assert retrieved["status"] == "sent"
        assert retrieved["sent_at"] is not None
        assert "sent123" in retrieved["reviewer_note"]

    @pytest.mark.asyncio
    async def test_update_draft_send_failed(self, storage):
        """전송 실패 기록"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        draft_id = await storage.save_draft({
            "project_id": "proj1",
            "source_channel": "slack",
            "status": "approved",
        })

        # 전송 실패
        result = await storage.update_draft_send_failed(draft_id, "Network error")
        assert result is True

        # 확인
        retrieved = await storage.get_draft(draft_id)
        assert retrieved["status"] == "send_failed"
        assert retrieved["send_error"] == "Network error"

    @pytest.mark.asyncio
    async def test_find_by_message_id_unique_index(self, storage):
        """find_by_message_id의 unique index 동작 (중복 체크)"""
        draft = {
            "source_channel": "slack",
            "source_message_id": "msg123",
            "original_text": "Test",
        }

        # 첫 저장
        draft_id1 = await storage.save_draft(draft)

        # 조회
        found = await storage.find_by_message_id("slack", "msg123")
        assert found is not None
        assert found["id"] == draft_id1

        # 동일 source_channel + source_message_id로 재저장 시도
        # unique index로 인해 upsert 동작 (REPLACE)
        draft_id2 = await storage.save_draft(draft)

        # 조회 - 하나만 존재
        found_again = await storage.find_by_message_id("slack", "msg123")
        assert found_again is not None
        # REPLACE로 인해 새 ID가 부여됨
        assert found_again["id"] == draft_id2

    @pytest.mark.asyncio
    async def test_get_pending_messages(self, storage):
        """미매칭 pending 메시지 조회"""
        # pending_match 상태 초안 생성
        for i in range(3):
            await storage.save_draft({
                "source_channel": "slack",
                "match_status": "pending_match",
                "original_text": f"Message {i}",
            })

        # matched 상태 초안 생성 (제외되어야 함)
        await storage.save_draft({
            "source_channel": "slack",
            "match_status": "matched",
            "original_text": "Matched message",
        })

        # 조회
        pending = await storage.get_pending_messages(limit=10)
        assert len(pending) == 3
        assert all(p["match_status"] == "pending_match" for p in pending)

    @pytest.mark.asyncio
    async def test_get_awaiting_drafts(self, storage):
        """매칭되었지만 draft 미생성 메시지 조회"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # awaiting_draft 상태 초안 생성
        for i in range(2):
            await storage.save_draft({
                "project_id": "proj1",
                "source_channel": "slack",
                "status": "awaiting_draft",
                "match_status": "matched",
                "original_text": f"Awaiting {i}",
            })

        # pending 상태 초안 생성 (제외되어야 함)
        await storage.save_draft({
            "project_id": "proj1",
            "source_channel": "slack",
            "status": "pending",
            "match_status": "matched",
            "original_text": "Already drafted",
        })

        # 조회
        awaiting = await storage.get_awaiting_drafts(limit=10)
        assert len(awaiting) == 2
        assert all(a["status"] == "awaiting_draft" for a in awaiting)
        assert all(a["match_status"] == "matched" for a in awaiting)

        # project_id 필터
        proj1_awaiting = await storage.get_awaiting_drafts(project_id="proj1", limit=10)
        assert len(proj1_awaiting) == 2

    # ==========================================
    # Statistics
    # ==========================================

    @pytest.mark.asyncio
    async def test_get_stats(self, storage):
        """통계 조회"""
        # 프로젝트 2개
        await storage.save_project({"id": "proj1", "name": "Project 1"})
        await storage.save_project({"id": "proj2", "name": "Project 2"})

        # context_entries 3개
        for i in range(3):
            await storage.save_context_entry({
                "id": f"entry{i}",
                "project_id": "proj1",
                "source": "slack",
                "entry_type": "message",
            })

        # drafts 생성
        # status='pending' 2개
        await storage.save_draft({"source_channel": "slack", "status": "pending", "match_status": "matched"})
        await storage.save_draft({"source_channel": "slack", "status": "pending", "match_status": "matched"})
        # status='approved' 1개
        await storage.save_draft({"source_channel": "slack", "status": "approved", "match_status": "matched"})
        # status='pending' (기본값) + match_status='pending_match' 1개
        await storage.save_draft({"source_channel": "slack", "match_status": "pending_match"})

        # 통계 조회
        stats = await storage.get_stats()
        assert stats["projects"] == 2
        assert stats["context_entries"] == 3
        # status='pending'인 항목: 3개 (위 3개 중 status='approved' 제외)
        assert stats["pending_drafts"] == 3
        # match_status='pending_match'인 항목: 1개
        assert stats["pending_matches"] == 1

    # ==========================================
    # Cleanup
    # ==========================================

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_dry_run(self, storage):
        """cleanup_old_entries의 dry_run 옵션"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # 오래된 context_entry 생성 (수동 타임스탬프)
        async with storage._connection.execute(
            """INSERT INTO context_entries
            (id, project_id, source, entry_type, collected_at)
            VALUES (?, ?, ?, ?, ?)""",
            ("old_entry", "proj1", "slack", "message", (datetime.now() - timedelta(days=100)).isoformat()),
        ) as cursor:
            pass
        await storage._connection.commit()

        # 오래된 draft (approved)
        async with storage._connection.execute(
            """INSERT INTO draft_responses
            (source_channel, status, created_at)
            VALUES (?, ?, ?)""",
            ("slack", "approved", (datetime.now() - timedelta(days=100)).isoformat()),
        ) as cursor:
            pass
        await storage._connection.commit()

        # dry_run=True
        counts = await storage.cleanup_old_entries(retention_days=90, dry_run=True)
        assert counts["context_entries"] == 1
        assert counts["draft_responses"] == 1

        # 실제로 삭제되지 않았는지 확인
        entries = await storage.get_context_entries("proj1", limit=100)
        assert len(entries) == 1

        drafts = await storage.list_drafts(limit=100)
        assert len(drafts) == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_actual_delete(self, storage):
        """cleanup_old_entries의 실제 삭제"""
        await storage.save_project({"id": "proj1", "name": "Project 1"})

        # 오래된 항목 생성
        async with storage._connection.execute(
            """INSERT INTO context_entries
            (id, project_id, source, entry_type, collected_at)
            VALUES (?, ?, ?, ?, ?)""",
            ("old_entry", "proj1", "slack", "message", (datetime.now() - timedelta(days=100)).isoformat()),
        ) as cursor:
            pass
        await storage._connection.commit()

        async with storage._connection.execute(
            """INSERT INTO draft_responses
            (source_channel, status, created_at)
            VALUES (?, ?, ?)""",
            ("slack", "approved", (datetime.now() - timedelta(days=100)).isoformat()),
        ) as cursor:
            pass
        await storage._connection.commit()

        # 실제 삭제 (dry_run=False)
        counts = await storage.cleanup_old_entries(retention_days=90, dry_run=False)
        assert counts["context_entries"] == 1
        assert counts["draft_responses"] == 1

        # 삭제 확인
        entries = await storage.get_context_entries("proj1", limit=100)
        assert len(entries) == 0

        drafts = await storage.list_drafts(limit=100)
        assert len(drafts) == 0
