from __future__ import annotations

import re
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime

from .agent import Agent
from .config import AgentConfig
from .commands import command_catalog
from .json_schema_registry import json_schema
from .memory import MemoryStore
from .modelprefs import SUPPORTED_MODELS, account_key, extract_blocked_until, limit_snapshot_from_message
from .permissions import PermissionSettings
from . import account_views as _account_views
from . import model_views as _model_views
from . import project_state_views as _project_state_views
from . import project_handoff_views as _project_handoff_views
from .project import role_tree_views as _role_tree_views
from .project import role_views as _role_views
from .project_handoff import ProjectHandoff
from .runtime_env import detect_runtime_capabilities, select_shell_backend
from .textcodec import read_text_utf8
from .tools.git import GitTool
from .secrets import SecretStore


def _main():
    from . import main as _main_module

    return _main_module


def _limits():
    from . import status_limits_views as _status_limits_views_module

    return _status_limits_views_module


def _roles():
    from . import project as _project_module

    return _project_module.role_views


def _shell_backend_report(config: AgentConfig) -> dict[str, object]:
    configured = str(getattr(config, "shell_backend", "auto") or "auto")
    selection = select_shell_backend(configured, detect_runtime_capabilities(config.workspace_root))
    return {
        "command": "shell backend",
        "configured": configured,
        "selected": selection["selected"],
        "available": selection["available"],
        "executable": selection["executable"],
        "reason": selection["reason"],
    }


def _render_shell_backend(config: AgentConfig) -> str:
    report = _shell_backend_report(config)
    return "\n".join(
        [
            "Shell backend:",
            f"- configured: {report['configured']}",
            f"- selected: {report['selected'] or 'none'}",
            f"- available: {str(report['available']).lower()}",
            f"- executable: {report['executable'] or 'none'}",
            f"- reason: {report['reason']}",
        ]
    )


def _source_reference_manifest(config: AgentConfig) -> list[dict[str, str]]:
    manifest_path = config.workspace_root / "docs" / "source_references.md"
    if not manifest_path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in read_text_utf8(manifest_path).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "`external_sources/" not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        project = cells[0].replace("`", "").strip()
        path_match = re.search(r"`([^`]+)`", cells[1])
        upstream_match = re.search(r"`([^`]+)`", cells[2])
        if not project or path_match is None or upstream_match is None:
            continue
        rows.append(
            {
                "project": project,
                "path": path_match.group(1),
                "upstream": upstream_match.group(1),
            }
        )
    return rows


def _provider_limit_snapshot_is_stale(captured_at: object, *, stale_after_minutes: int = 15) -> bool:
    return _limits()._provider_limit_snapshot_is_stale(captured_at, stale_after_minutes=stale_after_minutes)


def _provider_limit_windows(item: dict[str, object]) -> dict[str, object]:
    return _limits()._provider_limit_windows(item)


def _provider_limit_resets_at(windows: dict[str, object]) -> object:
    return _limits()._provider_limit_resets_at(windows)


def _provider_limit_account_view(account: dict[str, object]) -> dict[str, object]:
    return _limits()._provider_limit_account_view(account)


def _provider_limit_entry_view(
    item: dict[str, object],
    *,
    include_accounts: bool = False,
) -> dict[str, object]:
    return _limits()._provider_limit_entry_view(item, include_accounts=include_accounts)


def _provider_limit_summary_report(provider_limits: dict[str, object]) -> dict[str, object]:
    return _limits()._provider_limit_summary_report(provider_limits)


def _provider_limit_summary(agent: Agent, config: AgentConfig) -> str:
    return _limits()._provider_limit_summary(agent, config)


def _record_limit_message(
    config: AgentConfig,
    prefs,
    *,
    model: str,
    message: str,
    account: str | None = None,
) -> str:
    if model not in SUPPORTED_MODELS:
        return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
    clean_message = message.strip().replace("\n", " ")[:240]
    if not clean_message:
        return "Limit message cannot be empty."
    until = extract_blocked_until(clean_message)
    snapshot = limit_snapshot_from_message(clean_message, blocked_until=until)
    if account:
        if account not in (prefs.accounts_by_model or {}).get(model, []):
            prefs.add_account(model, account)
        prefs.last_limit_message_by_account = dict(prefs.last_limit_message_by_account or {})
        prefs.last_limit_message_by_account[account_key(model, account)] = clean_message
        prefs.set_account_limit_snapshot(model, account, snapshot)
        if until:
            prefs.block_account(model, account, until)
    else:
        prefs.last_limit_message_by_model = dict(prefs.last_limit_message_by_model or {})
        prefs.last_limit_message_by_model[model] = clean_message
        prefs.set_model_limit_snapshot(model, snapshot)
        if until:
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            prefs.blocked_until_by_model[model] = until
            if prefs.preferred_model == model:
                prefs.preferred_model = None
    prefs.normalize().save(config.settings_path)
    return f"Recorded limit snapshot for {f'{model}:{account}' if account else model}; {'blocked until ' + until if until else 'no reset time detected.'}"


def _clear_limit_snapshot(config: AgentConfig, prefs, *, model: str, account: str | None = None) -> str:
    if model not in SUPPORTED_MODELS:
        return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
    if account:
        key = account_key(model, account)
        prefs.blocked_until_by_account = dict(prefs.blocked_until_by_account or {})
        prefs.blocked_until_by_account.pop(key, None)
        prefs.last_limit_message_by_account = dict(prefs.last_limit_message_by_account or {})
        prefs.last_limit_message_by_account.pop(key, None)
        prefs.provider_limit_snapshot_by_account = dict(prefs.provider_limit_snapshot_by_account or {})
        prefs.provider_limit_snapshot_by_account.pop(key, None)
        return f"Cleared limit snapshot for {model}:{account}."
    prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
    prefs.blocked_until_by_model.pop(model, None)
    prefs.last_limit_message_by_model = dict(prefs.last_limit_message_by_model or {})
    prefs.last_limit_message_by_model.pop(model, None)
    prefs.provider_limit_snapshot_by_model = dict(prefs.provider_limit_snapshot_by_model or {})
    prefs.provider_limit_snapshot_by_model.pop(model, None)
    prefs.normalize().save(config.settings_path)
    return f"Cleared limit snapshot for {model}."


def _permissions_report(config: AgentConfig) -> dict[str, object]:
    workspace_settings = PermissionSettings.load(config.settings_path)
    session_settings = config.session_permission_settings
    effective_settings = workspace_settings.merged(session_settings)
    return {
        "command": "permissions",
        "schema": json_schema("permissions"),
        "workspace": {
            "mode": workspace_settings.default_mode,
            "allow": list(workspace_settings.allow),
            "ask": list(workspace_settings.ask),
            "deny": list(workspace_settings.deny),
        },
        "session": {
            "mode": None if session_settings is None else session_settings.default_mode,
            "allow": [] if session_settings is None else list(session_settings.allow),
            "ask": [] if session_settings is None else list(session_settings.ask),
            "deny": [] if session_settings is None else list(session_settings.deny),
        },
        "effective": {
            "mode": effective_settings.default_mode,
            "allow": list(effective_settings.allow),
            "ask": list(effective_settings.ask),
            "deny": list(effective_settings.deny),
        },
    }


def _render_runtime_status(config: AgentConfig) -> str:
    runtime = _main().detect_runtime_capabilities(config.workspace_root)
    shells = runtime["shells"]
    lines = [
        "Runtime:",
        f"- os_family: {runtime['os_family']}",
        f"- platform: {runtime['platform_system']} {runtime['platform_release']} {runtime['platform_machine']}",
        f"- default_shell: {runtime['default_shell'] or 'none'}",
        f"- recommended_shell: {runtime['recommended_shell']}",
        f"- path_separator: {runtime['path_separator']}",
        f"- line_ending: {runtime['line_ending']}",
    ]
    for name in ("bash", "zsh", "powershell", "cmd"):
        info = shells.get(name, {}) if isinstance(shells, dict) else {}
        state = "available" if info.get("available") else "unavailable"
        path = info.get("path") or "none"
        version = f" version={info['version']}" if info.get("version") else ""
        lines.append(f"- {name}: {state} path={path}{version}")
    return "\n".join(lines)


def _agent_capability_surface_for_node(config: AgentConfig) -> dict[str, object]:
    main = _main()
    runtime = main.detect_runtime_capabilities(config.workspace_root)
    shell_backend = _shell_backend_report(config)
    permissions = _permissions_report(config)
    return {
        "workspace": str(config.workspace_root),
        "os_family": str(runtime.get("os_family", "unknown")),
        "recommended_shell": str(runtime.get("recommended_shell", "unknown")),
        "default_shell": str(runtime.get("default_shell") or "none"),
        "shell_backend": {
            "configured": shell_backend["configured"],
            "selected": shell_backend["selected"] or "none",
            "executable": shell_backend["executable"] or "none",
        },
        "permission_mode": permissions["effective"]["mode"],
        "core_tools": {
            "shell": True,
            "files": True,
            "git": True,
            "web_research": True,
            "download": True,
            "compression": True,
            "wet_run_required": True,
        },
        "model_actions": sorted(main.ALLOWED_MODEL_ACTIONS),
        "file_operations": [
            "read_file",
            "inspect_file",
            "inspect_metadata_file",
            "write_file",
            "apply_patch",
            "search_replace_file",
            "insert_text_file",
            "delete_range_file",
            "delete_backward_file",
            "replace_range_file",
            "convert_encoding_file",
            "normalize_line_endings_file",
            "copy_path_file",
            "move_path_file",
            "delete_path_file",
            "chmod_path_file",
            "chown_path_file",
            "patch_file",
            "patch_files",
            "preview_patch_files",
            "list_files",
            "search_files",
        ],
        "git_operations": [
            "git_status",
            "git_diff",
            "git_log",
            "git_show",
            "git_file_history",
            "git_commit",
        ],
        "shell_operations": [
            "shell",
            "shell_session_create",
            "shell_session_send",
            "shell_session_close",
        ],
    }


