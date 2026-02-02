---
name: ai-login
description: AI 서비스 인증 설정 (GPT, Gemini)
---

# /ai-login - AI 서비스 인증

## 사용법

```bash
# AI 서비스 인증
/ai-login openai                    # OpenAI OAuth 인증
/ai-login google                    # Google OAuth 인증
/ai-login google --api-key          # API Key 방식

# 상태 확인
/ai-login status                    # 전체 인증 상태
/ai-login logout                    # 모든 세션 로그아웃
```

---

## 실행 지시 (CRITICAL)

$ARGUMENTS를 파싱하여 **Bash tool로 해당 스크립트를 직접 실행**하세요.
스크립트를 사용자에게 보여주지 말고 바로 실행하세요.

---

## openai | gpt

**우선순위**: Codex CLI 토큰 재사용 → Browser OAuth

1. Codex CLI (`~/.codex/auth.json`) 토큰이 있으면 자동 재사용
2. 없거나 만료되면 Browser OAuth 진행

```bash
python -c "
import asyncio
import sys
import json
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, 'C:/claude/ultimate-debate/src')

from ultimate_debate.auth.providers.openai_provider import OpenAIProvider
from ultimate_debate.auth.providers.base import AuthToken
from ultimate_debate.auth.storage import TokenStore

def try_import_codex_token():
    '''Codex CLI 토큰 가져오기 시도'''
    import base64
    from datetime import timedelta

    codex_auth_path = Path.home() / '.codex' / 'auth.json'

    if not codex_auth_path.exists():
        return None

    try:
        with open(codex_auth_path, 'r') as f:
            codex_auth = json.load(f)

        tokens = codex_auth.get('tokens', {})
        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')

        if not access_token:
            return None

        # JWT access_token에서 exp 클레임 추출 (검증 없이 디코딩만)
        def decode_jwt_exp(token: str):
            try:
                # JWT 구조: header.payload.signature
                parts = token.split('.')
                if len(parts) != 3:
                    return None

                # payload (두 번째 파트) 디코딩
                payload = parts[1]
                # base64url → base64 변환 (패딩 추가)
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload)
                claims = json.loads(decoded)

                return claims.get('exp')
            except Exception:
                return None

        # JWT에서 만료 시간 추출
        exp_timestamp = decode_jwt_exp(access_token)

        if exp_timestamp:
            # Unix timestamp → datetime
            expires_at = datetime.fromtimestamp(exp_timestamp)
        else:
            # exp 없으면 last_refresh + 10일로 추정
            last_refresh_str = codex_auth.get('last_refresh')
            if last_refresh_str:
                last_refresh = datetime.fromisoformat(last_refresh_str.replace('Z', '+00:00'))
                last_refresh = last_refresh.replace(tzinfo=None)
                expires_at = last_refresh + timedelta(days=10)
            else:
                # last_refresh도 없으면 현재 시간 + 10일
                expires_at = datetime.now() + timedelta(days=10)

        # 만료 확인
        if expires_at <= datetime.now():
            print('[INFO] Codex CLI 토큰이 만료됨')
            return None

        # AuthToken 생성
        return AuthToken(
            provider='openai',
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type='Bearer',
            scopes=['openid', 'profile', 'email', 'offline_access']
        )
    except Exception as e:
        print(f'[WARN] Codex CLI 토큰 읽기 실패: {e}')
        return None

async def main():
    print()
    print('=' * 60)
    print('  OpenAI Authentication')
    print('=' * 60)
    print()

    store = TokenStore()

    # 1. 이미 저장된 유효 토큰 확인
    existing_token = store.get_valid_token('openai')
    if existing_token:
        print('[OK] 이미 유효한 OpenAI 토큰이 있습니다.')
        print(f'    만료: {existing_token.expires_at.strftime(\"%Y-%m-%d %H:%M\")}')
        print()
        return

    # 2. Codex CLI 토큰 재사용 시도
    print('[1/2] Codex CLI 토큰 확인 중...')
    codex_token = try_import_codex_token()

    if codex_token:
        print('[OK] Codex CLI 토큰 발견!')
        print(f'    만료: {codex_token.expires_at.strftime(\"%Y-%m-%d %H:%M\")}')

        # 저장
        await store.save(codex_token)
        print()
        print('[SUCCESS] OpenAI 토큰 자동 가져오기 완료!')
        print('이제 /verify --provider openai로 GPT 검증을 사용할 수 있습니다.')
        return

    # 3. Codex CLI 토큰 없음 → Browser OAuth
    print('[INFO] Codex CLI 토큰 없음 → Browser OAuth 진행')
    print()
    print('브라우저에서 로그인하면 자동으로 인증이 완료됩니다.')
    print()

    provider = OpenAIProvider()

    try:
        # use_device_code=False로 Browser OAuth 사용 (자동 콜백)
        token = await provider.login(use_device_code=False)

        # 토큰 저장
        await store.save(token)

        print()
        print('[SUCCESS] OpenAI 로그인 완료!')
        print(f'   토큰 만료: {token.expires_at.strftime(\"%Y-%m-%d %H:%M\")}')
        print()
        print('이제 /verify --provider openai로 GPT 검증을 사용할 수 있습니다.')

    except Exception as e:
        print(f'[ERROR] 인증 실패: {e}')
        sys.exit(1)

asyncio.run(main())
"
```

