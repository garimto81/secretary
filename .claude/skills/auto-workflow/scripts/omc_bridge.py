"""
omc_bridge.py - OMC + BKIT 통합 에이전트 브리지

OMC 32개 + BKIT 11개 = 43개 에이전트 통합 관리
병렬 호출 및 비교 검토 로직 포함
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import asyncio


class OMCSkill(Enum):
    """OMC 스킬 열거형"""
    RALPLAN = "oh-my-claudecode:ralplan"
    ULTRAWORK = "oh-my-claudecode:ultrawork"
    RALPH = "oh-my-claudecode:ralph"
    ARCHITECT = "oh-my-claudecode:architect"
    REVIEW = "oh-my-claudecode:review"
    BUILD_FIX = "oh-my-claudecode:build-fix"
    AUTOPILOT = "oh-my-claudecode:autopilot"
    ULTRAQA = "oh-my-claudecode:ultraqa"


class BKITSkill(Enum):
    """BKIT 스킬 열거형"""
    PDCA = "bkit:pdca"
    STARTER = "bkit:starter"
    DYNAMIC = "bkit:dynamic"
    ENTERPRISE = "bkit:enterprise"
    CODE_REVIEW = "bkit:code-review"
    DEVELOPMENT_PIPELINE = "bkit:development-pipeline"


class ModelTier(Enum):
    """모델 티어"""
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class AgentDomain(Enum):
    """에이전트 도메인 분류"""
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    SEARCH = "search"
    RESEARCH = "research"
    FRONTEND = "frontend"
    DOCS = "docs"
    VISUAL = "visual"
    PLANNING = "planning"
    TESTING = "testing"
    SECURITY = "security"
    BUILD = "build"
    TDD = "tdd"
    REVIEW = "review"
    DATA = "data"
    VERIFICATION = "verification"
    IMPROVEMENT = "improvement"
    GUIDE = "guide"
    BACKEND = "backend"
    ENTERPRISE = "enterprise"
    INFRA = "infra"
    PIPELINE = "pipeline"


@dataclass
class AgentInfo:
    """에이전트 정보"""
    agent_type: str
    model: ModelTier
    domain: AgentDomain
    source: str  # "omc" or "bkit"
    description: str = ""


@dataclass
class AgentConfig:
    """에이전트 호출 설정"""
    agent_type: str
    model: ModelTier
    prompt: str
    background: bool = False


@dataclass
class AgentResult:
    """에이전트 실행 결과"""
    agent_type: str
    success: bool
    output: str
    source: str  # "omc" or "bkit"
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class ComparisonResult:
    """병렬 비교 검토 결과"""
    omc_result: Optional[AgentResult] = None
    bkit_result: Optional[AgentResult] = None
    winner: Optional[str] = None  # "omc", "bkit", "both", "none"
    comparison_notes: str = ""
    merged_output: str = ""
    confidence: float = 0.0


@dataclass
class PlanResult:
    """계획 결과"""
    success: bool
    plan_path: str
    iterations: int
    consensus_reached: bool


@dataclass
class ExecutionResult:
    """실행 결과"""
    success: bool
    completed_tasks: List[str]
    failed_tasks: List[str]
    agents_spawned: int


@dataclass
class RalphResult:
    """Ralph 루프 결과"""
    success: bool
    iterations: int
    architect_approved: bool
    final_status: str


@dataclass
class VerificationResult:
    """검증 결과"""
    approved: bool
    feedback: str
    issues: List[str]
    match_percentage: float = 0.0  # BKIT gap-detector용


# =============================================================================
# 통합 에이전트 레지스트리 (43개)
# =============================================================================

UNIFIED_AGENT_REGISTRY: Dict[str, AgentInfo] = {
    # -------------------------------------------------------------------------
    # OMC 에이전트 (32개)
    # -------------------------------------------------------------------------
    # Analysis (3)
    "oh-my-claudecode:architect-low": AgentInfo(
        "oh-my-claudecode:architect-low", ModelTier.HAIKU, AgentDomain.ANALYSIS,
        "omc", "간단한 구조 분석"
    ),
    "oh-my-claudecode:architect-medium": AgentInfo(
        "oh-my-claudecode:architect-medium", ModelTier.SONNET, AgentDomain.ANALYSIS,
        "omc", "중간 규모 설계"
    ),
    "oh-my-claudecode:architect": AgentInfo(
        "oh-my-claudecode:architect", ModelTier.OPUS, AgentDomain.ANALYSIS,
        "omc", "복잡한 아키텍처 분석"
    ),
    # Execution (3)
    "oh-my-claudecode:executor-low": AgentInfo(
        "oh-my-claudecode:executor-low", ModelTier.HAIKU, AgentDomain.EXECUTION,
        "omc", "단순 코드 변경"
    ),
    "oh-my-claudecode:executor": AgentInfo(
        "oh-my-claudecode:executor", ModelTier.SONNET, AgentDomain.EXECUTION,
        "omc", "기능 구현"
    ),
    "oh-my-claudecode:executor-high": AgentInfo(
        "oh-my-claudecode:executor-high", ModelTier.OPUS, AgentDomain.EXECUTION,
        "omc", "복잡한 리팩토링"
    ),
    # Search (3)
    "oh-my-claudecode:explore": AgentInfo(
        "oh-my-claudecode:explore", ModelTier.HAIKU, AgentDomain.SEARCH,
        "omc", "기본 코드베이스 탐색"
    ),
    "oh-my-claudecode:explore-medium": AgentInfo(
        "oh-my-claudecode:explore-medium", ModelTier.SONNET, AgentDomain.SEARCH,
        "omc", "상세 코드 탐색"
    ),
    "oh-my-claudecode:explore-high": AgentInfo(
        "oh-my-claudecode:explore-high", ModelTier.OPUS, AgentDomain.SEARCH,
        "omc", "심층 코드 분석"
    ),
    # Research (2)
    "oh-my-claudecode:researcher-low": AgentInfo(
        "oh-my-claudecode:researcher-low", ModelTier.HAIKU, AgentDomain.RESEARCH,
        "omc", "빠른 문서 조회"
    ),
    "oh-my-claudecode:researcher": AgentInfo(
        "oh-my-claudecode:researcher", ModelTier.SONNET, AgentDomain.RESEARCH,
        "omc", "리서치"
    ),
    # Frontend (3)
    "oh-my-claudecode:designer-low": AgentInfo(
        "oh-my-claudecode:designer-low", ModelTier.HAIKU, AgentDomain.FRONTEND,
        "omc", "간단한 UI 수정"
    ),
    "oh-my-claudecode:designer": AgentInfo(
        "oh-my-claudecode:designer", ModelTier.SONNET, AgentDomain.FRONTEND,
        "omc", "UI 컴포넌트"
    ),
    "oh-my-claudecode:designer-high": AgentInfo(
        "oh-my-claudecode:designer-high", ModelTier.OPUS, AgentDomain.FRONTEND,
        "omc", "디자인 시스템"
    ),
    # Docs (1)
    "oh-my-claudecode:writer": AgentInfo(
        "oh-my-claudecode:writer", ModelTier.HAIKU, AgentDomain.DOCS,
        "omc", "문서 작성"
    ),
    # Visual (1)
    "oh-my-claudecode:vision": AgentInfo(
        "oh-my-claudecode:vision", ModelTier.SONNET, AgentDomain.VISUAL,
        "omc", "이미지/다이어그램 분석"
    ),
    # Planning (3)
    "oh-my-claudecode:planner": AgentInfo(
        "oh-my-claudecode:planner", ModelTier.OPUS, AgentDomain.PLANNING,
        "omc", "전략적 계획"
    ),
    "oh-my-claudecode:critic": AgentInfo(
        "oh-my-claudecode:critic", ModelTier.OPUS, AgentDomain.PLANNING,
        "omc", "계획 비평"
    ),
    "oh-my-claudecode:analyst": AgentInfo(
        "oh-my-claudecode:analyst", ModelTier.OPUS, AgentDomain.PLANNING,
        "omc", "사전 분석"
    ),
    # Testing (2)
    "oh-my-claudecode:qa-tester": AgentInfo(
        "oh-my-claudecode:qa-tester", ModelTier.SONNET, AgentDomain.TESTING,
        "omc", "테스트 실행"
    ),
    "oh-my-claudecode:qa-tester-high": AgentInfo(
        "oh-my-claudecode:qa-tester-high", ModelTier.OPUS, AgentDomain.TESTING,
        "omc", "복잡한 테스트"
    ),
    # Security (2)
    "oh-my-claudecode:security-reviewer-low": AgentInfo(
        "oh-my-claudecode:security-reviewer-low", ModelTier.HAIKU, AgentDomain.SECURITY,
        "omc", "빠른 보안 스캔"
    ),
    "oh-my-claudecode:security-reviewer": AgentInfo(
        "oh-my-claudecode:security-reviewer", ModelTier.OPUS, AgentDomain.SECURITY,
        "omc", "심층 보안 분석"
    ),
    # Build (2)
    "oh-my-claudecode:build-fixer-low": AgentInfo(
        "oh-my-claudecode:build-fixer-low", ModelTier.HAIKU, AgentDomain.BUILD,
        "omc", "단순 빌드 오류"
    ),
    "oh-my-claudecode:build-fixer": AgentInfo(
        "oh-my-claudecode:build-fixer", ModelTier.SONNET, AgentDomain.BUILD,
        "omc", "빌드 오류 수정"
    ),
    # TDD (2)
    "oh-my-claudecode:tdd-guide-low": AgentInfo(
        "oh-my-claudecode:tdd-guide-low", ModelTier.HAIKU, AgentDomain.TDD,
        "omc", "기본 테스트 제안"
    ),
    "oh-my-claudecode:tdd-guide": AgentInfo(
        "oh-my-claudecode:tdd-guide", ModelTier.SONNET, AgentDomain.TDD,
        "omc", "TDD 워크플로우"
    ),
    # Review (2)
    "oh-my-claudecode:code-reviewer-low": AgentInfo(
        "oh-my-claudecode:code-reviewer-low", ModelTier.HAIKU, AgentDomain.REVIEW,
        "omc", "빠른 코드 검토"
    ),
    "oh-my-claudecode:code-reviewer": AgentInfo(
        "oh-my-claudecode:code-reviewer", ModelTier.OPUS, AgentDomain.REVIEW,
        "omc", "상세 코드 리뷰"
    ),
    # Data (3)
    "oh-my-claudecode:scientist-low": AgentInfo(
        "oh-my-claudecode:scientist-low", ModelTier.HAIKU, AgentDomain.DATA,
        "omc", "간단한 데이터 확인"
    ),
    "oh-my-claudecode:scientist": AgentInfo(
        "oh-my-claudecode:scientist", ModelTier.SONNET, AgentDomain.DATA,
        "omc", "데이터 분석"
    ),
    "oh-my-claudecode:scientist-high": AgentInfo(
        "oh-my-claudecode:scientist-high", ModelTier.OPUS, AgentDomain.DATA,
        "omc", "ML/통계 분석"
    ),

    # -------------------------------------------------------------------------
    # BKIT 에이전트 (11개)
    # -------------------------------------------------------------------------
    "bkit:starter-guide": AgentInfo(
        "bkit:starter-guide", ModelTier.SONNET, AgentDomain.GUIDE,
        "bkit", "초보자 가이드"
    ),
    "bkit:bkend-expert": AgentInfo(
        "bkit:bkend-expert", ModelTier.SONNET, AgentDomain.BACKEND,
        "bkit", "BaaS 전문가"
    ),
    "bkit:enterprise-expert": AgentInfo(
        "bkit:enterprise-expert", ModelTier.OPUS, AgentDomain.ENTERPRISE,
        "bkit", "엔터프라이즈 전문가"
    ),
    "bkit:infra-architect": AgentInfo(
        "bkit:infra-architect", ModelTier.OPUS, AgentDomain.INFRA,
        "bkit", "인프라 아키텍트"
    ),
    "bkit:pipeline-guide": AgentInfo(
        "bkit:pipeline-guide", ModelTier.SONNET, AgentDomain.PIPELINE,
        "bkit", "파이프라인 가이드"
    ),
    "bkit:gap-detector": AgentInfo(
        "bkit:gap-detector", ModelTier.OPUS, AgentDomain.VERIFICATION,
        "bkit", "설계-구현 갭 분석"
    ),
    "bkit:design-validator": AgentInfo(
        "bkit:design-validator", ModelTier.SONNET, AgentDomain.VERIFICATION,
        "bkit", "설계 문서 검증"
    ),
    "bkit:code-analyzer": AgentInfo(
        "bkit:code-analyzer", ModelTier.SONNET, AgentDomain.REVIEW,
        "bkit", "코드 품질 분석"
    ),
    "bkit:qa-monitor": AgentInfo(
        "bkit:qa-monitor", ModelTier.SONNET, AgentDomain.TESTING,
        "bkit", "QA 모니터링"
    ),
    "bkit:pdca-iterator": AgentInfo(
        "bkit:pdca-iterator", ModelTier.SONNET, AgentDomain.IMPROVEMENT,
        "bkit", "Check-Act 반복 개선"
    ),
    "bkit:report-generator": AgentInfo(
        "bkit:report-generator", ModelTier.HAIKU, AgentDomain.DOCS,
        "bkit", "완료 보고서 생성"
    ),
}


# =============================================================================
# 도메인별 에이전트 매핑 (비교 검토용)
# =============================================================================

DOMAIN_AGENT_PAIRS: Dict[AgentDomain, Dict[str, List[str]]] = {
    # 코드 리뷰: OMC code-reviewer vs BKIT code-analyzer
    AgentDomain.REVIEW: {
        "omc": ["oh-my-claudecode:code-reviewer", "oh-my-claudecode:code-reviewer-low"],
        "bkit": ["bkit:code-analyzer"],
    },
    # 테스트/QA: OMC qa-tester vs BKIT qa-monitor
    AgentDomain.TESTING: {
        "omc": ["oh-my-claudecode:qa-tester", "oh-my-claudecode:qa-tester-high"],
        "bkit": ["bkit:qa-monitor"],
    },
    # 검증: OMC architect vs BKIT gap-detector
    AgentDomain.VERIFICATION: {
        "omc": ["oh-my-claudecode:architect"],
        "bkit": ["bkit:gap-detector", "bkit:design-validator"],
    },
    # 문서: OMC writer vs BKIT report-generator
    AgentDomain.DOCS: {
        "omc": ["oh-my-claudecode:writer"],
        "bkit": ["bkit:report-generator"],
    },
    # 분석: OMC architect vs BKIT enterprise-expert
    AgentDomain.ANALYSIS: {
        "omc": ["oh-my-claudecode:architect", "oh-my-claudecode:architect-medium", "oh-my-claudecode:architect-low"],
        "bkit": ["bkit:enterprise-expert", "bkit:infra-architect"],
    },
}


# BKIT 에이전트 → OMC 폴백 매핑
BKIT_TO_OMC_FALLBACK: Dict[str, str] = {
    "bkit:gap-detector": "oh-my-claudecode:architect",
    "bkit:design-validator": "oh-my-claudecode:architect-medium",
    "bkit:code-analyzer": "oh-my-claudecode:code-reviewer",
    "bkit:qa-monitor": "oh-my-claudecode:qa-tester",
    "bkit:pdca-iterator": "oh-my-claudecode:executor",
    "bkit:report-generator": "oh-my-claudecode:writer",
    "bkit:starter-guide": "oh-my-claudecode:writer",
    "bkit:bkend-expert": "oh-my-claudecode:architect-medium",
    "bkit:enterprise-expert": "oh-my-claudecode:architect",
    "bkit:infra-architect": "oh-my-claudecode:architect",
    "bkit:pipeline-guide": "oh-my-claudecode:executor",
}


class OMCBridge:
    """OMC + BKIT 통합 에이전트 브리지"""

    def __init__(self):
        self.registry = UNIFIED_AGENT_REGISTRY
        self.domain_pairs = DOMAIN_AGENT_PAIRS

    # -------------------------------------------------------------------------
    # 에이전트 조회
    # -------------------------------------------------------------------------

    def get_agent(self, agent_type: str) -> Optional[AgentInfo]:
        """에이전트 정보 조회"""
        return self.registry.get(agent_type)

    def get_agent_with_fallback(self, agent_type: str, force_omc: bool = True) -> Tuple[str, Optional[AgentInfo], bool]:
        """에이전트 조회 (BKIT 호출 불가 시 OMC로 폴백)

        BKIT 에이전트는 현재 Claude Code에서 직접 호출이 불가능합니다.
        따라서 bkit: prefix 에이전트는 항상 OMC 에이전트로 폴백됩니다.

        Args:
            agent_type: 요청된 에이전트 타입
            force_omc: True면 bkit: prefix 에이전트를 항상 OMC로 폴백 (기본값: True)

        Returns:
            Tuple[실제 사용할 agent_type, AgentInfo, 폴백 발생 여부]
        """
        # BKIT 에이전트인 경우 항상 OMC로 폴백 (force_omc=True일 때)
        if force_omc and agent_type.startswith("bkit:"):
            fallback = BKIT_TO_OMC_FALLBACK.get(agent_type)
            if fallback:
                fallback_agent = self.get_agent(fallback)
                if fallback_agent:
                    # 폴백 발생 로그 (호출자가 확인 가능)
                    return fallback, fallback_agent, True
            # 폴백 매핑이 없는 경우에도 표시
            return agent_type, None, True

        # OMC 에이전트 또는 force_omc=False인 경우
        agent = self.get_agent(agent_type)
        if agent:
            return agent_type, agent, False

        return agent_type, None, False

    def get_agents_by_domain(self, domain: AgentDomain) -> List[AgentInfo]:
        """도메인별 에이전트 목록"""
        return [info for info in self.registry.values() if info.domain == domain]

    def get_agents_by_source(self, source: str) -> List[AgentInfo]:
        """소스별 에이전트 목록 (omc 또는 bkit)"""
        return [info for info in self.registry.values() if info.source == source]

    def get_agents_by_model(self, model: ModelTier) -> List[AgentInfo]:
        """모델별 에이전트 목록"""
        return [info for info in self.registry.values() if info.model == model]

    # -------------------------------------------------------------------------
    # 비교 가능한 에이전트 쌍 조회
    # -------------------------------------------------------------------------

    def get_comparable_agents(self, domain: AgentDomain) -> Optional[Dict[str, List[str]]]:
        """특정 도메인에서 비교 가능한 OMC/BKIT 에이전트 쌍 반환"""
        return self.domain_pairs.get(domain)

    def find_bkit_counterpart(self, omc_agent: str) -> Optional[str]:
        """OMC 에이전트에 대응하는 BKIT 에이전트 찾기"""
        omc_info = self.get_agent(omc_agent)
        if not omc_info or omc_info.source != "omc":
            return None

        pairs = self.get_comparable_agents(omc_info.domain)
        if pairs and "bkit" in pairs and pairs["bkit"]:
            # 같은 모델 티어 우선, 없으면 첫 번째
            for bkit_agent in pairs["bkit"]:
                bkit_info = self.get_agent(bkit_agent)
                if bkit_info and bkit_info.model == omc_info.model:
                    return bkit_agent
            return pairs["bkit"][0]
        return None

    def find_omc_counterpart(self, bkit_agent: str) -> Optional[str]:
        """BKIT 에이전트에 대응하는 OMC 에이전트 찾기"""
        bkit_info = self.get_agent(bkit_agent)
        if not bkit_info or bkit_info.source != "bkit":
            return None

        pairs = self.get_comparable_agents(bkit_info.domain)
        if pairs and "omc" in pairs and pairs["omc"]:
            # 같은 모델 티어 우선
            for omc_agent in pairs["omc"]:
                omc_info = self.get_agent(omc_agent)
                if omc_info and omc_info.model == bkit_info.model:
                    return omc_agent
            return pairs["omc"][0]
        return None

    # -------------------------------------------------------------------------
    # 커맨드 → 에이전트 매핑
    # -------------------------------------------------------------------------

    COMMAND_AGENT_MAP: Dict[str, Tuple[str, ModelTier]] = {
        "/debug": ("oh-my-claudecode:architect", ModelTier.OPUS),
        "/check --fix": ("oh-my-claudecode:build-fixer", ModelTier.SONNET),
        "/check --security": ("oh-my-claudecode:security-reviewer", ModelTier.OPUS),
        "/issue fix": ("oh-my-claudecode:executor", ModelTier.SONNET),
        "/pr auto": ("oh-my-claudecode:code-reviewer", ModelTier.OPUS),
        "/tdd": ("oh-my-claudecode:tdd-guide", ModelTier.SONNET),
        "/research": ("oh-my-claudecode:researcher", ModelTier.SONNET),
        "/audit quick": ("oh-my-claudecode:explore", ModelTier.HAIKU),
        # BKIT 커맨드 추가
        "/pdca analyze": ("bkit:gap-detector", ModelTier.OPUS),
        "/pdca iterate": ("bkit:pdca-iterator", ModelTier.SONNET),
        "/pdca report": ("bkit:report-generator", ModelTier.HAIKU),
    }

    def get_agent_for_command(self, command: str) -> Optional[AgentConfig]:
        """커맨드에 적합한 에이전트 반환"""
        if command in self.COMMAND_AGENT_MAP:
            agent_type, model = self.COMMAND_AGENT_MAP[command]
            return AgentConfig(agent_type=agent_type, model=model, prompt="")
        return None

    # -------------------------------------------------------------------------
    # Task 호출 코드 생성
    # -------------------------------------------------------------------------

    def build_task_call(self, agent_config: AgentConfig) -> str:
        """Task tool 호출 코드 생성"""
        return f'''Task(
    subagent_type="{agent_config.agent_type}",
    model="{agent_config.model.value}",
    prompt="""{agent_config.prompt}""",
    run_in_background={str(agent_config.background).lower()}
)'''

    def build_task_call_with_fallback(self, agent_config: AgentConfig) -> Tuple[str, bool, str]:
        """Task tool 호출 코드 생성 (BKIT 폴백 자동 처리)

        BKIT 에이전트가 요청된 경우 자동으로 OMC 에이전트로 폴백하고,
        폴백 발생 시 사용자에게 알림 메시지를 함께 반환합니다.

        Args:
            agent_config: 에이전트 호출 설정

        Returns:
            Tuple[Task 호출 코드, 폴백 발생 여부, 폴백 메시지]
        """
        actual_agent, agent_info, did_fallback = self.get_agent_with_fallback(agent_config.agent_type)

        # 폴백 메시지 생성
        fallback_message = ""
        if did_fallback:
            fallback_message = f"[BKIT Fallback] {agent_config.agent_type} -> {actual_agent}"

        # 실제 사용할 에이전트로 config 업데이트
        actual_model = agent_info.model if agent_info else agent_config.model
        updated_config = AgentConfig(
            agent_type=actual_agent,
            model=actual_model,
            prompt=agent_config.prompt,
            background=agent_config.background
        )

        task_call = self.build_task_call(updated_config)
        return task_call, did_fallback, fallback_message

    def resolve_agent_for_pdca_check(self, use_bkit: bool = True) -> Tuple[str, str]:
        """PDCA Check 단계용 에이전트 결정

        이중 검증(OMC Architect + BKIT gap-detector)을 위한 에이전트 쌍을 반환합니다.
        BKIT이 불가능한 경우 OMC만 사용합니다.

        Args:
            use_bkit: BKIT 에이전트 시도 여부 (False면 OMC만 사용)

        Returns:
            Tuple[주 검증 에이전트, 보조 검증 에이전트 또는 빈 문자열]
        """
        primary = "oh-my-claudecode:architect"

        if use_bkit:
            # BKIT gap-detector 시도 → 폴백 시 architect로 대체 (중복 방지)
            secondary_agent, _, did_fallback = self.get_agent_with_fallback("bkit:gap-detector")
            if did_fallback:
                # 폴백 발생 시 이중 검증 불가 (둘 다 architect가 됨)
                return primary, ""
            return primary, "bkit:gap-detector"

        return primary, ""

    def build_ralplan_call(self, task_description: str) -> str:
        """Ralplan 호출 코드 생성"""
        return f'''Task(
    subagent_type="oh-my-claudecode:planner",
    model="opus",
    prompt="""다음 작업에 대한 구현 계획을 수립하세요:

