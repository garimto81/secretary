"""ActionDispatcher 테스트"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.gateway.action_dispatcher import ActionDispatcher, DispatchResult
from scripts.gateway.models import NormalizedMessage, ChannelType, MessageType, Priority


@pytest.fixture
def dispatcher():
    """기본 dispatcher 인스턴스"""
    return ActionDispatcher()


@pytest.fixture
def dry_run_dispatcher():
    """dry_run 모드 dispatcher"""
    return ActionDispatcher(dry_run=True)


@pytest.fixture
def sample_message():
    """테스트용 샘플 메시지"""
    return NormalizedMessage(
        id="slack_C123_1234567890.123",
        channel=ChannelType.SLACK,
        channel_id="C123",
        sender_id="U456",
        sender_name="홍길동",
        text="2월 15일까지 보고서를 제출해주세요",
        message_type=MessageType.TEXT,
        priority=Priority.HIGH,
    )


class TestDispatch:
    """dispatch() 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_dispatch_deadline_creates_todo(self, dispatcher, sample_message):
        """deadline 액션 -> TODO 파일 생성"""
        actions = ["deadline:2/15 까지"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path(r"C:\claude\secretary\output\todos\2026-02-12.md")
            results = await dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert results[0].action == "deadline:2/15 까지"
        assert results[0].success is True
        assert results[0].output_path is not None
        mock_todo.assert_called_once()

        # 호출 인수 확인
        call_args = mock_todo.call_args
        assert call_args[1]["priority"] == "high"
        assert call_args[1]["sender"] == "홍길동"
        assert "[slack]" in call_args[1]["title"].lower()

    @pytest.mark.asyncio
    async def test_dispatch_action_request_creates_todo(self, dispatcher, sample_message):
        """action_request 액션 -> TODO 파일 생성"""
        actions = ["action_request:검토"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path(r"C:\claude\secretary\output\todos\2026-02-12.md")
            results = await dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert results[0].action == "action_request:검토"
        assert results[0].success is True
        assert results[0].output_path is not None
        mock_todo.assert_called_once()

        # 호출 인수 확인
        call_args = mock_todo.call_args
        assert "검토" in call_args[1]["title"]

    @pytest.mark.asyncio
    async def test_dispatch_question_returns_success_without_action(self, dispatcher, sample_message):
        """question 액션은 로그만 출력하고 success 반환"""
        actions = ["question"]
        results = await dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert results[0].action == "question"
        assert results[0].success is True
        assert results[0].output_path is None

    @pytest.mark.asyncio
    async def test_dispatch_empty_actions(self, dispatcher, sample_message):
        """빈 액션 리스트"""
        results = await dispatcher.dispatch(sample_message, [])
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_dispatch_multiple_actions(self, dispatcher, sample_message):
        """복수 액션 처리"""
        actions = ["deadline:2/15 까지", "action_request:검토", "question"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path(r"C:\claude\secretary\output\todos\2026-02-12.md")
            results = await dispatcher.dispatch(sample_message, actions)

        # deadline + action_request + question = 3
        assert len(results) == 3
        assert mock_todo.call_count == 2  # deadline + action_request만 TODO 생성

    @pytest.mark.asyncio
    async def test_dispatch_todo_failure_returns_error(self, dispatcher, sample_message):
        """TODO 생성 실패 시 에러 반환"""
        actions = ["deadline:2/15 까지"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.side_effect = Exception("파일 쓰기 실패")
            results = await dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert results[0].success is False
        assert "파일 쓰기 실패" in results[0].error

    @pytest.mark.asyncio
    async def test_dispatch_unknown_action_returns_error(self, dispatcher, sample_message):
        """알 수 없는 액션 타입 -> 에러 반환"""
        actions = ["unknown_action:test"]
        results = await dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert results[0].success is False
        assert "Unknown action type" in results[0].error


class TestPriorityMapping:
    """우선순위 매핑 테스트"""

    @pytest.mark.asyncio
    async def test_urgent_maps_to_high(self, dispatcher):
        """URGENT -> high"""
        msg = NormalizedMessage(
            id="test1",
            channel=ChannelType.SLACK,
            channel_id="C1",
            sender_id="U1",
            sender_name="테스터",
            text="긴급 요청",
            priority=Priority.URGENT,
        )
        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path("test.md")
            await dispatcher.dispatch(msg, ["action_request:요청"])

        call_args = mock_todo.call_args
        assert call_args[1]["priority"] == "high"

    @pytest.mark.asyncio
    async def test_high_maps_to_high(self, dispatcher):
        """HIGH -> high"""
        msg = NormalizedMessage(
            id="test2",
            channel=ChannelType.EMAIL,
            channel_id="inbox",
            sender_id="sender@example.com",
            sender_name="발신자",
            text="중요 메일",
            priority=Priority.HIGH,
        )
        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path("test.md")
            await dispatcher.dispatch(msg, ["deadline:2026-02-15"])

        call_args = mock_todo.call_args
        assert call_args[1]["priority"] == "high"

    @pytest.mark.asyncio
    async def test_normal_maps_to_medium(self, dispatcher):
        """NORMAL -> medium"""
        msg = NormalizedMessage(
            id="test3",
            channel=ChannelType.SLACK,
            channel_id="C1",
            sender_id="U1",
            text="일반 요청",
            priority=Priority.NORMAL,
        )
        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path("test.md")
            await dispatcher.dispatch(msg, ["action_request:확인"])

        call_args = mock_todo.call_args
        assert call_args[1]["priority"] == "medium"

    @pytest.mark.asyncio
    async def test_low_maps_to_low(self, dispatcher):
        """LOW -> low"""
        msg = NormalizedMessage(
            id="test4",
            channel=ChannelType.TELEGRAM,
            channel_id="123",
            sender_id="456",
            text="낮은 우선순위",
            priority=Priority.LOW,
        )
        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path("test.md")
            await dispatcher.dispatch(msg, ["deadline:2026-03-01"])

        call_args = mock_todo.call_args
        assert call_args[1]["priority"] == "low"


class TestDryRunMode:
    """dry_run 모드 테스트"""

    @pytest.mark.asyncio
    async def test_dry_run_no_file_creation(self, dry_run_dispatcher, sample_message):
        """dry_run=True면 실제 파일 생성 없음"""
        actions = ["deadline:2026-02-15"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            results = await dry_run_dispatcher.dispatch(sample_message, actions)

        # dry_run이므로 append_todo_from_message 호출되지 않음
        mock_todo.assert_not_called()
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].output_path == Path("dry-run-todo.md")

    @pytest.mark.asyncio
    async def test_dry_run_calendar_message(self, dry_run_dispatcher, sample_message):
        """dry_run=True면 calendar도 dry-run 메시지만"""
        actions = ["deadline:2026-02-15"]

        results = await dry_run_dispatcher.dispatch(sample_message, actions)

        assert len(results) == 1
        assert "[DRY-RUN]" in (results[0].calendar_dry_run or "")


class TestTodoEntryCreation:
    """_create_todo_entry() 테스트"""

    def test_create_todo_entry_with_deadline(self, dispatcher, sample_message):
        """deadline이 있는 TODO 항목 생성"""
        entry = dispatcher._create_todo_entry(sample_message, deadline_text="2026-02-15")

        assert entry["type"] == "gateway"
        assert entry["priority"] == "high"  # sample_message.priority = HIGH
        assert entry["sender"] == "홍길동"
        assert entry["deadline"] == "2026-02-15"
        assert "[slack]" in entry["title"].lower()
        assert "홍길동" in entry["title"]
        assert "마감: 2026-02-15" in entry["title"]

    def test_create_todo_entry_with_keyword(self, dispatcher, sample_message):
        """keyword가 있는 TODO 항목 생성"""
        entry = dispatcher._create_todo_entry(sample_message, keyword="검토")

        assert entry["type"] == "gateway"
        assert "(검토)" in entry["title"]
        assert entry["deadline"] == ""

    def test_create_todo_entry_truncates_long_text(self, dispatcher):
        """긴 메시지 텍스트는 50자로 자름"""
        long_msg = NormalizedMessage(
            id="test",
            channel=ChannelType.EMAIL,
            channel_id="inbox",
            sender_id="sender@example.com",
            sender_name="발신자",
            text="A" * 100,  # 100자
            priority=Priority.NORMAL,
        )

        entry = dispatcher._create_todo_entry(long_msg)
        # 타이틀에 "A" * 50 + "..." 포함
        assert "A" * 50 in entry["title"]
        assert "..." in entry["title"]


class TestDateParsing:
    """_is_parsable_date() 테스트"""

    def test_iso_date_is_parsable(self, dispatcher):
        """YYYY-MM-DD 형식은 파싱 가능"""
        assert dispatcher._is_parsable_date("2026-02-15") is True

    def test_korean_date_with_numbers_is_parsable(self, dispatcher):
        """숫자가 포함된 한글 날짜는 파싱 시도 가능"""
        assert dispatcher._is_parsable_date("2월 15일") is True

    def test_text_without_numbers_not_parsable(self, dispatcher):
        """숫자가 없으면 파싱 불가"""
        assert dispatcher._is_parsable_date("내일까지") is False

    def test_empty_string_not_parsable(self, dispatcher):
        """빈 문자열은 파싱 불가"""
        assert dispatcher._is_parsable_date("") is False


class TestCalendarDryRun:
    """_run_calendar_dry_run() 테스트"""

    @pytest.mark.asyncio
    async def test_calendar_dry_run_not_called_if_unparsable(self, dispatcher, sample_message):
        """파싱 불가능한 날짜는 calendar dry-run 실행 안 함"""
        actions = ["deadline:내일까지"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            mock_todo.return_value = Path("test.md")
            results = await dispatcher.dispatch(sample_message, actions)

        # calendar_dry_run이 None이어야 함
        assert results[0].calendar_dry_run is None

    @pytest.mark.asyncio
    async def test_calendar_dry_run_called_if_parsable(self, dispatcher, sample_message):
        """파싱 가능한 날짜는 calendar dry-run 실행"""
        actions = ["deadline:2026-02-15"]

        with patch("scripts.actions.todo_generator.append_todo_from_message", new_callable=AsyncMock) as mock_todo:
            with patch.object(dispatcher, "_run_calendar_dry_run", new_callable=AsyncMock) as mock_calendar:
                mock_todo.return_value = Path("test.md")
                mock_calendar.return_value = "Calendar dry-run output"
                results = await dispatcher.dispatch(sample_message, actions)

        mock_calendar.assert_called_once()
        assert results[0].calendar_dry_run == "Calendar dry-run output"
