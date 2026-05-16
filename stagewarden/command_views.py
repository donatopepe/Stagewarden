from __future__ import annotations

from typing import Any

from .agent import Agent
from .config import AgentConfig
from .tools.git import GitTool
from .json_schema_registry import json_schema
from .permissions import PermissionSettings, VALID_PERMISSION_MODES
from .tools.files import FileTool
from . import shell_views as _shell_views


def _main():
    from . import main as _main_module

    return _main_module


def _parse_limit(raw: str, *, default: int) -> int:
    if not raw:
        return default
    try:
        return max(1, min(int(raw), 200))
    except ValueError:
        return default


def _handle_permission_command(parts: list[str], config: AgentConfig, agent: Agent | None = None) -> str:
    settings = PermissionSettings.load(config.settings_path)
    if len(parts) < 2:
        return (
            "Usage: permissions | permission mode <mode> | permission allow <rule> | "
            "permission ask <rule> | permission deny <rule> | permission reset | "
            "permission session <mode|allow|ask|deny|reset> ..."
        )
    if parts[1] == "session":
        session = config.session_permission_settings or PermissionSettings()
        if len(parts) < 3:
            return "Usage: permission session mode <mode> | permission session allow <rule> | permission session ask <rule> | permission session deny <rule> | permission session reset"
        session_action = parts[2]
        if session_action == "mode":
            if len(parts) != 4:
                return f"Usage: permission session mode <{'|'.join(VALID_PERMISSION_MODES)}>"
            mode = parts[3].strip().lower().replace("-", "_")
            if mode not in VALID_PERMISSION_MODES:
                return f"Unsupported session permission mode '{parts[3]}'."
            session.default_mode = mode
            config.session_permission_settings = session.normalize()
            if agent is not None:
                _main()._refresh_runtime_permissions(agent)
            return f"Session permission mode set to {mode}."
        if session_action in {"allow", "ask", "deny"}:
            if len(parts) < 4:
                return f"Usage: permission session {session_action} <rule>"
            rule = " ".join(parts[3:]).strip()
            target = getattr(session, session_action)
            if rule not in target:
                target.append(rule)
            config.session_permission_settings = session.normalize()
            if agent is not None:
                _main()._refresh_runtime_permissions(agent)
            return f"Added session {session_action} rule: {rule}"
        if session_action == "reset":
            config.session_permission_settings = None
            if agent is not None:
                _main()._refresh_runtime_permissions(agent)
            return "Session permission settings reset."
        return "Usage: permission session mode <mode> | permission session allow <rule> | permission session ask <rule> | permission session deny <rule> | permission session reset"
    action = parts[1]
    if action == "mode":
        if len(parts) != 3:
            return f"Usage: permission mode <{'|'.join(VALID_PERMISSION_MODES)}>"
        mode = parts[2].strip().lower().replace("-", "_")
        if mode not in VALID_PERMISSION_MODES:
            return f"Unsupported permission mode '{parts[2]}'."
        settings.default_mode = mode
        settings.normalize().save(config.settings_path)
        if agent is not None:
            _main()._refresh_runtime_permissions(agent)
        return f"Permission mode set to {mode}."
    if action in {"allow", "ask", "deny"}:
        if len(parts) < 3:
            return f"Usage: permission {action} <rule>"
        rule = " ".join(parts[2:]).strip()
        target = getattr(settings, action)
        if rule not in target:
            target.append(rule)
        settings.normalize().save(config.settings_path)
        if agent is not None:
            _main()._refresh_runtime_permissions(agent)
        return f"Added {action} rule: {rule}"
    if action == "reset":
        PermissionSettings().save(config.settings_path)
        if agent is not None:
            _main()._refresh_runtime_permissions(agent)
        return "Permission settings reset."
    return (
        "Usage: permissions | permission mode <mode> | permission allow <rule> | "
        "permission ask <rule> | permission deny <rule> | permission reset | "
        "permission session <mode|allow|ask|deny|reset> ..."
    )


def _handle_shell_command(parts: list[str], config: AgentConfig) -> str | None:
    if not parts or parts[0] != "shell":
        return None
    if len(parts) >= 2 and parts[1] == "backend":
        if len(parts) == 2:
            return _shell_views._render_shell_backend(config)
        if len(parts) == 4 and parts[2] == "use":
            backend = parts[3].strip().lower()
            if backend not in {"auto", "bash", "zsh", "powershell", "cmd"}:
                return "Usage: shell backend use <auto|bash|zsh|powershell|cmd>"
            _shell_views._save_shell_backend(config, backend)
            config.shell_backend = backend
            return f"Shell backend set to {backend}.\n{_shell_views._render_shell_backend(config)}"
    return "Usage: shell backend | shell backend use <auto|bash|zsh|powershell|cmd>"


def _parse_git_oneline(stdout: str) -> list[dict[str, str]]:
    commits: list[dict[str, str]] = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        commit, _, subject = text.partition(" ")
        subject = subject.strip()
        if subject.startswith("(") and ") " in subject:
            _decorations, _sep, subject = subject.partition(") ")
        commits.append({"commit": commit, "subject": subject.strip()})
    return commits


