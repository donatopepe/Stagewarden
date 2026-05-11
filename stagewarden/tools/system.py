from __future__ import annotations

import os
import platform
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import shutil

try:  # Optional dependency.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None

try:  # Optional dependency.
    import pyperclip  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyperclip = None


@dataclass(slots=True)
class SystemResult:
    ok: bool
    command: str
    message: str
    info: dict[str, Any] | None = None
    items: list[dict[str, Any]] | None = None
    path: str | None = None
    pid: int | None = None
    port: int | None = None
    duration_ms: int = 0
    error_type: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "message": self.message,
            "info": dict(self.info or {}),
            "items": list(self.items or []),
            "path": self.path,
            "pid": self.pid,
            "port": self.port,
            "duration_ms": self.duration_ms,
            "error_type": self.error_type,
            "error": self.error,
        }


class SystemTool:
    def __init__(self, workspace_root: Path, *, timeout_seconds: int = 10, max_items: int = 200) -> None:
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items

    def info(self) -> SystemResult:
        started = time.monotonic()
        try:
            info = {
                "platform": platform.platform(),
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": sys.version.split()[0],
                "cwd": str(Path.cwd()),
                "hostname": platform.node(),
                "cpu_count": os.cpu_count(),
                "home": str(Path.home()),
            }
            if psutil is not None:
                try:
                    vm = psutil.virtual_memory()
                    info["memory_total"] = vm.total
                    info["memory_available"] = vm.available
                except Exception:
                    pass
            info["disk_usage"] = self._disk_usage_dict(self.workspace_root)
            return SystemResult(True, "system info", "System information collected.", info=info, duration_ms=self._elapsed_ms(started))
        except OSError as exc:
            return self._error("system info", str(exc), started)

    def disk_usage(self, path: str = ".") -> SystemResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            usage = self._disk_usage_dict(target)
            return SystemResult(True, "disk usage", f"Disk usage for {self._display_path(target)}.", info=usage, path=self._display_path(target), duration_ms=self._elapsed_ms(started))
        except OSError as exc:
            return self._error("disk usage", str(exc), started, path=path)

    def process_list(self, *, limit: int = 50) -> SystemResult:
        started = time.monotonic()
        try:
            if psutil is not None:
                items = []
                for proc in psutil.process_iter(attrs=["pid", "ppid", "name", "status", "cpu_percent", "memory_percent", "cmdline"]):
                    try:
                        info = proc.info
                        cmdline = " ".join(info.get("cmdline") or []) or info.get("name") or ""
                        items.append(
                            {
                                "pid": info.get("pid"),
                                "ppid": info.get("ppid"),
                                "name": info.get("name") or "",
                                "status": info.get("status") or "",
                                "cpu_percent": info.get("cpu_percent"),
                                "memory_percent": round(float(info.get("memory_percent") or 0.0), 3),
                                "cmdline": cmdline,
                            }
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):  # pragma: no cover - optional dependency behavior
                        continue
                    if len(items) >= limit:
                        break
                return SystemResult(True, "process list", f"Listed {len(items)} process(es).", items=items, duration_ms=self._elapsed_ms(started))

            items = self._fallback_process_list(limit=limit)
            return SystemResult(True, "process list", f"Listed {len(items)} process(es).", items=items, duration_ms=self._elapsed_ms(started))
        except OSError as exc:
            return self._error("process list", str(exc), started)

    def process_kill(self, pid: int, *, force: bool = False) -> SystemResult:
        started = time.monotonic()
        try:
            if pid <= 0:
                raise ValueError("pid must be positive.")
            if os.name == "nt":
                command = ["taskkill", "/PID", str(pid), "/F"] if force else ["taskkill", "/PID", str(pid)]
                completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
                if completed.returncode != 0:
                    raise OSError(completed.stderr.strip() or completed.stdout.strip() or "taskkill failed.")
            else:
                os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            return SystemResult(True, "process kill", f"Sent {'SIGKILL' if force else 'SIGTERM'} to {pid}.", pid=pid, duration_ms=self._elapsed_ms(started))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return self._error("process kill", str(exc), started, pid=pid)

    def port_check(self, host: str, port: int, *, timeout: float = 2.0) -> SystemResult:
        started = time.monotonic()
        try:
            if not host.strip():
                raise ValueError("host is required.")
            if port <= 0 or port > 65535:
                raise ValueError("port must be between 1 and 65535.")
            with socket.create_connection((host, port), timeout=timeout):
                pass
            return SystemResult(True, "port check", f"Port {host}:{port} is reachable.", port=port, duration_ms=self._elapsed_ms(started))
        except (OSError, ValueError) as exc:
            return self._error("port check", str(exc), started, port=port)

    def clipboard_get(self) -> SystemResult:
        started = time.monotonic()
        try:
            text = self._clipboard_get()
            return SystemResult(True, "clipboard get", "Clipboard contents retrieved.", info={"text": text}, duration_ms=self._elapsed_ms(started))
        except (OSError, RuntimeError, ValueError) as exc:
            return self._error("clipboard get", str(exc), started)

    def clipboard_set(self, text: str) -> SystemResult:
        started = time.monotonic()
        try:
            self._clipboard_set(text)
            return SystemResult(True, "clipboard set", "Clipboard contents updated.", info={"text": text}, duration_ms=self._elapsed_ms(started))
        except (OSError, RuntimeError, ValueError) as exc:
            return self._error("clipboard set", str(exc), started)

    def clipboard_clear(self) -> SystemResult:
        return self.clipboard_set("")

    def open_url(self, url: str) -> SystemResult:
        started = time.monotonic()
        try:
            if not url.strip():
                raise ValueError("URL is required.")
            opened = webbrowser.open(url, new=0, autoraise=False)
            if not opened:
                raise RuntimeError("No browser could be opened.")
            return SystemResult(True, "open url", f"Opened browser URL: {url}", info={"url": url}, duration_ms=self._elapsed_ms(started))
        except (OSError, RuntimeError, ValueError) as exc:
            return self._error("open url", str(exc), started, path=url)

    def _clipboard_get(self) -> str:
        if pyperclip is not None:
            return str(pyperclip.paste())
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover - optional dependency behavior
            raise RuntimeError("Clipboard support requires pyperclip or tkinter.") from exc
        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        finally:
            root.destroy()
        return text

    def _clipboard_set(self, text: str) -> None:
        if pyperclip is not None:
            pyperclip.copy(text)
            return
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover - optional dependency behavior
            raise RuntimeError("Clipboard support requires pyperclip or tkinter.") from exc
        root = tk.Tk()
        root.withdraw()
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
        finally:
            root.destroy()

    def _fallback_process_list(self, *, limit: int) -> list[dict[str, Any]]:
        if os.name == "nt":
            command = ["tasklist", "/FO", "CSV", "/NH"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
            if completed.returncode != 0:
                raise OSError(completed.stderr.strip() or "tasklist failed.")
            items: list[dict[str, Any]] = []
            for line in completed.stdout.splitlines():
                line = line.strip().strip('"')
                if not line:
                    continue
                parts = [part.strip('"') for part in line.split('","')]
                if len(parts) >= 2:
                    items.append({"pid": None, "ppid": None, "name": parts[0], "status": "", "cpu_percent": None, "memory_percent": None, "cmdline": parts[0]})
                if len(items) >= limit:
                    break
            return items
        commands = (
            ["ps", "-eo", "pid=,ppid=,stat=,%cpu=,%mem=,comm="],
            ["ps", "-A", "-o", "pid=,ppid=,stat=,%cpu=,%mem=,comm="],
            ["ps", "-ax", "-o", "pid=,ppid=,stat=,%cpu=,%mem=,comm="],
        )
        last_error = "ps failed."
        for command in commands:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
            if completed.returncode != 0:
                last_error = completed.stderr.strip() or completed.stdout.strip() or last_error
                continue
            items = []
            for line in completed.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 5)
                if len(parts) < 6:
                    continue
                pid_s, ppid_s, status, cpu_s, mem_s, comm = parts
                items.append(
                    {
                        "pid": int(pid_s),
                        "ppid": int(ppid_s),
                        "name": Path(comm).name,
                        "status": status,
                        "cpu_percent": float(cpu_s),
                        "memory_percent": float(mem_s),
                        "cmdline": comm,
                    }
                )
                if len(items) >= limit:
                    break
            return items
        raise OSError(last_error)

    def _safe_path(self, path: str) -> Path:
        candidate = (path or ".").strip()
        resolved = (self.workspace_root / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
        if self.workspace_root not in [resolved, *resolved.parents]:
            raise ValueError("Path must stay inside the workspace.")
        return resolved

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path)

    def _disk_usage_dict(self, path: Path) -> dict[str, Any]:
        usage = shutil.disk_usage(path)
        return {
            "path": str(path),
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent_used": round((usage.used / usage.total * 100.0) if usage.total else 0.0, 3),
        }

    def _elapsed_ms(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _error(self, command: str, message: str, started: float, *, path: str | None = None, pid: int | None = None, port: int | None = None) -> SystemResult:
        return SystemResult(False, command, message, path=path, pid=pid, port=port, duration_ms=self._elapsed_ms(started), error_type="system_error", error=message)
