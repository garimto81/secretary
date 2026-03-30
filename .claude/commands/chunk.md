---
name: chunk
description: PDF 청킹 - 토큰 기반(텍스트) 또는 페이지 기반(레이아웃 보존) 분할
---

# /chunk - PDF 청킹 커맨드

PDF를 LLM 입력용 청크로 분할합니다.
**백그라운드 실행**으로 Claude Code 멈춤 현상을 방지합니다.

## 세 가지 모드

| 모드 | 옵션 | 특징 | 용도 |
|------|------|------|------|
| **토큰** (기본) | - | 텍스트만 추출 | 순수 텍스트 분석 |
| **페이지** | `--page` | **레이아웃 100% 보존** | 이미지/표 포함, 멀티모달 LLM |
| **PRD** | `--prd` | 계층형 청킹, 섹션 메타데이터 | PRD/기획서 MD/PDF |

## Usage

### 토큰 기반 (기본)

```
/chunk <pdf_path>                    # 기본 청킹 (4000토큰, 200 오버랩)
/chunk <pdf_path> --tokens 2000      # 토큰 수 지정
/chunk <pdf_path> --overlap 100      # 오버랩 지정
/chunk <pdf_path> --info             # PDF 정보만 확인 (빠름)
/chunk <pdf_path> --preview 3        # 처음 3개 청크 미리보기
```

### PRD 모드 (`--prd` 옵션) — MD 및 PDF 지원

```
/chunk <path>                    # 기본 (PDF 토큰 기반)
/chunk <path>.md --prd           # PRD 계층형 청킹 (Hierarchical)
/chunk <path>.md --prd --strategy semantic  # 표/목록 집중 PRD
/chunk <path>.md --prd --strategy fixed     # 고정 크기 + PRD 메타데이터
/chunk <path>.md --info          # 토큰 추정 + 추천 전략 출력
/chunk <path>.pdf --prd          # PDF도 PRD 모드 적용
```

### 페이지 기반 (`--page` 옵션)

```
/chunk <pdf_path> --page                    # 기본 10페이지씩 분할 (레이아웃 보존)
/chunk <pdf_path> --page --pages 20         # 20페이지씩 분할
/chunk <pdf_path> --page --inline           # Base64 JSON (API용)
/chunk <pdf_path> --page --info             # PDF 정보만 확인
```

## 핵심: 백그라운드 실행

**문제**: 큰 PDF 처리 시 Claude Code가 멈추는 현상
**해결**: 모든 청킹 작업은 **백그라운드로 실행**

### 실행 방식

1. **정보 확인** (`--info`): 빠른 foreground 실행
2. **청킹 작업**: 반드시 `run_in_background: true`로 실행
3. **결과 확인**: 완료 후 JSON 파일 경로 안내

## Workflow

### 토큰 모드 (기본)

1. PDF 경로 유효성 검사
2. `--info` 옵션 시: 빠른 정보 출력 (foreground)
3. 청킹 실행: **백그라운드**로 실행
   ```powershell
   python -m lib.pdf_utils chunk <pdf_path> --tokens <tokens> --overlap <overlap> -o <output.json>
   ```
4. 작업 상태 안내
5. 완료 시 JSON 파일 경로 및 요약 출력

### PRD 모드 (`--prd`) — v2.0.0

1. 파일 경로 유효성 검사 (MD/PDF 확인)
2. **분석 단계** (foreground, `--info` 동일 로직):
   - 토큰 추정치 계산
   - PRD 구조 감지 (heading 수, 요구사항 번호 패턴, 표 존재 여부)
   - 추천 전략 결정 (auto_select_strategy)
3. **사용자 확인 플로우** (R10 신규 — `--strategy` 미지정 시만):
   - 분석 결과 출력:
     ```
     파일: document.md
     토큰 추정: 85,000 (PRD 구조 감지: 예, 점수: 4/5)
     추천 전략: hierarchical (섹션 계층 보존)
     예상 청크: ~12개 (8,000 토큰/청크)
     ```
   - AskUserQuestion으로 선택 요청:
     - option 1: "승인 — hierarchical 전략으로 진행"
     - option 2: "전략 변경 — fixed / semantic 중 선택"
     - option 3: "취소"
   - `--yes` 또는 `--strategy` 명시 시 이 단계 스킵
