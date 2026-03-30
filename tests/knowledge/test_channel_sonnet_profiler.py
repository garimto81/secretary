"""
ChannelSonnetProfiler 단위 테스트
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.knowledge.channel_sonnet_profiler import ChannelSonnetProfiler


@pytest.fixture
def sample_mastery_context():
    return {
        "top_keywords": ["gateway", "pipeline", "api", "slack", "python", "database", "token", "auth"],
        "key_decisions": ["REST API 대신 gRPC 도입", "SQLite WAL mode 사용", "OAuth2 인증 표준화"],
        "channel_summary": "백엔드 개발 채널",
    }


class TestChannelSonnetProfiler:

    def test_build_profile_skip_existing(self, tmp_path, sample_mastery_context):
        """기존 파일 있고 force=False → 7일 이내이면 스킵, 7일 이상이면 재생성"""
        from datetime import datetime, timedelta

        # 최신 파일 (2일 전) → 스킵해야 함
        existing_data = {
            "channel_id": "C_TEST",
            "built_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "channel_summary": "기존 요약",
            "key_topics": ["existing_topic"],
            "communication_style": "기술적",
            "key_decisions": [],
            "member_profiles": {},
            "response_guidelines": "기존 지침",
            "escalation_hints": [],
        }
        ctx_dir = tmp_path / "channel_contexts"
        ctx_dir.mkdir()
        (ctx_dir / "C_TEST.json").write_text(json.dumps(existing_data, ensure_ascii=False), encoding="utf-8")

        profiler = ChannelSonnetProfiler(model="sonnet")

        import asyncio

        async def run():
            with patch("scripts.knowledge.channel_sonnet_profiler.CONTEXT_DIR", ctx_dir):
                return await profiler.build_profile("C_TEST", sample_mastery_context, force=False)

        result = asyncio.run(run())
        # 7일 이내이므로 기존 내용 반환
        assert result["channel_summary"] == "기존 요약"
        assert result["key_topics"] == ["existing_topic"]

    def test_build_profile_fallback(self, tmp_path, sample_mastery_context):
        """claude_path=None → fallback JSON 생성"""
        ctx_dir = tmp_path / "channel_contexts"

        profiler = ChannelSonnetProfiler(model="sonnet")
        profiler.claude_path = None  # Claude CLI 없음으로 강제

        import asyncio

        async def run():
            with patch("scripts.knowledge.channel_sonnet_profiler.CONTEXT_DIR", ctx_dir):
                return await profiler.build_profile("C_FALLBACK", sample_mastery_context, force=True)

        result = asyncio.run(run())
        assert result["channel_id"] == "C_FALLBACK"
        assert "built_at" in result
        assert "channel_summary" in result
        assert "response_guidelines" in result

    def test_build_profile_creates_context_dir(self, tmp_path, sample_mastery_context):
        """CONTEXT_DIR 없어도 자동 생성"""
        ctx_dir = tmp_path / "nonexistent" / "channel_contexts"
        assert not ctx_dir.exists()

        profiler = ChannelSonnetProfiler(model="sonnet")
        profiler.claude_path = None

        import asyncio

        async def run():
            with patch("scripts.knowledge.channel_sonnet_profiler.CONTEXT_DIR", ctx_dir):
                return await profiler.build_profile("C_NEW", sample_mastery_context)

        asyncio.run(run())
        assert ctx_dir.exists()
        assert (ctx_dir / "C_NEW.json").exists()

    def test_calc_fallback_contains_keywords(self, tmp_path, sample_mastery_context):
        """fallback에 mastery_context keywords 포함"""
        profiler = ChannelSonnetProfiler()
        profiler.claude_path = None

        fallback = profiler._build_fallback("C_TEST", sample_mastery_context)

        for kw in sample_mastery_context["top_keywords"][:8]:
            assert kw in fallback["key_topics"]

    def test_fallback_decisions_limited_to_5(self, tmp_path):
        """fallback key_decisions는 최대 5개"""
        mastery = {
            "top_keywords": [],
            "key_decisions": [f"결정 {i}" for i in range(10)],
        }
        profiler = ChannelSonnetProfiler()
        fallback = profiler._build_fallback("C_TEST", mastery)
        assert len(fallback["key_decisions"]) <= 5

    def test_fallback_keywords_limited_to_8(self, tmp_path):
        """fallback key_topics는 최대 8개"""
        mastery = {
            "top_keywords": [f"kw{i}" for i in range(20)],
            "key_decisions": [],
        }
        profiler = ChannelSonnetProfiler()
        fallback = profiler._build_fallback("C_TEST", mastery)
        assert len(fallback["key_topics"]) <= 8

    def test_build_profile_sonnet_failure_uses_fallback(self, tmp_path, sample_mastery_context):
        """Sonnet 호출 실패 시 fallback 사용 (예외 전파 금지)"""
        ctx_dir = tmp_path / "channel_contexts"

        profiler = ChannelSonnetProfiler(model="sonnet")
        profiler.claude_path = "/fake/claude"  # 존재하지 않는 경로

        import asyncio

        async def run():
            with patch("scripts.knowledge.channel_sonnet_profiler.CONTEXT_DIR", ctx_dir):
                # _call_sonnet이 예외를 던져도 fallback 반환
                return await profiler.build_profile("C_FAIL", sample_mastery_context, force=True)

        result = asyncio.run(run())
        assert result["channel_id"] == "C_FAIL"
        assert "channel_summary" in result

    def test_force_true_overwrites_existing(self, tmp_path, sample_mastery_context):
        """force=True면 기존 파일 덮어씀"""
        ctx_dir = tmp_path / "channel_contexts"
        ctx_dir.mkdir()
        existing_data = {"channel_id": "C_OLD", "old_field": "old_value"}
        (ctx_dir / "C_OVERWRITE.json").write_text(json.dumps(existing_data), encoding="utf-8")

        profiler = ChannelSonnetProfiler()
        profiler.claude_path = None  # fallback 사용

        import asyncio

        async def run():
            with patch("scripts.knowledge.channel_sonnet_profiler.CONTEXT_DIR", ctx_dir):
                return await profiler.build_profile("C_OVERWRITE", sample_mastery_context, force=True)

        result = asyncio.run(run())
        # fallback으로 덮어써진 결과
        assert "old_field" not in result
        assert "built_at" in result
