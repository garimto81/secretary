# Design: 필터 로직 적합성 개선 (filter-logic-fix)

**Plan Reference**: docs/01-plan/filter-logic-fix.plan.md

## 설계 원칙

1. **거짓 양성 최소화**: substring → 단어 경계 정규식
2. **결정적 동작 보장**: set 순서 의존 제거
3. **안전한 fallback**: 실패 시 최소 동작 (비용 방지)
4. **하위 호환성 유지**: 기존 정상 감지 사례 보존

## 상세 설계

### 1. DedupFilter 개선 (handler.py) [CRITICAL]

**Before**:
```python
self._recent_ids: set = set()
# eviction:
self._recent_ids = set(list(self._recent_ids)[-500:])
```

**After**:
```python
from collections import OrderedDict
self._recent_ids: OrderedDict = OrderedDict()
# eviction: 가장 오래된 항목부터 제거
while len(self._recent_ids) > self._max_cache:
    self._recent_ids.popitem(last=False)
```

변경:
- `set` → `OrderedDict` (삽입 순서 보장)
- `add(key)` → `self._recent_ids[key] = True`
- `key in self._recent_ids` 동일하게 동작
- eviction: `popitem(last=False)`로 가장 오래된 항목 제거
- `_max_cache` 초과 시 즉시 1개씩 제거 (일괄 절반 삭제 대신)

### 2. Ollama fallback 수정 (handler.py) [CRITICAL]

**Before**:
```python
return AnalysisResult(needs_response=True, confidence=0.0, ...)
```

**After**:
```python
return AnalysisResult(needs_response=False, confidence=0.0, ...)
```

추가: 로깅 강화
```python
print("[Intelligence] WARNING: Ollama 비활성화/실패 - 분석 건너뜀 (needs_response=False)")
```

### 3. Pipeline 긴급 키워드 개선 (pipeline.py) [HIGH]

**Before**:
```python
if keyword.lower() in text_lower:
    return "urgent"
```

**After**:
- 컴파일된 정규식으로 전환
- 한국어: 앞뒤 공백/문장부호/시작/끝 경계 사용
- 부정 컨텍스트 패턴 추가

```python
# __init__에서 컴파일
self._urgent_patterns = []
for keyword in self.config["urgent_keywords"]:
    # 한국어 단어 경계: 공백/문장부호/문장 시작·끝
    pattern = re.compile(
        rf'(?:^|[\s,.\-!?;:()\"\'·]){re.escape(keyword)}(?:[\s,.\-!?;:()\"\'·]|$)',
        re.IGNORECASE
    )
    self._urgent_patterns.append(pattern)

# 부정 컨텍스트 (이 패턴에 매칭되면 긴급이 아님)
self._urgent_deny_patterns = [
    re.compile(r'지금까지|지금은|지금처럼', re.IGNORECASE),
    re.compile(r'바로가기|바로잡|바로옆|바로그', re.IGNORECASE),
    re.compile(r'빨리빨리', re.IGNORECASE),
]
```

### 4. Pipeline 액션 키워드 개선 (pipeline.py) [HIGH]

**Before**:
```python
for keyword in action_keywords:
    if keyword.lower() in text_lower:
        actions.append(f"action_request:{keyword}")
        break  # 첫 매칭에서 중단
```

**After**:
- break 제거 → 모든 매칭 키워드 수집
- 완료형 제외 패턴 추가
- deadline_patterns도 break 제거

```python
# 완료형 제외 패턴
self._action_completion_patterns = [
    re.compile(rf'{re.escape(kw)}(했|됐|완료|끝)', re.IGNORECASE)
    for kw in self.config["action_keywords"]
]

# 매칭 로직
matched_keywords = set()
for i, keyword in enumerate(action_keywords):
    if keyword.lower() in text_lower:
        # 완료형인지 확인
        if not self._action_completion_patterns[i].search(text):
            matched_keywords.add(keyword)

for kw in matched_keywords:
    actions.append(f"action_request:{kw}")
```

### 5. Pipeline 질문 패턴 개선 (pipeline.py) [MEDIUM]

**Before**:
```python
if "?" in text or "어떻게" in text or "언제" in text or "왜" in text:
```