{task_description}

계획 수립 후 Architect와 합의를 진행합니다."""
)'''

    def build_ultrawork_call(self, tasks: List[str]) -> str:
        """Ultrawork 병렬 실행 호출 코드 생성"""
        task_list = "\n".join(f"- {t}" for t in tasks)
        return f'''# Ultrawork 병렬 실행
# 다음 작업들을 병렬로 실행:
{task_list}

# 독립적인 작업들은 병렬 Task 호출
Task(subagent_type="oh-my-claudecode:executor", model="sonnet", prompt="...")
Task(subagent_type="oh-my-claudecode:executor", model="sonnet", prompt="...")
'''

    def build_architect_verify_call(self, task_summary: str) -> str:
        """Architect 검증 호출 코드 생성"""
        return f'''Task(
    subagent_type="oh-my-claudecode:architect",
    model="opus",
    prompt="""다음 구현이 완료되었는지 검증하세요:

{task_summary}

검증 항목:
1. 원래 요청을 완전히 충족하는가?
2. 명백한 버그가 있는가?
3. 누락된 엣지 케이스가 있는가?
4. 코드 품질이 수용 가능한가?

APPROVED 또는 REJECTED 중 하나로 응답하세요."""
)'''

    # -------------------------------------------------------------------------
    # 병렬 비교 검토 호출 (NEW)
    # -------------------------------------------------------------------------

    def build_parallel_comparison_call(
        self,
        domain: AgentDomain,
        prompt: str,
        model_tier: ModelTier = ModelTier.SONNET
    ) -> str:
        """
        OMC와 BKIT 에이전트를 병렬로 호출하여 비교 검토하는 코드 생성

        Args:
            domain: 에이전트 도메인 (REVIEW, TESTING, VERIFICATION 등)
            prompt: 작업 프롬프트
            model_tier: 선호 모델 티어

        Returns:
            병렬 호출 코드
        """
        pairs = self.get_comparable_agents(domain)
        if not pairs:
            # 비교 가능한 쌍이 없으면 OMC 단독 실행
            return self._build_single_agent_call(domain, prompt, model_tier, "omc")

        # OMC 에이전트 선택
        omc_agent = self._select_agent_by_tier(pairs.get("omc", []), model_tier)
        # BKIT 에이전트 선택
        bkit_agent = self._select_agent_by_tier(pairs.get("bkit", []), model_tier)

        if not omc_agent and not bkit_agent:
            return "# 비교 가능한 에이전트 없음"

        if not omc_agent:
            return self._build_single_agent_call(domain, prompt, model_tier, "bkit")
        if not bkit_agent:
            return self._build_single_agent_call(domain, prompt, model_tier, "omc")

        omc_info = self.get_agent(omc_agent)
        bkit_info = self.get_agent(bkit_agent)

        return f'''# ============================================================
# 병렬 비교 검토: {domain.value}
# OMC: {omc_agent} ({omc_info.model.value})
# BKIT: {bkit_agent} ({bkit_info.model.value})
# ============================================================

# 두 에이전트를 병렬로 호출
# (Claude Code에서는 한 메시지에 여러 Task 호출로 병렬 실행)

# OMC 에이전트 호출
Task(
    subagent_type="{omc_agent}",
    model="{omc_info.model.value}",
    description="[OMC] {domain.value} 분석",
    prompt="""{prompt}

