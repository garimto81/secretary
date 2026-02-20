#!/usr/bin/env python3
"""
SecretaryGateway - Central Gateway Server

통합 메시징 게이트웨이 서버.

Usage:
    python server.py start [--port 8800]
    python server.py stop
    python server.py status
    python server.py channels

Examples:
    python server.py start
    python server.py status
    python server.py channels
"""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent  # C:\claude\secretary
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
    # lib.slack, lib.gmail 등 공유 라이브러리 경로
    _claude_root = _project_root.parent  # C:\claude
    if str(_claude_root) not in sys.path:
        sys.path.insert(0, str(_claude_root))

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.adapters.base import ChannelAdapter
    from scripts.gateway.channel_registry import ChannelRegistry
    from scripts.gateway.pipeline import MessagePipeline
    from scripts.gateway.storage import UnifiedStorage
except ImportError:
    try:
        from gateway.adapters.base import ChannelAdapter
        from gateway.channel_registry import ChannelRegistry
        from gateway.pipeline import MessagePipeline
        from gateway.storage import UnifiedStorage
    except ImportError:
        from .adapters.base import ChannelAdapter
        from .channel_registry import ChannelRegistry
        from .pipeline import MessagePipeline
        from .storage import UnifiedStorage


# 기본 경로
DEFAULT_CONFIG_PATH = Path(r"C:\claude\secretary\config\gateway.json")
DEFAULT_CHANNELS_PATH = Path(r"C:\claude\secretary\config\channels.json")
DEFAULT_DATA_DIR = Path(r"C:\claude\secretary\data")
PID_FILE = DEFAULT_DATA_DIR / "gateway.pid"


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    설정 파일 로드

    Args:
        config_path: 설정 파일 경로

    Returns:
        설정 딕셔너리
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # 기본 설정 반환
    return {
        "enabled": True,
        "port": 8800,
        "data_dir": str(DEFAULT_DATA_DIR),
        "channels": {
            "slack": {"enabled": False},
            "gmail": {"enabled": False},
        },
        "pipeline": {
            "urgent_keywords": ["긴급", "urgent", "ASAP", "지금", "바로", "즉시"],
            "action_keywords": ["해주세요", "부탁", "요청", "확인", "검토"],
        },
        "safety": {
            "auto_send_disabled": True,
            "require_confirmation": True,
            "rate_limit_per_minute": 10,
        },
    }


