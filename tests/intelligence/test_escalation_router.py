"""
EscalationRouter 단위 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.escalation_router import EscalationRouter


class TestEscalationRouter:
    def setup_method(self):
        self.router = EscalationRouter(
            confidence_threshold=0.6,
            complexity_threshold=0.7,
            token_count_threshold=500,
        )

    def test_low_confidence(self):
        """confidence < threshold → should_escalate=True, reason=low_confidence"""
        decision = self.router.decide(0.4, "질문", "간단한 질문입니다")
        assert decision.should_escalate is True
        assert decision.reason == "low_confidence"
        assert decision.confidence_score == 0.4

    def test_high_complexity_code_block(self):
        """``` 코드블록 + 500자 이상 + 기술용어 → should_escalate=True, reason=high_complexity"""
        # 코드블록(+0.3) + 500자+(+0.2) + 기술용어 api gateway pipeline(+0.3) = 0.8 > 0.7
        long_text = "```python\napi gateway pipeline\n```\n" + "api gateway pipeline server database " * 20
        decision = self.router.decide(0.9, "질문", long_text)
        assert decision.should_escalate is True
        assert decision.reason == "high_complexity"

    def test_no_escalation(self):
        """confidence 높고 짧은 메시지 → should_escalate=False"""
        decision = self.router.decide(0.9, "잡담", "오늘 점심 뭐 먹을까요?")
        assert decision.should_escalate is False
        assert decision.reason == "no_escalation"

    def test_escalation_intent(self):
        """escalation_intents에 포함된 intent → should_escalate=True"""
        decision = self.router.decide(0.9, "technical_deep_dive", "아키텍처 리뷰 부탁드립니다")
        assert decision.should_escalate is True
        assert decision.reason == "escalation_intent"

    def test_escalation_intent_architecture_review(self):
        """architecture_review intent → should_escalate=True"""
        decision = self.router.decide(0.8, "architecture_review", "설계 검토")
        assert decision.should_escalate is True
        assert decision.reason == "escalation_intent"

    def test_escalation_intent_debug_investigation(self):
        """debug_investigation intent → should_escalate=True"""
        decision = self.router.decide(0.8, "debug_investigation", "버그 분석")
        assert decision.should_escalate is True
        assert decision.reason == "escalation_intent"

    def test_long_input(self):
        """501 단어 이상 → should_escalate=True, reason=long_input"""
        long_text = " ".join(["word"] * 502)
        decision = self.router.decide(0.9, "정보공유", long_text)
        assert decision.should_escalate is True
        assert decision.reason == "long_input"

    def test_fullwidth_question_mark(self):
        """전각 물음표 3개 이상 → complexity_score에 0.1 추가됨"""
        text = "이게 맞나요？ 왜 그럴까요？ 어떻게 해야 하나요？"
        decision_plain = self.router.decide(0.9, "질문", "이게 맞나요")
        decision_fullwidth = self.router.decide(0.9, "질문", text)
        assert decision_fullwidth.complexity_score >= decision_plain.complexity_score + 0.09

    def test_tech_terms_increase_complexity(self):
        """기술 용어가 많을수록 complexity_score 증가"""
        tech_text = "api gateway pipeline async sqlite llm oauth webhook docker kubernetes"
        plain_text = "오늘 날씨가 맑고 좋네요 산책 가고 싶어요 커피 마실까요"
        router = EscalationRouter()
        tech_complexity = router._calc_complexity(tech_text)
        plain_complexity = router._calc_complexity(plain_text)
        assert tech_complexity > plain_complexity

    def test_complexity_capped_at_1(self):
        """complexity_score는 1.0을 넘지 않음"""
        text = "```code```\n" + "api " * 200 + "?" * 10 + "english word " * 50
        decision = self.router.decide(0.9, "질문", text)
        assert decision.complexity_score <= 1.0

    def test_exact_confidence_threshold_not_escalated(self):
        """confidence == threshold → 에스컬레이션 안 함 (strictly less than)"""
        decision = self.router.decide(0.6, "잡담", "간단한 메시지")
        # complexity 낮고 intent 무해하면 escalate 안 함
        assert decision.should_escalate is False

    def test_priority_order_low_confidence_first(self):
        """low_confidence가 high_complexity보다 먼저 체크됨"""
        long_code = "```\n" + "code\n" * 50 + "```\n" + "질문 " * 100
        decision = self.router.decide(0.4, "질문", long_code)
        # confidence 체크가 먼저이므로 reason=low_confidence
        assert decision.reason == "low_confidence"