---

## status

```bash
python -c "
import sys
sys.path.insert(0, 'C:/claude/ultimate-debate/src')
from ultimate_debate.auth.storage import TokenStore

storage = TokenStore()

print()
print('## AI Authentication Status')
print()
print('| Provider | Status | Type |')
print('|----------|--------|------|')

openai_token = storage.get_valid_token('openai')
if openai_token:
    token_type = 'API Key' if openai_token.token_type == 'api_key' else 'OAuth'
    expires = '만료 없음' if openai_token.expires_at is None else openai_token.expires_at.strftime('%Y-%m-%d %H:%M')
    print(f'| OpenAI | VALID (expires {expires}) | {token_type} |')
else:
    print('| OpenAI | Not logged in | - |')

google_token = storage.get_valid_token('google')
if google_token:
    token_type = 'API Key' if google_token.token_type == 'api_key' else 'OAuth'
    expires = '만료 없음' if google_token.expires_at is None else google_token.expires_at.strftime('%Y-%m-%d %H:%M')
    print(f'| Google | VALID (expires {expires}) | {token_type} |')
else:
    print('| Google | Not logged in | - |')

print()
"
```

---

## logout

```bash
python -c "
import asyncio
import sys
sys.path.insert(0, 'C:/claude/ultimate-debate/src')
from ultimate_debate.auth.storage import TokenStore

async def logout():
    storage = TokenStore()
    await storage.clear_all()
    print('[OK] All AI sessions logged out.')

asyncio.run(logout())
"
```

---

## google | gemini

**인증 우선순위**: Gemini CLI 토큰 → 저장된 토큰 → Browser OAuth

로컬 HTTP 서버를 띄워 콜백을 자동 수신합니다. 포트 충돌 시 자동으로 다음 포트를 시도합니다.

