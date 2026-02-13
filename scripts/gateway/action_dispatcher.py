#!/usr/bin/env python3
"""
Action Dispatcher - Gateway Pipeline에서 탐지된 액션을 실제 자동화 스크립트로 디스패치

액션 타입:
- deadline: TODO 생성 + Calendar dry-run
- action_request: TODO 생성
- question: 로그만 출력 (실제 처리 없음)
"""

import asyncio
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 3중 import fallback 패턴
try:
    from scripts.gateway.models import NormalizedMessage, Priority
except ImportError:
    try:
        from gateway.models import NormalizedMessage, Priority
    except ImportError:
        from .models import NormalizedMessage, Priority

# todo_generator import (3중 fallback)
try:
    from scripts.actions import todo_generator
except ImportError:
    try:
        from actions import todo_generator
    except ImportError:
        # 상대 import는 패키지 내부에서만 작동
        import importlib.util
        todo_generator_path = Path(__file__).parent.parent / "actions" / "todo_generator.py"
        spec = importlib.util.spec_from_file_location("todo_generator", todo_generator_path)
        todo_generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(todo_generator)

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """디스패치 결과"""
    action: str
    success: bool
    output_path: Optional[Path] = None
    calendar_dry_run: Optional[str] = None
    error: Optional[str] = None