class SecretaryGateway:
    """
    Central Gateway Server

    Features:
    - 여러 채널 어댑터 관리
    - 통합 메시지 파이프라인
    - CLI 인터페이스

    Example:
        gateway = SecretaryGateway()
        await gateway.start()
    """

    def __init__(self, config_path: Path | None = None):
        """
        Gateway 초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = load_config(config_path)
        self.adapters: dict[str, ChannelAdapter] = {}
        self.pipeline: MessagePipeline | None = None
        self.storage: UnifiedStorage | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._start_time: datetime | None = None
        self._reporter = None
        self._intel_storage = None
        self._intel_handler = None
        self._channel_registry: ChannelRegistry | None = None
        self._channel_watcher = None

    async def start(self) -> None:
        """Gateway 시작"""
        if self._running:
            print("Gateway가 이미 실행 중입니다.")
            return

        print("Secretary Gateway 시작 중...")

        # PID 파일 생성
        self._write_pid()

        # 스토리지 초기화
        data_dir = Path(self.config.get("data_dir", str(DEFAULT_DATA_DIR)))
        data_dir.mkdir(parents=True, exist_ok=True)

        self.storage = UnifiedStorage(data_dir / "gateway.db")
        await self.storage.connect()

        # 파이프라인 초기화
        pipeline_config = self.config.get("pipeline", {})
        safety_cfg = self.config.get("safety", {})
        pipeline_config["rate_limit_per_minute"] = safety_cfg.get("rate_limit_per_minute", 10)

        self.pipeline = MessagePipeline(self.storage, pipeline_config)

        # 어댑터 연결
        await self._connect_adapters()

        self._running = True
        self._start_time = datetime.now()

        print(f"Gateway 시작 완료 (포트: {self.config.get('port', 8800)})")
        print(f"활성화된 채널: {list(self.adapters.keys())}")
        print("종료: Ctrl+C")

        # ChannelWatcher 시작 (channels.json 감시)
        await self._start_channel_watcher()

        # FR-04: 초기 채널 덤프 (덤프 없는 채널만, 백그라운드)
        asyncio.create_task(self._run_initial_channel_dumps())

        # 메시지 수신 루프 시작
        await self._message_loop()

    async def stop(self) -> None:
        """Gateway 중지"""
        if not self._running:
            print("Gateway가 실행 중이 아닙니다.")
            return

        print("Gateway 중지 중...")

        self._running = False

        # 진행 중인 태스크 취소
        for task in self._tasks:
            task.cancel()

        # 어댑터 연결 해제
        for name, adapter in self.adapters.items():
            try:
                await adapter.disconnect()
                print(f"  - {name} 어댑터 연결 해제")
            except Exception as e:
                print(f"  - {name} 어댑터 연결 해제 실패: {e}")

        # Reporter 중지
        if self._reporter:
            try:
                await self._reporter.stop()
                print("  - Reporter 중지")
            except Exception as e:
                print(f"  - Reporter 중지 실패: {e}")

        # ChannelWatcher 중지
        if self._channel_watcher:
            try:
                await self._channel_watcher.stop()
                print("  - ChannelWatcher 중지")
            except Exception as e:
                print(f"  - ChannelWatcher 중지 실패: {e}")

        # Intelligence 워커 중지
        if self._intel_handler:
            try:
                await self._intel_handler.stop_worker()
                print("  - Intelligence 워커 중지")
            except Exception as e:
                print(f"  - Intelligence 워커 중지 실패: {e}")

        # Intelligence 스토리지 종료
        if self._intel_storage:
            try:
                await self._intel_storage.close()
                print("  - Intelligence 스토리지 종료")
            except Exception as e:
                print(f"  - Intelligence 스토리지 종료 실패: {e}")

        # 스토리지 종료
        if self.storage:
            await self.storage.close()

        # PID 파일 삭제
        self._remove_pid()

        print("Gateway 중지 완료")

    async def add_adapter(self, adapter: ChannelAdapter) -> None:
        """
        어댑터 추가

        Args:
            adapter: 채널 어댑터 인스턴스
        """
        if adapter.channel_type is None:
            raise ValueError("어댑터의 channel_type이 설정되지 않았습니다.")

        name = adapter.channel_type.value
        self.adapters[name] = adapter

        if self._running:
            success = await adapter.connect()
            if success:
                # 메시지 수신 태스크 시작
                task = asyncio.create_task(self._adapter_listen_loop(adapter))
                self._tasks.append(task)

    async def _connect_adapters(self) -> None:
        """설정된 어댑터 연결"""
        channels_config = self.config.get("channels", {})

        # ChannelRegistry 로드 시도 (channels.json 존재 시)
        if DEFAULT_CHANNELS_PATH.exists():
            try:
                registry = ChannelRegistry()
                registry.load(DEFAULT_CHANNELS_PATH)
                self._channel_registry = registry

                # monitor 역할 채널로 Slack 채널 목록 override
                monitor_channels = registry.get_by_role("monitor", "slack")
                if monitor_channels and "slack" in channels_config:
                    channels_config["slack"]["channels"] = monitor_channels
                    print(f"  - ChannelRegistry: {len(monitor_channels)}개 채널 로드됨")
            except Exception as e:
                print(f"  - ChannelRegistry 로드 실패, gateway.json 폴백: {e}")

        # 자동 어댑터 생성 (Slack, Gmail)
        for channel_name, channel_config in channels_config.items():
            if not channel_config.get("enabled", False):
                continue

            if channel_name not in self.adapters:
                adapter = self._create_adapter(channel_name, channel_config)
                if adapter:
                    self.adapters[channel_name] = adapter

        # 어댑터 연결
        for channel_name in list(self.adapters.keys()):
            channel_config = channels_config.get(channel_name, {})
            if not channel_config.get("enabled", False):
                continue

            adapter = self.adapters[channel_name]
            success = await adapter.connect()
            if success:
                print(f"  - {channel_name} 어댑터 연결 성공")
            else:
                print(f"  - {channel_name} 어댑터 연결 실패")

        # Intelligence 핸들러 등록
        await self._register_intelligence_handler()

    def _create_adapter(self, channel_name: str, config: dict):
        """채널 이름으로 어댑터 자동 생성"""
        try:
            if channel_name == "slack":
                from scripts.gateway.adapters.slack import SlackAdapter
                return SlackAdapter(config)
            elif channel_name in ("gmail", "email"):
                from scripts.gateway.adapters.gmail import GmailAdapter
                return GmailAdapter(config)
        except ImportError:
            try:
                if channel_name == "slack":
                    from gateway.adapters.slack import SlackAdapter
                    return SlackAdapter(config)
                elif channel_name in ("gmail", "email"):
                    from gateway.adapters.gmail import GmailAdapter
                    return GmailAdapter(config)
            except ImportError:
                pass
        except Exception as e:
            print(f"  - {channel_name} 어댑터 생성 실패: {e}")
        return None

    async def _register_intelligence_handler(self) -> None:
        """Project Intelligence 핸들러를 파이프라인에 등록"""
        if not self.pipeline:
            return

        intel_config = self.config.get("intelligence", {})
        if not intel_config.get("enabled", True):
            return

        try:
            from scripts.intelligence.context_store import IntelligenceStorage
            from scripts.intelligence.project_registry import ProjectRegistry
            from scripts.intelligence.response.handler import ProjectIntelligenceHandler

            intel_storage = IntelligenceStorage()
            await intel_storage.connect()

            registry = ProjectRegistry(intel_storage)
            await registry.load_from_config()

            ollama_config = intel_config.get("ollama")
            claude_config = intel_config.get("claude_draft")

            # 레지스트리 우선, 없으면 gateway.json 폴백
            if self._channel_registry is not None:
                chatbot_channels = self._channel_registry.get_by_role("chatbot", "slack")
            else:
                chatbot_channels = intel_config.get("chatbot_channels", [])

            handler = ProjectIntelligenceHandler(
                storage=intel_storage,
                registry=registry,
                ollama_config=ollama_config,
                claude_config=claude_config,
                chatbot_channels=chatbot_channels,
            )

            # handler 참조 보관 (종료 시 worker 정리용)
            self._intel_handler = handler

            # IntelligenceStorage 참조 보관 (종료 시 close용)
            self._intel_storage = intel_storage

            # PriorityQueue 워커 시작
            await handler.start_worker()
            print("  - Intelligence PriorityQueue 워커 시작")

            # Reporter 초기화 (gateway.json의 reporter 섹션)
            reporter_config = self.config.get("reporter", {})
            if reporter_config.get("enabled", False):
                try:
                    from scripts.reporter.reporter import SecretaryReporter
                except ImportError:
                    try:
                        from reporter.reporter import SecretaryReporter
                    except ImportError:
                        SecretaryReporter = None

                if SecretaryReporter is not None:
                    try:
                        reporter = SecretaryReporter(
                            gateway_storage=self.storage,
                            intel_storage=intel_storage,
                            config=reporter_config,
                        )
                        await reporter.start()
                        handler.set_reporter(reporter)
                        self._reporter = reporter
                        print("  - Reporter 시작 (Slack DM)")
                    except Exception as e:
                        print(f"  - Reporter 시작 실패: {e}")

            self.pipeline.add_handler(handler.handle)
            tier1 = "ollama" if ollama_config and ollama_config.get("enabled") else "규칙만"
            tier2 = "claude-opus" if claude_config and claude_config.get("enabled") else "수동"
            print(f"  - Intelligence 핸들러 등록 완료 (분석: {tier1}, 작성: {tier2})")
        except ImportError:
            pass
        except Exception as e:
            print(f"  - Intelligence 핸들러 등록 실패: {e}")

    async def _run_initial_channel_dumps(self) -> None:
        """FR-04: 등록된 채널 중 덤프 파일 없는 채널을 백그라운드로 덤프."""
        try:
            try:
                from scripts.knowledge.channel_message_dumper import ChannelMessageDumper
            except ImportError:
                try:
                    from knowledge.channel_message_dumper import ChannelMessageDumper
                except ImportError:
                    return

            dumper = ChannelMessageDumper()

            # channels.json enabled Slack 채널 수집
            channels: list[str] = []
            if self._channel_registry is not None:
                for role in ("monitor", "chatbot", "intelligence"):
                    for ch_id in self._channel_registry.get_by_role(role, "slack"):
                        if ch_id not in channels:
                            channels.append(ch_id)
            elif DEFAULT_CHANNELS_PATH.exists():
                try:
                    data = json.loads(DEFAULT_CHANNELS_PATH.read_text(encoding="utf-8"))
                    for ch in data.get("channels", []):
                        if ch.get("enabled") and ch.get("channel_type") == "slack":
                            ch_id = ch.get("channel_id")
                            if ch_id and ch_id not in channels:
                                channels.append(ch_id)
                except Exception:
                    pass

            if not channels:
                return

            print(f"  - FR-04: {len(channels)}개 채널 초기 덤프 체크")
            for channel_id in channels:
                if not self._running:
                    break
                try:
                    await dumper.dump(channel_id, force=False)
                except Exception as e:
                    print(f"  - FR-04: {channel_id} 덤프 실패 (무시): {e}")
        except Exception as e:
            print(f"  - FR-04: 초기 덤프 훅 오류 (무시): {e}")

    async def _start_channel_watcher(self) -> None:
        """ChannelWatcher 시작 (channels.json 감시)"""
        try:
            try:
                from scripts.gateway.channel_watcher import ChannelWatcher
            except ImportError:
                try:
                    from gateway.channel_watcher import ChannelWatcher
                except ImportError:
                    from .channel_watcher import ChannelWatcher

            watcher = ChannelWatcher()
            await watcher.start()
            self._channel_watcher = watcher
            print("  - ChannelWatcher 시작 (channels.json 감시)")
        except Exception as e:
            print(f"  - ChannelWatcher 시작 실패 (무시): {e}")

    async def _message_loop(self) -> None:
        """메시지 수신 루프"""
        # 각 어댑터에 대해 수신 태스크 생성
        for _name, adapter in self.adapters.items():
            if adapter.is_connected:
                task = asyncio.create_task(self._adapter_listen_loop(adapter))
                self._tasks.append(task)

        # 모든 태스크가 종료될 때까지 대기
        if self._tasks:
            try:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

    async def _adapter_listen_loop(self, adapter: ChannelAdapter) -> None:
        """
        단일 어댑터의 메시지 수신 루프

        Args:
            adapter: 채널 어댑터
        """
        channel_name = adapter.channel_type.value if adapter.channel_type else "unknown"

        try:
            async for message in adapter.listen():
                if not self._running:
                    break

                # 파이프라인 처리
                if self.pipeline:
                    result = await self.pipeline.process(message)

                    if result.error:
                        print(f"[{channel_name}] 처리 오류: {result.error}")
                    elif result.priority == "urgent":
                        print(f"[{channel_name}] 긴급 메시지: {message.sender_name}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[{channel_name}] 수신 오류: {e}")

    def get_status(self) -> dict[str, Any]:
        """
        상태 조회

        Returns:
            상태 딕셔너리
        """
        uptime = None
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        adapters_status = {}
        for name, adapter in self.adapters.items():
            adapters_status[name] = {
                "connected": adapter.is_connected,
            }

        return {
            "running": self._running,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "uptime_seconds": uptime,
            "port": self.config.get("port", 8800),
            "adapters": adapters_status,
            "adapters_count": len(self.adapters),
            "tasks_count": len(self._tasks),
        }

    def _write_pid(self) -> None:
        """PID 파일 생성"""
        import os

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        """PID 파일 삭제"""
        if PID_FILE.exists():
            PID_FILE.unlink()

    @staticmethod
    def get_running_pid() -> int | None:
        """
        실행 중인 Gateway PID 조회

        Returns:
            PID 또는 None
        """
        if PID_FILE.exists():
            with open(PID_FILE) as f:
                try:
                    return int(f.read().strip())
                except ValueError:
                    return None
        return None


def interactive_slack_channel_select(config_path: Path) -> list:
    """Slack 채널을 대화형으로 선택하고 gateway.json에 저장"""
    try:
        from lib.slack import SlackClient
        client = SlackClient()
        if not client.validate_token():
            print("[Slack] 토큰 검증 실패. 'python -m lib.slack login'을 실행하세요.")
            return []

        channels = client.list_channels(include_private=True)
        member_channels = [ch for ch in channels if ch.is_member]
        if not member_channels:
            print("[Slack] bot이 참여한 채널이 없습니다.")
            return []

        print("\n=== Slack 채널 선택 ===")
        print("bot이 참여한 채널 목록:\n")
        for i, ch in enumerate(member_channels, 1):
            private_tag = " [비공개]" if ch.is_private else ""
            topic_tag = f" - {ch.topic}" if ch.topic else ""
            print(f"  {i:3d}. #{ch.name}{private_tag}{topic_tag}")
        print(f"\n  0. 전체 선택 ({len(member_channels)}개)\n")

        while True:
            try:
                raw = input("감시할 채널 번호를 입력하세요 (쉼표 구분, 0=전체): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Slack] 채널 선택이 취소되었습니다.")
                return []
            if not raw:
                continue
            if raw == "0":
                selected = member_channels
                break
            try:
                indices = [int(x.strip()) for x in raw.split(",")]
                selected = []
                invalid = False
                for idx in indices:
                    if 1 <= idx <= len(member_channels):
                        selected.append(member_channels[idx - 1])
                    else:
                        print(f"  잘못된 번호: {idx} (1-{len(member_channels)} 범위)")
                        invalid = True
                if invalid:
                    continue
                if selected:
                    break
                print("  최소 1개 채널을 선택하세요.")
            except ValueError:
                print("  숫자만 입력하세요. (예: 1,3,5)")

        selected_ids = [ch.id for ch in selected]
        selected_names = [f"#{ch.name}" for ch in selected]
        print(f"\n선택됨: {', '.join(selected_names)}")
        _save_slack_channels(config_path, selected_ids)
        return selected_ids
    except Exception as e:
        print(f"[Slack] 채널 선택 중 오류 발생: {e}")
        print("[Slack] gateway.json에 channels를 직접 설정하세요.")
        return []


def _save_slack_channels(config_path: Path, channel_ids: list) -> None:
    """선택된 Slack 채널을 gateway.json에 저장"""
    config = load_config(config_path)
    config.setdefault("channels", {}).setdefault("slack", {})["channels"] = channel_ids
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[Slack] {len(channel_ids)}개 채널이 {config_path}에 저장됨")


# CLI 명령 핸들러
async def cmd_start(args: argparse.Namespace) -> None:
    """start 명령 처리"""
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    # Slack 대화형 채널 선택 (서버 시작 전, 동기 처리)
    slack_config = config.get("channels", {}).get("slack", {})
    if slack_config.get("enabled", False) and not slack_config.get("channels"):
        if sys.stdin.isatty():
            selected = interactive_slack_channel_select(config_path)
            if selected:
                config["channels"]["slack"]["channels"] = selected
        else:
            print("[Slack] 비대화형 환경입니다. gateway.json에 channels를 직접 설정하세요.")

    gateway = SecretaryGateway(config_path)

    # 대화형 선택으로 변경된 config 반영
    if config.get("channels", {}).get("slack", {}).get("channels"):
        gateway.config = config

    # 포트 오버라이드
    if args.port:
        gateway.config["port"] = args.port

    # 시그널 핸들러 설정
    loop = asyncio.get_event_loop()

    def signal_handler():
        print("\n중지 신호 수신...")
        asyncio.create_task(gateway.stop())

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        await gateway.start()
    except KeyboardInterrupt:
        print("\nCtrl+C 감지, 종료 중...")
    finally:
        if gateway._running:
            await gateway.stop()


def cmd_stop(args: argparse.Namespace) -> None:
    """stop 명령 처리"""
    pid = SecretaryGateway.get_running_pid()

    if pid is None:
        print("실행 중인 Gateway가 없습니다.")
        return

    import os

    try:
        if sys.platform == "win32":
            # Windows에서 프로세스 종료
            os.system(f"taskkill /PID {pid} /F >nul 2>&1")
        else:
            os.kill(pid, signal.SIGTERM)

        print(f"Gateway 종료 신호 전송 (PID: {pid})")

        # PID 파일 삭제
        if PID_FILE.exists():
            PID_FILE.unlink()

    except OSError as e:
        print(f"종료 실패: {e}")


def cmd_status(args: argparse.Namespace) -> None:
    """status 명령 처리"""
    pid = SecretaryGateway.get_running_pid()

    if pid is None:
        print("Gateway 상태: 중지됨")
        return

    # 프로세스 존재 여부 확인
    import os

    try:
        if sys.platform == "win32":
            # Windows에서 프로세스 확인
            result = os.system(f"tasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul")
            running = result == 0
        else:
            os.kill(pid, 0)
            running = True
    except OSError:
        running = False

    if running:
        print(f"Gateway 상태: 실행 중 (PID: {pid})")
    else:
        print("Gateway 상태: 중지됨 (PID 파일 잔존)")
        # PID 파일 정리
        if PID_FILE.exists():
            PID_FILE.unlink()


def cmd_channels(args: argparse.Namespace) -> None:
    """channels 명령 처리"""
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    channels = config.get("channels", {})

    print("설정된 채널:")
    print("-" * 40)

    for name, channel_config in channels.items():
        enabled = channel_config.get("enabled", False)
        status = "활성화" if enabled else "비활성화"
        print(f"  {name}: {status}")

    print("-" * 40)


def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        description="Secretary Gateway - 통합 메시징 게이트웨이",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python server.py start              # Gateway 시작
  python server.py start --port 9000  # 포트 지정하여 시작
  python server.py stop               # Gateway 중지
  python server.py status             # 상태 확인
  python server.py channels           # 채널 목록
        """,
    )

    parser.add_argument(
        "--config",
        help="설정 파일 경로 (기본: config/gateway.json)",
    )

    subparsers = parser.add_subparsers(dest="command", help="명령")

    # start 명령
    start_parser = subparsers.add_parser("start", help="Gateway 시작")
    start_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="포트 번호 (기본: 8800)",
    )
    start_parser.add_argument(
        "--daemon",
        action="store_true",
        help="백그라운드 실행 (미구현)",
    )

    # stop 명령
    subparsers.add_parser("stop", help="Gateway 중지")

    # status 명령
    subparsers.add_parser("status", help="상태 확인")

    # channels 명령
    subparsers.add_parser("channels", help="채널 목록")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "start":
        asyncio.run(cmd_start(args))
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "channels":
        cmd_channels(args)


if __name__ == "__main__":
    main()
