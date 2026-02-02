#!/usr/bin/env python3
"""
MS To Do Adapter - Push-only synchronization

Usage:
    python mstodo_adapter.py login                          # OAuth 인증
    python mstodo_adapter.py lists                          # 리스트 조회
    python mstodo_adapter.py push --title "제목" --list personal
    python mstodo_adapter.py push --title "제목" --due 2026-02-10

Features:
    - Push-only (no delete/complete operations)
    - Duplicate check (title + due date)
    - List separation (personal/business)

Safety Rules:
    - Push-only: 삭제/완료 처리 금지
    - Duplicate prevention: 중복 항목 생성 방지
    - Graceful error handling
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

# Windows console UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# HTTP client
try:
    import httpx
except ImportError:
    print("Error: httpx 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install httpx")
    sys.exit(1)

# Import auth module
from mstodo_auth import (
    get_access_token,
    login as auth_login,
    TOKEN_FILE,
)


# Microsoft Graph API
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

# List configuration
class TodoList(Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


# List display names (created if not exist)
LIST_NAMES = {
    TodoList.PERSONAL: "Secretary - 개인",
    TodoList.BUSINESS: "Secretary - 법인",
}

# Config file for list IDs cache
CONFIG_FILE = Path(r"C:\claude\secretary\config\mstodo.json")


@dataclass
class TodoItem:
    """MS To Do item data model"""
    title: str
    body: Optional[str] = None
    due_date: Optional[date] = None
    importance: str = "normal"  # low, normal, high
    list_type: TodoList = TodoList.PERSONAL

    # Duplicate detection fields
    source: str = "secretary"
    source_id: Optional[str] = None


@dataclass
class MSTodoConfig:
    """Configuration for MS To Do adapter"""
    list_ids: dict = field(default_factory=dict)  # TodoList -> Graph API list ID

    @classmethod
    def load(cls) -> "MSTodoConfig":
        """Load config from file"""
        if not CONFIG_FILE.exists():
            return cls()

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(list_ids=data.get("list_ids", {}))
        except (json.JSONDecodeError, IOError):
            return cls()

    def save(self) -> None:
        """Save config to file"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"list_ids": self.list_ids}, f, indent=2)


class MSTodoAdapter:
    """
    MS To Do Push-only Adapter

    Features:
    - Browser OAuth authentication (via mstodo_auth)
    - List-specific task creation (personal/business)
    - Duplicate check (title + due date)
    """

    def __init__(self):
        self.config = MSTodoConfig.load()
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get HTTP client with auth header"""
        if self._client is None:
            access_token = get_access_token()
            if not access_token:
                raise RuntimeError("Not authenticated. Run 'login' first.")

            self._client = httpx.Client(
                base_url=GRAPH_API_BASE,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

        return self._client

    def close(self) -> None:
        """Close HTTP client"""
        if self._client:
            self._client.close()
            self._client = None

    def get_user_info(self) -> dict:
        """Get current user info"""
        client = self._get_client()
        response = client.get("/me")
        response.raise_for_status()
        return response.json()

    def get_lists(self) -> List[dict]:
        """
        Get all To Do lists

        Returns:
            List of todo list dicts with id, displayName, etc.
        """
        client = self._get_client()
        response = client.get("/me/todo/lists")
        response.raise_for_status()
        return response.json().get("value", [])

    def get_or_create_list(self, list_type: TodoList) -> str:
        """
        Get list ID, create if not exists

        Args:
            list_type: Personal or Business list type

        Returns:
            Graph API list ID
        """
        # Check cache first
        cached_id = self.config.list_ids.get(list_type.value)
        if cached_id:
            # Verify list still exists
            try:
                client = self._get_client()
                response = client.get(f"/me/todo/lists/{cached_id}")
                if response.status_code == 200:
                    return cached_id
            except httpx.HTTPError:
                pass

        # Search existing lists
        lists = self.get_lists()
        target_name = LIST_NAMES[list_type]

        for lst in lists:
            if lst.get("displayName") == target_name:
                # Found, cache and return
                self.config.list_ids[list_type.value] = lst["id"]
                self.config.save()
                return lst["id"]

        # Create new list
        client = self._get_client()
        response = client.post(
            "/me/todo/lists",
            json={"displayName": target_name}
        )
        response.raise_for_status()

        new_list = response.json()
        list_id = new_list["id"]

        # Cache and return
        self.config.list_ids[list_type.value] = list_id
        self.config.save()

        print(f"Created list: {target_name}")
        return list_id

    def get_tasks(self, list_type: TodoList, include_completed: bool = False) -> List[dict]:
        """
        Get tasks from a list

        Args:
            list_type: Personal or Business list type
            include_completed: Include completed tasks

        Returns:
            List of task dicts
        """
        list_id = self.get_or_create_list(list_type)
        client = self._get_client()

        # Filter: exclude completed by default
        url = f"/me/todo/lists/{list_id}/tasks"
        if not include_completed:
            url += "?$filter=status ne 'completed'"

        response = client.get(url)
        response.raise_for_status()

        return response.json().get("value", [])

    def check_duplicate(self, item: TodoItem) -> bool:
        """
        Check for duplicate task

        Duplicate criteria:
        - Same normalized title
        - Same due date (or both None)

        Args:
            item: TodoItem to check

        Returns:
            True if duplicate exists
        """
        existing = self.get_tasks(item.list_type, include_completed=False)

        normalized_title = self._normalize_title(item.title)

        for task in existing:
            # Compare title
            if self._normalize_title(task.get("title", "")) != normalized_title:
                continue

            # Compare due date
            task_due = task.get("dueDateTime")
            if task_due:
                task_due_date = task_due.get("dateTime", "").split("T")[0]
            else:
                task_due_date = None

            item_due_date = item.due_date.isoformat() if item.due_date else None

            if task_due_date == item_due_date:
                return True

        return False

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison: lowercase, collapse whitespace"""
        return " ".join(title.lower().split())

    def push_todo(self, item: TodoItem, skip_duplicate_check: bool = False) -> dict:
        """
        Push a TODO item (create)

        Args:
            item: TodoItem to create
            skip_duplicate_check: Skip duplicate check if True

        Returns:
            Result dict with status and task info

        Safety:
            - Push-only (no delete/update)
            - Duplicate check by default
        """
        # Duplicate check
        if not skip_duplicate_check:
            if self.check_duplicate(item):
                return {
                    "status": "skipped",
                    "reason": "duplicate",
                    "title": item.title,
                }

        # Get list ID
        list_id = self.get_or_create_list(item.list_type)

        # Build task payload
        task_data = {
            "title": item.title,
            "importance": item.importance,
        }

        if item.body:
            task_data["body"] = {
                "content": item.body,
                "contentType": "text",
            }

        if item.due_date:
            task_data["dueDateTime"] = {
                "dateTime": f"{item.due_date.isoformat()}T00:00:00",
                "timeZone": "Asia/Seoul",
            }

        # Create task
        client = self._get_client()
        response = client.post(
            f"/me/todo/lists/{list_id}/tasks",
            json=task_data
        )
        response.raise_for_status()

        created = response.json()

        return {
            "status": "created",
            "id": created.get("id"),
            "title": created.get("title"),
            "list": LIST_NAMES[item.list_type],
        }


