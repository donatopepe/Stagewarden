from __future__ import annotations

import os
import shlex

from .config import AgentConfig
from .tools.browser import BrowserResult, BrowserTool
from .tools.external_io import ExternalIOResult, ExternalIOTool
from .tools.system import SystemResult, SystemTool
from .tools.watch import WatchResult, WatchTool


def parse_limit(value: str, *, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def execute_external_io_command(command: str, config: AgentConfig) -> ExternalIOResult | None:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return ExternalIOResult(ok=False, command=command, message=str(exc), error=str(exc))
    if not parts:
        return None
    tool = ExternalIOTool(config.workspace_root)
    if parts[0] == "checksum" and len(parts) == 2:
        return tool.checksum(parts[1])
    if parts[0] == "hash" and len(parts) in {2, 3}:
        return tool.hash_file(parts[1], algorithm=parts[2] if len(parts) == 3 else "sha256")
    if parts[0] == "download":
        max_bytes: int | None = None
        clean: list[str] = []
        index = 1
        while index < len(parts):
            if parts[index] == "--max-bytes" and index + 1 < len(parts):
                try:
                    max_bytes = int(parts[index + 1])
                except ValueError:
                    return ExternalIOResult(ok=False, command="download", message="--max-bytes must be an integer.", error="invalid_max_bytes")
                index += 2
                continue
            clean.append(parts[index])
            index += 1
        if len(clean) in {1, 2}:
            return tool.download(clean[0], clean[1] if len(clean) == 2 else None, max_bytes=max_bytes)
        return ExternalIOResult(ok=False, command="download", message="Usage: download <url> [path] [--max-bytes N]", error="usage")
    if parts[0] == "compress" and len(parts) in {2, 3}:
        return tool.gzip_compress(parts[1], parts[2] if len(parts) == 3 else None)
    if parts[:2] == ["archive", "verify"] and len(parts) == 3:
        return tool.verify_archive(parts[2])
    if parts[:2] == ["archive", "list"] and len(parts) == 3:
        return tool.archive_list(parts[2])
    if parts[:2] == ["archive", "extract"] and len(parts) in {3, 4}:
        return tool.archive_extract(parts[2], parts[3] if len(parts) == 4 else None)
    if parts[:2] == ["archive", "create"] and len(parts) >= 3:
        format_name: str | None = None
        clean: list[str] = []
        index = 2
        while index < len(parts):
            if parts[index] == "--format" and index + 1 < len(parts):
                format_name = parts[index + 1]
                index += 2
                continue
            clean.append(parts[index])
            index += 1
        if len(clean) in {1, 2}:
            return tool.archive_create(clean[0], clean[1] if len(clean) == 2 else None, format=format_name)
        return ExternalIOResult(ok=False, command="archive create", message="Usage: archive create <source> [destination] [--format zip|tar|gztar|bztar|xztar]", error="usage")
    if parts[:2] == ["web", "search"] and len(parts) >= 3:
        endpoint = os.environ.get("STAGEWARDEN_WEB_SEARCH_ENDPOINT")
        return tool.web_search(" ".join(parts[2:]), endpoint=endpoint)
    if parts[0] in {"download", "checksum", "hash", "compress", "archive", "web"}:
        return ExternalIOResult(
            ok=False,
            command=parts[0],
            message="Usage: web search <query> | download <url> [path] [--max-bytes N] | checksum <path> | hash <path> [algorithm] | compress <path> [target.gz] | archive verify <path.gz> | archive list <path> | archive extract <path> [destination] | archive create <source> [destination] [--format zip|tar|gztar|bztar|xztar]",
            error="usage",
        )
    return None


def handle_external_io_command(command: str, config: AgentConfig, *, execute_external_io_command=execute_external_io_command, record_handoff_action=None) -> str | None:  # noqa: ANN001
    result = execute_external_io_command(command, config)
    if result is None:
        return None
    if result.ok and record_handoff_action is not None:
        record_handoff_action(
            config,
            phase="external_io",
            task=command,
            summary=result.message,
            details=result.as_dict(),
        )
    status = "OK" if result.ok else "FAILED"
    detail = result.path or result.url or result.error or ""
    return f"{result.command}: {status} {result.message} {detail}".strip()


def execute_browser_command(command: str, config: AgentConfig) -> BrowserResult | None:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return BrowserResult(ok=False, command=command, message=str(exc), error=str(exc))
    if not parts:
        return None
    if parts[:2] == ["browser", "fetch"] and len(parts) >= 3:
        limit = 10
        if len(parts) >= 4:
            if parts[3] == "--limit" and len(parts) >= 5:
                limit = parse_limit(parts[4], default=10)
            else:
                limit = parse_limit(parts[3], default=10)
        return BrowserTool(config.workspace_root).fetch(parts[2], limit=limit)
    if parts[:2] == ["browser", "open"] and len(parts) == 3:
        return BrowserTool(config.workspace_root).open(parts[2])
    if parts[:2] == ["browser", "screenshot"] and len(parts) >= 3:
        full_page = True
        path: str | None = None
        browser_name = "chromium"
        index = 3
        while index < len(parts):
            if parts[index] == "--full-page":
                full_page = True
                index += 1
                continue
            if parts[index] == "--browser" and index + 1 < len(parts):
                browser_name = parts[index + 1]
                index += 2
                continue
            if path is None:
                path = parts[index]
            index += 1
        return BrowserTool(config.workspace_root).screenshot(parts[2], path=path, full_page=full_page, browser=browser_name)
    if parts[0] == "browser":
        return BrowserResult(
            ok=False,
            command="browser",
            message="Usage: browser fetch <url> [--limit N] | browser open <url> | browser screenshot <url> [path] [--browser chromium|firefox|webkit] [--full-page]",
            error_type="usage",
            error="usage",
        )
    return None


def execute_system_command(command: str, config: AgentConfig) -> SystemResult | None:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return SystemResult(ok=False, command=command, message=str(exc), error_type="usage", error=str(exc))
    if not parts:
        return None
    tool = SystemTool(config.workspace_root)
    if parts[:2] == ["system", "info"] and len(parts) == 2:
        return tool.info()
    if parts[:2] == ["disk", "usage"]:
        return tool.disk_usage(parts[2] if len(parts) >= 3 else ".")
    if parts[:2] == ["process", "list"]:
        limit = parse_limit(parts[2] if len(parts) >= 3 else "", default=50)
        return tool.process_list(limit=limit)
    if parts[:2] == ["process", "kill"] and len(parts) in {3, 4}:
        force = "--force" in parts[3:]
        try:
            pid = int(parts[2])
        except ValueError:
            return SystemResult(ok=False, command="process kill", message="PID must be an integer.", error_type="usage", error="invalid_pid")
        return tool.process_kill(pid, force=force)
    if parts[:2] == ["port", "check"] and len(parts) == 4:
        try:
            port = int(parts[3])
        except ValueError:
            return SystemResult(ok=False, command="port check", message="Port must be an integer.", error_type="usage", error="invalid_port")
        return tool.port_check(parts[2], port)
    if parts[:2] == ["clipboard", "get"] and len(parts) == 2:
        return tool.clipboard_get()
    if parts[:2] == ["clipboard", "set"] and len(parts) >= 3:
        return tool.clipboard_set(" ".join(parts[2:]))
    if parts[:2] == ["clipboard", "clear"] and len(parts) == 2:
        return tool.clipboard_clear()
    if parts[:2] == ["open", "url"] and len(parts) == 3:
        return tool.open_url(parts[2])
    if parts[0] in {"system", "disk", "process", "port", "clipboard", "open"}:
        return SystemResult(
            ok=False,
            command=" ".join(parts[:2]) if len(parts) >= 2 else parts[0],
            message="Usage: system info | disk usage [path] | process list [limit] | process kill <pid> [--force] | port check <host> <port> | clipboard get | clipboard set <text> | clipboard clear | open url <url>",
            error_type="usage",
            error="usage",
        )
    return None


def execute_watch_command(command: str, config: AgentConfig) -> WatchResult | None:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return WatchResult(ok=False, command=command, message=str(exc), error=str(exc))
    if not parts:
        return None
    if parts[0] != "watch":
        return None
    tool = WatchTool(config.workspace_root)
    if len(parts) >= 2:
        path = parts[1]
        timeout = None
        recursive = True
        poll = None
        index = 2
        while index < len(parts):
            if parts[index] == "--timeout" and index + 1 < len(parts):
                try:
                    timeout = float(parts[index + 1])
                except ValueError:
                    return WatchResult(ok=False, command="watch", message="--timeout must be numeric.", error_type="usage", error="invalid_timeout")
                index += 2
                continue
            if parts[index] == "--poll" and index + 1 < len(parts):
                try:
                    poll = float(parts[index + 1])
                except ValueError:
                    return WatchResult(ok=False, command="watch", message="--poll must be numeric.", error_type="usage", error="invalid_poll")
                index += 2
                continue
            if parts[index] == "--recursive":
                recursive = True
                index += 1
                continue
            if parts[index] == "--no-recursive":
                recursive = False
                index += 1
                continue
            index += 1
        return tool.watch(path, timeout_seconds=timeout, recursive=recursive, poll_interval=poll)
    return WatchResult(ok=False, command="watch", message="Usage: watch <path> [--timeout N] [--recursive|--no-recursive] [--poll N]", error_type="usage", error="usage")
