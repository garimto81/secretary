"""
Work Tracker 테스트 공유 fixtures
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.storage import WorkTrackerStorage


@pytest.fixture
async def storage(tmp_path):
    db_path = tmp_path / "test_work_tracker.db"
    async with WorkTrackerStorage(db_path) as s:
        yield s