def _sources_status_report(config: AgentConfig, *, strict: bool = False) -> dict[str, object]:
    main = _main()
    manifest = main._source_reference_manifest(config)
    items: list[dict[str, object]] = []
    for entry in manifest:
        local_path = config.workspace_root / entry["path"]
        exists = local_path.exists()
        is_git = (local_path / ".git").exists()
        head_ok = False
        remote_ok = False
        shallow_ok = False
        head = None
        remote = None
        shallow = None
        message = "missing"
        if exists and is_git:
            head_ok, head = main._git_output(local_path, "rev-parse", "--short", "HEAD")
            remote_ok, remote = main._git_output(local_path, "remote", "get-url", "origin")
            shallow_ok, shallow = main._git_output(local_path, "rev-parse", "--is-shallow-repository")
            message = "ok" if head_ok and remote_ok and main._normalize_git_url(remote) == main._normalize_git_url(entry["upstream"]) else "metadata mismatch"
        elif exists:
            message = "path exists but is not a git repository"
        items.append(
            {
                "project": entry["project"],
                "path": entry["path"],
                "expected_upstream": entry["upstream"],
                "exists": exists,
                "git_repository": is_git,
                "head": head if head_ok else None,
                "upstream": remote if remote_ok else None,
                "upstream_matches": bool(remote_ok and main._normalize_git_url(remote) == main._normalize_git_url(entry["upstream"])),
                "shallow": (shallow == "true") if shallow_ok else None,
                "status": "OK" if message == "ok" else ("FAIL" if strict else "WARN"),
                "message": message,
            }
        )
    ok = bool(items) and all(item["status"] == "OK" for item in items)
    return {
        "command": "sources status --strict" if strict else "sources status",
        "manifest": "docs/source_references.md",
        "strict": strict,
        "count": len(items),
        "ok": ok,
        "summary": {
            "ok": sum(1 for item in items if item["status"] == "OK"),
            "warn": sum(1 for item in items if item["status"] == "WARN"),
            "fail": sum(1 for item in items if item["status"] == "FAIL"),
        },
        "items": items,
    }


def _render_sources_status(config: AgentConfig, *, strict: bool = False) -> str:
    report = _sources_status_report(config, strict=strict)
    lines = ["External source references:"]
    if strict:
        lines.append("- strict: yes")
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    lines.append(
        f"- summary: ok={summary.get('ok', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}"
    )
    if not report["items"]:
        return "\n".join(lines + ["- WARN manifest missing or contains no external source rows."])
    for item in report["items"]:
        lines.append(
            f"- {item['project']}: {item['status']} {item['message']} "
            f"path={item['path']} head={item['head'] or 'unknown'} "
            f"upstream={item['upstream'] or 'unknown'} shallow={item['shallow']}"
        )
        if not item["upstream_matches"]:
            lines.append(f"  expected_upstream={item['expected_upstream']}")
    return "\n".join(lines)


def _sources_update_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    status = _sources_status_report(config)
    items: list[dict[str, object]] = []
    for item in status["items"]:
        if not item.get("exists") or not item.get("git_repository"):
            items.append({**item, "updated": False, "ok": False, "update_message": "missing or not a git repository"})
            continue
        if not item.get("upstream_matches"):
            items.append(
                {
                    **item,
                    "updated": False,
                    "ok": False,
                    "before_head": item.get("head"),
                    "after_head": item.get("head"),
                    "update_message": "skipped: upstream mismatch",
                }
            )
            continue
        local_path = config.workspace_root / str(item["path"])
        before_ok, before = main._git_output(local_path, "rev-parse", "--short", "HEAD")
        completed = main._git_completed(local_path, "pull", "--ff-only", timeout=30)
        after_ok, after = main._git_output(local_path, "rev-parse", "--short", "HEAD")
        output = completed.stdout.strip() or completed.stderr.strip()
        items.append(
            {
                **item,
                "ok": completed.returncode == 0 and after_ok,
                "updated": bool(before_ok and after_ok and before != after),
                "before_head": before if before_ok else None,
                "after_head": after if after_ok else None,
                "update_message": output or "already up to date",
            }
        )
    report = {
        "command": "sources update",
        "count": len(items),
        "updated_count": sum(1 for item in items if item.get("updated")),
        "failed_count": sum(1 for item in items if not item.get("ok")),
        "ok": bool(items) and all(bool(item.get("ok")) for item in items),
        "items": items,
    }
    _project_handoff_views._record_handoff_action(
        config,
        phase="sources_update",
        task="sources update",
        summary=f"Updated {sum(1 for item in items if item.get('updated'))}/{len(items)} external source repositories.",
        details=report,
    )
    return report


def _render_sources_update(config: AgentConfig) -> str:
    report = _sources_update_report(config)
    lines = ["External source update:"]
    lines.append(f"- ok: {str(report['ok']).lower()}")
    lines.append(f"- summary: updated={report['updated_count']} failed={report['failed_count']} total={report['count']}")
    for item in report["items"]:
        lines.append(
            f"- {item['project']}: {'OK' if item.get('ok') else 'FAIL'} "
            f"updated={str(bool(item.get('updated'))).lower()} "
            f"before={item.get('before_head') or item.get('head') or 'unknown'} "
            f"after={item.get('after_head') or 'unknown'}"
        )
        if item.get("update_message"):
            lines.append(f"  message={item['update_message']}")
    return "\n".join(lines)


def _handle_sources_command(command: str, config: AgentConfig) -> str | None:
    if command in {"sources", "sources status"}:
        return _render_sources_status(config)
    if command == "sources status --strict":
        return _render_sources_status(config, strict=True)
    if command == "sources update":
        return _render_sources_update(config)
    if command.startswith("sources "):
        return "Usage: sources | sources status [--strict] | sources update"
    return None


