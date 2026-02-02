#!/usr/bin/env python3
"""
Auto Model Router - 작업 유형 분류 및 모델 선택 (v14.0)

v14.0 변경사항:
- 복잡도 판단 로직 제거 (복잡도 계산 생략)
- 작업 유형 분류 추가: 문서 작업 vs 개발 작업
- Ralplan + Critic 항상 실행을 위한 classify_task_type() 함수 추가

모델 선택은 여전히 지원:
- 모델 매핑: complexity → haiku/sonnet/opus 자동 라우팅
- 비용 추적: 모델별 사용량 로깅
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


# 동적 프로젝트 루트 감지
def _get_project_root() -> Path:
    """프로젝트 루트 디렉토리를 동적으로 감지"""
    if env_root := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent.parent
    if (project_root / ".claude").exists():
        return project_root
    return Path.cwd()


PROJECT_ROOT = _get_project_root()
STATS_DIR = PROJECT_ROOT / ".omc" / "stats"
MODEL_STATS_FILE = STATS_DIR / "model_usage.json"


class Complexity(Enum):
    """작업 복잡도 레벨"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelTier(Enum):
    """모델 티어"""
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


# =============================================================================
# v14.0 신규: 작업 유형 분류 (문서 vs 개발)
# =============================================================================

class TaskType(Enum):
    """작업 유형"""
    DOCS = "docs"      # 문서 작업 → Ralplan + Critic + Writer
    DEV = "dev"        # 개발 작업 → Ralplan + Critic + Ralph + Architect


# 문서 작업 키워드 (이 키워드 포함 시 문서 작업으로 분류)
DOCS_KEYWORDS = [
    # 영어
    "docs", "documentation", "readme", "README",
    "markdown", "guide", "tutorial", "checklist",
    "meeting notes", "specification", "spec",
    # 한글
    "문서", "PRD", "설계", "기획", "명세",
    "설명", "가이드", "체크리스트", "회의록",
    "정리", "작성", "업데이트",
    # 확장자
    ".md",
]


def classify_task_type(description: str) -> TaskType:
    """
    작업 유형 분류 (v14.0 신규)

    복잡도 계산 없이 단순히 문서 작업인지 개발 작업인지만 판단

    Args:
        description: 작업 설명

    Returns:
        TaskType.DOCS 또는 TaskType.DEV
    """
    description_lower = description.lower()

    for keyword in DOCS_KEYWORDS:
        if keyword.lower() in description_lower:
            return TaskType.DOCS

    return TaskType.DEV


def get_workflow_for_type(task_type: TaskType) -> dict:
    """
    작업 유형에 따른 워크플로우 반환

    Args:
        task_type: 작업 유형

    Returns:
        워크플로우 정보 딕셔너리
    """
    if task_type == TaskType.DOCS:
        return {
            "type": "docs",
            "phases": ["ralplan", "critic", "writer"],
            "needs_ralph": False,
            "needs_architect": False,
            "completion_tag": "DOCS_COMPLETE",
        }
    else:
        return {
            "type": "dev",
            "phases": ["ralplan", "critic", "ultrawork", "ralph", "architect"],
            "needs_ralph": True,
            "needs_architect": True,
            "completion_tag": "TASK_COMPLETE",
        }


# =============================================================================
# 기존: 복잡도 키워드 매핑 (모델 선택용으로 유지)
# =============================================================================

# 복잡도 키워드 매핑
COMPLEXITY_KEYWORDS = {
    "high": [
        "architecture",
        "refactor",
        "migrate",
        "redesign",
        "rewrite",
        "debug complex",
        "race condition",
        "deadlock",
        "memory leak",
        "performance optimization",
        "security vulnerability",
        "multi-file",
        "cross-cutting",
        "system-wide",
        "대규모",
        "아키텍처",
        "리팩토링",
        "마이그레이션",
    ],
    "low": [
        "lookup",
        "find",
        "search",
        "list",
        "show",
        "get",
        "read",
        "simple",
        "quick",
        "trivial",
        "typo",
        "comment",
        "조회",
        "검색",
        "찾기",
        "간단한",
        "오타",
    ],
}

# 작업 유형별 기본 복잡도
TASK_TYPE_COMPLEXITY = {
    # LOW 작업
    "lookup": Complexity.LOW,
    "search": Complexity.LOW,
    "find": Complexity.LOW,
    "read": Complexity.LOW,
    "list": Complexity.LOW,
    # MEDIUM 작업
    "implement": Complexity.MEDIUM,
    "feature": Complexity.MEDIUM,
    "fix": Complexity.MEDIUM,
    "add": Complexity.MEDIUM,
    "update": Complexity.MEDIUM,
    "test": Complexity.MEDIUM,
    # HIGH 작업
    "refactor": Complexity.HIGH,
    "architect": Complexity.HIGH,
    "migrate": Complexity.HIGH,
    "debug_complex": Complexity.HIGH,
    "security": Complexity.HIGH,
}

