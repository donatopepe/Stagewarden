from __future__ import annotations

from typing import Any, Callable

from .config import AgentConfig
from .memory import MemoryStore
from .textcodec import dumps_ascii
from .tools.browser import BrowserResult
from .tools.external_io import ExternalIOResult
from .tools.system import SystemResult
from .tools.watch import WatchResult


RecordHandoffAction = Callable[..., None]


def external_io_result_to_text(result: ExternalIOResult) -> str:
    lines = [f"{result.command}: {'OK' if result.ok else 'FAIL'} {result.message}"]
    if not result.ok and getattr(result, "retryable", False):
        lines.append("- retry: safe to resume when connectivity returns")
    if result.url:
        lines.append(f"- url: {result.url}")
    if result.path:
        lines.append(f"- path: {result.path}")
    if result.bytes_written:
        lines.append(f"- bytes: {result.bytes_written}")
    if getattr(result, "hash_algorithm", None):
        lines.append(f"- hash_algorithm: {result.hash_algorithm}")
    if getattr(result, "digest", None):
        lines.append(f"- digest: {result.digest}")
    if result.sha256:
        lines.append(f"- sha256: {result.sha256}")
    if result.content_type:
        lines.append(f"- content_type: {result.content_type}")
    if result.items:
        lines.append("Results:")
        for index, item in enumerate(result.items, 1):
            title = item.get("title") or "(untitled)"
            url = item.get("url") or ""
            snippet = item.get("snippet") or ""
            lines.append(f"- {index}. {title} {url}".rstrip())
            if snippet:
                lines.append(f"  {snippet}")
    if result.error:
        lines.append(f"- error: {result.error}")
    return "\n".join(lines)


def record_external_io_evidence(
    config: AgentConfig,
    result: ExternalIOResult,
    *,
    task: str,
    record_handoff_action: RecordHandoffAction,
) -> None:
    memory = MemoryStore.load(config.memory_path)
    memory.record_tool_transcript(
        iteration=0,
        step_id="external-io",
        tool="external_io",
        action_type=result.command,
        success=result.ok,
        summary=result.message,
        detail=dumps_ascii(result.as_dict()),
        duration_ms=result.duration_ms,
        error_type=None if result.ok else (result.error_type or "external_io_error"),
    )
    memory.save(config.memory_path)
    phase_names = {
        "web search": "web_search",
        "download": "download_file",
        "checksum": "checksum_file",
        "compress": "compress_file",
        "archive verify": "archive_verify",
    }
    phase = phase_names.get(result.command, result.command.replace(" ", "_"))
    record_handoff_action(
        config,
        phase=phase,
        task=task,
        summary=result.message,
        details={
            "ok": result.ok,
            "path": result.path,
            "url": result.url,
            "bytes_written": result.bytes_written,
            "sha256": result.sha256,
            "hash_algorithm": getattr(result, "hash_algorithm", None),
            "digest": getattr(result, "digest", None),
            "content_type": result.content_type,
            "error": result.error,
            "items": result.items or [],
        },
    )


def handle_external_io_command(
    command: str,
    config: AgentConfig,
    *,
    execute_external_io_command: Callable[[str, AgentConfig], ExternalIOResult | None],
    record_handoff_action: RecordHandoffAction,
) -> str | None:
    result = execute_external_io_command(command, config)
    if result is None:
        return None
    record_external_io_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return external_io_result_to_text(result)


def external_io_report(
    command: str,
    config: AgentConfig,
    *,
    execute_external_io_command: Callable[[str, AgentConfig], ExternalIOResult | None],
    record_handoff_action: RecordHandoffAction,
) -> dict[str, object] | None:
    result = execute_external_io_command(command, config)
    if result is None:
        return None
    record_external_io_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return result.as_dict()


def browser_result_to_text(result: BrowserResult) -> str:
    lines = [f"{result.command}: {'OK' if result.ok else 'FAIL'} {result.message}"]
    if result.url:
        lines.append(f"- url: {result.url}")
    if result.path:
        lines.append(f"- path: {result.path}")
    if result.title:
        lines.append(f"- title: {result.title}")
    if result.bytes_read:
        lines.append(f"- bytes_read: {result.bytes_read}")
    if result.content_type:
        lines.append(f"- content_type: {result.content_type}")
    if result.items:
        lines.append("Links:")
        for index, item in enumerate(result.items, 1):
            href = item.get("href") or ""
            text = item.get("text") or ""
            lines.append(f"- {index}. {text} {href}".rstrip())
    if result.error:
        lines.append(f"- error: {result.error}")
    return "\n".join(lines)


def record_browser_evidence(
    config: AgentConfig,
    result: BrowserResult,
    *,
    task: str,
    record_handoff_action: RecordHandoffAction,
) -> None:
    memory = MemoryStore.load(config.memory_path)
    memory.record_tool_transcript(
        iteration=0,
        step_id="browser",
        tool="browser",
        action_type=result.command,
        success=result.ok,
        summary=result.message,
        detail=dumps_ascii(result.as_dict()),
        duration_ms=result.duration_ms,
        error_type=None if result.ok else (result.error_type or "browser_error"),
    )
    memory.save(config.memory_path)
    record_handoff_action(
        config,
        phase=result.command.replace(" ", "_"),
        task=task,
        summary=result.message,
        details={
            "ok": result.ok,
            "url": result.url,
            "path": result.path,
            "title": result.title,
            "bytes_read": result.bytes_read,
            "content_type": result.content_type,
            "error": result.error,
            "items": result.items or [],
        },
    )


