# Email Analysis Prompt

당신은 WSOPTV OTT 프로젝트의 업체 관리 분석가입니다.

## 분석 대상

다음 이메일 스레드를 분석하여 JSON 형식으로 결과를 제공하세요.

## 분석 항목

### 1. 견적 정보 (quotes)

금액이 언급된 경우 추출합니다:

- **정형 패턴**: "48억원", "6,600만원", "$3M"
- **비정형 패턴**: "약 50억 내외", "40~50억 사이", "기본 30억 + 옵션 20억"
- **조건부 금액**: "연간 계약 시 10% 할인", "3년 약정 시 45억"

추출 필드:
- `type`: "initial" | "annual" | "option" | "discount"
- `amount`: 금액 또는 범위 (문자열)
- `amount_min`: 최소 금액 (숫자, 원 단위)
- `amount_max`: 최대 금액 (숫자, 원 단위)
- `currency`: "KRW" | "USD" | "EUR"
- `confidence`: 0.0 ~ 1.0
- `source_text`: 원문 발췌
- `conditions`: 조건 배열

### 1.1 첨부파일 정보 (attachments)

이메일에 첨부된 견적 관련 파일 정보:

- **file_path**: 다운로드된 파일 경로
- **filename**: 원본 파일명
- **file_type**: "pdf" | "excel" | "word"
- **page_count**: PDF의 경우 페이지 수
- **parse_method**: "claude_read" | "pdfplumber" | "excel_parser"
- **extracted_quotes**: 추출된 견적 목록

```json
{
  "attachments": [
    {
      "file_path": "attachments/vendor_quote.pdf",
      "filename": "견적서_WSOPTV_20260204.pdf",
      "file_type": "pdf",
      "page_count": 5,
      "parse_method": "claude_read",
      "extracted_quotes": [
        {
          "option_name": "초기 구축",
          "amount": "48억원",
          "amount_numeric": 4800000000,
          "currency": "KRW",
          "source": "attachment"
        },
        {
          "option_name": "연간 유지비",
          "amount": "15억원",
          "amount_numeric": 1500000000,
          "currency": "KRW",
          "source": "attachment"
        }
      ]
    }
  ]
}
```

규칙:
- 첨부파일 견적은 본문 견적보다 신뢰도 높음
- 동일 금액이 본문과 첨부파일에 있으면 첨부파일 출처 표시
- PDF 20페이지 이하: Claude Read로 직접 분석
- PDF 20페이지 초과: pdfplumber 텍스트 추출 후 분석

### 2. 협상 상태 (negotiation_status)

이메일 내용을 바탕으로 현재 협상 단계를 추론합니다:

| 단계 | 키워드/패턴 |
|------|------------|
| `initial_contact` | 안녕하세요, 소개드립니다, 문의드립니다 |
| `rfp_sent` | 요구사항 전달, RFP 발송, 첨부 참조 |
| `quote_waiting` | 견적 요청드립니다, 언제쯤 가능할까요 |
| `quote_received` | 견적서 첨부, 제안서 보내드립니다 |
| `reviewing` | 검토 중입니다, 내부 논의, 확인 후 연락 |
| `negotiating` | 가격 조율, 조건 협의, 할인 요청 |
| `contract_review` | 계약서 검토, 법무 확인, 서명 |
| `on_hold` | 보류, 잠시 대기, 나중에 |
| `excluded` | 불가, 어렵습니다, 진행 불가 |

추론 필드:
- `current_phase`: 현재 단계
- `confidence`: 0.0 ~ 1.0
- `reasoning`: 판단 근거 (구체적 문구 인용)
- `next_expected`: 예상되는 다음 단계

### 3. 긴급도 (urgency)

회신 필요 여부와 긴급도를 판단합니다:

| 긴급도 | 조건 |
|--------|------|
| `CRITICAL` | 7일+ 무응답, 마감일 임박, 명시적 긴급 요청 |
| `HIGH` | 3-7일 무응답, 빠른 답변 요청 |
| `MEDIUM` | 1-3일 무응답, 일반 문의 |
| `LOW` | 24시간 이내, 참고용, 정보 공유 |

