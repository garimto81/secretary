"""EscalationRouter — Qwen 분석 결과 기반 Sonnet 에스컬레이션 판단"""
from dataclasses import dataclass

TECH_TERMS = {
    "api", "gateway", "pipeline", "async", "sqlite", "llm", "oauth",
    "webhook", "docker", "kubernetes", "ci", "cd", "deploy", "server",
    "database", "query", "index", "schema", "migration", "endpoint",
    "jwt", "token", "auth", "ssl", "tls", "nginx", "redis", "celery",
}


@dataclass
class EscalationDecision:
    should_escalate: bool
    reason: str  # "low_confidence", "high_complexity", "escalation_intent", "long_input"
    confidence_score: float
    complexity_score: float


class EscalationRouter:
    def __init__(
        self,
        confidence_threshold: float = 0.6,
        complexity_threshold: float = 0.7,
        token_count_threshold: int = 500,
    ):
        self.confidence_threshold = confidence_threshold
        self.complexity_threshold = complexity_threshold
        self.token_count_threshold = token_count_threshold
        self.escalation_intents = {
            "technical_deep_dive",
            "architecture_review",
            "debug_investigation",
        }

    def _calc_complexity(self, text: str) -> float:
        score = 0.0
        if "```" in text:
            score += 0.3
        if len(text) > 500:
            score += 0.2
        words = text.lower().split()
        if words:
            density = len(set(words) & TECH_TERMS) / len(words)
            score += min(density * 3.0, 0.3)
        if text.count("?") + text.count("\uff1f") >= 3:
            score += 0.1
        english_words = [w for w in words if w.isascii() and w.isalpha()]
        if words and len(english_words) / len(words) > 0.3:
            score += 0.1
        return min(score, 1.0)

    def decide(self, confidence: float, intent: str, original_text: str) -> EscalationDecision:
        complexity = self._calc_complexity(original_text)
        word_count = len(original_text.split())

        if confidence < self.confidence_threshold:
            return EscalationDecision(True, "low_confidence", confidence, complexity)
        if complexity > self.complexity_threshold:
            return EscalationDecision(True, "high_complexity", confidence, complexity)
        if intent in self.escalation_intents:
            return EscalationDecision(True, "escalation_intent", confidence, complexity)
        if word_count > self.token_count_threshold:
            return EscalationDecision(True, "long_input", confidence, complexity)
        return EscalationDecision(False, "no_escalation", confidence, complexity)