## 출력 형식
- 분석 결과
- 발견된 이슈 목록
- 권장 조치사항
- 신뢰도 점수 (0-100)"""
)

# BKIT 에이전트 호출
Task(
    subagent_type="{bkit_agent}",
    model="{bkit_info.model.value}",
    description="[BKIT] {domain.value} 분석",
    prompt="""{prompt}

## 출력 형식
- 분석 결과
- 발견된 이슈 목록
- 권장 조치사항
- 신뢰도 점수 (0-100)"""
)

# 결과 비교 검토는 두 에이전트 완료 후 수행
'''

    def build_verification_comparison_call(
        self,
        design_doc: str,
        implementation: str,
        gap_threshold: int = 90
    ) -> str:
        """
        설계-구현 검증을 위한 병렬 비교 호출 (Architect + gap-detector)

        Args:
            design_doc: 설계 문서 경로 또는 내용
            implementation: 구현 코드 경로 또는 내용
            gap_threshold: gap-detector 통과 임계값 (기본 90%)

        Returns:
            병렬 검증 호출 코드
        """
        return f'''# ============================================================
# 이중 검증: OMC Architect + BKIT gap-detector
# ============================================================

# OMC Architect 검증 (기능적 완성도)
Task(
    subagent_type="oh-my-claudecode:architect",
    model="opus",
    description="[OMC] Architect 검증",
    prompt="""## 설계 문서
{design_doc}

