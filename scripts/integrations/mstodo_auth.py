#!/usr/bin/env python3
"""
MS To Do Authentication - MSAL Browser OAuth

Usage:
    python mstodo_auth.py login    # OAuth 인증
    python mstodo_auth.py status   # 토큰 상태 확인
    python mstodo_auth.py logout   # 토큰 삭제

Token Location:
    C:\\claude\\json\\token_mstodo.json
"""

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

# Windows console UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# MSAL import
try:
    import msal
except ImportError:
    print("Error: MSAL 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install msal")
    sys.exit(1)

# Token storage path
TOKEN_FILE = Path(r"C:\claude\json\token_mstodo.json")

# Azure AD App Configuration
# Register at: https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade
# Use "Personal Microsoft accounts only" for consumer To Do
CLIENT_ID = "YOUR_CLIENT_ID_HERE"  # Replace with actual Azure AD App Client ID
AUTHORITY = "https://login.microsoftonline.com/consumers"  # Personal MS accounts
REDIRECT_PORT = 8400
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

# Microsoft Graph API Scopes
SCOPES = [
    "Tasks.ReadWrite",
    "User.Read",
]


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """OAuth callback handler for localhost redirect"""

    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        """Handle OAuth callback GET request"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            AuthCallbackHandler.auth_code = params["code"][0]
            self._send_success_response()
        elif "error" in params:
            AuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self._send_error_response(AuthCallbackHandler.error)
        else:
            self._send_error_response("Unknown error")

    def _send_success_response(self):
        """Send success HTML response"""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Authorization Successful</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: #107c10;">Authorization Successful</h1>
            <p>You can close this window and return to the terminal.</p>
            <script>setTimeout(function() { window.close(); }, 3000);</script>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_error_response(self, error: str):
        """Send error HTML response"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Authorization Failed</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: #d13438;">Authorization Failed</h1>
            <p>{error}</p>
        </body>
        </html>
        """
        self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        """Suppress HTTP request logs"""
        pass


def load_token() -> Optional[dict]:
    """Load token from file"""
    if not TOKEN_FILE.exists():
        return None

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_token(token: dict) -> None:
    """Save token to file"""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Add timestamp
    token["saved_at"] = datetime.now().isoformat()

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2, ensure_ascii=False)


def delete_token() -> bool:
    """Delete token file"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        return True
    return False


def create_msal_app() -> msal.PublicClientApplication:
    """Create MSAL public client application"""
    return msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
    )


def acquire_token_interactive() -> Optional[dict]:
    """
    Acquire token via browser OAuth flow

    1. Start local HTTP server for callback
    2. Open browser for Microsoft login
    3. Receive auth code via callback
    4. Exchange code for token
    """
    app = create_msal_app()

    # Build authorization URL
    auth_url = app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    print(f"Opening browser for Microsoft login...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")

    # Open browser
    webbrowser.open(auth_url)

    # Start local server to receive callback
    AuthCallbackHandler.auth_code = None
    AuthCallbackHandler.error = None

    server = HTTPServer(("localhost", REDIRECT_PORT), AuthCallbackHandler)
    server.timeout = 120  # 2 minute timeout

    print(f"Waiting for authorization (port {REDIRECT_PORT})...")

    try:
        server.handle_request()  # Handle single request
    except Exception as e:
        print(f"Error: Server error - {e}")
        return None
    finally:
        server.server_close()

    # Check for error
    if AuthCallbackHandler.error:
        print(f"Error: {AuthCallbackHandler.error}")
        return None

    # Check for auth code
    if not AuthCallbackHandler.auth_code:
        print("Error: No authorization code received")
        return None

    # Exchange code for token
    print("Exchanging code for token...")

    result = app.acquire_token_by_authorization_code(
        code=AuthCallbackHandler.auth_code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        print(f"Error: {result.get('error_description', result['error'])}")
        return None

    return result


def acquire_token_silent() -> Optional[dict]:
    """
    Acquire token silently using cached refresh token

    Returns:
        Token dict if successful, None otherwise
    """
    token_cache = load_token()
    if not token_cache:
        return None

    app = create_msal_app()

    # Try to get accounts from cache (MSAL doesn't persist accounts automatically)
    # We need to use the refresh token directly

    if "refresh_token" not in token_cache:
        return None

    # Try to refresh
    result = app.acquire_token_by_refresh_token(
        refresh_token=token_cache["refresh_token"],
        scopes=SCOPES,
    )

    if "error" in result:
        return None

    return result


def get_access_token() -> Optional[str]:
    """
    Get valid access token (refresh if needed)

    Returns:
        Access token string if successful, None otherwise
    """
    # Try silent acquisition first
    token = acquire_token_silent()

    if token and "access_token" in token:
        # Save refreshed token
        save_token(token)
        return token["access_token"]

    # Load existing token
    cached = load_token()
    if cached and "access_token" in cached:
        # Check if expired (rough check)
        # Note: For production, properly check expires_in
        return cached["access_token"]

    return None


def login() -> bool:
    """
    Perform interactive login

    Returns:
        True if successful, False otherwise
    """
    print("MS To Do OAuth Login")
    print("=" * 40)

    if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("Error: Azure AD Client ID가 설정되지 않았습니다.")
        print()
        print("설정 방법:")
        print("1. Azure Portal에서 앱 등록")
        print("   https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade")
        print("2. 'New registration' 클릭")
        print("3. Name: Secretary MS To Do")
        print("4. Supported account types: Personal Microsoft accounts only")
        print("5. Redirect URI: http://localhost:8400 (Web)")
        print("6. API permissions: Tasks.ReadWrite, User.Read")
        print("7. Authentication > Allow public client flows: Yes")
        print("8. 생성된 Application (client) ID를 이 파일에 입력")
        return False

    token = acquire_token_interactive()

    if not token:
        print("Login failed.")
        return False

    save_token(token)

    print()
    print("Login successful!")
    print(f"Token saved to: {TOKEN_FILE}")

    return True


def status() -> None:
    """Show token status"""
    print("MS To Do Token Status")
    print("=" * 40)

    token = load_token()

    if not token:
        print("Status: Not logged in")
        print(f"Token file: {TOKEN_FILE} (not found)")
        return

    print(f"Status: Logged in")
    print(f"Token file: {TOKEN_FILE}")
    print(f"Saved at: {token.get('saved_at', 'Unknown')}")
    print(f"Scopes: {', '.join(token.get('scope', []))}")

    # Check if token works
    access_token = get_access_token()
    if access_token:
        print("Access token: Valid")
    else:
        print("Access token: Expired or invalid (re-login required)")


def logout() -> None:
    """Delete stored token"""
    print("MS To Do Logout")
    print("=" * 40)

    if delete_token():
        print("Token deleted successfully.")
    else:
        print("No token to delete.")


def main():
    parser = argparse.ArgumentParser(description="MS To Do OAuth Authentication")
    parser.add_argument(
        "command",
        choices=["login", "status", "logout"],
        help="Command to execute"
    )
    args = parser.parse_args()

    if args.command == "login":
        success = login()
        sys.exit(0 if success else 1)
    elif args.command == "status":
        status()
    elif args.command == "logout":
        logout()


if __name__ == "__main__":
    main()