def handle_browser_command(
    command: str,
    config: AgentConfig,
    *,
    execute_browser_command: Callable[[str, AgentConfig], BrowserResult | None],
    record_handoff_action: RecordHandoffAction,
) -> str | None:
    result = execute_browser_command(command, config)
    if result is None:
        return None
    record_browser_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return browser_result_to_text(result)


def browser_report(
    command: str,
    config: AgentConfig,
    *,
    execute_browser_command: Callable[[str, AgentConfig], BrowserResult | None],
    record_handoff_action: RecordHandoffAction,
) -> dict[str, object] | None:
    result = execute_browser_command(command, config)
    if result is None:
        return None
    record_browser_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return result.as_dict()


def watch_result_to_text(result: WatchResult) -> str:
    lines = [f"{result.command}: {'OK' if result.ok else 'FAIL'} {result.message}"]
    if result.path:
        lines.append(f"- path: {result.path}")
    if result.items:
        lines.append("Events:")
        for index, item in enumerate(result.items, 1):
            parts = ", ".join(f"{key}={value}" for key, value in item.items())
            lines.append(f"- {index}. {parts}")
    if result.error:
        lines.append(f"- error: {result.error}")
    return "\n".join(lines)


def record_watch_evidence(
    config: AgentConfig,
    result: WatchResult,
    *,
    task: str,
    record_handoff_action: RecordHandoffAction,
) -> None:
    memory = MemoryStore.load(config.memory_path)
    memory.record_tool_transcript(
        iteration=0,
        step_id="watch",
        tool="watch",
        action_type=result.command,
        success=result.ok,
        summary=result.message,
        detail=dumps_ascii(result.as_dict()),
        duration_ms=result.duration_ms,
        error_type=None if result.ok else (result.error_type or "watch_error"),
    )
    memory.save(config.memory_path)
    record_handoff_action(
        config,
        phase="watch",
        task=task,
        summary=result.message,
        details={
            "ok": result.ok,
            "path": result.path,
            "items": result.items or [],
            "error": result.error,
        },
    )


def handle_watch_command(
    command: str,
    config: AgentConfig,
    *,
    execute_watch_command: Callable[[str, AgentConfig], WatchResult | None],
    record_handoff_action: RecordHandoffAction,
) -> str | None:
    result = execute_watch_command(command, config)
    if result is None:
        return None
    record_watch_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return watch_result_to_text(result)


def watch_report(
    command: str,
    config: AgentConfig,
    *,
    execute_watch_command: Callable[[str, AgentConfig], WatchResult | None],
    record_handoff_action: RecordHandoffAction,
) -> dict[str, object] | None:
    result = execute_watch_command(command, config)
    if result is None:
        return None
    record_watch_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return result.as_dict()


def system_result_to_text(result: SystemResult) -> str:
    lines = [f"{result.command}: {result.message}"]
    if result.info:
        lines.append("Info:")
        for key, value in result.info.items():
            lines.append(f"- {key}: {value}")
    if result.items:
        lines.append("Items:")
        for index, item in enumerate(result.items, 1):
            parts = ", ".join(f"{key}={value}" for key, value in item.items())
            lines.append(f"- {index}. {parts}")
    if result.path:
        lines.append(f"- path: {result.path}")
    if result.pid is not None:
        lines.append(f"- pid: {result.pid}")
    if result.port is not None:
        lines.append(f"- port: {result.port}")
    if result.error:
        lines.append(f"- error: {result.error}")
    return "\n".join(lines)


def record_system_evidence(
    config: AgentConfig,
    result: SystemResult,
    *,
    task: str,
    record_handoff_action: RecordHandoffAction,
) -> None:
    memory = MemoryStore.load(config.memory_path)
    memory.record_tool_transcript(
        iteration=0,
        step_id="system",
        tool="system",
        action_type=result.command,
        success=result.ok,
        summary=result.message,
        detail=dumps_ascii(result.as_dict()),
        duration_ms=result.duration_ms,
        error_type=None if result.ok else (result.error_type or "system_error"),
    )
    memory.save(config.memory_path)
    record_handoff_action(
        config,
        phase=result.command.replace(" ", "_"),
        task=task,
        summary=result.message,
        details={
            "ok": result.ok,
            "info": result.info or {},
            "items": result.items or [],
            "path": result.path,
            "pid": result.pid,
            "port": result.port,
            "error": result.error,
        },
    )


def handle_system_command(
    command: str,
    config: AgentConfig,
    *,
    execute_system_command: Callable[[str, AgentConfig], SystemResult | None],
    record_handoff_action: RecordHandoffAction,
) -> str | None:
    result = execute_system_command(command, config)
    if result is None:
        return None
    record_system_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return system_result_to_text(result)


def system_report(
    command: str,
    config: AgentConfig,
    *,
    execute_system_command: Callable[[str, AgentConfig], SystemResult | None],
    record_handoff_action: RecordHandoffAction,
) -> dict[str, object] | None:
    result = execute_system_command(command, config)
    if result is None:
        return None
    record_system_evidence(config, result, task=command, record_handoff_action=record_handoff_action)
    return result.as_dict()