## 구현 코드
{implementation}

## 검증 항목
1. 원래 요청을 완전히 충족하는가?
2. 명백한 버그가 있는가?
3. 누락된 엣지 케이스가 있는가?
4. 코드 품질이 수용 가능한가?

## 출력
- verdict: APPROVED 또는 REJECTED
- issues: [발견된 이슈 목록]
- feedback: 상세 피드백"""
)

# BKIT gap-detector 검증 (설계-구현 일치도)
Task(
    subagent_type="bkit:gap-detector",
    model="opus",
    description="[BKIT] 설계-구현 갭 분석",
    prompt="""## 설계 문서
{design_doc}

## 구현 코드
{implementation}

## 검증 항목
1. 설계에 명시된 기능이 모두 구현되었는가?
2. 구현이 설계를 정확히 따르는가?
3. 누락된 기능이 있는가?
4. 추가된 기능이 있는가?

## 임계값
통과 기준: {gap_threshold}%

## 출력
- match_percentage: 0-100
- verdict: PASS (>={gap_threshold}%) / WARN (70-{gap_threshold-1}%) / FAIL (<70%)
- gaps: [설계에 있으나 구현에 없는 항목]
- extras: [구현에 있으나 설계에 없는 항목]
- recommendations: [권장 조치사항]"""
)

# 두 검증 결과를 종합하여 최종 판정
# - Architect APPROVED + gap >= {gap_threshold}% → 완료
# - 둘 중 하나라도 실패 → 개선 필요
'''

    def build_code_review_comparison_call(self, code_path: str) -> str:
        """
        코드 리뷰를 위한 병렬 비교 호출 (code-reviewer + code-analyzer)

        Args:
            code_path: 리뷰할 코드 경로

        Returns:
            병렬 리뷰 호출 코드
        """
        return f'''# ============================================================
# 코드 리뷰: OMC code-reviewer + BKIT code-analyzer
# ============================================================

# OMC 코드 리뷰 (보안, 품질, 유지보수성)
Task(
    subagent_type="oh-my-claudecode:code-reviewer",
    model="opus",
    description="[OMC] 코드 리뷰",
    prompt="""## 리뷰 대상
{code_path}