def _handle_git_command(command: str, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts or parts[0] != "git":
        return None
    tool = GitTool(config)
    if len(parts) == 2 and parts[1] == "status":
        result = tool.status()
        return result.stdout or result.error or "Clean working tree."
    if len(parts) in {2, 3} and parts[1] == "log":
        limit = _parse_limit(parts[2] if len(parts) == 3 else "", default=20)
        result = tool.log(limit=limit)
        return result.stdout or result.error or "No git history."
    if parts[1] == "history":
        if len(parts) not in {3, 4}:
            return "Usage: git history <path> [limit]"
        limit = _parse_limit(parts[3] if len(parts) == 4 else "", default=20)
        result = tool.file_history(parts[2], limit=limit)
        return result.stdout or result.error or "No file history."
    if parts[1] == "show":
        stat = "--stat" in parts[2:]
        revision_parts = [item for item in parts[2:] if item != "--stat"]
        revision = revision_parts[0] if revision_parts else "HEAD"
        result = tool.show(revision=revision, stat=stat)
        return result.stdout or result.error or "No revision details."
    return "Usage: git status | git log [limit] | git history <path> [limit] | git show [--stat] [revision]"


def _git_command_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    parts = command.split()
    if not parts or parts[0] != "git":
        return None
    tool = GitTool(config)
    if len(parts) == 2 and parts[1] == "status":
        result = tool.status()
        return {
            "command": "git status",
            "schema": json_schema("git status"),
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "lines": result.stdout.splitlines() if result.stdout else [],
        }
    if len(parts) in {2, 3} and parts[1] == "log":
        limit = _parse_limit(parts[2] if len(parts) == 3 else "", default=20)
        result = tool.log(limit=limit)
        return {
            "command": "git log",
            "schema": json_schema("git log"),
            "limit": limit,
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "commits": _parse_git_oneline(result.stdout),
        }
    if len(parts) >= 2 and parts[1] == "history":
        if len(parts) not in {3, 4}:
            return {
                "command": "git history",
                "schema": json_schema("git history"),
                "ok": False,
                "error": "Usage: git history <path> [limit]",
            }
        limit = _parse_limit(parts[3] if len(parts) == 4 else "", default=20)
        result = tool.file_history(parts[2], limit=limit)
        return {
            "command": "git history",
            "schema": json_schema("git history"),
            "path": parts[2],
            "limit": limit,
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "commits": _parse_git_oneline(result.stdout),
        }
    if len(parts) >= 2 and parts[1] == "show":
        stat = "--stat" in parts[2:]
        revision_parts = [item for item in parts[2:] if item != "--stat"]
        revision = revision_parts[0] if revision_parts else "HEAD"
        result = tool.show(revision=revision, stat=stat)
        return {
            "command": "git show",
            "schema": json_schema("git show"),
            "revision": revision,
            "stat": stat,
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "lines": result.stdout.splitlines() if result.stdout else [],
        }
    return {
        "command": command,
        "schema": json_schema("git"),
        "ok": False,
        "error": "Usage: git status | git log [limit] | git history <path> [limit] | git show [--stat] [revision]",
    }


def _resolve_shell_session_id(agent: Agent, requested: str) -> str | None:
    sessions = agent.executor.shell.sessions
    if requested == "last":
        if not sessions:
            return None
        return next(reversed(sessions))
    return requested if requested in sessions else None


def _handle_shell_session_command(command: str, agent: Agent) -> str | None:
    parts = command.split(maxsplit=3)
    if not parts:
        return None
    if parts[0] == "sessions":
        result = agent.executor.shell.list_sessions()
        return result.output_preview or result.error
    if parts[0] != "session":
        return None
    if len(parts) < 2:
        return "Usage: session create [cwd] | session list | session send <id|last> <command> | session close <id|last>"
    action = parts[1]
    if action == "list":
        result = agent.executor.shell.list_sessions()
        return result.output_preview or result.error
    if action == "create":
        cwd = parts[2] if len(parts) >= 3 else None
        result = agent.executor.shell.create_session(cwd=cwd)
        return result.output_preview or result.error
    if action == "send":
        if len(parts) != 4:
            return "Usage: session send <id|last> <command>"
        session_id = _resolve_shell_session_id(agent, parts[2])
        if session_id is None:
            return "Unknown shell session."
        result = agent.executor.shell.send_session(session_id, parts[3])
        return result.output_preview or result.error
    if action == "close":
        if len(parts) != 3:
            return "Usage: session close <id|last>"
        session_id = _resolve_shell_session_id(agent, parts[2])
        if session_id is None:
            return "Unknown shell session."
        result = agent.executor.shell.close_session(session_id)
        return result.output_preview or result.error
    return "Usage: session create [cwd] | session list | session send <id|last> <command> | session close <id|last>"


def _handle_patch_command(command: str, agent: Agent) -> str | None:
    parts = command.split(maxsplit=2)
    if not parts or parts[0] != "patch":
        return None
    if len(parts) != 3 or parts[1] != "preview":
        return "Usage: patch preview <diff-file>"
    diff_file = agent.executor.files.read(parts[2])
    if not diff_file.ok:
        return diff_file.error
    result = agent.executor.files.preview_patch_files(diff_file.content)
    if not result.ok:
        return result.error
    return f"Patch preview:\n{result.content}"


def _file_command_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    parts = command.split()
    if len(parts) < 2 or parts[0] != "file":
        return None
    tool = FileTool(config)
    action = parts[1]
    flags = set(part for part in parts[2:] if part.startswith("--"))
    args = [part for part in parts[2:] if not part.startswith("--")]
    dry_run = "--dry-run" in flags
    overwrite = "--overwrite" in flags
    recursive = "--recursive" in flags
    if action == "inspect":
        if len(args) != 1:
            return {"command": "file inspect", "ok": False, "error": "Usage: file inspect <path>"}
        result = tool.inspect(args[0])
        return {"command": "file inspect", "path": args[0], "ok": result.ok, "error": result.error, "report": result.report}
    if action == "stat":
        if len(args) != 1:
            return {"command": "file stat", "ok": False, "error": "Usage: file stat <path>"}
        result = tool.inspect_metadata(args[0])
        return {"command": "file stat", "path": args[0], "ok": result.ok, "error": result.error, "report": result.report}
    if action == "copy":
        if len(args) != 2:
            return {"command": "file copy", "ok": False, "error": "Usage: file copy <source> <destination> [--overwrite] [--dry-run]"}
        result = tool.copy_path(args[0], args[1], overwrite=overwrite, dry_run=dry_run)
        return {"command": "file copy", "source": args[0], "destination": args[1], "ok": result.ok, "error": result.error, "report": result.report, "message": result.content}
    if action == "move":
        if len(args) != 2:
            return {"command": "file move", "ok": False, "error": "Usage: file move <source> <destination> [--overwrite] [--dry-run]"}
        result = tool.move_path(args[0], args[1], overwrite=overwrite, dry_run=dry_run)
        return {"command": "file move", "source": args[0], "destination": args[1], "ok": result.ok, "error": result.error, "report": result.report, "message": result.content}
    if action == "delete":
        if len(args) != 1:
            return {"command": "file delete", "ok": False, "error": "Usage: file delete <path> [--recursive] [--dry-run]"}
        result = tool.delete_path(args[0], recursive=recursive, dry_run=dry_run)
        return {"command": "file delete", "path": args[0], "ok": result.ok, "error": result.error, "report": result.report, "message": result.content}
    if action == "chmod":
        if len(args) != 2:
            return {"command": "file chmod", "ok": False, "error": "Usage: file chmod <path> <mode> [--recursive] [--dry-run]"}
        result = tool.chmod_path(args[0], args[1], recursive=recursive, dry_run=dry_run)
        return {"command": "file chmod", "path": args[0], "mode": args[1], "ok": result.ok, "error": result.error, "report": result.report, "message": result.content}
    if action == "chown":
        if len(args) not in {2, 3}:
            return {"command": "file chown", "ok": False, "error": "Usage: file chown <path> <user> [group] [--recursive] [--dry-run]"}
        group = args[2] if len(args) == 3 else None
        result = tool.chown_path(args[0], user=args[1], group=group, recursive=recursive, dry_run=dry_run)
        return {"command": "file chown", "path": args[0], "user": args[1], "group": group, "ok": result.ok, "error": result.error, "report": result.report, "message": result.content}
    return {"command": command, "ok": False, "error": "Usage: file inspect <path> | file stat <path> | file copy <source> <destination> [--overwrite] [--dry-run] | file move <source> <destination> [--overwrite] [--dry-run] | file delete <path> [--recursive] [--dry-run] | file chmod <path> <mode> [--recursive] [--dry-run] | file chown <path> <user> [group] [--recursive] [--dry-run]"}


def _render_file_command(report: dict[str, object]) -> str:
    if not report.get("ok"):
        return str(report.get("error") or "File command failed.")
    command = str(report.get("command", "file"))
    detail = report.get("report")
    message = str(report.get("message") or "").strip()
    if command in {"file inspect", "file stat"} and isinstance(detail, dict):
        lines = [f"{command}:"]
        for key, value in detail.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
    return message or f"{command}: OK"


def _handle_file_command(command: str, config: AgentConfig) -> str | None:
    report = _file_command_report(command, config)
    if report is None:
        return None
    return _render_file_command(report)


def _shell_sessions_report(agent: Agent) -> dict[str, object]:
    items: list[dict[str, str]] = []
    for session_id, session in sorted(agent.executor.shell.sessions.items()):
        state = "closed" if session.process.poll() is not None else "running"
        items.append(
            {
                "id": session_id,
                "cwd": session.cwd,
                "state": state,
            }
        )
    return {
        "command": "sessions",
        "schema": json_schema("sessions"),
        "count": len(items),
        "items": items,
    }
