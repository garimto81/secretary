"""
Intelligence 테스트 공유 fixtures
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ==========================================
# Mock Models
# ==========================================

class MockChannel:
    """NormalizedMessage.channel mock"""
    def __init__(self, value="slack"):
        self.value = value


@dataclass
class MockMessage:
    """NormalizedMessage mock"""
    id: str = "msg-001"
    text: str = "테스트 메시지입니다"
    sender_id: str = "U12345"
    sender_name: str = "TestUser"
    channel_id: str = "C09N8J3UJN9"
    channel: MockChannel = field(default_factory=lambda: MockChannel("slack"))


@dataclass
class MockEnrichedMessage:
    """EnrichedMessage mock"""
    original: MockMessage = field(default_factory=MockMessage)
    priority: str | None = None
    has_action: bool = False
    actions: list[str] = field(default_factory=list)


@dataclass
class MockPipelineResult:
    """PipelineResult mock"""
    priority: str | None = "normal"


@dataclass
class MockMatchResult:
    """ContextMatcher.match() 결과 mock"""
    matched: bool = False
    project_id: str | None = None
    project_name: str | None = None
    confidence: float = 0.0
    tier: str | None = None
    reason: str = ""


# ==========================================
# Shared Fixtures
# ==========================================

@pytest.fixture
def mock_storage():
    """mock IntelligenceStorage"""
    storage = AsyncMock()
    storage.find_by_message_id = AsyncMock(return_value=None)
    storage.save_draft = AsyncMock(return_value=1)
    storage.get_context_entries = AsyncMock(return_value=[])
    storage.save_project = AsyncMock()
    storage.get_project = AsyncMock(return_value=None)
    storage.list_projects = AsyncMock(return_value=[])
    storage.connect = AsyncMock()
    storage.close = AsyncMock()
    return storage


@pytest.fixture
def mock_registry():
    """mock ProjectRegistry"""
    registry = AsyncMock()
    registry.list_all = AsyncMock(return_value=[
        {
            "id": "secretary",
            "name": "Secretary",
            "keywords": ["daily report", "automation", "비서"],
            "description": "AI 비서 자동화 프로젝트",
            "slack_channels": ["C09N8J3UJN9"],
            "contacts": ["U12345"],
        },
        {
            "id": "wsoptv",
            "name": "WSOP TV Automation",
            "keywords": ["wsop", "방송", "자막", "영상"],
            "description": "WSOP 방송 자동화",
            "slack_channels": ["C0WSOP1234"],
            "contacts": [],
        },
    ])
    registry.get = AsyncMock(return_value={
        "id": "secretary",
        "name": "Secretary",
        "description": "AI 비서 자동화 프로젝트",
    })
    registry.find_by_channel = AsyncMock(return_value=None)
    registry.find_by_keyword = AsyncMock(return_value=[])
    registry.find_by_contact = AsyncMock(return_value=None)
    return registry


@pytest.fixture
def sample_message():
    """기본 테스트 메시지"""
    return MockMessage()


@pytest.fixture
def urgent_message():
    """긴급 테스트 메시지"""
    return MockMessage(
        id="msg-urgent-001",
        text="긴급: 서버 장애 발생! 즉시 확인 부탁드립니다.",
        sender_id="U99999",
        sender_name="Admin",
    )


@pytest.fixture
def enriched_message(sample_message):
    """EnrichedMessage mock"""
    return MockEnrichedMessage(original=sample_message)


@pytest.fixture
def urgent_enriched(urgent_message):
    """urgent EnrichedMessage mock"""
    return MockEnrichedMessage(original=urgent_message, priority="urgent")


@pytest.fixture
def normal_result():
    """normal priority PipelineResult"""
    return MockPipelineResult(priority="normal")


@pytest.fixture
def urgent_result():
    """urgent priority PipelineResult"""
    return MockPipelineResult(priority="urgent")


@pytest.fixture
def sample_projects():
    """테스트용 프로젝트 목록"""
    return [
        {
            "id": "secretary",
            "name": "Secretary",
            "keywords": ["daily report", "automation", "비서"],
            "description": "AI 비서 자동화 프로젝트",
        },
        {
            "id": "wsoptv",
            "name": "WSOP TV Automation",
            "keywords": ["wsop", "방송", "자막"],
            "description": "WSOP 방송 자동화",
        },
    ]