## 리뷰 항목
1. 보안 취약점 (OWASP Top 10)
2. 코드 품질 (SOLID, DRY, KISS)
3. 유지보수성
4. 성능 이슈
5. 테스트 커버리지

## 출력
- severity: CRITICAL / HIGH / MEDIUM / LOW
- issues: [이슈 목록 with file:line]
- suggestions: [개선 제안]"""
)

# BKIT 코드 분석 (PDCA 관점)
Task(
    subagent_type="bkit:code-analyzer",
    model="sonnet",
    description="[BKIT] 코드 품질 분석",
    prompt="""## 분석 대상
{code_path}

## 분석 항목
1. 아키텍처 일관성
2. 컨벤션 준수
3. 문서화 상태
4. 테스트 품질
5. 에러 핸들링

## 출력
- quality_score: 0-100
- category_scores: {{architecture, convention, docs, tests, error_handling}}
- issues: [이슈 목록]
- improvements: [개선점]"""
)

# 두 리뷰 결과를 병합하여 종합 리뷰 리포트 생성
'''

    def _select_agent_by_tier(
        self,
        agents: List[str],
        preferred_tier: ModelTier
    ) -> Optional[str]:
        """선호 티어에 맞는 에이전트 선택"""
        if not agents:
            return None

        # 선호 티어와 일치하는 에이전트 찾기
        for agent in agents:
            info = self.get_agent(agent)
            if info and info.model == preferred_tier:
                return agent

        # 없으면 첫 번째 반환
        return agents[0]

    def _build_single_agent_call(
        self,
        domain: AgentDomain,
        prompt: str,
        model_tier: ModelTier,
        source: str
    ) -> str:
        """단일 에이전트 호출 코드 생성"""
        agents = [
            info for info in self.registry.values()
            if info.domain == domain and info.source == source
        ]
        if not agents:
            return f"# {domain.value} 도메인에 {source} 에이전트 없음"

        agent = self._select_agent_by_tier(
            [a.agent_type for a in agents],
            model_tier
        )
        if not agent:
            return f"# {model_tier.value} 티어 에이전트 없음"

        info = self.get_agent(agent)
        return f'''Task(
    subagent_type="{agent}",
    model="{info.model.value}",
    prompt="""{prompt}"""
)'''

    # -------------------------------------------------------------------------
    # 결과 비교 및 병합
    # -------------------------------------------------------------------------

    def compare_results(
        self,
        omc_result: AgentResult,
        bkit_result: AgentResult
    ) -> ComparisonResult:
        """
        두 에이전트 결과를 비교하여 최선의 결과 선택

        Args:
            omc_result: OMC 에이전트 결과
            bkit_result: BKIT 에이전트 결과

        Returns:
            비교 결과
        """
        comparison = ComparisonResult(
            omc_result=omc_result,
            bkit_result=bkit_result
        )

        # 둘 다 실패
        if not omc_result.success and not bkit_result.success:
            comparison.winner = "none"
            comparison.comparison_notes = "Both agents failed"
            return comparison

        # 하나만 성공
        if omc_result.success and not bkit_result.success:
            comparison.winner = "omc"
            comparison.merged_output = omc_result.output
            comparison.confidence = 0.7
            comparison.comparison_notes = "Only OMC succeeded"
            return comparison

        if bkit_result.success and not omc_result.success:
            comparison.winner = "bkit"
            comparison.merged_output = bkit_result.output
            comparison.confidence = 0.7
            comparison.comparison_notes = "Only BKIT succeeded"
            return comparison

        # 둘 다 성공 - 결과 병합
        comparison.winner = "both"
        comparison.confidence = 0.9
        comparison.comparison_notes = "Both agents succeeded, results merged"
        comparison.merged_output = f"""## OMC 분석 결과
{omc_result.output}

