"""
공유 상수 정의

텍스트 절삭, rate limit 등 프로젝트 전체에서 사용하는 상수.
"""

# 텍스트 절삭 상수
MAX_TEXT_STORAGE = 4000          # DB 저장 시 최대 텍스트 길이
MAX_TEXT_LLM_CONTEXT = 12000     # LLM 컨텍스트 최대 길이
MAX_TEXT_DRAFT_DISPLAY = 2000    # Draft 파일 내 원본 메시지 표시 길이
MAX_OLLAMA_REASONING = 3000     # Ollama 추론 텍스트 최대 길이 (Claude 전달 시)

# Rate limit 상수
RATE_LIMIT_PIPELINE_PER_MINUTE = 10    # Pipeline toast 알림
RATE_LIMIT_CLAUDE_PER_MINUTE = 5       # Claude draft 생성
RATE_LIMIT_OLLAMA_PER_MINUTE = 10      # Ollama 분석