# 복잡도 → 모델 매핑
COMPLEXITY_MODEL_MAP = {
    Complexity.LOW: ModelTier.HAIKU,
    Complexity.MEDIUM: ModelTier.SONNET,
    Complexity.HIGH: ModelTier.OPUS,
}

# 모델별 예상 토큰 비용 (상대적)
MODEL_TOKEN_COST = {
    ModelTier.HAIKU: 1.0,
    ModelTier.SONNET: 3.0,
    ModelTier.OPUS: 15.0,
}


@dataclass
class ComplexityAnalysis:
    """복잡도 분석 결과"""
    complexity: Complexity
    recommended_model: ModelTier
    confidence: float  # 0.0 ~ 1.0
    factors: dict[str, any]
    reasoning: str


@dataclass
class TaskContext:
    """작업 컨텍스트"""
    description: str
    task_type: Optional[str] = None
    affected_files: int = 1
    estimated_lines: int = 0
    has_tests: bool = False
    involves_api: bool = False
    involves_database: bool = False
    keywords: list[str] = None

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class ModelRouter:
    """모델 라우터 클래스"""

    def __init__(self):
        self.stats = {
            "total_routings": 0,
            "by_model": {
                ModelTier.HAIKU.value: 0,
                ModelTier.SONNET.value: 0,
                ModelTier.OPUS.value: 0,
            },
            "by_complexity": {
                Complexity.LOW.value: 0,
                Complexity.MEDIUM.value: 0,
                Complexity.HIGH.value: 0,
            },
            "estimated_cost_units": 0.0,
        }
        self._load_stats()

    def _load_stats(self):
        """통계 파일 로드"""
        STATS_DIR.mkdir(parents=True, exist_ok=True)
        if MODEL_STATS_FILE.exists():
            try:
                with open(MODEL_STATS_FILE, "r", encoding="utf-8") as f:
                    saved_stats = json.load(f)
                    self.stats.update(saved_stats)
            except (json.JSONDecodeError, OSError):
                pass

    def _save_stats(self):
        """통계 파일 저장"""
        STATS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(MODEL_STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _extract_keywords(self, text: str) -> list[str]:
        """텍스트에서 키워드 추출"""
        text_lower = text.lower()
        found_keywords = []

        for complexity, keywords in COMPLEXITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    found_keywords.append((keyword, complexity))

        return found_keywords

    def _analyze_file_count(self, count: int) -> tuple[Complexity, float]:
        """파일 수 기반 복잡도 분석"""
        if count <= 1:
            return Complexity.LOW, 0.9
        elif count <= 5:
            return Complexity.MEDIUM, 0.8
        else:
            return Complexity.HIGH, 0.85

    def _analyze_keywords(self, keywords: list[tuple[str, str]]) -> tuple[Complexity, float]:
        """키워드 기반 복잡도 분석"""
        if not keywords:
            return Complexity.MEDIUM, 0.5  # 기본값

        high_count = sum(1 for _, c in keywords if c == "high")
        low_count = sum(1 for _, c in keywords if c == "low")

        if high_count > 0:
            return Complexity.HIGH, min(0.9, 0.6 + high_count * 0.1)
        elif low_count > high_count:
            return Complexity.LOW, min(0.9, 0.6 + low_count * 0.1)
        else:
            return Complexity.MEDIUM, 0.7

    def _analyze_task_type(self, task_type: Optional[str]) -> tuple[Complexity, float]:
        """작업 유형 기반 복잡도 분석"""
        if not task_type:
            return Complexity.MEDIUM, 0.5

        complexity = TASK_TYPE_COMPLEXITY.get(task_type.lower(), Complexity.MEDIUM)
        return complexity, 0.8

    def analyze_complexity(self, context: TaskContext) -> ComplexityAnalysis:
        """
        작업 복잡도 분석

        Args:
            context: 작업 컨텍스트

        Returns:
            ComplexityAnalysis 객체
        """
        factors = {}
        complexity_scores = {
            Complexity.LOW: 0.0,
            Complexity.MEDIUM: 0.0,
            Complexity.HIGH: 0.0,
        }

        # 1. 파일 수 분석 (가중치: 0.3)
        file_complexity, file_confidence = self._analyze_file_count(context.affected_files)
        factors["file_count"] = {
            "value": context.affected_files,
            "complexity": file_complexity.value,
            "confidence": file_confidence,
        }
        complexity_scores[file_complexity] += 0.3 * file_confidence

        # 2. 키워드 분석 (가중치: 0.35)
        extracted_keywords = self._extract_keywords(context.description)
        keyword_complexity, keyword_confidence = self._analyze_keywords(extracted_keywords)
        factors["keywords"] = {
            "found": [k for k, _ in extracted_keywords],
            "complexity": keyword_complexity.value,
            "confidence": keyword_confidence,
        }
        complexity_scores[keyword_complexity] += 0.35 * keyword_confidence

        # 3. 작업 유형 분석 (가중치: 0.25)
        type_complexity, type_confidence = self._analyze_task_type(context.task_type)
        factors["task_type"] = {
            "type": context.task_type,
            "complexity": type_complexity.value,
            "confidence": type_confidence,
        }
        complexity_scores[type_complexity] += 0.25 * type_confidence

        # 4. 추가 요소 (가중치: 0.1)
        additional_score = 0.0
        additional_factors = []

        if context.involves_api:
            additional_score += 0.3
            additional_factors.append("API involved")
        if context.involves_database:
            additional_score += 0.3
            additional_factors.append("Database involved")
        if context.estimated_lines > 200:
            additional_score += 0.2
            additional_factors.append("Large change")
        if not context.has_tests:
            additional_score += 0.1
            additional_factors.append("No tests")

        factors["additional"] = {
            "factors": additional_factors,
            "score": additional_score,
        }

        # 추가 요소는 MEDIUM/HIGH 쪽으로 가중
        if additional_score > 0.5:
            complexity_scores[Complexity.HIGH] += 0.1 * additional_score
        elif additional_score > 0:
            complexity_scores[Complexity.MEDIUM] += 0.1 * additional_score

        # 최종 복잡도 결정
        final_complexity = max(complexity_scores, key=complexity_scores.get)
        final_confidence = complexity_scores[final_complexity]

        # 신뢰도 정규화 (0.5 ~ 0.95)
        final_confidence = min(0.95, max(0.5, final_confidence))

        # 추천 모델
        recommended_model = COMPLEXITY_MODEL_MAP[final_complexity]

        # 추론 설명 생성
        reasoning = self._generate_reasoning(final_complexity, factors)

        return ComplexityAnalysis(
            complexity=final_complexity,
            recommended_model=recommended_model,
            confidence=final_confidence,
            factors=factors,
            reasoning=reasoning,
        )

    def _generate_reasoning(self, complexity: Complexity, factors: dict) -> str:
        """추론 설명 생성"""
        parts = []

        file_count = factors.get("file_count", {}).get("value", 1)
        if file_count > 5:
            parts.append(f"영향 파일 {file_count}개로 대규모 변경")
        elif file_count > 1:
            parts.append(f"영향 파일 {file_count}개")

        keywords = factors.get("keywords", {}).get("found", [])
        if keywords:
            parts.append(f"키워드: {', '.join(keywords[:3])}")

        task_type = factors.get("task_type", {}).get("type")
        if task_type:
            parts.append(f"작업 유형: {task_type}")

        additional = factors.get("additional", {}).get("factors", [])
        if additional:
            parts.append(f"추가 요소: {', '.join(additional)}")

        if not parts:
            parts.append("기본 복잡도 추정")

        return f"[{complexity.value.upper()}] " + " | ".join(parts)

    def route(self, context: TaskContext) -> tuple[ModelTier, ComplexityAnalysis]:
        """
        작업에 적합한 모델 라우팅

        Args:
            context: 작업 컨텍스트

        Returns:
            (추천 모델, 분석 결과)
        """
        analysis = self.analyze_complexity(context)

        # 통계 업데이트
        self.stats["total_routings"] += 1
        self.stats["by_model"][analysis.recommended_model.value] += 1
        self.stats["by_complexity"][analysis.complexity.value] += 1
        self.stats["estimated_cost_units"] += MODEL_TOKEN_COST[analysis.recommended_model]
        self._save_stats()

        return analysis.recommended_model, analysis

    def route_simple(self, description: str, file_count: int = 1) -> str:
        """
        간단한 라우팅 (문자열 반환)

        Args:
            description: 작업 설명
            file_count: 영향받는 파일 수

        Returns:
            모델 이름 ("haiku", "sonnet", "opus")
        """
        context = TaskContext(
            description=description,
            affected_files=file_count,
        )
        model, _ = self.route(context)
        return model.value

    def get_stats(self) -> dict:
        """사용 통계 조회"""
        total = self.stats["total_routings"]
        if total == 0:
            return self.stats

        # 비율 계산
        stats_with_ratios = {
            **self.stats,
            "model_ratios": {
                model: round(count / total * 100, 1)
                for model, count in self.stats["by_model"].items()
            },
            "complexity_ratios": {
                complexity: round(count / total * 100, 1)
                for complexity, count in self.stats["by_complexity"].items()
            },
        }

        return stats_with_ratios

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "total_routings": 0,
            "by_model": {m.value: 0 for m in ModelTier},
            "by_complexity": {c.value: 0 for c in Complexity},
            "estimated_cost_units": 0.0,
        }
        self._save_stats()