4. **청킹 실행** (백그라운드):
   ```powershell
   python C:\claude\ebs\tools\pdf_chunker.py <path> --prd --strategy <chosen>
   ```
5. 완료 시 JSON 파일 경로 및 청크 요약 출력

### 페이지 모드 (`--page`)

1. PDF 경로 유효성 검사
2. `--info` 옵션 시: PDF 정보 출력 (페이지 수, 이미지 수 등)
3. 청킹 실행: **백그라운드**로 실행
   ```powershell
   # file 모드 (기본) - 분할 PDF 파일 생성
   python -m lib.pdf_utils chunk <pdf_path> --page --pages <N>

   # inline 모드 - Base64 JSON 출력 (API용)
   python -m lib.pdf_utils chunk <pdf_path> --page --pages <N> --inline -o <output.json>
   ```
4. 완료 시 출력 디렉토리/파일 경로 안내

## 출력 형식

### 성공 시
```
✅ 청킹 완료: input.pdf
- 청크 수: 15개
- 총 토큰: 45,000
- 출력 파일: C:\claude\...\input.chunks.json

다음 단계:
- JSON 파일을 읽어 청크별로 LLM에 전달하세요
```

### 백그라운드 실행 시
```
🔄 청킹 작업 시작 (백그라운드)
- 입력: large.pdf (120 페이지)
- 예상 청크: ~30개

⏳ 작업 ID: chunk_12345
완료 시 알림이 표시됩니다.
```

## 안전 규칙

1. **120초 타임아웃**: 백그라운드에서도 안전하게
2. **대용량 PDF (100+ 페이지)**: 자동 백그라운드 전환
3. **메모리 관리**: PyMuPDF의 점진적 페이지 처리

## 옵션 상세

### 공통 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--page` | **페이지 모드 활성화** (레이아웃 보존) | - |
| `--info` | PDF 정보만 출력 (빠름) | - |
| `-o, --output` | 출력 경로 | 자동 생성 |
| `--quiet` | 진행 메시지 숨기기 | - |

### 토큰 모드 전용 (기본)

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-t, --tokens` | 청크당 최대 토큰 수 | 4000 |
| `--overlap` | 청크 간 오버랩 토큰 수 | 200 |
| `--encoding` | tiktoken 인코딩 | cl100k_base |
| `--preview N` | 처음 N개 청크 미리보기 | - |

### 페이지 모드 전용 (`--page`)

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--pages N` | 청크당 페이지 수 | 10 |
| `--inline` | Base64 JSON 출력 (API용) | file |

### PRD 모드 전용 (`--prd`)

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--strategy` | 전략 강제 지정 (확인 단계 스킵) | auto |
| `--threshold N` | 청킹 임계 토큰 수 | 60000 |
| `--yes` | 확인 단계 스킵 (자동화용) | - |

## 스크립트 경로

```
# 통합 CLI
python -m lib.pdf_utils chunk [옵션]

# 소스 모듈
C:\claude\lib\pdf_utils\
```

## 의존성

- **필수**: `pymupdf` (PDF 파싱)
- **선택**: `tiktoken` (정확한 토큰 계산, 없으면 간이 추정 사용)

설치:
```powershell
pip install pymupdf tiktoken
```

## 예제

### 토큰 모드 (텍스트 추출)

```
# 기본 사용
/chunk C:\claude\docs\manual.pdf

# 토큰 크기 조정
/chunk C:\claude\docs\large.pdf --tokens 2000 --overlap 100

# 정보 확인 후 청킹
/chunk C:\claude\docs\report.pdf --info
/chunk C:\claude\docs\report.pdf --tokens 3000

# 미리보기로 확인
/chunk C:\claude\docs\test.pdf --preview 5
```

### 페이지 모드 (레이아웃 보존)

```
# 기본 사용 (10페이지씩 분할)
/chunk C:\claude\docs\manual.pdf --page

