"""TCP control socket for injecting messages into a running goal loop."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable

CONTROL_INFO_FILE = ".stagewarden/goal_loop_control.txt"


def _read_lines(sock: socket.socket) -> list[bytes]:
    """Read all available lines from a socket with a short timeout."""
    lines: list[bytes] = []
    sock.settimeout(0.1)
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            lines.extend(data.split(b"\n"))
    except (socket.timeout, OSError):
        pass
    return lines


class GoalLoopControlServer:
    """TCP server that accepts external messages for a running goal loop.

    Protocol:
    - Connect to 127.0.0.1:<port>
    - Send one JSON object per line matching node-communication.md format
    - Server responds with "OK\\n" or "ERROR: <msg>\\n"

    Port is written to .stagewarden/goal_loop_control.txt so external tools
    can discover it.
    """

    def __init__(self, workspace_root: Path,
                 on_message: Callable[[dict[str, Any]], None] | None = None,
                 host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self._port = port
        self.workspace_root = workspace_root
        self.on_message = on_message
        self.server: socket.socket | None = None
        self.running = False
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        """Start TCP server on background thread."""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self._port))
        self.server.listen(5)
        self.server.settimeout(1.0)  # allow periodic check of running flag
        self._port = self.server.getsockname()[1]
        self.running = True
        self._write_info()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the TCP server."""
        self.running = False
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=2)
        self._remove_info()

    def _write_info(self) -> None:
        """Write port info to file for external tools."""
        info_file = self.workspace_root / CONTROL_INFO_FILE
        try:
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text(
                json.dumps({
                    "host": self.host,
                    "port": self._port,
                    "pid": os.getpid(),
                    "protocol": "json-line",
                    "description": "Goal loop control socket. "
                                   "Send one JSON message per line matching node-communication format.",
                }, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _remove_info(self) -> None:
        info_file = self.workspace_root / CONTROL_INFO_FILE
        try:
            if info_file.exists():
                info_file.unlink()
        except OSError:
            pass

    def _accept_loop(self) -> None:
        while self.running:
            try:
                client, addr = self.server.accept()  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                break
            # Handle client in a short-lived thread
            t = threading.Thread(target=self._handle_client,
                                 args=(client,), daemon=True)
            t.start()

    def _handle_client(self, client: socket.socket) -> None:
        try:
            lines = _read_lines(client)
            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                    if not isinstance(msg, dict):
                        client.sendall(b"ERROR: message must be a JSON object\n")
                        continue
                    # Validate required fields
                    if "FROM" not in msg or "TO" not in msg:
                        client.sendall(
                            b"ERROR: message must have FROM and TO fields\n"
                        )
                        continue
                    msg.setdefault("TYPE", "status")
                    msg.setdefault("PRIORITY", "low")
                    msg.setdefault("TOLERANCE IMPACT", "none")
                    if self.on_message:
                        self.on_message(msg)
                    client.sendall(b"OK\n")
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    client.sendall(f"ERROR: {exc}\n".encode("utf-8"))
        finally:
            try:
                client.close()
            except OSError:
                pass

    def __enter__(self) -> GoalLoopControlServer:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


def send_control_message(port: int, message: dict[str, Any],
                         host: str = "127.0.0.1") -> str:
    """Send a message to a running goal loop control socket.

    Returns the server response string.
    """
    with socket.create_connection((host, port), timeout=5) as sock:
        payload = (json.dumps(message) + "\n").encode("utf-8")
        sock.sendall(payload)
        response = sock.recv(4096)
        return response.decode("utf-8").strip()


def discover_control_port(workspace_root: Path) -> int | None:
    """Read the control port from .stagewarden/goal_loop_control.txt.

    Returns None if no running goal loop is found.
    """
    info_file = workspace_root / CONTROL_INFO_FILE
    try:
        data = json.loads(info_file.read_text(encoding="utf-8"))
        return int(data["port"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