# === 편의 함수 ===

def route_model(
    description: str,
    file_count: int = 1,
    task_type: Optional[str] = None,
) -> dict:
    """
    모델 라우팅 편의 함수

    Args:
        description: 작업 설명
        file_count: 영향받는 파일 수
        task_type: 작업 유형

    Returns:
        {
            "model": str,
            "complexity": str,
            "confidence": float,
            "reasoning": str
        }
    """
    router = ModelRouter()
    context = TaskContext(
        description=description,
        affected_files=file_count,
        task_type=task_type,
    )
    model, analysis = router.route(context)

    return {
        "model": model.value,
        "complexity": analysis.complexity.value,
        "confidence": analysis.confidence,
        "reasoning": analysis.reasoning,
    }


def classify_and_route(description: str, file_count: int = 1) -> dict:
    """
    작업 분류 + 모델 라우팅 통합 함수 (v14.0 신규)

    Args:
        description: 작업 설명
        file_count: 영향받는 파일 수

    Returns:
        {
            "task_type": "docs" | "dev",
            "workflow": {...},
            "model": "haiku" | "sonnet" | "opus",
            "reasoning": str
        }
    """
    # 1. 작업 유형 분류
    task_type = classify_task_type(description)
    workflow = get_workflow_for_type(task_type)

    # 2. 모델 선택 (복잡도 기반 - 모델 선택에만 사용)
    model_result = route_model(description, file_count)

    return {
        "task_type": task_type.value,
        "workflow": workflow,
        "model": model_result["model"],
        "reasoning": f"[{task_type.value.upper()}] {model_result['reasoning']}",
    }


