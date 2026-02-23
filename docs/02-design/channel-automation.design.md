# 채널 분석 자동화 설계

## 개요

새로운 Slack 채널을 channels.json에 등록하면 자동으로 전체 분석 파이프라인이 실행됩니다.

## 아키텍처

### 자동화 플로우

```mermaid
flowchart TD
    A[channels.json에 채널 추가] --> B[ChannelWatcher 30초 폴링 감지]
    B --> C[KnowledgeBootstrap.run_mastery 실행]
    C --> C1[1 learn_slack_full — 전체 메시지 수집]
    C1 --> C2[2 _fetch_thread_replies — 스레드 수집]
    C2 --> C3[3 _collect_channel_metadata — 멤버/핀/User ID 매핑]
    C3 --> C4[4 build_mastery_context user_map — TF-IDF + 샘플 추출]
    C4 --> C5[5 ChannelPRDWriter.write — PRD 생성]
    C5 --> C6[6 ChannelSonnetProfiler.build_profile pinned_messages — AI 프로파일 생성]
    C6 --> D[config/channel_contexts/{channel_id}.json 생성]
```

### 산출물

| 경로 | 내용 |
|------|------|
| `config/channel_contexts/{channel_id}.json` | AI 응답 전문가 컨텍스트 |
| `docs/channel-prd/{channel_id}.md` | 채널 PRD |

## 새 채널 등록 절차

### Step 1: channels.json 수정

`config/channels.json`에 다음 형식으로 추가:

```json
{
  "id": "C1234567890",
  "name": "채널명",
  "type": "slack",
  "roles": ["monitor", "chatbot"],
  "project_id": "secretary",
  "enabled": true
}
```

### Step 2: Gateway 서버 실행 중이면 자동 트리거

30초 내 ChannelWatcher가 감지 → 파이프라인 자동 실행

### Step 3: 수동 즉시 실행 (선택)

```bash
python -m scripts.knowledge.bootstrap mastery {channel_id} --project {project_id} --force
```

## 코드 구조

### ChannelWatcher (channel_watcher.py)

- 폴링 간격: 30초 (`DEFAULT_POLL_INTERVAL`)
- 새 채널 감지 시: `_run_full_pipeline(channel_id)` 비동기 실행
- `project_id`: `channels.json`의 `project_id` 필드 사용 (없으면 channel_id로 fallback)
- `_channel_projects` dict: `{channel_id: project_id}` 매핑 관리

```python
# _load_channel_ids()에서 _channel_projects도 함께 업데이트
self._channel_projects[ch_id] = ch.get("project_id", ch_id)

# _run_mastery()에서 project_id 조회
project_id = self._channel_projects.get(channel_id, channel_id)
```

### KnowledgeBootstrap (bootstrap.py)

- CLI: `python -m scripts.knowledge.bootstrap mastery {channel_id} --project {project_id}`
- `--force`: 강제 재분석 (캐시 무시)
- `run_mastery()` 반환 값: 요약 dict (`channel_id`, `channel_name`, `project_id`, `total_messages` 등)

## CLI 명령어

```bash
# Gateway 서버 시작 (ChannelWatcher 포함)
python scripts/gateway/server.py start

# 채널 즉시 수동 분석
python -m scripts.knowledge.bootstrap mastery {channel_id} --project {project_id}
python -m scripts.knowledge.bootstrap mastery {channel_id} --project {project_id} --force

# 결과 확인 (AI 프로파일)
cat config/channel_contexts/{channel_id}.json

# PRD 확인
cat docs/channel-prd/{channel_id}.md
```

## 주의사항

| 항목 | 내용 |
|------|------|
| Sonnet 프로파일 캐싱 | 7일 캐싱 — `--force`로 재생성 가능 |
| User ID 매핑 | channels.json 멤버 목록 → Slack API 호출 (0.5초 간격) |
| 대규모 채널 | 5000메시지+ 채널은 첫 실행 10-30분 소요 예상 |
| pinned_messages | `_build_profile()` 호출 시 `pinned_messages=[]` 명시 (run_mastery 반환값에 미포함) |
