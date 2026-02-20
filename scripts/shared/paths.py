"""
공유 경로 정의

프로젝트 루트 자동 탐색 및 주요 경로 상수.
"""

from pathlib import Path


def _find_project_root() -> Path:
    """프로젝트 루트 자동 탐색 (CLAUDE.md 또는 .git 기준)"""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists() or (parent / ".git").exists():
            # secretary 하위 프로젝트인지 확인
            if parent.name == "secretary" or (parent / "scripts" / "gateway").exists():
                return parent
        # secretary 하위 프로젝트 직접 탐색
        if (parent / "secretary" / "CLAUDE.md").exists():
            return parent / "secretary"
    # fallback
    return Path(r"C:\claude\secretary")


PROJECT_ROOT = _find_project_root()

# 주요 디렉토리
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "scripts" / "intelligence" / "prompts"

# DB 파일
GATEWAY_DB = DATA_DIR / "gateway.db"
INTELLIGENCE_DB = DATA_DIR / "intelligence.db"

# 데이터 디렉토리
DRAFTS_DIR = DATA_DIR / "drafts"

# 설정 파일
GATEWAY_CONFIG = CONFIG_DIR / "gateway.json"
PROJECTS_CONFIG = CONFIG_DIR / "projects.json"

# Knowledge 컨텍스트 디렉토리
CHANNEL_CONTEXTS_DIR = CONFIG_DIR / "channel_contexts"
GMAIL_CONTEXTS_DIR = CONFIG_DIR / "gmail_contexts"

# Channel PRD 문서 디렉토리
CHANNEL_DOCS_DIR = CONFIG_DIR / "channel_docs"

# 채널 메시지 덤프 디렉토리
CHANNEL_DUMPS_DIR = DATA_DIR / "channel_dumps"