**After**:
```python
# URL의 ? 제외
text_no_url = re.sub(r'https?://\S+', '', text)
# 코드 블록 제외
text_clean = re.sub(r'`[^`]*`', '', text_no_url)
# 한국어 질문어 단어 경계
question_patterns = [
    re.compile(r'\?(?![\w/=&])'),  # URL query string이 아닌 ?
    re.compile(r'(?:^|[\s])어떻게(?:[\s]|$)'),
    re.compile(r'(?:^|[\s])언제(?:[\s]|$)'),
    re.compile(r'(?:^|[\s])왜(?:[\s]|$)'),
]
if any(p.search(text_clean) for p in question_patterns):
    actions.append("question")
```

### 6. ProjectRegistry 키워드 매칭 개선 (project_registry.py) [HIGH]

**Before**:
```python
if project_id in text_lower:
    score += 1
if name in text_lower:
    score += 1
for keyword in keywords:
    if keyword.lower() in text_lower:
        score += 1
```

**After**:
```python
import re

def _word_match(term: str, text: str) -> bool:
    """단어 경계 매칭 (한국어/영어 혼합 지원)"""
    pattern = re.compile(
        rf'(?:^|[\s,.\-!?;:()\"\'·]){re.escape(term.lower())}(?:[\s,.\-!?;:()\"\'·]|$)',
        re.IGNORECASE
    )
    return bool(pattern.search(text))

if _word_match(project_id, text_lower):
    score += 1
if _word_match(name, text_lower):
    score += 1
for keyword in keywords:
    if _word_match(keyword, text_lower):
        score += 1
```

### 7. Gmail 라벨 선택 안정화 (gmail.py) [HIGH]

**Before**:
```python
user_labels = [l for l in meaningful if not l.isupper()]
if user_labels:
    return user_labels[0].lower()
```

**After**:
```python
user_labels = sorted([l for l in meaningful if not l.isupper()])
if user_labels:
    return user_labels[0].lower()
```

추가: `_seen_ids` eviction
```python
# connect()에서
self._max_seen = 5000

# _poll_new_messages()에서
if len(self._seen_ids) > self._max_seen:
    # 가장 오래된 절반 제거 (삽입 순서 보장 - Python 3.7+)
    to_keep = list(self._seen_ids)[-self._max_seen // 2:]
    self._seen_ids = set(to_keep)
```

### 8. ActionDispatcher 한국어 날짜 (action_dispatcher.py) [HIGH]

**Before**:
```python
return any(c.isdigit() for c in deadline_text)
```

**After**:
```python
KOREAN_RELATIVE_DATES = {"오늘", "내일", "모레", "이번", "다음", "금주", "차주"}

if any(c.isdigit() for c in deadline_text):
    return True
if any(kr in deadline_text for kr in self.KOREAN_RELATIVE_DATES):
    return True
return False
```

### 9. Slack is_mention 개선 (slack.py) [MEDIUM]

**Before**:
```python
is_mention="<@" in (msg.text or ""),
```

**After**:
```python
import re
# 사용자 멘션만 매칭 (<@U로 시작), 그룹 멘션 제외
is_mention=bool(re.search(r'<@U[A-Z0-9]+>', msg.text or "")),
```

### 10. _resolve_project confidence 비교 (handler.py) [MEDIUM]

**Before**:
```python
if rule_match.matched:
    return rule_match.project_id
```

**After**:
```python
if rule_match.matched and rule_match.confidence >= 0.6:
    return rule_match.project_id
```

Tier 3 sender match(confidence=0.5)가 Ollama 0.3-0.7 범위의 결과를 override하지 않도록 최소 confidence 0.6 요구.

### 11. mark_processed 타이밍 조정 (handler.py) [MEDIUM]

mark_processed()를 Step 6/7/8 완료 후로 이동:

**Before** (Step 4에서 호출):
```python
# Step 4
self.dedup.mark_processed(source_channel, message.id)
# Step 5-8...
```

**After** (전체 처리 완료 후):
```python
# Step 4 제거
# Step 5-8...
# 마지막에 호출
self.dedup.mark_processed(source_channel, message.id)
```

### 12. ContextMatcher 주석 수정 (context_matcher.py) [LOW]

줄 8: `"Tier 2: Keyword Match (confidence 0.7)"` → `"Tier 2: Keyword Match (confidence 0.6~0.8)"`
