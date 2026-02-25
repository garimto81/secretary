"""GitHub 저장소 private 전환 도구"""
import argparse
import sys
from pathlib import Path

import httpx

# Windows UTF-8 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GITHUB_API_BASE = "https://api.github.com"
TOKEN_PATH = Path(r"C:\claude\json\github_token.txt")


def load_token() -> str:
    """토큰 파일에서 Bearer 토큰 읽기"""
    if not TOKEN_PATH.exists():
        print(f"❌ 토큰 파일 없음: {TOKEN_PATH}")
        sys.exit(1)
    token = TOKEN_PATH.read_text().strip()
    if not token:
        print("❌ 토큰이 비어있음")
        sys.exit(1)
    return token


def create_headers(token: str) -> dict:
    """GitHub API 헤더 생성"""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def check_token(token: str) -> dict:
    """
    GET /user 호출하여 X-OAuth-Scopes 헤더 파싱
    Returns: {"login": str, "scopes": list, "has_repo_scope": bool}
    """
    headers = create_headers(token)
    with httpx.Client() as client:
        response = client.get(f"{GITHUB_API_BASE}/user", headers=headers)
        if response.status_code != 200:
            print(f"❌ Token 검증 실패: {response.status_code}")
            print(response.text)
            sys.exit(1)

        scopes_header = response.headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
        user_login = response.json().get("login", "unknown")

        return {
            "login": user_login,
            "scopes": scopes,
            "has_repo_scope": "repo" in scopes,
        }


def list_public_repos(token: str) -> list:
    """
    GET /user/repos?visibility=public&per_page=100
    페이지네이션 처리 (100개씩)
    Returns: [{"name": str, "full_name": str, "private": bool, "url": str}, ...]
    """
    headers = create_headers(token)
    repos = []
    page = 1

    with httpx.Client() as client:
        while True:
            response = client.get(
                f"{GITHUB_API_BASE}/user/repos",
                headers=headers,
                params={"visibility": "public", "per_page": 100, "page": page},
            )
            if response.status_code != 200:
                print(f"❌ 저장소 목록 조회 실패: {response.status_code}")
                sys.exit(1)

            data = response.json()
            if not data:
                break

            for repo in data:
                repos.append(
                    {
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "private": repo["private"],
                        "url": repo["html_url"],
                    }
                )

            page += 1

    return repos


def convert_to_private(token: str) -> dict:
    """
    모든 public 저장소를 private으로 전환
    Returns: {"success": int, "failed": int}
    """
    print("⚠️  WARNING: Private 전환을 시작합니다. 이는 되돌리기 어려운 작업입니다.")
    confirm = input("계속하시겠습니까? (yes/no): ")
    if confirm.lower() != "yes":
        print("작업 취소됨")
        sys.exit(0)

    repos = list_public_repos(token)
    headers = create_headers(token)

    success_count = 0
    failed_repos = []

    print(f"\n[Converting {len(repos)} repositories to private]")

    with httpx.Client() as client:
        for i, repo in enumerate(repos, 1):
            print(f"[{i}/{len(repos)}] {repo['full_name']}...", end=" ", flush=True)

            try:
                response = client.patch(
                    f"{GITHUB_API_BASE}/repos/{repo['full_name']}",
                    headers=headers,
                    json={"private": True},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    print("✓")
                    success_count += 1
                else:
                    print(f"✗ ({response.status_code})")
                    failed_repos.append((repo["full_name"], response.status_code, response.text))

            except httpx.RequestError as e:
                print(f"✗ (error: {e})")
                failed_repos.append((repo["full_name"], "error", str(e)))

    print("\n[Conversion Summary]")
    print(f"Success: {success_count}/{len(repos)}")
    if failed_repos:
        print(f"Failed: {len(failed_repos)}")
        for name, code, _msg in failed_repos:
            print(f"  - {name}: {code}")

    return {"success": success_count, "failed": len(failed_repos)}


def verify_conversion(token: str) -> bool:
    """
    GET /user/repos?visibility=public 호출
    공개 저장소가 남아있으면 False, 없으면 True
    """
    print("[Verifying conversion...]")

    repos = list_public_repos(token)

    if len(repos) == 0:
        print("✓ 모든 저장소가 private으로 전환되었습니다")
        return True
    else:
        print(f"✗ 공개 저장소 {len(repos)}개가 남아있습니다:")
        for repo in repos:
            print(f"  - {repo['full_name']}")
        return False


def main():
    parser = argparse.ArgumentParser(description="GitHub 저장소를 private으로 전환")
    parser.add_argument("--check-token", action="store_true", help="토큰 scope 확인")
    parser.add_argument("--list", action="store_true", help="Public 저장소 목록 조회 (dry-run)")
    parser.add_argument("--convert", action="store_true", help="Private 전환 실행")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="--convert 사용 시 실제 전환 실행 (없으면 dry-run)",
    )
    parser.add_argument("--verify", action="store_true", help="전환 결과 검증")

    args = parser.parse_args()

    if not any([args.check_token, args.list, args.convert, args.verify]):
        parser.print_help()
        sys.exit(1)

    token = load_token()

    if args.check_token:
        result = check_token(token)
        print("[Token Scope Check]")
        print(f"Login: {result['login']}")
        print(f"Scopes: {', '.join(result['scopes'])}")
        print(f"repo scope: {'✓' if result['has_repo_scope'] else '✗'}")

        if not result["has_repo_scope"]:
            print("\n❌ repo scope 없음. 토큰 재발급 필요")
            sys.exit(1)

    if args.list:
        repos = list_public_repos(token)
        print("\n[Public Repositories (dry-run)]")
        for i, repo in enumerate(repos, 1):
            print(f"{i}. {repo['full_name']} ({repo['url']})")
        print(f"\nTotal: {len(repos)} repository/repositories to convert")

    if args.convert:
        if not args.confirm:
            repos = list_public_repos(token)
            print(f"\n⚠️  WARNING: {len(repos)} 저장소를 private으로 전환합니다")
            print(
                "실제 전환하려면 --confirm 플래그 추가:\n"
                "python scripts/github_private_converter.py --convert --confirm"
            )
            sys.exit(0)

        # NFR-2: --convert --confirm 경로에서 scope 자동 사전 확인
        scope_result = check_token(token)
        if not scope_result["has_repo_scope"]:
            print("❌ repo scope 없음. 토큰 재발급 후 재시도하세요.")
            sys.exit(1)

        convert_to_private(token)

    if args.verify:
        verify_conversion(token)


if __name__ == "__main__":
    main()