# 페이지 수 지정
/chunk C:\claude\docs\large.pdf --page --pages 20

# API 전송용 Base64 JSON 출력
/chunk C:\claude\docs\report.pdf --page --inline

# 정보 확인
/chunk C:\claude\docs\report.pdf --page --info

# 출력 디렉토리 지정
/chunk C:\claude\docs\manual.pdf --page -o C:\output\manual_chunks
```

### 언제 어떤 모드를 사용?

| 상황 | 권장 옵션 |
|------|----------|
| 순수 텍스트 분석 | (기본) |
| 이미지/표 포함 문서 | `--page` |
| Claude Vision API 사용 | `--page --inline` |
| 원본 레이아웃 중요 | `--page` |

## 출력 JSON 구조

### 토큰 모드 출력

```json
{
  "source_file": "C:\\claude\\docs\\input.pdf",
  "total_pages": 50,
  "total_chars": 120000,
  "total_tokens": 30000,
  "chunk_count": 8,
  "max_tokens_per_chunk": 4000,
  "overlap_tokens": 200,
  "encoding": "cl100k_base",
  "chunks": [
    {
      "chunk_id": 0,
      "text": "...",
      "token_count": 3980,
      "start_page": 1,
      "end_page": 6,
      "char_start": 0,
      "char_end": 15000
    }
  ]
}
```

### PRD 모드 출력

```json
{
  "source_file": "C:\\claude\\docs\\prd.md",
  "total_pages": 0,
  "total_chars": 45000,
  "total_tokens": 15000,
  "chunk_count": 8,
  "max_tokens_per_chunk": 8000,
  "overlap_tokens": 400,
  "encoding": "cl100k_base",
  "prd_mode": true,
  "strategy": "hierarchical",
  "section_tree": [
    {"title": "PRD 제목", "level": 1},
    {"title": "1. 개요", "level": 2},
    {"title": "2. 요구사항", "level": 2}
  ],
  "chunks": [
    {
      "chunk_id": 0,
      "text": "# 1. 개요\n\n내용...",
      "token_count": 1200,
      "section_path": ["PRD 제목", "1. 개요"],
      "level": 2,
      "parent_summary": "PRD 제목",
      "prev_chunk_id": null,
      "next_chunk_id": 1,
      "has_table": false,
      "has_code": false,
      "is_atomic": false,
      "start_char": 0,
      "end_char": 3600
    }
  ]
}
```

### 페이지 모드 - file 출력

```json
{
  "source_file": "manual.pdf",
  "total_pages": 120,
  "pages_per_chunk": 10,
  "chunk_count": 12,
  "format": "file",
  "output_dir": "manual_split/",
  "chunks": [
    {
      "chunk_id": 0,
      "start_page": 1,
      "end_page": 10,
      "page_count": 10,
      "file_path": "manual_split/manual_p001-010.pdf"
    }
  ]
}
```

### 페이지 모드 - inline 출력 (API용)

```json
{
  "source_file": "manual.pdf",
  "total_pages": 120,
  "pages_per_chunk": 10,
  "chunk_count": 12,
  "format": "inline",
  "chunks": [
    {
      "chunk_id": 0,
      "start_page": 1,
      "end_page": 10,
      "page_count": 10,
      "media_type": "application/pdf",
      "data_base64": "JVBERi0xLjQK..."
    }
  ]
}
```

## Related

- `/research` - 청킹 후 분석 작업
- `/auto` - 청킹 기반 자동화 워크플로우 (자율 반복 모드)

## Troubleshooting

### tiktoken 미설치 시
- 간이 토큰 추정 사용 (평균 3자 = 1토큰)
- 정확한 계산이 필요하면: `pip install tiktoken`

### 백그라운드 타임아웃
- 기본 120초 제한
- 초대형 PDF (500+ 페이지)는 청크 크기를 늘려서 실행

### 메모리 부족
- `--tokens` 값을 줄여서 실행 (예: 2000)
- PyMuPDF가 페이지 단위로 처리하므로 대용량도 안전
