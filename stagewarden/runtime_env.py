from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_SHELLS: tuple[str, ...] = ("bash", "zsh", "powershell", "cmd")


def detect_runtime_capabilities(cwd: Path | None = None) -> dict[str, Any]:
    system = platform.system()
    os_family = _normalize_os_family(system)
    default_shell = os.environ.get("COMSPEC") if os_family == "windows" else os.environ.get("SHELL")
    shells = {name: _shell_info(name) for name in SUPPORTED_SHELLS}
    return {
        "os_family": os_family,
        "platform_system": system,
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "cwd": str((cwd or Path.cwd()).resolve()),
        "default_shell": default_shell or "",
        "path_separator": os.sep,
        "line_ending": "crlf" if os_family == "windows" else "lf",
        "shells": shells,
        "recommended_shell": _recommended_shell(os_family, default_shell or "", shells),
    }


def select_shell_backend(requested: str = "auto", capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
    caps = capabilities or detect_runtime_capabilities()
    requested_normalized = (requested or "auto").strip().lower()
    shells = caps.get("shells", {})
    os_family = str(caps.get("os_family", "unknown"))

    if requested_normalized == "auto":
        selected = str(caps.get("recommended_shell") or _recommended_shell(os_family, str(caps.get("default_shell", "")), shells))
        info = _shell_from_caps(shells, selected)
        return {
            "requested": "auto",
            "selected": selected,
            "available": bool(info.get("available")),
            "executable": info.get("path"),
            "reason": f"auto selected {selected} for {os_family}",
        }

    if requested_normalized not in SUPPORTED_SHELLS:
        return {
            "requested": requested,
            "selected": None,
            "available": False,
            "executable": None,
            "reason": f"unsupported shell: {requested}",
        }

    info = _shell_from_caps(shells, requested_normalized)
    return {
        "requested": requested_normalized,
        "selected": requested_normalized,
        "available": bool(info.get("available")),
        "executable": info.get("path"),
        "reason": "requested shell is available" if info.get("available") else f"requested shell is not available: {requested_normalized}",
    }


def _normalize_os_family(system: str) -> str:
    lowered = system.lower()
    if lowered == "darwin":
        return "macos"
    if lowered == "linux":
        return "linux"
    if lowered == "windows":
        return "windows"
    return "unknown"


def _shell_info(name: str) -> dict[str, Any]:
    executable = _find_shell(name)
    version = _shell_version(name, executable) if executable else ""
    return {
        "available": executable is not None,
        "path": executable,
        "version": version,
    }


def _find_shell(name: str) -> str | None:
    if name == "powershell":
        return shutil.which("pwsh") or shutil.which("powershell")
    if name == "cmd":
        return shutil.which("cmd")
    return shutil.which(name)


def _shell_version(name: str, executable: str) -> str:
    args = _version_args(name, executable)
    if not args:
        return ""
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
    except OSError:
        return ""
    except subprocess.TimeoutExpired:
        return "timeout"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0].strip() if output else ""


def _version_args(name: str, executable: str) -> list[str]:
    if name in {"bash", "zsh"}:
        return [executable, "--version"]
    if name == "powershell":
        return [executable, "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]
    if name == "cmd":
        return [executable, "/d", "/c", "ver"]
    return []


def _recommended_shell(os_family: str, default_shell: str, shells: dict[str, Any]) -> str:
    if os_family == "windows":
        if _shell_from_caps(shells, "powershell").get("available"):
            return "powershell"
        if _shell_from_caps(shells, "cmd").get("available"):
            return "cmd"
        return "powershell"
    default_name = Path(default_shell).name.lower() if default_shell else ""
    if default_name in {"zsh", "bash"} and _shell_from_caps(shells, default_name).get("available"):
        return default_name
    if _shell_from_caps(shells, "bash").get("available"):
        return "bash"
    if _shell_from_caps(shells, "zsh").get("available"):
        return "zsh"
    return "sh"


def _shell_from_caps(shells: Any, name: str) -> dict[str, Any]:
    if isinstance(shells, dict):
        value = shells.get(name)
        if isinstance(value, dict):
            return value
    return {"available": False, "path": None, "version": ""}
