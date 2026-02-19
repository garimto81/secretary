"""Knowledge Bootstrap - Gmail/Slack 히스토리 일괄 학습"""

import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# 3중 import fallback
try:
    from scripts.knowledge.models import KnowledgeDocument
    from scripts.knowledge.store import KnowledgeStore
except ImportError:
    try:
        from knowledge.models import KnowledgeDocument
        from knowledge.store import KnowledgeStore
    except ImportError:
        from .models import KnowledgeDocument
        from .store import KnowledgeStore


@dataclass
class BootstrapResult:
    """Bootstrap 실행 결과"""
    project_id: str
    source: str
    total_fetched: int = 0
    total_ingested: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
    error_messages: list = field(default_factory=list)


class KnowledgeBootstrap:
    """초기 학습 실행기 - Gmail/Slack 히스토리 일괄 수집"""

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._python = sys.executable

    async def learn_gmail(
        self,
        project_id: str,
        label: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> BootstrapResult:
        """Gmail 이메일 일괄 학습

        Args:
            project_id: 프로젝트 ID
            label: Gmail 라벨 (예: "INBOX", "project-x")
            query: Gmail 검색 쿼리 (label과 동시 사용 가능)
            limit: 최대 수집 건수

        Returns:
            BootstrapResult
        """
        result = BootstrapResult(project_id=project_id, source="gmail")
        start = time.monotonic()

        # 검색 쿼리 구성
        search_query = query or ""
        if label:
            label_query = f"label:{label}"
            search_query = f"{label_query} {search_query}".strip()

        if not search_query:
            search_query = "in:inbox"

        # Step 1: 메시지 목록 검색
        search_args = ["lib.gmail", "search", search_query, "--limit", str(limit), "--json"]
        search_data = await asyncio.to_thread(self._run_subprocess, search_args)

        if search_data is None:
            result.error_messages.append("Gmail search subprocess 실패")
            result.errors += 1
            result.elapsed_seconds = time.monotonic() - start
            return result

        emails = search_data.get("emails", [])
        result.total_fetched = len(emails)

        if not emails:
            logger.info(f"Gmail 검색 결과 없음: query='{search_query}'")
            result.elapsed_seconds = time.monotonic() - start
            return result

        # Step 2: 각 메시지 본문 읽기 + ingestion
        for email_summary in emails:
            msg_id = email_summary.get("id")
            if not msg_id:
                result.errors += 1
                continue

            try:
                # 본문 읽기
                read_args = ["lib.gmail", "read", msg_id, "--json"]
                email_data = await asyncio.to_thread(self._run_subprocess, read_args)

                if email_data is None:
                    result.errors += 1
                    result.error_messages.append(f"Gmail read 실패: {msg_id}")
                    continue

                # 본문 추출 (body_text 우선, body_html fallback)
                body = email_data.get("body_text") or ""
                if not body.strip():
                    html_body = email_data.get("body_html") or ""
                    if html_body:
                        body = self._strip_html(html_body)

                if not body.strip():
                    body = email_summary.get("snippet") or ""

                if not body.strip():
                    result.duplicates_skipped += 1
                    continue

                # 본문 길이 제한
                if len(body) > 8000:
                    body = body[:8000] + "\n\n[... 생략 ...]"

                # 날짜 파싱
                created_at = None
                date_str = email_data.get("date") or email_summary.get("date")
                if date_str:
                    try:
                        created_at = datetime.fromisoformat(date_str)
                    except (ValueError, TypeError):
                        pass

                # KnowledgeDocument 생성
                doc = KnowledgeDocument(
                    id=f"gmail:{msg_id}",
                    project_id=project_id,
                    source="gmail",
                    source_id=msg_id,
                    content=body,
                    sender_name=email_data.get("from") or email_summary.get("from", ""),
                    sender_id=email_data.get("from") or "",
                    subject=email_data.get("subject") or email_summary.get("subject", ""),
                    thread_id=email_data.get("thread_id") or "",
                    content_type="email",
                    metadata={
                        "to": email_data.get("to"),
                        "cc": email_data.get("cc"),
                        "labels": email_data.get("labels", []),
                        "is_unread": email_data.get("is_unread", False),
                        "permalink": email_data.get("permalink", ""),
                    },
                    created_at=created_at,
                )

                await self.store.ingest(doc)
                result.total_ingested += 1

            except Exception as e:
                result.errors += 1
                result.error_messages.append(f"Gmail 처리 오류 ({msg_id}): {str(e)[:100]}")
                logger.error(f"Gmail ingest 오류: {msg_id}: {e}")
                continue

        # Step 3: ingestion_state 업데이트
        await self._save_checkpoint(
            project_id=project_id,
            source="gmail",
            checkpoint_key=f"label:{label}" if label else f"query:{search_query[:50]}",
            documents_ingested=result.total_ingested,
        )

        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            f"Gmail bootstrap 완료: project={project_id}, "
            f"fetched={result.total_fetched}, ingested={result.total_ingested}, "
            f"errors={result.errors}"
        )
        return result

    async def learn_slack(
        self,
        project_id: str,
        channel_id: str,
        limit: int = 500,
    ) -> BootstrapResult:
        """Slack 채널 히스토리 일괄 학습

        Args:
            project_id: 프로젝트 ID
            channel_id: Slack 채널 ID (예: "C0123456789")
            limit: 최대 수집 건수

        Returns:
            BootstrapResult
        """
        result = BootstrapResult(project_id=project_id, source="slack")
        start = time.monotonic()

        # Step 1: 채널 히스토리 수집
        history_args = ["lib.slack", "history", channel_id, "--limit", str(limit), "--json"]
        history_data = await asyncio.to_thread(self._run_subprocess, history_args)

        if history_data is None:
            result.error_messages.append(f"Slack history subprocess 실패: {channel_id}")
            result.errors += 1
            result.elapsed_seconds = time.monotonic() - start
            return result

        messages = history_data.get("messages", [])
        result.total_fetched = len(messages)

        if not messages:
            logger.info(f"Slack 히스토리 없음: channel={channel_id}")
            result.elapsed_seconds = time.monotonic() - start
            return result

        # Step 2: 각 메시지를 KnowledgeDocument로 변환 + ingestion
        for msg in messages:
            ts = msg.get("ts")
            if not ts:
                result.errors += 1
                continue

            try:
                text = msg.get("text") or ""
                if not text.strip():
                    result.duplicates_skipped += 1
                    continue

                # 본문 길이 제한
                if len(text) > 8000:
                    text = text[:8000] + "\n\n[... 생략 ...]"

                # 날짜 파싱 (Slack ts는 Unix epoch.microsecond 형식)
                created_at = None
                timestamp_str = msg.get("timestamp")
                if timestamp_str:
                    try:
                        created_at = datetime.fromisoformat(timestamp_str)
                    except (ValueError, TypeError):
                        pass

                if not created_at:
                    try:
                        epoch = float(ts.split(".")[0])
                        created_at = datetime.fromtimestamp(epoch)
                    except (ValueError, TypeError, IndexError):
                        pass

                doc = KnowledgeDocument(
                    id=f"slack:{ts}",
                    project_id=project_id,
                    source="slack",
                    source_id=ts,
                    content=text,
                    sender_name=msg.get("user") or "",
                    sender_id=msg.get("user") or "",
                    subject="",
                    thread_id=msg.get("thread_ts") or "",
                    content_type="message",
                    metadata={
                        "channel_id": channel_id,
                        "thread_ts": msg.get("thread_ts"),
                    },
                    created_at=created_at,
                )

                await self.store.ingest(doc)
                result.total_ingested += 1

            except Exception as e:
                result.errors += 1
                result.error_messages.append(f"Slack 처리 오류 ({ts}): {str(e)[:100]}")
                logger.error(f"Slack ingest 오류: {ts}: {e}")
                continue

        # Step 3: ingestion_state 업데이트
        await self._save_checkpoint(
            project_id=project_id,
            source="slack",
            checkpoint_key=f"channel:{channel_id}",
            documents_ingested=result.total_ingested,
        )

        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            f"Slack bootstrap 완료: project={project_id}, channel={channel_id}, "
            f"fetched={result.total_fetched}, ingested={result.total_ingested}, "
            f"errors={result.errors}"
        )
        return result

    async def learn_slack_full(
        self,
        project_id: str,
        channel_id: str,
        page_size: int = 100,
        rate_limit_sleep: float = 1.2,
        resume_cursor: Optional[str] = None,
    ) -> BootstrapResult:
        """cursor-based pagination으로 채널 전체 히스토리 수집.

        checkpoint_key = f"full:{channel_id}"
        cursor 위치를 ingestion_state에 저장 → 재실행 시 이어받기.
        """
        result = BootstrapResult(project_id=project_id, source="slack")
        start = time.monotonic()

        checkpoint_key = f"full:{channel_id}"
        cursor = resume_cursor

        # checkpoint에서 cursor 복원
        if cursor is None:
            cursor = await self._load_cursor_checkpoint(project_id, checkpoint_key)

        parent_ts_list = []  # thread replies 수집용
        page_num = 0

        while True:
            page_num += 1

            # subprocess 호출: lib.slack history {channel_id} --limit {page_size} [--cursor {cursor}] --json
            args = ["lib.slack", "history", channel_id, "--limit", str(page_size), "--json"]
            if cursor:
                args.extend(["--cursor", cursor])

            history_data = await asyncio.to_thread(self._run_subprocess, args)

            if history_data is None:
                result.error_messages.append(f"Page {page_num}: subprocess 실패")
                result.errors += 1
                break

            messages = history_data.get("messages", [])
            if not messages:
                break

            # 메시지 처리
            for msg in messages:
                ts = msg.get("ts")
                if not ts:
                    result.errors += 1
                    continue

                try:
                    text = msg.get("text") or ""
                    if not text.strip():
                        result.duplicates_skipped += 1
                        continue

                    if len(text) > 8000:
                        text = text[:8000] + "\n\n[... 생략 ...]"

                    # 날짜 파싱
                    created_at = None
                    timestamp_str = msg.get("timestamp")
                    if timestamp_str:
                        try:
                            created_at = datetime.fromisoformat(timestamp_str)
                        except (ValueError, TypeError):
                            pass
                    if not created_at:
                        try:
                            epoch = float(ts.split(".")[0])
                            created_at = datetime.fromtimestamp(epoch)
                        except (ValueError, TypeError, IndexError):
                            pass

                    doc = KnowledgeDocument(
                        id=f"slack:{ts}",
                        project_id=project_id,
                        source="slack",
                        source_id=ts,
                        content=text,
                        sender_name=msg.get("user") or "",
                        sender_id=msg.get("user") or "",
                        subject="",
                        thread_id=msg.get("thread_ts") or "",
                        content_type="message",
                        metadata={
                            "channel_id": channel_id,
                            "thread_ts": msg.get("thread_ts"),
                            "reply_count": msg.get("reply_count", 0),
                        },
                        created_at=created_at,
                    )

                    await self.store.ingest(doc)
                    result.total_ingested += 1

                    # thread parent 수집 (reply_count > 0 또는 thread_ts == ts)
                    thread_ts = msg.get("thread_ts")
                    reply_count = msg.get("reply_count", 0)
                    if thread_ts and thread_ts == ts and reply_count > 0:
                        parent_ts_list.append(thread_ts)

                except Exception as e:
                    result.errors += 1
                    result.error_messages.append(f"Slack 처리 오류 ({ts}): {str(e)[:100]}")
                    continue

            result.total_fetched += len(messages)

            # 진행률 출력
            print(f"  Page {page_num}: +{len(messages)}건, total: {result.total_fetched}건")

            # next_cursor 확인
            next_cursor = history_data.get("response_metadata", {}).get("next_cursor", "")
            if not next_cursor:
                break

            cursor = next_cursor

            # cursor checkpoint 저장
            await self._save_cursor_checkpoint(project_id, checkpoint_key, cursor)

            # rate limiting
            await asyncio.sleep(rate_limit_sleep)

        # 전체 수집 완료 후 checkpoint 정리
        await self._save_checkpoint(
            project_id=project_id,
            source="slack",
            checkpoint_key=checkpoint_key,
            documents_ingested=result.total_ingested,
        )

        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            f"Slack full bootstrap 완료: project={project_id}, channel={channel_id}, "
            f"fetched={result.total_fetched}, ingested={result.total_ingested}, "
            f"threads={len(parent_ts_list)}, errors={result.errors}"
        )

        # thread parent ts 목록을 result에 저장 (나중에 thread replies 수집에 사용)
        result._parent_ts_list = parent_ts_list

        return result

    async def _fetch_thread_replies(
        self,
        project_id: str,
        channel_id: str,
        thread_ts: str,
        rate_limit_sleep: float = 1.2,
    ) -> int:
        """thread_ts의 replies를 수집하여 Knowledge에 저장.

        Returns:
            수집된 reply 건수
        """
        args = ["lib.slack", "replies", channel_id, thread_ts, "--json"]

        replies_data = await asyncio.to_thread(self._run_subprocess, args)
        if replies_data is None:
            return 0

        replies = replies_data.get("messages", [])
        count = 0

        for reply in replies:
            reply_ts = reply.get("ts")
            if not reply_ts or reply_ts == thread_ts:
                continue  # parent 자체는 건너뜀

            try:
                text = reply.get("text") or ""
                if not text.strip():
                    continue

                if len(text) > 8000:
                    text = text[:8000] + "\n\n[... 생략 ...]"

                created_at = None
                try:
                    epoch = float(reply_ts.split(".")[0])
                    created_at = datetime.fromtimestamp(epoch)
                except (ValueError, TypeError, IndexError):
                    pass

                doc = KnowledgeDocument(
                    id=f"slack:{reply_ts}",
                    project_id=project_id,
                    source="slack",
                    source_id=reply_ts,
                    content=text,
                    sender_name=reply.get("user") or "",
                    sender_id=reply.get("user") or "",
                    subject="",
                    thread_id=thread_ts,
                    content_type="thread_reply",
                    metadata={
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                        "parent_ts": thread_ts,
                    },
                    created_at=created_at,
                )

                await self.store.ingest(doc)
                count += 1

            except Exception as e:
                logger.error(f"Thread reply 처리 오류 ({reply_ts}): {e}")
                continue

        await asyncio.sleep(rate_limit_sleep)
        return count

    async def _collect_channel_metadata(
        self,
        channel_id: str,
    ) -> dict:
        """채널 메타데이터 수집 (info, members, pins)

        Returns:
            dict with keys: channel_name, topic, purpose, created, members, pinned_messages
        """
        metadata = {
            "channel_name": "",
            "topic": "",
            "purpose": "",
            "created": None,
            "members": [],
            "pinned_messages": [],
        }

        # 채널 정보
        info_data = await asyncio.to_thread(
            self._run_subprocess, ["lib.slack", "info", channel_id, "--json"]
        )
        if info_data:
            channel = info_data.get("channel", info_data)
            metadata["channel_name"] = channel.get("name") or channel.get("channel_name") or ""
            metadata["topic"] = channel.get("topic", {}).get("value", "") if isinstance(channel.get("topic"), dict) else str(channel.get("topic", ""))
            metadata["purpose"] = channel.get("purpose", {}).get("value", "") if isinstance(channel.get("purpose"), dict) else str(channel.get("purpose", ""))
            created_ts = channel.get("created")
            if created_ts:
                try:
                    metadata["created"] = datetime.fromtimestamp(int(created_ts))
                except (ValueError, TypeError):
                    pass

        # 멤버 목록
        members_data = await asyncio.to_thread(
            self._run_subprocess, ["lib.slack", "members", channel_id, "--json"]
        )
        if members_data:
            metadata["members"] = members_data.get("members", [])

        # 핀된 메시지
        pins_data = await asyncio.to_thread(
            self._run_subprocess, ["lib.slack", "pins", channel_id, "--json"]
        )
        if pins_data:
            items = pins_data.get("items", pins_data.get("pins", []))
            for item in items:
                msg = item.get("message", item)
                metadata["pinned_messages"].append({
                    "ts": msg.get("ts", ""),
                    "text": (msg.get("text") or "")[:500],
                })

        return metadata

    async def _load_cursor_checkpoint(self, project_id: str, checkpoint_key: str) -> Optional[str]:
        """ingestion_state에서 cursor checkpoint 로드"""
        try:
            self.store._ensure_connected()
            state_id = f"{project_id}:slack:{checkpoint_key}"
            async with self.store._connection.execute(
                "SELECT checkpoint_value FROM ingestion_state WHERE id = ?",
                (state_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["checkpoint_value"]:
                    value = row["checkpoint_value"]
                    # ISO 형식 날짜면 이전 완료 상태 → None 반환
                    if "T" in value and "-" in value:
                        return None
                    return value
                return None
        except Exception:
            return None

    async def _save_cursor_checkpoint(self, project_id: str, checkpoint_key: str, cursor_value: str) -> None:
        """ingestion_state에 cursor checkpoint 저장"""
        try:
            self.store._ensure_connected()
            state_id = f"{project_id}:slack:{checkpoint_key}"
            now = datetime.now().isoformat()
            await self.store._connection.execute(
                """INSERT OR REPLACE INTO ingestion_state
                (id, source, project_id, checkpoint_key, checkpoint_value,
                 last_run_at, documents_ingested, error_message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (state_id, "slack", project_id, checkpoint_key, cursor_value, now, 0, None, now),
            )
            await self.store._connection.commit()
        except Exception as e:
            logger.error(f"Cursor checkpoint 저장 실패: {e}")

    async def run_mastery(
        self,
        project_id: str,
        channel_id: str,
        page_size: int = 100,
    ) -> dict:
        """Channel Mastery 전체 실행 (CLI용)

        1. learn_slack_full() — 전체 히스토리 수집
        2. _fetch_thread_replies() — 모든 parent의 threads 수집
        3. _collect_channel_metadata() — 채널 메타데이터 수집

        Returns:
            실행 결과 요약 dict
        """
        import time as _time
        total_start = _time.monotonic()

        print(f"\n=== Channel Mastery 시작 ===")
        print(f"채널: {channel_id}, 프로젝트: {project_id}\n")

        # Step 1: 전체 히스토리 수집
        print("[1/3] 전체 히스토리 수집...")
        history_result = await self.learn_slack_full(
            project_id=project_id,
            channel_id=channel_id,
            page_size=page_size,
        )

        # Step 2: Thread replies 수집
        parent_ts_list = getattr(history_result, '_parent_ts_list', [])
        total_replies = 0
        print(f"\n[2/3] 스레드 replies 수집... ({len(parent_ts_list)}개 thread)")
        for i, thread_ts in enumerate(parent_ts_list, 1):
            try:
                count = await self._fetch_thread_replies(
                    project_id=project_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                )
                total_replies += count
                if i % 10 == 0 or i == len(parent_ts_list):
                    print(f"  Thread {i}/{len(parent_ts_list)}: +{count} replies, total: {total_replies}건")
            except Exception as e:
                logger.error(f"Thread {thread_ts} 수집 실패: {e}")
                continue

        # Step 3: 채널 메타데이터 수집
        print(f"\n[3/3] 채널 메타데이터 수집...")
        channel_meta = await self._collect_channel_metadata(channel_id)

        total_elapsed = _time.monotonic() - total_start
        minutes = int(total_elapsed // 60)
        seconds = int(total_elapsed % 60)

        summary = {
            "channel_id": channel_id,
            "channel_name": channel_meta.get("channel_name", ""),
            "project_id": project_id,
            "total_messages": history_result.total_fetched,
            "total_ingested": history_result.total_ingested,
            "total_threads": len(parent_ts_list),
            "total_replies": total_replies,
            "members_count": len(channel_meta.get("members", [])),
            "pinned_count": len(channel_meta.get("pinned_messages", [])),
            "errors": history_result.errors,
            "elapsed_seconds": total_elapsed,
        }

        channel_name = channel_meta.get("channel_name") or channel_id
        print(f"\n=== Channel Mastery 완료 ===")
        print(f"채널: #{channel_name} ({channel_id})")
        print(f"총 메시지: {history_result.total_fetched:,}건 (저장: {history_result.total_ingested:,}건)")
        print(f"스레드 replies: {total_replies:,}건 ({len(parent_ts_list):,}개 thread)")
        print(f"멤버: {len(channel_meta.get('members', []))}명")
        print(f"핀: {len(channel_meta.get('pinned_messages', []))}개")
        print(f"소요 시간: {minutes}분 {seconds}초")

        return summary

    def _run_subprocess(self, args: List[str]) -> Optional[dict]:
        """subprocess 실행 + JSON 파싱

        Args:
            args: python -m 뒤에 붙일 인자 목록

        Returns:
            파싱된 JSON dict 또는 None
        """
        try:
            proc = subprocess.run(
                [self._python, "-m"] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=str(Path(r"C:\claude")),
            )
            if proc.returncode != 0:
                logger.error(f"subprocess 실패: {' '.join(args)}: {proc.stderr[:200]}")
                return None
            if not proc.stdout.strip():
                return None
            return json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            logger.error(f"subprocess 타임아웃: {' '.join(args)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {' '.join(args)}: {e}")
            return None
        except Exception as e:
            logger.error(f"subprocess 오류: {' '.join(args)}: {e}")
            return None

    async def _save_checkpoint(
        self,
        project_id: str,
        source: str,
        checkpoint_key: str,
        documents_ingested: int,
        error_message: Optional[str] = None,
    ) -> None:
        """ingestion_state 테이블에 체크포인트 저장"""
        try:
            store = self.store
            store._ensure_connected()

            state_id = f"{project_id}:{source}:{checkpoint_key}"
            now = datetime.now().isoformat()

            await store._connection.execute(
                """INSERT OR REPLACE INTO ingestion_state
                (id, source, project_id, checkpoint_key, checkpoint_value,
                 last_run_at, documents_ingested, error_message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state_id,
                    source,
                    project_id,
                    checkpoint_key,
                    now,
                    now,
                    documents_ingested,
                    error_message,
                    now,
                ),
            )
            await store._connection.commit()
        except Exception as e:
            logger.error(f"체크포인트 저장 실패: {e}")

    @staticmethod
    def _strip_html(html: str) -> str:
        """HTML 태그 제거 -> 순수 텍스트"""
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# === CLI 진입점 ===
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge Bootstrap CLI")
    subparsers = parser.add_subparsers(dest="command", help="서브커맨드")

    # mastery 서브커맨드
    mastery_parser = subparsers.add_parser("mastery", help="Channel Mastery 전체 실행")
    mastery_parser.add_argument("channel_id", help="Slack 채널 ID")
    mastery_parser.add_argument("--project", default="secretary", help="프로젝트 ID (기본: secretary)")
    mastery_parser.add_argument("--page-size", type=int, default=100, help="페이지당 메시지 수 (기본: 100)")

    # learn_slack 서브커맨드 (기존 호환)
    slack_parser = subparsers.add_parser("slack", help="Slack 채널 히스토리 학습")
    slack_parser.add_argument("channel_id", help="Slack 채널 ID")
    slack_parser.add_argument("--project", default="secretary", help="프로젝트 ID")
    slack_parser.add_argument("--limit", type=int, default=500, help="최대 수집 건수")

    # learn_gmail 서브커맨드
    gmail_parser = subparsers.add_parser("gmail", help="Gmail 히스토리 학습")
    gmail_parser.add_argument("--project", default="secretary", help="프로젝트 ID")
    gmail_parser.add_argument("--label", help="Gmail 라벨")
    gmail_parser.add_argument("--query", help="Gmail 검색 쿼리")
    gmail_parser.add_argument("--limit", type=int, default=100, help="최대 수집 건수")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    async def _main():
        from scripts.knowledge.store import KnowledgeStore
        async with KnowledgeStore() as store:
            bootstrap = KnowledgeBootstrap(store)

            if args.command == "mastery":
                summary = await bootstrap.run_mastery(
                    project_id=args.project,
                    channel_id=args.channel_id,
                    page_size=args.page_size,
                )
                if summary.get("errors"):
                    print(f"\n경고: {summary['errors']}건의 오류 발생")

            elif args.command == "slack":
                result = await bootstrap.learn_slack(
                    project_id=args.project,
                    channel_id=args.channel_id,
                    limit=args.limit,
                )
                print(f"완료: fetched={result.total_fetched}, ingested={result.total_ingested}")

            elif args.command == "gmail":
                result = await bootstrap.learn_gmail(
                    project_id=args.project,
                    label=args.label,
                    query=args.query,
                    limit=args.limit,
                )
                print(f"완료: fetched={result.total_fetched}, ingested={result.total_ingested}")

    asyncio.run(_main())
