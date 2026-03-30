"""
문서 스캐너 - 마크다운 문서의 섹션별 시각화 필요성 판단

문서를 ## 헤딩 기준으로 분할하고, 각 섹션을 NEED/SKIP/EXIST로 분류합니다.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from lib.mockup_hybrid import MockupBackend


class SectionClassification(Enum):
    """섹션 분류"""
    NEED = "need"       # 시각화 필요
    SKIP = "skip"       # 서술형 (시각화 불필요)
    EXIST = "exist"     # 이미 시각화 존재


@dataclass
class SectionScanResult:
    """섹션 스캔 결과"""
    heading: str                           # "## 인증 흐름"
    heading_level: int                     # 2
    content: str                           # 섹션 본문 전체
    line_start: int                        # 문서에서 시작 라인
    line_end: int                          # 문서에서 끝 라인
    classification: SectionClassification  # NEED / SKIP / EXIST
    suggested_tier: Optional[MockupBackend] = None  # MERMAID / HTML / STITCH
    suggested_diagram_type: Optional[str] = None    # flowchart, sequenceDiagram 등
    reason: str = ""                       # 분류 이유


@dataclass
class DocumentScanResult:
    """문서 전체 스캔 결과"""
    doc_path: Path
    total_sections: int
    need_sections: list[SectionScanResult] = field(default_factory=list)
    skip_sections: list[SectionScanResult] = field(default_factory=list)
    exist_sections: list[SectionScanResult] = field(default_factory=list)

    @property
    def mockup_count(self) -> int:
        return len(self.need_sections)

    def summary(self) -> str:
        """스캔 결과 요약"""
        lines = [
            f"문서 스캔: {self.doc_path}",
            f"  발견: {self.total_sections}개 섹션 중 {self.mockup_count}개 시각화 대상",
        ]
        if self.exist_sections:
            lines.append(f"  기존: {len(self.exist_sections)}개 (이미 시각화 존재)")
        if self.skip_sections:
            skip_names = [s.heading.lstrip('#').strip() for s in self.skip_sections]
            lines.append(f"  스킵: {', '.join(skip_names)}")
        return "\n".join(lines)


# 시각화가 필요한 섹션 제목 키워드
VISUAL_HEADING_KEYWORDS = {
    "mermaid": {
        "flowchart": ["흐름", "플로우", "flow", "워크플로우", "workflow", "프로세스", "process", "파이프라인", "pipeline", "절차", "단계"],
        "sequenceDiagram": ["시퀀스", "sequence", "API 호출", "api call", "통신", "communication", "인증", "auth", "요청/응답"],
        "erDiagram": ["데이터 모델", "data model", "데이터베이스", "database", "DB 스키마", "db schema", "스키마", "schema", "ER", "엔티티", "entity", "테이블 관계"],
        "classDiagram": ["클래스", "class", "인터페이스", "interface", "상속", "inheritance", "객체 구조"],
        "stateDiagram-v2": ["상태", "state", "상태 머신", "state machine", "라이프사이클", "lifecycle", "상태 전이"],
        "gitGraph": ["브랜치", "branch", "깃 플로우", "git flow", "브랜칭 전략"],
    },
    "html": ["화면", "UI", "레이아웃", "layout", "페이지", "page", "대시보드", "dashboard", "와이어프레임", "wireframe", "목업", "mockup", "컴포넌트", "component"],
}

# 시각화 불필요한 섹션 제목 키워드
SKIP_HEADING_KEYWORDS = ["배경", "background", "개요", "overview", "요약", "summary", "참고", "reference", "위험", "risk", "제약", "constraint", "변경 로그", "changelog", "목차", "toc"]


class DocumentScanner:
    """마크다운 문서 스캐너"""

    def scan(self, doc_path: Path, force: bool = False) -> DocumentScanResult:
        """
        문서를 스캔하여 섹션별 시각화 필요성 판단

        Args:
            doc_path: 마크다운 문서 경로
            force: True면 EXIST 섹션도 NEED로 재분류

        Returns:
            DocumentScanResult 객체
        """
        content = doc_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 섹션 분리 (## 이상의 헤딩)
        sections = self._split_sections(lines)

        result = DocumentScanResult(
            doc_path=doc_path,
            total_sections=len(sections),
        )

        for section in sections:
            scan = self._classify_section(section, force)

            if scan.classification == SectionClassification.NEED:
                result.need_sections.append(scan)
            elif scan.classification == SectionClassification.EXIST:
                result.exist_sections.append(scan)
            else:
                result.skip_sections.append(scan)

        return result

    def _split_sections(self, lines: list[str]) -> list[dict]:
        """## 헤딩 기준으로 섹션 분리"""
        sections = []
        current = None

        for i, line in enumerate(lines):
            heading_match = re.match(r'^(#{2,4})\s+(.+)$', line)
            if heading_match:
                if current:
                    current["line_end"] = i - 1
                    current["content"] = "\n".join(lines[current["content_start"]:i]).strip()
                    sections.append(current)

                current = {
                    "heading": line,
                    "heading_text": heading_match.group(2).strip(),
                    "heading_level": len(heading_match.group(1)),
                    "line_start": i,
                    "content_start": i + 1,
                    "line_end": i,
                    "content": "",
                }

        # 마지막 섹션
        if current:
            current["line_end"] = len(lines) - 1
            current["content"] = "\n".join(lines[current["content_start"]:]).strip()
            sections.append(current)

        return sections

    def _classify_section(self, section: dict, force: bool) -> SectionScanResult:
        """섹션 분류"""
        heading_text = section["heading_text"]
        content = section["content"]

        # 1. EXIST 체크: 이미 mermaid 블록이나 이미지가 있는가?
        if not force and self._has_existing_visual(content):
            return SectionScanResult(
                heading=section["heading"],
                heading_level=section["heading_level"],
                content=content,
                line_start=section["line_start"],
                line_end=section["line_end"],
                classification=SectionClassification.EXIST,
                reason="이미 시각화 존재",
            )

        # 2. SKIP 체크: 명확한 서술형 섹션인가?
        heading_lower = heading_text.lower()
        for kw in SKIP_HEADING_KEYWORDS:
            if kw.lower() in heading_lower:
                return SectionScanResult(
                    heading=section["heading"],
                    heading_level=section["heading_level"],
                    content=content,
                    line_start=section["line_start"],
                    line_end=section["line_end"],
                    classification=SectionClassification.SKIP,
                    reason=f"서술형 섹션 ('{kw}')",
                )

        # 3. NEED 체크: 시각화 키워드 매칭
        # 3a. Mermaid 키워드 (다이어그램 타입별)
        for diagram_type, keywords in VISUAL_HEADING_KEYWORDS["mermaid"].items():
            for kw in keywords:
                if len(kw) <= 3:
                    if re.search(r'\b' + re.escape(kw.lower()) + r'\b', heading_lower):
                        return SectionScanResult(
                            heading=section["heading"],
                            heading_level=section["heading_level"],
                            content=content,
                            line_start=section["line_start"],
                            line_end=section["line_end"],
                            classification=SectionClassification.NEED,
                            suggested_tier=MockupBackend.MERMAID,
                            suggested_diagram_type=diagram_type,
                            reason=f"Mermaid {diagram_type} ('{kw}')",
                        )
                elif kw.lower() in heading_lower:
                    return SectionScanResult(
                        heading=section["heading"],
                        heading_level=section["heading_level"],
                        content=content,
                        line_start=section["line_start"],
                        line_end=section["line_end"],
                        classification=SectionClassification.NEED,
                        suggested_tier=MockupBackend.MERMAID,
                        suggested_diagram_type=diagram_type,
                        reason=f"Mermaid {diagram_type} ('{kw}')",
                    )

        # 3b. HTML 키워드
        for kw in VISUAL_HEADING_KEYWORDS["html"]:
            if kw.lower() in heading_lower:
                return SectionScanResult(
                    heading=section["heading"],
                    heading_level=section["heading_level"],
                    content=content,
                    line_start=section["line_start"],
                    line_end=section["line_end"],
                    classification=SectionClassification.NEED,
                    suggested_tier=MockupBackend.HTML,
                    reason=f"HTML wireframe ('{kw}')",
                )

        # 4. 본문 내용 기반 추가 판단
        content_result = self._analyze_content(section)
        if content_result:
            return content_result

        # 5. 기본값: SKIP
        return SectionScanResult(
            heading=section["heading"],
            heading_level=section["heading_level"],
            content=content,
            line_start=section["line_start"],
            line_end=section["line_end"],
            classification=SectionClassification.SKIP,
            reason="시각화 키워드 없음",
        )

    def _has_existing_visual(self, content: str) -> bool:
        """이미 시각화가 존재하는지 확인"""
        # mermaid 코드 블록
        if re.search(r'```mermaid', content):
            return True
        # 이미지 참조
        if re.search(r'!\[.*?\]\(.*?\)', content):
            return True
        return False

    def _analyze_content(self, section: dict) -> Optional[SectionScanResult]:
        """본문 내용 기반 추가 판단 (제목에 키워드 없을 때)"""
        content = section["content"]
        content_lower = content.lower()

        # 번호 매긴 단계가 3개 이상 있으면 flowchart 후보
        numbered_steps = re.findall(r'^\d+[\.\)]\s', content, re.MULTILINE)
        if len(numbered_steps) >= 3:
            return SectionScanResult(
                heading=section["heading"],
                heading_level=section["heading_level"],
                content=content,
                line_start=section["line_start"],
                line_end=section["line_end"],
                classification=SectionClassification.NEED,
                suggested_tier=MockupBackend.MERMAID,
                suggested_diagram_type="flowchart",
                reason=f"번호 단계 {len(numbered_steps)}개 감지 → flowchart",
            )

        # 화살표 패턴이 있으면 flowchart/sequence 후보
        arrow_patterns = re.findall(r'→|->|>>|에서\s.*으로|부터\s.*까지', content)
        if len(arrow_patterns) >= 2:
            return SectionScanResult(
                heading=section["heading"],
                heading_level=section["heading_level"],
                content=content,
                line_start=section["line_start"],
                line_end=section["line_end"],
                classification=SectionClassification.NEED,
                suggested_tier=MockupBackend.MERMAID,
                suggested_diagram_type="flowchart",
                reason=f"화살표/흐름 패턴 {len(arrow_patterns)}개 감지",
            )

        return None
