from __future__ import annotations

import platform
import os
import shutil
import subprocess
import sys
from datetime import datetime

from .agent import Agent
from .config import AgentConfig
from .json_schema_registry import json_schema
from .memory import MemoryStore
from .project_handoff import ProjectHandoff
from .tools.git import GitTool


def _views():
    from . import status_views as _status_views_module

    return _status_views_module


def _main():
    from . import main as _main_module

    return _main_module


def _statusline_rate_limit(item: dict[str, object]) -> dict[str, object]:
    entry = _views()._provider_limit_entry_view(item, include_accounts=False)
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
    views = _views()
    status = views._status_report(agent, config)
    usage = views._model_usage_report(config)["report"]
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
        "rate_limits_summary": views._provider_limit_summary_report(status["provider_limits"]),
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
    views = _views()
    return {
        "command": "overview",
        "schema": json_schema("overview"),
        "status": views._status_report(agent, config),
        "board": main._board_report(config),
        "model_usage": views._model_usage_report(config),
        "provider_limits": views._provider_limit_status_report(agent, config),
        "transcript": main._transcript_report(config),
        "handoff": main._handoff_report(config),
    }


def _health_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    views = _views()
    board = main._board_report(config)
    status = views._status_report(agent, config)
    usage = views._model_usage_report(config)["report"]
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
    views = _views()
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
        items.append({"severity": "blocker", "code": "roles", "action": "Run `/roles setup` or `/roles propose` and approve the baseline before role-routed work."})
    if not sources.get("ok"):
        items.append({"severity": "warning", "code": "sources", "action": "Run `/sources status` and refresh any missing source references before source-derived implementation work."})
    if log_errors.get("count", 0) > 0:
        items.append(
            {
                "severity": "blocker",
                "code": "log_errors",
                "action": f"Recent logs contain {log_errors.get('count', 0)} error entry(s). Inspect `/transcript` and the memory log, then rerun the battery/preflight check.",
            }
        )
    if getattr(git_dirty, "ok", False) and str(getattr(git_dirty, "stdout", "")).strip():
        items.append({"severity": "warning", "code": "dirty_git", "action": "Run `/git status` and clear or commit the dirty workspace before relying on the current handoff."})
    if provider_limits.get("providers"):
        for item in provider_limits.get("providers", []):
            if not isinstance(item, dict) or not item.get("blocked_until"):
                continue
            items.append({"severity": "warning", "code": f"provider_{item.get('provider')}", "action": f"Provider {item.get('provider')} is blocked until {item.get('blocked_until')}; prefer a different provider or wait for the reset."})
    provider_limit_summary = views._provider_limit_summary_report(provider_limits)
    if provider_limit_summary["blocked_models"] or provider_limit_summary["stale_models"]:
        items.append({"severity": "warning", "code": "provider_limits", "action": "Run `/model limits` and `/model use <provider>` to inspect blocked or stale provider snapshots before relying on provider availability."})
    if provider_limit_summary["stale_models"]:
        items.append({"severity": "warning", "code": "provider_limits_stale", "action": "Refresh provider limit snapshots before relying on provider availability decisions."})
    if stage_view.get("recovery_state") not in {None, "", "none"}:
        items.append({"severity": "warning", "code": "recovery", "action": "Run `/exception` to review the recovery plan and clear the active recovery state before continuing."})
    if stage_view.get("boundary_decision") in {"review_boundary:no_plan_status", "review_boundary:incomplete"}:
        items.append({"severity": "warning", "code": "handoff_boundary", "action": "The current handoff boundary still needs review. Confirm the current stage and plan status before advancing."})
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
        shell_backend=main._shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=main._prince2_role_check_report(config),
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
    views = _views()
    doctor = _doctor_report(config)
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    git_dirty = git.status_porcelain()
    role_check = main._prince2_role_check_report(config)
    provider_limits = views._provider_limit_status_report(agent, config)
    sources = main._sources_status_report(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    log_errors = main._log_error_report(config)
    stage_view = handoff.stage_view()
    remediations = _preflight_remediations(
        doctor=doctor,
        runtime=doctor["runtime"],
        shell_backend=main._shell_backend_report(config),
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
        "shell_backend": main._shell_backend_report(config),
        "git": {
            "ok": git_status.ok,
            "head": git_head.stdout.strip() if git_head.ok else None,
            "status": git_status.stdout.strip() if git_status.ok else git_status.error,
            "dirty": bool(git_dirty.ok and git_dirty.stdout.strip()),
            "dirty_paths": git_dirty.stdout.splitlines() if git_dirty.ok and git_dirty.stdout else [],
        },
        "roles_check": role_check,
        "provider_limits": provider_limits,
        "baseline": main._agent_baseline_report(config),
        "sources": sources,
        "permissions": views._permissions_report(config),
        "handoff": {
            "summary": handoff.summary(),
            "stage_view": stage_view,
        },
        "log_errors": log_errors,
        "remediations": remediations,
    }


def _report_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    views = _views()
    handoff = ProjectHandoff.load(config.handoff_path)
    board = main._board_report(config)
    usage = views._model_usage_report(config)["report"]
    transcript = main._transcript_report(config)["report"]
    stage_view = handoff.stage_view()
    register_statuses = stage_view["register_statuses"]
    governance_status = (
        "clean"
        if register_statuses["issues_open"] == 0 and register_statuses["risks_open"] == 0 and register_statuses["quality_open"] == 0
        else "residual_controls"
    )
    lessons = [f"[{item.get('type', 'lesson')}] {item.get('step_id', '-')} :: {item.get('lesson', '')}" for item in handoff.lessons_log[-3:]]
    backlog = [f"[{str(item.get('status', 'planned')).strip().lower() or 'planned'}] {item.get('step_id', '-')} :: {item.get('title', '')}" for item in handoff.implementation_backlog[:5]]
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
        "provider_limits": views._provider_limit_status_report(agent, config),
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
        "python": {"ok": python_ok, "status": "OK" if python_ok else "FAIL", "version": platform.python_version(), "required": ">=3.11", "executable": sys.executable},
        "git": {},
        "path_launcher": {},
        "repository": {},
        "runtime": _main().detect_runtime_capabilities(config.workspace_root),
        "baseline": _main()._agent_baseline_report(config),
        "providers": [],
        "policy": {"silent_install": False, "note": "no prerequisites are installed silently by doctor."},
    }
    git_path = shutil.which("git")
    if git_path:
        git_available = GitTool(config).ensure_available()
        report["git"] = {"ok": git_available.ok, "status": "OK" if git_available.ok else "FAIL", "message": git_available.stdout.strip() or git_available.error or "git available", "path": git_path}
    else:
        report["git"] = {"ok": False, "status": "FAIL", "message": "git executable not found in PATH. Install git before running Stagewarden.", "path": None}
    launcher = shutil.which("stagewarden")
    report["path_launcher"] = {"ok": bool(launcher), "status": "OK" if launcher else "WARN", "path": launcher, "message": launcher or "`stagewarden` not found in PATH; run setup.sh/setup.ps1 or use python -m stagewarden.main."}
    repo_probe = GitTool(config)._run(["git", "rev-parse", "--is-inside-work-tree"])
    report["repository"] = {"ok": repo_probe.ok and repo_probe.stdout.strip() == "true", "status": "OK" if repo_probe.ok and repo_probe.stdout.strip() == "true" else "WARN", "message": "current workspace is a git worktree" if repo_probe.ok and repo_probe.stdout.strip() == "true" else "current workspace is not a git worktree; Stagewarden will initialize one during normal agent startup."}
    providers: list[dict[str, object]] = []
    main = _main()
    for model in main.REGISTRY_MODELS:
        capability = main.provider_capability(model)
        token_state = "n/a"
        if capability.token_env:
            token_state = "set" if os.environ.get(capability.token_env) else f"missing:{capability.token_env}"
        providers.append({"provider": model, "auth": capability.auth_type, "profiles": capability.supports_account_profiles, "browser_login": capability.supports_browser_login, "api_key": capability.supports_api_key, "token_env": token_state, "default_model": capability.default_model})
    report["providers"] = providers
    return report


