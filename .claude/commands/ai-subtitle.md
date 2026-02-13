---
name: ai-subtitle
description: Claude Vision으로 이미지 분석 및 마케팅 자막 생성 (휠 복원 전문)
---

# /ai-subtitle - Claude Vision AI 자막 생성

Claude의 Read 도구를 사용하여 이미지를 직접 분석하고 마케팅 자막을 생성합니다.

## Usage

```bash
/ai-subtitle                           # temp/ 폴더 이미지 분석
/ai-subtitle -g <group_id>             # 그룹 이미지 다운로드 후 분석
/ai-subtitle -g <group_id> -n 10       # 최대 N개 이미지
/ai-subtitle --output subtitles.json   # JSON 파일로 저장
```

## Workflow

Claude Code가 수행하는 작업:

### Step 1: 이미지 준비

그룹 ID가 제공된 경우:
```bash
node -e "
import('./src/api/pocketbase.js').then(async (pb) => {
  const photos = await pb.fetchPhotos('GROUP_ID', { limit: N });
  for (const p of photos) await pb.downloadImage(p, './temp');
  console.log(JSON.stringify(photos.map(p => p.id)));
});
"
```

### Step 2: 이미지 목록 확인

```bash
ls ./temp/*.jpg
```

### Step 3: 이미지 분석 (Read 도구 사용)

**각 이미지를 Read 도구로 직접 열어서 분석합니다:**

```
Read("./temp/image1.jpg")  → Phase 분류 + 자막 생성
Read("./temp/image2.jpg")  → Phase 분류 + 자막 생성
...
```

### Step 4: 결과 출력

콘솔에 결과 테이블 출력 + JSON 파일 생성 (옵션)

## 분석 가이드라인

### Phase 분류 기준

| Phase | 시각적 특징 | 자막 톤 |
|-------|------------|---------|
| **overview** | 차량 전체, 작업장 전경 | 소개/도입 |
| **before** | 손상, 스크래치, 브레이크 더스트, 오염 | 문제 제기 |
| **process** | 세척 중, 연마 중, 도장 부스, 작업 장면 | 과정 설명 |
| **after** | 깨끗한 표면, 광택, 완성된 상태 | 결과/만족 |

### 자막 작성 규칙

1. **길이**: 15자 이내 (한글 기준)
2. **언어**: 순한글 (외래어 최소화)
3. **톤**: 전문적이고 신뢰감 있게
4. **다양성**: 이미지마다 다른 표현 사용
5. **정확성**: 이미지 상태를 정확히 반영

### 좋은 자막 예시

| Phase | 자막 예시 |
|-------|----------|
| overview | "오늘의 주인공, 마이바흐 GLS" |
| overview | "휠 복원이 필요한 순간" |
| before | "브레이크 더스트와 스크래치 가득" |
| before | "연석에 긁힌 상처들" |
| before | "세월의 흔적이 남긴 자국" |
| process | "꼼꼼한 세척이 기본입니다" |
| process | "정밀 도장으로 새 생명을" |
| process | "장인의 손길이 닿는 순간" |
| after | "6시간의 정성이 담긴 결과" |
| after | "출고 당시 그대로, 완벽한 복원" |
| after | "마이바흐의 품격을 되찾다" |

### 나쁜 자막 예시 (피해야 할 패턴)

- "정밀 복원으로 완성된 신차급 휠의 광택" (너무 김)
- 모든 이미지에 동일한 "신차급 광택" 사용 (다양성 부족)
- before 이미지에 "완벽한 광택" (상태 불일치)
- 영어/외래어 과다 사용

## Output Format

### 콘솔 출력

```
🎬 AI 자막 생성 (Claude Vision)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| # | 파일명 | Phase | 자막 |
|---|--------|-------|------|
| 1 | l7v0rfmav504yup | after | 6시간의 정성이 담긴 마이바흐 휠 |
| 2 | 49zhdkcixcjmgos | before | 브레이크 더스트와 스크래치 가득 |
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 완료: 10개 이미지 분석
📁 저장됨: ./output/subtitles.json
```

### JSON 출력 (--output 옵션)

```json
{
  "group_id": "2pg9uk43qkqo688",
  "group_name": "벤츠 GLS 마이바흐 버핑휠 원복",
  "generated_at": "2026-01-07T12:00:00Z",
  "model": "claude-sonnet",
  "subtitles": [
    {
      "id": "l7v0rfmav504yup",
      "file": "l7v0rfmav504yup.jpg",
      "phase": "after",
      "subtitle": "6시간의 정성이 담긴 마이바흐 휠",
      "confidence": 0.95
    }
  ],
  "phase_summary": {
    "overview": 2,
    "before": 3,
    "process": 2,
    "after": 3
  }
}
```

## 영상 생성에 적용

생성된 자막을 영상에 적용:

```bash
# JSON 파일의 자막을 사용하여 영상 생성
node src/index.js create -g GROUP_ID --auto --subtitle-json ./output/subtitles.json
```

## 제한사항

- 한 번에 최대 20개 이미지 권장 (토큰 제한)
- 이미지 형식: JPG, PNG, WebP
- 큰 이미지는 자동 리사이즈됨

## Related Commands

- `/commit` - 변경사항 커밋
- `/check` - 코드 품질 검사
