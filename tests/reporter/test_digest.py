"""
DigestReport 테스트
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.reporter.digest import DigestReport


class TestDigestReport:
    """DigestReport 테스트"""

    @pytest.fixture
    def mock_gateway(self):
        storage = MagicMock()
        storage._connection = None
        return storage

    @pytest.fixture
    def mock_intel(self):
        storage = MagicMock()
        storage._connection = None
        return storage

    @pytest.fixture
    def digest(self, mock_gateway, mock_intel):
        return DigestReport(mock_gateway, mock_intel)

    @pytest.mark.asyncio
    async def test_generate_empty(self, digest):
        """빈 DB에서 Digest 생성"""
        data = await digest.generate()

        assert "date" in data
        assert data["messages"]["total"] == 0
        assert data["drafts"]["total"] == 0
        assert data["pending_matches"] == 0
        assert data["actions"] == 0

    def test_format_slack(self, digest):
        """Slack 포맷"""
        data = {
            "date": "02/13",
            "messages": {"total": 47, "urgent": 2, "high": 5},
            "drafts": {"total": 3, "pending": 2, "approved": 1},
            "pending_matches": 5,
            "actions": 8,
        }

        text = digest.format_slack(data)
        assert "02/13" in text
        assert "47" in text
        assert "긴급 2" in text
        assert "높음 5" in text
        assert "대기 2" in text
        assert "승인 1" in text
        assert "미매칭" in text
        assert "8" in text

    @pytest.mark.asyncio
    async def test_generate_with_none_storage(self):
        """storage가 None이어도 에러 없이 동작"""
        digest = DigestReport(None, None)
        data = await digest.generate()
        assert data["messages"]["total"] == 0