if __name__ == "__main__":
    print("=== Model Router Test (v14.0) ===\n")

    # v14.0: 작업 유형 분류 테스트
    print("=== 작업 유형 분류 테스트 ===\n")

    type_test_cases = [
        ("PRD-0001 문서 업데이트", "docs"),
        ("README.md 수정", "docs"),
        ("API 설계 문서 작성", "docs"),
        ("로그인 기능 구현", "dev"),
        ("버그 수정: 인증 오류", "dev"),
        ("리팩토링 작업", "dev"),
        ("체크리스트 정리", "docs"),
    ]

    for desc, expected in type_test_cases:
        result = classify_task_type(desc)
        match = "O" if result.value == expected else "X"
        print(f"{match} '{desc}' → {result.value} (예상: {expected})")

    print("\n=== 통합 분류 + 라우팅 테스트 ===\n")

    integrated_cases = [
        "PRD-0002 문서 업데이트",
        "로그인 API 구현",
        "아키텍처 리팩토링 (10개 파일)",
    ]

    for desc in integrated_cases:
        result = classify_and_route(desc, file_count=3)
        print(f"작업: {desc}")
        print(f"  유형: {result['task_type']}")
        print(f"  모델: {result['model']}")
        print(f"  워크플로우: {result['workflow']['phases']}")
        print(f"  Ralph 필요: {result['workflow']['needs_ralph']}")
        print()

    # 기존 테스트
    print("=== 모델 라우팅 테스트 (기존) ===\n")

    router = ModelRouter()

    test_cases = [
        {
            "description": "Find the definition of UserService class",
            "file_count": 1,
            "expected": "haiku",
        },
        {
            "description": "Add validation to the login form",
            "file_count": 2,
            "expected": "sonnet",
        },
        {
            "description": "Refactor the entire authentication system across all modules",
            "file_count": 10,
            "expected": "opus",
        },
    ]

    for i, case in enumerate(test_cases, 1):
        context = TaskContext(
            description=case["description"],
            affected_files=case["file_count"],
        )
        model, analysis = router.route(context)

        match = "O" if model.value == case["expected"] else "X"
        print(f"{i}. {match} {case['description'][:50]}...")
        print(f"   예상: {case['expected']}, 실제: {model.value}")
        print()