## BKIT 분석 결과
{bkit_result.output}

## 종합
양쪽 분석을 종합하여 검토하세요."""

        return comparison


# =============================================================================
# 편의 함수
# =============================================================================

def get_omc_bridge() -> OMCBridge:
    """OMCBridge 인스턴스 반환"""
    return OMCBridge()


def get_agent_count() -> Dict[str, int]:
    """에이전트 수 통계"""
    bridge = OMCBridge()
    omc_count = len(bridge.get_agents_by_source("omc"))
    bkit_count = len(bridge.get_agents_by_source("bkit"))
    return {
        "omc": omc_count,
        "bkit": bkit_count,
        "total": omc_count + bkit_count
    }


def list_comparable_domains() -> List[AgentDomain]:
    """비교 가능한 도메인 목록"""
    return list(DOMAIN_AGENT_PAIRS.keys())


# =============================================================================
# 테스트/실행
# =============================================================================

if __name__ == "__main__":
    bridge = OMCBridge()

    # 에이전트 수 확인
    counts = get_agent_count()
    print(f"에이전트 수: OMC {counts['omc']}개, BKIT {counts['bkit']}개, 총 {counts['total']}개")

    # 비교 가능한 도메인
    print(f"\n비교 가능한 도메인: {[d.value for d in list_comparable_domains()]}")

    # BKIT 폴백 테스트
    print("\n=== BKIT 폴백 테스트 ===")
    test_bkit_agents = [
        "bkit:gap-detector",
        "bkit:code-analyzer",
        "bkit:qa-monitor",
        "bkit:pdca-iterator"
    ]
    for bkit_agent in test_bkit_agents:
        actual_agent, agent_info = bridge.get_agent_with_fallback(bkit_agent)
        if agent_info:
            fallback_status = " (폴백됨)" if actual_agent != bkit_agent else ""
            print(f"{bkit_agent} -> {actual_agent}{fallback_status} ({agent_info.model.value})")
        else:
            print(f"{bkit_agent} -> 폴백 실패")

    # OMC 에이전트는 폴백 없이 정상 조회
    print("\n=== OMC 에이전트 정상 조회 ===")
    test_omc_agents = [
        "oh-my-claudecode:architect",
        "oh-my-claudecode:executor",
    ]
    for omc_agent in test_omc_agents:
        actual_agent, agent_info = bridge.get_agent_with_fallback(omc_agent)
        if agent_info:
            print(f"{omc_agent} -> {actual_agent} ({agent_info.model.value})")

    # 병렬 비교 호출 테스트
    print("\n=== 코드 리뷰 병렬 비교 호출 ===")
    print(bridge.build_code_review_comparison_call("src/main.py"))

    # 검증 비교 호출 테스트
    print("\n=== 검증 병렬 비교 호출 ===")
    print(bridge.build_verification_comparison_call(
        "docs/02-design/feature.design.md",
        "src/feature.py",
        gap_threshold=90
    ))