class ActionDispatcher:
    """액션 디스패처 - 탐지된 액션을 실제 자동화로 연결"""

    KOREAN_RELATIVE_DATES = {"오늘", "내일", "모레", "이번", "다음", "금주", "차주"}

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: True면 실제 파일 생성/subprocess 실행 없이 로그만 출력
        """
        self.dry_run = dry_run

    async def dispatch(self, message: NormalizedMessage, actions: list[str]) -> list[DispatchResult]:
        """
        액션 리스트를 순회하며 각 액션을 처리

        Args:
            message: 원본 메시지
            actions: Pipeline에서 탐지한 액션 리스트 (예: ["deadline:2026-02-15", "action_request:check"])

        Returns:
            DispatchResult 리스트
        """
        results = []

        for action in actions:
            try:
                if action.startswith("deadline:"):
                    result = await self._handle_deadline(message, action)
                    results.append(result)

                elif action.startswith("action_request:"):
                    result = await self._handle_action_request(message, action)
                    results.append(result)

                elif action.startswith("question"):
                    # question은 실제 처리 없음 (로그만)
                    logger.info(f"[ActionDispatcher] Question detected: {message.id} - skipping auto-action")
                    results.append(DispatchResult(
                        action=action,
                        success=True,
                    ))

                else:
                    logger.warning(f"[ActionDispatcher] Unknown action type: {action}")
                    results.append(DispatchResult(
                        action=action,
                        success=False,
                        error=f"Unknown action type: {action}"
                    ))

            except Exception as e:
                logger.error(f"[ActionDispatcher] Failed to dispatch action '{action}': {e}", exc_info=True)
                results.append(DispatchResult(
                    action=action,
                    success=False,
                    error=str(e)
                ))

        return results

    async def _handle_deadline(self, message: NormalizedMessage, action: str) -> DispatchResult:
        """
        deadline 액션 처리: TODO 생성 + Calendar dry-run

        Args:
            message: 원본 메시지
            action: "deadline:2026-02-15" 형식

        Returns:
            DispatchResult
        """
        deadline_text = action.split(":", 1)[1] if ":" in action else ""

        # 1. TODO 생성
        todo_entry = self._create_todo_entry(message, deadline_text, "deadline")

        if self.dry_run:
            logger.info(f"[ActionDispatcher][DRY-RUN] Would create TODO: {todo_entry['title']}")
            todo_path = Path("dry-run-todo.md")
        else:
            try:
                todo_path = await todo_generator.append_todo_from_message(
                    title=todo_entry["title"],
                    priority=todo_entry["priority"],
                    sender=todo_entry["sender"],
                    deadline=todo_entry.get("deadline", ""),
                    source_type="gateway"
                )
                logger.info(f"[ActionDispatcher] TODO created: {todo_path}")
            except Exception as e:
                logger.error(f"[ActionDispatcher] TODO creation failed: {e}")
                return DispatchResult(
                    action=action,
                    success=False,
                    error=f"TODO creation failed: {e}"
                )

        # 2. Calendar dry-run (deadline 파싱 가능한 경우만)
        calendar_result = None
        if deadline_text and self._is_parsable_date(deadline_text):
            if self.dry_run:
                calendar_result = f"[DRY-RUN] Would call calendar_creator.py for deadline: {deadline_text}"
            else:
                try:
                    calendar_result = await self._run_calendar_dry_run(message, deadline_text)
                except Exception as e:
                    logger.warning(f"[ActionDispatcher] Calendar dry-run failed: {e}")
                    calendar_result = f"Calendar dry-run failed: {e}"

        return DispatchResult(
            action=action,
            success=True,
            output_path=todo_path,
            calendar_dry_run=calendar_result
        )

    async def _handle_action_request(self, message: NormalizedMessage, action: str) -> DispatchResult:
        """
        action_request 액션 처리: TODO 생성만

        Args:
            message: 원본 메시지
            action: "action_request:check" 형식

        Returns:
            DispatchResult
        """
        keyword = action.split(":", 1)[1] if ":" in action else ""

        # TODO 생성
        todo_entry = self._create_todo_entry(message, "", keyword)

        if self.dry_run:
            logger.info(f"[ActionDispatcher][DRY-RUN] Would create TODO: {todo_entry['title']}")
            todo_path = Path("dry-run-todo.md")
        else:
            try:
                todo_path = await todo_generator.append_todo_from_message(
                    title=todo_entry["title"],
                    priority=todo_entry["priority"],
                    sender=todo_entry["sender"],
                    source_type="gateway"
                )
                logger.info(f"[ActionDispatcher] TODO created: {todo_path}")
            except Exception as e:
                logger.error(f"[ActionDispatcher] TODO creation failed: {e}")
                return DispatchResult(
                    action=action,
                    success=False,
                    error=f"TODO creation failed: {e}"
                )

        return DispatchResult(
            action=action,
            success=True,
            output_path=todo_path
        )

    def _create_todo_entry(self, message: NormalizedMessage, deadline_text: str = "", keyword: str = "") -> dict:
        """
        NormalizedMessage에서 TODO 호환 dict 생성

        Args:
            message: 원본 메시지
            deadline_text: 마감일 텍스트 (deadline 액션에서만)
            keyword: 액션 키워드 (action_request 액션에서만)

        Returns:
            todo_generator에 전달할 dict
        """
        # 우선순위 매핑
        if message.priority in (Priority.URGENT, Priority.HIGH):
            priority = "high"
        elif message.priority == Priority.NORMAL:
            priority = "medium"
        else:
            priority = "low"

        # 채널 이름
        channel = message.channel.value if hasattr(message.channel, 'value') else str(message.channel)

        # 발신자
        sender = message.sender_name or "Unknown"

        # 메시지 텍스트 (최대 50자)
        message_text = (message.text or "")[:50]
        if len(message.text or "") > 50:
            message_text += "..."

        # 타이틀 생성
        if deadline_text:
            title = f"[{channel}] {sender}: {message_text} (마감: {deadline_text})"
        elif keyword:
            title = f"[{channel}] {sender}: {message_text} ({keyword})"
        else:
            title = f"[{channel}] {sender}: {message_text}"

        return {
            "type": "gateway",
            "priority": priority,
            "title": title,
            "sender": sender,
            "deadline": deadline_text if deadline_text else "",
        }

    def _is_parsable_date(self, deadline_text: str) -> bool:
        """
        deadline_text가 날짜로 파싱 가능한지 확인

        Args:
            deadline_text: 마감일 텍스트

        Returns:
            True if 파싱 가능할 것으로 예상
        """
        if not deadline_text:
            return False

        # YYYY-MM-DD 패턴
        if len(deadline_text.split("-")) == 3:
            return True

        # 숫자가 포함되어 있으면 파싱 시도 가능
        if any(c.isdigit() for c in deadline_text):
            return True

        # 한국어 상대 날짜
        if any(kr in deadline_text for kr in self.KOREAN_RELATIVE_DATES):
            return True

        return False

    async def _run_calendar_dry_run(self, message: NormalizedMessage, deadline_text: str) -> str:
        """
        Calendar dry-run subprocess 실행 (--confirm 없이)

        Args:
            message: 원본 메시지
            deadline_text: 마감일 텍스트

        Returns:
            subprocess 출력 (stdout/stderr)
        """
        # calendar_creator.py 경로
        calendar_script = Path(__file__).parent.parent / "actions" / "calendar_creator.py"
        if not calendar_script.exists():
            return f"calendar_creator.py not found: {calendar_script}"

        # 타이틀 생성
        channel = message.channel.value if hasattr(message.channel, 'value') else str(message.channel)
        sender = message.sender_name or "Unknown"
        title = f"[{channel}] {sender} - {deadline_text}"

        # subprocess 실행 (--confirm 없음 = dry-run)
        cmd = [
            sys.executable,
            str(calendar_script),
            "--title", title,
            "--start", deadline_text,
            # --confirm 없음 → dry-run
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += f"\n[stderr]: {stderr.decode('utf-8', errors='replace')}"

            return output.strip()

        except asyncio.TimeoutError:
            return "Calendar dry-run timeout (10s)"
        except Exception as e:
            return f"Calendar dry-run error: {e}"