def _doctor_ok(rendered: str) -> bool:
    return "\n- Python: FAIL" not in rendered and "\n- Git: FAIL" not in rendered


def _render_preflight(agent: Agent, config: AgentConfig) -> str:
    report = _preflight_report(agent, config)
    lines = ["Stagewarden preflight:", f"- ready: {str(report['ready']).lower()}", f"- log_errors: {report['log_errors']['status']} count={report['log_errors']['count']}", "Remediations:"]
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
        f"- provider_limits: {_main()._provider_limit_summary(agent, config)}",
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
    shell_backend = _main()._shell_backend_report(config)
    providers = report["providers"]
    lines = [
        "Doctor:",
        f"- Python: {python_info['status']} {python_info['version']}",
        f"- Git: {git_info['status']} {git_info.get('message', '')}",
        f"- Path launcher: {path_info['status']} {path_info.get('message', '')}",
        f"- Repository: {repo_info['status']} {repo_info.get('message', '')}",
        f"- Runtime: {runtime_info['os_family']} / {runtime_info['recommended_shell']}",
        f"- Shell backend: {shell_backend['selected'] or 'none'}",
        "Providers:",
    ]
    for item in providers:
        lines.append(
            f"- {item['provider']}: auth={item['auth']} profiles={str(item['profiles']).lower()} browser_login={str(item['browser_login']).lower()} api_key={str(item['api_key']).lower()} token_env={item['token_env']} default={item['default_model']}"
        )
    return "\n".join(lines)
