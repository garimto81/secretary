# Secretary - AI Daily Report Automation

Gmail, Google Calendar, GitHub를 통합 분석하여 일일 업무 현황 리포트를 자동 생성하는 도구입니다.

## Features

| 기능 | 스크립트 | 설명 |
|------|----------|------|
| **이메일 분석** | `gmail_analyzer.py` | 미읽은 이메일에서 할일/마감일 추출 |
| **캘린더 분석** | `calendar_analyzer.py` | 오늘/이번주 일정, 회의 준비 항목 |
| **GitHub 분석** | `github_analyzer.py` | 최근 활동, 이슈/PR 현황 분석 |
| **일일 리포트** | `daily_report.py` | 종합 업무 현황 리포트 생성 |

## Quick Start

```bash
# 전체 일일 리포트
python scripts/daily_report.py

# 개별 분석
python scripts/gmail_analyzer.py --unread --days 3
python scripts/calendar_analyzer.py --today
python scripts/github_analyzer.py --days 5
```

## Output Example

```
📊 일일 업무 현황 (2026-01-09 (Fri))
========================================

🚨 GitHub 주의 필요 (4건)
├── 🐛 #87 (claude): 응답 없음 4일
├── 🐛 #85 (claude): 응답 없음 4일
├── 🔀 #24 (mad_framework): 리뷰 대기 17일

🔥 활발한 프로젝트 (최근 5일)
├── garimto81/claude: 50 commits, 11 issues
├── garimto81/youtuber_vertuber: 50 commits, 0 issues

========================================
📈 요약
├── 이메일 할일: 0건
├── 오늘 일정: 0건
└── GitHub 주의: 4건

⚡ 긴급 처리 필요: 4건
```

## Setup

### Google OAuth (Gmail, Calendar)

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. Gmail API, Calendar API 활성화
3. OAuth 2.0 클라이언트 ID 생성 (Desktop App)
4. `credentials.json` 다운로드

```bash
# 첫 실행 시 브라우저에서 인증
python scripts/gmail_analyzer.py
```

### GitHub Token

```bash
# 환경 변수 설정
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# 또는 gh CLI 사용
gh auth login
```

필요한 권한: `repo`, `read:user`

## CLI Options

### daily_report.py

```bash
python scripts/daily_report.py [--gmail] [--calendar] [--github] [--all] [--json]
```

| 옵션 | 설명 |
|------|------|
| `--gmail` | 이메일 분석만 |
| `--calendar` | 캘린더 분석만 |
| `--github` | GitHub 분석만 |
| `--all` | 모든 소스 분석 (기본값) |
| `--json` | JSON 형식 출력 |

### gmail_analyzer.py

```bash
python scripts/gmail_analyzer.py [--unread] [--days N] [--max N] [--json]
```

### calendar_analyzer.py

```bash
python scripts/calendar_analyzer.py [--today] [--week] [--days N] [--json]
```

### github_analyzer.py

```bash
python scripts/github_analyzer.py [--days N] [--repos] [--json]
```

## Attention Criteria

### Email

| 조건 | 긴급도 |
|------|--------|
| 마감일 D-1 | High |
| 마감일 D-3 | Medium |
| 미응답 48시간+ | Medium |
| 미응답 72시간+ | High |

### GitHub

| 조건 | 표시 |
|------|------|
| PR 리뷰 대기 3일+ | 주의 필요 |
| 이슈 응답 없음 4일+ | 주의 필요 |
| 마감일 초과 이슈 | 긴급 |

## Requirements

- Python 3.10+
- google-auth, google-auth-oauthlib
- google-api-python-client
- requests

## License

MIT