```bash
python -c "
import asyncio
import sys
sys.path.insert(0, 'C:/claude/ultimate-debate/src')

from ultimate_debate.auth.providers.google_provider import GoogleProvider, try_import_gemini_cli_token
from ultimate_debate.auth.storage import TokenStore

async def main():
    print()
    print('=' * 60)
    print('  Google Authentication')
    print('=' * 60)
    print()

    store = TokenStore()

    # 1. 이미 저장된 유효 토큰 확인
    existing_token = store.get_valid_token('google')
    if existing_token:
        token_type = '(API Key)' if existing_token.token_type == 'api_key' else '(OAuth)'
        expires_info = '만료 없음' if existing_token.expires_at is None else existing_token.expires_at.strftime('%Y-%m-%d %H:%M')
        print(f'[OK] 이미 유효한 Google 토큰이 있습니다 {token_type}')
        print(f'    만료: {expires_info}')
        print()
        return

    # 2. Gemini CLI 토큰 재사용 시도
    print('[1/3] Gemini CLI 토큰 확인 중 (~/.gemini/oauth_creds.json)...')
    gemini_token = try_import_gemini_cli_token()

    if gemini_token:
        print('[OK] Gemini CLI 토큰 발견!')
        expires_info = '만료 없음' if gemini_token.expires_at is None else gemini_token.expires_at.strftime('%Y-%m-%d %H:%M')
        print(f'    만료: {expires_info}')

        # 저장
        await store.save(gemini_token)
        print()
        print('[SUCCESS] Gemini CLI 토큰 자동 가져오기 완료!')
        print('이제 /verify --provider gemini로 Gemini 검증을 사용할 수 있습니다.')
        return

    print('[INFO] Gemini CLI 토큰 없음')

    # 3. Browser OAuth 진행
    print()
    print('[2/3] Browser OAuth 진행...')
    print('브라우저에서 로그인하면 자동으로 인증이 완료됩니다.')
    print('(포트 8080~8089 중 사용 가능한 포트 자동 선택)')
    print()

    provider = GoogleProvider()

    try:
        token = await provider.login()

        # 토큰 저장
        await store.save(token)

        print()
        print('[SUCCESS] Google 로그인 완료!')
        print(f'   토큰 만료: {token.expires_at.strftime(\"%Y-%m-%d %H:%M\")}')
        print()
        print('이제 /verify --provider gemini로 Gemini 검증을 사용할 수 있습니다.')

    except Exception as e:
        print(f'[ERROR] 인증 실패: {e}')
        sys.exit(1)

asyncio.run(main())
"
```

---

## google --api-key | gemini --api-key

API Key 방식으로 인증합니다. Google AI Studio에서 발급받은 키를 입력합니다.
https://aistudio.google.com/app/apikey

```bash
python -c "
import asyncio
import sys
import getpass
sys.path.insert(0, 'C:/claude/ultimate-debate/src')

from ultimate_debate.auth.providers.google_provider import GoogleProvider
from ultimate_debate.auth.storage import TokenStore

async def main():
    print()
    print('=' * 60)
    print('  Google API Key Authentication')
    print('=' * 60)
    print()
    print('Google AI Studio에서 API Key를 발급받으세요:')
    print('https://aistudio.google.com/app/apikey')
    print()

    # API Key 입력
    api_key = getpass.getpass('API Key: ').strip()

    if not api_key:
        print('[ERROR] API Key가 입력되지 않았습니다.')
        sys.exit(1)

    provider = GoogleProvider()

    try:
        print()
        print('[1/2] API Key 검증 중...')
        token = await provider.login_with_api_key(api_key)

        # 토큰 저장
        print('[2/2] 토큰 저장 중...')
        store = TokenStore()
        await store.save(token)

        print()
        print('[SUCCESS] Google API Key 인증 완료!')
        print('   토큰 타입: API Key (만료 없음)')
        print()
        print('이제 /verify --provider gemini로 Gemini 검증을 사용할 수 있습니다.')

    except ValueError as e:
        print(f'[ERROR] {e}')
        sys.exit(1)
    except Exception as e:
        print(f'[ERROR] 인증 실패: {e}')
        sys.exit(1)

asyncio.run(main())
"
```

---

## 인증 흐름

### Google 인증 우선순위

```
/ai-login google
    │
    ├─ 1순위: 저장된 유효 토큰 확인 (TokenStore)
    │         └─ 유효하면 재사용 → 완료
    │
    ├─ 2순위: Gemini CLI 토큰 확인 (~/.gemini/oauth_creds.json)
    │         └─ 유효하면 재사용 → 완료
    │
    └─ 3순위: Browser OAuth 진행
              └─ 동적 포트 할당 (8080~8089)

/ai-login google --api-key
    │
    └─ API Key 입력 프롬프트 → 검증 → 저장
```

### OpenAI 인증 우선순위

```
/ai-login openai
    │
    ├─ 1순위: 저장된 유효 토큰 확인
    │
    ├─ 2순위: Codex CLI 토큰 (~/.codex/auth.json)
    │
    └─ 3순위: Browser OAuth (포트 1455)
```

> **자동 방식**: `/ai-login google` → 로그인 → 완료 (1단계)
> **API Key 방식**: `/ai-login google --api-key` → 키 입력 → 완료
