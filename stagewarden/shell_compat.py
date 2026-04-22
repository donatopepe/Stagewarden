from __future__ import annotations

import shlex
from pathlib import Path


WINDOWS_BACKENDS = {"powershell", "cmd"}
POSIX_ONLY_TOKENS = {"sed", "awk", "grep", "find", "bash", "sh"}


def shell_env_reference(name: str, shell_backend: str) -> str:
    clean = _clean_env_name(name)
    shell = _normalize_shell(shell_backend)
    if shell == "powershell":
        return f"$env:{clean}"
    if shell == "cmd":
        return f"%{clean}%"
    return f"${clean}"


def shell_quote(value: str, shell_backend: str) -> str:
    shell = _normalize_shell(shell_backend)
    if shell == "powershell":
        return "'" + value.replace("'", "''") + "'"
    if shell == "cmd":
        return '"' + value.replace('"', '\\"') + '"'
    return shlex.quote(value)


def shell_path_literal(path: str | Path, shell_backend: str, *, os_family: str) -> str:
    raw = str(path)
    shell = _normalize_shell(shell_backend)
    if os_family == "windows" or shell in WINDOWS_BACKENDS:
        normalized = raw.replace("/", "\\")
    else:
        normalized = raw.replace("\\", "/")
    return shell_quote(normalized, shell)


def prepare_command_for_shell(command: str, shell_backend: str) -> tuple[str | None, str | None]:
    shell = _normalize_shell(shell_backend)
    if shell not in WINDOWS_BACKENDS:
        return command, None

    tokens = _split_command(command, shell)
    if not tokens:
        return None, "Empty command."

    first = tokens[0].lower()
    if first in POSIX_ONLY_TOKENS:
        return None, (
            f"Command `{tokens[0]}` is POSIX-only for shell_backend={shell}. "
            "Use a translated command, choose bash/zsh, or run through an explicit compatible tool."
        )

    if shell == "powershell":
        return _translate_powershell(tokens), None
    return _translate_cmd(tokens), None


def _translate_powershell(tokens: list[str]) -> str:
    command = tokens[0].lower()
    args = tokens[1:]
    if command == "pwd":
        return "Get-Location"
    if command in {"ls", "dir"}:
        return _join_command("Get-ChildItem", args, "powershell")
    if command in {"cat", "type"}:
        return _join_command("Get-Content", args, "powershell")
    if command == "where":
        return _join_command("Get-Command", args, "powershell")
    return _join_command(tokens[0], args, "powershell")


def _translate_cmd(tokens: list[str]) -> str:
    command = tokens[0].lower()
    args = tokens[1:]
    if command == "pwd":
        return "cd"
    if command == "ls":
        return _join_command("dir", args, "cmd")
    if command == "cat":
        return _join_command("type", args, "cmd")
    return _join_command(tokens[0], args, "cmd")


def _join_command(command: str, args: list[str], shell_backend: str) -> str:
    if not args:
        return command
    return " ".join([command, *(shell_quote(arg, shell_backend) for arg in args)])


def _split_command(command: str, shell_backend: str) -> list[str]:
    try:
        return shlex.split(command, posix=shell_backend != "cmd")
    except ValueError:
        return command.split()


def _clean_env_name(name: str) -> str:
    clean = name.strip()
    if not clean.replace("_", "").isalnum() or not clean:
        raise ValueError("Environment variable name must contain only letters, numbers, and underscores.")
    return clean


def _normalize_shell(shell_backend: str) -> str:
    shell = (shell_backend or "").strip().lower()
    if shell in {"pwsh", "powershell.exe"}:
        return "powershell"
    if shell == "cmd.exe":
        return "cmd"
    return shell
