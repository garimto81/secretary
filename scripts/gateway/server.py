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
from typing import Dict, List, Optional, Any

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import NormalizedMessage, ChannelType
    from scripts.gateway.storage import UnifiedStorage
    from scripts.gateway.pipeline import MessagePipeline, PipelineResult
    from scripts.gateway.adapters.base import ChannelAdapter
except ImportError:
    try:
        from gateway.models import NormalizedMessage, ChannelType
        from gateway.storage import UnifiedStorage
        from gateway.pipeline import MessagePipeline, PipelineResult
        from gateway.adapters.base import ChannelAdapter
    except ImportError:
        from .models import NormalizedMessage, ChannelType
        from .storage import UnifiedStorage
        from .pipeline import MessagePipeline, PipelineResult
        from .adapters.base import ChannelAdapter


# 기본 경로
DEFAULT_CONFIG_PATH = Path(r"C:\claude\secretary\config\gateway.json")
DEFAULT_DATA_DIR = Path(r"C:\claude\secretary\data")
PID_FILE = DEFAULT_DATA_DIR / "gateway.pid"


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    설정 파일 로드

    Args:
        config_path: 설정 파일 경로

    Returns:
        설정 딕셔너리
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 기본 설정 반환
    return {
        "enabled": True,
        "port": 8800,
        "data_dir": str(DEFAULT_DATA_DIR),
        "channels": {
            "telegram": {"enabled": False},
            "whatsapp": {"enabled": False},
            "discord": {"enabled": False},
            "slack": {"enabled": False},
            "kakao": {"enabled": False},
        },
        "pipeline": {
            "urgent_keywords": ["긴급", "urgent", "ASAP", "지금", "바로", "즉시"],
            "action_keywords": ["해주세요", "부탁", "요청", "확인", "검토"],
        },
        "notifications": {
            "toast_enabled": True,
            "sound_enabled": False,
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

    def __init__(self, config_path: Optional[Path] = None):
        """
        Gateway 초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = load_config(config_path)
        self.adapters: Dict[str, ChannelAdapter] = {}
        self.pipeline: Optional[MessagePipeline] = None
        self.storage: Optional[UnifiedStorage] = None
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._start_time: Optional[datetime] = None

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
        pipeline_config["toast_enabled"] = self.config.get("notifications", {}).get("toast_enabled", True)
        pipeline_config["rate_limit_per_minute"] = self.config.get("safety", {}).get("rate_limit_per_minute", 10)

        self.pipeline = MessagePipeline(self.storage, pipeline_config)

        # 어댑터 연결
        await self._connect_adapters()

        self._running = True
        self._start_time = datetime.now()

        print(f"Gateway 시작 완료 (포트: {self.config.get('port', 8800)})")
        print(f"활성화된 채널: {list(self.adapters.keys())}")

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

        for channel_name, channel_config in channels_config.items():
            if not channel_config.get("enabled", False):
                continue

            # 어댑터가 이미 추가되어 있으면 연결
            if channel_name in self.adapters:
                adapter = self.adapters[channel_name]
                success = await adapter.connect()
                if success:
                    print(f"  - {channel_name} 어댑터 연결 성공")
                else:
                    print(f"  - {channel_name} 어댑터 연결 실패")

    async def _message_loop(self) -> None:
        """메시지 수신 루프"""
        # 각 어댑터에 대해 수신 태스크 생성
        for name, adapter in self.adapters.items():
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

    def get_status(self) -> Dict[str, Any]:
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
    def get_running_pid() -> Optional[int]:
        """
        실행 중인 Gateway PID 조회

        Returns:
            PID 또는 None
        """
        if PID_FILE.exists():
            with open(PID_FILE, "r") as f:
                try:
                    return int(f.read().strip())
                except ValueError:
                    return None
        return None


# CLI 명령 핸들러
async def cmd_start(args: argparse.Namespace) -> None:
    """start 명령 처리"""
    config_path = Path(args.config) if args.config else None
    gateway = SecretaryGateway(config_path)

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