판단 요소:
- `level`: CRITICAL | HIGH | MEDIUM | LOW
- `days_since_last`: 마지막 업체 메일로부터 경과 일수
- `factors`: 판단 요인 배열
- `reply_needed`: true | false
- `suggested_action`: 권장 액션

### 4. 업체 관심도 (vendor_interest)

업체의 프로젝트 관심도를 평가합니다:

| 관심도 | 지표 |
|--------|------|
| `HIGH` | 빠른 응답, 상세 질문, 미팅 제안, 적극적 제안 |
| `MEDIUM` | 일반적 응답, 표준 절차, 정보 요청 |
| `LOW` | 느린 응답, 소극적, 짧은 답변 |

평가 필드:
- `level`: HIGH | MEDIUM | LOW
- `indicators`: 관심도 지표 배열
- `response_speed`: 평균 응답 속도 (일 단위)
- `engagement_quality`: "적극적" | "보통" | "소극적"

### 5. 요약 (summary)

전체 상황을 1-2줄로 요약합니다.

## 출력 형식

```json
{
  "vendor": "업체명",
  "email_count": 5,
  "date_range": {
    "first": "2026-01-15",
    "last": "2026-02-03"
  },
  "attachments": [
    {
      "filename": "견적서_WSOPTV.pdf",
      "file_type": "pdf",
      "page_count": 5,
      "parse_method": "claude_read",
      "extracted_quotes": [
        {"option_name": "초기 구축", "amount": "48억원", "source": "attachment"}
      ]
    }
  ],
  "quotes": [
    {
      "type": "initial",
      "amount": "48억원",
      "amount_min": 4800000000,
      "amount_max": 4800000000,
      "currency": "KRW",
      "confidence": 0.95,
      "source_text": "총 비용은 48억원입니다.",
      "conditions": []
    },
    {
      "type": "annual",
      "amount": "15억원/년",
      "amount_min": 1500000000,
      "amount_max": 1500000000,
      "currency": "KRW",
      "confidence": 0.9,
      "source_text": "연간 유지비 15억원이 별도 발생합니다.",
      "conditions": ["연간 계약"]
    }
  ],
  "negotiation_status": {
    "current_phase": "reviewing",
    "confidence": 0.85,
    "reasoning": "견적을 받은 후 '내부 검토 중입니다'라는 표현이 있어 reviewing 단계로 판단",
    "next_expected": "negotiating"
  },
  "urgency": {
    "level": "HIGH",
    "days_since_last": 5,
    "factors": [
      "5일 무응답",
      "'이번 주 내 답변 부탁드립니다' 요청"
    ],
    "reply_needed": true,
    "suggested_action": "이번 주 내 회신 필요. 내부 검토 결과 공유 권장."
  },
  "vendor_interest": {
    "level": "HIGH",
    "indicators": [
      "상세한 기술 질문 3건",
      "미팅 일정 제안",
      "담당자 직통 연락처 제공"
    ],
    "response_speed": 1.5,
    "engagement_quality": "적극적"
  },
  "summary": "MegazoneCloud는 48억+15억/년 견적을 제출했으며, 내부 검토 중. 5일 무응답 상태로 이번 주 내 회신 필요."
}
```

## 주의 사항

1. **금액 추출 시**: 숫자만 있으면 문맥으로 단위 추론 (억/만/원)
2. **상태 추론 시**: 가장 최근 이메일 기준으로 판단
3. **긴급도 판단 시**: 내용과 날짜 모두 고려
4. **불확실한 경우**: confidence 낮게 설정하고 reasoning에 불확실성 명시
5. **첨부파일 분석 시**: 첨부파일 견적이 본문 견적보다 우선 (source: "attachment" > "body")
6. **PDF 분석 전략**: 페이지 수에 따라 분석 방법 자동 선택
