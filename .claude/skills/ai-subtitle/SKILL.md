---
name: ai-subtitle
description: >
  Claude Vision을 사용한 AI 자막 생성. Read 도구로 이미지를 직접 분석하여
  휠 복원 마케팅 자막과 Phase(작업 단계)를 분류합니다.
version: 1.0.0

triggers:
  keywords:
    - "ai-subtitle"
    - "자막 생성"
    - "이미지 분석"
    - "휠 복원 자막"
  context:
    - "마케팅 자막 생성"
    - "이미지 Phase 분류"

capabilities:
  - analyze_wheel_images
  - generate_marketing_subtitle
  - classify_work_phase
  - export_subtitle_json

model_preference: sonnet
auto_trigger: false
token_budget: 3000
---

# AI Subtitle Generator (Claude Vision)

Claude의 Read 도구를 사용하여 이미지를 직접 분석하고 마케팅 자막을 생성합니다.

## 사용법

```bash
/ai-subtitle                           # 현재 temp/ 폴더 이미지 분석
/ai-subtitle -g <group_id>             # 특정 그룹 이미지 다운로드 후 분석
/ai-subtitle -g <group_id> -n 10       # 최대 10개 이미지 분석
/ai-subtitle --output subtitles.json   # 결과를 JSON 파일로 저장
```

## 실행 프로세스

### Phase 1: 이미지 준비

1. 그룹 ID가 제공되면 PocketBase에서 사진 조회
2. temp/ 디렉토리에 이미지 다운로드
3. 이미지 목록 확인

```bash
# 이미지 다운로드 (그룹 ID 제공 시)
node -e "
import('./src/api/pocketbase.js').then(async (pb) => {
  const photos = await pb.fetchPhotos('GROUP_ID', { limit: N });
  for (const p of photos) {
    await pb.downloadImage(p, './temp');
  }
});
"
```

### Phase 2: 이미지 분석 (Claude Vision)

각 이미지에 대해 Read 도구를 사용하여 직접 분석:

```
Read("./temp/image1.jpg")
Read("./temp/image2.jpg")
...
```

### Phase 3: 자막 생성

각 이미지를 분석하여 다음 정보 추출:

| 항목 | 설명 |
|------|------|
| **Phase** | overview / before / process / after |
| **자막** | 15자 이내 마케팅 문구 |
| **신뢰도** | 0.0 ~ 1.0 |

### Phase 4: 결과 출력

```json
{
  "group": "벤츠 GLS 마이바흐 버핑휠 원복",
  "generated_at": "2026-01-07T12:00:00Z",
  "subtitles": [
    {
      "id": "l7v0rfmav504yup",
      "file": "l7v0rfmav504yup.jpg",
      "phase": "after",
      "subtitle": "6시간의 정성이 담긴 마이바흐 휠",
      "confidence": 0.95
    }
  ]
}
```

## 자막 생성 가이드라인

### Phase 분류 기준

| Phase | 특징 | 예시 |
|-------|------|------|
| **overview** | 차량 전체 모습, 작업장 전경 | 차량 정면/후면, 리프트 위 |
| **before** | 손상/오염 상태, 스크래치, 더스트 | 브레이크 더스트, 연석 자국 |
| **process** | 작업 중, 세척, 도장, 연마 | 물 분사, 도장 부스 |
| **after** | 복원 완료, 깨끗한 상태, 광택 | 신차급 광택, 완성된 휠 |

### 자막 작성 원칙

1. **15자 이내** - 짧고 임팩트 있게
2. **한글 사용** - 외래어/영어 최소화
3. **이미지 상태 반영** - before는 손상 표현, after는 완성 표현
4. **마케팅 톤** - 전문성과 신뢰감 전달
5. **다양성 유지** - 동일 패턴 반복 금지

### 자막 예시

| Phase | 좋은 예 | 나쁜 예 |
|-------|---------|---------|
| overview | "오늘의 주인공, 마이바흐 GLS" | "차량입니다" |
| before | "브레이크 더스트와 스크래치 가득" | "완벽한 휠 광택" |
| process | "꼼꼼한 세척이 기본입니다" | "정밀 복원 완료" |
| after | "6시간의 정성이 담긴 결과" | "정밀 복원으로 완성된 휠" |

## 출력 형식

### 콘솔 출력

```
🎬 AI 자막 생성 (Claude Vision)
========================================

[1/10] l7v0rfmav504yup.jpg
  Phase: after (0.95)
  자막: "6시간의 정성이 담긴 마이바흐 휠"

[2/10] 49zhdkcixcjmgos.jpg
  Phase: before (0.90)
  자막: "브레이크 더스트와 스크래치 가득"

========================================
✅ 완료: 10개 이미지 분석
```

### JSON 파일 저장 (--output 옵션)

```bash
# 결과를 파일로 저장
/ai-subtitle -g GROUP_ID --output ./output/subtitles.json
```

## 주의사항

1. **이미지 수 제한**: 한 번에 최대 20개 권장 (토큰 제한)
2. **이미지 크기**: 큰 이미지는 자동으로 리사이즈됨
3. **지원 형식**: JPG, PNG, WebP
4. **temp 폴더**: 분석 후 자동 정리되지 않음

## 관련 파일

| 파일 | 설명 |
|------|------|
| `src/api/pocketbase.js` | PocketBase API (이미지 다운로드) |
| `src/ai/prompt-templates.js` | 프롬프트 템플릿 |
| `src/video/subtitle.js` | 자막 포맷팅 |
