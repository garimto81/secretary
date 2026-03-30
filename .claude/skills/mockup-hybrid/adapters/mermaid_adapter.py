"""
Mermaid 다이어그램 어댑터

프롬프트를 분석하여 적합한 Mermaid 다이어그램 코드를 생성합니다.
"""

import re
from dataclasses import dataclass
from typing import Optional


# 다이어그램 타입별 트리거 키워드
DIAGRAM_TYPE_KEYWORDS = {
    "flowchart": {
        "ko": ["흐름", "플로우", "워크플로우", "프로세스", "단계", "절차", "파이프라인"],
        "en": ["flow", "workflow", "process", "step", "procedure", "pipeline"],
    },
    "sequenceDiagram": {
        "ko": ["시퀀스", "API 호출", "통신", "인증", "요청", "응답", "호출 흐름"],
        "en": ["sequence", "api call", "communication", "auth", "request", "response"],
    },
    "erDiagram": {
        "ko": ["DB", "데이터베이스", "스키마", "ER", "테이블 관계", "데이터 모델", "엔티티"],
        "en": ["database", "schema", "er", "table relation", "data model", "entity"],
    },
    "classDiagram": {
        "ko": ["클래스", "인터페이스", "상속", "객체", "OOP"],
        "en": ["class", "interface", "inheritance", "object", "oop"],
    },
    "stateDiagram-v2": {
        "ko": ["상태", "상태 머신", "상태 전이", "라이프사이클"],
        "en": ["state", "state machine", "state transition", "lifecycle"],
    },
    "gitGraph": {
        "ko": ["브랜치", "커밋", "머지", "깃 플로우"],
        "en": ["branch", "commit", "merge", "git flow"],
    },
}


@dataclass
class MermaidGenerationResult:
    """Mermaid 생성 결과"""
    success: bool
    mermaid_code: str
    diagram_type: str
    error_message: Optional[str] = None


class MermaidAdapter:
    """Mermaid 다이어그램 어댑터"""

    def detect_diagram_type(self, prompt: str) -> str:
        """프롬프트에서 다이어그램 타입 감지"""
        prompt_lower = prompt.lower()

        for diagram_type, keywords in DIAGRAM_TYPE_KEYWORDS.items():
            all_keywords = keywords["ko"] + keywords["en"]
            for keyword in all_keywords:
                if keyword.lower() in prompt_lower:
                    return diagram_type

        return "flowchart"  # 기본값

    def generate_from_prompt(self, prompt: str) -> MermaidGenerationResult:
        """
        프롬프트에서 mermaid 다이어그램 생성

        Args:
            prompt: 사용자 프롬프트

        Returns:
            MermaidGenerationResult 객체
        """
        try:
            # 다이어그램 타입 감지
            diagram_type = self.detect_diagram_type(prompt)

            # 프롬프트 파싱
            parts = re.split(r'\s*[-:]\s*', prompt, maxsplit=1)
            title = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else title

            # 다이어그램 타입별 스켈레톤 생성
            mermaid_code = self._generate_skeleton(diagram_type, title, description)

            return MermaidGenerationResult(
                success=True,
                mermaid_code=mermaid_code,
                diagram_type=diagram_type,
            )

        except Exception as e:
            return MermaidGenerationResult(
                success=False,
                mermaid_code="",
                diagram_type="flowchart",
                error_message=str(e),
            )

    def _generate_skeleton(self, diagram_type: str, title: str, description: str) -> str:
        """다이어그램 타입별 스켈레톤 생성"""
        generators = {
            "flowchart": self._flowchart_skeleton,
            "sequenceDiagram": self._sequence_skeleton,
            "erDiagram": self._er_skeleton,
            "classDiagram": self._class_skeleton,
            "stateDiagram-v2": self._state_skeleton,
            "gitGraph": self._git_skeleton,
        }

        generator = generators.get(diagram_type, self._flowchart_skeleton)
        return generator(title, description)

    def _flowchart_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
flowchart TD
    A[시작] --> B{{{{{description}}}}}
    B -->|Yes| C[처리]
    B -->|No| D[종료]
    C --> E[결과]
    E --> D"""

    def _sequence_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
sequenceDiagram
    participant Client
    participant Server
    participant DB

    Client->>Server: 요청
    Server->>DB: 조회
    DB-->>Server: 결과
    Server-->>Client: 응답"""

    def _er_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
erDiagram
    ENTITY_A ||--o{{ ENTITY_B : contains
    ENTITY_B ||--|{{ ENTITY_C : has
    ENTITY_A {{
        int id PK
        string name
        datetime created_at
    }}
    ENTITY_B {{
        int id PK
        int entity_a_id FK
        string value
    }}"""

    def _class_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
classDiagram
    class BaseClass {{
        +String name
        +execute() void
    }}
    class ConcreteA {{
        +process() void
    }}
    class ConcreteB {{
        +handle() void
    }}
    BaseClass <|-- ConcreteA
    BaseClass <|-- ConcreteB"""

    def _state_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : start
    Processing --> Success : complete
    Processing --> Error : fail
    Error --> Idle : retry
    Success --> [*]"""

    def _git_skeleton(self, title: str, description: str) -> str:
        return f"""---
title: {title}
---
gitGraph
    commit
    branch feature
    checkout feature
    commit
    commit
    checkout main
    merge feature
    commit"""

    def to_html_wrapper(self, mermaid_code: str, title: str = "Diagram") -> str:
        """
        Mermaid 코드를 CSS 제약이 적용된 HTML로 래핑

        CSS 제약: width/height auto, max-width 720px, max-height 1280px
        Mermaid.js CDN으로 렌더링
        """
        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=720">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #fff; padding: 16px; }}
    .diagram-container {{
      width: auto;
      max-width: 720px;
      height: auto;
      max-height: 1280px;
      overflow: hidden;
    }}
    .diagram-container svg {{
      max-width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
  <div class="diagram-container">
    <pre class="mermaid">{mermaid_code}</pre>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});</script>
</body>
</html>"""
