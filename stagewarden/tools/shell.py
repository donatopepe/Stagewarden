from __future__ import annotations

import os
import platform
import selectors
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..config import AgentConfig
from ..permissions import PermissionPolicy
from ..textcodec import detect_confusables, to_ascii_safe_text


@dataclass(slots=True)
class ShellResult:
    ok: bool
    command: str
    cwd: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    duration_ms: int = 0
    output_preview: str = ""
    session_id: str = ""
    warnings: list[str] | None = None


@dataclass(slots=True)
class ShellSession:
    id: str
    process: subprocess.Popen[bytes]
    cwd: str


class ShellTool:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.sessions: dict[str, ShellSession] = {}
        self.os_name = platform.system().lower()
        self.is_windows = self.os_name == "windows"
        self.permissions = PermissionPolicy.load(config.settings_path, config.session_permission_settings)

    def refresh_permissions(self) -> None:
        self.permissions = PermissionPolicy.load(self.config.settings_path, self.config.session_permission_settings)

    def run(self, command: str, cwd: str | None = None) -> ShellResult:
        command = command.strip()
        invalid = self._validate_command(command, cwd)
        if invalid is not None:
            return invalid

        run_cwd = self._resolve_cwd(cwd)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                self._command_args(command),
                cwd=run_cwd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.config.shell_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ShellResult(False, command, str(run_cwd), -1, error="Command timed out.", duration_ms=duration_ms)
        except OSError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ShellResult(False, command, str(run_cwd), -1, error=str(exc), duration_ms=duration_ms)

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        stdout, stderr, warnings = self._normalize_text_outputs(stdout, stderr)
        preview = self._build_preview(command, completed.returncode, stdout, stderr, duration_ms, warnings=warnings)
        return ShellResult(
            ok=completed.returncode == 0,
            command=command,
            cwd=str(run_cwd),
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            error="" if completed.returncode == 0 else (stderr or "Command failed."),
            duration_ms=duration_ms,
            output_preview=preview,
            warnings=warnings,
        )

    def create_session(self, cwd: str | None = None) -> ShellResult:
        run_cwd = self._resolve_cwd(cwd)
        session_id = uuid.uuid4().hex[:12]
        try:
            process = subprocess.Popen(
                self._interactive_shell_args(),
                cwd=run_cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
            )
        except OSError as exc:
            return ShellResult(False, "", str(run_cwd), -1, error=str(exc))

        self.sessions[session_id] = ShellSession(id=session_id, process=process, cwd=str(run_cwd))
        return ShellResult(
            ok=True,
            command="",
            cwd=str(run_cwd),
            returncode=0,
            session_id=session_id,
            output_preview=f"shell_session_created id={session_id} cwd={run_cwd}",
        )

    def send_session(self, session_id: str, command: str) -> ShellResult:
        session = self.sessions.get(session_id)
        if session is None:
            return ShellResult(False, command, "", -1, error="Unknown shell session.", session_id=session_id)

        invalid = self._validate_command(command, session.cwd)
        if invalid is not None:
            invalid.session_id = session_id
            return invalid

        if session.process.poll() is not None:
            return ShellResult(False, command, session.cwd, -1, error="Shell session is closed.", session_id=session_id)

        marker = f"__STAGEWARDEN_EXIT__:{uuid.uuid4().hex}"
        payload = self._session_payload(command, marker)
        started = time.monotonic()
        try:
            assert session.process.stdin is not None
            session.process.stdin.write(payload)
            session.process.stdin.flush()
            combined = self._read_until_marker(session.process, marker, self.config.shell_timeout_seconds)
        except TimeoutError:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ShellResult(
                False,
                command,
                session.cwd,
                -1,
                error="Session command timed out.",
                duration_ms=duration_ms,
                session_id=session_id,
            )
        except OSError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ShellResult(False, command, session.cwd, -1, error=str(exc), duration_ms=duration_ms, session_id=session_id)

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, returncode = self._split_marker_output(combined, marker)
        stdout = stdout.strip()
        stdout, _stderr, warnings = self._normalize_text_outputs(stdout, "")
        preview = self._build_preview(command, returncode, stdout, "", duration_ms, session_id=session_id, warnings=warnings)
        return ShellResult(
            ok=returncode == 0,
            command=command,
            cwd=session.cwd,
            returncode=returncode,
            stdout=stdout.strip(),
            duration_ms=duration_ms,
            output_preview=preview,
            error="" if returncode == 0 else "Command failed.",
            session_id=session_id,
            warnings=warnings,
        )

    def close_session(self, session_id: str) -> ShellResult:
        session = self.sessions.pop(session_id, None)
        if session is None:
            return ShellResult(False, "", "", -1, error="Unknown shell session.", session_id=session_id)

        process = session.process
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
        return ShellResult(
            ok=True,
            command="",
            cwd=session.cwd,
            returncode=0,
            session_id=session_id,
            output_preview=f"shell_session_closed id={session_id}",
        )

    def _validate_command(self, command: str, cwd: str | None) -> ShellResult | None:
        command = command.strip()
        if not command:
            return ShellResult(False, command, str(self.config.workspace_root), -1, error="Empty command.")

        if any(token in command for token in self.config.blocked_shell_tokens):
            return ShellResult(False, command, str(self.config.workspace_root), -1, error="Blocked command token.")

        first_token = command.split()[0]
        if not any(first_token == prefix for prefix in self.config.allowed_shell_prefixes):
            return ShellResult(False, command, str(self.config.workspace_root), -1, error="Command prefix not allowed.")

        capability = "shell:read" if self._is_read_only_command(command) else "shell:write"
        decision = self.permissions.decide(capability, command)
        if not decision.allowed:
            if decision.source.startswith("ask:") and self._approve_permission(capability, command, decision):
                return None
            return ShellResult(False, command, str(self.config.workspace_root), -1, error=decision.message or "Permission denied.")

        run_cwd = self._resolve_cwd(cwd)
        if not self.config.is_within_workspace(run_cwd):
            return ShellResult(False, command, str(run_cwd), -1, error="Working directory is outside the workspace.")
        return None

    def _approve_permission(self, capability: str, detail: str, decision: object) -> bool:
        approver = self.config.permission_approver
        if approver is None:
            return False
        try:
            approved = bool(approver(capability, detail, decision))  # type: ignore[arg-type]
        except (OSError, EOFError):
            return False
        if approved:
            self.refresh_permissions()
        return approved

    def _command_args(self, command: str) -> list[str]:
        if self.is_windows:
            shell = self._windows_shell()
            if shell.endswith("cmd.exe") or shell.lower() == "cmd":
                return [shell, "/d", "/s", "/c", command]
            return [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
        shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        if Path(shell).name == "bash":
            return [shell, "-lc", command]
        return [shell, "-c", command]

    def _interactive_shell_args(self) -> list[str]:
        if self.is_windows:
            shell = self._windows_shell()
            if shell.endswith("cmd.exe") or shell.lower() == "cmd":
                return [shell, "/d", "/q"]
            return [shell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass"]
        shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        if Path(shell).name == "bash":
            return [shell, "--noprofile", "--norc"]
        return [shell]

    def _session_payload(self, command: str, marker: str) -> bytes:
        if self.is_windows:
            return f"{command}\nWrite-Output \"{marker}:$LASTEXITCODE\"\n".encode()
        return f"{command}\nprintf '{marker}:%s\\n' $?\n".encode()

    def _windows_shell(self) -> str:
        return shutil.which("pwsh") or shutil.which("powershell") or shutil.which("cmd") or "powershell"

    def _resolve_cwd(self, cwd: str | None) -> Path:
        return self.config.resolve_path(cwd) if cwd else self.config.workspace_root_resolved

    def _is_read_only_command(self, command: str) -> bool:
        if self._has_write_operator(command):
            return False
        try:
            tokens = shlex.split(command, posix=not self.is_windows)
        except ValueError:
            tokens = command.split()
        if not tokens:
            return False
        first_token = tokens[0]
        if first_token == "git":
            return self._is_read_only_git(tokens[1:])
        if first_token in {"npm", "node", "python", "python3", "pytest", "make", "bash", "sh", "pwsh", "powershell", "cmd"}:
            return self._is_read_only_program(tokens)
        return first_token in {
            "ls",
            "pwd",
            "cat",
            "find",
            "rg",
            "grep",
            "sed",
            "awk",
            "where",
            "dir",
            "type",
        }

    def _has_write_operator(self, command: str) -> bool:
        return any(operator in command for operator in (">", ">>", "2>", "1>", "| tee ", "|tee "))

    def _is_read_only_git(self, args: list[str]) -> bool:
        if not args:
            return False
        passthrough_options = {"-c", "--config-env"}
        index = 0
        while index < len(args):
            token = args[index]
            if token in passthrough_options:
                index += 2
                continue
            if token.startswith("-"):
                index += 1
                continue
            break
        if index >= len(args):
            return False
        subcommand = args[index]
        return subcommand in {
            "status",
            "log",
            "show",
            "diff",
            "rev-parse",
            "branch",
            "tag",
            "remote",
            "ls-files",
            "grep",
            "blame",
            "describe",
        }

    def _is_read_only_program(self, tokens: list[str]) -> bool:
        if not tokens:
            return False
        first = tokens[0]
        lowered = [token.lower() for token in tokens[1:]]
        write_words = {
            "install",
            "add",
            "remove",
            "uninstall",
            "update",
            "upgrade",
            "publish",
            "run",
            "exec",
            "build",
            "start",
            "dev",
            "test",
            "write",
            "touch",
            "rm",
            "del",
            "copy",
            "move",
            "mkdir",
            "rmdir",
        }
        if any(token in write_words for token in lowered):
            return False
        if first in {"python", "python3"}:
            return any(token in {"--version", "-V", "-VV"} for token in tokens[1:]) or "-m" in tokens and "pytest" not in lowered
        if first == "node":
            return any(token in {"--version", "-v"} for token in lowered)
        if first == "npm":
            return bool(lowered and lowered[0] in {"view", "version", "--version", "-v", "help"})
        if first == "pytest":
            return False
        return False

    def _read_until_marker(self, process: subprocess.Popen[bytes], marker: str, timeout_seconds: int) -> str:
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        chunks: list[bytes] = []
        marker_bytes = marker.encode()

        while time.monotonic() < deadline:
            events = selector.select(timeout=0.1)
            for key, _mask in events:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    continue
                chunks.append(chunk)
                if marker_bytes in b"".join(chunks):
                    selector.unregister(process.stdout)
                    return b"".join(chunks).decode(errors="replace")

            if process.poll() is not None and not events:
                break

        selector.unregister(process.stdout)
        raise TimeoutError("Timed out waiting for command marker.")

    def _split_marker_output(self, combined: str, marker: str) -> tuple[str, int]:
        output, _, tail = combined.partition(marker)
        tail = tail.lstrip(":")
        exit_text = tail.splitlines()[0].strip() if tail else "-1"
        try:
            returncode = int(exit_text)
        except ValueError:
            returncode = -1
        return output, returncode

    def _build_preview(
        self,
        command: str,
        returncode: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
        *,
        session_id: str = "",
        warnings: list[str] | None = None,
    ) -> str:
        sections = []
        if session_id:
            sections.append(f"session_id={session_id}")
        sections.extend(
            [
                f"$ {command}",
                f"exit_code={returncode}",
                f"duration_ms={duration_ms}",
            ]
        )
        if warnings:
            sections.append(f"warnings:\n{'; '.join(warnings)}")
        if stdout:
            sections.append(f"stdout:\n{stdout[:2000]}")
        if stderr:
            sections.append(f"stderr:\n{stderr[:2000]}")
        return "\n".join(sections)

    def _normalize_text_outputs(self, stdout: str, stderr: str) -> tuple[str, str, list[str]]:
        warnings = detect_confusables(stdout) + detect_confusables(stderr)
        if self.config.strict_ascii_output:
            return to_ascii_safe_text(stdout), to_ascii_safe_text(stderr), warnings
        return stdout, stderr, warnings
