#!/usr/bin/env python3
"""
Context Manager - 인과관계 기반 컨텍스트 관리

Codex Agent Loop 최적화 기법 + 인과관계 그래프를 결합하여
context compaction 시에도 중요 정보를 보존합니다.

핵심 기능:
- Causality Graph: 노드 간 인과관계 추적 (causes, leads_to, resolved_by)
- Importance Scoring: HIGH/MEDIUM/LOW 기반 compaction 우선순위
- 기존 시스템 통합: phase_gate, auto_state, note와 연동
- Compact Summary: compaction 생존용 압축 요약 자동 생성

노드 유형:
- REQUEST: 사용자 요청
- ANALYSIS: 분석 결과
- DECISION: 결정 사항
- REJECTED: 거부된 대안
- FILE: 파일 변경
- ERROR: 발생한 에러
- SOLUTION: 해결책
- LEARNING: 학습 내용/패턴

엣지 유형:
- causes: A가 B를 유발
- leads_to: A가 B로 이어짐
- resolved_by: A(에러)가 B(솔루션)로 해결
- blocks: A가 B를 차단
- depends_on: A가 B에 의존
- rejects: A가 B를 거부 (대안 기록)
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


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
CONTEXT_DIR = PROJECT_ROOT / ".omc" / "context"
CONTEXT_FILE = CONTEXT_DIR / "context_graph.json"
SUMMARY_FILE = CONTEXT_DIR / "compact_summary.md"
ARCHIVE_DIR = CONTEXT_DIR / "archive"

# === 파일 크기 제한 설정 ===
MAX_NODES = 500                    # 최대 노드 수
MAX_EDGES = 1000                   # 최대 엣지 수
MAX_FILE_SIZE_KB = 1024            # 최대 파일 크기 (1MB)
TTL_HOURS = 24                     # 노드 TTL (24시간)
CLEANUP_THRESHOLD_PERCENT = 80     # 이 비율 초과 시 정리 시작
ARCHIVE_BATCH_SIZE = 100           # 아카이브 시 배치 크기

# === v13.0 설정 ===
WISDOM_DIR = PROJECT_ROOT / ".omc" / "notepads"
CIRCUIT_BREAKER_FILE = PROJECT_ROOT / ".omc" / "state" / "circuit-breaker.json"
VERIFICATION_FRESHNESS_SECONDS = 300  # 5분


class NodeType(Enum):
    """컨텍스트 노드 유형"""
    REQUEST = "request"          # 사용자 요청
    ANALYSIS = "analysis"        # 분석 결과
    DECISION = "decision"        # 결정 사항
    REJECTED = "rejected"        # 거부된 대안
    FILE = "file"                # 파일 변경
    ERROR = "error"              # 발생한 에러
    SOLUTION = "solution"        # 해결책
    LEARNING = "learning"        # 학습 내용


class EdgeType(Enum):
    """컨텍스트 엣지 유형"""
    CAUSES = "causes"            # A가 B를 유발
    LEADS_TO = "leads_to"        # A가 B로 이어짐
    RESOLVED_BY = "resolved_by"  # A(에러)가 B(솔루션)로 해결
    BLOCKS = "blocks"            # A가 B를 차단
    DEPENDS_ON = "depends_on"    # A가 B에 의존
    REJECTS = "rejects"          # A가 B를 거부


class Importance(Enum):
    """중요도 레벨 (compaction 우선순위)"""
    HIGH = "high"      # 절대 삭제 금지
    MEDIUM = "medium"  # 가능하면 보존
    LOW = "low"        # 필요 시 삭제 가능


# === v13.0: CircuitBreaker ===

class CircuitBreaker:
    """
    3-Failure 에러 에스컬레이션 패턴

    같은 태스크에서 연속 3번 실패하면 Architect에게 에스컬레이션합니다.

    실패 처리 흐름:
    1. 1차 실패: RETRY (재시도)
    2. 2차 실패: ALTERNATE_APPROACH (다른 접근법 시도)
    3. 3차 실패: ESCALATE_TO_ARCHITECT (Architect에게 에스컬레이션)
    """

    def __init__(self, max_failures: int = 3):
        """
        Args:
            max_failures: 에스컬레이션 전 최대 실패 횟수 (기본값: 3)
        """
        self.max_failures = max_failures
        self.failure_counts: dict[str, int] = {}  # {task_key: count}
        self.failure_history: dict[str, list] = {}  # {task_key: [errors]}

    def record_failure(self, task_key: str, error: str) -> str:
        """
        실패 기록 및 다음 액션 결정

        Args:
            task_key: 태스크 식별자
            error: 에러 메시지

        Returns:
            "RETRY" | "ALTERNATE_APPROACH" | "ESCALATE_TO_ARCHITECT"
        """
        # 카운터 증가
        self.failure_counts[task_key] = self.failure_counts.get(task_key, 0) + 1
        count = self.failure_counts[task_key]

        # 에러 히스토리 기록
        if task_key not in self.failure_history:
            self.failure_history[task_key] = []
        self.failure_history[task_key].append({
            "error": error,
            "timestamp": datetime.now().isoformat(),
            "attempt": count,
        })

        # 다음 액션 결정
        if count == 1:
            return "RETRY"
        elif count == 2:
            return "ALTERNATE_APPROACH"
        else:  # count >= 3
            return "ESCALATE_TO_ARCHITECT"

    def reset(self, task_key: str):
        """
        태스크 성공 시 카운터 리셋

        Args:
            task_key: 태스크 식별자
        """
        if task_key in self.failure_counts:
            del self.failure_counts[task_key]
        if task_key in self.failure_history:
            del self.failure_history[task_key]

    def get_failure_summary(self, task_key: str) -> dict:
        """
        실패 이력 요약

        Args:
            task_key: 태스크 식별자

        Returns:
            {
                "task_key": str,
                "failure_count": int,
                "errors": list[dict],
                "recommendation": str
            }
        """
        count = self.failure_counts.get(task_key, 0)
        history = self.failure_history.get(task_key, [])

        if count == 0:
            recommendation = "NO_FAILURES"
        elif count == 1:
            recommendation = "RETRY"
        elif count == 2:
            recommendation = "ALTERNATE_APPROACH"
        else:
            recommendation = "ESCALATE_TO_ARCHITECT"

        return {
            "task_key": task_key,
            "failure_count": count,
            "errors": history,
            "recommendation": recommendation,
        }

    def to_dict(self) -> dict:
        """직렬화"""
        return {
            "max_failures": self.max_failures,
            "failure_counts": self.failure_counts,
            "failure_history": self.failure_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CircuitBreaker":
        """역직렬화"""
        cb = cls(max_failures=data.get("max_failures", 3))
        cb.failure_counts = data.get("failure_counts", {})
        cb.failure_history = data.get("failure_history", {})
        return cb

    def get_all_failures(self) -> dict[str, dict]:
        """
        모든 태스크의 실패 상태 조회

        Returns:
            {task_key: failure_summary}
        """
        result = {}
        for task_key in self.failure_counts:
            result[task_key] = self.get_failure_summary(task_key)
        return result


# === v13.0: VerificationResult ===

@dataclass
class VerificationResult:
    """검증 결과"""
    check_type: str  # "BUILD", "TEST", "LINT", "FUNCTIONALITY", "ARCHITECT", "TODO", "ERROR_FREE"
    passed: bool
    evidence: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "check_type": self.check_type,
            "passed": self.passed,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VerificationResult":
        return cls(
            check_type=data["check_type"],
            passed=data["passed"],
            evidence=data["evidence"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class ContextNode:
    """컨텍스트 그래프 노드"""
    id: str
    type: NodeType
    content: str
    importance: Importance = Importance.MEDIUM
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "importance": self.importance.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextNode":
        return cls(
            id=data["id"],
            type=NodeType(data["type"]),
            content=data["content"],
            importance=Importance(data.get("importance", "medium")),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ContextEdge:
    """컨텍스트 그래프 엣지"""
    source_id: str
    target_id: str
    type: EdgeType
    description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.value,
            "description": self.description,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            type=EdgeType(data["type"]),
            description=data.get("description", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


class ContextManager:
    """인과관계 기반 컨텍스트 관리자"""

    def __init__(self, session_id: Optional[str] = None):
        """
        Args:
            session_id: 세션 ID (None이면 자동 생성)
        """
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

        self.session_id = session_id or f"ctx_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.nodes: dict[str, ContextNode] = {}
        self.edges: list[ContextEdge] = []
        self._node_counter = 0

        # v13.0: CircuitBreaker 및 Verification 추가
        self.circuit_breaker = CircuitBreaker()
        self.verifications: dict[str, VerificationResult] = {}

        # 기존 컨텍스트 로드
        self._load()

    def _load(self):
        """컨텍스트 파일 로드"""
        if CONTEXT_FILE.exists():
            try:
                with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    # 같은 세션만 로드
                    if data.get("session_id") == self.session_id:
                        for node_data in data.get("nodes", []):
                            node = ContextNode.from_dict(node_data)
                            self.nodes[node.id] = node

                        for edge_data in data.get("edges", []):
                            edge = ContextEdge.from_dict(edge_data)
                            self.edges.append(edge)

                        self._node_counter = data.get("node_counter", len(self.nodes))

                        # v13.0: CircuitBreaker 로드
                        if "circuit_breaker" in data:
                            self.circuit_breaker = CircuitBreaker.from_dict(data["circuit_breaker"])

                        # v13.0: Verifications 로드
                        for vdata in data.get("verifications", []):
                            vr = VerificationResult.from_dict(vdata)
                            self.verifications[vr.check_type] = vr
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        """컨텍스트 파일 저장 (자동 정리 포함)"""
        # 저장 전 자동 정리 체크
        self._auto_cleanup()

        try:
            with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "updated_at": datetime.now().isoformat(),
                    "node_counter": self._node_counter,
                    "nodes": [n.to_dict() for n in self.nodes.values()],
                    "edges": [e.to_dict() for e in self.edges],
                    # v13.0: CircuitBreaker 저장
                    "circuit_breaker": self.circuit_breaker.to_dict(),
                    # v13.0: Verifications 저장
                    "verifications": [v.to_dict() for v in self.verifications.values()],
                }, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"Warning: Failed to save context: {e}")

    # === 자동 정리 메커니즘 ===

    def _auto_cleanup(self):
        """자동 정리 트리거 (노드 수, 파일 크기, TTL 기반)"""
        cleanup_needed = False
        reason = ""

        # 1. 노드 수 체크
        node_threshold = int(MAX_NODES * CLEANUP_THRESHOLD_PERCENT / 100)
        if len(self.nodes) > node_threshold:
            cleanup_needed = True
            reason = f"노드 수 초과 ({len(self.nodes)}/{MAX_NODES})"

        # 2. 엣지 수 체크
        edge_threshold = int(MAX_EDGES * CLEANUP_THRESHOLD_PERCENT / 100)
        if len(self.edges) > edge_threshold:
            cleanup_needed = True
            reason = f"엣지 수 초과 ({len(self.edges)}/{MAX_EDGES})"

        # 3. 파일 크기 체크
        if CONTEXT_FILE.exists():
            file_size_kb = CONTEXT_FILE.stat().st_size / 1024
            size_threshold = MAX_FILE_SIZE_KB * CLEANUP_THRESHOLD_PERCENT / 100
            if file_size_kb > size_threshold:
                cleanup_needed = True
                reason = f"파일 크기 초과 ({file_size_kb:.1f}KB/{MAX_FILE_SIZE_KB}KB)"

        if cleanup_needed:
            self._perform_cleanup(reason)

    def _perform_cleanup(self, reason: str = ""):
        """정리 수행 (중요도 + TTL 기반)"""
        now = datetime.now()
        ttl_cutoff = now - timedelta(hours=TTL_HOURS)

        # 삭제 대상 노드 수집
        nodes_to_remove = []

        for node_id, node in self.nodes.items():
            # TTL 만료 체크
            try:
                node_time = datetime.fromisoformat(node.timestamp)
                is_expired = node_time < ttl_cutoff
            except (ValueError, TypeError):
                is_expired = False

            # 삭제 조건: (TTL 만료 AND LOW) OR (TTL 만료 AND MEDIUM AND 정리 필요)
            if is_expired:
                if node.importance == Importance.LOW:
                    nodes_to_remove.append((node_id, node, "TTL+LOW"))
                elif node.importance == Importance.MEDIUM and len(self.nodes) > MAX_NODES:
                    nodes_to_remove.append((node_id, node, "TTL+MEDIUM+OVERFLOW"))

        # 아직 MAX를 초과하면 LOW importance 우선 삭제 (TTL 무관)
        if len(self.nodes) - len(nodes_to_remove) > MAX_NODES:
            low_nodes = [
                (nid, n, "LOW_PRIORITY")
                for nid, n in self.nodes.items()
                if n.importance == Importance.LOW and nid not in [x[0] for x in nodes_to_remove]
            ]
            # 오래된 순으로 정렬
            low_nodes.sort(key=lambda x: x[1].timestamp)
            nodes_to_remove.extend(low_nodes[:ARCHIVE_BATCH_SIZE])

        if nodes_to_remove:
            # 아카이브 후 삭제
            self._archive_nodes([n for _, n, _ in nodes_to_remove], reason)

            # 노드 삭제
            removed_ids = set()
            for node_id, _, _ in nodes_to_remove:
                if node_id in self.nodes:
                    del self.nodes[node_id]
                    removed_ids.add(node_id)

            # 관련 엣지 삭제
            self.edges = [
                e for e in self.edges
                if e.source_id not in removed_ids and e.target_id not in removed_ids
            ]

    def _archive_nodes(self, nodes: list, reason: str = ""):
        """삭제될 노드를 아카이브 파일로 보관"""
        if not nodes:
            return

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        archive_file = ARCHIVE_DIR / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "archived_at": datetime.now().isoformat(),
                    "reason": reason,
                    "node_count": len(nodes),
                    "nodes": [n.to_dict() for n in nodes],
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 아카이브 실패해도 정리는 진행

    def force_cleanup(self, keep_high_only: bool = False) -> dict:
        """
        강제 정리 수행

        Args:
            keep_high_only: True면 HIGH importance만 보존

        Returns:
            정리 결과 통계
        """
        before_nodes = len(self.nodes)
        before_edges = len(self.edges)

        nodes_to_remove = []

        for node_id, node in self.nodes.items():
            if keep_high_only:
                if node.importance != Importance.HIGH:
                    nodes_to_remove.append((node_id, node))
            else:
                if node.importance == Importance.LOW:
                    nodes_to_remove.append((node_id, node))

        if nodes_to_remove:
            self._archive_nodes([n for _, n in nodes_to_remove], "force_cleanup")

            removed_ids = set()
            for node_id, _ in nodes_to_remove:
                if node_id in self.nodes:
                    del self.nodes[node_id]
                    removed_ids.add(node_id)

            self.edges = [
                e for e in self.edges
                if e.source_id not in removed_ids and e.target_id not in removed_ids
            ]

        # 강제 정리 후 저장 (재귀 방지를 위해 직접 저장)
        try:
            with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "updated_at": datetime.now().isoformat(),
                    "node_counter": self._node_counter,
                    "nodes": [n.to_dict() for n in self.nodes.values()],
                    "edges": [e.to_dict() for e in self.edges],
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

        return {
            "before_nodes": before_nodes,
            "after_nodes": len(self.nodes),
            "removed_nodes": before_nodes - len(self.nodes),
            "before_edges": before_edges,
            "after_edges": len(self.edges),
            "removed_edges": before_edges - len(self.edges),
        }

    def get_file_stats(self) -> dict:
        """파일 크기 및 제한 상태 조회"""
        file_size_kb = 0
        if CONTEXT_FILE.exists():
            file_size_kb = CONTEXT_FILE.stat().st_size / 1024

        return {
            "file_size_kb": round(file_size_kb, 2),
            "max_file_size_kb": MAX_FILE_SIZE_KB,
            "file_usage_percent": round(file_size_kb / MAX_FILE_SIZE_KB * 100, 1),
            "node_count": len(self.nodes),
            "max_nodes": MAX_NODES,
            "node_usage_percent": round(len(self.nodes) / MAX_NODES * 100, 1),
            "edge_count": len(self.edges),
            "max_edges": MAX_EDGES,
            "edge_usage_percent": round(len(self.edges) / MAX_EDGES * 100, 1),
            "ttl_hours": TTL_HOURS,
            "cleanup_threshold_percent": CLEANUP_THRESHOLD_PERCENT,
        }

    def _generate_id(self, prefix: str) -> str:
        """고유 ID 생성"""
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    # === 노드 추가 API ===

    def record_request(self, content: str, metadata: Optional[dict] = None) -> str:
        """사용자 요청 기록"""
        node_id = self._generate_id("req")
        node = ContextNode(
            id=node_id,
            type=NodeType.REQUEST,
            content=content,
            importance=Importance.HIGH,  # 요청은 항상 HIGH
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        self._save()
        return node_id

    def record_analysis(
        self,
        content: str,
        caused_by: Optional[str] = None,
        importance: Importance = Importance.MEDIUM,
        metadata: Optional[dict] = None
    ) -> str:
        """분석 결과 기록"""
        node_id = self._generate_id("analysis")
        node = ContextNode(
            id=node_id,
            type=NodeType.ANALYSIS,
            content=content,
            importance=importance,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node

        if caused_by and caused_by in self.nodes:
            self._add_edge(caused_by, node_id, EdgeType.LEADS_TO, "분석 수행")

        self._save()
        return node_id

    def record_decision(
        self,
        content: str,
        rationale: str,
        caused_by: Optional[str] = None,
        alternatives: Optional[list[str]] = None,
        importance: Importance = Importance.HIGH,
        metadata: Optional[dict] = None
    ) -> str:
        """결정 사항 기록"""
        node_id = self._generate_id("decision")
        node = ContextNode(
            id=node_id,
            type=NodeType.DECISION,
            content=content,
            importance=importance,
            metadata={
                "rationale": rationale,
                "alternatives": alternatives or [],
                **(metadata or {}),
            },
        )
        self.nodes[node_id] = node

        if caused_by and caused_by in self.nodes:
            self._add_edge(caused_by, node_id, EdgeType.LEADS_TO, "결정으로 이어짐")

        # 거부된 대안 기록
        if alternatives:
            for alt in alternatives:
                alt_id = self._generate_id("rejected")
                alt_node = ContextNode(
                    id=alt_id,
                    type=NodeType.REJECTED,
                    content=alt,
                    importance=Importance.LOW,
                )
                self.nodes[alt_id] = alt_node
                self._add_edge(node_id, alt_id, EdgeType.REJECTS, "대안 거부")

        self._save()
        return node_id

    def record_file_change(
        self,
        file_path: str,
        change_type: str,  # create, modify, delete
        description: str,
        caused_by: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """파일 변경 기록"""
        node_id = self._generate_id("file")
        node = ContextNode(
            id=node_id,
            type=NodeType.FILE,
            content=f"[{change_type.upper()}] {file_path}: {description}",
            importance=Importance.MEDIUM,
            metadata={
                "file_path": file_path,
                "change_type": change_type,
                **(metadata or {}),
            },
        )
        self.nodes[node_id] = node

        if caused_by and caused_by in self.nodes:
            self._add_edge(caused_by, node_id, EdgeType.CAUSES, f"{change_type} 유발")

        self._save()
        return node_id

    def record_error(
        self,
        error_message: str,
        caused_by: Optional[str] = None,
        context: Optional[str] = None,
        importance: Importance = Importance.HIGH,
        metadata: Optional[dict] = None
    ) -> str:
        """에러 기록"""
        node_id = self._generate_id("error")
        node = ContextNode(
            id=node_id,
            type=NodeType.ERROR,
            content=error_message,
            importance=importance,
            metadata={
                "context": context,
                "resolved": False,
                **(metadata or {}),
            },
        )
        self.nodes[node_id] = node

        if caused_by and caused_by in self.nodes:
            self._add_edge(caused_by, node_id, EdgeType.CAUSES, "에러 유발")

        self._save()
        return node_id

    def record_solution(
        self,
        content: str,
        resolves: str,  # 해결하는 에러 노드 ID
        approach: str,
        importance: Importance = Importance.HIGH,
        metadata: Optional[dict] = None
    ) -> str:
        """해결책 기록"""
        node_id = self._generate_id("solution")
        node = ContextNode(
            id=node_id,
            type=NodeType.SOLUTION,
            content=content,
            importance=importance,
            metadata={
                "approach": approach,
                **(metadata or {}),
            },
        )
        self.nodes[node_id] = node

        if resolves and resolves in self.nodes:
            self._add_edge(resolves, node_id, EdgeType.RESOLVED_BY, "해결됨")
            # 에러 노드 resolved 상태 업데이트
            self.nodes[resolves].metadata["resolved"] = True

        self._save()
        return node_id

    def record_learning(
        self,
        content: str,
        source: Optional[str] = None,
        importance: Importance = Importance.HIGH,
        metadata: Optional[dict] = None
    ) -> str:
        """학습 내용 기록"""
        node_id = self._generate_id("learning")
        node = ContextNode(
            id=node_id,
            type=NodeType.LEARNING,
            content=content,
            importance=importance,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node

        if source and source in self.nodes:
            self._add_edge(source, node_id, EdgeType.LEADS_TO, "학습으로 이어짐")

        self._save()
        return node_id

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        description: str = ""
    ):
        """엣지 추가"""
        edge = ContextEdge(
            source_id=source_id,
            target_id=target_id,
            type=edge_type,
            description=description,
        )
        self.edges.append(edge)

    def add_dependency(self, node_id: str, depends_on: str, description: str = ""):
        """의존성 관계 추가"""
        if node_id in self.nodes and depends_on in self.nodes:
            self._add_edge(node_id, depends_on, EdgeType.DEPENDS_ON, description)
            self._save()

    def add_blocking(self, blocker_id: str, blocked_id: str, description: str = ""):
        """차단 관계 추가"""
        if blocker_id in self.nodes and blocked_id in self.nodes:
            self._add_edge(blocker_id, blocked_id, EdgeType.BLOCKS, description)
            self._save()

    # === 조회 API ===

    def get_node(self, node_id: str) -> Optional[ContextNode]:
        """노드 조회"""
        return self.nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> list[ContextNode]:
        """유형별 노드 조회"""
        return [n for n in self.nodes.values() if n.type == node_type]

    def get_high_importance_nodes(self) -> list[ContextNode]:
        """HIGH 중요도 노드 조회"""
        return [n for n in self.nodes.values() if n.importance == Importance.HIGH]

    def get_unresolved_errors(self) -> list[ContextNode]:
        """미해결 에러 조회"""
        return [
            n for n in self.nodes.values()
            if n.type == NodeType.ERROR and not n.metadata.get("resolved", False)
        ]

    def get_related_nodes(self, node_id: str) -> dict[str, list[ContextNode]]:
        """노드와 관련된 모든 노드 조회"""
        if node_id not in self.nodes:
            return {}

        result = {
            "causes": [],      # 이 노드가 유발한 것들
            "caused_by": [],   # 이 노드를 유발한 것들
            "resolves": [],    # 이 노드가 해결한 것들
            "resolved_by": [], # 이 노드를 해결한 것들
            "blocks": [],      # 이 노드가 차단하는 것들
            "blocked_by": [],  # 이 노드를 차단하는 것들
            "depends_on": [],  # 이 노드가 의존하는 것들
        }

        for edge in self.edges:
            if edge.source_id == node_id:
                target_node = self.nodes.get(edge.target_id)
                if target_node:
                    if edge.type == EdgeType.CAUSES:
                        result["causes"].append(target_node)
                    elif edge.type == EdgeType.RESOLVED_BY:
                        result["resolved_by"].append(target_node)
                    elif edge.type == EdgeType.BLOCKS:
                        result["blocks"].append(target_node)
                    elif edge.type == EdgeType.DEPENDS_ON:
                        result["depends_on"].append(target_node)

            elif edge.target_id == node_id:
                source_node = self.nodes.get(edge.source_id)
                if source_node:
                    if edge.type == EdgeType.CAUSES:
                        result["caused_by"].append(source_node)
                    elif edge.type == EdgeType.RESOLVED_BY:
                        result["resolves"].append(source_node)
                    elif edge.type == EdgeType.BLOCKS:
                        result["blocked_by"].append(source_node)

        return result

    # === Compact Summary 생성 ===

    def generate_compact_summary(self) -> str:
        """Compaction 생존용 압축 요약 생성"""
        summary_lines = [
            "# Context Compact Summary",
            f"Session: {self.session_id}",
            f"Generated: {datetime.now().isoformat()}",
            "",
        ]

        # 1. 원본 요청
        requests = self.get_nodes_by_type(NodeType.REQUEST)
        if requests:
            summary_lines.append("## Original Request")
            for req in requests:
                summary_lines.append(f"- {req.content}")
            summary_lines.append("")

        # 2. 핵심 결정 (HIGH importance)
        decisions = [
            n for n in self.get_nodes_by_type(NodeType.DECISION)
            if n.importance == Importance.HIGH
        ]
        if decisions:
            summary_lines.append("## Key Decisions")
            for dec in decisions:
                summary_lines.append(f"- **{dec.content}**")
                if dec.metadata.get("rationale"):
                    summary_lines.append(f"  - Rationale: {dec.metadata['rationale']}")
            summary_lines.append("")

        # 3. 변경된 파일
        files = self.get_nodes_by_type(NodeType.FILE)
        if files:
            summary_lines.append("## Changed Files")
            for f in files:
                summary_lines.append(f"- {f.content}")
            summary_lines.append("")

        # 4. 미해결 에러
        unresolved = self.get_unresolved_errors()
        if unresolved:
            summary_lines.append("## Unresolved Errors")
            for err in unresolved:
                summary_lines.append(f"- ⚠️ {err.content}")
            summary_lines.append("")

        # 5. 해결된 에러와 솔루션
        solutions = self.get_nodes_by_type(NodeType.SOLUTION)
        if solutions:
            summary_lines.append("## Solutions Applied")
            for sol in solutions:
                summary_lines.append(f"- ✅ {sol.content}")
                if sol.metadata.get("approach"):
                    summary_lines.append(f"  - Approach: {sol.metadata['approach']}")
            summary_lines.append("")

        # 6. 학습 내용 (패턴, 인사이트)
        learnings = self.get_nodes_by_type(NodeType.LEARNING)
        if learnings:
            summary_lines.append("## Learnings")
            for learn in learnings:
                summary_lines.append(f"- 💡 {learn.content}")
            summary_lines.append("")

        # 7. 인과관계 요약
        causal_chains = self._extract_causal_chains()
        if causal_chains:
            summary_lines.append("## Causality Chains")
            for chain in causal_chains[:5]:  # 상위 5개만
                summary_lines.append(f"- {chain}")
            summary_lines.append("")

        summary = "\n".join(summary_lines)

        # 파일로 저장
        try:
            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                f.write(summary)
        except OSError:
            pass

        return summary

    def _extract_causal_chains(self) -> list[str]:
        """인과관계 체인 추출"""
        chains = []

        # REQUEST → ... → SOLUTION 또는 DECISION 체인 찾기
        requests = self.get_nodes_by_type(NodeType.REQUEST)

        for req in requests:
            chain = self._trace_chain(req.id, set())
            if len(chain) > 1:
                chain_str = " → ".join([
                    f"[{self.nodes[nid].type.value}] {self.nodes[nid].content[:30]}..."
                    if len(self.nodes[nid].content) > 30
                    else f"[{self.nodes[nid].type.value}] {self.nodes[nid].content}"
                    for nid in chain
                ])
                chains.append(chain_str)

        return chains

    def _trace_chain(self, start_id: str, visited: set) -> list[str]:
        """노드에서 시작하는 체인 추적"""
        if start_id in visited:
            return []

        visited.add(start_id)
        chain = [start_id]

        # 다음 노드 찾기 (LEADS_TO, CAUSES, RESOLVED_BY)
        for edge in self.edges:
            if edge.source_id == start_id and edge.type in [
                EdgeType.LEADS_TO, EdgeType.CAUSES, EdgeType.RESOLVED_BY
            ]:
                next_chain = self._trace_chain(edge.target_id, visited)
                if next_chain:
                    chain.extend(next_chain)
                    break  # 첫 번째 체인만

        return chain

    def get_stats(self) -> dict:
        """통계 조회"""
        type_counts = {}
        for node in self.nodes.values():
            type_counts[node.type.value] = type_counts.get(node.type.value, 0) + 1

        importance_counts = {}
        for node in self.nodes.values():
            importance_counts[node.importance.value] = importance_counts.get(node.importance.value, 0) + 1

        return {
            "session_id": self.session_id,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_by_type": type_counts,
            "nodes_by_importance": importance_counts,
            "unresolved_errors": len(self.get_unresolved_errors()),
            "high_importance": len(self.get_high_importance_nodes()),
        }

    def clear(self):
        """컨텍스트 초기화"""
        self.nodes = {}
        self.edges = []
        self._node_counter = 0
        self._save()

    # === 세션 복원 API ===

    def get_restoration_prompt(self) -> str:
        """
        /clear 후 복원용 프롬프트 생성

        HIGH importance 노드와 인과관계 체인을 기반으로
        새 세션에서 맥락을 복원할 수 있는 프롬프트를 생성합니다.

        Returns:
            복원용 프롬프트 문자열
        """
        if not self.nodes:
            return ""

        lines = [
            "# 이전 세션 컨텍스트 복원",
            "",
            "다음은 이전 세션에서 저장된 핵심 맥락입니다. 이 정보를 기반으로 작업을 계속하세요.",
            "",
        ]

        # 1. 원본 요청
        requests = self.get_nodes_by_type(NodeType.REQUEST)
        if requests:
            lines.append("## 원본 요청")
            for req in requests:
                lines.append(f"- {req.content}")
            lines.append("")

        # 2. 핵심 결정사항 (HIGH importance)
        decisions = [
            n for n in self.get_nodes_by_type(NodeType.DECISION)
            if n.importance == Importance.HIGH
        ]
        if decisions:
            lines.append("## 핵심 결정사항")
            for dec in decisions:
                lines.append(f"- **{dec.content}**")
                if dec.metadata.get("rationale"):
                    lines.append(f"  - 근거: {dec.metadata['rationale']}")
                if dec.metadata.get("alternatives"):
                    alts = ", ".join(dec.metadata["alternatives"])
                    lines.append(f"  - 거부된 대안: {alts}")
            lines.append("")

        # 3. 변경된 파일
        files = self.get_nodes_by_type(NodeType.FILE)
        if files:
            lines.append("## 변경된 파일")
            for f in files:
                lines.append(f"- {f.content}")
            lines.append("")

        # 4. 해결된 에러와 솔루션
        solutions = self.get_nodes_by_type(NodeType.SOLUTION)
        if solutions:
            lines.append("## 적용된 솔루션")
            for sol in solutions:
                lines.append(f"- ✅ {sol.content}")
                if sol.metadata.get("approach"):
                    lines.append(f"  - 접근법: {sol.metadata['approach']}")
            lines.append("")

        # 5. 미해결 에러 (있다면)
        unresolved = self.get_unresolved_errors()
        if unresolved:
            lines.append("## ⚠️ 미해결 에러")
            for err in unresolved:
                lines.append(f"- {err.content}")
                if err.metadata.get("context"):
                    lines.append(f"  - 상황: {err.metadata['context']}")
            lines.append("")

        # 6. 학습 내용
        learnings = self.get_nodes_by_type(NodeType.LEARNING)
        if learnings:
            lines.append("## 학습 내용")
            for learn in learnings:
                lines.append(f"- 💡 {learn.content}")
            lines.append("")

        # 7. 인과관계 체인 요약
        causal_chains = self._extract_causal_chains()
        if causal_chains:
            lines.append("## 인과관계 흐름")
            for chain in causal_chains[:3]:  # 상위 3개
                lines.append(f"- {chain}")
            lines.append("")

        # 8. 다음 작업 힌트
        lines.append("## 다음 작업")
        if unresolved:
            lines.append("- 위의 미해결 에러를 먼저 해결하세요")
        else:
            lines.append("- 이전 세션의 맥락을 기반으로 작업을 계속하세요")
        lines.append("")

        return "\n".join(lines)

    def get_session_info(self) -> dict:
        """
        세션 복원 정보 조회

        Returns:
            {
                "has_context": bool,
                "session_id": str,
                "node_count": int,
                "high_importance_count": int,
                "unresolved_errors": int,
                "last_updated": str,
                "requests": list[str],
                "decisions": list[str],
            }
        """
        if not self.nodes:
            return {"has_context": False}

        requests = [n.content for n in self.get_nodes_by_type(NodeType.REQUEST)]
        decisions = [
            n.content for n in self.get_nodes_by_type(NodeType.DECISION)
            if n.importance == Importance.HIGH
        ]

        # 마지막 업데이트 시간 찾기
        last_updated = ""
        if self.nodes:
            timestamps = [n.timestamp for n in self.nodes.values()]
            last_updated = max(timestamps) if timestamps else ""

        return {
            "has_context": True,
            "session_id": self.session_id,
            "node_count": len(self.nodes),
            "high_importance_count": len(self.get_high_importance_nodes()),
            "unresolved_errors": len(self.get_unresolved_errors()),
            "last_updated": last_updated,
            "requests": requests,
            "decisions": decisions[:5],  # 최대 5개
        }

    def should_restore(self) -> bool:
        """
        복원이 의미있는지 판단

        Returns:
            복원 권장 여부
        """
        if not self.nodes:
            return False

        # HIGH importance 노드가 3개 이상이면 복원 권장
        high_count = len(self.get_high_importance_nodes())
        if high_count >= 3:
            return True

        # 미해결 에러가 있으면 복원 권장
        if self.get_unresolved_errors():
            return True

        # 결정사항이 있으면 복원 권장
        if self.get_nodes_by_type(NodeType.DECISION):
            return True

        return False

    # === v13.0: CircuitBreaker 통합 API ===

    def record_failure(self, task_key: str, error_node_id: str) -> str:
        """
        실패 기록 및 다음 액션 반환

        Args:
            task_key: 태스크 식별자
            error_node_id: 관련 에러 노드 ID

        Returns:
            "RETRY" | "ALTERNATE_APPROACH" | "ESCALATE_TO_ARCHITECT"
        """
        # 에러 노드에서 에러 메시지 추출
        error_msg = ""
        if error_node_id in self.nodes:
            error_msg = self.nodes[error_node_id].content

        action = self.circuit_breaker.record_failure(task_key, error_msg)
        self._save()
        return action

    def record_success(self, task_key: str):
        """
        성공 시 CircuitBreaker 리셋

        Args:
            task_key: 태스크 식별자
        """
        self.circuit_breaker.reset(task_key)
        self._save()

    def get_escalation_summary(self) -> str:
        """
        Architect 에스컬레이션용 요약 생성

        에스컬레이션이 필요한 태스크들의 실패 이력을 요약합니다.

        Returns:
            에스컬레이션 요약 문자열
        """
        lines = [
            "# Escalation Summary",
            f"Session: {self.session_id}",
            f"Generated: {datetime.now().isoformat()}",
            "",
        ]

        all_failures = self.circuit_breaker.get_all_failures()
        escalated = {
            k: v for k, v in all_failures.items()
            if v["recommendation"] == "ESCALATE_TO_ARCHITECT"
        }

        if not escalated:
            lines.append("No tasks require escalation.")
            return "\n".join(lines)

        lines.append(f"## Escalated Tasks ({len(escalated)} tasks)")
        lines.append("")

        for task_key, summary in escalated.items():
            lines.append(f"### Task: {task_key}")
            lines.append(f"- **Failure Count**: {summary['failure_count']}")
            lines.append(f"- **Errors**:")

            for err in summary["errors"]:
                lines.append(f"  - [{err['attempt']}] {err['timestamp'][:19]}: {err['error'][:100]}")

            lines.append("")

        # 관련 컨텍스트 추가
        unresolved = self.get_unresolved_errors()
        if unresolved:
            lines.append("## Related Unresolved Errors")
            for err in unresolved[:5]:
                lines.append(f"- {err.content[:150]}")
            lines.append("")

        return "\n".join(lines)

    # === v13.0: Verification Protocol 통합 API ===

    def record_verification(self, check_type: str, passed: bool, evidence: str) -> str:
        """
        검증 결과 기록 (5분 freshness 추적)

        Args:
            check_type: 검증 유형 ("BUILD", "TEST", "LINT", "FUNCTIONALITY", "ARCHITECT", "TODO", "ERROR_FREE")
            passed: 통과 여부
            evidence: 증거 (출력 로그 등)

        Returns:
            검증 결과 노드 ID
        """
        vr = VerificationResult(
            check_type=check_type,
            passed=passed,
            evidence=evidence,
        )
        self.verifications[check_type] = vr
        self._save()

        # 컨텍스트 노드로도 기록 (추적용)
        status = "PASSED" if passed else "FAILED"
        node_id = self._generate_id("verify")
        node = ContextNode(
            id=node_id,
            type=NodeType.ANALYSIS,
            content=f"[VERIFICATION] {check_type}: {status}",
            importance=Importance.MEDIUM if passed else Importance.HIGH,
            metadata={
                "check_type": check_type,
                "passed": passed,
                "evidence": evidence[:500] if len(evidence) > 500 else evidence,
            },
        )
        self.nodes[node_id] = node
        self._save()

        return node_id

    def get_verification_status(self) -> dict:
        """
        모든 검증 상태 조회

        Returns:
            {
                "BUILD": {"passed": True, "fresh": True, "age_seconds": 120},
                ...
            }
        """
        now = datetime.now()
        result = {}

        for check_type, vr in self.verifications.items():
            try:
                ts = datetime.fromisoformat(vr.timestamp)
                age_seconds = (now - ts).total_seconds()
                fresh = age_seconds <= VERIFICATION_FRESHNESS_SECONDS
            except (ValueError, TypeError):
                age_seconds = float('inf')
                fresh = False

            result[check_type] = {
                "passed": vr.passed,
                "fresh": fresh,
                "age_seconds": int(age_seconds),
                "timestamp": vr.timestamp,
                "evidence": vr.evidence[:200] if len(vr.evidence) > 200 else vr.evidence,
            }

        return result

    def is_verification_fresh(self, check_type: str, max_age_seconds: int = VERIFICATION_FRESHNESS_SECONDS) -> bool:
        """
        검증 결과가 fresh한지 확인

        Args:
            check_type: 검증 유형
            max_age_seconds: 최대 유효 시간 (기본 5분)

        Returns:
            fresh 여부
        """
        if check_type not in self.verifications:
            return False

        vr = self.verifications[check_type]
        try:
            ts = datetime.fromisoformat(vr.timestamp)
            age_seconds = (datetime.now() - ts).total_seconds()
            return age_seconds <= max_age_seconds
        except (ValueError, TypeError):
            return False

    # === v13.0: Notepad Wisdom 연동 API ===

    def export_to_wisdom(self, plan_name: str) -> dict:
        """
        HIGH importance 노드를 Notepad Wisdom으로 내보내기

        Args:
            plan_name: 계획 이름 (디렉토리 이름으로 사용)

        Returns:
            {"learnings": int, "decisions": int, "issues": int}
        """
        wisdom_path = WISDOM_DIR / plan_name
        wisdom_path.mkdir(parents=True, exist_ok=True)

        counts = {"learnings": 0, "decisions": 0, "issues": 0}

        # 1. Learnings 내보내기
        learnings = [
            n for n in self.get_nodes_by_type(NodeType.LEARNING)
            if n.importance == Importance.HIGH
        ]
        if learnings:
            learning_file = wisdom_path / "learnings.md"
            lines = [
                "# Learnings",
                f"Exported from session: {self.session_id}",
                f"Exported at: {datetime.now().isoformat()}",
                "",
            ]
            for learn in learnings:
                lines.append(f"## {learn.timestamp[:10]}")
                lines.append(f"- {learn.content}")
                if learn.metadata:
                    for k, v in learn.metadata.items():
                        if k not in ("timestamp",):
                            lines.append(f"  - {k}: {v}")
                lines.append("")

            try:
                with open(learning_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                counts["learnings"] = len(learnings)
            except OSError:
                pass

        # 2. Decisions 내보내기
        decisions = [
            n for n in self.get_nodes_by_type(NodeType.DECISION)
            if n.importance == Importance.HIGH
        ]
        if decisions:
            decision_file = wisdom_path / "decisions.md"
            lines = [
                "# Decisions",
                f"Exported from session: {self.session_id}",
                f"Exported at: {datetime.now().isoformat()}",
                "",
            ]
            for dec in decisions:
                lines.append(f"## {dec.timestamp[:10]}: {dec.content[:50]}")
                lines.append(f"**Decision**: {dec.content}")
                if dec.metadata.get("rationale"):
                    lines.append(f"**Rationale**: {dec.metadata['rationale']}")
                if dec.metadata.get("alternatives"):
                    lines.append(f"**Rejected Alternatives**: {', '.join(dec.metadata['alternatives'])}")
                lines.append("")

            try:
                with open(decision_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                counts["decisions"] = len(decisions)
            except OSError:
                pass

        # 3. Issues 내보내기 (ERROR + SOLUTION 쌍)
        errors = [
            n for n in self.get_nodes_by_type(NodeType.ERROR)
            if n.importance == Importance.HIGH or n.metadata.get("resolved")
        ]
        solutions = {
            edge.source_id: self.nodes.get(edge.target_id)
            for edge in self.edges
            if edge.type == EdgeType.RESOLVED_BY
        }

        if errors:
            issue_file = wisdom_path / "issues.md"
            lines = [
                "# Issues",
                f"Exported from session: {self.session_id}",
                f"Exported at: {datetime.now().isoformat()}",
                "",
            ]
            for err in errors:
                lines.append(f"## {err.timestamp[:10]}: Issue")
                lines.append(f"**Error**: {err.content}")
                if err.metadata.get("context"):
                    lines.append(f"**Context**: {err.metadata['context']}")

                sol = solutions.get(err.id)
                if sol:
                    lines.append(f"**Solution**: {sol.content}")
                    if sol.metadata.get("approach"):
                        lines.append(f"**Approach**: {sol.metadata['approach']}")
                else:
                    lines.append("**Status**: Unresolved")
                lines.append("")

            try:
                with open(issue_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                counts["issues"] = len(errors)
            except OSError:
                pass

        return counts


# === 편의 함수 ===

def get_current_context() -> Optional[ContextManager]:
    """현재 세션의 컨텍스트 매니저 로드"""
    if CONTEXT_FILE.exists():
        try:
            with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                session_id = data.get("session_id")
                if session_id:
                    return ContextManager(session_id)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def create_context(session_id: Optional[str] = None) -> ContextManager:
    """새 컨텍스트 생성"""
    return ContextManager(session_id)


def get_compact_summary() -> str:
    """현재 컨텍스트의 압축 요약 조회"""
    ctx = get_current_context()
    if ctx:
        return ctx.generate_compact_summary()
    return "No context available"


def check_restorable_session() -> dict:
    """
    복원 가능한 이전 세션 확인

    Returns:
        {
            "restorable": bool,
            "session_info": dict,
            "restoration_prompt": str (restorable일 때만)
        }
    """
    # 1. context_graph.json 확인
    if not CONTEXT_FILE.exists():
        return {"restorable": False, "reason": "No previous context file"}

    ctx = get_current_context()
    if not ctx:
        return {"restorable": False, "reason": "Failed to load context"}

    session_info = ctx.get_session_info()
    if not session_info.get("has_context"):
        return {"restorable": False, "reason": "Empty context"}

    if not ctx.should_restore():
        return {
            "restorable": False,
            "reason": "Not enough important context to restore",
            "session_info": session_info,
        }

    return {
        "restorable": True,
        "session_info": session_info,
        "restoration_prompt": ctx.get_restoration_prompt(),
    }


def get_restoration_prompt() -> str:
    """
    이전 세션 복원용 프롬프트 조회

    /auto 시작 시 이 함수를 호출하여 이전 맥락을 주입합니다.

    Returns:
        복원 프롬프트 또는 빈 문자열
    """
    ctx = get_current_context()
    if ctx and ctx.should_restore():
        return ctx.get_restoration_prompt()
    return ""


def format_session_summary_for_display() -> str:
    """
    사용자에게 보여줄 세션 요약 포맷팅

    Returns:
        포맷팅된 세션 요약 문자열
    """
    result = check_restorable_session()

    if not result.get("restorable"):
        return f"복원 가능한 이전 세션이 없습니다. ({result.get('reason', 'Unknown')})"

    info = result["session_info"]

    lines = [
        "## 이전 세션 발견",
        "",
        f"- **세션 ID**: {info.get('session_id', 'Unknown')}",
        f"- **노드 수**: {info.get('node_count', 0)}개",
        f"- **중요 노드**: {info.get('high_importance_count', 0)}개",
        f"- **미해결 에러**: {info.get('unresolved_errors', 0)}개",
        f"- **마지막 업데이트**: {info.get('last_updated', 'Unknown')[:19]}",
        "",
    ]

    requests = info.get("requests", [])
    if requests:
        lines.append("### 원본 요청")
        for req in requests:
            lines.append(f"- {req}")
        lines.append("")

    decisions = info.get("decisions", [])
    if decisions:
        lines.append("### 주요 결정사항")
        for dec in decisions[:3]:
            lines.append(f"- {dec}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Context Manager Test ===\n")

    # 테스트 1: 컨텍스트 생성
    print("1. 컨텍스트 생성")
    ctx = ContextManager("test_session")
    print(f"   Session ID: {ctx.session_id}")

    # 테스트 2: 요청 기록
    print("\n2. 요청 기록")
    req_id = ctx.record_request("API 인증 기능 구현")
    print(f"   Request ID: {req_id}")

    # 테스트 3: 분석 기록
    print("\n3. 분석 기록")
    analysis_id = ctx.record_analysis(
        "JWT 토큰 방식이 적합함. 기존 세션 기반 인증에서 전환 필요.",
        caused_by=req_id,
        importance=Importance.HIGH
    )
    print(f"   Analysis ID: {analysis_id}")

    # 테스트 4: 결정 기록
    print("\n4. 결정 기록")
    decision_id = ctx.record_decision(
        "JWT + Refresh Token 방식 채택",
        rationale="확장성과 stateless 특성이 마이크로서비스 아키텍처에 적합",
        caused_by=analysis_id,
        alternatives=["Session Cookie 방식", "OAuth 2.0 Only"]
    )
    print(f"   Decision ID: {decision_id}")

    # 테스트 5: 파일 변경 기록
    print("\n5. 파일 변경 기록")
    file_id = ctx.record_file_change(
        "src/auth/jwt_handler.py",
        "create",
        "JWT 토큰 생성/검증 핸들러 구현",
        caused_by=decision_id
    )
    print(f"   File ID: {file_id}")

    # 테스트 6: 에러 기록
    print("\n6. 에러 기록")
    error_id = ctx.record_error(
        "PyJWT 모듈 import 실패: ModuleNotFoundError",
        caused_by=file_id,
        context="jwt_handler.py 실행 시"
    )
    print(f"   Error ID: {error_id}")

    # 테스트 7: 솔루션 기록
    print("\n7. 솔루션 기록")
    solution_id = ctx.record_solution(
        "pip install PyJWT 실행으로 해결",
        resolves=error_id,
        approach="의존성 설치"
    )
    print(f"   Solution ID: {solution_id}")

    # 테스트 8: 학습 기록
    print("\n8. 학습 기록")
    learning_id = ctx.record_learning(
        "JWT 관련 의존성은 requirements.txt에 추가해야 함",
        source=solution_id
    )
    print(f"   Learning ID: {learning_id}")

    # 테스트 9: 통계
    print("\n9. 통계")
    stats = ctx.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # 테스트 10: 관련 노드 조회
    print("\n10. 관련 노드 조회 (error)")
    related = ctx.get_related_nodes(error_id)
    print(f"    Caused by: {len(related['caused_by'])}개")
    print(f"    Resolved by: {len(related['resolved_by'])}개")

    # 테스트 11: Compact Summary
    print("\n11. Compact Summary")
    summary = ctx.generate_compact_summary()
    print(summary)

    # 테스트 12: 파일 크기 통계
    print("\n12. 파일 크기 및 제한 통계")
    file_stats = ctx.get_file_stats()
    for key, value in file_stats.items():
        print(f"    {key}: {value}")

    # 테스트 13: 강제 정리 (LOW importance만)
    print("\n13. 강제 정리 테스트")
    # LOW importance 노드 추가
    for i in range(5):
        ctx.record_analysis(
            f"테스트 분석 {i}",
            importance=Importance.LOW
        )
    print(f"    정리 전 노드 수: {len(ctx.nodes)}")
    cleanup_result = ctx.force_cleanup(keep_high_only=False)
    print(f"    정리 후 노드 수: {cleanup_result['after_nodes']}")
    print(f"    삭제된 노드: {cleanup_result['removed_nodes']}")

    # 테스트 14: 세션 복원 정보
    print("\n14. 세션 복원 정보")
    session_info = ctx.get_session_info()
    print(f"    has_context: {session_info.get('has_context')}")
    print(f"    node_count: {session_info.get('node_count')}")
    print(f"    high_importance: {session_info.get('high_importance_count')}")
    print(f"    should_restore: {ctx.should_restore()}")

    # 테스트 15: 복원 프롬프트 생성
    print("\n15. 복원 프롬프트 생성")
    restoration_prompt = ctx.get_restoration_prompt()
    print(f"    프롬프트 길이: {len(restoration_prompt)} 문자")
    if restoration_prompt:
        # 처음 500자만 출력
        preview = restoration_prompt[:500] + "..." if len(restoration_prompt) > 500 else restoration_prompt
        print(f"    미리보기:\n{preview}")

    # 테스트 16: check_restorable_session 함수
    print("\n16. check_restorable_session 함수")
    result = check_restorable_session()
    print(f"    restorable: {result.get('restorable')}")
    if result.get("session_info"):
        print(f"    requests: {result['session_info'].get('requests', [])}")

    # === v13.0 테스트 ===

    # 테스트 17: CircuitBreaker
    print("\n17. CircuitBreaker 테스트")
    cb = CircuitBreaker(max_failures=3)
    action1 = cb.record_failure("task_1", "첫 번째 에러")
    print(f"    1차 실패: {action1}")  # RETRY
    action2 = cb.record_failure("task_1", "두 번째 에러")
    print(f"    2차 실패: {action2}")  # ALTERNATE_APPROACH
    action3 = cb.record_failure("task_1", "세 번째 에러")
    print(f"    3차 실패: {action3}")  # ESCALATE_TO_ARCHITECT

    summary = cb.get_failure_summary("task_1")
    print(f"    실패 요약: count={summary['failure_count']}, rec={summary['recommendation']}")

    cb.reset("task_1")
    print(f"    리셋 후: {cb.get_failure_summary('task_1')['failure_count']}")

    # 테스트 18: ContextManager CircuitBreaker 통합
    print("\n18. ContextManager CircuitBreaker 통합")
    ctx.record_error("테스트 에러 1", context="테스트 상황")
    action = ctx.record_failure("test_task", error_id)
    print(f"    record_failure 결과: {action}")
    ctx.record_success("test_task")
    print("    record_success 완료")

    # 테스트 19: Verification Protocol
    print("\n19. Verification Protocol 테스트")
    verify_id = ctx.record_verification("BUILD", True, "npm run build: SUCCESS")
    print(f"    Verification ID: {verify_id}")
    ctx.record_verification("TEST", False, "pytest: 1 test failed")
    ctx.record_verification("LINT", True, "ruff check: no issues")

    status = ctx.get_verification_status()
    for check, info in status.items():
        print(f"    {check}: passed={info['passed']}, fresh={info['fresh']}, age={info['age_seconds']}s")

    fresh = ctx.is_verification_fresh("BUILD")
    print(f"    BUILD fresh: {fresh}")

    # 테스트 20: Notepad Wisdom 내보내기
    print("\n20. Notepad Wisdom 내보내기 테스트")
    export_counts = ctx.export_to_wisdom("test_plan")
    print(f"    내보내기 결과: {export_counts}")

    # 테스트 21: Escalation Summary
    print("\n21. Escalation Summary 테스트")
    # 에스컬레이션 상황 만들기
    for i in range(3):
        ctx.circuit_breaker.record_failure("escalate_task", f"에러 {i+1}")
    escalation = ctx.get_escalation_summary()
    print(f"    Escalation Summary 길이: {len(escalation)} 문자")
    if "escalate_task" in escalation:
        print("    escalate_task가 에스컬레이션 목록에 포함됨")

    print("\n=== 테스트 완료 ===")