def cmd_login() -> int:
    """Handle login command"""
    success = auth_login()
    return 0 if success else 1


def cmd_lists() -> int:
    """Handle lists command"""
    adapter = MSTodoAdapter()

    try:
        # Get user info
        user = adapter.get_user_info()
        print(f"User: {user.get('displayName', 'Unknown')} ({user.get('mail', user.get('userPrincipalName', ''))})")
        print()

        # Get lists
        lists = adapter.get_lists()
        print(f"To Do Lists ({len(lists)}):")

        for lst in lists:
            task_count = lst.get("wellknownListName", "")
            name = lst["displayName"]
            list_id = lst["id"]

            # Mark Secretary lists
            is_secretary = any(name == LIST_NAMES[lt] for lt in TodoList)
            marker = " [Secretary]" if is_secretary else ""

            print(f"  - {name}{marker}")
            print(f"    ID: {list_id}")

        return 0

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print("Error: Authentication expired. Run 'login' again.")
        else:
            print(f"Error: {e.response.status_code} - {e.response.text}")
        return 1
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    finally:
        adapter.close()


def cmd_push(args) -> int:
    """Handle push command"""
    adapter = MSTodoAdapter()

    try:
        # Parse list type
        list_type = TodoList.PERSONAL
        if args.list:
            try:
                list_type = TodoList(args.list.lower())
            except ValueError:
                print(f"Error: Unknown list type '{args.list}'. Use 'personal' or 'business'.")
                return 1

        # Parse due date
        due_date = None
        if args.due:
            try:
                due_date = datetime.strptime(args.due, "%Y-%m-%d").date()
            except ValueError:
                print(f"Error: Invalid date format '{args.due}'. Use YYYY-MM-DD.")
                return 1

        # Parse importance
        importance = "normal"
        if args.importance:
            if args.importance.lower() in ["low", "normal", "high"]:
                importance = args.importance.lower()
            else:
                print(f"Error: Invalid importance '{args.importance}'. Use low/normal/high.")
                return 1

        # Create item
        item = TodoItem(
            title=args.title,
            body=args.body,
            due_date=due_date,
            importance=importance,
            list_type=list_type,
        )

        # Push
        result = adapter.push_todo(item, skip_duplicate_check=args.force)

        # Output
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["status"] == "created":
                print(f"Created: {result['title']}")
                print(f"List: {result['list']}")
                print(f"ID: {result['id']}")
            elif result["status"] == "skipped":
                print(f"Skipped (duplicate): {result['title']}")

        return 0

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print("Error: Authentication expired. Run 'login' again.")
        else:
            print(f"Error: {e.response.status_code} - {e.response.text}")
        return 1
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    finally:
        adapter.close()


def main():
    parser = argparse.ArgumentParser(
        description="MS To Do Adapter - Push-only synchronization"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # login command
    subparsers.add_parser("login", help="OAuth authentication")

    # lists command
    subparsers.add_parser("lists", help="Show To Do lists")

    # push command
    push_parser = subparsers.add_parser("push", help="Push a TODO item")
    push_parser.add_argument("--title", required=True, help="Task title")
    push_parser.add_argument("--body", help="Task body/description")
    push_parser.add_argument("--due", help="Due date (YYYY-MM-DD)")
    push_parser.add_argument(
        "--list",
        choices=["personal", "business"],
        default="personal",
        help="Target list (default: personal)"
    )
    push_parser.add_argument(
        "--importance",
        choices=["low", "normal", "high"],
        default="normal",
        help="Task importance (default: normal)"
    )
    push_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip duplicate check"
    )
    push_parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output"
    )

    args = parser.parse_args()

    if args.command == "login":
        sys.exit(cmd_login())
    elif args.command == "lists":
        sys.exit(cmd_lists())
    elif args.command == "push":
        sys.exit(cmd_push(args))


if __name__ == "__main__":
    main()