def _update_status_report(config: AgentConfig, *, fetch: bool = False) -> dict[str, object]:
    main = _main()
    root = config.workspace_root
    inside_ok, inside = main._git_output(root, "rev-parse", "--is-inside-work-tree")
    if not inside_ok or inside != "true":
        return {
            "command": "update check" if fetch else "update status",
            "ok": False,
            "repository": False,
            "message": "Workspace is not a git repository.",
            "update_available": False,
        }
    fetch_message = None
    if fetch:
        fetched = main._git_completed(root, "fetch", "--quiet", "--prune", timeout=60)
        fetch_message = fetched.stdout.strip() or fetched.stderr.strip() or "fetch completed"
        if fetched.returncode != 0:
            return {
                "command": "update check",
                "ok": False,
                "repository": True,
                "message": fetch_message,
                "update_available": False,
            }
    branch_ok, branch = main._git_output(root, "branch", "--show-current")
    head_ok, head = main._git_output(root, "rev-parse", "--short", "HEAD")
    upstream_ok, upstream = main._git_output(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_head_ok, upstream_head = (False, "")
    ahead = behind = 0
    if upstream_ok:
        upstream_head_ok, upstream_head = main._git_output(root, "rev-parse", "--short", upstream)
        counts_ok, counts = main._git_output(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts_ok:
            parts = counts.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    dirty_ok, dirty = main._git_output(root, "status", "--porcelain")
    remote_ok, remote = main._git_output(root, "remote", "get-url", "origin")
    ok = bool(branch_ok and head_ok and upstream_ok and upstream_head_ok and dirty_ok)
    return {
        "command": "update check" if fetch else "update status",
        "ok": ok,
        "repository": True,
        "branch": branch if branch_ok else None,
        "head": head if head_ok else None,
        "upstream": upstream if upstream_ok else None,
        "upstream_head": upstream_head if upstream_head_ok else None,
        "remote": remote if remote_ok else None,
        "ahead": ahead,
        "behind": behind,
        "dirty": bool(dirty.strip()) if dirty_ok else None,
        "update_available": behind > 0,
        "fetch_message": fetch_message,
        "message": "ok" if ok else "No upstream configured or git metadata unavailable.",
    }


def _render_update_status(config: AgentConfig, *, fetch: bool = False) -> str:
    report = _update_status_report(config, fetch=fetch)
    lines = ["Stagewarden self-update:"]
    lines.append(f"- ok: {str(bool(report.get('ok'))).lower()}")
    lines.append(f"- branch: {report.get('branch') or 'unknown'}")
    lines.append(f"- head: {report.get('head') or 'unknown'}")
    lines.append(f"- upstream: {report.get('upstream') or 'none'}")
    lines.append(f"- upstream_head: {report.get('upstream_head') or 'unknown'}")
    lines.append(f"- ahead: {report.get('ahead', 0)}")
    lines.append(f"- behind: {report.get('behind', 0)}")
    lines.append(f"- dirty: {str(report.get('dirty')).lower()}")
    lines.append(f"- update_available: {str(bool(report.get('update_available'))).lower()}")
    if report.get("fetch_message"):
        lines.append(f"- fetch: {report['fetch_message']}")
    if not report.get("ok"):
        lines.append(f"- message: {report.get('message')}")
    return "\n".join(lines)


def _update_apply_report(config: AgentConfig, *, confirmed: bool = False) -> dict[str, object]:
    main = _main()
    if not confirmed:
        return {
            "command": "update apply",
            "ok": False,
            "applied": False,
            "needs_confirmation": True,
            "message": "Use update apply --yes to confirm fast-forward self-update.",
        }
    before = _update_status_report(config, fetch=True)
    if not before.get("ok"):
        return {"command": "update apply", "ok": False, "applied": False, "message": before.get("message"), "before": before}
    if before.get("dirty"):
        return {"command": "update apply", "ok": False, "applied": False, "message": "Refusing self-update with dirty working tree.", "before": before}
    if not before.get("update_available"):
        return {"command": "update apply", "ok": True, "applied": False, "message": "Already up to date.", "before": before, "after": before}
    pulled = main._git_completed(config.workspace_root, "pull", "--ff-only", timeout=60)
    after = _update_status_report(config, fetch=False)
    output = pulled.stdout.strip() or pulled.stderr.strip()
    report = {
        "command": "update apply",
        "ok": pulled.returncode == 0 and bool(after.get("ok")),
        "applied": pulled.returncode == 0 and before.get("head") != after.get("head"),
        "message": output or "fast-forward applied",
        "before": before,
        "after": after,
    }
    _project_handoff_views._record_handoff_action(
        config,
        phase="update_apply",
        task="update apply --yes",
        summary=str(report["message"]),
        details=report,
    )
    return report


def _render_update_apply(config: AgentConfig, *, confirmed: bool = False) -> str:
    report = _update_apply_report(config, confirmed=confirmed)
    lines = ["Stagewarden self-update apply:"]
    lines.append(f"- ok: {str(bool(report.get('ok'))).lower()}")
    lines.append(f"- applied: {str(bool(report.get('applied'))).lower()}")
    if report.get("needs_confirmation"):
        lines.append("- needs_confirmation: yes")
    lines.append(f"- message: {report.get('message')}")
    before = report.get("before", {}) if isinstance(report.get("before"), dict) else {}
    after = report.get("after", {}) if isinstance(report.get("after"), dict) else {}
    if before:
        lines.append(f"- before_head: {before.get('head') or 'unknown'}")
    if after:
        lines.append(f"- after_head: {after.get('head') or 'unknown'}")
    return "\n".join(lines)


def _handle_update_command(command: str, config: AgentConfig) -> str | None:
    if command == "update status":
        return _render_update_status(config)
    if command in {"update check", "update check --json"}:
        return _render_update_status(config, fetch=True)
    if command in {"update apply", "update apply --yes"}:
        return _render_update_apply(config, confirmed=command.endswith(" --yes"))
    if command.startswith("update "):
        return "Usage: update status | update check [--json] | update apply --yes"
    return None


def _provider_limit_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _limits()._provider_limit_status_report(agent, config)


def _render_provider_limit_status(agent: Agent, config: AgentConfig) -> str:
    return _limits()._render_provider_limit_status(agent, config)


def _render_model_status(agent: Agent, config: AgentConfig) -> str:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    status = agent.router.status()
    lines = ["Provider configuration:"]
    for provider in SUPPORTED_MODELS:
        backend = main.MODEL_BACKENDS[provider]["label"]
        capability = main.provider_capability(provider)
        enabled = "enabled" if provider in status["enabled_models"] else "disabled"
        blocked_until = status["blocked_until_by_model"].get(provider)
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        active = " active" if provider in status["active_models"] else " inactive"
        preferred = " preferred-provider" if status["preferred_model"] == provider else ""
        provider_model, selection_mode, default_model = _model_views._provider_model_display(prefs, provider)
        params = _model_views._provider_model_params_display(prefs, provider)
        active_account = (prefs.active_account_by_model or {}).get(provider) or "none"
        auth = capability.auth_type
        profiles = "profiles=yes" if capability.supports_account_profiles else "profiles=no"
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if params
            else ""
        )
        lines.append(
            f"- {provider}: {enabled}{active}{preferred}{blocked} "
            f"provider_model={provider_model} selection={selection_mode} active_account={active_account} default_model={default_model} "
            f"auth={auth} {profiles}{params_text} ({backend})"
        )
        account_lines = _account_views._render_account_lines(prefs, provider)
        lines.extend(account_lines)
    latest_attempt = agent.memory.latest_attempt()
    if latest_attempt is not None:
        status_text = "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}"
        lines.append(
            f"- last_attempt: step={latest_attempt.step_id} "
            f"status={status_text} "
            f"account={latest_attempt.account or 'none'} provider_model={latest_attempt.variant or 'provider-default'}"
        )
    if status["preferred_model"] is None:
        lines.append("- preferred_provider: automatic routing")
    else:
        lines.append(f"- preferred_provider: {status['preferred_model']}")
    return "\n".join(lines)


def _selected_model_report(model_report: dict[str, object]) -> dict[str, object] | None:
    models = model_report.get("models", []) if isinstance(model_report, dict) else []
    if not isinstance(models, list):
        return None
    selected = next((item for item in models if isinstance(item, dict) and item.get("preferred")), None)
    if selected is None:
        selected = next((item for item in models if isinstance(item, dict) and item.get("active")), None)
    return selected if isinstance(selected, dict) else None


def _model_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    status = agent.router.status()
    catalog = main.load_ai_models_catalog()
    models: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        capability = main.provider_capability(model)
        provider_catalog = main.catalog_entries_for_provider(model, catalog)
        provider_default_entry = next((item for item in provider_catalog if str(item.get("model_id")) == "provider-default"), None)
        provider_model, selection_mode, default_model = _model_views._provider_model_display(prefs, model)
        params = _model_views._provider_model_params_display(prefs, model)
        catalog_entry = main.catalog_entry_for_provider_model(model, provider_model, catalog)
        models.append(
            {
                "model": model,
                "provider": model,
                "enabled": model in status["enabled_models"],
                "active": model in status["active_models"],
                "preferred": status["preferred_model"] == model,
                "blocked_until": status["blocked_until_by_model"].get(model),
                "variant": prefs.variant_for_model(model) or "provider-default",
                "provider_model": provider_model,
                "provider_model_selection": selection_mode,
                "provider_model_default": default_model,
                "provider_model_params": params,
                "auth": capability.auth_type,
                "profiles": capability.supports_account_profiles,
                "backend": main.MODEL_BACKENDS[model]["label"],
                "catalog": _model_views._catalog_entry_display(catalog_entry, None),
                "catalog_source": (catalog_entry or provider_default_entry or {}).get("source") if (catalog_entry or provider_default_entry) else None,
                "pricing_source": (catalog_entry or provider_default_entry or {}).get("pricing_source")
                if (catalog_entry or provider_default_entry)
                else None,
                "catalog_size": len(provider_catalog),
            }
        )
    return {
        "command": "models",
        "schema": json_schema("models"),
        "models": models,
        "preferred_model": status["preferred_model"],
        "preferred_provider": status["preferred_model"],
    }


def _model_limits_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    report = _provider_limit_status_report(agent, config)
    return {
        "command": "model limits",
        "schema": json_schema("model limits"),
        "summary": _provider_limit_summary_report(report),
        "providers": [_provider_limit_entry_view(item, include_accounts=True) for item in report["providers"]],
    }


def _render_model_limits(agent: Agent, config: AgentConfig) -> str:
    report = _model_limits_report(agent, config)
    lines = ["Model/provider limits:"]
    if not report["providers"]:
        lines.append("- none")
        return "\n".join(lines)
    summary = report["summary"]
    lines.append(
        "- summary: "
        f"blocked_models={','.join(summary['blocked_models']) if summary['blocked_models'] else 'none'} "
        f"stale_models={','.join(summary['stale_models']) if summary['stale_models'] else 'none'} "
        f"blocked_accounts={','.join(summary['blocked_accounts']) if summary['blocked_accounts'] else 'none'} "
        f"stale_accounts={','.join(summary['stale_accounts']) if summary['stale_accounts'] else 'none'}"
    )
    for item in report["providers"]:
        blocked = f" blocked_until={item['blocked_until']}" if item["blocked_until"] else ""
        reason = f" reason={item['reason']}" if item["reason"] else ""
        window = f" window={item['rate_limit_type']}" if item["rate_limit_type"] else ""
        utilization = f" utilization={item['utilization']}%" if item["utilization"] is not None else ""
        captured = f" captured_at={item['captured_at']}" if item["captured_at"] else ""
        lines.append(
            f"- {item['provider']}: {item['status']}{blocked}{reason}{window}{utilization}{captured} "
            f"account={item['account']} provider_model={item['provider_model']} "
            f"selection={item['provider_model_selection']}"
        )
        if item["provider_model_params"]:
            lines.append(
                "  params="
                + ",".join(f"{key}={value}" for key, value in sorted(item["provider_model_params"].items()))
            )
        for account in item["blocked_accounts"]:
            account_reason = f" reason={account['reason']}" if account["reason"] else ""
            lines.append(
                f"  account {account['name']}: blocked_until={account['blocked_until']}{account_reason}"
            )
    return "\n".join(lines)


def _render_model_usage(config: AgentConfig) -> str:
    try:
        return MemoryStore.load(config.memory_path).model_usage_summary()
    except (OSError, ValueError, TypeError):
        return "Model usage:\n- no model attempts recorded"


def _model_usage_report(config: AgentConfig) -> dict[str, object]:
    try:
        report = MemoryStore.load(config.memory_path).model_usage_stats()
    except (OSError, ValueError, TypeError):
        report = MemoryStore().model_usage_stats()
    return {
        "command": "models usage",
        "schema": json_schema("models usage"),
        "report": report,
        "policy": {
            "routing_budget": "prefer cloud analysis first (cheap/chatgpt/openai/claude); use local only when available and selected from discovered local-model characteristics or as fallback.",
        },
    }


def _render_focus_snapshot(snapshot: dict[str, object]) -> str:
    lines = [
        "Focus snapshot:",
        f"- task: {snapshot['task']}",
        f"- current_step: {snapshot['current_step']}",
        f"- current_step_status: {snapshot['current_step_status']}",
        f"- next_action: {snapshot['next_action']}",
        f"- boundary_decision: {snapshot['boundary_decision']}",
        f"- active_route: provider={snapshot['active_provider'] or 'none'} account={snapshot['active_account']} provider_model={snapshot['active_provider_model'] or 'none'}",
    ]
    params = snapshot.get("active_provider_model_params")
    if isinstance(params, dict) and params:
        lines.append("- active_provider_model_params: " + ",".join(f"{key}={value}" for key, value in sorted(params.items())))
    else:
        lines.append("- active_provider_model_params: none")
    latest_attempt = snapshot.get("latest_model_attempt")
    if isinstance(latest_attempt, dict):
        lines.append(
            f"- latest_model_attempt: step={latest_attempt['step']} action={latest_attempt['action']} "
            f"status={latest_attempt['status']} account={latest_attempt.get('account', 'none')} "
            f"provider_model={latest_attempt['provider_model']} provider={latest_attempt['provider']}"
        )
    else:
        lines.append("- latest_model_attempt: none")
    latest_tool = snapshot.get("latest_tool_evidence")
    if isinstance(latest_tool, dict):
        lines.append(
            f"- latest_tool_evidence: tool={latest_tool['tool']} action={latest_tool['action']} status={latest_tool['status']}"
        )
    else:
        lines.append("- latest_tool_evidence: none")
    active_limit = snapshot.get("active_limit")
    if isinstance(active_limit, dict):
        blocked = f" blocked_until={active_limit['blocked_until']}" if active_limit.get("blocked_until") else ""
        reason = f" reason={active_limit['reason']}" if active_limit.get("reason") else ""
        stale = " stale=true" if active_limit.get("stale") else ""
        lines.append(f"- active_provider_limit: {active_limit['status'] or 'unknown'}{blocked}{reason}{stale}")
    else:
        lines.append("- active_provider_limit: none")
    latest_action = snapshot.get("latest_handoff_action")
    if isinstance(latest_action, dict):
        lines.append(
            f"- latest_handoff_action: phase={latest_action['phase']} task={latest_action['task']} "
            f"summary={latest_action['summary']} git_head={latest_action['git_head'] or 'none'}"
        )
    else:
        lines.append("- latest_handoff_action: none")
    lines.append(f"- resume_ready: {str(bool(snapshot['resume_ready'])).lower()}")
    return "\n".join(lines)


def _agent_baseline_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    catalog = command_catalog()
    available: set[str] = set()
    for item in catalog:
        for value in (item.get("name"), item.get("usage"), *(item.get("aliases", []) if isinstance(item.get("aliases"), list) else [])):
            if value:
                available.add(str(value).split("[", 1)[0].split("<", 1)[0].strip())
                available.add(str(value).strip())
    groups: list[dict[str, object]] = []
    missing_total: list[str] = []
    for group in main.BASELINE_CAPABILITY_GROUPS:
        required = [str(item) for item in group["required_commands"]]
        missing = [item for item in required if item not in available]
        missing_total.extend(f"{group['id']}:{item}" for item in missing)
        groups.append(
            {
                "id": group["id"],
                "source": group["source"],
                "description": group["description"],
                "required_commands": required,
                "missing_commands": missing,
                "status": "ok" if not missing else "missing",
                "remediation": "none" if not missing else main.BASELINE_REMEDIATION_BY_GROUP.get(str(group["id"]), "Restore missing command surfaces."),
            }
        )
    runtime = main.detect_runtime_capabilities(config.workspace_root)
    configured_shell = str(getattr(config, "shell_backend", "auto") or "auto")
    shell_selection = select_shell_backend(configured_shell, detect_runtime_capabilities(config.workspace_root))
    shell = {
        "command": "shell backend",
        "configured": configured_shell,
        "selected": shell_selection["selected"],
        "available": shell_selection["available"],
        "executable": shell_selection["executable"],
        "reason": shell_selection["reason"],
    }
    environment = {
        "git_available": shutil.which("git") is not None,
        "shell_available": bool(shell["available"]),
        "recommended_shell": runtime["recommended_shell"],
        "os_family": runtime["os_family"],
    }
    env_missing = [
        key
        for key, ok in {
            "git_available": environment["git_available"],
            "shell_available": environment["shell_available"],
        }.items()
        if not ok
    ]
    status = "ok" if not missing_total and not env_missing else "warn"
    remediations = [
        {
            "severity": "error",
            "code": f"baseline_{group['id']}",
            "action": group["remediation"],
            "missing_commands": group["missing_commands"],
        }
        for group in groups
        if group["status"] != "ok"
    ]
    if "git_available" in env_missing:
        remediations.append(
            {
                "severity": "error",
                "code": "baseline_git_available",
                "action": "Install Git and ensure `git` is on PATH before running Stagewarden.",
                "missing_commands": [],
            }
        )
    if "shell_available" in env_missing:
        remediations.append(
            {
                "severity": "error",
                "code": "baseline_shell_available",
                "action": "Configure an available shell backend with `/shell backend use <auto|bash|zsh|powershell|cmd>`.",
                "missing_commands": [],
            }
        )
    return {
        "command": "baseline",
        "baseline": "codex_cli+claude_code_minimum",
        "ok": status == "ok",
        "status": status,
        "groups": groups,
        "environment": environment,
        "missing": missing_total + env_missing,
        "remediations": remediations,
        "remediation": "Implement missing command surfaces or fix local prerequisites before claiming Codex/Claude baseline parity." if status != "ok" else "Baseline satisfied.",
    }


def _render_agent_baseline(config: AgentConfig) -> str:
    report = _agent_baseline_report(config)
    lines = [
        "Stagewarden Codex/Claude baseline:",
        f"- status: {report['status']}",
        f"- ok: {str(report['ok']).lower()}",
        f"- os: {report['environment']['os_family']} shell={report['environment']['recommended_shell']}",
        f"- git_available: {str(report['environment']['git_available']).lower()}",
        "Capability groups:",
    ]
    for group in report["groups"]:
        missing = ",".join(group["missing_commands"]) if group["missing_commands"] else "none"
        lines.append(f"- {group['id']}: {group['status']} missing={missing}")
    lines.append(f"Remediation: {report['remediation']}")
    return "\n".join(lines)


def _focus_snapshot(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    handoff = ProjectHandoff.load(config.handoff_path)
    active_model = _selected_model_report(_model_status_report(agent, config))
    latest_attempt = agent.memory.latest_attempt()
    latest_tool = agent.memory.latest_tool_event()
    latest_limit = None
    if active_model:
        prefs = _model_views._load_model_preferences(config)
        latest_limit = dict(prefs.provider_limit_snapshot_by_model or {}).get(str(active_model["provider"]))
    latest_handoff_action = None
    if getattr(handoff, "entries", None):
        latest_entry = handoff.entries[-1]
        latest_handoff_action = {
            "phase": latest_entry.phase,
            "task": latest_entry.task,
            "summary": latest_entry.summary,
            "git_head": latest_entry.git_head,
            "details": dict(latest_entry.details),
        }
    return {
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "session_state": handoff.status or "none",
        "session_recoverable": handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
        "next_action": handoff.rendered_next_action(),
        "boundary_decision": handoff.stage_view()["boundary_decision"],
        "active_provider": None if active_model is None else active_model["provider"],
        "active_provider_model": None if active_model is None else active_model["provider_model"],
        "active_account": "none"
        if active_model is None
        else ((_model_views._load_model_preferences(config).active_account_by_model or {}).get(str(active_model["provider"])) or "none"),
        "active_provider_model_params": {} if active_model is None else dict(active_model["provider_model_params"]),
        "latest_model_attempt": None
        if latest_attempt is None
        else {
            "step": latest_attempt.step_id,
            "action": latest_attempt.action_type,
            "status": "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}",
            "account": latest_attempt.account or "none",
            "provider": latest_attempt.model,
            "provider_model": latest_attempt.variant or "provider-default",
        },
        "latest_tool_evidence": None
        if latest_tool is None
        else {
            "tool": latest_tool.tool,
            "action": latest_tool.action_type,
            "status": "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}",
        },
        "active_limit": None
        if not isinstance(latest_limit, dict)
        else {
            "status": latest_limit.get("status"),
            "reason": latest_limit.get("reason"),
            "blocked_until": latest_limit.get("blocked_until"),
            "stale": bool(latest_limit.get("stale", False)),
        },
        "latest_handoff_action": latest_handoff_action,
        "resume_ready": bool(handoff.task) and handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
    }


def _status_pricing_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    model_report = _model_status_report(agent, config)
    selected = _selected_model_report(model_report)
    analysis_model = main._choose_cloud_priority_model(agent, prefs)
    if isinstance(model_report, dict):
        models = model_report.get("models", [])
        if isinstance(models, list):
            cloud_selected = next(
                (item for item in models if isinstance(item, dict) and item.get("model") == analysis_model),
                None,
            )
            if isinstance(cloud_selected, dict):
                selected = cloud_selected
    catalog = selected.get("catalog", {}) if isinstance(selected, dict) else {}
    pricing_source = None
    if isinstance(catalog, dict):
        pricing_source = catalog.get("pricing_source")
    if pricing_source is None and isinstance(selected, dict):
        pricing_source = selected.get("pricing_source")
    if pricing_source is None and isinstance(selected, dict):
        pricing_source = "local" if selected.get("model") == "local" else "openrouter"
    return {
        "active_model": None
        if selected is None
        else {
            "provider": selected.get("provider"),
            "provider_model": selected.get("provider_model"),
            "catalog_source": selected.get("catalog_source"),
        },
        "source": pricing_source or "unknown",
        "catalog_source": None if not isinstance(catalog, dict) else catalog.get("catalog_source"),
        "cost_per_input_token_usd": None if not isinstance(catalog, dict) else catalog.get("cost_per_input_token_usd"),
        "cost_per_output_token_usd": None if not isinstance(catalog, dict) else catalog.get("cost_per_output_token_usd"),
        "blended_price_usd_per_1m_tokens": None if not isinstance(catalog, dict) else catalog.get("blended_price_usd_per_1m_tokens"),
    }


def _status_cost_sidebar_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    total_input_cost = 0.0
    total_output_cost = 0.0
    total_cost = 0.0
    total_tokens = 0
    cost_nodes: list[dict[str, object]] = []
    for node in nodes:
        input_cost = float(node.get("business_case_input_cost_usd", 0.0) or 0.0)
        output_cost = float(node.get("business_case_output_cost_usd", 0.0) or 0.0)
        node_cost = float(node.get("business_case_cost_usd", input_cost + output_cost) or 0.0)
        total_input_cost += input_cost
        total_output_cost += output_cost
        total_cost += node_cost
        total_tokens += int(node.get("business_case_token_count", 0) or 0)
        cost_nodes.append(
            {
                "node_id": node.get("node_id"),
                "label": node.get("label"),
                "mnemonic": node.get("mnemonic"),
                "team_name": node.get("team_name"),
                "mode": node.get("mode", "manual"),
                "provider": node.get("provider"),
                "provider_model": node.get("provider_model"),
                "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
                "business_case_cost_usd": node_cost,
                "business_case_input_cost_usd": input_cost,
                "business_case_output_cost_usd": output_cost,
            }
        )
    cost_nodes.sort(key=lambda item: float(item.get("business_case_cost_usd", 0.0) or 0.0), reverse=True)
    pricing = _status_pricing_report(agent, config)
    usage = _model_usage_report(config)["report"]
    return {
        "command": "cost",
        "schema": json_schema("status"),
        "business_case": {
            "nodes": len(nodes),
            "tokens": total_tokens,
            "input_cost_usd": round(total_input_cost, 8),
            "output_cost_usd": round(total_output_cost, 8),
            "total_cost_usd": round(total_cost, 8),
        },
        "active_pricing": pricing,
        "model_usage": usage,
        "node_costs": cost_nodes,
        "top_nodes": cost_nodes[:5],
    }


def _render_cost_sidebar(agent: Agent, config: AgentConfig) -> str:
    report = _status_cost_sidebar_report(agent, config)
    business_case = report["business_case"] if isinstance(report.get("business_case"), dict) else {}
    active_pricing = report["active_pricing"] if isinstance(report.get("active_pricing"), dict) else {}
    usage = report["model_usage"] if isinstance(report.get("model_usage"), dict) else {}
    totals = usage.get("totals", {}) if isinstance(usage.get("totals"), dict) else {}
    try:
        failure_rate = float(totals.get("failure_rate", 0) or 0.0)
    except (TypeError, ValueError):
        failure_rate = 0.0
    lines = [
        "Cost sidebar:",
        f"- business_case_nodes: {business_case.get('nodes', 0)}",
        f"- business_case_tokens: {business_case.get('tokens', 0)}",
        f"- business_case_input_cost_usd: {business_case.get('input_cost_usd', 0)}",
        f"- business_case_output_cost_usd: {business_case.get('output_cost_usd', 0)}",
        f"- business_case_total_cost_usd: {business_case.get('total_cost_usd', 0)}",
        (
            "- active_pricing: "
            f"source={active_pricing.get('source', 'unknown')} "
            f"provider={active_pricing.get('active_model', {}).get('provider') if active_pricing.get('active_model') else 'none'} "
            f"provider_model={active_pricing.get('active_model', {}).get('provider_model') if active_pricing.get('active_model') else 'none'} "
            f"input={active_pricing.get('cost_per_input_token_usd', 'none')} "
            f"output={active_pricing.get('cost_per_output_token_usd', 'none')}"
        ),
        (
            "- model_usage: "
            f"calls={totals.get('calls', 0)} failures={totals.get('failures', 0)} "
            f"failure_rate={failure_rate:.2f}%"
        ),
    ]
    top_nodes = [node for node in report.get("top_nodes", []) if isinstance(node, dict)]
    if top_nodes:
        lines.append("- top_cost_nodes:")
        for node in top_nodes:
            lines.append(
                f"  - {node.get('label')} [{node.get('node_id')}]: mnemonic={node.get('mnemonic', 'none')} "
                f"team={node.get('team_name', 'none')} mode={node.get('mode', 'manual')} "
                f"provider={node.get('provider', 'none')} provider_model={node.get('provider_model', 'none')} "
                f"tokens={node.get('business_case_token_count', 0)} "
                f"cost_usd={node.get('business_case_cost_usd', 0)} "
                f"input_cost_usd={node.get('business_case_input_cost_usd', 0)} "
                f"output_cost_usd={node.get('business_case_output_cost_usd', 0)}"
            )
    else:
        lines.append("- top_cost_nodes: none")
    return "\n".join(lines)


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    _model_views._apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    provider_limits = _provider_limit_status_report(agent, config)
    permissions = _permissions_report(config)
    stage_view = handoff.stage_view()
    local_fallback = main._delivery_local_fallback_report(config)
    pricing = _status_pricing_report(agent, config)
    return {
        "command": "status",
        "schema": json_schema("status"),
        "workspace": str(config.workspace_root),
        "mode": mode,
        "files": {
            "memory": config.memory_path.name,
            "trace": config.trace_path.name,
            "handoff": config.handoff_path.name,
            "model_config": config.model_prefs_path.name,
        },
        "models": _model_status_report(agent, config),
        "baseline": _agent_baseline_report(config),
        "goal": handoff.goal_view(),
        "provider_limits": provider_limits,
        "limits_summary": _provider_limit_summary_report(provider_limits),
        "runtime": main.detect_runtime_capabilities(config.workspace_root),
        "shell_backend": {
            "command": "shell backend",
            "configured": str(getattr(config, "shell_backend", "auto") or "auto"),
            "selected": select_shell_backend(str(getattr(config, "shell_backend", "auto") or "auto"), detect_runtime_capabilities(config.workspace_root))["selected"],
            "available": select_shell_backend(str(getattr(config, "shell_backend", "auto") or "auto"), detect_runtime_capabilities(config.workspace_root))["available"],
            "executable": select_shell_backend(str(getattr(config, "shell_backend", "auto") or "auto"), detect_runtime_capabilities(config.workspace_root))["executable"],
            "reason": select_shell_backend(str(getattr(config, "shell_backend", "auto") or "auto"), detect_runtime_capabilities(config.workspace_root))["reason"],
        },
        "focus": _focus_snapshot(agent, config),
        "roles": _roles()._prince2_roles_report(config),
        "permissions": permissions,
        "pricing": pricing,
        "handoff": {
            "summary": handoff.summary(),
            "operational_posture": handoff.rendered_operational_posture(),
            "stage_view": stage_view,
        },
        "local_fallback": local_fallback,
        "remediations": main._status_remediation_report(provider_limits=provider_limits, stage_view=stage_view, config=config),
    }


def _status_dashboard_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    status = _status_report(agent, config)
    provider_limits = status["provider_limits"]
    model_report = status["models"]
    pricing = _status_pricing_report(agent, config)
    handoff = status["handoff"]["stage_view"]
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    workspace_settings = status["permissions"]["effective"]
    active_model = next((item for item in model_report["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in model_report["models"] if item["active"]), None)
    providers = provider_limits["providers"]
    focus = _focus_snapshot(agent, config)
    budget = _project_state_views.budget_report(config)["budget"]
    question = _project_state_views.question_report(config)["user_question"]
    return {
        "command": "status",
        "view": "full",
        "schema": json_schema("status"),
        "identity": {
            "name": "Stagewarden",
            "workspace": status["workspace"],
            "mode": status["mode"],
            "python": platform.python_version(),
        },
        "model": {
            "preferred_model": model_report["preferred_model"] or "automatic",
            "preferred_provider": model_report["preferred_provider"] or "automatic",
            "active_model": None if active_model is None else active_model["model"],
            "active_provider": None if active_model is None else active_model["model"],
            "active_variant": None if active_model is None else active_model["variant"],
            "active_provider_model": None if active_model is None else active_model["provider_model"],
            "active_provider_model_params": {} if active_model is None else active_model["provider_model_params"],
            "enabled": [item["model"] for item in model_report["models"] if item["enabled"]],
            "active": [item["model"] for item in model_report["models"] if item["active"]],
        },
        "account": {
            "active_accounts": {
                item["provider"]: item["active_account"]
                for item in providers
            },
            "auth_modes": {
                item["model"]: item["auth"]
                for item in model_report["models"]
            },
        },
        "limits": [_provider_limit_entry_view(item, include_accounts=True) for item in providers],
        "limits_summary": _provider_limit_summary_report(provider_limits),
        "workspace": {
            "cwd": status["workspace"],
            "files": status["files"],
        },
        "runtime": status["runtime"],
        "shell_backend": status["shell_backend"],
        "permissions": {
            "mode": workspace_settings["mode"],
            "allow": workspace_settings["allow"],
            "ask": workspace_settings["ask"],
            "deny": workspace_settings["deny"],
        },
        "pricing": pricing,
        "cost_sidebar": _status_cost_sidebar_report(agent, config),
        "git": {
            "ok": git_status.ok,
            "head": git_head.stdout.strip() if git_head.ok else None,
            "status": git_status.stdout.strip() if git_status.ok else git_status.error,
        },
        "handoff": {
            "stage_health": handoff["stage_health"],
            "recovery_state": handoff["recovery_state"],
            "boundary_decision": handoff["boundary_decision"],
            "next_action": handoff["next_action"],
            "git_boundary": handoff["git_boundary"],
            "register_statuses": handoff["register_statuses"],
            "backlog_statuses": handoff["backlog_statuses"],
            "node_runtime_summary": handoff["node_runtime_summary"],
        },
        "baseline": status["baseline"],
        "goal": status["goal"],
        "budget": budget,
        "user_question": question,
        "local_fallback": status["local_fallback"],
        "focus": focus,
        "usage": _model_usage_report(config)["report"],
        "quality_gates": {
            "wet_run_required": True,
            "dry_run_valid_checkpoint": False,
            "git_snapshot_required": True,
            "provider_limits_stale_after_minutes": 15,
        },
        "remediations": status["remediations"],
    }


def _render_status(agent: Agent, config: AgentConfig) -> str:
    main = _main()
    _model_views._apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    status = _status_report(agent, config)
    pricing = _status_pricing_report(agent, config)
    lines = [
        "Stagewarden status:",
        f"- workspace: {config.workspace_root}",
        f"- mode: {mode}",
        f"- memory: {config.memory_path.name}",
        f"- trace: {config.trace_path.name}",
        f"- handoff: {config.handoff_path.name}",
        f"- model_config: {config.model_prefs_path.name}",
        _render_agent_baseline(config),
        _render_focus_snapshot(_focus_snapshot(agent, config)),
        _render_model_status(agent, config),
        (
            f"- pricing_source: {pricing['source']} "
            f"provider={pricing['active_model']['provider'] if pricing['active_model'] else 'none'} "
            f"provider_model={pricing['active_model']['provider_model'] if pricing['active_model'] else 'none'} "
            f"input={pricing['cost_per_input_token_usd'] if pricing['cost_per_input_token_usd'] is not None else 'none'} "
            f"output={pricing['cost_per_output_token_usd'] if pricing['cost_per_output_token_usd'] is not None else 'none'}"
        ),
        _render_cost_sidebar(agent, config),
        _render_provider_limit_status(agent, config),
        _render_runtime_status(config),
        _render_shell_backend(config),
        main._render_resume_context(config),
        _project_state_views.render_goal_report(config),
        _project_state_views.render_budget_report(config),
        _project_state_views.render_question_report(config),
        main._render_permissions(config),
        "PRINCE2 roles:",
        _role_tree_views._render_prince2_role_status_hint(config),
        _role_views._render_prince2_roles(config),
        "Handoff summary:",
        handoff.summary(),
        handoff.rendered_operational_posture(),
        "Local fallback readiness:",
        (
            f"- status={status['local_fallback']['status']} "
            f"ready_nodes={status['local_fallback']['delivery_nodes_with_local_fallback']}/{status['local_fallback']['delivery_nodes']} "
            f"candidates={','.join(status['local_fallback']['candidate_ids']) if status['local_fallback']['candidate_ids'] else 'none'}"
        ),
        _render_remediations(status["remediations"]),
    ]
    return "\n".join(lines)


def _render_status_full(agent: Agent, config: AgentConfig) -> str:
    main = _main()
    report = _status_dashboard_report(agent, config)
    model = report["model"] if isinstance(report.get("model"), dict) else {}
    account = report["account"] if isinstance(report.get("account"), dict) else {}
    usage = report["usage"] if isinstance(report.get("usage"), dict) else {}
    cost_sidebar = report["cost_sidebar"] if isinstance(report.get("cost_sidebar"), dict) else {}
    lines = [
        "Stagewarden full status:",
        f"- workspace: {report['identity']['workspace']}",
        f"- mode: {report['identity']['mode']}",
        f"- python: {report['identity']['python']}",
        (
            f"- model: preferred={model.get('preferred_model', 'automatic')} "
            f"active={model.get('active_model', 'none')} "
            f"variant={model.get('active_variant', 'none')} "
            f"provider_model={model.get('active_provider_model', 'none')}"
        ),
        (
            f"- account: active={account.get('active_accounts', {})} "
            f"auth_modes={account.get('auth_modes', {})}"
        ),
        (
            "- limits_summary: "
            f"blocked_models={','.join(report['limits_summary'].get('blocked_models', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('blocked_models') else 'none'} "
            f"stale_models={','.join(report['limits_summary'].get('stale_models', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('stale_models') else 'none'} "
            f"blocked_accounts={','.join(report['limits_summary'].get('blocked_accounts', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('blocked_accounts') else 'none'} "
            f"stale_accounts={','.join(report['limits_summary'].get('stale_accounts', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('stale_accounts') else 'none'}"
        ),
        f"- pricing_source: {report['pricing']['source'] if isinstance(report.get('pricing'), dict) else 'unknown'}",
        f"- budget: {report['budget']}",
        f"- goal: {report['goal']}",
        f"- user_question: {report['user_question']}",
        f"- git_head: {report['git']['head'] if isinstance(report.get('git'), dict) else 'unknown'}",
        f"- usage_calls: {usage.get('calls', 0)}",
        f"- usage_failures: {usage.get('failures', 0)}",
    ]
    if cost_sidebar:
        lines.append(
            f"- cost_sidebar: nodes={cost_sidebar.get('business_case', {}).get('nodes', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0} "
            f"tokens={cost_sidebar.get('business_case', {}).get('tokens', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0} "
            f"total_cost_usd={cost_sidebar.get('business_case', {}).get('total_cost_usd', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0}"
        )
        lines.append("Node cost breakdown:")
        for line in _render_cost_sidebar(agent, config).splitlines():
            lines.append(f"  {line}")
    lines.append(f"- quality_gates: {report['quality_gates']}")
    lines.append("Remediations:")
    lines.extend(_render_remediations(report["remediations"]).splitlines()[1:])
    return "\n".join(lines)


def _render_remediations(remediations: object) -> str:
    lines = ["Remediations:"]
    if isinstance(remediations, list) and remediations:
        for item in remediations:
            if isinstance(item, dict):
                lines.append(f"- {item.get('severity', 'info')} {item.get('code', 'unknown')}: {item.get('action', '')}")
        return "\n".join(lines)
    lines.append("- none")
    return "\n".join(lines)


def _render_overview(agent: Agent, config: AgentConfig) -> str:
    board = _board_report(config)
    usage = _model_usage_report(config)["report"]
    transcript = _transcript_report(config)["report"]
    status = _status_report(agent, config)
    lines = [
        "Workspace overview:",
        f"- workspace: {status['workspace']}",
        f"- mode: {status['mode']}",
        f"- recommended_authorization: {board['recommended_authorization']}",
        f"- boundary_decision: {board['boundary_decision']}",
        f"- open_issues: {board['open_issues']}",
        f"- open_risks: {board['open_risks']}",
        f"- quality_open: {board['quality_open']}",
        f"- recovery_state: {board['recovery_state']}",
        f"- model_calls: {usage['totals']['calls']}",
        f"- model_failures: {usage['totals']['failures']}",
        f"- escalation_path: {usage['totals']['escalation_path']}",
        f"- provider_limits: {_provider_limit_summary(agent, config)}",
        f"- transcript_entries: {transcript['count']}",
    ]
    return "\n".join(lines)


def _render_health(agent: Agent, config: AgentConfig) -> str:
    report = _health_report(agent, config)
    log_errors = report.get("log_errors", {}) if isinstance(report.get("log_errors"), dict) else {}
    lines = [
        "Health check:",
        f"- workspace: {report['workspace']}",
        f"- mode: {report['mode']}",
        f"- ready: {str(report['ready']).lower()}",
        f"- recommended_authorization: {report['recommended_authorization']}",
        f"- boundary_decision: {report['boundary_decision']}",
        f"- open_issues: {report['open_issues']}",
        f"- open_risks: {report['open_risks']}",
        f"- quality_open: {report['quality_open']}",
        f"- recovery_state: {report['recovery_state']}",
        f"- next_action: {report['next_action']}",
        f"- model_failures: {report['model_failures']}",
        f"- model_calls: {report['model_calls']}",
        f"- transcript_entries: {report['transcript_entries']}",
        f"- log_errors: {log_errors.get('status', 'unknown')} count={log_errors.get('count', 0)}",
    ]
    return "\n".join(lines)


def _statusline_rate_limit(item: dict[str, object]) -> dict[str, object]:
    entry = _provider_limit_entry_view(item, include_accounts=False)
    return {
        "provider": entry["provider"],
        "account": entry["account"],
        "status": entry["status"],
        "blocked_until": entry["blocked_until"],
        "reason": entry["reason"],
        "rate_limit_type": entry["rate_limit_type"],
        "stale": entry["stale"],
        "blocked_accounts": entry["blocked_accounts_count"],
        "used_percentage": entry["utilization"],
        "utilization": entry["utilization"],
        "resets_at": entry["resets_at"],
        "overage_status": entry["overage_status"],
        "overage_resets_at": entry["overage_resets_at"],
        "overage_disabled_reason": entry["overage_disabled_reason"],
    }


def _statusline_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
    memory = MemoryStore.load(config.memory_path)
    git = GitTool(config)
    git_head = git.head()
    provider_limits = status["provider_limits"]["providers"]
    preferred = status["models"]["preferred_model"]
    active_model = next((item for item in status["models"]["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in status["models"]["models"] if item["active"]), None)
    return {
        "command": "statusline",
        "schema": json_schema("statusline"),
        "workspace": {
            "current_dir": status["workspace"],
            "project_dir": status["workspace"],
            "added_dirs": [],
            "git_head": git_head.stdout.strip() if git_head.ok else None,
            "git_worktree": None,
        },
        "version": "stagewarden",
        "model": {
            "preferred": preferred or "automatic",
            "preferred_provider": preferred or "automatic",
            "active": None if active_model is None else active_model["model"],
            "active_provider": None if active_model is None else active_model["model"],
            "variant": None if active_model is None else active_model["variant"],
            "provider_model": None if active_model is None else active_model["provider_model"],
            "provider_model_selection": None if active_model is None else active_model["provider_model_selection"],
            "provider_model_params": {} if active_model is None else active_model["provider_model_params"],
        },
        "context_window": memory.context_window_stats(),
        "rate_limits": [_statusline_rate_limit(item) for item in provider_limits],
        "rate_limits_summary": _provider_limit_summary_report(status["provider_limits"]),
        "baseline": {
            "status": status["baseline"]["status"],
            "ok": status["baseline"]["ok"],
            "missing": status["baseline"]["missing"],
        },
        "local_fallback": status["local_fallback"],
        "goal": status["goal"],
        "handoff": status["handoff"]["stage_view"],
        "latest_handoff_action": status["focus"].get("latest_handoff_action"),
        "usage": usage["totals"],
    }


def _overview_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    return {
        "command": "overview",
        "schema": json_schema("overview"),
        "status": _status_report(agent, config),
        "board": main._board_report(config),
        "model_usage": _model_usage_report(config),
        "provider_limits": _provider_limit_status_report(agent, config),
        "transcript": main._transcript_report(config),
        "handoff": main._handoff_report(config),
    }


def _health_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    board = main._board_report(config)
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
    transcript = main._transcript_report(config)["report"]
    log_errors = main._log_error_report(config)
    ready = (
        board["recommended_authorization"] in {"continue", "close"}
        and board["open_issues"] == 0
        and board["recovery_state"] == "none"
        and log_errors["count"] == 0
    )
    return {
        "command": "health",
        "schema": json_schema("health"),
        "workspace": status["workspace"],
        "mode": status["mode"],
        "ready": ready,
        "recommended_authorization": board["recommended_authorization"],
        "boundary_decision": board["boundary_decision"],
        "open_issues": board["open_issues"],
        "open_risks": board["open_risks"],
        "quality_open": board["quality_open"],
        "recovery_state": board["recovery_state"],
        "next_action": board["next_action"],
        "model_failures": usage["totals"]["failures"],
        "model_calls": usage["totals"]["calls"],
        "transcript_entries": transcript["count"],
        "log_errors": log_errors,
    }


def _preflight_remediations(
    *,
    doctor: dict[str, object],
    runtime: dict[str, object],
    shell_backend: dict[str, object],
    git_status: object,
    git_dirty: object,
    role_check: dict[str, object],
    provider_limits: dict[str, object],
    sources: dict[str, object],
    stage_view: dict[str, object],
    log_errors: dict[str, object],
) -> list[dict[str, str]]:
    main = _main()
    items: list[dict[str, str]] = []
    if not doctor.get("python", {}).get("ok"):  # type: ignore[union-attr]
        items.append({"severity": "blocker", "code": "python", "action": "Install Python 3.11+ and rerun `/preflight`."})
    if not doctor.get("git", {}).get("ok"):  # type: ignore[union-attr]
        items.append({"severity": "blocker", "code": "git", "action": "Install git; Stagewarden requires git for every project."})
    if not shell_backend.get("available"):
        items.append({"severity": "blocker", "code": "shell_backend", "action": "Choose an available backend with `/shell backend use <auto|bash|zsh|powershell|cmd>`."})
    runtime_shells = runtime.get("shells", {}) if isinstance(runtime, dict) else {}
    bash_info = runtime_shells.get("bash", {}) if isinstance(runtime_shells, dict) else {}
    if runtime.get("os_family") == "windows" and not bash_info.get("available"):
        items.append(
            {
                "severity": "warning",
                "code": "windows_shell_readiness",
                "action": "Bash is not available on this Windows runtime; bash-required or POSIX-only commands will be rejected unless you install bash or translate them.",
            }
        )
    if not role_check.get("ok"):
        items.append(
            {
                "severity": "blocker",
                "code": "roles",
                "action": "Run `/roles setup` or `/roles propose` and approve the baseline before role-routed work.",
            }
        )
    if not sources.get("ok"):
        items.append(
            {
                "severity": "warning",
                "code": "sources",
                "action": "Run `/sources status` and refresh any missing source references before source-derived implementation work.",
            }
        )
    if log_errors.get("count", 0) > 0:
        items.append(
            {
                "severity": "blocker",
                "code": "log_errors",
                "action": f"Recent logs contain {log_errors.get('count', 0)} error entry(s). Inspect `/transcript` and the memory log, then rerun the battery/preflight check.",
            }
        )
    if getattr(git_dirty, "ok", False) and str(getattr(git_dirty, "stdout", "")).strip():
        items.append(
            {
                "severity": "warning",
                "code": "dirty_git",
                "action": "Run `/git status` and clear or commit the dirty workspace before relying on the current handoff.",
            }
        )
    if provider_limits.get("providers"):
        for item in provider_limits.get("providers", []):
            if not isinstance(item, dict) or not item.get("blocked_until"):
                continue
            items.append(
                {
                    "severity": "warning",
                    "code": f"provider_{item.get('provider')}",
                    "action": f"Provider {item.get('provider')} is blocked until {item.get('blocked_until')}; prefer a different provider or wait for the reset.",
                }
            )
    provider_limit_summary = _provider_limit_summary_report(provider_limits)
    if provider_limit_summary["blocked_models"] or provider_limit_summary["stale_models"]:
        items.append(
            {
                "severity": "warning",
                "code": "provider_limits",
                "action": "Run `/model limits` and `/model use <provider>` to inspect blocked or stale provider snapshots before relying on provider availability.",
            }
        )
    if provider_limit_summary["stale_models"]:
        items.append(
            {
                "severity": "warning",
                "code": "provider_limits_stale",
                "action": "Refresh provider limit snapshots before relying on provider availability decisions.",
            }
        )
    if stage_view.get("recovery_state") not in {None, "", "none"}:
        items.append(
            {
                "severity": "warning",
                "code": "recovery",
                "action": "Run `/exception` to review the recovery plan and clear the active recovery state before continuing.",
            }
        )
    if stage_view.get("boundary_decision") in {"review_boundary:no_plan_status", "review_boundary:incomplete"}:
        items.append(
            {
                "severity": "warning",
                "code": "handoff_boundary",
                "action": "The current handoff boundary still needs review. Confirm the current stage and plan status before advancing.",
            }
        )
    if not items:
        items.append({"severity": "info", "code": "ready", "action": "All preflight checks passed."})
    return items


def _status_remediation_report(
    *,
    provider_limits: dict[str, object],
    stage_view: dict[str, object],
    config: AgentConfig,
) -> list[dict[str, str]]:
    main = _main()
    git = GitTool(config)
    git_status = git.status()
    git_dirty = git.status_porcelain()
    items = _preflight_remediations(
        doctor={"python": {"ok": True}, "git": {"ok": True}},
        runtime=main.detect_runtime_capabilities(config.workspace_root),
        shell_backend=_shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=_role_tree_views._prince2_role_check_report(config),
        provider_limits=provider_limits,
        sources=main._sources_status_report(config),
        stage_view=stage_view,
        log_errors=main._log_error_report(config),
    )
    local_fallback = main._delivery_local_fallback_report(config)
    if local_fallback["status"] == "available":
        items.append(
            {
                "severity": "warning",
                "code": "local_fallback_partial",
                "action": (
                    "Discovered local fallback candidates exist but are not preloaded on every delivery node. "
                    "Run `/roles setup`, `/role assign`, or `/project start` to preload the recommended local fallback routes."
                ),
            }
        )
    elif local_fallback["status"] == "missing" and int(local_fallback.get("delivery_nodes", 0) or 0) > 0:
        items.append(
            {
                "severity": "info",
                "code": "local_fallback_missing",
                "action": (
                    "No local fallback candidates are available for the current delivery nodes. "
                    "Continue on cloud providers or start Ollama and rerun discovery before planning local fallback execution."
                ),
            }
        )
    return items


def _preflight_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    doctor = _doctor_report(config)
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    git_dirty = git.status_porcelain()
    role_check = _role_tree_views._prince2_role_check_report(config)
    provider_limits = _provider_limit_status_report(agent, config)
    sources = main._sources_status_report(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    log_errors = main._log_error_report(config)
    stage_view = handoff.stage_view()
    remediations = _preflight_remediations(
        doctor=doctor,
        runtime=doctor["runtime"],
        shell_backend=_shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=role_check,
        provider_limits=provider_limits,
        sources=sources,
        stage_view=stage_view,
        log_errors=log_errors,
    )
    ready = not any(item["severity"] == "blocker" for item in remediations) and log_errors["count"] == 0
    return {
        "command": "preflight",
        "schema": json_schema("preflight"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ready": ready,
        "doctor": doctor,
        "runtime": doctor["runtime"],
        "shell_backend": _shell_backend_report(config),
        "git": {
            "ok": git_status.ok,
            "head": git_head.stdout.strip() if git_head.ok else None,
            "status": git_status.stdout.strip() if git_status.ok else git_status.error,
            "dirty": bool(git_dirty.ok and git_dirty.stdout.strip()),
            "dirty_paths": git_dirty.stdout.splitlines() if git_dirty.ok and git_dirty.stdout else [],
        },
        "roles_check": role_check,
        "provider_limits": provider_limits,
        "baseline": _agent_baseline_report(config),
        "sources": sources,
        "permissions": _permissions_report(config),
        "handoff": {
            "summary": handoff.summary(),
            "stage_view": stage_view,
        },
        "log_errors": log_errors,
        "remediations": remediations,
    }


def _report_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    handoff = ProjectHandoff.load(config.handoff_path)
    board = main._board_report(config)
    usage = _model_usage_report(config)["report"]
    transcript = main._transcript_report(config)["report"]
    stage_view = handoff.stage_view()
    register_statuses = stage_view["register_statuses"]
    governance_status = (
        "clean"
        if register_statuses["issues_open"] == 0
        and register_statuses["risks_open"] == 0
        and register_statuses["quality_open"] == 0
        else "residual_controls"
    )
    lessons = [
        f"[{item.get('type', 'lesson')}] {item.get('step_id', '-')} :: {item.get('lesson', '')}"
        for item in handoff.lessons_log[-3:]
    ]
    backlog = [
        f"[{str(item.get('status', 'planned')).strip().lower() or 'planned'}] {item.get('step_id', '-')} :: {item.get('title', '')}"
        for item in handoff.implementation_backlog[:5]
    ]
    return {
        "command": "report",
        "schema": json_schema("report"),
        "task": handoff.task or "unknown",
        "project_status": handoff.status,
        "current_step": handoff.current_step_id or "none",
        "stage_health": stage_view["stage_health"],
        "recommended_authorization": board["recommended_authorization"],
        "boundary_decision": board["boundary_decision"],
        "next_action": board["next_action"],
        "open_issues": board["open_issues"],
        "open_risks": board["open_risks"],
        "quality_open": board["quality_open"],
        "recovery_state": board["recovery_state"],
        "governance_status": governance_status,
        "model_calls": usage["totals"]["calls"],
        "model_failures": usage["totals"]["failures"],
        "escalation_path": usage["totals"]["escalation_path"],
        "provider_limits": _provider_limit_status_report(agent, config),
        "transcript_entries": transcript["count"],
        "recent_lessons": lessons,
        "backlog_preview": backlog,
    }


def _doctor_report(config: AgentConfig) -> dict[str, object]:
    python_ok = sys.version_info >= (3, 11)
    report: dict[str, object] = {
        "command": "doctor",
        "schema": json_schema("doctor"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": {
            "ok": python_ok,
            "status": "OK" if python_ok else "FAIL",
            "version": platform.python_version(),
            "required": ">=3.11",
            "executable": sys.executable,
        },
        "git": {},
        "path_launcher": {},
        "repository": {},
        "runtime": _main().detect_runtime_capabilities(config.workspace_root),
        "baseline": _main()._agent_baseline_report(config),
        "providers": [],
        "policy": {
            "silent_install": False,
            "note": "no prerequisites are installed silently by doctor.",
        },
    }

    git_path = shutil.which("git")
    if git_path:
        git_available = GitTool(config).ensure_available()
        if git_available.ok:
            version = git_available.stdout.strip() or "git available"
            report["git"] = {
                "ok": True,
                "status": "OK",
                "message": version,
                "path": git_path,
            }
        else:
            report["git"] = {
                "ok": False,
                "status": "FAIL",
                "message": git_available.error or "git is not usable",
                "path": git_path,
            }
    else:
        report["git"] = {
            "ok": False,
            "status": "FAIL",
            "message": "git executable not found in PATH. Install git before running Stagewarden.",
            "path": None,
        }

    launcher = shutil.which("stagewarden")
    if launcher:
        report["path_launcher"] = {
            "ok": True,
            "status": "OK",
            "path": launcher,
            "message": launcher,
        }
    else:
        report["path_launcher"] = {
            "ok": False,
            "status": "WARN",
            "path": None,
            "message": "`stagewarden` not found in PATH; run setup.sh/setup.ps1 or use python -m stagewarden.main.",
        }

    repo_probe = GitTool(config)._run(["git", "rev-parse", "--is-inside-work-tree"])
    if repo_probe.ok and repo_probe.stdout.strip() == "true":
        report["repository"] = {
            "ok": True,
            "status": "OK",
            "message": "current workspace is a git worktree",
        }
    else:
        report["repository"] = {
            "ok": False,
            "status": "WARN",
            "message": "current workspace is not a git worktree; Stagewarden will initialize one during normal agent startup.",
        }

    providers: list[dict[str, object]] = []
    main = _main()
    for model in main.REGISTRY_MODELS:
        capability = main.provider_capability(model)
        token_state = "n/a"
        if capability.token_env:
            token_state = "set" if os.environ.get(capability.token_env) else f"missing:{capability.token_env}"
        providers.append(
            {
                "provider": model,
                "auth": capability.auth_type,
                "profiles": capability.supports_account_profiles,
                "browser_login": capability.supports_browser_login,
                "api_key": capability.supports_api_key,
                "token_env": token_state,
                "default_model": capability.default_model,
            }
        )
    report["providers"] = providers
    return report


def _doctor_ok(rendered: str) -> bool:
    return "\n- Python: FAIL" not in rendered and "\n- Git: FAIL" not in rendered


def _render_preflight(agent: Agent, config: AgentConfig) -> str:
    report = _preflight_report(agent, config)
    lines = [
        "Stagewarden preflight:",
        f"- ready: {str(report['ready']).lower()}",
        f"- log_errors: {report['log_errors']['status']} count={report['log_errors']['count']}",
        "Remediations:",
    ]
    if report["remediations"]:
        for item in report["remediations"]:
            lines.append(f"- {item['severity']} {item['code']}: {item['action']}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _render_report(agent: Agent, config: AgentConfig) -> str:
    report = _report_report(agent, config)
    lines = [
        "Project report:",
        f"- task: {report['task']}",
        f"- project_status: {report['project_status']}",
        f"- current_step: {report['current_step']}",
        f"- stage_health: {report['stage_health']}",
        f"- governance_status: {report['governance_status']}",
        f"- recommended_authorization: {report['recommended_authorization']}",
        f"- boundary_decision: {report['boundary_decision']}",
        f"- next_action: {report['next_action']}",
        f"- open_issues: {report['open_issues']}",
        f"- open_risks: {report['open_risks']}",
        f"- quality_open: {report['quality_open']}",
        f"- recovery_state: {report['recovery_state']}",
        f"- model_calls: {report['model_calls']}",
        f"- model_failures: {report['model_failures']}",
        f"- escalation_path: {report['escalation_path']}",
        f"- provider_limits: {_provider_limit_summary(agent, config)}",
        f"- transcript_entries: {report['transcript_entries']}",
        "Recent lessons:",
    ]
    if report["recent_lessons"]:
        for item in report["recent_lessons"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("Backlog preview:")
    if report["backlog_preview"]:
        for item in report["backlog_preview"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _render_doctor(config: AgentConfig) -> str:
    report = _doctor_report(config)
    python_info = report["python"]
    git_info = report["git"]
    path_info = report["path_launcher"]
    repo_info = report["repository"]
    runtime_info = report["runtime"]
    shell_backend = _shell_backend_report(config)
    providers = report["providers"]
    policy_info = report["policy"]
    baseline_info = report["baseline"]
    lines = ["Stagewarden doctor:"]
    lines.append(
        f"- Python: {python_info['status']} {python_info['version']} "
        f"(required {python_info['required']}, executable={python_info['executable']})"
    )
    if git_info.get("ok"):
        lines.append(f"- Git: OK {git_info['message']} ({git_info['path']})")
    else:
        lines.append(f"- Git: FAIL {git_info['message']}")
    if path_info.get("ok"):
        lines.append(f"- PATH launcher: OK {path_info['message']}")
    else:
        lines.append(f"- PATH launcher: WARN {path_info['message']}")
    lines.append(f"- Repository: {repo_info['status']} {repo_info['message']}")
    lines.append(
        f"- Runtime: os={runtime_info['os_family']} shell={runtime_info['recommended_shell']} "
        f"default={runtime_info['default_shell'] or 'none'} line_ending={runtime_info['line_ending']}"
    )
    lines.append(
        f"- Shell backend: configured={shell_backend['configured']} selected={shell_backend['selected'] or 'none'} "
        f"available={str(shell_backend['available']).lower()}"
    )
    lines.append(
        f"- Baseline: {baseline_info['status']} "
        f"missing={len(baseline_info['missing'])} groups={len(baseline_info['groups'])}"
    )
    if baseline_info["remediations"]:
        lines.append("Baseline remediations:")
        for item in baseline_info["remediations"]:
            lines.append(f"- {item['code']}: {item['action']}")
    lines.append("Provider capabilities:")
    for provider in providers:
        lines.append(
            f"- {provider['provider']}: auth={provider['auth']} profiles={'yes' if provider['profiles'] else 'no'} "
            f"browser_login={'yes' if provider['browser_login'] else 'no'} api_key={'yes' if provider['api_key'] else 'no'} "
            f"token_env={provider['token_env']} default_model={provider['default_model']}"
        )
    lines.append(f"- Policy: {policy_info['note']}")
    return "\n".join(lines)
