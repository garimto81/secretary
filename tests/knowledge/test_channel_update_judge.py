"""ChannelUpdateJudge 단위 테스트"""
import json
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def judge():
    from scripts.knowledge.channel_update_judge import ChannelUpdateJudge
    return ChannelUpdateJudge(
        ollama_url="http://localhost:11434",
        ollama_model="qwen3:8b",
        ollama_timeout=5,
        sonnet_timeout=10,
        confidence_threshold=0.7,
    )


def _make_qwen_response(needs_update: bool, section: str | None, new_content: str | None, confidence: float, reasoning: str) -> str:
    return json.dumps({
        "needs_update": needs_update,
        "section": section,
        "new_content": new_content,
        "confidence": confidence,
        "reasoning": reasoning,
    }, ensure_ascii=False)


def _make_sonnet_response(needs_update: bool, section: str | None, new_content: str | None, reasoning: str) -> str:
    return json.dumps({
        "needs_update": needs_update,
        "section": section,
        "new_content": new_content,
        "reasoning": reasoning,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChannelUpdateJudgeHighConfQwen:
    @pytest.mark.asyncio
    async def test_judge_needs_update_high_conf_qwen(self, judge):
        """Qwen confidence >= 0.7 → Sonnet 호출 없이 즉시 결정"""
        qwen_text = _make_qwen_response(
            needs_update=True,
            section="핵심 의사결정",
            new_content="- v3.0 출시 확정",
            confidence=0.9,
            reasoning="팀의 공식 결정사항",
        )
        with patch.object(judge, "_judge_with_qwen", new=AsyncMock()) as mock_qwen, \
             patch.object(judge, "_judge_with_sonnet", new=AsyncMock()) as mock_sonnet:
            from scripts.knowledge.channel_update_judge import UpdateDecision
            mock_qwen.return_value = UpdateDecision(
                needs_update=True,
                section="핵심 의사결정",
                new_content="- v3.0 출시 확정",
                judged_by="qwen",
                confidence=0.9,
                reasoning="팀의 공식 결정사항",
            )
            result = await judge.judge("v3.0 출시 결정했습니다", "C_TEST", "기존 PRD")

            mock_qwen.assert_called_once()
            mock_sonnet.assert_not_called()
            assert result.needs_update is True
            assert result.judged_by == "qwen"
            assert result.confidence == 0.9
            assert result.section == "핵심 의사결정"


class TestChannelUpdateJudgeLowConfQwen:
    @pytest.mark.asyncio
    async def test_judge_no_update_low_conf_qwen(self, judge):
        """Qwen confidence < 0.7 → Sonnet 에스컬레이션"""
        from scripts.knowledge.channel_update_judge import UpdateDecision

        low_conf_decision = UpdateDecision(
            needs_update=False,
            section=None,
            new_content=None,
            judged_by="qwen",
            confidence=0.4,
            reasoning="판단 불확실",
        )
        sonnet_decision = UpdateDecision(
            needs_update=True,
            section="주요 토픽",
            new_content="- 새로운 토픽",
            judged_by="sonnet",
            confidence=0.85,
            reasoning="Sonnet 정밀 판단",
        )
        with patch.object(judge, "_judge_with_qwen", new=AsyncMock(return_value=low_conf_decision)), \
             patch.object(judge, "_judge_with_sonnet", new=AsyncMock(return_value=sonnet_decision)):
            result = await judge.judge("어떤 메시지", "C_TEST", "PRD 내용")

            assert result.judged_by == "sonnet"
            assert result.confidence == 0.85


class TestChannelUpdateJudgeQwenError:
    @pytest.mark.asyncio
    async def test_judge_fallback_on_qwen_error(self, judge):
        """Qwen 실패 → Sonnet 호출"""
        from scripts.knowledge.channel_update_judge import UpdateDecision

        sonnet_decision = UpdateDecision(
            needs_update=False,
            section=None,
            new_content=None,
            judged_by="sonnet",
            confidence=0.85,
            reasoning="단순 잡담",
        )
        with patch.object(judge, "_judge_with_qwen", new=AsyncMock(side_effect=ConnectionError("Ollama 연결 실패"))), \
             patch.object(judge, "_judge_with_sonnet", new=AsyncMock(return_value=sonnet_decision)):
            result = await judge.judge("안녕하세요", "C_TEST", "")

            assert result.judged_by == "sonnet"


class TestChannelUpdateJudgeNoUpdate:
    @pytest.mark.asyncio
    async def test_judge_no_update(self, judge):
        """needs_update=false 케이스"""
        from scripts.knowledge.channel_update_judge import UpdateDecision

        no_update_decision = UpdateDecision(
            needs_update=False,
            section=None,
            new_content=None,
            judged_by="qwen",
            confidence=0.95,
            reasoning="단순 인사말",
        )
        with patch.object(judge, "_judge_with_qwen", new=AsyncMock(return_value=no_update_decision)), \
             patch.object(judge, "_judge_with_sonnet", new=AsyncMock()) as mock_sonnet:
            result = await judge.judge("안녕하세요!", "C_TEST", "PRD 내용")

            assert result.needs_update is False
            assert result.section is None
            mock_sonnet.assert_not_called()


class TestChannelUpdateJudgeLoadPRD:
    def test_load_prd_returns_empty_for_missing(self, tmp_path):
        """PRD 파일 없으면 빈 문자열 반환"""
        with patch("scripts.knowledge.channel_update_judge.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_update_judge import ChannelUpdateJudge
            j = ChannelUpdateJudge()
            result = j._load_prd("C_NONEXISTENT")
            assert result == ""

    def test_load_prd_returns_content(self, tmp_path):
        """PRD 파일 있으면 내용 반환"""
        prd_file = tmp_path / "C_LOAD.md"
        prd_file.write_text("# 테스트 PRD\n## 채널 개요\n설명\n", encoding="utf-8")

        with patch("scripts.knowledge.channel_update_judge.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_update_judge import ChannelUpdateJudge
            j = ChannelUpdateJudge()
            result = j._load_prd("C_LOAD")
            assert "테스트 PRD" in result


class TestChannelUpdateJudgeParseDecision:
    def test_parse_decision_valid_json(self, judge):
        """유효한 JSON 파싱"""
        text = _make_qwen_response(True, "주요 토픽", "- 새 토픽", 0.8, "유효한 결정")
        decision = judge._parse_decision(text, judged_by="qwen")
        assert decision.needs_update is True
        assert decision.section == "주요 토픽"
        assert decision.confidence == 0.8
        assert decision.judged_by == "qwen"

    def test_parse_decision_invalid_json_returns_fallback(self, judge):
        """JSON 파싱 실패 시 fallback 반환"""
        decision = judge._parse_decision("JSON이 아닌 텍스트", judged_by="qwen")
        assert decision.needs_update is False
        assert decision.judged_by == "fallback"
        assert decision.confidence == 0.0

    def test_parse_decision_json_in_text(self, judge):
        """텍스트 중간에 JSON 포함 시 추출"""
        text = f"분석 결과: {_make_qwen_response(False, None, None, 0.9, '잡담')} 끝"
        decision = judge._parse_decision(text, judged_by="qwen")
        assert decision.needs_update is False
        assert decision.confidence == 0.9


class TestChannelUpdateJudgeAllFail:
    @pytest.mark.asyncio
    async def test_judge_returns_fallback_when_all_fail(self, judge):
        """Qwen + Sonnet 모두 실패 시 fallback 반환"""
        with patch.object(judge, "_judge_with_qwen", new=AsyncMock(side_effect=RuntimeError("Qwen 오류"))), \
             patch.object(judge, "_judge_with_sonnet", new=AsyncMock(side_effect=RuntimeError("Sonnet 오류"))):
            result = await judge.judge("메시지", "C_TEST", "")

            assert result.judged_by == "fallback"
            assert result.needs_update is False
            assert result.confidence == 0.0
