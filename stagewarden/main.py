from __future__ import annotations

import argparse
import atexit
import copy
from dataclasses import replace
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

try:
    import readline
except ImportError:  # pragma: no cover - platform dependent
    readline = None

from .agent import Agent
from .auth import CodexBrowserLoginFlow, CodexBrowserLogoutFlow, OpenAIDeviceCodeFlow
from .executor import ALLOWED_MODEL_ACTIONS
from .commands import (
    command_catalog,
    command_phrases,
    command_specs_by_query,
    help_topic_catalog,
    help_topic_lines,
    help_topic_report,
    render_command_catalog,
)
from .config import AgentConfig
from .extensions import discover_extensions, scaffold_extension
from .handoff import MODEL_BACKENDS, MODEL_VARIANT_CATALOG, available_model_variants, canonicalize_model_variant, format_run_model
from .ljson import LJSONOptions, benchmark_sizes, decode, dump_file, encode, load_file
from .memory import MemoryStore
from .modelprefs import (
    ModelPreferences,
    PRINCE2_ROLE_IDS,
    PRINCE2_ROLE_LABELS,
    SUPPORTED_MODELS,
    account_key,
    classify_limit_reason,
    extract_blocked_until,
    limit_snapshot_from_message,
)
from .permissions import PermissionPolicy, PermissionSettings, VALID_PERMISSION_MODES
from .provider_registry import (
    SUPPORTED_MODELS as REGISTRY_MODELS,
    provider_capability,
    provider_model_preset,
    provider_model_spec,
    provider_model_specs,
)
from .role_tree import (
    ROLE_CONTEXT_RULES,
    build_prince2_role_flow,
    build_prince2_role_matrix,
    build_prince2_role_matrix_payload,
    build_prince2_role_tree,
    check_prince2_role_tree,
    check_prince2_role_tree_payload,
    render_prince2_role_check,
    render_prince2_role_flow,
    render_prince2_role_matrix,
    render_prince2_role_tree,
)
from .project_handoff import HandoffEntry, ProjectHandoff
from .roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS
from .runtime_env import detect_runtime_capabilities, select_shell_backend
from .secrets import SecretStore
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8
from .tools.files import FileTool
from .tools.git import GitTool
from .tools.external_io import ExternalIOResult, ExternalIOTool


INTERACTIVE_COMMAND_PHRASES: tuple[str, ...] = tuple(dict.fromkeys((
    *command_phrases(),
    "help",
    "help core",
    "help models",
    "help accounts",
    "help permissions",
    "help handoff",
    "help git",
    "help caveman",
    "help ljson",
    "slash",
    "exit",
    "quit",
    "reset",
    "overview",
    "health",
    "report",
    "status",
    "status full",
    "statusline",
    "preflight",
    "shell backend",
    "stream on",
    "stream off",
    "stream status",
    "doctor",
    "handoff",
    "handoff export",
    "handoff md",
    "board",
    "stage review",
    "resume",
    "resume --show",
    "resume context",
    "resume --clear",
    "boundary",
    "risks",
    "issues",
    "quality",
    "exception",
    "lessons",
    "transcript",
    "trace",
    "todo",
    "models",
    "models usage",
    "models limits",
    "cost",
    "accounts",
    "roles",
    "roles setup",
    "roles propose",
    "roles domains",
    "roles context",
    "roles messages",
    "roles runtime",
    "project start",
    "auth status",
    "permissions",
    "sessions",
    "session list",
    "session create",
    "session send last",
    "session close last",
    "patch preview",
    "git status",
    "git log",
    "git history",
    "git show",
    "git show --stat",
    "model use",
    "model choose",
    "model preset",
    "model add",
    "model remove",
    "model list",
    "model limits",
    "model variant",
    "model variant-clear",
    "model block",
    "model unblock",
    "model limit-record",
    "model limit-clear",
    "model clear",
    "account add",
    "account choose",
    "account login",
    "account login-device",
    "account import",
    "account env",
    "account use",
    "account logout",
    "account remove",
    "account block",
    "account unblock",
    "account limit-record",
    "account limit-clear",
    "account clear",
    "role configure",
    "role clear",
    "sources",
    "sources status",
    "permission mode",
    "permission allow",
    "permission ask",
    "permission deny",
    "permission reset",
    "permission session mode",
    "permission session allow",
    "permission session ask",
    "permission session deny",
    "permission session reset",
    "mode normal",
    "mode caveman",
    "mode plan",
    "mode auto",
    "mode accept-edits",
    "mode dont-ask",
    "mode default",
    "caveman help",
    "caveman on",
    "caveman off",
)))
INTERACTIVE_COMMAND_PREFIX = "/"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stagewarden", description="Stagewarden: production-grade CLI coding agent.")
    parser.add_argument("task", nargs="*", default=[], help='Task to execute, for example: stagewarden "fix the failing tests"')
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum agent loop iterations.")
    parser.add_argument("--verbose", action="store_true", help="Print step-by-step logs.")
    parser.add_argument("--strict-ascii-output", dest="strict_ascii_output", action="store_true", default=True, help="Escape ambiguous non-ASCII characters in structured and generated text output.")
    parser.add_argument("--allow-unicode-output", dest="strict_ascii_output", action="store_false", help="Disable ASCII-safe escaping for generic file output.")
    parser.add_argument("--caveman", nargs="?", const="full", choices=["lite", "full", "ultra", "wenyan-lite", "wenyan", "wenyan-ultra"], help="Activate caveman mode at the selected level.")
    parser.add_argument("--caveman-commit", action="store_true", help="Generate a caveman-style commit message from the current diff.")
    parser.add_argument("--caveman-review", action="store_true", help="Generate one-line caveman review findings for the current diff.")
    parser.add_argument("--caveman-help", action="store_true", help="Show caveman commands and usage.")
    parser.add_argument("--caveman-compress", metavar="PATH", help="Compress a natural-language memory file and write a .original backup.")
    parser.add_argument("--ljson-encode", metavar="JSON_PATH", help="Encode a JSON array file to LJSON.")
    parser.add_argument("--ljson-decode", metavar="LJSON_PATH", help="Decode an LJSON file to JSON array.")
    parser.add_argument("--ljson-output", metavar="OUT_PATH", help="Output path for --ljson-encode/--ljson-decode.")
    parser.add_argument("--ljson-numeric", action="store_true", help="Use numeric-key LJSON representation when encoding.")
    parser.add_argument("--ljson-gzip", action="store_true", help="Write gzipped LJSON when encoding.")
    parser.add_argument("--ljson-benchmark", metavar="JSON_PATH", help="Benchmark standard JSON vs LJSON for a JSON array file.")
    parser.add_argument("--interactive", action="store_true", help="Start an interactive Stagewarden shell.")
    parser.add_argument("--json", action="store_true", help="Emit JSON for machine-readable commands such as `doctor`.")
    parser.add_argument("--full", action="store_true", help="Show expanded status dashboard sections.")
    return parser


def interactive_help_text(topic: str | None = None) -> str:
    if topic:
        return _interactive_help_topic(topic)
    return _interactive_help_overview()


def _interactive_help_overview() -> str:
    lines = [
        "Stagewarden interactive shell",
        "",
        "Use `/help` or `/help <topic>` for full commands and examples.",
        "Use `/slash [prefix]` to open a readable slash-command palette.",
        "All shell commands start with `/`. Any input without `/` is sent to the agent as a task.",
        "",
        "Topics:",
    ]
    for item in help_topic_catalog():
        aliases = item.get("aliases", [])
        alias_text = f" aliases={','.join(str(alias) for alias in aliases)}" if aliases else ""
        lines.append(f"- /help {item['key']}: {item['summary']}{alias_text}")
    lines.extend(
        (
            "",
            "Fast examples:",
            "- stagewarden> /overview",
            "- stagewarden> /slash mo",
            "- stagewarden> /health",
            "- stagewarden> /report",
            "- stagewarden> /preflight",
            "- stagewarden> /shell backend",
            "- stagewarden> /stream status",
            "- stagewarden> /help models",
            "- stagewarden> /models",
            "- stagewarden> models usage",
            "- stagewarden> session create",
            "- stagewarden> session send last pwd",
            "- stagewarden> patch preview changes.diff",
            "- stagewarden> board",
            "- stagewarden> handoff",
            "- stagewarden> fix failing tests",
        )
    )
    return "\n".join(lines)


def _slash_palette_report(config: AgentConfig, prefix: str = "") -> dict[str, object]:
    lowered = prefix.strip().lower()
    specs = command_specs_by_query(lowered)
    prefs = _load_model_preferences(config)
    enabled = ", ".join(prefs.enabled_models or []) or "none"
    active_accounts: list[str] = []
    for provider in prefs.enabled_models or []:
        active = (prefs.active_account_by_model or {}).get(provider)
        if active:
            active_accounts.append(f"{provider}={active}")
    blocked: list[str] = []
    for provider in prefs.enabled_models or []:
        until = (prefs.blocked_until_by_model or {}).get(provider)
        if until:
            blocked.append(f"{provider}:{until}")
    entries: list[dict[str, object]] = []
    for spec in specs:
        hint = ""
        if spec.name == "model variant":
            variant_summary: list[str] = []
            for provider in prefs.enabled_models or []:
                variants = [item.id for item in provider_model_specs(provider)[:3]]
                if variants:
                    variant_summary.append(f"{provider}={','.join(variants)}")
            hint = f"provider_models[{'; '.join(variant_summary) or 'none'}]"
        elif spec.name == "model param set":
            hint = "params[reasoning_effort]"
        elif spec.name.startswith("model "):
            hint = f"providers[{enabled}]"
        elif spec.name.startswith("account "):
            hint = f"active_accounts[{', '.join(active_accounts) or 'none'}]"
        elif spec.name.startswith("role "):
            hint = f"roles[{', '.join(PRINCE2_ROLE_IDS)}]"
        elif spec.name == "shell backend use":
            hint = "backends[auto,bash,zsh,powershell,cmd]"
        entries.append(
            {
                "name": spec.name,
                "usage": spec.usage,
                "description": spec.description,
                "aliases": list(spec.aliases),
                "json": spec.json,
                "handler": spec.handler,
                "examples": list(spec.examples),
                "hint": hint,
            }
        )
    return {
        "command": "slash",
        "prefix": f"/{lowered}" if lowered else "/",
        "context": {
            "enabled_providers": list(prefs.enabled_models or []),
            "active_accounts": active_accounts,
            "blocked_providers": blocked,
        },
        "count": len(entries),
        "entries": entries,
    }


def _render_slash_palette(config: AgentConfig, prefix: str = "") -> str:
    report = _slash_palette_report(config, prefix)
    context = report["context"]
    entries = list(report["entries"])
    lines = ["Slash command palette:"]
    lines.append(f"- prefix: {report['prefix']}")
    enabled = ", ".join(context["enabled_providers"]) or "none"
    active_accounts = ", ".join(context["active_accounts"]) or "none"
    blocked = ", ".join(context["blocked_providers"]) or "none"
    lines.append(f"- enabled_providers: {enabled}")
    lines.append(f"- active_accounts: {active_accounts}")
    lines.append(f"- blocked_providers: {blocked}")
    if not entries:
        lines.append("- no matches")
        return "\n".join(lines)
    for item in entries[:20]:
        aliases = f" aliases={','.join(item['aliases'])}" if item["aliases"] else ""
        json_hint = " json" if item["json"] else ""
        hint = f" hint={item['hint']}" if item["hint"] else ""
        lines.append(f"- /{item['name']}: {item['description']}{aliases}{json_hint}{hint}")
        if item.get("examples"):
            lines.append(f"  example: /{item['examples'][0]}")
    if len(entries) > 20:
        lines.append(f"- truncated: showing 20 of {len(entries)} matches")
    return "\n".join(lines)


def _guided_slash_choice(
    config: AgentConfig,
    query: str,
    *,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Slash chooser unavailable without an interactive input/output stream."
    entries = list(_slash_palette_report(config, query)["entries"])[:20]
    if not entries:
        return "No slash commands match the query."
    options = [
        (str(item["usage"]), f"/{item['usage']} - {item['description']}")
        for item in entries
        if isinstance(item, dict)
    ]
    selected = _prompt_menu_choice(
        title="Choose slash command:",
        options=options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if selected is None:
        return "Slash chooser cancelled."
    return f"Selected slash command: /{selected}"


def _render_slash_choice_candidates(config: AgentConfig, query: str = "") -> str:
    entries = list(_slash_palette_report(config, query)["entries"])[:10]
    lines = ["Slash chooser candidates:"]
    lines.append(f"- query: {query or '(none)'}")
    if not entries:
        lines.append("- no matches")
        return "\n".join(lines)
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"{index}. /{item['usage']} - {item['description']}")
    lines.append("- note: use interactive /slash choose to select one item.")
    return "\n".join(lines)


def _help_json_report(topic: str | None = None) -> dict[str, object]:
    return help_topic_report(topic)


def _interactive_help_topic(topic: str) -> str:
    lines = help_topic_lines(topic)
    if lines is None:
        return _interactive_help_overview() + f"\n\nUnknown help topic: {topic}"
    return "\n".join(lines)


def _load_model_preferences(config: AgentConfig) -> ModelPreferences:
    return ModelPreferences.load(config.model_prefs_path)


def _save_model_preferences(config: AgentConfig, prefs: ModelPreferences) -> None:
    prefs.normalize().save(config.model_prefs_path)


def _sync_handoff_preferences(agent: Agent, prefs: ModelPreferences) -> None:
    agent.handoff.account_env_by_target = dict(prefs.env_var_by_account or {})
    agent.handoff.model_variant_by_model = dict(prefs.variant_by_model or {})
    agent.handoff.model_params_by_model = {
        model: dict(params) for model, params in (prefs.params_by_model or {}).items()
    }
    agent.project_handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))


def _apply_model_preferences(agent: Agent, config: AgentConfig) -> ModelPreferences:
    prefs = _load_model_preferences(config)
    agent.router.configure(
        enabled_models=prefs.enabled_models,
        preferred_model=prefs.preferred_model,
        blocked_until_by_model=prefs.blocked_until_by_model or {},
    )
    _sync_handoff_preferences(agent, prefs)
    return prefs


def _provider_model_display(prefs: ModelPreferences, provider: str) -> tuple[str, str, str]:
    capability = provider_capability(provider)
    pinned = prefs.variant_for_model(provider)
    if pinned:
        return pinned, "pinned", capability.default_model
    if provider in {"chatgpt", "openai", "claude"}:
        return "automatic-by-task", "automatic", capability.default_model
    return capability.default_model, "provider-default", capability.default_model


def _provider_model_params_display(prefs: ModelPreferences, provider: str) -> dict[str, str]:
    return prefs.params_for_model(provider)


def _render_model_status(agent: Agent, config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    status = agent.router.status()
    lines = ["Provider configuration:"]
    for provider in SUPPORTED_MODELS:
        backend = MODEL_BACKENDS[provider]["label"]
        capability = provider_capability(provider)
        enabled = "enabled" if provider in status["enabled_models"] else "disabled"
        blocked_until = status["blocked_until_by_model"].get(provider)
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        active = " active" if provider in status["active_models"] else " inactive"
        preferred = " preferred-provider" if status["preferred_model"] == provider else ""
        provider_model, selection_mode, default_model = _provider_model_display(prefs, provider)
        params = _provider_model_params_display(prefs, provider)
        auth = capability.auth_type
        profiles = "profiles=yes" if capability.supports_account_profiles else "profiles=no"
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if params
            else ""
        )
        lines.append(
            f"- {provider}: {enabled}{active}{preferred}{blocked} "
            f"provider_model={provider_model} selection={selection_mode} default_model={default_model} "
            f"auth={auth} {profiles}{params_text} ({backend})"
        )
        account_lines = _render_account_lines(prefs, provider)
        lines.extend(account_lines)
    if status["preferred_model"] is None:
        lines.append("- preferred_provider: automatic routing")
    else:
        lines.append(f"- preferred_provider: {status['preferred_model']}")
    return "\n".join(lines)


def _render_account_lines(prefs: ModelPreferences, model: str) -> list[str]:
    lines: list[str] = []
    accounts = (prefs.accounts_by_model or {}).get(model, [])
    active_account = (prefs.active_account_by_model or {}).get(model)
    for account in accounts:
        key = account_key(model, account)
        blocked_until = (prefs.blocked_until_by_account or {}).get(key)
        env_var = (prefs.env_var_by_account or {}).get(key)
        keychain = " token=stored" if SecretStore().has_token(model, account) else ""
        active = " active-account" if active_account == account else ""
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        env_text = f" env={env_var}" if env_var else ""
        lines.append(f"  account {account}:{active}{blocked}{env_text}{keychain}")
    return lines


def _sync_prince2_roles_to_handoff(config: AgentConfig, prefs: ModelPreferences) -> None:
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    if prefs.prince2_role_tree_baseline:
        handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline))
    handoff.save(config.handoff_path)


def _prince2_roles_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    return {
        "command": "roles",
        "roles": [
            {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "assignment": dict((prefs.prince2_roles or {}).get(role, {})),
            }
            for role in PRINCE2_ROLE_IDS
        ],
    }


def _render_prince2_roles(config: AgentConfig) -> str:
    report = _prince2_roles_report(config)
    lines = ["PRINCE2 role assignments:"]
    for item in report["roles"]:
        assignment = item["assignment"]
        if not assignment:
            lines.append(f"- {item['label']} ({item['role']}): unassigned")
            continue
        params = assignment.get("params", {})
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if isinstance(params, dict) and params
            else ""
        )
        lines.append(
            f"- {item['label']} ({item['role']}): mode={assignment.get('mode', 'manual')} "
            f"provider={assignment.get('provider', 'unknown')} "
            f"provider_model={assignment.get('provider_model', 'unknown')} "
            f"account={assignment.get('account') or 'none'}"
            f"{params_text} source={assignment.get('source', 'manual')}"
        )
    return "\n".join(lines)


def _render_prince2_role_domains() -> str:
    lines = ["PRINCE2 role domains:"]
    for role in PRINCE2_ROLE_IDS:
        lines.append(
            f"- {PRINCE2_ROLE_LABELS[role]} ({role}): "
            f"responsibility={PRINCE2_ROLE_AUTOMATION_RULES.get(role, 'controlled project work')}; "
            f"context_scope={PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, 'controlled project work')}"
        )
    lines.append("- rule: a role-assigned model receives only the context inside its PRINCE2 domain unless escalation changes the active role.")
    return "\n".join(lines)


def _prince2_role_domains_report() -> dict[str, object]:
    return {
        "command": "roles domains",
        "rule": "a role-assigned model receives only the context inside its PRINCE2 domain unless escalation changes the active role",
        "roles": [
            {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "responsibility": PRINCE2_ROLE_AUTOMATION_RULES.get(role, "controlled project work"),
                "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, "controlled project work"),
            }
            for role in PRINCE2_ROLE_IDS
        ],
    }


def _prince2_role_tree_report(config: AgentConfig) -> dict[str, object]:
    return build_prince2_role_tree(_load_model_preferences(config))


def _render_prince2_role_tree(config: AgentConfig) -> str:
    return render_prince2_role_tree(_prince2_role_tree_report(config))


def _prince2_role_check_report(config: AgentConfig) -> dict[str, object]:
    return check_prince2_role_tree(_load_model_preferences(config))


def _render_prince2_role_check(config: AgentConfig) -> str:
    return render_prince2_role_check(_prince2_role_check_report(config))


def _prince2_role_flow_report() -> dict[str, object]:
    return build_prince2_role_flow()


def _render_prince2_role_flow() -> str:
    return render_prince2_role_flow(_prince2_role_flow_report())


def _prince2_role_matrix_report(config: AgentConfig) -> dict[str, object]:
    return build_prince2_role_matrix(_load_model_preferences(config))


def _render_prince2_role_matrix(config: AgentConfig) -> str:
    return render_prince2_role_matrix(_prince2_role_matrix_report(config))


def _current_git_head(config: AgentConfig) -> str | None:
    result = GitTool(config).head()
    return result.stdout.strip() if result.ok and result.stdout.strip() else None


def _record_handoff_action(
    config: AgentConfig,
    *,
    phase: str,
    summary: str,
    task: str = "",
    details: dict[str, object] | None = None,
) -> None:
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.record_action(
        phase=phase,
        summary=summary,
        task=task,
        git_head=_current_git_head(config),
        details=dict(details or {}),
    )
    handoff.save(config.handoff_path)


def _build_prince2_role_tree_baseline(config: AgentConfig, *, source: str) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    local_execution = _local_execution_candidates_report(config)
    tree = _enrich_tree_with_local_execution_candidates(build_prince2_role_tree(prefs), local_execution)
    return {
        "version": "1",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "status": "approved",
        "tree": tree,
        "flow": build_prince2_role_flow(),
        "check": check_prince2_role_tree_payload(tree, prefs),
        "matrix": build_prince2_role_matrix_payload(tree, prefs),
        "local_execution": local_execution,
    }


def _approve_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    baseline = _build_prince2_role_tree_baseline(config, source=source)
    prefs.set_prince2_role_tree_baseline(baseline)
    _save_model_preferences(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline or {}))
    handoff.save(config.handoff_path)
    return baseline


def _refresh_prince2_role_tree_baseline_checks(baseline: dict[str, object], prefs: ModelPreferences) -> dict[str, object]:
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    baseline["check"] = check_prince2_role_tree_payload(tree, prefs)
    baseline["matrix"] = build_prince2_role_matrix_payload(tree, prefs)
    return baseline


def _persist_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, baseline: dict[str, object]) -> None:
    prefs.set_prince2_role_tree_baseline(baseline)
    _save_model_preferences(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline or {}))
    handoff.save(config.handoff_path)


def _ensure_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    baseline = dict(prefs.prince2_role_tree_baseline or {})
    if baseline:
        return baseline
    return _build_prince2_role_tree_baseline(config, source=source)


def _add_child_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    parent_id: str,
    role_type: str,
    node_id: str | None = None,
) -> dict[str, object]:
    if role_type not in PRINCE2_ROLE_IDS:
        raise ValueError(f"Unsupported PRINCE2 role '{role_type}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}")
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_add_child")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = list(tree.get("nodes", [])) if isinstance(tree.get("nodes", []), list) else []
    parent = next((node for node in nodes if isinstance(node, dict) and node.get("node_id") == parent_id), None)
    if parent is None:
        raise ValueError(f"Parent role node '{parent_id}' not found.")
    existing_ids = {str(node.get("node_id")) for node in nodes if isinstance(node, dict)}
    if node_id is None:
        base = f"{parent_id}.{role_type}"
        candidate = base
        index = 2
        while candidate in existing_ids:
            candidate = f"{base}_{index}"
            index += 1
        node_id = candidate
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", node_id):
        raise ValueError("Node id must contain only letters, numbers, dot, dash, and underscore.")
    if node_id in existing_ids:
        raise ValueError(f"Role node '{node_id}' already exists.")
    rule = ROLE_CONTEXT_RULES[role_type].as_dict()
    child = {
        "node_id": node_id,
        "role_type": role_type,
        "label": f"{PRINCE2_ROLE_LABELS[role_type]} Delegated",
        "parent_id": parent_id,
        "level": f"delegated_{parent.get('level', 'node')}",
        "accountability_boundary": f"delegated {PRINCE2_ROLE_LABELS[role_type]} accountability under {parent.get('label', parent_id)}",
        "delegated_authority": f"delegated by {parent.get('label', parent_id)}; cannot exceed parent authority or approved tolerances",
        "responsibility_domain": PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, "controlled project work"),
        "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, "controlled project work"),
        "context_rule": rule,
        "assignment": {},
        "fallback_pool": list(prefs.active_models() or prefs.enabled_models),
        "readiness": "unassigned",
    }
    nodes.append(child)
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = "role_add_child"
    baseline["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _refresh_prince2_role_tree_baseline_checks(baseline, prefs)
    _persist_prince2_role_tree_baseline(config, prefs, baseline)
    return child


def _assign_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    provider: str,
    provider_model: str,
    params: dict[str, str] | None = None,
    account: str | None = None,
    pool: str = "primary",
) -> dict[str, object]:
    clean_pool = str(pool).strip().lower() or "primary"
    if clean_pool not in {"primary", "reviewer", "fallback"}:
        raise ValueError("Pool must be primary, reviewer, or fallback.")
    if provider not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported provider '{provider}'. Supported: {', '.join(SUPPORTED_MODELS)}")
    canonical_model = canonicalize_model_variant(provider, provider_model)
    if account is not None and account not in (prefs.accounts_by_model or {}).get(provider, []):
        raise ValueError(f"Account '{account}' is not configured for provider '{provider}'.")
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_assign")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = list(tree.get("nodes", [])) if isinstance(tree.get("nodes", []), list) else []
    target = next((node for node in nodes if isinstance(node, dict) and node.get("node_id") == node_id), None)
    if target is None:
        raise ValueError(f"Role node '{node_id}' not found.")
    clean_params: dict[str, str] = {}
    spec = provider_model_spec(provider, canonical_model)
    for key, value in (params or {}).items():
        if key != "reasoning_effort":
            continue
        if spec is not None and value in spec.reasoning_efforts:
            clean_params[key] = value
    route = {
        "role": str(target.get("role_type", "")),
        "node_id": node_id,
        "label": str(target.get("label", node_id)),
        "mode": "manual",
        "provider": provider,
        "provider_model": canonical_model,
        "params": clean_params,
        "account": account,
        "source": "node_manual",
    }
    if clean_pool == "primary":
        target["assignment"] = route
        target["fallback_pool"] = [model for model in (prefs.active_models() or prefs.enabled_models) if model != provider]
        target["readiness"] = "assigned"
    else:
        pools = target.get("assignment_pool", {}) if isinstance(target.get("assignment_pool"), dict) else {}
        routes = [dict(item) for item in pools.get(clean_pool, []) if isinstance(item, dict)] if isinstance(pools.get(clean_pool, []), list) else []
        routes = [
            item
            for item in routes
            if not (item.get("provider") == provider and item.get("provider_model") == canonical_model and item.get("account") == account)
        ]
        route["pool"] = clean_pool
        routes.append(route)
        pools[clean_pool] = routes
        target["assignment_pool"] = pools
        if target.get("assignment"):
            target["readiness"] = "assigned"
        else:
            target["readiness"] = "reviewer_pool_only" if clean_pool == "reviewer" else "fallback_pool_only"
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = "role_assign"
    baseline["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _refresh_prince2_role_tree_baseline_checks(baseline, prefs)
    _persist_prince2_role_tree_baseline(config, prefs, baseline)
    return dict(target)


def _prince2_role_tree_baseline_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    baseline = dict(prefs.prince2_role_tree_baseline or {})
    return {
        "command": "roles baseline",
        "status": "approved" if baseline else "missing",
        "baseline": baseline,
    }


def _render_prince2_role_tree_baseline(config: AgentConfig) -> str:
    report = _prince2_role_tree_baseline_report(config)
    baseline = report["baseline"]
    if not isinstance(baseline, dict) or not baseline:
        return "PRINCE2 role-tree baseline: missing\n- action: run /project start or /roles tree approve"
    check = baseline.get("check", {})
    matrix = baseline.get("matrix", {})
    tree = baseline.get("tree", {})
    local_execution = baseline.get("local_execution", {}) if isinstance(baseline.get("local_execution"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    rows = matrix.get("rows", []) if isinstance(matrix, dict) else []
    check_status = check.get("status", "unknown") if isinstance(check, dict) else "unknown"
    lines = [
        "PRINCE2 role-tree baseline:",
        f"- status: {baseline.get('status', 'approved')}",
        f"- approved_at: {baseline.get('approved_at', 'unknown')}",
        f"- source: {baseline.get('source', 'unknown')}",
        f"- check_status: {check_status}",
        f"- nodes: {len(nodes)}",
        f"- matrix_rows: {len(rows)}",
        "- rule: this approved role tree is the governance baseline for future role-routed context handoffs.",
    ]
    if local_execution:
        candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
        lines.append(
            "- local_execution_candidates: "
            + (", ".join(str(item.get("id", "")) for item in candidates if str(item.get("id", "")).strip()) or "none")
        )
    return "\n".join(lines)


def _prince2_role_tree_baseline_matrix_report(config: AgentConfig) -> dict[str, object]:
    report = _prince2_role_tree_baseline_report(config)
    baseline = report.get("baseline", {})
    matrix = baseline.get("matrix", {}) if isinstance(baseline, dict) else {}
    if not isinstance(matrix, dict) or not matrix:
        return {
            "command": "roles baseline matrix",
            "status": "missing",
            "message": "No approved PRINCE2 role-tree baseline matrix. Run /project start, /roles propose, or /roles tree approve first.",
        }
    payload = dict(matrix)
    payload["command"] = "roles baseline matrix"
    payload["baseline_status"] = report.get("status", "missing")
    return payload


def _prince2_role_runtime_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_runtime_report()


def _render_prince2_role_runtime(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_runtime()


def _prince2_role_active_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_active_report()


def _render_prince2_role_active(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_active()


def _prince2_role_queue_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_queue_report()


def _render_prince2_role_queues(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_queues()


def _prince2_role_control_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_control_report()


def _render_prince2_role_control(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_control()


def _prince2_role_messages_report(config: AgentConfig, node_id: str | None = None) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_messages_report(node_id=node_id)


def _render_prince2_role_messages(config: AgentConfig, node_id: str | None = None) -> str:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_messages(node_id=node_id)


def _agent_capability_surface_for_node(config: AgentConfig) -> dict[str, object]:
    runtime = detect_runtime_capabilities(config.workspace_root)
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
        "model_actions": sorted(ALLOWED_MODEL_ACTIONS),
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


def _prince2_role_context_report(config: AgentConfig, node_id: str) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    runtime_report = handoff.prince2_node_runtime_report()
    runtime = runtime_report.get("runtime", {}) if isinstance(runtime_report.get("runtime"), dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    node = next((item for item in nodes if str(item.get("node_id", "")).strip() == node_id), None)
    if node is None:
        return {
            "command": "roles context",
            "status": "missing",
            "node_id": node_id,
            "message": f"Node '{node_id}' not found in PRINCE2 runtime.",
        }
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    incoming = [edge for edge in edges if str(edge.get("target_node", "")).strip() == node_id]
    outgoing = [edge for edge in edges if str(edge.get("source_node", "")).strip() == node_id]
    assignment = dict(node.get("assignment", {})) if isinstance(node.get("assignment"), dict) else {}
    role_type = str(node.get("role_type", "")).strip()
    return {
        "command": "roles context",
        "status": "ok",
        "node_id": node_id,
        "node_label": str(node.get("label", node_id)),
        "role_type": role_type,
        "runtime_state": {
            "state": str(node.get("state", "unknown")),
            "wait_status": str(node.get("wait_status", "none")),
            "wait_reason": node.get("wait_reason"),
            "wake_triggers": list(node.get("wake_triggers", [])),
            "inbox_count": int(node.get("inbox_count", 0) or 0),
            "outbox_count": int(node.get("outbox_count", 0) or 0),
            "transcript_refs": [str(item) for item in node.get("transcript_refs", [])] if isinstance(node.get("transcript_refs", []), list) else [],
        },
        "assignment": assignment,
        "prince2_role_context": {
            "responsibility_domain": str(node.get("responsibility_domain", PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, ""))),
            "context_scope": str(node.get("context_scope", PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, ""))),
            "accountability_boundary": str(node.get("accountability_boundary", "")),
            "delegated_authority": str(node.get("delegated_authority", "")),
            "context_include": list((node.get("context_rule") or {}).get("include", [])) if isinstance(node.get("context_rule"), dict) else [],
            "context_exclude": list((node.get("context_rule") or {}).get("exclude", [])) if isinstance(node.get("context_rule"), dict) else [],
        },
        "communications": {
            "incoming_edges": incoming,
            "outgoing_edges": outgoing,
            "commands": [
                "roles active [--json]",
                "roles control [--json]",
                "roles queues [--json]",
                "roles messages [node_id]",
                "role message <source_node> <target_node> <edge_id> payload=<scope1,scope2>",
                "role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]",
                "role wake <node_id> trigger=<name>",
                "role tick <node_id>",
                "roles tick [max_nodes]",
            ],
        },
        "agent_capabilities": _agent_capability_surface_for_node(config),
        "project_context": {
            "task": handoff.task or "none",
            "project_status": handoff.status or "idle",
            "current_step": handoff.current_step_id or "none",
            "current_step_status": handoff.current_step_status or "none",
        },
    }


def _render_prince2_role_context(config: AgentConfig, node_id: str) -> str:
    report = _prince2_role_context_report(config, node_id)
    if report.get("status") != "ok":
        return str(report.get("message", "PRINCE2 role context unavailable."))
    runtime_state = report["runtime_state"]
    role_context = report["prince2_role_context"]
    assignment = report["assignment"]
    comms = report["communications"]
    caps = report["agent_capabilities"]
    lines = [
        "PRINCE2 node AI context:",
        f"- node: {report['node_label']} [{report['node_id']}]",
        f"- role_type: {report['role_type']}",
        f"- state: {runtime_state['state']} wait={runtime_state['wait_status']} inbox={runtime_state['inbox_count']} outbox={runtime_state['outbox_count']}",
        f"- provider: {assignment.get('provider') or 'none'} provider_model={assignment.get('provider_model') or 'none'} account={assignment.get('account') or 'none'}",
        f"- responsibility_domain: {role_context['responsibility_domain']}",
        f"- context_scope: {role_context['context_scope']}",
        f"- accountability_boundary: {role_context['accountability_boundary']}",
        f"- delegated_authority: {role_context['delegated_authority']}",
        f"- context_include: {', '.join(role_context['context_include']) or 'none'}",
        f"- context_exclude: {', '.join(role_context['context_exclude']) or 'none'}",
        f"- wake_triggers: {', '.join(runtime_state['wake_triggers']) or 'none'}",
        f"- incoming_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['incoming_edges']) or 'none'}",
        f"- outgoing_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['outgoing_edges']) or 'none'}",
        f"- agent_tools: {', '.join(caps['shell_operations'] + caps['git_operations'][:2] + ['...'])}",
        f"- file_ops: {', '.join(caps['file_operations'][:6])}, ...",
        "- communication_commands:",
    ]
    for command in comms["commands"]:
        lines.append(f"  {command}")
    lines.append(f"- project_task: {report['project_context']['task']}")
    lines.append(f"- project_status: {report['project_context']['project_status']}")
    lines.append(f"- current_step: {report['project_context']['current_step']} [{report['project_context']['current_step_status']}]")
    return "\n".join(lines)


def _send_prince2_role_message(
    config: AgentConfig,
    *,
    source_node: str,
    target_node: str,
    edge_id: str,
    payload_scope: list[str],
    evidence_refs: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    message = handoff.send_prince2_node_message(
        source_node=source_node,
        target_node=target_node,
        edge_id=edge_id,
        payload_scope=payload_scope,
        evidence_refs=evidence_refs,
        summary=summary,
    )
    handoff.save(config.handoff_path)
    _record_handoff_action(
        config,
        phase="role_message",
        task=f"role message {source_node} {target_node} {edge_id}",
        summary=f"Queued governed PRINCE2 node message {message['message_id']}.",
        details={
            "source_node": source_node,
            "target_node": target_node,
            "edge_id": edge_id,
            "payload_scope": list(payload_scope),
            "evidence_refs": list(evidence_refs or []),
        },
    )
    return message


def _set_prince2_role_node_waiting(
    config: AgentConfig,
    *,
    node_id: str,
    reason: str,
    wake_triggers: list[str] | None = None,
) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    node = handoff.set_prince2_node_waiting(node_id=node_id, reason=reason, wake_triggers=wake_triggers)
    handoff.save(config.handoff_path)
    _record_handoff_action(
        config,
        phase="role_wait",
        task=f"role wait {node_id}",
        summary=f"Node {node_id} moved to waiting state.",
        details={"node_id": node_id, "reason": reason, "wake_triggers": list(wake_triggers or [])},
    )
    return node


def _wake_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
    trigger: str,
) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    node = handoff.wake_prince2_node(node_id=node_id, trigger=trigger)
    handoff.save(config.handoff_path)
    _record_handoff_action(
        config,
        phase="role_wake",
        task=f"role wake {node_id}",
        summary=f"Node {node_id} woke with trigger {trigger}.",
        details={"node_id": node_id, "trigger": trigger},
    )
    return node


def _tick_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    result = handoff.tick_prince2_node(node_id=node_id)
    handoff.save(config.handoff_path)
    _record_handoff_action(
        config,
        phase="role_tick",
        task=f"role tick {node_id}",
        summary=f"Node {node_id} advanced to {result.get('state', 'unknown')}.",
        details=dict(result),
    )
    return result


def _tick_prince2_role_runtime(
    config: AgentConfig,
    *,
    max_nodes: int | None = None,
) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    _sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    result = handoff.tick_prince2_runtime(max_nodes=max_nodes)
    handoff.save(config.handoff_path)
    _record_handoff_action(
        config,
        phase="roles_tick",
        task=f"roles tick {max_nodes if max_nodes is not None else ''}".strip(),
        summary=f"Batch advanced PRINCE2 runtime across {result.get('processed', 0)} node(s).",
        details=dict(result),
    )
    return result


def _render_prince2_role_tree_baseline_matrix(config: AgentConfig) -> str:
    report = _prince2_role_tree_baseline_matrix_report(config)
    if report.get("status") == "missing":
        return str(report.get("message", "No approved PRINCE2 role-tree baseline matrix."))
    return render_prince2_role_matrix(report)


def _render_prince2_role_status_hint(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    configured = len(prefs.prince2_roles or {})
    tree_baseline = "approved" if prefs.prince2_role_tree_baseline else "missing"
    if configured == len(PRINCE2_ROLE_IDS):
        return f"- prince2_role_baseline: complete ({configured}/{len(PRINCE2_ROLE_IDS)}); role_tree={tree_baseline}"
    if configured:
        return (
            f"- prince2_role_baseline: partial ({configured}/{len(PRINCE2_ROLE_IDS)}); "
            f"role_tree={tree_baseline}; run /roles setup to complete governance ownership."
        )
    return "- prince2_role_baseline: missing; role_tree=missing; run /project start or /roles setup before controlled delivery."


def _project_design_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = _load_model_preferences(config)
    runtime = detect_runtime_capabilities()
    shell_backend = _shell_backend_report(config)
    provider_limits = _provider_limit_status_report(agent, config)
    permissions = _permissions_report(config)
    role_check = _prince2_role_check_report(config)
    baseline = _prince2_role_tree_baseline_report(config)
    focus = _focus_snapshot(agent, config)

    enabled_providers = [item["provider"] for item in provider_limits["providers"] if item["enabled"]]
    active_accounts = {
        provider: account
        for provider, account in (prefs.active_account_by_model or {}).items()
        if account
    }
    blocked_providers = [
        {
            "provider": item["provider"],
            "blocked_until": item["blocked_until"],
            "reason": item["last_error_reason"],
        }
        for item in provider_limits["providers"]
        if item["blocked_until"]
    ]
    capability_spec = {
        "workspace": str(config.workspace_root),
        "os_family": str(runtime.get("os_family", "unknown")),
        "platform_release": str(runtime.get("platform_release", "unknown")),
        "architecture": str(runtime.get("platform_machine", "unknown")),
        "default_shell": str(runtime.get("default_shell") or "none"),
        "recommended_shell": str(runtime.get("recommended_shell", "unknown")),
        "shell_backend": {
            "configured": shell_backend["configured"],
            "selected": shell_backend["selected"] or "none",
            "executable": shell_backend["executable"] or "none",
        },
        "capabilities": {
            "shell": True,
            "files": True,
            "git": True,
            "web_research": True,
            "download": True,
            "compression": True,
            "wet_run_required": True,
        },
        "permission_mode": permissions["effective"]["mode"],
        "enabled_providers": enabled_providers,
        "active_accounts": active_accounts,
        "blocked_providers": blocked_providers,
        "preferred_provider": prefs.preferred_model or "automatic",
    }
    project_spec = {
        "task": handoff.task or "missing",
        "brief": dict(handoff.project_brief),
        "brief_fields": sorted(handoff.project_brief),
        "project_status": handoff.status,
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "boundary_decision": handoff.stage_view()["boundary_decision"],
        "next_action": handoff.rendered_next_action(),
        "open_risks": len([item for item in handoff.risk_register if str(item.get("status", "open")).strip().lower() != "closed"]),
        "open_issues": len([item for item in handoff.issue_register if str(item.get("status", "open")).strip().lower() != "closed"]),
        "quality_open": len([item for item in handoff.quality_register if str(item.get("status", "")).strip().lower() not in {"accepted", "closed"}]),
        "role_tree_status": baseline["status"],
        "role_tree_nodes": len((baseline.get("baseline", {}) or {}).get("tree", {}).get("nodes", [])) if isinstance((baseline.get("baseline", {}) or {}).get("tree", {}), dict) else 0,
    }
    gaps: list[dict[str, str]] = []
    if not handoff.task.strip():
        gaps.append({"code": "missing_project_task", "message": "Project specification is missing a task/objective in handoff context."})
    if not handoff.project_brief.get("objective"):
        gaps.append({"code": "missing_project_objective", "message": "Project brief is missing the objective field."})
    if not handoff.project_brief.get("scope"):
        gaps.append({"code": "missing_project_scope", "message": "Project brief is missing the scope field."})
    if not handoff.project_brief.get("expected_outputs"):
        gaps.append({"code": "missing_expected_outputs", "message": "Project brief is missing the expected_outputs field."})
    if not handoff.project_brief.get("delivery_mode"):
        gaps.append({"code": "missing_delivery_mode", "message": "Project brief is missing the delivery_mode field."})
    if role_check.get("status") != "ok":
        gaps.append({"code": "role_tree_not_ready", "message": "Role tree is not fully ready; AI tree design must treat current structure as provisional."})
    if not enabled_providers:
        gaps.append({"code": "no_enabled_providers", "message": "No enabled providers are available for AI-assisted design."})
    if shell_backend["selected"] in {None, ""}:
        gaps.append({"code": "shell_backend_unknown", "message": "Selected shell backend is unknown, so capability context is incomplete."})
    if not baseline.get("baseline"):
        gaps.append({"code": "missing_role_tree_baseline", "message": "No approved role-tree baseline exists yet."})
    ready = not gaps
    return {
        "command": "project design",
        "ready_for_ai_design": ready,
        "agent_capability_specification": capability_spec,
        "project_specification": project_spec,
        "role_tree_check": role_check,
        "focus": focus,
        "clarification_gaps": gaps,
    }


def _render_project_design(agent: Agent, config: AgentConfig) -> str:
    report = _project_design_report(agent, config)
    capability = report["agent_capability_specification"]
    project = report["project_specification"]
    blocked_text = ", ".join(
        f"{item['provider']}:{item['blocked_until']}"
        for item in capability["blocked_providers"]
    ) or "none"
    lines = [
        "Project design packet:",
        f"- ready_for_ai_design: {str(report['ready_for_ai_design']).lower()}",
        "Agent capability specification:",
        f"- workspace: {capability['workspace']}",
        f"- os_family: {capability['os_family']}",
        f"- shell_backend: configured={capability['shell_backend']['configured']} selected={capability['shell_backend']['selected']} executable={capability['shell_backend']['executable']}",
        f"- permission_mode: {capability['permission_mode']}",
        f"- enabled_providers: {', '.join(capability['enabled_providers']) or 'none'}",
        f"- active_accounts: {', '.join(f'{key}={value}' for key, value in sorted(capability['active_accounts'].items())) or 'none'}",
        f"- blocked_providers: {blocked_text}",
        f"- wet_run_required: {str(capability['capabilities']['wet_run_required']).lower()}",
        "Project specification:",
        f"- task: {project['task']}",
        f"- brief_fields: {', '.join(project['brief_fields']) or 'none'}",
        f"- project_status: {project['project_status']}",
        f"- current_step: {project['current_step']}",
        f"- boundary_decision: {project['boundary_decision']}",
        f"- next_action: {project['next_action']}",
        f"- open_risks: {project['open_risks']}",
        f"- open_issues: {project['open_issues']}",
        f"- quality_open: {project['quality_open']}",
        f"- role_tree_status: {project['role_tree_status']}",
        f"- role_tree_nodes: {project['role_tree_nodes']}",
        "Project brief:",
    ]
    brief = project["brief"]
    if isinstance(brief, dict) and brief:
        for key in sorted(brief):
            lines.append(f"- {key}: {brief[key]}")
    else:
        lines.append("- none")
    lines.extend(
        [
        "Clarification gaps:",
        ]
    )
    gaps = report["clarification_gaps"]
    if gaps:
        for item in gaps:
            lines.append(f"- {item['code']}: {item['message']}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _project_tree_ai_needed(design: dict[str, object], proposal: dict[str, object]) -> bool:
    if proposal.get("status") != "ready_for_review":
        return False
    project = design.get("project_specification") if isinstance(design.get("project_specification"), dict) else {}
    brief = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    text = " ".join(str(value).lower() for value in brief.values())
    complexity_tokens = (
        "complex",
        "regulated",
        "enterprise",
        "multi-vendor",
        "multi provider",
        "rate-limit",
        "rate limit",
        "high uncertainty",
        "alto rischio",
        "alta incertezza",
        "security",
        "auth",
        "compliance",
    )
    return any(token in text for token in complexity_tokens)


def _render_project_start(agent: Agent, config: AgentConfig, prefs: ModelPreferences, *, force_ai: bool = False) -> str:
    design = _project_design_report(agent, config)
    local_proposal = _project_tree_proposal_report(config)
    use_ai = force_ai or _project_tree_ai_needed(design, local_proposal)
    proposal = _project_tree_proposal_report(config, agent=agent, use_ai=True) if use_ai else local_proposal
    sections = [
        "Project startup design gate:",
        _render_project_design(agent, config),
        _render_project_tree_proposal_report(proposal),
    ]
    ignored_startup_design_gaps = {"role_tree_not_ready", "missing_role_tree_baseline"}
    raw_design_gaps = design.get("clarification_gaps", [])
    design_gaps = [
        item
        for item in raw_design_gaps
        if isinstance(item, dict) and str(item.get("code", "")) not in ignored_startup_design_gaps
    ] if isinstance(raw_design_gaps, list) else []
    proposal_gaps = proposal.get("clarification_gaps", [])
    has_gaps = bool(design_gaps or proposal_gaps)
    if has_gaps or proposal.get("status") != "ready_for_review":
        _record_handoff_action(
            config,
            phase="project_start_blocked",
            summary="Project startup blocked by unresolved design/proposal clarification gaps.",
            task="project start",
            details={
                "design_gaps": design_gaps,
                "proposal_gaps": proposal_gaps if isinstance(proposal_gaps, list) else [],
                "proposal_status": proposal.get("status"),
                "ai_requested": proposal.get("ai_requested"),
                "ai_assistance": proposal.get("ai_assistance"),
            },
        )
        lines = [
            "Project startup blocked:",
            "- reason: project design/proposal has unresolved clarification gaps.",
            "- action: complete /project brief fields, rerun /project tree propose, then rerun /project start.",
            "- override: use /project tree approve --force if the Project Board accepts the gaps explicitly.",
        ]
        for item in design_gaps if isinstance(design_gaps, list) else []:
            if isinstance(item, dict):
                lines.append(f"- design_gap {item.get('code', 'gap')}: {item.get('message', 'missing')}")
        for item in proposal_gaps if isinstance(proposal_gaps, list) else []:
            if isinstance(item, dict):
                lines.append(f"- proposal_gap {item.get('code', 'gap')}: {item.get('message', 'missing')}")
        sections.append("\n".join(lines))
        return "\n\n".join(sections)
    approval = _approve_project_tree_proposal(config, force=False, proposal_report=proposal)
    _apply_model_preferences(agent, config)
    _record_handoff_action(
        config,
        phase="project_start_approved",
        summary="Project startup approved through controlled project-tree proposal path.",
        task="project start",
        details={
            "approval_status": approval.get("status"),
            "forced": approval.get("forced"),
            "proposal_added_nodes": proposal.get("added_nodes", []),
            "ai_requested": proposal.get("ai_requested"),
            "ai_assistance": proposal.get("ai_assistance"),
            "local_execution": proposal.get("local_execution", {}),
        },
    )
    sections.append(_render_project_tree_approval_report(approval, config))
    local_execution = proposal.get("local_execution") if isinstance(proposal.get("local_execution"), dict) else {}
    local_candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    if local_candidates:
        lines = ["Project start local fallback preload:"]
        lines.append(
            "- candidates: "
            + ", ".join(str(item.get("id", "")) for item in local_candidates if str(item.get("id", "")).strip())
        )
        if local_execution.get("message"):
            lines.append(f"- recommendation: {local_execution.get('message')}")
        lines.append("- status: approved baseline includes recommended local delivery fallback routes.")
        sections.append("\n".join(lines))
    sections.extend(
        [
            _render_prince2_roles(config),
            _render_prince2_role_tree_baseline(config),
        ]
    )
    return "\n\n".join(sections)


def _project_start_ready(config: AgentConfig) -> bool:
    handoff = ProjectHandoff.load(config.handoff_path)
    if not handoff.task.strip():
        return False
    for field_name in ("objective", "scope", "expected_outputs", "delivery_mode"):
        if not handoff.project_brief.get(field_name):
            return False
    return True


PROJECT_BRIEF_FIELDS: dict[str, str] = {
    "objective": "Why the project exists and what outcome it should achieve.",
    "scope": "What is in scope for this project brief.",
    "expected_outputs": "What deliverables or outcomes must exist at completion.",
    "delivery_mode": "Delivery approach such as agile, sequential, hybrid, or investigative.",
    "constraints": "Known limits such as budget, time, regulatory, or platform constraints.",
    "quality_gates": "Explicit acceptance or validation gates required before closure.",
    "stakeholders": "Key stakeholders, sponsors, users, suppliers, or reviewers.",
    "uncertainty": "Known uncertainty, ambiguity, or discovery level.",
    "risk_tolerance": "Declared tolerance or escalation posture for risk.",
}


def _project_brief_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "project brief",
        "fields": dict(handoff.project_brief),
        "supported_fields": dict(PROJECT_BRIEF_FIELDS),
        "count": len(handoff.project_brief),
    }


def _render_project_brief(config: AgentConfig) -> str:
    report = _project_brief_report(config)
    lines = ["Project brief:"]
    fields = report["fields"]
    if isinstance(fields, dict) and fields:
        for key in sorted(fields):
            lines.append(f"- {key}: {fields[key]}")
    else:
        lines.append("- none")
    lines.append("Supported fields:")
    for key in sorted(PROJECT_BRIEF_FIELDS):
        lines.append(f"- {key}: {PROJECT_BRIEF_FIELDS[key]}")
    return "\n".join(lines)


def _handle_project_brief_command(command: str, config: AgentConfig) -> str | None:
    parts = command.split()
    if parts[:2] != ["project", "brief"]:
        return None
    handoff = ProjectHandoff.load(config.handoff_path)
    if len(parts) == 2:
        return _render_project_brief(config)
    if len(parts) >= 4 and parts[2] == "set":
        field_name = parts[3].strip().lower()
        if field_name not in PROJECT_BRIEF_FIELDS:
            return f"Unsupported project brief field '{field_name}'. Supported: {', '.join(sorted(PROJECT_BRIEF_FIELDS))}"
        prefix = f"project brief set {parts[3]}"
        value = command[len(prefix):].strip()
        if not value:
            return "Usage: project brief set <field> <value>"
        handoff.update_project_brief({field_name: value})
        handoff.save(config.handoff_path)
        return f"Project brief updated: {field_name}={handoff.project_brief.get(field_name, '')}"
    if len(parts) >= 3 and parts[2] == "clear":
        if len(parts) == 3:
            handoff.clear_project_brief()
            handoff.save(config.handoff_path)
            return "Project brief cleared."
        field_name = parts[3].strip().lower()
        if field_name not in PROJECT_BRIEF_FIELDS:
            return f"Unsupported project brief field '{field_name}'. Supported: {', '.join(sorted(PROJECT_BRIEF_FIELDS))}"
        handoff.clear_project_brief(field_name)
        handoff.save(config.handoff_path)
        return f"Project brief field cleared: {field_name}"
    return "Usage: project brief | project brief set <field> <value> | project brief clear [field]"


def _assignment_for_role(prefs: ModelPreferences, role: str) -> dict[str, object]:
    proposal = prefs.propose_prince2_roles()
    assignment = dict((prefs.prince2_roles or {}).get(role) or proposal.get(role, {}))
    if not assignment:
        return {}
    assignment.setdefault("role", role)
    assignment.setdefault("label", PRINCE2_ROLE_LABELS.get(role, role))
    assignment.setdefault("mode", "auto")
    assignment.setdefault("source", "project_tree_proposal")
    return assignment


def _role_node_from_template(
    *,
    node_id: str,
    role_type: str,
    label: str,
    parent_id: str | None,
    level: str,
    accountability_boundary: str,
    delegated_authority: str,
    assignment: dict[str, object],
    active_models: list[str],
) -> dict[str, object]:
    provider = str(assignment.get("provider", "")) if assignment else ""
    return {
        "node_id": node_id,
        "role_type": role_type,
        "label": label,
        "parent_id": parent_id,
        "level": level,
        "accountability_boundary": accountability_boundary,
        "delegated_authority": delegated_authority,
        "responsibility_domain": PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, "controlled project work"),
        "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, "controlled project work"),
        "context_rule": ROLE_CONTEXT_RULES[role_type].as_dict(),
        "assignment": assignment,
        "fallback_pool": [item for item in active_models if item != provider],
        "readiness": "assigned" if assignment else "unassigned",
    }


def _route_from_local_execution_candidate(candidate: dict[str, object], *, node: dict[str, object]) -> dict[str, object] | None:
    provider_model = str(candidate.get("id", "")).strip()
    if not provider_model:
        return None
    params: dict[str, str] = {}
    reasoning_default = str(candidate.get("reasoning_default", "")).strip()
    if reasoning_default:
        params["reasoning_effort"] = reasoning_default
    return {
        "role": str(node.get("role_type", "")),
        "node_id": str(node.get("node_id", "")),
        "label": str(node.get("label", node.get("node_id", ""))),
        "mode": "auto",
        "provider": "local",
        "provider_model": provider_model,
        "params": params,
        "account": None,
        "source": "auto_local_execution_candidate",
        "pool": "fallback",
    }


def _enrich_tree_with_local_execution_candidates(
    tree: dict[str, object],
    local_execution: dict[str, object],
) -> dict[str, object]:
    nodes = [dict(node) for node in tree.get("nodes", []) if isinstance(node, dict)]
    candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    candidate_ids = [str(item.get("id", "")).strip() for item in candidates if str(item.get("id", "")).strip()]
    for node in nodes:
        if not str(node.get("level", "")).startswith("delivery"):
            continue
        node["local_execution_candidates"] = list(candidate_ids)
        if not candidates:
            continue
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = [dict(item) for item in pools.get("fallback", []) if isinstance(item, dict)] if isinstance(pools.get("fallback", []), list) else []
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        assignment_provider = str(assignment.get("provider", "")).strip()
        assignment_model = str(assignment.get("provider_model", "")).strip()
        existing = {
            (str(item.get("provider", "")).strip(), str(item.get("provider_model", "")).strip(), str(item.get("account", "")).strip())
            for item in routes
        }
        for candidate in candidates:
            route = _route_from_local_execution_candidate(candidate, node=node)
            if route is None:
                continue
            signature = (
                str(route.get("provider", "")).strip(),
                str(route.get("provider_model", "")).strip(),
                str(route.get("account", "")).strip(),
            )
            if assignment_provider == "local" and assignment_model == signature[1]:
                continue
            if signature in existing:
                continue
            routes.append(route)
            existing.add(signature)
        if routes:
            pools["fallback"] = routes
            node["assignment_pool"] = pools
    enriched = dict(tree)
    enriched["nodes"] = nodes
    return enriched


def _project_tree_proposal_report(config: AgentConfig, *, agent: Agent | None = None, use_ai: bool = False) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = _load_model_preferences(config)
    proposed_roles = prefs.propose_prince2_roles()
    merged_roles = dict(proposed_roles)
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    active_models = list(proposal_prefs.active_models() or proposal_prefs.enabled_models)
    local_execution = _local_execution_candidates_report(config, agent=agent, use_ai=use_ai)
    base_tree = build_prince2_role_tree(proposal_prefs)
    nodes = [dict(node) for node in base_tree.get("nodes", []) if isinstance(node, dict)]
    brief = {str(key): str(value) for key, value in handoff.project_brief.items()}
    joined = " ".join(brief.values()).lower()
    assumptions: list[str] = []
    added_nodes: list[str] = []

    delivery_keywords = ("cli", "shell", "git", "code", "coding", "test", "tests", "download", "web", "compression", "multi", "windows", "linux", "macos")
    complex_delivery = any(keyword in joined for keyword in delivery_keywords) or brief.get("delivery_mode", "").lower() in {"hybrid", "agile", "iterative", "investigative"}
    if complex_delivery:
        node_id = "delivery.implementation_team"
        nodes.append(
            _role_node_from_template(
                node_id=node_id,
                role_type="team_manager",
                label="Implementation Team Manager",
                parent_id="management.project_manager",
                level="delivery",
                accountability_boundary="delegated delivery of implementation work packages within agreed tolerances",
                delegated_authority="executes implementation work packages and escalates forecast tolerance breaches",
                assignment=_assignment_for_role(proposal_prefs, "team_manager"),
                active_models=active_models,
            )
        )
        added_nodes.append(node_id)
        assumptions.append("Project brief indicates implementation complexity, so a delegated implementation Team Manager node is proposed.")

    if any(keyword in joined for keyword in ("test", "tests", "quality", "wet-run", "validation", "verifica", "collaudo")):
        node_id = "assurance.validation_assurance"
        nodes.append(
            _role_node_from_template(
                node_id=node_id,
                role_type="project_assurance",
                label="Validation Assurance",
                parent_id="board.executive",
                level="assurance",
                accountability_boundary="independent validation of wet-run evidence, quality gates, and acceptance readiness",
                delegated_authority="reviews evidence independently; does not execute delivery work",
                assignment=_assignment_for_role(proposal_prefs, "project_assurance"),
                active_models=active_models,
            )
        )
        added_nodes.append(node_id)
        assumptions.append("Project brief mentions validation/testing, so an independent validation assurance node is proposed.")

    if any(keyword in joined for keyword in ("user", "utente", "account", "login", "auth", "browser", "ux", "interactive", "shell")):
        node_id = "board.user_acceptance"
        nodes.append(
            _role_node_from_template(
                node_id=node_id,
                role_type="senior_user",
                label="User Acceptance Delegate",
                parent_id="board.senior_user",
                level="direction",
                accountability_boundary="delegated user acceptance and usability feedback inside Senior User accountability",
                delegated_authority="reviews user-facing acceptance evidence and escalates adoption issues",
                assignment=_assignment_for_role(proposal_prefs, "senior_user"),
                active_models=active_models,
            )
        )
        added_nodes.append(node_id)
        assumptions.append("Project brief indicates user-facing behaviour, so a delegated user acceptance node is proposed.")

    if any(keyword in joined for keyword in ("rate-limit", "limit", "provider", "model", "handoff", "exception", "risk")):
        node_id = "authority.model_change_authority"
        nodes.append(
            _role_node_from_template(
                node_id=node_id,
                role_type="change_authority",
                label="Model Routing Change Authority",
                parent_id="board.executive",
                level="delegated_authority",
                accountability_boundary="delegated model/provider routing changes inside approved tolerances",
                delegated_authority="approves provider/model fallback and re-baseline decisions within delegated limits",
                assignment=_assignment_for_role(proposal_prefs, "change_authority"),
                active_models=active_models,
            )
        )
        added_nodes.append(node_id)
        assumptions.append("Project brief indicates provider/rate-limit or exception complexity, so a delegated change authority node is proposed.")

    tree = dict(base_tree)
    tree["command"] = "project tree propose"
    tree["source"] = "project_brief_local_rules"
    tree["nodes"] = nodes
    tree = _enrich_tree_with_local_execution_candidates(tree, local_execution)
    check = check_prince2_role_tree_payload(tree, proposal_prefs)
    matrix = build_prince2_role_matrix_payload(tree, proposal_prefs)
    gaps: list[dict[str, str]] = []
    for required in ("objective", "scope", "expected_outputs", "delivery_mode"):
        if not brief.get(required):
            gaps.append({"code": f"missing_{required}", "message": f"Project brief is missing {required}."})
    report = {
        "command": "project tree propose",
        "status": "ready_for_review" if not gaps and check.get("status") != "error" else "needs_clarification",
        "source": "local_rules",
        "ai_requested": bool(use_ai),
        "ai_assistance": {
            "attempted": False,
            "ok": None,
            "model": None,
            "account": None,
            "message": "AI assistance was not requested.",
            "valid_added_nodes": [],
            "rejected_nodes": [],
        },
        "project_brief": brief,
        "assumptions": assumptions,
        "added_nodes": added_nodes,
        "tree": tree,
        "local_execution": local_execution,
        "check": check,
        "matrix": matrix,
        "clarification_gaps": gaps,
        "approval_rule": "proposal only; user or Project Board must approve before persistence",
    }
    if use_ai:
        active_agent = agent or _configure_readonly_agent_for_workspace(config)
        report = _merge_ai_project_tree_proposal(active_agent, config, report)
    return report


def _project_tree_ai_prompt(design: dict[str, object], local_report: dict[str, object]) -> str:
    packet = {
        "purpose": "Design a proportional PRINCE2 role-tree proposal for Stagewarden.",
        "rules": [
            "Return only valid JSON.",
            "Do not persist or approve anything.",
            "Suggest only additional nodes that are justified by the project brief.",
            "Each node must have node_id, role_type, label, parent_id, level, accountability_boundary, and delegated_authority.",
            "Allowed role_type values: " + ", ".join(PRINCE2_ROLE_IDS),
            "Respect PRINCE2 accountability boundaries and keep each node context limited to its responsibility domain.",
            "If you propose custom context slices, include context_include/context_exclude and do not widen beyond the node domain.",
            "Include tolerance_boundary, validation_condition, and open_questions when useful for review.",
            "Prefer cheaper/local providers unless the node domain requires stronger reasoning.",
        ],
        "expected_schema": {
            "summary": "short rationale",
            "assumptions": ["short assumption"],
            "tree_patches": [
                {
                    "node_id": "lowercase.dot_or_underscore_id",
                    "role_type": "project_manager",
                    "label": "Node label",
                    "parent_id": "management.project_manager",
                    "level": "management",
                    "accountability_boundary": "bounded accountability/delegation statement",
                    "delegated_authority": "what this node may decide or execute",
                    "responsibility_domain": "bounded domain of competence",
                    "context_scope": "short context visibility scope",
                    "context_include": ["allowed context slice"],
                    "context_exclude": ["forbidden context slice"],
                    "tolerance_boundary": "delegated tolerance boundary",
                    "validation_condition": "how the node proves its work/decision",
                    "open_questions": ["review question"],
                }
            ],
        },
        "project_design_packet": design,
        "local_proposal": local_report,
    }
    return dumps_ascii(packet)


def _merge_ai_project_tree_proposal(agent: Agent, config: AgentConfig, local_report: dict[str, object]) -> dict[str, object]:
    report = copy.deepcopy(local_report)
    design = _project_design_report(agent, config)
    prompt = _project_tree_ai_prompt(design, local_report)
    _apply_model_preferences(agent, config)
    prefs = _load_model_preferences(config)
    model = _choose_cloud_priority_model(agent, prefs)
    account = prefs.account_for_model(model)
    result = agent.handoff.execute(format_run_model(model, prompt, account=account))
    assistance: dict[str, object] = {
        "attempted": True,
        "ok": False,
        "model": model,
        "account": account or None,
        "message": "",
        "valid_added_nodes": [],
        "rejected_nodes": [],
    }
    if not result.ok:
        assistance["message"] = result.error or "AI proposal model call failed; using local proposal only."
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_failed"
        return report
    try:
        payload = loads_text(result.output)
    except ValueError as exc:
        assistance["message"] = f"AI proposal output was not valid JSON: {exc}"
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_invalid"
        return report
    if not isinstance(payload, dict):
        assistance["message"] = "AI proposal output must be a JSON object."
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_invalid"
        return report

    prefs = _load_model_preferences(config)
    proposed_roles = prefs.propose_prince2_roles()
    merged_roles = dict(proposed_roles)
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    active_models = list(proposal_prefs.active_models() or proposal_prefs.enabled_models)
    tree = report["tree"] if isinstance(report.get("tree"), dict) else {}
    nodes = [dict(node) for node in tree.get("nodes", []) if isinstance(node, dict)]
    existing = {str(node.get("node_id", "")) for node in nodes}
    patches = payload.get("tree_patches", payload.get("nodes", []))
    if not isinstance(patches, list):
        patches = []
    rejected: list[dict[str, str]] = []
    added: list[str] = []
    for raw_patch in patches:
        if not isinstance(raw_patch, dict):
            rejected.append({"node_id": "unknown", "reason": "patch is not an object"})
            continue
        node_id = str(raw_patch.get("node_id", "")).strip().lower()
        role_type = str(raw_patch.get("role_type", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,80}", node_id):
            rejected.append({"node_id": node_id or "unknown", "reason": "invalid node_id"})
            continue
        if node_id in existing:
            rejected.append({"node_id": node_id, "reason": "duplicate node_id"})
            continue
        if role_type not in PRINCE2_ROLE_IDS:
            rejected.append({"node_id": node_id, "reason": "unsupported role_type"})
            continue
        parent_id = str(raw_patch.get("parent_id") or "management.project_manager").strip()
        node = _role_node_from_template(
            node_id=node_id,
            role_type=role_type,
            label=str(raw_patch.get("label") or PRINCE2_ROLE_LABELS.get(role_type, role_type)).strip(),
            parent_id=parent_id,
            level=str(raw_patch.get("level") or "delegated").strip(),
            accountability_boundary=str(raw_patch.get("accountability_boundary") or "delegated PRINCE2 accountability within agreed tolerances").strip(),
            delegated_authority=str(raw_patch.get("delegated_authority") or "executes delegated work and escalates tolerance breaches").strip(),
            assignment=_assignment_for_role(proposal_prefs, role_type),
            active_models=active_models,
        )
        context_include = raw_patch.get("context_include")
        context_exclude = raw_patch.get("context_exclude")
        if isinstance(context_include, list) or isinstance(context_exclude, list):
            base_rule = node.get("context_rule") if isinstance(node.get("context_rule"), dict) else {}
            node["context_rule"] = {
                "include": [str(item) for item in context_include] if isinstance(context_include, list) else list(base_rule.get("include", [])),
                "exclude": [str(item) for item in context_exclude] if isinstance(context_exclude, list) else list(base_rule.get("exclude", [])),
                "expansion_events": list(base_rule.get("expansion_events", [])),
            }
        for optional_key in ("responsibility_domain", "context_scope", "tolerance_boundary", "validation_condition"):
            value = str(raw_patch.get(optional_key, "")).strip()
            if value:
                node[optional_key] = value
        open_questions = raw_patch.get("open_questions")
        if isinstance(open_questions, list):
            node["open_questions"] = [str(item) for item in open_questions if str(item).strip()]
        nodes.append(node)
        existing.add(node_id)
        added.append(node_id)

    tree["nodes"] = nodes
    tree["source"] = "project_brief_local_rules_plus_ai"
    report["tree"] = tree
    report["source"] = "local_rules_plus_ai" if added else "local_rules_ai_no_changes"
    report["check"] = check_prince2_role_tree_payload(tree, proposal_prefs)
    report["matrix"] = build_prince2_role_matrix_payload(tree, proposal_prefs)
    report["added_nodes"] = list(dict.fromkeys([*report.get("added_nodes", []), *added]))
    assumptions = list(report.get("assumptions", [])) if isinstance(report.get("assumptions"), list) else []
    summary = str(payload.get("summary", "")).strip()
    if summary:
        assumptions.append(f"AI tree designer: {summary}")
    ai_assumptions = payload.get("assumptions", [])
    if isinstance(ai_assumptions, list):
        assumptions.extend(str(item).strip() for item in ai_assumptions if str(item).strip())
    report["assumptions"] = assumptions
    assistance["ok"] = True
    assistance["message"] = "AI proposal merged into review-only project tree." if added else "AI proposal returned no valid new nodes; using local proposal."
    assistance["valid_added_nodes"] = added
    assistance["rejected_nodes"] = rejected
    report["ai_assistance"] = assistance
    return report


def _render_project_tree_proposal(config: AgentConfig) -> str:
    report = _project_tree_proposal_report(config)
    return _render_project_tree_proposal_report(report)


def _render_project_tree_proposal_report(report: dict[str, object]) -> str:
    check = report["check"] if isinstance(report.get("check"), dict) else {}
    summary = check.get("summary", {}) if isinstance(check.get("summary"), dict) else {}
    lines = [
        "Project tree proposal:",
        f"- status: {report['status']}",
        f"- source: {report['source']}",
        f"- ai_requested: {str(bool(report.get('ai_requested'))).lower()}",
        f"- nodes: {summary.get('nodes', 0)} assigned={summary.get('assigned', 0)} unassigned={summary.get('unassigned', 0)}",
        f"- added_nodes: {', '.join(report['added_nodes']) or 'none'}",
        f"- approval_rule: {report['approval_rule']}",
        "AI assistance:",
    ]
    ai_assistance = report.get("ai_assistance") if isinstance(report.get("ai_assistance"), dict) else {}
    if ai_assistance:
        added = ai_assistance.get("valid_added_nodes", [])
        rejected = ai_assistance.get("rejected_nodes", [])
        lines.append(
            f"- attempted: {str(bool(ai_assistance.get('attempted'))).lower()} "
            f"ok={ai_assistance.get('ok')} model={ai_assistance.get('model') or 'none'} "
            f"account={ai_assistance.get('account') or 'none'}"
        )
        lines.append(f"- message: {ai_assistance.get('message') or 'none'}")
        lines.append(f"- valid_added_nodes: {', '.join(added) if isinstance(added, list) and added else 'none'}")
        lines.append(f"- rejected_nodes: {len(rejected) if isinstance(rejected, list) else 0}")
    else:
        lines.append("- none")
    local_execution = report.get("local_execution") if isinstance(report.get("local_execution"), dict) else {}
    lines.append("Local execution candidates:")
    if local_execution:
        ai = local_execution.get("ai_analysis", {}) if isinstance(local_execution.get("ai_analysis"), dict) else {}
        lines.append(
            f"- source: {local_execution.get('catalog_source', 'unknown')} "
            f"ai_attempted={str(bool(ai.get('attempted'))).lower()} ai_ok={ai.get('ok')}"
        )
        if local_execution.get("message"):
            lines.append(f"- recommendation: {local_execution.get('message')}")
        candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
        if candidates:
            for item in candidates:
                lines.append(
                    f"- {item.get('id')}: fit={item.get('agentic_fit')} risk={item.get('tool_support_risk')} "
                    f"best_for={', '.join(str(entry) for entry in item.get('best_for', [])) or 'none'}"
                )
        else:
            lines.append("- none")
    else:
        lines.append("- none")
    lines.append("Assumptions:")
    assumptions = report["assumptions"]
    if isinstance(assumptions, list) and assumptions:
        for item in assumptions:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("Clarification gaps:")
    gaps = report["clarification_gaps"]
    if isinstance(gaps, list) and gaps:
        for item in gaps:
            if isinstance(item, dict):
                lines.append(f"- {item.get('code')}: {item.get('message')}")
    else:
        lines.append("- none")
    lines.append("Node preview:")
    tree = report["tree"] if isinstance(report.get("tree"), dict) else {}
    for node in tree.get("nodes", []) if isinstance(tree.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        marker = "added" if node.get("node_id") in report["added_nodes"] else "base"
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        lines.append(
            f"- [{marker}] {node.get('node_id')} role={node.get('role_type')} "
            f"parent={node.get('parent_id') or 'none'} provider={assignment.get('provider') or 'none'} "
            f"provider_model={assignment.get('provider_model') or 'none'}"
        )
    return "\n".join(lines)


def _record_project_tree_proposal_action(config: AgentConfig, report: dict[str, object], *, task: str) -> None:
    _record_handoff_action(
        config,
        phase="project_tree_proposal_ai" if report.get("ai_requested") else "project_tree_proposal",
        summary="Project tree proposal generated for review; no baseline persisted.",
        task=task,
        details={
            "status": report.get("status"),
            "source": report.get("source"),
            "ai_requested": report.get("ai_requested"),
            "ai_assistance": report.get("ai_assistance"),
            "added_nodes": report.get("added_nodes", []),
            "clarification_gaps": report.get("clarification_gaps", []),
            "node_count": len(report.get("tree", {}).get("nodes", [])) if isinstance(report.get("tree"), dict) else 0,
        },
    )


def _approve_project_tree_proposal(
    config: AgentConfig,
    *,
    force: bool = False,
    proposal_report: dict[str, object] | None = None,
) -> dict[str, object]:
    report = proposal_report or _project_tree_proposal_report(config)
    gaps = report.get("clarification_gaps", [])
    if isinstance(gaps, list) and gaps and not force:
        _record_handoff_action(
            config,
            phase="project_tree_approval_blocked",
            summary="Project tree approval blocked by unresolved clarification gaps.",
            task="project tree approve",
            details={
                "clarification_gaps": gaps,
                "proposal_status": report.get("status"),
                "added_nodes": report.get("added_nodes", []),
            },
        )
        return {
            "command": "project tree approve",
            "status": "blocked",
            "message": "Project tree proposal has clarification gaps; resolve them or rerun with --force.",
            "clarification_gaps": gaps,
            "proposal": report,
        }
    prefs = _load_model_preferences(config)
    merged_roles = dict(prefs.propose_prince2_roles())
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    baseline = {
        "version": "1",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "source": "project_tree_approve_force" if force else "project_tree_approve",
        "status": "approved",
        "tree": _enrich_tree_with_local_execution_candidates(
            dict(report["tree"]) if isinstance(report.get("tree"), dict) else {},
            dict(report.get("local_execution", {})) if isinstance(report.get("local_execution"), dict) else {},
        ),
        "flow": build_prince2_role_flow(),
        "check": {},
        "matrix": {},
        "local_execution": dict(report.get("local_execution", {})) if isinstance(report.get("local_execution"), dict) else {},
        "proposal": {
            "source": report["source"],
            "assumptions": list(report.get("assumptions", [])) if isinstance(report.get("assumptions"), list) else [],
            "added_nodes": list(report.get("added_nodes", [])) if isinstance(report.get("added_nodes"), list) else [],
            "clarification_gaps": list(gaps) if isinstance(gaps, list) else [],
            "project_brief": dict(report.get("project_brief", {})) if isinstance(report.get("project_brief"), dict) else {},
            "ai_requested": bool(report.get("ai_requested")),
            "ai_assistance": dict(report.get("ai_assistance", {})) if isinstance(report.get("ai_assistance"), dict) else {},
            "forced": force,
        },
    }
    _refresh_prince2_role_tree_baseline_checks(baseline, proposal_prefs)
    _persist_prince2_role_tree_baseline(config, proposal_prefs, baseline)
    _record_handoff_action(
        config,
        phase="project_tree_approval",
        summary="Project tree proposal approved and persisted as PRINCE2 role-tree baseline.",
        task="project tree approve --force" if force else "project tree approve",
        details={
            "forced": force,
            "source": baseline["source"],
            "added_nodes": baseline["proposal"]["added_nodes"],
            "clarification_gaps": baseline["proposal"]["clarification_gaps"],
            "node_count": len(report.get("tree", {}).get("nodes", [])) if isinstance(report.get("tree"), dict) else 0,
        },
    )
    return {
        "command": "project tree approve",
        "status": "approved",
        "forced": force,
        "message": "Approved project-tree proposal as PRINCE2 role-tree baseline.",
        "baseline": _prince2_role_tree_baseline_report(config),
    }


def _render_project_tree_approval_report(report: dict[str, object], config: AgentConfig) -> str:
    lines = ["Project tree approval:"]
    lines.append(f"- status: {report['status']}")
    lines.append(f"- message: {report['message']}")
    if report["status"] == "blocked":
        lines.append("Clarification gaps:")
        gaps = report.get("clarification_gaps", [])
        if isinstance(gaps, list) and gaps:
            for item in gaps:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('code')}: {item.get('message')}")
        lines.append("- action: resolve missing project brief fields or rerun /project tree approve --force")
        return "\n".join(lines)
    lines.append(f"- forced: {str(bool(report.get('forced'))).lower()}")
    baseline = report.get("baseline") if isinstance(report.get("baseline"), dict) else {}
    lines.append(f"- baseline_status: {baseline.get('status', 'unknown')}")
    if isinstance(baseline.get("baseline"), dict):
        proposal = baseline["baseline"].get("proposal", {})
        added = proposal.get("added_nodes", []) if isinstance(proposal, dict) else []
        lines.append(f"- added_nodes: {', '.join(added) if isinstance(added, list) and added else 'none'}")
    return "\n".join(lines) + "\n" + _render_prince2_role_tree_baseline(config)


def _render_project_tree_approval(config: AgentConfig, *, force: bool = False) -> str:
    return _render_project_tree_approval_report(_approve_project_tree_proposal(config, force=force), config)


def _role_options() -> list[tuple[str, str]]:
    return [(role, f"{PRINCE2_ROLE_LABELS[role]} ({role})") for role in PRINCE2_ROLE_IDS]


def _role_tree_node_options(config: AgentConfig) -> list[tuple[str, str]]:
    prefs = _load_model_preferences(config)
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_menu")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    options: list[tuple[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        provider = assignment.get("provider", "unassigned") if isinstance(assignment, dict) and assignment else "unassigned"
        provider_model = assignment.get("provider_model", "none") if isinstance(assignment, dict) and assignment else "none"
        label = (
            f"{node.get('label', node_id)} [{node_id}] "
            f"role={node.get('role_type', 'unknown')} provider={provider} provider_model={provider_model}"
        )
        options.append((node_id, label))
    return options


def _role_tree_node_record(config: AgentConfig, node_id: str) -> dict[str, object] | None:
    prefs = _load_model_preferences(config)
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_node_context")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    for node in nodes:
        if isinstance(node, dict) and str(node.get("node_id", "")).strip() == node_id:
            return dict(node)
    return None


def _node_local_fallback_candidates(node: dict[str, object]) -> list[dict[str, object]]:
    pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
    routes = pools.get("fallback", []) if isinstance(pools.get("fallback"), list) else []
    local_routes = [dict(item) for item in routes if isinstance(item, dict) and item.get("provider") == "local"]
    local_routes.sort(key=lambda item: str(item.get("provider_model", "")))
    return local_routes


def _guided_role_node_assignment_context(config: AgentConfig, node_id: str, pool: str) -> str:
    node = _role_tree_node_record(config, node_id)
    if not node:
        return ""
    lines = [
        "Node assignment context:",
        f"- node_id: {node_id}",
        f"- role_type: {node.get('role_type', 'unknown')}",
        f"- level: {node.get('level', 'unknown')}",
        f"- selected_pool: {pool}",
    ]
    local_routes = _node_local_fallback_candidates(node)
    if local_routes:
        lines.append(
            "- recommended_local_fallbacks: "
            + ", ".join(
                f"{item.get('provider_model')}({((item.get('params') or {}).get('reasoning_effort') or 'provider-default')})"
                for item in local_routes
            )
        )
    else:
        lines.append("- recommended_local_fallbacks: none")
    return "\n".join(lines)


def _guided_provider_options_for_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    providers = list(prefs.enabled_models or list(SUPPORTED_MODELS))
    node = _role_tree_node_record(config, node_id)
    local_routes = _node_local_fallback_candidates(node) if node else []
    recommended_local = bool(pool == "fallback" and local_routes)
    ordered: list[str] = []
    if recommended_local and "local" in providers:
        ordered.append("local")
    for provider in providers:
        if provider not in ordered:
            ordered.append(provider)
    options: list[tuple[str, str]] = []
    for provider in ordered:
        label = provider
        if provider == "local" and local_routes:
            label += " | recommended for this node fallback"
        options.append((provider, label))
    return options


def _guided_provider_model_options_for_node(
    config: AgentConfig,
    *,
    provider: str,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    node = _role_tree_node_record(config, node_id)
    local_routes = _node_local_fallback_candidates(node) if node else []
    if provider == "local" and pool == "fallback" and local_routes:
        return [
            (
                str(item.get("provider_model", "")),
                f"{item.get('provider_model')} | recommended local fallback reasoning={((item.get('params') or {}).get('reasoning_effort') or 'provider-default')}",
            )
            for item in local_routes
            if str(item.get("provider_model", "")).strip()
        ]
    specs = list(provider_model_specs(provider))
    return [(spec.id, f"{spec.id} | {spec.label}") for spec in specs]


def _guided_provider_context(prefs: ModelPreferences, provider: str | None = None) -> str:
    enabled = ", ".join(prefs.enabled_models or []) or "none"
    preferred = prefs.preferred_model or "automatic"
    lines = [
        "Selection context:",
        f"- enabled_providers: {enabled}",
        f"- preferred_provider: {preferred}",
    ]
    active_accounts = []
    for item in prefs.enabled_models or []:
        account = (prefs.active_account_by_model or {}).get(item)
        if account:
            active_accounts.append(f"{item}={account}")
    blocked = []
    for item in prefs.enabled_models or []:
        until = (prefs.blocked_until_by_model or {}).get(item)
        if until:
            blocked.append(f"{item}:{until}")
    lines.append(f"- active_accounts: {', '.join(active_accounts) or 'none'}")
    lines.append(f"- blocked_providers: {', '.join(blocked) or 'none'}")
    if provider:
        provider_model = prefs.variant_for_model(provider) or provider_capability(provider).default_model
        params = prefs.params_for_model(provider)
        reasoning = params.get("reasoning_effort") or "provider-default"
        accounts = ", ".join((prefs.accounts_by_model or {}).get(provider, [])) or "none"
        lines.extend(
            [
                f"- selected_provider: {provider}",
                f"- current_provider_model: {provider_model}",
                f"- current_reasoning_effort: {reasoning}",
                f"- configured_accounts: {accounts}",
            ]
        )
    return "\n".join(lines)


def _route_pool_options() -> list[tuple[str, str]]:
    return [
        ("primary", "primary - route used for normal execution"),
        ("reviewer", "reviewer - independent review/assurance route"),
        ("fallback", "fallback - same-context route used if primary is unavailable"),
    ]


def _guided_role_context(role: str) -> str:
    return "\n".join(
        [
            "PRINCE2 role context:",
            f"- role: {PRINCE2_ROLE_LABELS[role]} ({role})",
            f"- responsibility: {PRINCE2_ROLE_AUTOMATION_RULES.get(role, 'controlled project work')}",
            f"- context_scope: {PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, 'controlled project work')}",
        ]
    )


def _guided_role_configure(
    *,
    requested_role: str | None,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role configuration is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role configure`."
    role = requested_role
    if role is None:
        role = _prompt_menu_choice(
            title="Choose PRINCE2 role:",
            options=_role_options(),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if role is None:
            return "Role configuration cancelled."
    if role not in PRINCE2_ROLE_IDS:
        return f"Unsupported PRINCE2 role '{role}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}"
    output_stream.write(_guided_role_context(role) + "\n")
    output_stream.write(_guided_provider_context(prefs) + "\n")
    mode = _prompt_menu_choice(
        title=f"Configure {PRINCE2_ROLE_LABELS[role]}:",
        options=[("auto", "Automatic proposal for this role"), ("manual", "Manual provider/model/account selection")],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if mode is None:
        return "Role configuration cancelled."
    if mode == "auto":
        assignment = prefs.propose_prince2_roles()[role]
        prefs.set_prince2_role_assignment(
            role,
            mode="auto",
            provider=str(assignment["provider"]),
            provider_model=str(assignment["provider_model"]),
            params=dict(assignment.get("params", {})),
            account=assignment.get("account"),
            source="auto_proposal",
        )
        _save_model_preferences(config, prefs)
        _sync_prince2_roles_to_handoff(config, prefs)
        return f"Assigned {PRINCE2_ROLE_LABELS[role]} automatically."
    provider = _prompt_menu_choice(
        title=f"Choose provider for {PRINCE2_ROLE_LABELS[role]}:",
        options=[(provider, provider) for provider in (prefs.enabled_models or list(SUPPORTED_MODELS))],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider is None:
        return "Role configuration cancelled."
    output_stream.write(_guided_provider_context(prefs, provider) + "\n")
    specs = list(provider_model_specs(provider))
    provider_model = _prompt_menu_choice(
        title=f"Choose provider-model for {provider}:",
        options=[(spec.id, f"{spec.id} | {spec.label}") for spec in specs],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Role configuration cancelled."
    spec = provider_model_spec(provider, provider_model)
    params: dict[str, str] = {}
    if spec is not None and spec.reasoning_efforts:
        reasoning = _prompt_menu_choice(
            title=f"Choose reasoning_effort for {provider}:{provider_model}:",
            options=[
                (effort, f"{effort}{' (default)' if effort == spec.reasoning_default else ''}")
                for effort in spec.reasoning_efforts
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning is None:
            return "Role configuration cancelled."
        params["reasoning_effort"] = reasoning
    account_options = [("", "none")]
    account_options.extend((account, account) for account in (prefs.accounts_by_model or {}).get(provider, []))
    account = _prompt_menu_choice(
        title=f"Choose account for {provider}:",
        options=account_options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if account is None:
        return "Role configuration cancelled."
    prefs.set_prince2_role_assignment(
        role,
        mode="manual",
        provider=provider,
        provider_model=provider_model,
        params=params,
        account=account or None,
        source="manual_menu",
    )
    _save_model_preferences(config, prefs)
    _sync_prince2_roles_to_handoff(config, prefs)
    params_text = " ".join(f"{key}={value}" for key, value in sorted(params.items()))
    return (
        f"Assigned {PRINCE2_ROLE_LABELS[role]}: provider={provider} "
        f"provider_model={provider_model} account={account or 'none'}"
        + (f" {params_text}" if params_text else "")
        + "."
    )


def _guided_role_add_child(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role node creation is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role add-child`."
    output_stream.write("PRINCE2 delegated node setup:\n")
    output_stream.write("- rule: delegated nodes inherit PRINCE2 role context but remain under parent accountability.\n")
    parent_id = _prompt_menu_choice(
        title="Choose parent role-tree node:",
        options=_role_tree_node_options(config),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if parent_id is None:
        return "Role node creation cancelled."
    role_type = _prompt_menu_choice(
        title="Choose delegated PRINCE2 role type:",
        options=_role_options(),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if role_type is None:
        return "Role node creation cancelled."
    output_stream.write("Optional node id, or blank for automatic id: ")
    output_stream.flush()
    response = input_stream.readline()
    if response == "":
        return "Role node creation cancelled."
    node_id = response.strip() or None
    try:
        child = _add_child_prince2_role_node(config, prefs, parent_id=parent_id, role_type=role_type, node_id=node_id)
    except ValueError as exc:
        return str(exc)
    return f"Added delegated PRINCE2 role node {child.get('node_id')} under {child.get('parent_id')}."


def _guided_role_assign(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role node assignment is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role assign`."
    output_stream.write("PRINCE2 role-tree node assignment:\n")
    output_stream.write("- rule: choose a specific node so provider fallback does not widen context.\n")
    node_id = _prompt_menu_choice(
        title="Choose role-tree node:",
        options=_role_tree_node_options(config),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if node_id is None:
        return "Role node assignment cancelled."
    pool = _prompt_menu_choice(
        title=f"Choose assignment pool for {node_id}:",
        options=_route_pool_options(),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if pool is None:
        return "Role node assignment cancelled."
    output_stream.write(_guided_role_node_assignment_context(config, node_id, pool) + "\n")
    output_stream.write(_guided_provider_context(prefs) + "\n")
    provider = _prompt_menu_choice(
        title=f"Choose provider for {node_id}:",
        options=_guided_provider_options_for_node(config, prefs, node_id=node_id, pool=pool),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider is None:
        return "Role node assignment cancelled."
    output_stream.write(_guided_provider_context(prefs, provider) + "\n")
    provider_model = _prompt_menu_choice(
        title=f"Choose provider-model for {provider}:",
        options=_guided_provider_model_options_for_node(config, provider=provider, node_id=node_id, pool=pool),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Role node assignment cancelled."
    spec = provider_model_spec(provider, provider_model)
    params: dict[str, str] = {}
    if spec is not None and spec.reasoning_efforts:
        reasoning = _prompt_menu_choice(
            title=f"Choose reasoning_effort for {provider}:{provider_model}:",
            options=[
                (effort, f"{effort}{' (default)' if effort == spec.reasoning_default else ''}")
                for effort in spec.reasoning_efforts
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning is None:
            return "Role node assignment cancelled."
        params["reasoning_effort"] = reasoning
    account_options = [("", "none")]
    account_options.extend((account, account) for account in (prefs.accounts_by_model or {}).get(provider, []))
    account = _prompt_menu_choice(
        title=f"Choose account for {provider}:",
        options=account_options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if account is None:
        return "Role node assignment cancelled."
    try:
        node = _assign_prince2_role_node(
            config,
            prefs,
            node_id=node_id,
            provider=provider,
            provider_model=provider_model,
            params=params,
            account=account or None,
            pool=pool,
        )
    except ValueError as exc:
        return str(exc)
    assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
    params_text = " ".join(f"{key}={value}" for key, value in sorted(params.items()))
    if pool == "primary":
        provider_display = assignment.get("provider")
        provider_model_display = assignment.get("provider_model")
        account_display = assignment.get("account") or "none"
    else:
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = pools.get(pool, []) if isinstance(pools.get(pool), list) else []
        route = routes[-1] if routes and isinstance(routes[-1], dict) else {}
        provider_display = route.get("provider")
        provider_model_display = route.get("provider_model")
        account_display = route.get("account") or "none"
    return (
        f"Assigned role node {node.get('node_id')}: provider={provider_display} "
        f"provider_model={provider_model_display} account={account_display}"
        + (f" {params_text}" if params_text else "")
        + f" pool={pool}"
        + "."
    )


def _guided_roles_setup(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        prefs.apply_prince2_role_proposal()
        _save_model_preferences(config, prefs)
        _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_auto")
        return "Applied automatic PRINCE2 role proposal."
    choice = _prompt_menu_choice(
        title="PRINCE2 role setup:",
        options=[
            ("auto", "Automatic proposal based on available providers/accounts/models"),
            ("manual", "Manual configuration role by role"),
            ("show", "Show current assignments only"),
        ],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if choice is None:
        return "Role setup cancelled."
    if choice == "show":
        return _render_prince2_roles(config)
    if choice == "auto":
        prefs.apply_prince2_role_proposal()
        _save_model_preferences(config, prefs)
        _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_auto")
        return (
            "Applied automatic PRINCE2 role proposal.\n"
            + _render_prince2_roles(config)
            + "\n"
            + _render_prince2_role_tree_baseline(config)
        )
    while True:
        role = _prompt_menu_choice(
            title="Choose role to configure, or `done`:",
            options=[("done", "done")] + _role_options(),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if role is None or role == "done":
            break
        output_stream.write(
            _guided_role_configure(
                requested_role=role,
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
            + "\n"
        )
        output_stream.flush()
        prefs = _load_model_preferences(config)
    local_execution = _local_execution_candidates_report(config)
    candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    if candidates:
        output_stream.write(
            "Recommended local fallback candidates discovered: "
            + ", ".join(str(item.get("id", "")) for item in candidates if str(item.get("id", "")).strip())
            + "\n"
        )
        preload = _prompt_menu_choice(
            title="Approve baseline with recommended local delivery fallbacks now?",
            options=[
                ("yes", "Yes - approve baseline and preload recommended local fallback routes"),
                ("no", "No - keep only role assignments for now"),
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if preload is None:
            return "Role setup cancelled."
        if preload == "yes":
            _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_manual_local_fallbacks")
            return (
                "Role setup completed with approved baseline and recommended local delivery fallbacks.\n"
                + _render_prince2_roles(config)
                + "\n"
                + _render_prince2_role_tree_baseline(config)
            )
    return "Role setup completed.\n" + _render_prince2_roles(config)


def _handle_role_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "project" and parts[1:2] == ["start"] and len(parts) in {2, 3}:
        if len(parts) == 3 and parts[2] != "--ai":
            return "Usage: project start [--ai]"
        prefs = _load_model_preferences(config)
        return _render_project_start(agent, config, prefs, force_ai=len(parts) == 3)
    if parts[0] == "roles":
        prefs = _load_model_preferences(config)
        if len(parts) == 1:
            _sync_prince2_roles_to_handoff(config, prefs)
            return _render_prince2_roles(config)
        if len(parts) == 2 and parts[1] == "domains":
            return _render_prince2_role_domains()
        if len(parts) == 3 and parts[1] == "context":
            return _render_prince2_role_context(config, parts[2])
        if len(parts) == 2 and parts[1] == "tree":
            return _render_prince2_role_tree(config)
        if len(parts) == 3 and parts[1] == "tree" and parts[2] == "approve":
            _approve_prince2_role_tree_baseline(config, prefs, source="roles_tree_approve")
            return "Approved PRINCE2 role-tree baseline.\n" + _render_prince2_role_tree_baseline(config)
        if len(parts) == 2 and parts[1] == "baseline":
            return _render_prince2_role_tree_baseline(config)
        if len(parts) == 3 and parts[1] == "baseline" and parts[2] == "matrix":
            return _render_prince2_role_tree_baseline_matrix(config)
        if len(parts) in {2, 3} and parts[1] == "messages":
            return _render_prince2_role_messages(config, node_id=parts[2] if len(parts) == 3 else None)
        if len(parts) == 2 and parts[1] == "runtime":
            return _render_prince2_role_runtime(config)
        if len(parts) == 2 and parts[1] == "active":
            return _render_prince2_role_active(config)
        if len(parts) == 2 and parts[1] == "control":
            return _render_prince2_role_control(config)
        if len(parts) == 2 and parts[1] == "queues":
            return _render_prince2_role_queues(config)
        if len(parts) in {2, 3} and parts[1] == "tick":
            max_nodes = None
            if len(parts) == 3:
                try:
                    max_nodes = int(parts[2])
                except ValueError:
                    return "Usage: roles tick [max_nodes]"
            result = _tick_prince2_role_runtime(config, max_nodes=max_nodes)
            return (
                f"Batch advanced PRINCE2 runtime: processed={result.get('processed')} "
                f"woken={result.get('woken')} progressed={result.get('progressed')} skipped={result.get('skipped')}.\n"
                + _render_prince2_role_runtime(config)
            )
        if len(parts) == 2 and parts[1] == "check":
            return _render_prince2_role_check(config)
        if len(parts) == 2 and parts[1] == "flow":
            return _render_prince2_role_flow()
        if len(parts) == 2 and parts[1] == "matrix":
            return _render_prince2_role_matrix(config)
        if len(parts) == 2 and parts[1] == "propose":
            prefs.apply_prince2_role_proposal()
            _save_model_preferences(config, prefs)
            _approve_prince2_role_tree_baseline(config, prefs, source="roles_propose")
            _apply_model_preferences(agent, config)
            return (
                "Applied automatic PRINCE2 role proposal.\n"
                + _render_prince2_roles(config)
                + "\n"
                + _render_prince2_role_tree_baseline(config)
            )
        if len(parts) == 2 and parts[1] == "setup":
            return _guided_roles_setup(
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        return "Usage: roles | roles domains | roles context <node_id> | roles tree | roles tree approve | roles baseline | roles baseline matrix | roles runtime | roles active | roles control | roles queues | roles messages [node_id] | roles tick [max_nodes] | roles check | roles flow | roles matrix | roles propose | roles setup"
    if parts[0] == "role":
        prefs = _load_model_preferences(config)
        if len(parts) in {4, 5} and parts[1] == "add-child":
            try:
                child = _add_child_prince2_role_node(
                    config,
                    prefs,
                    parent_id=parts[2],
                    role_type=parts[3],
                    node_id=parts[4] if len(parts) == 5 else None,
                )
            except ValueError as exc:
                return str(exc)
            return (
                f"Added delegated PRINCE2 role node {child.get('node_id')} under {child.get('parent_id')}.\n"
                + _render_prince2_role_tree_baseline(config)
            )
        if len(parts) == 2 and parts[1] == "add-child":
            return _guided_role_add_child(
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if len(parts) >= 5 and parts[1] == "assign":
            extra_params: dict[str, str] = {}
            account = None
            pool = "primary"
            for token in parts[5:]:
                key, separator, value = token.partition("=")
                if not separator:
                    return "Usage: role assign <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]"
                if key == "account":
                    account = value or None
                elif key == "pool":
                    pool = value
                else:
                    extra_params[key] = value
            try:
                node = _assign_prince2_role_node(
                    config,
                    prefs,
                    node_id=parts[2],
                    provider=parts[3],
                    provider_model=parts[4],
                    params=extra_params,
                    account=account,
                    pool=pool,
                )
            except ValueError as exc:
                return str(exc)
            assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
            if pool == "primary":
                return (
                    f"Assigned role node {node.get('node_id')}: provider={assignment.get('provider')} "
                    f"provider_model={assignment.get('provider_model')} account={assignment.get('account') or 'none'} pool=primary."
                )
            pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
            routes = pools.get(pool, []) if isinstance(pools.get(pool, []), list) else []
            route = routes[-1] if routes and isinstance(routes[-1], dict) else {}
            return (
                f"Assigned role node {node.get('node_id')}: provider={route.get('provider')} "
                f"provider_model={route.get('provider_model')} account={route.get('account') or 'none'} pool={pool}."
            )
        if len(parts) == 2 and parts[1] == "assign":
            return _guided_role_assign(
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if len(parts) >= 6 and parts[1] == "message":
            payload_scope: list[str] = []
            evidence_refs: list[str] = []
            summary = None
            for token in parts[5:]:
                key, separator, value = token.partition("=")
                if not separator:
                    return "Usage: role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>]"
                if key == "payload":
                    payload_scope = [item.strip() for item in value.split(",") if item.strip()]
                elif key == "evidence":
                    evidence_refs = [item.strip() for item in value.split(",") if item.strip()]
                elif key == "summary":
                    summary = value.replace("_", " ").strip()
            if not payload_scope:
                return "Usage: role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>]"
            try:
                message = _send_prince2_role_message(
                    config,
                    source_node=parts[2],
                    target_node=parts[3],
                    edge_id=parts[4],
                    payload_scope=payload_scope,
                    evidence_refs=evidence_refs,
                    summary=summary,
                )
            except ValueError as exc:
                _record_handoff_action(
                    config,
                    phase="role_message_blocked",
                    task=f"role message {parts[2]} {parts[3]} {parts[4]}",
                    summary=str(exc),
                    details={
                        "source_node": parts[2],
                        "target_node": parts[3],
                        "edge_id": parts[4],
                        "payload_scope": list(payload_scope),
                    },
                )
                return str(exc)
            return (
                f"Queued PRINCE2 node message {message.get('message_id')} "
                f"{parts[2]} -> {parts[3]} edge={parts[4]}.\n"
                + _render_prince2_role_messages(config, node_id=parts[3])
            )
        if len(parts) >= 4 and parts[1] == "wait":
            reason = None
            wake_triggers = None
            for token in parts[3:]:
                key, separator, value = token.partition("=")
                if not separator:
                    return "Usage: role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]"
                if key == "reason":
                    reason = value.replace("_", " ").strip()
                elif key == "wake":
                    wake_triggers = [item.strip() for item in value.split(",") if item.strip()]
            if not reason:
                return "Usage: role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]"
            try:
                node = _set_prince2_role_node_waiting(
                    config,
                    node_id=parts[2],
                    reason=reason,
                    wake_triggers=wake_triggers,
                )
            except ValueError as exc:
                return str(exc)
            return (
                f"Node {node.get('node_id')} is now waiting.\n"
                + _render_prince2_role_runtime(config)
            )
        if len(parts) >= 4 and parts[1] == "wake":
            trigger = None
            for token in parts[3:]:
                key, separator, value = token.partition("=")
                if not separator:
                    return "Usage: role wake <node_id> trigger=<name>"
                if key == "trigger":
                    trigger = value.strip()
            if not trigger:
                return "Usage: role wake <node_id> trigger=<name>"
            try:
                node = _wake_prince2_role_node(
                    config,
                    node_id=parts[2],
                    trigger=trigger,
                )
            except ValueError as exc:
                return str(exc)
            return (
                f"Node {node.get('node_id')} woke with trigger {trigger}.\n"
                + _render_prince2_role_runtime(config)
            )
        if len(parts) == 3 and parts[1] == "tick":
            try:
                result = _tick_prince2_role_node(config, node_id=parts[2])
            except ValueError as exc:
                return str(exc)
            return (
                f"Node {result.get('node_id')} advanced to {result.get('state')}.\n"
                + _render_prince2_role_messages(config, node_id=parts[2])
            )
        if len(parts) >= 2 and parts[1] == "configure":
            if len(parts) > 3:
                return "Usage: role configure [role]"
            requested_role = parts[2] if len(parts) == 3 else None
            return _guided_role_configure(
                requested_role=requested_role,
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if len(parts) == 3 and parts[1] == "clear":
            role = parts[2]
            if role not in PRINCE2_ROLE_IDS:
                return f"Unsupported PRINCE2 role '{role}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}"
            prefs.clear_prince2_role_assignment(role)
            _save_model_preferences(config, prefs)
            _sync_prince2_roles_to_handoff(config, prefs)
            return f"Cleared PRINCE2 role assignment for {PRINCE2_ROLE_LABELS[role]}."
        return "Usage: role configure [role] | role clear <role> | role add-child <parent_node> <role_type> [node_id] | role assign <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>] | role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>] | role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>] | role wake <node_id> trigger=<name> | role tick <node_id> | roles tick [max_nodes]"
    return None


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


def _git_output(cwd: Path, *args: str) -> tuple[bool, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, output


def _git_completed(cwd: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _normalize_git_url(url: str | None) -> str:
    clean = str(url or "").strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    return clean


def _sources_status_report(config: AgentConfig, *, strict: bool = False) -> dict[str, object]:
    manifest = _source_reference_manifest(config)
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
            head_ok, head = _git_output(local_path, "rev-parse", "--short", "HEAD")
            remote_ok, remote = _git_output(local_path, "remote", "get-url", "origin")
            shallow_ok, shallow = _git_output(local_path, "rev-parse", "--is-shallow-repository")
            message = "ok" if head_ok and remote_ok and _normalize_git_url(remote) == _normalize_git_url(entry["upstream"]) else "metadata mismatch"
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
                "upstream_matches": bool(remote_ok and _normalize_git_url(remote) == _normalize_git_url(entry["upstream"])),
                "shallow": (shallow == "true") if shallow_ok else None,
                "status": "OK" if message == "ok" else ("FAIL" if strict else "WARN"),
                "message": message,
            }
        )
    return {
        "command": "sources status --strict" if strict else "sources status",
        "manifest": "docs/source_references.md",
        "strict": strict,
        "count": len(items),
        "ok": bool(items) and all(item["status"] == "OK" for item in items),
        "items": items,
    }


def _render_sources_status(config: AgentConfig, *, strict: bool = False) -> str:
    report = _sources_status_report(config, strict=strict)
    lines = ["External source references:"]
    if strict:
        lines.append("- strict: yes")
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
    status = _sources_status_report(config)
    items: list[dict[str, object]] = []
    for item in status["items"]:
        if not item.get("exists") or not item.get("git_repository"):
            items.append({**item, "updated": False, "ok": False, "update_message": "missing or not a git repository"})
            continue
        local_path = config.workspace_root / str(item["path"])
        before_ok, before = _git_output(local_path, "rev-parse", "--short", "HEAD")
        completed = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=local_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        after_ok, after = _git_output(local_path, "rev-parse", "--short", "HEAD")
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
        "ok": bool(items) and all(bool(item.get("ok")) for item in items),
        "items": items,
    }
    _record_handoff_action(
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
    root = config.workspace_root
    inside_ok, inside = _git_output(root, "rev-parse", "--is-inside-work-tree")
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
        fetched = _git_completed(root, "fetch", "--quiet", "--prune", timeout=60)
        fetch_message = fetched.stdout.strip() or fetched.stderr.strip() or "fetch completed"
        if fetched.returncode != 0:
            return {
                "command": "update check",
                "ok": False,
                "repository": True,
                "message": fetch_message,
                "update_available": False,
            }
    branch_ok, branch = _git_output(root, "branch", "--show-current")
    head_ok, head = _git_output(root, "rev-parse", "--short", "HEAD")
    upstream_ok, upstream = _git_output(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_head_ok, upstream_head = (False, "")
    ahead = behind = 0
    if upstream_ok:
        upstream_head_ok, upstream_head = _git_output(root, "rev-parse", "--short", upstream)
        counts_ok, counts = _git_output(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts_ok:
            parts = counts.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    dirty_ok, dirty = _git_output(root, "status", "--porcelain")
    remote_ok, remote = _git_output(root, "remote", "get-url", "origin")
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
    pulled = _git_completed(config.workspace_root, "pull", "--ff-only", timeout=60)
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
    _record_handoff_action(
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


def _render_extensions_report(report: dict[str, object]) -> str:
    lines = ["Stagewarden extensions:"]
    lines.append(f"- root: {report.get('root', '.stagewarden/extensions')}")
    lines.append(f"- ok: {str(bool(report.get('ok'))).lower()}")
    lines.append(f"- count: {report.get('count', 0)}")
    extensions = report.get("extensions", [])
    if isinstance(extensions, list) and extensions:
        for item in extensions:
            if not isinstance(item, dict):
                continue
            caps = ", ".join(str(cap) for cap in item.get("capabilities", []) or []) or "none"
            execution = str(item.get("execution") or "unknown")
            schema_version = str(item.get("schema_version") or "unknown")
            lines.append(
                f"- {item.get('name')}: {'OK' if item.get('ok') else 'FAIL'} "
                f"version={item.get('version') or 'unknown'} schema={schema_version} "
                f"execution={execution} path={item.get('path')} capabilities={caps}"
            )
            entrypoints = item.get("entrypoints", {})
            if isinstance(entrypoints, dict) and entrypoints:
                rendered = ", ".join(f"{key}={value}" for key, value in sorted(entrypoints.items()))
                lines.append(f"  entrypoints={rendered}")
            missing = item.get("missing_entrypoints", [])
            if isinstance(missing, list) and missing:
                lines.append(f"  missing_entrypoints={', '.join(str(value) for value in missing)}")
            if item.get("message") and item.get("message") != "ok":
                lines.append(f"  message={item['message']}")
    return "\n".join(lines)


def _handle_extension_command(command: str, config: AgentConfig) -> str | None:
    if command == "extensions":
        return _render_extensions_report(discover_extensions(config.workspace_root))
    if command.startswith("extension scaffold "):
        name = command.split(maxsplit=2)[2]
        try:
            report = scaffold_extension(config.workspace_root, name)
        except ValueError as exc:
            return f"Extension scaffold failed: {exc}"
        _record_handoff_action(
            config,
            phase="extension_scaffold",
            task=command,
            summary=f"Created extension scaffold {report['name']}.",
            details=report,
        )
        return (
            "Extension scaffold created:\n"
            f"- name: {report['name']}\n"
            f"- path: {report['path']}\n"
            f"- manifest: {report['manifest']}\n"
            "- execution: disabled-by-default"
        )
    if command.startswith("extension ") or command.startswith("extensions "):
        return "Usage: extensions | extension scaffold <name>"
    return None


def _external_io_result_to_text(result: ExternalIOResult) -> str:
    lines = [f"{result.command}: {'OK' if result.ok else 'FAIL'} {result.message}"]
    if result.url:
        lines.append(f"- url: {result.url}")
    if result.path:
        lines.append(f"- path: {result.path}")
    if result.bytes_written:
        lines.append(f"- bytes: {result.bytes_written}")
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


def _record_external_io_evidence(config: AgentConfig, result: ExternalIOResult, *, task: str) -> None:
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
        error_type=None if result.ok else "external_io_error",
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
    _record_handoff_action(
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
            "content_type": result.content_type,
            "error": result.error,
            "items": result.items or [],
        },
    )


def _external_io_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    result = _external_io_execute(command, config)
    if result is None:
        return None
    _record_external_io_evidence(config, result, task=command)
    return result.as_dict()


def _handle_external_io_command(command: str, config: AgentConfig) -> str | None:
    result = _external_io_execute(command, config)
    if result is None:
        return None
    _record_external_io_evidence(config, result, task=command)
    return _external_io_result_to_text(result)


def _external_io_execute(command: str, config: AgentConfig) -> ExternalIOResult | None:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return ExternalIOResult(ok=False, command="external io", message=str(exc), error=str(exc))
    if not parts:
        return None
    tool = ExternalIOTool(config.workspace_root)
    if parts[0] == "checksum" and len(parts) == 2:
        return tool.checksum(parts[1])
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
    if parts[:2] == ["web", "search"] and len(parts) >= 3:
        endpoint = os.environ.get("STAGEWARDEN_WEB_SEARCH_ENDPOINT")
        return tool.web_search(" ".join(parts[2:]), endpoint=endpoint)
    if parts[0] in {"download", "checksum", "compress", "archive", "web"}:
        return ExternalIOResult(
            ok=False,
            command=parts[0],
            message="Usage: web search <query> | download <url> [path] [--max-bytes N] | checksum <path> | compress <path> [target.gz] | archive verify <path.gz>",
            error="usage",
        )
    return None


def _provider_limit_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    status = agent.router.status()
    memory = MemoryStore.load(config.memory_path)
    providers: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        if model not in status["enabled_models"]:
            continue
        provider_model, selection_mode, _default_model = _provider_model_display(prefs, model)
        accounts = list((prefs.accounts_by_model or {}).get(model, []))
        active_account = prefs.account_for_model(model)
        blocked_model_until = status["blocked_until_by_model"].get(model)
        blocked_accounts = [
            {
                "name": account,
                "blocked_until": (prefs.blocked_until_by_account or {}).get(account_key(model, account)),
                "last_limit_message": (prefs.last_limit_message_by_account or {}).get(account_key(model, account)),
                "last_limit_reason": classify_limit_reason(
                    (prefs.last_limit_message_by_account or {}).get(account_key(model, account)),
                    fallback=None,
                ),
                "active": account == active_account,
                "limit_snapshot": (prefs.provider_limit_snapshot_by_account or {}).get(account_key(model, account)),
            }
            for account in accounts
            if (prefs.blocked_until_by_account or {}).get(account_key(model, account))
        ]
        last_attempt = next((item for item in reversed(memory.attempts) if item.model == model), None)
        last_success = next((item for item in reversed(memory.attempts) if item.model == model and item.success), None)
        last_limit_message = (prefs.last_limit_message_by_model or {}).get(model)
        last_error_reason = classify_limit_reason(
            last_limit_message,
            fallback=(last_attempt.error_type or "unknown") if last_attempt is not None and not last_attempt.success else None,
        )
        providers.append(
            {
                "provider": model,
                "enabled": model in status["enabled_models"],
                "active": model in status["active_models"],
                "preferred": status["preferred_model"] == model,
                "variant": prefs.variant_for_model(model) or "provider-default",
                "provider_model": provider_model,
                "provider_model_selection": selection_mode,
                "provider_model_params": _provider_model_params_display(prefs, model),
                "active_account": active_account or "none",
                "blocked_until": blocked_model_until,
                "last_limit_message": last_limit_message,
                "limit_snapshot": (prefs.provider_limit_snapshot_by_model or {}).get(model),
                "blocked_accounts": blocked_accounts,
                "last_error_reason": last_error_reason,
                "last_attempt": None
                if last_attempt is None
                else {
                    "step": last_attempt.step_id,
                    "status": "ok" if last_attempt.success else f"failed:{last_attempt.error_type or 'unknown'}",
                    "account": last_attempt.account or "none",
                    "variant": last_attempt.variant or "provider-default",
                },
                "last_success": None
                if last_success is None
                else {
                    "step": last_success.step_id,
                    "account": last_success.account or "none",
                    "variant": last_success.variant or "provider-default",
                },
            }
        )
    return {
        "providers": providers,
    }


def _provider_limit_summary_report(provider_limits: dict[str, object]) -> dict[str, object]:
    providers = [
        item
        for item in provider_limits.get("providers", [])
        if isinstance(item, dict)
    ]
    blocked_models = [str(item["provider"]) for item in providers if item.get("blocked_until")]
    stale_models = [
        str(item["provider"])
        for item in providers
        if bool(_provider_limit_windows(item).get("stale"))
    ]
    blocked_accounts = [
        f"{item['provider']}:{account['name']}"
        for item in providers
        for account in item.get("blocked_accounts", [])
        if isinstance(account, dict) and account.get("blocked_until")
    ]
    stale_accounts = [
        f"{item['provider']}:{account['name']}"
        for item in providers
        for account in item.get("blocked_accounts", [])
        if isinstance(account, dict)
        and isinstance(account.get("limit_snapshot"), dict)
        and _provider_limit_snapshot_is_stale(account["limit_snapshot"].get("captured_at"))
    ]
    last_errors = [
        f"{item['provider']}={item['last_error_reason']}"
        for item in providers
        if item.get("last_error_reason")
    ]
    active_routes = [
        f"{item['provider']}:{item['active_account']}/{item['variant']}"
        for item in providers
    ]
    return {
        "providers_count": len(providers),
        "blocked_models": blocked_models,
        "stale_models": stale_models,
        "blocked_accounts": blocked_accounts,
        "stale_accounts": stale_accounts,
        "last_errors": last_errors,
        "routes": active_routes,
    }


def _render_provider_limit_status(agent: Agent, config: AgentConfig) -> str:
    report = _provider_limit_status_report(agent, config)
    lines = ["Provider limit status:"]
    if not report["providers"]:
        lines.append("- none")
        return "\n".join(lines)
    for item in report["providers"]:
        blocked = f" blocked-until={item['blocked_until']}" if item["blocked_until"] else ""
        preferred = " preferred" if item["preferred"] else ""
        active = " active" if item["active"] else " inactive"
        lines.append(
            f"- {item['provider']}: enabled{active}{preferred}{blocked} "
            f"provider_model={item['provider_model']} selection={item['provider_model_selection']} "
            f"active_account={item['active_account']}"
        )
        if item["last_error_reason"]:
            lines.append(f"  last_error_reason={item['last_error_reason']}")
        if item["last_limit_message"]:
            lines.append(f"  last_limit_message={item['last_limit_message']}")
        last_attempt = item["last_attempt"]
        if isinstance(last_attempt, dict):
            lines.append(
                f"  last_attempt: step={last_attempt['step']} status={last_attempt['status']} "
                f"account={last_attempt['account']} provider_model={last_attempt['variant']}"
            )
        last_success = item["last_success"]
        if isinstance(last_success, dict):
            lines.append(
                f"  last_success: step={last_success['step']} account={last_success['account']} "
                f"provider_model={last_success['variant']}"
            )
        blocked_accounts = item["blocked_accounts"]
        for blocked_account in blocked_accounts:
            active_account_tag = " active-account" if blocked_account["active"] else ""
            lines.append(
                f"  blocked_account {blocked_account['name']}:{active_account_tag} "
                f"blocked-until={blocked_account['blocked_until']}"
            )
            if blocked_account["last_limit_reason"]:
                lines.append(f"    last_limit_reason={blocked_account['last_limit_reason']}")
            if blocked_account["last_limit_message"]:
                lines.append(f"    last_limit_message={blocked_account['last_limit_message']}")
    return "\n".join(lines)


def _model_limits_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    report = _provider_limit_status_report(agent, config)
    return {
        "command": "model limits",
        "summary": _provider_limit_summary_report(report),
        "providers": [
            {
                "provider": item["provider"],
                "account": item["active_account"],
                "variant": item["variant"],
                "provider_model": item["provider_model"],
                "provider_model_selection": item["provider_model_selection"],
                "provider_model_params": item["provider_model_params"],
                **_provider_limit_windows(item),
                "blocked_accounts": [
                    {
                        "name": account["name"],
                        "active": account["active"],
                        "blocked_until": account["blocked_until"],
                        "reason": account["last_limit_reason"],
                        "snapshot": account["limit_snapshot"],
                    }
                    for account in item["blocked_accounts"]
                ],
            }
            for item in report["providers"]
        ],
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


def _record_limit_message(
    config: AgentConfig,
    prefs: ModelPreferences,
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
    _save_model_preferences(config, prefs)
    target = f"{model}:{account}" if account else model
    if until:
        return f"Recorded limit snapshot for {target}; blocked until {until}."
    return f"Recorded limit snapshot for {target}; no reset time detected."


def _clear_limit_snapshot(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    model: str,
    account: str | None = None,
) -> str:
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
        _save_model_preferences(config, prefs)
        return f"Cleared limit snapshot for {model}:{account}."
    prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
    prefs.blocked_until_by_model.pop(model, None)
    prefs.last_limit_message_by_model = dict(prefs.last_limit_message_by_model or {})
    prefs.last_limit_message_by_model.pop(model, None)
    prefs.provider_limit_snapshot_by_model = dict(prefs.provider_limit_snapshot_by_model or {})
    prefs.provider_limit_snapshot_by_model.pop(model, None)
    _save_model_preferences(config, prefs)
    return f"Cleared limit snapshot for {model}."


def _provider_limit_windows(item: dict[str, object]) -> dict[str, object]:
    blocked_until = item.get("blocked_until")
    reason = item.get("last_error_reason")
    snapshot = item.get("limit_snapshot")
    base = {
        "status": "blocked" if blocked_until else "available",
        "reason": reason,
        "blocked_until": blocked_until,
        "primary_window": None,
        "secondary_window": None,
        "credits": None,
        "rate_limit_type": reason,
        "utilization": None,
        "overage_status": None,
        "overage_resets_at": None,
        "overage_disabled_reason": None,
        "stale": False,
        "captured_at": None,
    }
    if isinstance(snapshot, dict):
        for key in base:
            if snapshot.get(key) is not None:
                base[key] = snapshot[key]
        base["stale"] = _provider_limit_snapshot_is_stale(base.get("captured_at"))
        if blocked_until:
            base["status"] = "blocked"
            base["blocked_until"] = blocked_until
        if reason:
            base["reason"] = reason
        if base["rate_limit_type"] is None:
            base["rate_limit_type"] = base["reason"]
    return base


def _provider_limit_snapshot_is_stale(captured_at: object, *, stale_after_minutes: int = 15) -> bool:
    if not captured_at:
        return False
    try:
        captured = datetime.fromisoformat(str(captured_at))
    except ValueError:
        return True
    now = datetime.now(tz=captured.tzinfo) if captured.tzinfo is not None else datetime.now()
    if captured > now:
        return False
    return (now - captured).total_seconds() > stale_after_minutes * 60


def _status_dashboard_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    status = _status_report(agent, config)
    provider_limits = status["provider_limits"]
    model_report = status["models"]
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
    return {
        "command": "status",
        "view": "full",
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
        "limits": [
            {
                "provider": item["provider"],
                "account": item["active_account"],
                "variant": item["variant"],
                **_provider_limit_windows(item),
            }
            for item in providers
        ],
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


def _render_status_full(agent: Agent, config: AgentConfig) -> str:
    report = _status_dashboard_report(agent, config)
    lines = [
        "Stagewarden full status:",
        "Identity:",
        f"- workspace: {report['identity']['workspace']}",
        f"- mode: {report['identity']['mode']}",
        f"- python: {report['identity']['python']}",
        "Focus:",
        f"- task: {report['focus']['task']}",
        f"- current_step: {report['focus']['current_step']}",
        f"- next_action: {report['focus']['next_action']}",
        (
            f"- active_route: provider={report['focus']['active_provider'] or 'none'} "
            f"account={report['focus']['active_account']} "
            f"provider_model={report['focus']['active_provider_model'] or 'none'}"
        ),
        "Model:",
        f"- preferred_provider: {report['model']['preferred_provider']}",
        f"- active_provider: {report['model']['active_provider'] or 'none'}",
        f"- active_provider_model: {report['model']['active_provider_model'] or 'none'}",
        (
            "- active_provider_model_params: "
            + ",".join(f"{key}={value}" for key, value in sorted(report["model"]["active_provider_model_params"].items()))
            if report["model"]["active_provider_model_params"]
            else "- active_provider_model_params: none"
        ),
        f"- enabled_providers: {', '.join(report['model']['enabled']) or 'none'}",
        "Account:",
    ]
    for provider, account in report["account"]["active_accounts"].items():
        lines.append(f"- {provider}: active_account={account}")
    lines.append("Limits:")
    for item in report["limits"]:
        blocked = f" blocked_until={item['blocked_until']}" if item["blocked_until"] else ""
        reason = f" reason={item['reason']}" if item["reason"] else ""
        stale = " stale=true" if item["stale"] else ""
        lines.append(f"- {item['provider']}: {item['status']}{blocked}{reason}{stale}")
    summary = report["limits_summary"]
    lines.append(
        "- limits_summary: "
        f"blocked_models={','.join(summary['blocked_models']) if summary['blocked_models'] else 'none'} "
        f"stale_models={','.join(summary['stale_models']) if summary['stale_models'] else 'none'} "
        f"blocked_accounts={','.join(summary['blocked_accounts']) if summary['blocked_accounts'] else 'none'} "
        f"stale_accounts={','.join(summary['stale_accounts']) if summary['stale_accounts'] else 'none'}"
    )
    lines.extend(
        [
        "Workspace:",
        f"- cwd: {report['workspace']['cwd']}",
        "Runtime:",
        f"- os_family: {report['runtime']['os_family']}",
        f"- recommended_shell: {report['runtime']['recommended_shell']}",
        f"- default_shell: {report['runtime']['default_shell'] or 'none'}",
        "Shell Backend:",
        f"- configured: {report['shell_backend']['configured']}",
        f"- selected: {report['shell_backend']['selected'] or 'none'}",
        f"- executable: {report['shell_backend']['executable'] or 'none'}",
        "Permissions:",
            f"- mode: {report['permissions']['mode']}",
            f"- allow: {len(report['permissions']['allow'])}",
            f"- ask: {len(report['permissions']['ask'])}",
            f"- deny: {len(report['permissions']['deny'])}",
            "Git:",
            f"- ok: {str(report['git']['ok']).lower()}",
            f"- head: {report['git']['head'] or 'none'}",
            f"- status: {report['git']['status'] or 'clean'}",
            "Handoff:",
            f"- stage_health: {report['handoff']['stage_health']}",
            f"- recovery_state: {report['handoff']['recovery_state']}",
            f"- boundary_decision: {report['handoff']['boundary_decision']}",
            f"- next_action: {report['handoff']['next_action']}",
            (
                "- node_runtime: "
                f"status={report['handoff']['node_runtime_summary']['status']} "
                f"nodes={report['handoff']['node_runtime_summary']['nodes']} "
                f"ready={report['handoff']['node_runtime_summary']['ready']} "
                f"waiting={report['handoff']['node_runtime_summary']['waiting']} "
                f"running={report['handoff']['node_runtime_summary']['running']} "
                f"blocked={report['handoff']['node_runtime_summary']['blocked']}"
            ),
            "Usage:",
            f"- calls: {report['usage']['totals']['calls']}",
            f"- failures: {report['usage']['totals']['failures']}",
            f"- escalation_path: {report['usage']['totals']['escalation_path']}",
            "Quality Gates:",
            "- wet_run_required: true",
            "- dry_run_valid_checkpoint: false",
            "- git_snapshot_required: true",
            "Remediations:",
        ]
    )
    if report["remediations"]:
        for item in report["remediations"]:
            lines.append(f"- {item['severity']} {item['code']}: {item['action']}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _statusline_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
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
        "handoff": status["handoff"]["stage_view"],
        "latest_handoff_action": status["focus"].get("latest_handoff_action"),
        "usage": usage["totals"],
    }


def _statusline_rate_limit(item: dict[str, object]) -> dict[str, object]:
    windows = _provider_limit_windows(item)
    return {
        "provider": item["provider"],
        "account": item["active_account"],
        "status": windows["status"],
        "blocked_until": windows["blocked_until"],
        "reason": windows["reason"],
        "rate_limit_type": windows["rate_limit_type"],
        "stale": windows["stale"],
        "blocked_accounts": len(item.get("blocked_accounts", [])),
        "used_percentage": windows["utilization"],
        "resets_at": windows["blocked_until"] or windows["overage_resets_at"],
    }


def _focus_snapshot(agent: Agent, config: AgentConfig) -> dict[str, object]:
    _apply_model_preferences(agent, config)
    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = _load_model_preferences(config)
    memory = MemoryStore.load(config.memory_path)
    model_report = _model_status_report(agent, config)
    active_model = next((item for item in model_report["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in model_report["models"] if item["active"]), None)
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    active_provider = None if active_model is None else active_model["provider"]
    latest_limit = None
    if active_provider:
        latest_limit = dict(prefs.provider_limit_snapshot_by_model or {}).get(str(active_provider))
    return {
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "next_action": handoff.rendered_next_action(),
        "boundary_decision": handoff.stage_view()["boundary_decision"],
        "active_provider": None if active_model is None else active_model["provider"],
        "active_provider_model": None if active_model is None else active_model["provider_model"],
        "active_account": "none"
        if active_model is None
        else ((_load_model_preferences(config).active_account_by_model or {}).get(str(active_model["provider"])) or "none"),
        "active_provider_model_params": {} if active_model is None else dict(active_model["provider_model_params"]),
        "latest_model_attempt": None
        if latest_attempt is None
        else {
            "step": latest_attempt.step_id,
            "action": latest_attempt.action_type,
            "status": "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}",
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
        "latest_handoff_action": _latest_handoff_action(config),
        "resume_ready": bool(handoff.task),
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
            f"status={latest_attempt['status']} provider={latest_attempt['provider']} "
            f"provider_model={latest_attempt['provider_model']}"
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


def _provider_limit_summary(agent: Agent, config: AgentConfig) -> str:
    report = _provider_limit_status_report(agent, config)
    summary = _provider_limit_summary_report(report)
    if not summary["providers_count"]:
        return "none"
    parts = [
        f"providers={summary['providers_count']}",
        f"blocked_models={','.join(summary['blocked_models']) if summary['blocked_models'] else 'none'}",
        f"stale_models={','.join(summary['stale_models']) if summary['stale_models'] else 'none'}",
        f"blocked_accounts={','.join(summary['blocked_accounts']) if summary['blocked_accounts'] else 'none'}",
        f"stale_accounts={','.join(summary['stale_accounts']) if summary['stale_accounts'] else 'none'}",
        f"last_errors={','.join(summary['last_errors']) if summary['last_errors'] else 'none'}",
        f"routes={','.join(summary['routes'])}",
    ]
    return " ".join(parts)


def _render_accounts(config: AgentConfig) -> str:
    prefs = _load_model_preferences(config)
    lines = ["Account profiles:"]
    found = False
    for model in SUPPORTED_MODELS:
        rendered = _render_account_lines(prefs, model)
        if rendered:
            found = True
            lines.append(f"- {model}")
            lines.extend(rendered)
    if not found:
        lines.append("- none configured")
    return "\n".join(lines)


def _accounts_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    models: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        accounts = []
        for account in (prefs.accounts_by_model or {}).get(model, []):
            key = account_key(model, account)
            accounts.append(
                {
                    "name": account,
                    "active": (prefs.active_account_by_model or {}).get(model) == account,
                    "blocked_until": (prefs.blocked_until_by_account or {}).get(key),
                    "env": (prefs.env_var_by_account or {}).get(key),
                    "token_stored": SecretStore().has_token(model, account),
                }
            )
        if accounts:
            models.append({"model": model, "accounts": accounts})
    return {
        "command": "accounts",
        "models": models,
    }


def _auth_status_report(provider: str) -> dict[str, object]:
    normalized = provider.strip().lower()
    aliases = {
        "gpt": "chatgpt",
        "codex": "chatgpt",
        "openai": "chatgpt",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"chatgpt", "claude"}:
        return {
            "command": "auth status",
            "provider": provider,
            "ok": False,
            "logged_in": False,
            "auth_method": "unsupported",
            "source": "stagewarden",
            "message": "Supported providers: chatgpt, openai, codex, claude.",
        }
    if normalized == "chatgpt":
        codex = shutil.which("codex")
        if codex is None:
            return {
                "command": "auth status",
                "provider": normalized,
                "ok": False,
                "logged_in": False,
                "auth_method": "missing_cli",
                "source": "codex login status",
                "message": "codex CLI not found in PATH.",
            }
        completed = subprocess.run(
            [codex, "login", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        message = (completed.stderr or completed.stdout).strip()
        logged_in = completed.returncode == 0
        if "ChatGPT" in message:
            auth_method = "chatgpt"
        elif "API key" in message:
            auth_method = "apikey"
        elif "Not logged in" in message:
            auth_method = "none"
        else:
            auth_method = "unknown"
        return {
            "command": "auth status",
            "provider": normalized,
            "ok": completed.returncode == 0,
            "logged_in": logged_in,
            "auth_method": auth_method,
            "source": "codex login status",
            "message": message,
        }
    claude = shutil.which("claude")
    if claude is None:
        return {
            "command": "auth status",
            "provider": normalized,
            "ok": False,
            "logged_in": False,
            "auth_method": "missing_cli",
            "source": "claude auth status --json",
            "message": "claude CLI not found in PATH.",
        }
    completed = subprocess.run(
        [claude, "auth", "status", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    raw = (completed.stdout or completed.stderr).strip()
    parsed: dict[str, object] = {}
    if raw:
        try:
            value = loads_text(raw)
            if isinstance(value, dict):
                parsed = value
        except ValueError:
            parsed = {}
    logged_in = bool(parsed.get("loggedIn")) if parsed else completed.returncode == 0
    return {
        "command": "auth status",
        "provider": normalized,
        "ok": completed.returncode == 0,
        "logged_in": logged_in,
        "auth_method": str(parsed.get("authMethod", "unknown" if raw else "none")),
        "api_provider": parsed.get("apiProvider"),
        "source": "claude auth status --json",
        "message": raw,
    }


def _render_auth_status(provider: str) -> str:
    report = _auth_status_report(provider)
    lines = [
        "Provider auth status:",
        f"- provider: {report['provider']}",
        f"- ok: {str(report['ok']).lower()}",
        f"- logged_in: {str(report['logged_in']).lower()}",
        f"- auth_method: {report['auth_method']}",
        f"- source: {report['source']}",
    ]
    if report.get("api_provider"):
        lines.append(f"- api_provider: {report['api_provider']}")
    if report.get("message"):
        lines.append(f"- message: {report['message']}")
    return "\n".join(lines)


def _render_status(agent: Agent, config: AgentConfig) -> str:
    _apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    status = _status_report(agent, config)
    lines = [
        "Stagewarden status:",
        f"- workspace: {config.workspace_root}",
        f"- mode: {mode}",
        f"- memory: {config.memory_path.name}",
        f"- trace: {config.trace_path.name}",
        f"- handoff: {config.handoff_path.name}",
        f"- model_config: {config.model_prefs_path.name}",
        _render_focus_snapshot(_focus_snapshot(agent, config)),
        _render_model_status(agent, config),
        _render_provider_limit_status(agent, config),
        _render_runtime_status(config),
        _render_shell_backend(config),
        _render_resume_context(config),
        _render_permissions(config),
        "PRINCE2 roles:",
        _render_prince2_role_status_hint(config),
        _render_prince2_roles(config),
        "Handoff summary:",
        handoff.summary(),
        handoff.rendered_operational_posture(),
        _render_remediations(status["remediations"]),
    ]
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


def _render_runtime_status(config: AgentConfig) -> str:
    runtime = detect_runtime_capabilities(config.workspace_root)
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


def _permissions_report(config: AgentConfig) -> dict[str, object]:
    workspace_settings = PermissionSettings.load(config.settings_path)
    session_settings = config.session_permission_settings
    effective_settings = workspace_settings.merged(session_settings)
    return {
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


def _workspace_settings_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = loads_text(read_text_utf8(path))
    return payload if isinstance(payload, dict) else {}


def _configured_shell_backend(config: AgentConfig) -> str:
    payload = _workspace_settings_payload(config.settings_path)
    shell = payload.get("shell", {}) if isinstance(payload, dict) else {}
    if isinstance(shell, dict):
        value = str(shell.get("backend", "auto")).strip().lower()
        if value in {"auto", "bash", "zsh", "powershell", "cmd"}:
            return value
    return "auto"


def _save_shell_backend(config: AgentConfig, backend: str) -> None:
    payload = _workspace_settings_payload(config.settings_path)
    shell = payload.get("shell", {})
    if not isinstance(shell, dict):
        shell = {}
    shell["backend"] = backend
    payload["shell"] = shell
    write_text_utf8(config.settings_path, dumps_ascii(payload, indent=2))


def _shell_backend_report(config: AgentConfig) -> dict[str, object]:
    configured = _configured_shell_backend(config)
    capabilities = detect_runtime_capabilities(config.workspace_root)
    selection = select_shell_backend(configured, capabilities)
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


def _model_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    status = agent.router.status()
    models: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        capability = provider_capability(model)
        provider_model, selection_mode, default_model = _provider_model_display(prefs, model)
        params = _provider_model_params_display(prefs, model)
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
                "backend": MODEL_BACKENDS[model]["label"],
            }
        )
    return {
        "command": "models",
        "models": models,
        "preferred_model": status["preferred_model"],
        "preferred_provider": status["preferred_model"],
    }


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    _apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    provider_limits = _provider_limit_status_report(agent, config)
    permissions = _permissions_report(config)
    stage_view = handoff.stage_view()
    return {
        "command": "status",
        "workspace": str(config.workspace_root),
        "mode": mode,
        "files": {
            "memory": config.memory_path.name,
            "trace": config.trace_path.name,
            "handoff": config.handoff_path.name,
            "model_config": config.model_prefs_path.name,
        },
        "models": _model_status_report(agent, config),
        "provider_limits": provider_limits,
        "limits_summary": _provider_limit_summary_report(provider_limits),
        "runtime": detect_runtime_capabilities(config.workspace_root),
        "shell_backend": _shell_backend_report(config),
        "focus": _focus_snapshot(agent, config),
        "roles": _prince2_roles_report(config),
        "permissions": permissions,
        "handoff": {
            "summary": handoff.summary(),
            "operational_posture": handoff.rendered_operational_posture(),
            "stage_view": stage_view,
        },
        "remediations": _status_remediation_report(provider_limits=provider_limits, stage_view=stage_view, config=config),
    }


def _overview_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return {
        "command": "overview",
        "status": _status_report(agent, config),
        "board": _board_report(config),
        "model_usage": _model_usage_report(config),
        "provider_limits": _provider_limit_status_report(agent, config),
        "transcript": _transcript_report(config),
        "handoff": _handoff_report(config),
    }


def _health_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    board = _board_report(config)
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
    transcript = _transcript_report(config)["report"]
    ready = (
        board["recommended_authorization"] in {"continue", "close"}
        and board["open_issues"] == 0
        and board["recovery_state"] == "none"
    )
    return {
        "command": "health",
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
    }


def _preflight_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    doctor = _doctor_report(config)
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    git_dirty = git.status_porcelain()
    role_check = _prince2_role_check_report(config)
    provider_limits = _provider_limit_status_report(agent, config)
    sources = _sources_status_report(config)
    handoff = ProjectHandoff.load(config.handoff_path)
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
    )
    ready = not any(item["severity"] == "blocker" for item in remediations)
    return {
        "command": "preflight",
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
        "sources": sources,
        "permissions": _permissions_report(config),
        "handoff": {
            "summary": handoff.summary(),
            "stage_view": stage_view,
        },
        "remediations": remediations,
    }


def _status_remediation_report(
    *,
    provider_limits: dict[str, object],
    stage_view: dict[str, object],
    config: AgentConfig,
) -> list[dict[str, str]]:
    git = GitTool(config)
    git_status = git.status()
    git_dirty = git.status_porcelain()
    return _preflight_remediations(
        doctor={"python": {"ok": True}, "git": {"ok": True}},
        runtime=detect_runtime_capabilities(config.workspace_root),
        shell_backend=_shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=_prince2_role_check_report(config),
        provider_limits=provider_limits,
        sources=_sources_status_report(config),
        stage_view=stage_view,
    )


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
) -> list[dict[str, str]]:
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
    if not getattr(git_status, "ok", False):
        items.append({"severity": "warning", "code": "git_status", "action": "Run `/doctor` and confirm this folder is a git worktree."})
    if getattr(git_dirty, "ok", False) and getattr(git_dirty, "stdout", "").strip():
        items.append({"severity": "warning", "code": "dirty_git", "action": "Review `/git status`; commit or let Stagewarden checkpoint before execution."})
    if role_check.get("status") == "error":
        items.append({"severity": "warning", "code": "roles", "action": "Run `/roles setup` or `/roles propose` before PRINCE2 role-routed work."})
    blocked = [
        str(provider["provider"])
        for provider in provider_limits.get("providers", [])
        if isinstance(provider, dict) and provider.get("blocked_until")
    ]
    if blocked:
        items.append({"severity": "warning", "code": "provider_limits", "action": f"Blocked providers: {', '.join(blocked)}. Run `/model limits` and choose another provider or wait."})
    stale = [
        str(provider["provider"])
        for provider in provider_limits.get("providers", [])
        if isinstance(provider, dict) and bool(_provider_limit_windows(provider).get("stale"))
    ]
    if stale:
        items.append(
            {
                "severity": "warning",
                "code": "provider_limits_stale",
                "action": f"Stale provider limit snapshots: {', '.join(stale)}. Refresh routing evidence or clear outdated limits before execution decisions.",
            }
        )
    if not sources.get("ok"):
        items.append({"severity": "warning", "code": "sources", "action": "Run `/sources status` before source-derived implementation work."})
    if stage_view.get("recovery_state") != "none":
        items.append({"severity": "warning", "code": "recovery", "action": "Review `/exception` and close recovery lane before normal-stage work."})
    return items


def _render_preflight(agent: Agent, config: AgentConfig) -> str:
    report = _preflight_report(agent, config)
    runtime = report["runtime"]
    git = report["git"]
    role_check = report["roles_check"]
    lines = [
        "Stagewarden preflight:",
        f"- ready: {str(report['ready']).lower()}",
        f"- runtime: os={runtime['os_family']} shell={runtime['recommended_shell']} default={runtime['default_shell'] or 'none'}",
        f"- shell_backend: configured={report['shell_backend']['configured']} selected={report['shell_backend']['selected'] or 'none'}",
        f"- git: ok={str(git['ok']).lower()} dirty={str(git['dirty']).lower()} head={git['head'] or 'none'}",
        f"- roles_check: {role_check['status']} errors={role_check['summary']['errors']} warnings={role_check['summary']['warnings']}",
        f"- providers: {len(report['provider_limits']['providers'])}",
        f"- sources: {'ok' if report['sources']['ok'] else 'warn'} count={report['sources']['count']}",
        f"- stage_health: {report['handoff']['stage_view']['stage_health']}",
        "Remediations:",
    ]
    if report["remediations"]:
        for item in report["remediations"]:
            lines.append(f"- {item['severity']} {item['code']}: {item['action']}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _report_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    board = _board_report(config)
    usage = _model_usage_report(config)["report"]
    transcript = _transcript_report(config)["report"]
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
    ]
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


def _doctor_report(config: AgentConfig) -> dict[str, object]:
    python_ok = sys.version_info >= (3, 11)
    report: dict[str, object] = {
        "command": "doctor",
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
        "runtime": detect_runtime_capabilities(config.workspace_root),
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
    for model in REGISTRY_MODELS:
        capability = provider_capability(model)
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
    lines.append("Provider capabilities:")
    for provider in providers:
        lines.append(
            f"- {provider['provider']}: auth={provider['auth']} profiles={'yes' if provider['profiles'] else 'no'} "
            f"browser_login={'yes' if provider['browser_login'] else 'no'} api_key={'yes' if provider['api_key'] else 'no'} "
            f"token_env={provider['token_env']} default_model={provider['default_model']}"
        )
    lines.append(f"- Policy: {policy_info['note']}")
    return "\n".join(lines)


def _doctor_ok(rendered: str) -> bool:
    return "\n- Python: FAIL" not in rendered and "\n- Git: FAIL" not in rendered


def _render_handoff(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    lines = [
        "Project handoff:",
        handoff.summary(),
        handoff.rendered_operational_posture(),
        handoff.rendered_stage_view(),
        handoff.rendered_prince2_node_runtime(),
        handoff.rendered_implementation_backlog(),
    ]
    if handoff.entries:
        lines.append("Recent handoff entries:")
        for entry in handoff.entries[-8:]:
            lines.append(
                f"- [{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
                f"status={entry.step_status or '-'} model={entry.model or '-'} "
                f"head={entry.git_head or 'unknown'}"
            )
    return "\n".join(lines)


def _handoff_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "handoff",
        "handoff": handoff.as_dict(),
        "stage_view": handoff.stage_view(),
        "node_runtime": handoff.prince2_node_runtime_report(),
        "next_action": handoff.rendered_next_action(),
    }


ACTION_PHASE_PREFIXES = (
    "project_",
    "role_",
    "model_",
    "account_",
    "permission_",
    "git_",
    "shell_",
    "sources_",
    "update_",
    "extension_",
    "web_",
    "download_",
    "checksum_",
    "compress_",
    "archive_",
)


def _is_handoff_action_entry(entry: HandoffEntry) -> bool:
    return (
        entry.phase.endswith("_approval")
        or entry.phase.endswith("_blocked")
        or entry.phase.startswith(ACTION_PHASE_PREFIXES)
    )


def _handoff_action_payload(entry: HandoffEntry) -> dict[str, object]:
    return {
        "timestamp": entry.timestamp,
        "phase": entry.phase,
        "task": entry.task,
        "summary": entry.summary,
        "git_head": entry.git_head,
        "details": dict(entry.details),
    }


def _latest_handoff_action(config: AgentConfig) -> dict[str, object] | None:
    handoff = ProjectHandoff.load(config.handoff_path)
    for entry in reversed(handoff.entries):
        if _is_handoff_action_entry(entry):
            return _handoff_action_payload(entry)
    return None


def _handoff_actions_report(config: AgentConfig, *, limit: int = 20) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    safe_limit = max(1, min(int(limit), 200))
    action_entries = [entry for entry in handoff.entries if _is_handoff_action_entry(entry)]
    selected = action_entries[-safe_limit:]
    return {
        "command": "handoff actions",
        "count": len(action_entries),
        "limit": safe_limit,
        "entries": [_handoff_action_payload(entry) for entry in selected],
    }


def _render_handoff_actions(config: AgentConfig, *, limit: int = 20) -> str:
    report = _handoff_actions_report(config, limit=limit)
    lines = [
        "Handoff actions:",
        f"- count: {report['count']}",
        f"- showing: {len(report['entries'])}/{report['count']}",
    ]
    entries = report["entries"]
    if not isinstance(entries, list) or not entries:
        lines.append("- none")
        return "\n".join(lines)
    for item in entries:
        if not isinstance(item, dict):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        detail_keys = ", ".join(sorted(details)) if details else "none"
        lines.append(
            f"- [{item.get('phase')}] {item.get('summary')} "
            f"task={item.get('task') or 'none'} head={item.get('git_head') or 'unknown'} details={detail_keys}"
        )
    return "\n".join(lines)


def _parse_optional_limit(parts: list[str], *, default: int = 20) -> int:
    if len(parts) <= 2:
        return default
    try:
        return max(1, min(int(parts[2]), 200))
    except ValueError:
        return default


def _render_resume_show(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    agent = _configure_readonly_agent_for_workspace(config)
    focus = _focus_snapshot(agent, config)
    lines = [
        "Resume target:",
        f"- task: {handoff.task or 'none'}",
        f"- current_step: {handoff.current_step_id or 'none'}",
        f"- current_step_status: {handoff.current_step_status or 'none'}",
        f"- next_action: {handoff.rendered_next_action()}",
        f"- active_route: provider={focus['active_provider'] or 'none'} account={focus['active_account']} provider_model={focus['active_provider_model'] or 'none'}",
        f"- resume_ready: {str(bool(focus['resume_ready'])).lower()}",
        handoff.rendered_stage_view(),
    ]
    return "\n".join(lines)


def _resume_context_payload(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    memory = MemoryStore.load(config.memory_path)
    agent = _configure_readonly_agent_for_workspace(config)
    focus = _focus_snapshot(agent, config)
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    latest_snapshot = handoff.latest_git_snapshot()
    attempt_payload: dict[str, object] | None = None
    if latest_attempt is not None:
        attempt_payload = {
            "step": latest_attempt.step_id,
            "action": latest_attempt.action_type,
            "status": "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}",
            "route": {
                "model": latest_attempt.model,
                "provider": latest_attempt.model,
                "account": latest_attempt.account or "none",
                "variant": latest_attempt.variant or "provider-default",
                "provider_model": latest_attempt.variant or "provider-default",
            },
            "observation": (latest_attempt.observation or "none").strip().replace("\n", " ")[:200],
        }
    tool_payload: dict[str, object] | None = None
    if latest_tool is not None:
        tool_payload = {
            "tool": latest_tool.tool,
            "action": latest_tool.action_type,
            "status": "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}",
            "duration_ms": latest_tool.duration_ms or 0,
            "summary": latest_tool.summary,
        }
    snapshot_payload: dict[str, object] | None = None
    if latest_snapshot is not None:
        snapshot_payload = {
            "git_head": latest_snapshot["git_head"],
            "summary": latest_snapshot["summary"],
            "timestamp": latest_snapshot["timestamp"],
        }
    return {
        "command": "resume context",
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "active_route": {
            "provider": focus["active_provider"] or "none",
            "account": focus["active_account"],
            "provider_model": focus["active_provider_model"] or "none",
            "params": focus["active_provider_model_params"],
        },
        "resume_ready": bool(focus["resume_ready"]),
        "boundary_decision": focus["boundary_decision"],
        "latest_model_attempt": attempt_payload,
        "latest_tool_evidence": tool_payload,
        "latest_git_snapshot": snapshot_payload,
        "active_limit": focus["active_limit"],
    }


def _render_resume_context(config: AgentConfig) -> str:
    payload = _resume_context_payload(config)
    lines = [
        "Resume context:",
        f"- task: {payload['task']}",
        f"- current_step: {payload['current_step']}",
        f"- current_step_status: {payload['current_step_status']}",
        f"- boundary_decision: {payload['boundary_decision']}",
    ]
    route = payload["active_route"]
    lines.append(
        f"- active_route: provider={route['provider']} account={route['account']} provider_model={route['provider_model']}"
    )
    params = route.get("params")
    if isinstance(params, dict) and params:
        lines.append("- active_provider_model_params: " + ",".join(f"{key}={value}" for key, value in sorted(params.items())))
    attempt = payload["latest_model_attempt"]
    if isinstance(attempt, dict):
        route = attempt["route"]
        lines.extend(
            [
                f"- latest_model_attempt: step={attempt['step']} action={attempt['action']} status={attempt['status']}",
                (
                    f"- latest_route: provider={route['provider']} "
                    f"account={route['account']} provider_model={route['provider_model']}"
                ),
                f"- latest_observation: {attempt['observation']}",
            ]
        )
    else:
        lines.append("- latest_model_attempt: none")
    tool = payload["latest_tool_evidence"]
    if isinstance(tool, dict):
        lines.append(
            f"- latest_tool_evidence: tool={tool['tool']} action={tool['action']} "
            f"status={tool['status']} duration_ms={tool['duration_ms']}"
        )
    else:
        lines.append("- latest_tool_evidence: none")
    snapshot = payload["latest_git_snapshot"]
    if isinstance(snapshot, dict):
        lines.append(f"- latest_git_snapshot: {snapshot['git_head']} :: {snapshot['summary']}")
    else:
        lines.append("- latest_git_snapshot: none")
    active_limit = payload.get("active_limit")
    if isinstance(active_limit, dict):
        blocked = f" blocked_until={active_limit['blocked_until']}" if active_limit.get("blocked_until") else ""
        reason = f" reason={active_limit['reason']}" if active_limit.get("reason") else ""
        lines.append(f"- active_provider_limit: {active_limit['status'] or 'unknown'}{blocked}{reason}")
    else:
        lines.append("- active_provider_limit: none")
    lines.append(f"- resume_ready: {str(bool(payload['resume_ready'])).lower()}")
    return "\n".join(lines)


def _resume_show_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    agent = _configure_readonly_agent_for_workspace(config)
    return {
        "command": "resume --show",
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "next_action": handoff.rendered_next_action(),
        "stage_view": handoff.stage_view(),
        "focus": _focus_snapshot(agent, config),
    }


def _archive_and_clear_handoff(config: AgentConfig) -> str:
    if not config.handoff_path.exists():
        ProjectHandoff().save(config.handoff_path)
        return "No handoff existed. Created a fresh handoff context."
    archive = config.workspace_root / f".stagewarden_handoff.archive.{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    write_text_utf8(archive, read_text_utf8(config.handoff_path))
    ProjectHandoff().save(config.handoff_path)
    return f"Archived handoff to {archive.name}. Fresh handoff context created."


def _archive_and_clear_handoff_report(config: AgentConfig) -> dict[str, object]:
    if not config.handoff_path.exists():
        ProjectHandoff().save(config.handoff_path)
        return {
            "command": "resume --clear",
            "archived": False,
            "archive_path": None,
            "message": "No handoff existed. Created a fresh handoff context.",
        }
    archive = config.workspace_root / f".stagewarden_handoff.archive.{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    write_text_utf8(archive, read_text_utf8(config.handoff_path))
    ProjectHandoff().save(config.handoff_path)
    return {
        "command": "resume --clear",
        "archived": True,
        "archive_path": archive.name,
        "message": f"Archived handoff to {archive.name}. Fresh handoff context created.",
    }


def _load_handoff_into_agent(agent: Agent, config: AgentConfig) -> ProjectHandoff:
    handoff = ProjectHandoff.load(config.handoff_path)
    agent.project_handoff = handoff
    agent.executor.project_handoff = handoff
    return handoff


def _handle_resume_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts or parts[0] != "resume":
        return None
    if len(parts) == 1:
        handoff = _load_handoff_into_agent(agent, config)
        if not handoff.task:
            return "No task in handoff to resume.\n" + _render_resume_show(config)
        resumed_step_id = handoff.current_step_id or "none"
        result = agent.run(handoff.task)
        return f"Resumed from handoff step {resumed_step_id}.\n{result.message}"
    if len(parts) == 2 and parts[1] == "--show":
        return _render_resume_show(config)
    if len(parts) == 2 and parts[1] == "context":
        return _render_resume_context(config)
    if len(parts) == 2 and parts[1] == "--clear":
        _load_handoff_into_agent(agent, config)
        return _archive_and_clear_handoff(config)
    return "Usage: resume | resume --show | resume context | resume --clear"


RUNTIME_HANDOFF_START = "<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->"
RUNTIME_HANDOFF_END = "<!-- STAGEWARDEN_RUNTIME_HANDOFF_END -->"


def _redact_handoff_markdown(value: str) -> str:
    redacted = re.sub(
        r"(?i)\b(access_token|refresh_token|id_token|auth_token|api_key|token)\b\s*[:=]\s*['\"]?[^'\"\s,}\]]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )
    redacted = re.sub(r"(?i)bearer\s+[a-z0-9._\-]{12,}", "Bearer [REDACTED]", redacted)
    redacted = re.sub(r"\b[a-zA-Z0-9_\-]{32,}\.[a-zA-Z0-9_\-]{16,}\.[a-zA-Z0-9_\-]{16,}\b", "[REDACTED_JWT]", redacted)
    return redacted


def _runtime_handoff_markdown(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    memory = MemoryStore.load(config.memory_path)
    view = handoff.stage_view()
    git_boundary = view["git_boundary"]
    pid_boundary = view["pid_boundary"]
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    latest_snapshot = handoff.latest_git_snapshot()
    lines = [
        RUNTIME_HANDOFF_START,
        "## Runtime Handoff Export",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "### Current State",
        "",
        f"- task: {handoff.task or 'unknown'}",
        f"- project_status: {handoff.status}",
        f"- plan_status: {handoff.plan_status or 'unknown'}",
        f"- recovery_state: {view['recovery_state']}",
        f"- stage_health: {view['stage_health']}",
        f"- next_action: {view['next_action']}",
        f"- current_step: {handoff.current_step_id or 'none'}",
        f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
        f"- pid_boundary: project_status={pid_boundary['project_status']} updated_at={pid_boundary['updated_at']}",
        "",
        "### Registers",
        "",
        handoff.rendered_register_status_summary(),
        "",
        "### Execution Resume Context",
        "",
    ]
    if latest_attempt is None:
        lines.append("- latest_model_attempt: none")
    else:
        attempt_status = "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}"
        lines.extend(
            [
                f"- latest_model_attempt: step={latest_attempt.step_id} action={latest_attempt.action_type} status={attempt_status}",
                (
                    f"- latest_route: provider={latest_attempt.model} "
                    f"account={latest_attempt.account or 'none'} "
                    f"provider_model={latest_attempt.variant or 'provider-default'}"
                ),
                f"- latest_observation: {(latest_attempt.observation or 'none').strip().replace(chr(10), ' ')[:200]}",
            ]
        )
    if latest_tool is None:
        lines.append("- latest_tool_evidence: none")
    else:
        tool_status = "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}"
        lines.append(
            f"- latest_tool_evidence: tool={latest_tool.tool} action={latest_tool.action_type} "
            f"status={tool_status} duration_ms={latest_tool.duration_ms or 0}"
        )
    if latest_snapshot is None:
        lines.append("- latest_git_snapshot: none")
    else:
        lines.append(
            f"- latest_git_snapshot: {latest_snapshot['git_head']} :: {latest_snapshot['summary']}"
        )
    lines.extend(
        [
            "",
        "### Implementation Backlog",
        "",
        handoff.rendered_implementation_backlog(),
        "",
        "### Risks",
        "",
        handoff.rendered_risks(),
        "",
        "### Issues",
        "",
        handoff.rendered_issues(),
        "",
        "### Quality",
        "",
        handoff.rendered_quality(),
        "",
        "### Lessons",
        "",
        handoff.rendered_lessons(),
        "",
        "### Recent Entries",
        "",
    ]
    )
    if handoff.entries:
        for entry in handoff.entries[-8:]:
            lines.append(
                f"- [{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
                f"status={entry.step_status or '-'} model={entry.model or '-'} head={entry.git_head or 'unknown'}"
            )
    else:
        lines.append("- none")
    lines.extend(["", RUNTIME_HANDOFF_END, ""])
    return _redact_handoff_markdown("\n".join(lines))


def _export_handoff_markdown(config: AgentConfig) -> str:
    target = config.workspace_root / "HANDOFF.md"
    generated = _runtime_handoff_markdown(config)
    existing = read_text_utf8(target) if target.exists() else "# Stagewarden Handoff\n"
    if RUNTIME_HANDOFF_START in existing and RUNTIME_HANDOFF_END in existing:
        prefix, _marker, rest = existing.partition(RUNTIME_HANDOFF_START)
        _old, _end_marker, suffix = rest.partition(RUNTIME_HANDOFF_END)
        updated = prefix.rstrip() + "\n\n" + generated.rstrip() + "\n" + suffix.lstrip()
    else:
        updated = existing.rstrip() + "\n\n" + generated
    write_text_utf8(target, updated)
    return f"Exported runtime handoff to {target.name}."


def _export_handoff_markdown_report(config: AgentConfig) -> dict[str, object]:
    target = config.workspace_root / "HANDOFF.md"
    generated = _runtime_handoff_markdown(config)
    existing = read_text_utf8(target) if target.exists() else "# Stagewarden Handoff\n"
    if RUNTIME_HANDOFF_START in existing and RUNTIME_HANDOFF_END in existing:
        prefix, _marker, rest = existing.partition(RUNTIME_HANDOFF_START)
        _old, _end_marker, suffix = rest.partition(RUNTIME_HANDOFF_END)
        updated = prefix.rstrip() + "\n\n" + generated.rstrip() + "\n" + suffix.lstrip()
    else:
        updated = existing.rstrip() + "\n\n" + generated
    write_text_utf8(target, updated)
    return {
        "command": "handoff export",
        "target": target.name,
        "updated": True,
        "message": f"Exported runtime handoff to {target.name}.",
    }


def _render_boundary(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    return "\n".join(
        [
            "Boundary recommendation:",
            handoff.rendered_stage_view(),
        ]
    )


def _boundary_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "boundary",
        "stage_view": handoff.stage_view(),
    }


def _board_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    stage_view = handoff.stage_view()
    register_statuses = stage_view["register_statuses"]
    business_justification = "viable"
    if handoff.status == "exception":
        business_justification = "at_risk"
    if stage_view["boundary_decision"] == "review_boundary:open_issues":
        business_justification = "review_required"
    if stage_view["boundary_decision"] == "close_project":
        recommendation = "close"
    elif stage_view["recovery_state"] in {"exception_active", "recovery_active", "recovery_cleared"}:
        recommendation = "recover"
    elif register_statuses["issues_open"] > 0 or stage_view["boundary_decision"].startswith("review_boundary:"):
        recommendation = "review"
    else:
        recommendation = "continue"
    return {
        "command": "board",
        "task": handoff.task or "none",
        "business_justification": business_justification,
        "boundary_decision": stage_view["boundary_decision"],
        "open_issues": register_statuses["issues_open"],
        "open_risks": register_statuses["risks_open"],
        "quality_open": register_statuses["quality_open"],
        "quality_accepted": register_statuses["quality_accepted"],
        "recovery_state": stage_view["recovery_state"],
        "recommended_authorization": recommendation,
        "next_action": stage_view["next_action"],
        "stage_view": stage_view,
    }


def _render_board(config: AgentConfig) -> str:
    report = _board_report(config)
    lines = [
        "Board review:",
        f"- task: {report['task']}",
        f"- business_justification: {report['business_justification']}",
        f"- boundary_decision: {report['boundary_decision']}",
        f"- open_issues: {report['open_issues']}",
        f"- open_risks: {report['open_risks']}",
        f"- quality_open: {report['quality_open']}",
        f"- quality_accepted: {report['quality_accepted']}",
        f"- recovery_state: {report['recovery_state']}",
        f"- recommended_authorization: {report['recommended_authorization']}",
        f"- next_action: {report['next_action']}",
    ]
    return "\n".join(lines)


def _render_permissions(config: AgentConfig) -> str:
    workspace_settings = PermissionSettings.load(config.settings_path)
    session_settings = config.session_permission_settings
    effective_settings = workspace_settings.merged(session_settings)
    lines = ["Permission settings:"]
    lines.append(f"- workspace mode: {workspace_settings.default_mode}")
    lines.append(f"- workspace allow: {', '.join(workspace_settings.allow) if workspace_settings.allow else 'none'}")
    lines.append(f"- workspace ask: {', '.join(workspace_settings.ask) if workspace_settings.ask else 'none'}")
    lines.append(f"- workspace deny: {', '.join(workspace_settings.deny) if workspace_settings.deny else 'none'}")
    if session_settings is None:
        lines.append("- session mode: none")
        lines.append("- session allow: none")
        lines.append("- session ask: none")
        lines.append("- session deny: none")
    else:
        lines.append(f"- session mode: {session_settings.default_mode}")
        lines.append(f"- session allow: {', '.join(session_settings.allow) if session_settings.allow else 'none'}")
        lines.append(f"- session ask: {', '.join(session_settings.ask) if session_settings.ask else 'none'}")
        lines.append(f"- session deny: {', '.join(session_settings.deny) if session_settings.deny else 'none'}")
    lines.append(f"- effective mode: {effective_settings.default_mode}")
    lines.append(f"- effective allow: {', '.join(effective_settings.allow) if effective_settings.allow else 'none'}")
    lines.append(f"- effective ask: {', '.join(effective_settings.ask) if effective_settings.ask else 'none'}")
    lines.append(f"- effective deny: {', '.join(effective_settings.deny) if effective_settings.deny else 'none'}")
    return "\n".join(lines)


def _render_risks(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_risks()


def _risks_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "risks",
        "count": len(handoff.risk_register),
        "items": list(handoff.risk_register),
    }


def _render_issues(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_issues()


def _issues_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "issues",
        "count": len(handoff.issue_register),
        "items": list(handoff.issue_register),
    }


def _render_quality(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_quality()


def _quality_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "quality",
        "count": len(handoff.quality_register),
        "items": list(handoff.quality_register),
    }


def _render_exception(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_exception_plan()


def _exception_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "exception",
        "count": len(handoff.exception_plan),
        "items": list(handoff.exception_plan),
    }


def _render_lessons(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_lessons()


def _lessons_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "lessons",
        "count": len(handoff.lessons_log),
        "items": list(handoff.lessons_log),
    }


def _render_todo(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_implementation_backlog()


def _todo_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "todo",
        "count": len(handoff.implementation_backlog),
        "items": list(handoff.implementation_backlog),
    }


def _render_transcript(config: AgentConfig) -> str:
    try:
        return MemoryStore.load(config.memory_path).transcript_summary()
    except (OSError, ValueError, TypeError):
        return "No tool transcript."


def _transcript_report(config: AgentConfig) -> dict[str, object]:
    try:
        return {
            "command": "transcript",
            "report": MemoryStore.load(config.memory_path).transcript_report(),
        }
    except (OSError, ValueError, TypeError):
        return {
            "command": "transcript",
            "report": MemoryStore().transcript_report(),
        }


def _render_model_usage(config: AgentConfig) -> str:
    try:
        return MemoryStore.load(config.memory_path).model_usage_summary()
    except (OSError, ValueError, TypeError):
        return "Model usage:\n- no model attempts recorded"


def _model_usage_report(config: AgentConfig) -> dict[str, object]:
    try:
        return {
            "command": "models usage",
            "report": MemoryStore.load(config.memory_path).model_usage_stats(),
            "policy": {
                "routing_budget": "prefer cloud analysis first (cheap/chatgpt/openai/claude); use local only when available and selected from discovered local-model characteristics or as fallback.",
            },
        }
    except (OSError, ValueError, TypeError):
        return {
            "command": "models usage",
            "report": MemoryStore().model_usage_stats(),
            "policy": {
                "routing_budget": "prefer cloud analysis first (cheap/chatgpt/openai/claude); use local only when available and selected from discovered local-model characteristics or as fallback.",
            },
        }


def _configure_agent_for_workspace(config: AgentConfig) -> Agent:
    agent = Agent(config)
    _apply_model_preferences(agent, config)
    return agent


def _configure_readonly_agent_for_workspace(config: AgentConfig) -> Agent:
    readonly_config = replace(config, enforce_git=False, auto_git_commit=False)
    agent = Agent(readonly_config)
    _apply_model_preferences(agent, readonly_config)
    return agent


def _planned_shell_route(agent: Agent, command: str) -> tuple[str, str, str]:
    prefs = _load_model_preferences(agent.config)
    provider = agent.router.choose_model(command, command, 0)
    account = prefs.account_for_model(provider) or "none"
    provider_model = (
        prefs.variant_for_model(provider)
        or agent.router.choose_variant(provider, command, command, 0)
        or "provider-default"
    )
    return provider, account, provider_model


def _choose_cloud_priority_model(agent: Agent, prefs: ModelPreferences) -> str:
    active = set(agent.router.status().get("active_models", []))
    for candidate in ("chatgpt", "openai", "claude", "cheap", "local"):
        if candidate in active:
            return candidate
    return agent.router.choose_model("fallback cloud priority", "analysis", 0)


def _render_shell_progress(agent: Agent, *, phase: str, command: str | None = None) -> str:
    handoff = agent.project_handoff
    view = handoff.stage_view()
    active = view["active_step"]
    active_label = "none"
    if isinstance(active, dict):
        active_label = f"{active.get('id', 'unknown')} [{active.get('status', 'unknown')}]"
    git_boundary = view["git_boundary"]
    route_line = "- route: unknown"
    if phase == "before" and command is not None:
        provider, account, provider_model = _planned_shell_route(agent, command)
        route_line = f"- route: provider={provider} account={account} provider_model={provider_model}"
    elif phase == "after":
        latest = agent.memory.latest_attempt()
        if latest is not None:
            route_line = (
                f"- route: provider={latest.model} "
                f"account={latest.account or 'none'} "
                f"provider_model={latest.variant or 'provider-default'}"
            )
    snapshot_line = None
    if phase == "after":
        snapshot = handoff.latest_git_snapshot()
        if snapshot is not None:
            snapshot_line = f"- git_snapshot: {snapshot['git_head']} :: {snapshot['summary']}"
    return "\n".join(
        [
            f"Shell progress ({phase}):",
            f"- active_step: {active_label}",
            f"- stage_health: {view['stage_health']}",
            f"- boundary_decision: {view['boundary_decision']}",
            f"- recovery_state: {view['recovery_state']}",
            f"- git_head: {git_boundary['current']}",
            route_line,
        ]
        + ([snapshot_line] if snapshot_line else [])
    )


def _render_last_step_outcome(agent: Agent) -> str:
    latest = agent.memory.latest_attempt()
    if latest is None:
        return "Last step outcome:\n- none"
    latest_tool = agent.memory.latest_tool_event()
    status = "ok" if latest.success else f"failed:{latest.error_type or 'unknown'}"
    observation = latest.observation.strip().replace("\n", " ")
    lines = [
        "Last step outcome:",
        f"- step: {latest.step_id}",
        f"- action: {latest.action_type}",
        f"- status: {status}",
        (
            f"- route: provider={latest.model} account={latest.account or 'none'} "
            f"provider_model={latest.variant or 'provider-default'}"
        ),
        (
            f"- evidence: tool={latest_tool.tool} action={latest_tool.action_type} "
            f"duration_ms={latest_tool.duration_ms or 0}"
            if latest_tool is not None
            else "- evidence: none"
        ),
        f"- observation: {observation[:200] or 'none'}",
    ]
    return "\n".join(lines)


def _refresh_runtime_permissions(agent: Agent) -> None:
    agent.refresh_permissions()


def _prompt_menu_choice(
    *,
    title: str,
    options: list[tuple[str, str]],
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str | None:
    if input_stream is None or output_stream is None:
        return None
    while True:
        output_stream.write(f"{title}\n")
        for index, (_, label) in enumerate(options, start=1):
            output_stream.write(f"{index}. {label}\n")
        output_stream.write("Choose a number or value, or `q` to cancel: ")
        output_stream.flush()
        response = input_stream.readline()
        if response == "":
            return None
        selected = response.strip()
        if not selected or selected.lower() in {"q", "quit", "cancel", "exit"}:
            return None
        if selected.isdigit():
            index = int(selected) - 1
            if 0 <= index < len(options):
                return options[index][0]
        else:
            lowered = selected.lower()
            for value, label in options:
                if lowered in {value.lower(), label.lower()}:
                    return value
        output_stream.write("Invalid selection. Try again or enter `q` to cancel.\n")


def _local_model_profile_from_spec(spec) -> dict[str, object]:
    agentic_fit = "medium"
    tool_support_risk = "unknown"
    availability = str(spec.availability or "unknown")
    hint = str(spec.context_window_hint or "")
    lowered_hint = hint.lower()
    if availability == "local-agentic":
        agentic_fit = "high"
        tool_support_risk = "medium"
    elif availability == "local-limited":
        agentic_fit = "low"
        tool_support_risk = "high"
    elif availability == "local-specialized":
        agentic_fit = "medium"
        tool_support_risk = "medium"
    strengths: list[str] = []
    weaknesses: list[str] = []
    best_for: list[str] = []
    if "coder" in spec.id.lower():
        strengths.append("coding-oriented local model")
        best_for.append("code editing and repository tasks")
    if "deepseek" in spec.id.lower() or "r1" in spec.id.lower():
        strengths.append("stronger reasoning-oriented profile")
        best_for.append("deeper debugging and analysis")
    if "sqlcoder" in spec.id.lower():
        strengths.append("specialized SQL profile")
        best_for.append("SQL generation and schema work")
    if "validate tool support" in lowered_hint:
        weaknesses.append("tool support must be validated before agentic routing")
        best_for.append("manual/local chat unless validated")
    if not strengths:
        strengths.append("available local model discovered from Ollama")
    if not best_for:
        best_for.append("general local experimentation")
    summary = hint or f"Discovered local model {spec.id}."
    return {
        "id": spec.id,
        "label": spec.label,
        "availability": availability,
        "reasoning_efforts": list(spec.reasoning_efforts),
        "reasoning_default": spec.reasoning_default,
        "metadata_hint": hint,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "best_for": best_for,
        "agentic_fit": agentic_fit,
        "tool_support_risk": tool_support_risk,
        "source": spec.source,
    }


def _local_model_inspection_prompt(catalog: list[dict[str, object]], selected_model: str | None) -> str:
    inventory = dumps_ascii({"models": catalog}, indent=2)
    return "\n".join(
        [
            "You are evaluating dynamically discovered local Ollama models for a Codex-style coding agent.",
            "Task: analyze the discovered local model inventory and summarize the peculiarities of each model.",
            "Rules:",
            "- Use only the provided model ids and metadata hints.",
            "- Do not invent benchmark numbers.",
            "- If tool support is uncertain, say so explicitly.",
            "- Return valid JSON only.",
            "- JSON schema:",
            '{',
            '  "models": [',
            '    {',
            '      "id": "model id",',
            '      "summary": "short summary",',
            '      "strengths": ["..."],',
            '      "weaknesses": ["..."],',
            '      "best_for": ["..."],',
            '      "agentic_fit": "high|medium|low",',
            '      "tool_support_risk": "low|medium|high|unknown"',
            "    }",
            "  ],",
            '  "global_recommendation": "short recommendation"',
            "}",
            f"Selected model: {selected_model or 'all discovered local models'}",
            "Discovered inventory:",
            inventory,
        ]
    )


def _inspect_provider_models(
    agent: Agent,
    config: AgentConfig,
    *,
    provider: str,
    provider_model: str | None = None,
) -> dict[str, object]:
    if provider not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model '{provider}'. Supported: {', '.join(SUPPORTED_MODELS)}")
    specs = [spec for spec in provider_model_specs(provider) if spec.id != "provider-default"]
    if provider_model is not None:
        specs = [spec for spec in specs if spec.id == provider_model]
        if not specs:
            raise ValueError(f"Provider-model '{provider_model}' not found for provider '{provider}'.")
    catalog = [_local_model_profile_from_spec(spec) for spec in specs] if provider == "local" else [
        {
            "id": spec.id,
            "label": spec.label,
            "availability": spec.availability,
            "reasoning_efforts": list(spec.reasoning_efforts),
            "reasoning_default": spec.reasoning_default,
            "metadata_hint": spec.context_window_hint,
            "summary": spec.context_window_hint or spec.label,
            "strengths": [],
            "weaknesses": [],
            "best_for": [],
            "agentic_fit": "unknown",
            "tool_support_risk": "unknown",
            "source": spec.source,
        }
        for spec in specs
    ]
    report: dict[str, object] = {
        "command": "model inspect",
        "provider": provider,
        "provider_model": provider_model,
        "status": "ok",
        "catalog_source": next((item["source"] for item in catalog if item.get("source")), provider_capability(provider).source) if catalog else provider_capability(provider).source,
        "models": catalog,
        "ai_analysis": {
            "attempted": False,
            "ok": False,
            "model": None,
            "account": None,
            "message": "",
        },
    }
    if provider != "local" or not catalog:
        return report
    _apply_model_preferences(agent, config)
    prefs = _load_model_preferences(config)
    analysis_model = _choose_cloud_priority_model(agent, prefs)
    account = prefs.account_for_model(analysis_model)
    result = agent.handoff.execute(format_run_model(analysis_model, _local_model_inspection_prompt(catalog, provider_model), account=account))
    ai_analysis = {
        "attempted": True,
        "ok": False,
        "model": analysis_model,
        "account": account or None,
        "message": "",
    }
    if not result.ok:
        ai_analysis["message"] = result.error or "Model inspection call failed."
        report["ai_analysis"] = ai_analysis
        report["global_recommendation"] = "Using metadata-derived local model profiles only."
        return report
    try:
        payload = loads_text(result.output)
    except ValueError as exc:
        ai_analysis["message"] = f"Inspection output was not valid JSON: {exc}"
        report["ai_analysis"] = ai_analysis
        report["global_recommendation"] = "Using metadata-derived local model profiles only."
        return report
    ai_models = payload.get("models", []) if isinstance(payload, dict) else []
    ai_by_id = {
        str(item.get("id", "")).strip(): item
        for item in ai_models
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    merged_models: list[dict[str, object]] = []
    for item in catalog:
        merged = dict(item)
        candidate = ai_by_id.get(str(item.get("id")))
        if isinstance(candidate, dict):
            for key in ("summary", "agentic_fit", "tool_support_risk"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
            for key in ("strengths", "weaknesses", "best_for"):
                value = candidate.get(key)
                if isinstance(value, list):
                    merged[key] = [str(entry).strip() for entry in value if str(entry).strip()]
        merged_models.append(merged)
    ai_analysis["ok"] = True
    ai_analysis["message"] = "AI synthesis applied to discovered local model inventory."
    report["models"] = merged_models
    report["ai_analysis"] = ai_analysis
    report["global_recommendation"] = (
        str(payload.get("global_recommendation", "")).strip()
        if isinstance(payload, dict) and str(payload.get("global_recommendation", "")).strip()
        else "Prefer models with high agentic fit and lower tool support risk."
    )
    return report


def _render_provider_model_inspection(report: dict[str, object]) -> str:
    lines = [
        f"Provider-model inspection for {report.get('provider', 'unknown')}:",
        f"- provider_model_filter: {report.get('provider_model') or 'all'}",
        f"- catalog_source: {report.get('catalog_source', 'unknown')}",
    ]
    ai = report.get("ai_analysis", {}) if isinstance(report.get("ai_analysis"), dict) else {}
    lines.append(
        f"- ai_analysis: attempted={ai.get('attempted', False)} ok={ai.get('ok', False)} "
        f"model={ai.get('model') or 'none'} account={ai.get('account') or 'none'}"
    )
    if ai.get("message"):
        lines.append(f"- ai_message: {ai.get('message')}")
    if report.get("global_recommendation"):
        lines.append(f"- recommendation: {report.get('global_recommendation')}")
    models = [item for item in report.get("models", []) if isinstance(item, dict)]
    if not models:
        lines.append("- models: none")
        return "\n".join(lines)
    lines.append("Models:")
    for item in models:
        lines.append(
            f"- {item.get('id')}: fit={item.get('agentic_fit')} tool_support_risk={item.get('tool_support_risk')} "
            f"availability={item.get('availability')} summary={item.get('summary')}"
        )
        strengths = ", ".join(str(entry) for entry in item.get("strengths", []) if str(entry).strip()) or "none"
        weaknesses = ", ".join(str(entry) for entry in item.get("weaknesses", []) if str(entry).strip()) or "none"
        best_for = ", ".join(str(entry) for entry in item.get("best_for", []) if str(entry).strip()) or "none"
        lines.append(f"  strengths: {strengths}")
        lines.append(f"  weaknesses: {weaknesses}")
        lines.append(f"  best_for: {best_for}")
    return "\n".join(lines)


def _local_execution_candidates_report(
    config: AgentConfig,
    *,
    agent: Agent | None = None,
    use_ai: bool = False,
) -> dict[str, object]:
    specs = [spec for spec in provider_model_specs("local") if spec.id != "provider-default"]
    if not specs:
        return {
            "status": "missing",
            "message": "No local models discovered from Ollama.",
            "models": [],
            "candidates": [],
            "ai_analysis": {"attempted": False, "ok": False, "model": None, "account": None, "message": "Local discovery unavailable."},
        }
    if use_ai and agent is not None:
        report = _inspect_provider_models(agent, config, provider="local")
    else:
        report = {
            "status": "ok",
            "provider": "local",
            "models": [_local_model_profile_from_spec(spec) for spec in specs],
            "ai_analysis": {"attempted": False, "ok": False, "model": None, "account": None, "message": "Metadata-only local profile."},
            "global_recommendation": "Use local models only when runtime-discovered and appropriate for bounded node execution.",
        }
    models = [item for item in report.get("models", []) if isinstance(item, dict)]
    fit_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    risk_rank = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    candidates = sorted(
        models,
        key=lambda item: (
            fit_rank.get(str(item.get("agentic_fit", "unknown")), 3),
            risk_rank.get(str(item.get("tool_support_risk", "unknown")), 2),
            str(item.get("id", "")),
        ),
    )
    return {
        "status": "ok",
        "message": report.get("global_recommendation", ""),
        "models": models,
        "candidates": candidates[:3],
        "ai_analysis": report.get("ai_analysis", {}),
        "catalog_source": report.get("catalog_source", "dynamic local inspection"),
    }


def _guided_model_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    agent: Agent,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided model selection is available in the interactive shell. Run `python3 -m stagewarden.main` and use `model choose`."
    providers = list(prefs.enabled_models or []) or list(SUPPORTED_MODELS)
    output_stream.write(_guided_provider_context(prefs, requested_model if requested_model in SUPPORTED_MODELS else None) + "\n")
    model = requested_model
    if model is None:
        model = _prompt_menu_choice(
            title="Choose provider:",
            options=[(item, item) for item in providers],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if model is None:
            return "Guided model selection cancelled."
    if model not in SUPPORTED_MODELS:
        return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
    if model not in prefs.enabled_models:
        prefs.enabled_models.append(model)
    output_stream.write(_guided_provider_context(prefs, model) + "\n")
    specs = list(provider_model_specs(model))
    provider_model = _prompt_menu_choice(
        title=f"Choose provider-model for {model}:",
        options=[(spec.id, f"{spec.id} | {spec.label}") for spec in specs],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Guided model selection cancelled."
    spec = provider_model_spec(model, provider_model)
    reasoning_value = None
    if spec is not None and spec.reasoning_efforts:
        current_reasoning = prefs.params_for_model(model).get("reasoning_effort") or spec.reasoning_default or spec.reasoning_efforts[0]
        reasoning_value = _prompt_menu_choice(
            title=f"Choose reasoning_effort for {model}:{provider_model}:",
            options=[
                (effort, f"{effort}{' (default)' if effort == current_reasoning else ''}")
                for effort in spec.reasoning_efforts
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning_value is None:
            return "Guided model selection cancelled."
    prefs.preferred_model = model
    prefs.set_variant(model, provider_model)
    if reasoning_value is not None:
        prefs.set_model_param(model, "reasoning_effort", reasoning_value)
    _save_model_preferences(config, prefs)
    _apply_model_preferences(agent, config)
    params_text = f" reasoning_effort={reasoning_value}" if reasoning_value is not None else ""
    return f"Guided selection applied: provider={model} provider_model={provider_model}{params_text}."


def _handle_model_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "cost":
        return _render_model_usage(config)
    if parts[0] == "models":
        if len(parts) == 2 and parts[1] == "usage":
            return _render_model_usage(config)
        if len(parts) == 2 and parts[1] == "limits":
            _apply_model_preferences(agent, config)
            return _render_model_limits(agent, config)
        if len(parts) != 1:
            return "Usage: models | models usage | models limits"
        _apply_model_preferences(agent, config)
        return _render_model_status(agent, config)
    if parts[0] != "model":
        return None
    if len(parts) < 2:
        return _model_usage()
    prefs = _load_model_preferences(config)
    if command.startswith("model limit-record "):
        fields = command[len("model limit-record ") :].split(maxsplit=1)
        if len(fields) != 2:
            return "Usage: model limit-record <model> <provider message>"
        model, message = fields
        result = _record_limit_message(config, prefs, model=model, message=message)
        _apply_model_preferences(agent, config)
        return result
    if command.startswith("model limit-clear "):
        fields = command[len("model limit-clear ") :].split(maxsplit=1)
        if len(fields) != 1:
            return "Usage: model limit-clear <model>"
        result = _clear_limit_snapshot(config, prefs, model=fields[0])
        _apply_model_preferences(agent, config)
        return result

    action = parts[1]
    try:
        if action == "choose":
            if len(parts) > 3:
                return "Usage: model choose [provider]"
            requested_model = parts[2] if len(parts) == 3 else None
            return _guided_model_choice(
                requested_model=requested_model,
                prefs=prefs,
                agent=agent,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "use":
            if len(parts) != 3:
                return "Usage: model use <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            prefs.preferred_model = model
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            provider_model = prefs.variant_for_model(model) or "automatic-by-task"
            return f"Preferred provider set to {model}. Current provider_model={provider_model}."
        if action == "list":
            if len(parts) != 3:
                return "Usage: model list <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            capability = provider_capability(model)
            specs = provider_model_specs(model)
            source = (
                next((spec.source for spec in specs if spec.id != "provider-default" and spec.source), capability.source)
                if model == "local"
                else MODEL_VARIANT_CATALOG[model]["source"]
            )
            lines = [
                f"Provider-model catalog for {model}:",
                f"Default provider-model: {capability.default_model}",
                f"Auth: {capability.auth_type}",
                f"Account profiles: {'yes' if capability.supports_account_profiles else 'no'}",
                f"Browser login: {'yes' if capability.supports_browser_login else 'no'}",
                f"API key: {'yes' if capability.supports_api_key else 'no'}",
                f"Token env: {capability.token_env or 'none'}",
                f"Model env: {capability.model_env or 'none'}",
                f"Context: {capability.context_assumption}",
                f"Login hint: {capability.login_hint}",
                f"Source: {source}",
                "Models:",
            ]
            for spec in specs:
                efforts = ",".join(spec.reasoning_efforts) if spec.reasoning_efforts else "none"
                default_effort = spec.reasoning_default or "none"
                lines.append(
                    f"- {spec.id}: label={spec.label} reasoning_effort=[{efforts}] "
                    f"default_reasoning={default_effort} availability={spec.availability}"
                )
            return "\n".join(lines)
        if action == "inspect":
            if len(parts) not in {3, 4}:
                return "Usage: model inspect <provider> [provider_model]"
            provider = parts[2]
            provider_model = parts[3] if len(parts) == 4 else None
            report = _inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)
            return _render_provider_model_inspection(report)
        if action == "params":
            if len(parts) != 3:
                return "Usage: model params <provider>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            provider_model = prefs.variant_for_model(model) or "provider-default"
            spec = provider_model_spec(model, provider_model)
            params = prefs.params_for_model(model)
            reasoning_options = [] if spec is None else list(spec.reasoning_efforts)
            current_reasoning = params.get("reasoning_effort") or (None if spec is None else spec.reasoning_default)
            return "\n".join(
                [
                    f"Provider params for {model}:",
                    f"- provider_model: {provider_model}",
                    f"- reasoning_effort_supported: {', '.join(reasoning_options) or 'none'}",
                    f"- reasoning_effort_current: {current_reasoning or 'none'}",
                ]
            )
        if action == "preset":
            if len(parts) not in {3, 4}:
                return "Usage: model preset <provider> [fast|balanced|deep|plan]"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if len(parts) == 3:
                return _guided_model_choice(
                    requested_model=model,
                    prefs=prefs,
                    agent=agent,
                    config=config,
                    input_stream=input_stream,
                    output_stream=output_stream,
                )
            preset = parts[3]
            provider_model, params = provider_model_preset(model, preset)
            prefs.set_variant(model, provider_model)
            for key, value in params.items():
                prefs.set_model_param(model, key, value)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            params_text = ", ".join(f"{key}={value}" for key, value in sorted(params.items())) or "none"
            return f"Applied preset {preset} to {model}: provider_model={provider_model} params={params_text}."
        if action == "param":
            if len(parts) < 4:
                return "Usage: model param <set|clear> ..."
            subaction = parts[2]
            if subaction == "set":
                if len(parts) != 6:
                    return "Usage: model param set <provider> <key> <value>"
                model, key, value = parts[3], parts[4], parts[5]
                if model not in SUPPORTED_MODELS:
                    return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
                prefs.set_model_param(model, key, value)
                _save_model_preferences(config, prefs)
                _apply_model_preferences(agent, config)
                provider_model = prefs.variant_for_model(model) or "provider-default"
                return f"Set {key}={value} for {model}:{provider_model}."
            if subaction == "clear":
                if len(parts) != 5:
                    return "Usage: model param clear <provider> <key>"
                model, key = parts[3], parts[4]
                if model not in SUPPORTED_MODELS:
                    return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
                prefs.clear_model_param(model, key)
                _save_model_preferences(config, prefs)
                _apply_model_preferences(agent, config)
                return f"Cleared {key} for {model}."
            return "Usage: model param set <provider> <key> <value> | model param clear <provider> <key>"
        if action == "limits":
            if len(parts) != 2:
                return "Usage: model limits"
            _apply_model_preferences(agent, config)
            return _render_model_limits(agent, config)
        if action == "variant":
            if len(parts) != 4:
                return "Usage: model variant <name> <variant>"
            model, variant = parts[2], parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            canonical = canonicalize_model_variant(model, variant)
            prefs.set_variant(model, canonical)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Provider model for {model} set to {canonical}."
        if action == "variant-clear":
            if len(parts) != 3:
                return "Usage: model variant-clear <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            prefs.clear_variant(model)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Provider model pin for {model} cleared. Automatic/provider default selection restored."
        if action == "add":
            if len(parts) != 3:
                return "Usage: model add <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Enabled model {model}."
        if action == "remove":
            if len(parts) != 3:
                return "Usage: model remove <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if model not in prefs.enabled_models:
                return f"Model {model} is already disabled."
            if len(prefs.enabled_models) == 1:
                return "Cannot disable the last enabled model."
            prefs.enabled_models = [item for item in prefs.enabled_models if item != model]
            if prefs.preferred_model == model:
                prefs.preferred_model = None
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Disabled model {model}."
        if action == "block":
            if len(parts) != 5 or parts[3] != "until":
                return "Usage: model block <name> until YYYY-MM-DDTHH:MM"
            model = parts[2]
            until = parts[4]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            try:
                datetime.fromisoformat(until)
            except ValueError:
                return "Invalid date/time. Use YYYY-MM-DDTHH:MM."
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            prefs.blocked_until_by_model[model] = until
            if prefs.preferred_model == model:
                prefs.preferred_model = None
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Blocked model {model} until {until}."
        if action == "unblock":
            if len(parts) != 3:
                return "Usage: model unblock <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            if model not in prefs.blocked_until_by_model:
                return f"Model {model} is not blocked."
            prefs.blocked_until_by_model.pop(model, None)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Unblocked model {model}."
        if action == "clear":
            prefs.preferred_model = None
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return "Preferred provider cleared. Automatic routing restored."
    except ValueError as exc:
        return str(exc)

    return _model_usage()


def _model_usage() -> str:
    return (
        "Usage: model use <name> | model choose [name] | model add <name> | model list <name> | model inspect <provider> [provider_model] | "
        "model params <name> | model variant <name> <variant> | model variant-clear <name> | "
        "model preset <name> <fast|balanced|deep|plan> | "
        "model param set <name> <key> <value> | model param clear <name> <key> | "
        "model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | "
        "model unblock <name> | model limits | model limit-record <name> <message> | "
        "model limit-clear <name> | model clear"
    )


def _handle_account_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "accounts":
        return _render_accounts(config)
    if parts[0] != "account":
        return None
    if len(parts) < 2:
        return _account_usage()

    action = parts[1]
    prefs = _load_model_preferences(config)
    try:
        if action == "limit-record":
            fields = command[len("account limit-record ") :].split(maxsplit=2)
            if len(fields) != 3:
                return "Usage: account limit-record <model> <name> <provider message>"
            model, name, message = fields
            result = _record_limit_message(config, prefs, model=model, account=name, message=message)
            _apply_model_preferences(agent, config)
            return result
        if action == "limit-clear":
            fields = command[len("account limit-clear ") :].split(maxsplit=1)
            if len(fields) != 2:
                return "Usage: account limit-clear <model> <name>"
            model, name = fields
            result = _clear_limit_snapshot(config, prefs, model=model, account=name)
            _apply_model_preferences(agent, config)
            return result
        if action == "add":
            if len(parts) not in {4, 5}:
                return "Usage: account add <model> <name> [ENV_VAR]"
            model, name = parts[2], parts[3]
            prefs.add_account(model, name, env_var=parts[4] if len(parts) == 5 else None)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Added account {model}:{name}."
        if action == "login":
            if len(parts) != 4:
                return "Usage: account login <model> <name>"
            model, name = parts[2], parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            capability = provider_capability(model)
            if not capability.supports_browser_login or model not in {"chatgpt", "openai"}:
                return f"Interactive login is not supported for model '{model}'. {capability.login_hint}"
            prefs.add_account(model, name)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            if model == "chatgpt":
                result = CodexBrowserLoginFlow(model=model, account=name).run()
            else:
                result = OpenAIDeviceCodeFlow(model=model, account=name).run()
            if not result.ok:
                return result.message
            if result.secret_payload or result.token:
                saved = SecretStore().save_token(model, name, result.secret_payload or result.token)
                if not saved.ok:
                    return saved.message
            prefs.set_active_account(model, name)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            if result.secret_payload or result.token:
                return f"{result.message}\nSaved token for {model}:{name}."
            return result.message
        if action == "login-device":
            if len(parts) != 4:
                return "Usage: account login-device <chatgpt|openai> <name>"
            model, name = parts[2], parts[3]
            if model not in {"chatgpt", "openai"}:
                return "Device code login is supported only for chatgpt and openai."
            return _handle_account_command(
                f"account login {model} {name}",
                agent,
                config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "logout":
            if len(parts) != 4:
                return "Usage: account logout <model> <name>"
            model, name = parts[2], parts[3]
            if model == "chatgpt":
                browser_logout = CodexBrowserLogoutFlow(model=model).run()
                if not browser_logout.ok:
                    return browser_logout.message
            result = SecretStore().delete_token(model, name)
            if model == "chatgpt":
                return f"{browser_logout.message}\n{result.message}"
            return result.message
        if action == "env":
            if len(parts) != 5:
                return "Usage: account env <model> <name> <ENV_VAR>"
            model, name, env_var = parts[2], parts[3], parts[4]
            if name not in (prefs.accounts_by_model or {}).get(model, []):
                prefs.add_account(model, name)
            prefs.set_account_env(model, name, env_var)
            _save_model_preferences(config, prefs)
            return f"Set token env for {model}:{name} to {env_var}."
        if action == "import":
            if len(parts) not in {4, 5}:
                return "Usage: account import <model> <name> [PATH]"
            model, name = parts[2], parts[3]
            if model != "claude":
                return f"Import is not supported for model '{model}'."
            path = Path(parts[4]) if len(parts) == 5 else _default_claude_credentials_path()
            if path is None:
                return "No default Claude credentials path is available. Pass an explicit path."
            if not path.exists():
                return f"Credentials file not found: {path}"
            payload = read_text_utf8(path).strip()
            if not payload:
                return f"Credentials file is empty: {path}"
            prefs.add_account(model, name)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            saved = SecretStore().save_token(model, name, payload)
            if not saved.ok:
                return saved.message
            prefs.set_active_account(model, name)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Imported credentials for {model}:{name} from {path}."
        if action == "use":
            if len(parts) != 4:
                return "Usage: account use <model> <name>"
            model, name = parts[2], parts[3]
            prefs.set_active_account(model, name)
            _save_model_preferences(config, prefs)
            return f"Active account for {model} set to {name}."
        if action == "choose":
            if len(parts) > 3:
                return "Usage: account choose [model]"
            requested_model = parts[2] if len(parts) == 3 else None
            return _guided_account_choice(
                requested_model=requested_model,
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "remove":
            if len(parts) != 4:
                return "Usage: account remove <model> <name>"
            model, name = parts[2], parts[3]
            prefs.remove_account(model, name)
            _save_model_preferences(config, prefs)
            return f"Removed account {model}:{name}."
        if action == "block":
            if len(parts) != 6 or parts[4] != "until":
                return "Usage: account block <model> <name> until YYYY-MM-DDTHH:MM"
            model, name, until = parts[2], parts[3], parts[5]
            prefs.block_account(model, name, until)
            _save_model_preferences(config, prefs)
            return f"Blocked account {model}:{name} until {until}."
        if action == "unblock":
            if len(parts) != 4:
                return "Usage: account unblock <model> <name>"
            model, name = parts[2], parts[3]
            prefs.unblock_account(model, name)
            _save_model_preferences(config, prefs)
            return f"Unblocked account {model}:{name}."
        if action == "clear":
            if len(parts) != 3:
                return "Usage: account clear <model>"
            prefs.set_active_account(parts[2], None)
            _save_model_preferences(config, prefs)
            return f"Cleared active account for {parts[2]}."
    except ValueError as exc:
        return str(exc)
    return _account_usage()


def _account_usage() -> str:
    return (
        "Usage: accounts | account add <model> <name> [ENV_VAR] | account login <model> <name> | "
        "account login-device <chatgpt|openai> <name> | "
        "account logout <model> <name> | account env <model> <name> <ENV_VAR> | account import <model> <name> [PATH] | "
        "account use <model> <name> | account choose [model] | account remove <model> <name> | "
        "account block <model> <name> until YYYY-MM-DDTHH:MM | account unblock <model> <name> | "
        "account limit-record <model> <name> <message> | account limit-clear <model> <name> | account clear <model>"
    )


def _default_claude_credentials_path() -> Path | None:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / ".credentials.json"
    home = Path.home()
    if not str(home):
        return None
    return home / ".claude" / ".credentials.json"


def _guided_account_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided account selection is available in the interactive shell. Run `python3 -m stagewarden.main` and use `account choose`."
    models_with_accounts = [
        model
        for model in SUPPORTED_MODELS
        if (prefs.accounts_by_model or {}).get(model)
    ]
    if not models_with_accounts:
        return "No configured account profiles are available."
    model = requested_model
    if model is None:
        model = _prompt_menu_choice(
            title="Choose provider for account:",
            options=[(item, item) for item in models_with_accounts],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if model is None:
            return "Guided account selection cancelled."
    accounts = list((prefs.accounts_by_model or {}).get(model, []))
    if not accounts:
        return f"No configured account profiles for {model}."
    chosen_account = _prompt_menu_choice(
        title=f"Choose account for {model}:",
        options=[(name, name) for name in accounts],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if chosen_account is None:
        return "Guided account selection cancelled."
    prefs.set_active_account(model, chosen_account)
    _save_model_preferences(config, prefs)
    return f"Active account for {model} set to {chosen_account}."


def _handle_mode_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "status":
        if len(parts) == 2 and parts[1] == "full":
            return _render_status_full(agent, config)
        return _render_status(agent, config)
    if parts[0] == "statusline":
        return dumps_ascii(_statusline_report(agent, config), indent=2)
    if parts[0] == "preflight":
        return _render_preflight(agent, config)
    if len(parts) == 3 and parts[0] == "auth" and parts[1] == "status":
        return _render_auth_status(parts[2])
    if parts[0] == "overview":
        return _render_overview(agent, config)
    if parts[0] == "health":
        return _render_health(agent, config)
    if parts[0] == "report":
        return _render_report(agent, config)
    if parts[0] == "doctor":
        return _render_doctor(config)
    if parts[0] == "handoff":
        if len(parts) == 2 and parts[1] in {"md", "export"}:
            return _export_handoff_markdown(config)
        if len(parts) >= 2 and parts[1] == "actions":
            return _render_handoff_actions(config, limit=_parse_optional_limit(parts))
        return _render_handoff(config)
    if parts[0] == "board" or command == "stage review":
        return _render_board(config)
    if parts[0] == "boundary":
        return _render_boundary(config)
    if parts[0] == "risks":
        return _render_risks(config)
    if parts[0] == "issues":
        return _render_issues(config)
    if parts[0] == "quality":
        return _render_quality(config)
    if parts[0] == "exception":
        return _render_exception(config)
    if parts[0] == "lessons":
        return _render_lessons(config)
    if parts[0] in {"transcript", "trace"}:
        return _render_transcript(config)
    if parts[0] == "todo":
        return _render_todo(config)
    if parts[0] == "permissions":
        return _render_permissions(config)
    if parts[0] == "permission":
        return _handle_permission_command(parts, config, agent)
    if parts[0] == "shell":
        return _handle_shell_command(parts, config)
    if parts[0] != "mode":
        return None
    if len(parts) == 2:
        mode = parts[1].strip().lower().replace("-", "_")
        if mode in VALID_PERMISSION_MODES:
            settings = PermissionSettings.load(config.settings_path)
            settings.default_mode = mode
            settings.normalize().save(config.settings_path)
            _refresh_runtime_permissions(agent)
            return f"Permission mode set to {mode}."
    if len(parts) == 2 and parts[1] == "normal":
        result = agent.run("normal mode")
        return result.message
    if len(parts) == 3 and parts[1] == "caveman":
        result = agent.run(f"/caveman {parts[2]}")
        return result.message
    return (
        "Usage: mode <normal|default|accept_edits|accept-edits|plan|auto|dont_ask|dont-ask> "
        "| mode caveman <level>"
    )


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
                _refresh_runtime_permissions(agent)
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
                _refresh_runtime_permissions(agent)
            return f"Added session {session_action} rule: {rule}"
        if session_action == "reset":
            config.session_permission_settings = None
            if agent is not None:
                _refresh_runtime_permissions(agent)
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
            _refresh_runtime_permissions(agent)
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
            _refresh_runtime_permissions(agent)
        return f"Added {action} rule: {rule}"
    if action == "reset":
        PermissionSettings().save(config.settings_path)
        if agent is not None:
            _refresh_runtime_permissions(agent)
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
            return _render_shell_backend(config)
        if len(parts) == 4 and parts[2] == "use":
            backend = parts[3].strip().lower()
            if backend not in {"auto", "bash", "zsh", "powershell", "cmd"}:
                return "Usage: shell backend use <auto|bash|zsh|powershell|cmd>"
            _save_shell_backend(config, backend)
            config.shell_backend = backend
            return f"Shell backend set to {backend}.\n{_render_shell_backend(config)}"
    return "Usage: shell backend | shell backend use <auto|bash|zsh|powershell|cmd>"


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


def _git_command_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    parts = command.split()
    if not parts or parts[0] != "git":
        return None
    tool = GitTool(config)
    if len(parts) == 2 and parts[1] == "status":
        result = tool.status()
        return {
            "command": "git status",
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
                "ok": False,
                "error": "Usage: git history <path> [limit]",
            }
        limit = _parse_limit(parts[3] if len(parts) == 4 else "", default=20)
        result = tool.file_history(parts[2], limit=limit)
        return {
            "command": "git history",
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
            "revision": revision,
            "stat": stat,
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "lines": result.stdout.splitlines() if result.stdout else [],
        }
    return {
        "command": "git",
        "ok": False,
        "error": "Usage: git status | git log [limit] | git history <path> [limit] | git show [--stat] [revision]",
    }


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
    return {"command": "file", "ok": False, "error": "Usage: file inspect <path> | file stat <path> | file copy <source> <destination> [--overwrite] [--dry-run] | file move <source> <destination> [--overwrite] [--dry-run] | file delete <path> [--recursive] [--dry-run] | file chmod <path> <mode> [--recursive] [--dry-run] | file chown <path> <user> [group] [--recursive] [--dry-run]"}


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


def _resolve_shell_session_id(agent: Agent, requested: str) -> str | None:
    sessions = agent.executor.shell.sessions
    if requested == "last":
        if not sessions:
            return None
        return next(reversed(sessions))
    return requested if requested in sessions else None


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
        "count": len(items),
        "items": items,
    }


def _parse_limit(raw: str, *, default: int) -> int:
    if not raw:
        return default
    try:
        return max(1, min(int(raw), 200))
    except ValueError:
        return default


def _default_ljson_encode_path(source: Path, *, gzip_enabled: bool) -> Path:
    if gzip_enabled:
        return source.with_suffix(".ljson.gz")
    return source.with_suffix(".ljson")


def _default_ljson_decode_path(source: Path) -> Path:
    if source.suffix == ".gz":
        without_gzip = source.with_suffix("")
        return without_gzip.with_suffix(".json")
    return source.with_suffix(".json")


def _workspace_relative_candidates(config: AgentConfig, partial: str) -> list[str]:
    workspace = config.workspace_root.resolve()
    partial = partial.strip()
    candidate = workspace / partial if partial else workspace
    parent = candidate.parent if partial and not partial.endswith("/") else candidate
    if not parent.exists() or not parent.is_dir():
        return []
    base_prefix = candidate.name if partial and not partial.endswith("/") else ""
    suggestions: list[str] = []
    for item in sorted(parent.iterdir(), key=lambda path: path.name.lower()):
        if base_prefix and not item.name.lower().startswith(base_prefix.lower()):
            continue
        try:
            relative = item.relative_to(workspace)
        except ValueError:
            continue
        text = relative.as_posix()
        if item.is_dir():
            text += "/"
        suggestions.append(text)
    return suggestions


def _prefixed_candidates(prefix: str, options: list[str], partial: str) -> list[str]:
    lowered = partial.strip().lower()
    matches = [option for option in options if option.lower().startswith(lowered)]
    return [f"{INTERACTIVE_COMMAND_PREFIX}{prefix}{item}" for item in matches]


def _provider_model_candidates(provider: str, partial: str) -> list[str]:
    try:
        specs = provider_model_specs(provider)
    except ValueError:
        return []
    lowered = partial.strip().lower()
    return [spec.id for spec in specs if spec.id.lower().startswith(lowered)]


def _reasoning_effort_candidates(provider: str, provider_model: str, partial: str) -> list[str]:
    spec = provider_model_spec(provider, provider_model)
    if spec is None:
        return []
    lowered = partial.strip().lower()
    return [effort for effort in spec.reasoning_efforts if effort.lower().startswith(lowered)]


def _account_name_candidates(config: AgentConfig, provider: str, partial: str) -> list[str]:
    try:
        prefs = _load_model_preferences(config)
    except OSError:
        return []
    accounts = list((prefs.accounts_by_model or {}).get(provider, []))
    return _prefixed_candidates(f"account use {provider} ", accounts, partial)


def _interactive_contextual_candidates(normalized: str, config: AgentConfig) -> list[str]:
    lowered = normalized.lower()
    provider_options = list(SUPPORTED_MODELS)
    role_options = list(PRINCE2_ROLE_IDS)
    backend_options = ["auto", "bash", "zsh", "powershell", "cmd"]
    if lowered.startswith("model variant "):
        parts = normalized.split()
        if len(parts) >= 3:
            provider = parts[2].strip().lower()
            if provider in SUPPORTED_MODELS:
                typed_after_provider = normalized.split(None, 3)
                partial = typed_after_provider[3] if len(typed_after_provider) > 3 else ""
                return _prefixed_candidates(
                    f"model variant {provider} ",
                    _provider_model_candidates(provider, partial),
                    partial,
                )
    if lowered.startswith("model param set "):
        parts = normalized.split()
        if len(parts) == 4:
            provider = parts[3].strip().lower()
            if provider in SUPPORTED_MODELS:
                return [f"{INTERACTIVE_COMMAND_PREFIX}model param set {provider} reasoning_effort "]
        if len(parts) >= 5:
            provider = parts[3].strip().lower()
            key = parts[4].strip().lower()
            if provider in SUPPORTED_MODELS and key == "reasoning_effort":
                prefs = _load_model_preferences(config)
                provider_model = prefs.variant_for_model(provider) or provider_capability(provider).default_model
                typed_after_key = normalized.split(None, 5)
                partial = typed_after_key[5] if len(typed_after_key) > 5 else ""
                return _prefixed_candidates(
                    f"model param set {provider} reasoning_effort ",
                    _reasoning_effort_candidates(provider, provider_model, partial),
                    partial,
                )
    for prefix in ("account use ", "account logout ", "account remove ", "account block ", "account unblock ", "account limit-record ", "account limit-clear "):
        if lowered.startswith(prefix):
            parts = normalized.split()
            if len(parts) >= 3:
                provider = parts[2].strip().lower()
                if provider in SUPPORTED_MODELS:
                    typed_after_provider = normalized.split(None, 3)
                    partial = typed_after_provider[3] if len(typed_after_provider) > 3 else ""
                    return _prefixed_candidates(f"{prefix}{provider} ", list((_load_model_preferences(config).accounts_by_model or {}).get(provider, [])), partial)
    prefix_map = (
        ("model use ", provider_options),
        ("model choose ", provider_options),
        ("model preset ", provider_options),
        ("model add ", provider_options),
        ("model remove ", provider_options),
        ("model list ", provider_options),
        ("model params ", provider_options),
        ("model variant ", provider_options),
        ("model variant-clear ", provider_options),
        ("model block ", provider_options),
        ("model unblock ", provider_options),
        ("model limit-record ", provider_options),
        ("model limit-clear ", provider_options),
        ("model param set ", provider_options),
        ("model param clear ", provider_options),
        ("account add ", provider_options),
        ("account choose ", provider_options),
        ("account login ", provider_options),
        ("account login-device ", ["chatgpt", "openai"]),
        ("account import ", provider_options),
        ("account env ", provider_options),
        ("account use ", provider_options),
        ("account logout ", provider_options),
        ("account remove ", provider_options),
        ("account block ", provider_options),
        ("account unblock ", provider_options),
        ("account limit-record ", provider_options),
        ("account limit-clear ", provider_options),
        ("account clear ", provider_options),
        ("role configure ", role_options),
        ("role clear ", role_options),
        ("shell backend use ", backend_options),
    )
    for prefix, options in prefix_map:
        if lowered.startswith(prefix):
            partial = normalized[len(prefix) :]
            return _prefixed_candidates(prefix, options, partial)
    return []


def _ranked_command_phrase_matches(lowered: str) -> list[str]:
    exact: list[str] = []
    word_boundary: list[str] = []
    contains: list[str] = []
    for phrase in INTERACTIVE_COMMAND_PHRASES:
        candidate = phrase.lower()
        if candidate == lowered:
            exact.append(phrase)
        elif candidate.startswith(lowered):
            exact.append(phrase)
        elif any(part.startswith(lowered) for part in candidate.split()):
            word_boundary.append(phrase)
        elif lowered and lowered in candidate:
            contains.append(phrase)
    ordered = exact + word_boundary + contains
    unique: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    if not unique and lowered:
        unique = [spec.name for spec in command_specs_by_query(lowered)[:20]]
    return [f"{INTERACTIVE_COMMAND_PREFIX}{phrase}" for phrase in unique]


def _interactive_completion_candidates(text: str, config: AgentConfig) -> list[str]:
    normalized = text.lstrip()
    if not normalized.startswith(INTERACTIVE_COMMAND_PREFIX):
        return []
    normalized = normalized[len(INTERACTIVE_COMMAND_PREFIX) :]
    lowered = normalized.lower()
    path_prefixes = (
        "git history ",
        "patch preview ",
        "session create ",
        "file inspect ",
        "file stat ",
        "file delete ",
        "file chmod ",
        "file chown ",
    )
    for prefix in path_prefixes:
        if lowered.startswith(prefix):
            partial = normalized[len(prefix) :]
            return [f"{INTERACTIVE_COMMAND_PREFIX}{prefix}{entry}" for entry in _workspace_relative_candidates(config, partial)]
    contextual = _interactive_contextual_candidates(normalized, config)
    if contextual:
        return contextual
    if lowered.startswith("git show "):
        return [
            f"{INTERACTIVE_COMMAND_PREFIX}{item}"
            for item in ("git show HEAD", "git show --stat HEAD")
            if item.startswith(lowered)
        ]
    return _ranked_command_phrase_matches(lowered)


def _configure_readline(config: AgentConfig) -> bool:
    if readline is None:
        return False
    history_path = config.history_path
    try:
        readline.set_history_length(1000)
        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")
        if history_path.exists():
            readline.read_history_file(str(history_path))

        def completer(text: str, state: int) -> str | None:
            buffer = readline.get_line_buffer()
            candidates = _interactive_completion_candidates(buffer, config)
            if state < len(candidates):
                return candidates[state]
            return None

        readline.set_completer(completer)

        def save_history() -> None:
            try:
                readline.write_history_file(str(history_path))
            except OSError:
                pass

        atexit.register(save_history)
        return True
    except Exception:
        return False


def _rewrite_shell_command(command: str, agent: Agent) -> tuple[str | None, str | None]:
    lowered = command.lower().strip()
    if lowered == "help":
        return None, interactive_help_text()
    if lowered in {"help topics", "help topics --json", "help --json"}:
        return None, dumps_ascii(_help_json_report(), indent=2) if lowered.endswith("--json") else interactive_help_text()
    if lowered == "slash choose":
        return None, _render_slash_choice_candidates(agent.config)
    if lowered.startswith("slash choose "):
        query = command.split(maxsplit=2)[2]
        return None, _render_slash_choice_candidates(agent.config, query)
    if lowered == "slash":
        return None, _render_slash_palette(agent.config)
    if lowered == "slash --json":
        return None, dumps_ascii(_slash_palette_report(agent.config), indent=2)
    if lowered.startswith("slash "):
        prefix = command.split(maxsplit=1)[1]
        if prefix.endswith(" --json"):
            prefix = prefix[: -len(" --json")].strip()
            return None, dumps_ascii(_slash_palette_report(agent.config, prefix), indent=2)
        return None, _render_slash_palette(agent.config, prefix)
    if lowered == "commands":
        return None, render_command_catalog()
    if lowered == "commands --json":
        return None, dumps_ascii({"command": "commands", "commands": command_catalog()}, indent=2)
    if lowered.startswith("help "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii(_help_json_report(), indent=2)
        if topic.lower().strip() == "caveman":
            return None, agent.caveman.help_text()
        if topic.lower().strip() == "topics":
            return None, interactive_help_text()
        if topic.lower().strip().endswith(" --json"):
            raw_topic = topic[: -len(" --json")].strip()
            if raw_topic.lower() == "caveman":
                return None, dumps_ascii({"command": "help", "ok": True, "topic": "caveman", "title": "Caveman", "message": "Use `help caveman` for the rich caveman help surface."}, indent=2)
            return None, dumps_ascii(_help_json_report(raw_topic), indent=2)
        return None, interactive_help_text(topic)
    if lowered.startswith("commands "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii({"command": "commands", "commands": command_catalog()}, indent=2)
        return None, interactive_help_text(topic)
    if lowered in {"caveman help", "help caveman"}:
        return None, agent.caveman.help_text()
    if lowered.startswith("caveman on"):
        parts = command.split(maxsplit=2)
        level = parts[2] if len(parts) == 3 else "full"
        return f"/caveman {level}", None
    if lowered in {"caveman off", "stop caveman", "normal mode"}:
        return "stop caveman", None
    if lowered == "caveman commit":
        return "/caveman commit", None
    if lowered == "caveman review":
        return "/caveman review", None
    if lowered.startswith("caveman compress "):
        return f"/caveman compress {command.split(maxsplit=2)[2]}", None
    return command, None


def _is_known_interactive_command(command: str) -> bool:
    normalized = command.strip().lower()
    if not normalized:
        return False
    if normalized in INTERACTIVE_COMMAND_PHRASES:
        return True
    prefixes = (
        "help ",
        "commands ",
        "auth status ",
        "model ",
        "account ",
        "roles ",
        "role ",
        "project ",
        "sources ",
        "permission ",
        "mode ",
        "caveman ",
        "git ",
        "file ",
        "session ",
        "patch preview ",
        "resume ",
        "handoff ",
    )
    return any(normalized.startswith(prefix) for prefix in prefixes)


def _permission_rule_from_decision(capability: str, detail: str, source: str) -> str:
    if source.startswith("ask:"):
        rule = source.split(":", 1)[1].strip()
        if rule:
            return rule
    family = capability.split(":", 1)[0]
    return f"{family}:{detail.strip()}" if detail.strip() else capability


def _remove_rule(items: list[str], rule: str) -> list[str]:
    normalized = rule.strip().lower()
    return [item for item in items if item.strip().lower() != normalized]


def _make_permission_approver(
    *,
    config: AgentConfig,
    input_stream: TextIO,
    output_stream: TextIO,
    get_agent: Callable[[], Agent],
) -> Callable[[str, str, object], bool]:
    def approve(capability: str, detail: str, decision: object) -> bool:
        source = getattr(decision, "source", "")
        rule = _permission_rule_from_decision(capability, detail, str(source))
        output_stream.write(
            "Permission approval required:\n"
            f"- capability: {capability}\n"
            f"- target: {detail or '-'}\n"
            f"- rule: {rule}\n"
            "Approve? [y/n/always/session/deny] "
        )
        output_stream.flush()
        answer = input_stream.readline()
        if answer == "":
            output_stream.write("\nPermission denied: no approval input.\n")
            output_stream.flush()
            return False
        choice = answer.strip().lower()
        if choice in {"y", "yes"}:
            output_stream.write("Permission approved once.\n")
            output_stream.flush()
            return True
        if choice in {"session", "s"}:
            session = config.session_permission_settings or PermissionSettings()
            if rule not in session.allow:
                session.allow.append(rule)
            config.session_permission_settings = session.normalize()
            agent = get_agent()
            agent.refresh_permissions()
            output_stream.write(f"Permission approved for this session: {rule}\n")
            output_stream.flush()
            return True
        if choice in {"always", "a"}:
            settings = PermissionSettings.load(config.settings_path)
            if rule not in settings.allow:
                settings.allow.append(rule)
            settings.ask = _remove_rule(settings.ask, rule)
            settings.normalize().save(config.settings_path)
            agent = get_agent()
            agent.refresh_permissions()
            output_stream.write(f"Permission persisted as allow rule: {rule}\n")
            output_stream.flush()
            return True
        if choice in {"deny", "d"}:
            settings = PermissionSettings.load(config.settings_path)
            if rule not in settings.deny:
                settings.deny.append(rule)
            settings.normalize().save(config.settings_path)
            agent = get_agent()
            agent.refresh_permissions()
            output_stream.write(f"Permission persisted as deny rule: {rule}\n")
            output_stream.flush()
            return False
        output_stream.write("Permission denied.\n")
        output_stream.flush()
        return False

    return approve


def _make_rate_limit_decider(*, input_stream: TextIO, output_stream: TextIO) -> Callable[[str, str | None, list[str]], str]:
    def decide(provider: str, blocked_until: str | None, alternatives: list[str]) -> str:
        if alternatives:
            choice = alternatives[0]
            output_stream.write(
                f"Provider {provider} is rate-limited"
                f"{' until ' + blocked_until if blocked_until else ''}. "
                f"Automatically switching to {choice}.\n"
            )
            output_stream.flush()
            return choice
        output_stream.write(
            f"Provider {provider} is rate-limited"
            f"{' until ' + blocked_until if blocked_until else ''} and no alternative provider is available.\n"
            "Choose `wait` to stop and retry after unlock, or `stop` to fail this step now: "
        )
        output_stream.flush()
        answer = input_stream.readline()
        if answer == "":
            return "stop"
        normalized = answer.strip().lower()
        return "wait" if normalized in {"wait", "w", "aspetta", "attendi"} else "stop"

    return decide


def run_interactive_shell(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    agent = _configure_agent_for_workspace(config)
    stream_enabled = True

    def apply_stream_callback(current_agent: Agent) -> None:
        if stream_enabled:
            current_agent.handoff.stream_callback = lambda chunk: (sink.write(chunk), sink.flush())
        else:
            current_agent.handoff.stream_callback = None

    apply_stream_callback(agent)
    config.permission_approver = _make_permission_approver(
        config=config,
        input_stream=source,
        output_stream=sink,
        get_agent=lambda: agent,
    )
    config.rate_limit_decider = _make_rate_limit_decider(input_stream=source, output_stream=sink)

    sink.write(f"Stagewarden interactive shell in {config.workspace_root}\n")
    sink.write("Type '/help' for commands. Any input without '/' is treated as a task.\n")
    if source is sys.stdin and sink is sys.stdout and _configure_readline(config):
        sink.write(f"History file: {config.history_path.name}\n")
    sink.flush()

    while True:
        sink.write("stagewarden> ")
        sink.flush()
        line = source.readline()
        if line == "":
            sink.write("\n")
            sink.flush()
            return 0

        command = line.strip()
        if not command:
            continue
        legacy_shell_command = (
            not command.startswith(INTERACTIVE_COMMAND_PREFIX)
            and source is not sys.stdin
            and _is_known_interactive_command(command)
        )
        if not command.startswith(INTERACTIVE_COMMAND_PREFIX) and not legacy_shell_command:
            sink.write(f"Running task: {command}\n")
            sink.write(f"{_render_shell_progress(agent, phase='before', command=command)}\n")
            sink.flush()
            result = agent.run(command)
            sink.write("Agent result:\n")
            sink.write(f"{result.message}\n")
            sink.write(f"{_render_last_step_outcome(agent)}\n")
            sink.write(f"{_render_shell_progress(agent, phase='after')}\n")
            sink.flush()
            continue
        shell_command = command[len(INTERACTIVE_COMMAND_PREFIX) :].strip() if command.startswith(INTERACTIVE_COMMAND_PREFIX) else command
        if not shell_command:
            sink.write("Command prefix detected but no command was provided. Use '/help'.\n")
            sink.flush()
            continue
        if shell_command in {"exit", "quit"}:
            sink.write("Session closed.\n")
            sink.flush()
            return 0
        if shell_command == "reset":
            config.session_permission_settings = None
            agent = _configure_agent_for_workspace(config)
            apply_stream_callback(agent)
            config.permission_approver = _make_permission_approver(
                config=config,
                input_stream=source,
                output_stream=sink,
                get_agent=lambda: agent,
            )
            sink.write("Session reset.\n")
            sink.flush()
            continue
        if shell_command in {"stream on", "stream off", "stream status"}:
            if shell_command == "stream status":
                sink.write(f"Model streaming is {'on' if stream_enabled else 'off'}.\n")
                sink.flush()
                continue
            stream_enabled = shell_command == "stream on"
            apply_stream_callback(agent)
            sink.write(f"Model streaming {'enabled' if stream_enabled else 'disabled'} for this session.\n")
            sink.flush()
            continue
        if shell_command == "slash choose" or shell_command.startswith("slash choose "):
            query = "" if shell_command == "slash choose" else shell_command.split(maxsplit=2)[2]
            sink.write(f"{_guided_slash_choice(config, query, input_stream=source, output_stream=sink)}\n")
            sink.flush()
            continue
        rewritten, immediate = _rewrite_shell_command(shell_command, agent)
        if immediate is not None:
            sink.write(f"{immediate}\n")
            sink.flush()
            continue
        shell_command = rewritten or shell_command
        model_message = _handle_model_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if model_message is not None:
            sink.write(f"{model_message}\n")
            sink.flush()
            continue
        account_message = _handle_account_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if account_message is not None:
            sink.write(f"{account_message}\n")
            sink.flush()
            continue
        project_brief_message = _handle_project_brief_command(shell_command, config)
        if project_brief_message is not None:
            sink.write(f"{project_brief_message}\n")
            sink.flush()
            continue
        if shell_command in {"project tree propose", "project tree propose --ai"}:
            use_ai = shell_command.endswith(" --ai")
            report = _project_tree_proposal_report(config, agent=agent, use_ai=use_ai)
            _record_project_tree_proposal_action(config, report, task=shell_command)
            sink.write(f"{_render_project_tree_proposal_report(report)}\n")
            sink.flush()
            continue
        if shell_command in {"project tree approve", "project tree approve --force"}:
            sink.write(f"{_render_project_tree_approval(config, force=shell_command.endswith(' --force'))}\n")
            sink.flush()
            continue
        role_message = _handle_role_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if role_message is not None:
            sink.write(f"{role_message}\n")
            sink.flush()
            continue
        sources_message = _handle_sources_command(shell_command, config)
        if sources_message is not None:
            sink.write(f"{sources_message}\n")
            sink.flush()
            continue
        update_message = _handle_update_command(shell_command, config)
        if update_message is not None:
            sink.write(f"{update_message}\n")
            sink.flush()
            continue
        extension_message = _handle_extension_command(shell_command, config)
        if extension_message is not None:
            sink.write(f"{extension_message}\n")
            sink.flush()
            continue
        external_io_message = _handle_external_io_command(shell_command, config)
        if external_io_message is not None:
            sink.write(f"{external_io_message}\n")
            sink.flush()
            continue
        mode_message = _handle_mode_command(shell_command, agent, config)
        if mode_message is not None:
            sink.write(f"{mode_message}\n")
            sink.flush()
            continue
        resume_message = _handle_resume_command(shell_command, agent, config)
        if resume_message is not None:
            sink.write(f"{resume_message}\n")
            sink.flush()
            continue
        git_message = _handle_git_command(shell_command, config)
        if git_message is not None:
            sink.write(f"{git_message}\n")
            sink.flush()
            continue
        file_message = _handle_file_command(shell_command, config)
        if file_message is not None:
            sink.write(f"{file_message}\n")
            sink.flush()
            continue
        shell_session_message = _handle_shell_session_command(shell_command, agent)
        if shell_session_message is not None:
            sink.write(f"{shell_session_message}\n")
            sink.flush()
            continue
        patch_message = _handle_patch_command(shell_command, agent)
        if patch_message is not None:
            sink.write(f"{patch_message}\n")
            sink.flush()
            continue
        sink.write(f"Unknown slash command: /{shell_command}\n")
        sink.write("Use '/help' for available commands or remove '/' to send a task to the agent.\n")
        sink.flush()


def main() -> int:
    args = build_parser().parse_args()
    config = AgentConfig(
        workspace_root=Path.cwd(),
        max_steps=args.max_steps,
        verbose=args.verbose,
        strict_ascii_output=args.strict_ascii_output,
    )
    config.shell_backend = _configured_shell_backend(config)

    if args.ljson_encode:
        source = Path(args.ljson_encode)
        records = loads_text(read_text_utf8(source))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-encode must be a JSON array.")
        target = Path(args.ljson_output) if args.ljson_output else _default_ljson_encode_path(source, gzip_enabled=args.ljson_gzip)
        dump_file(
            target,
            records,
            options=LJSONOptions(numeric_keys=args.ljson_numeric),
            gzip_enabled=args.ljson_gzip,
        )
        print(str(target))
        return 0

    if args.ljson_decode:
        source = Path(args.ljson_decode)
        records = load_file(source, gzipped=args.ljson_gzip or str(source).endswith(".gz"))
        target = Path(args.ljson_output) if args.ljson_output else _default_ljson_decode_path(source)
        write_text_utf8(target, dumps_ascii(records, indent=2))
        print(str(target))
        return 0

    if args.ljson_benchmark:
        records = loads_text(read_text_utf8(Path(args.ljson_benchmark)))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-benchmark must be a JSON array.")
        print(dumps_ascii(
            {
                "standard": benchmark_sizes(records),
                "numeric": benchmark_sizes(records, numeric_keys=True),
                "standard_gzip": benchmark_sizes(records, gzip_enabled=True),
                "numeric_gzip": benchmark_sizes(records, numeric_keys=True, gzip_enabled=True),
            },
            indent=2,
        ))
        return 0

    task = " ".join(args.task).strip()
    if args.caveman_help:
        task = "/caveman help"
    elif args.caveman_commit:
        task = "/caveman commit"
    elif args.caveman_review:
        task = "/caveman review"
    elif args.caveman_compress:
        task = f"/caveman compress {args.caveman_compress}"
    elif args.caveman:
        task = f"/caveman {args.caveman} {task}".strip()
    elif args.interactive or not task:
        return run_interactive_shell(config)
    if task in {"help", "help topics", "help --json", "help topics --json"}:
        if args.json or task.endswith("--json"):
            print(dumps_ascii(_help_json_report(), indent=2))
        else:
            print(interactive_help_text())
        return 0
    if task.startswith("help "):
        topic = task.split(maxsplit=1)[1]
        if topic == "--json":
            print(dumps_ascii(_help_json_report(), indent=2))
            return 0
        if topic.endswith(" --json"):
            raw_topic = topic[: -len(" --json")].strip()
            if raw_topic.lower() == "caveman":
                print(dumps_ascii({"command": "help", "ok": True, "topic": "caveman", "title": "Caveman", "message": "Use `help caveman` for the rich caveman help surface."}, indent=2))
            else:
                print(dumps_ascii(_help_json_report(raw_topic), indent=2))
            return 0
        if args.json:
            print(dumps_ascii(_help_json_report(topic), indent=2))
        elif topic.lower() == "caveman":
            print(Agent(config=config).caveman.help_text())
        elif topic.lower() == "topics":
            print(interactive_help_text())
        else:
            print(interactive_help_text(topic))
        return 0
    if task in {"commands", "commands --json"}:
        if args.json or task == "commands --json":
            print(dumps_ascii({"command": "commands", "commands": command_catalog()}, indent=2))
        else:
            print(render_command_catalog())
        return 0
    if task == "slash choose" or task.startswith("slash choose "):
        query = "" if task == "slash choose" else task.split(maxsplit=2)[2]
        if args.json:
            print(dumps_ascii({"command": "slash choose", "query": query, "entries": _slash_palette_report(config, query)["entries"][:10]}, indent=2))
        else:
            print(_render_slash_choice_candidates(config, query))
        return 0
    if task == "slash" or task.startswith("slash "):
        prefix = "" if task == "slash" else task.split(maxsplit=1)[1]
        if prefix.endswith(" --json"):
            prefix = prefix[: -len(" --json")].strip()
        if args.json or task.endswith(" --json"):
            print(dumps_ascii(_slash_palette_report(config, prefix), indent=2))
        else:
            print(_render_slash_palette(config, prefix))
        return 0
    if task == "doctor":
        report = _doctor_report(config)
        rendered = _render_doctor(config)
        if args.json:
            print(dumps_ascii(report, indent=2))
        else:
            print(rendered)
        return 0 if _doctor_ok(rendered) else 1
    if task == "status":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_status_dashboard_report(agent, config) if args.full else _status_report(agent, config), indent=2))
        else:
            print(_render_status_full(agent, config) if args.full else _render_status(agent, config))
        return 0
    if task in {"status full", "status --full"}:
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_status_dashboard_report(agent, config), indent=2))
        else:
            print(_render_status_full(agent, config))
        return 0
    if task == "statusline":
        agent = _configure_readonly_agent_for_workspace(config)
        print(dumps_ascii(_statusline_report(agent, config), indent=2))
        return 0
    if task == "preflight":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_preflight_report(agent, config), indent=2))
        else:
            print(_render_preflight(agent, config))
        return 0
    if task == "shell backend":
        if args.json:
            print(dumps_ascii(_shell_backend_report(config), indent=2))
        else:
            print(_render_shell_backend(config))
        return 0
    if task.startswith("shell backend use "):
        response = _handle_shell_command(task.split(), config)
        payload = {"command": "shell backend use", "message": response, "report": _shell_backend_report(config)}
        if args.json:
            print(dumps_ascii(payload, indent=2))
        else:
            print(response)
        return 0
    if task.startswith("auth status "):
        provider = task.split(maxsplit=2)[2]
        if args.json:
            print(dumps_ascii(_auth_status_report(provider), indent=2))
        else:
            print(_render_auth_status(provider))
        return 0
    if task == "overview":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_overview_report(agent, config), indent=2))
        else:
            print(_render_overview(agent, config))
        return 0
    if task == "health":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_health_report(agent, config), indent=2))
        else:
            print(_render_health(agent, config))
        return 0
    if task == "report":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_report_report(agent, config), indent=2))
        else:
            print(_render_report(agent, config))
        return 0
    if task == "models":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_model_status_report(agent, config), indent=2))
        else:
            print(_render_model_status(agent, config))
        return 0
    if task in {"model limits", "models limits"}:
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_model_limits_report(agent, config), indent=2))
        else:
            print(_render_model_limits(agent, config))
        return 0
    if (
        task.startswith("model limit-record ")
        or task.startswith("account limit-record ")
        or task.startswith("model limit-clear ")
        or task.startswith("account limit-clear ")
    ):
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_model_command(task, agent, config)
        if response is None:
            response = _handle_account_command(task, agent, config)
        payload = {"command": " ".join(task.split()[:2]), "message": response}
        if args.json:
            print(dumps_ascii(payload, indent=2))
        else:
            print(response or "No limit message recorded.")
        return 0 if response else 1
    if task == "model inspect" or task.startswith("model inspect "):
        agent = _configure_readonly_agent_for_workspace(config)
        parts = task.split()
        if len(parts) not in {3, 4}:
            payload = {"command": "model inspect", "ok": False, "error": "Usage: model inspect <provider> [provider_model]"}
            if args.json:
                print(dumps_ascii(payload, indent=2))
            else:
                print(payload["error"])
            return 1
        provider = parts[2]
        provider_model = parts[3] if len(parts) == 4 else None
        try:
            report = _inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)
        except ValueError as exc:
            payload = {"command": "model inspect", "ok": False, "error": str(exc)}
            if args.json:
                print(dumps_ascii(payload, indent=2))
            else:
                print(payload["error"])
            return 1
        if args.json:
            print(dumps_ascii(report, indent=2))
        else:
            print(_render_provider_model_inspection(report))
        return 0
    if task.startswith("model "):
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_model_command(task, agent, config)
        if response is None:
            print(_model_usage())
            return 1
        if args.json:
            print(dumps_ascii({"command": task, "message": response, "models": _model_status_report(agent, config)}, indent=2))
        else:
            print(response)
        return 0
    if task == "accounts":
        if args.json:
            print(dumps_ascii(_accounts_report(config), indent=2))
        else:
            print(_render_accounts(config))
        return 0
    if task == "roles":
        if args.json:
            print(dumps_ascii(_prince2_roles_report(config), indent=2))
        else:
            print(_render_prince2_roles(config))
        return 0
    if task == "project brief":
        if args.json:
            print(dumps_ascii(_project_brief_report(config), indent=2))
        else:
            print(_render_project_brief(config))
        return 0
    if task == "project design":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_project_design_report(agent, config), indent=2))
        else:
            print(_render_project_design(agent, config))
        return 0
    if task in {"project tree propose", "project tree propose --ai"}:
        use_ai = task.endswith(" --ai")
        agent = _configure_readonly_agent_for_workspace(config) if use_ai else None
        report = _project_tree_proposal_report(config, agent=agent, use_ai=use_ai)
        _record_project_tree_proposal_action(config, report, task=task)
        if args.json:
            print(dumps_ascii(report, indent=2))
        else:
            print(_render_project_tree_proposal_report(report))
        return 0
    if task in {"project tree approve", "project tree approve --force"}:
        force = task.endswith(" --force")
        report = _approve_project_tree_proposal(config, force=force)
        if args.json:
            print(dumps_ascii(report, indent=2))
        else:
            print(_render_project_tree_approval_report(report, config))
        return 0 if report["status"] == "approved" else 1
    if task == "roles domains":
        if args.json:
            print(dumps_ascii(_prince2_role_domains_report(), indent=2))
        else:
            print(_render_prince2_role_domains())
        return 0
    if task == "roles tree":
        if args.json:
            print(dumps_ascii(_prince2_role_tree_report(config), indent=2))
        else:
            print(_render_prince2_role_tree(config))
        return 0
    if task == "roles tree approve":
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_role_command(task, agent, config)
        if args.json:
            print(dumps_ascii(_prince2_role_tree_baseline_report(config), indent=2))
        else:
            print(response)
        return 0
    if task == "roles baseline":
        if args.json:
            print(dumps_ascii(_prince2_role_tree_baseline_report(config), indent=2))
        else:
            print(_render_prince2_role_tree_baseline(config))
        return 0
    if task == "roles baseline matrix":
        if args.json:
            print(dumps_ascii(_prince2_role_tree_baseline_matrix_report(config), indent=2))
        else:
            print(_render_prince2_role_tree_baseline_matrix(config))
        return 0
    if task.startswith("roles context "):
        node_id = task.split(maxsplit=2)[2]
        if args.json:
            print(dumps_ascii(_prince2_role_context_report(config, node_id), indent=2))
        else:
            print(_render_prince2_role_context(config, node_id))
        return 0
    if task == "roles active":
        if args.json:
            print(dumps_ascii(_prince2_role_active_report(config), indent=2))
        else:
            print(_render_prince2_role_active(config))
        return 0
    if task == "roles control":
        if args.json:
            print(dumps_ascii(_prince2_role_control_report(config), indent=2))
        else:
            print(_render_prince2_role_control(config))
        return 0
    if task == "roles queues":
        if args.json:
            print(dumps_ascii(_prince2_role_queue_report(config), indent=2))
        else:
            print(_render_prince2_role_queues(config))
        return 0
    if task == "roles messages" or task.startswith("roles messages "):
        node_id = task.split(maxsplit=2)[2] if len(task.split(maxsplit=2)) == 3 else None
        if args.json:
            print(dumps_ascii(_prince2_role_messages_report(config, node_id=node_id), indent=2))
        else:
            print(_render_prince2_role_messages(config, node_id=node_id))
        return 0
    if task == "roles runtime":
        if args.json:
            print(dumps_ascii(_prince2_role_runtime_report(config), indent=2))
        else:
            print(_render_prince2_role_runtime(config))
        return 0
    if task == "roles tick" or task.startswith("roles tick "):
        max_nodes = None
        if task != "roles tick":
            try:
                max_nodes = int(task.split(maxsplit=2)[2])
            except (ValueError, IndexError):
                error_payload = {"command": "roles tick", "ok": False, "error": "Usage: roles tick [max_nodes]"}
                if args.json:
                    print(dumps_ascii(error_payload, indent=2))
                else:
                    print(error_payload["error"])
                return 1
        result = _tick_prince2_role_runtime(config, max_nodes=max_nodes)
        if args.json:
            print(
                dumps_ascii(
                    {
                        "command": "roles tick",
                        "ok": True,
                        "result": result,
                        "runtime": _prince2_role_runtime_report(config),
                        "messages": _prince2_role_messages_report(config),
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"Batch advanced PRINCE2 runtime: processed={result.get('processed')} "
                f"woken={result.get('woken')} progressed={result.get('progressed')} skipped={result.get('skipped')}.\n"
                + _render_prince2_role_runtime(config)
            )
        return 0
    if task == "roles check":
        if args.json:
            print(dumps_ascii(_prince2_role_check_report(config), indent=2))
        else:
            print(_render_prince2_role_check(config))
        return 0
    if task == "roles flow":
        if args.json:
            print(dumps_ascii(_prince2_role_flow_report(), indent=2))
        else:
            print(_render_prince2_role_flow())
        return 0
    if task == "roles matrix":
        if args.json:
            print(dumps_ascii(_prince2_role_matrix_report(config), indent=2))
        else:
            print(_render_prince2_role_matrix(config))
        return 0
    if task.startswith("project brief "):
        response = _handle_project_brief_command(task, config)
        if response is None:
            print("Usage: project brief | project brief set <field> <value> | project brief clear [field]")
            return 1
        if args.json:
            print(dumps_ascii({"command": task, "message": response, "project_brief": _project_brief_report(config)}, indent=2))
        else:
            print(response)
        return 0
    if task.startswith("roles ") or task.startswith("role ") or task in {"project start", "project start --ai"}:
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_role_command(task, agent, config)
        if response is None:
            print("Usage: project brief | project brief set <field> <value> | project brief clear [field] | roles | roles domains | roles context <node_id> | roles tree | roles tree approve | roles baseline | roles baseline matrix | roles runtime | roles active | roles control | roles queues | roles messages [node_id] | roles tick [max_nodes] | roles check | roles flow | roles matrix | roles propose | roles setup | role configure [role] | role clear <role> | role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> | role wait <node_id> reason=<text_with_underscores> | role wake <node_id> trigger=<name> | role tick <node_id> | project start [--ai]")
            return 1
        if args.json:
            if task.startswith("role message "):
                parts = task.split()
                node_id = parts[3] if len(parts) >= 4 else None
                print(
                    dumps_ascii(
                        {
                            "command": task,
                            "message": response,
                            "messages": _prince2_role_messages_report(config, node_id=node_id),
                        },
                        indent=2,
                    )
                )
            elif task.startswith("role wait ") or task.startswith("role wake ") or task.startswith("role tick "):
                parts = task.split()
                node_id = parts[2] if len(parts) >= 3 else None
                print(
                    dumps_ascii(
                        {
                            "command": task,
                            "message": response,
                            "runtime": _prince2_role_runtime_report(config),
                            "messages": _prince2_role_messages_report(config, node_id=node_id),
                        },
                        indent=2,
                    )
                )
            elif task.startswith("roles tick"):
                print(
                    dumps_ascii(
                        {
                            "command": task,
                            "result": _tick_prince2_role_runtime(
                                config,
                                max_nodes=int(task.split(maxsplit=2)[2]) if len(task.split(maxsplit=2)) == 3 else None,
                            ),
                            "runtime": _prince2_role_runtime_report(config),
                            "messages": _prince2_role_messages_report(config),
                        },
                        indent=2,
                    )
                )
            else:
                print(dumps_ascii({"command": task, "message": response, "roles": _prince2_roles_report(config)}, indent=2))
        else:
            print(response)
        return 1 if task.startswith("project start") and not _project_start_ready(config) else 0
    if task in {"sources", "sources status"} or task.startswith("sources "):
        if args.json:
            if task == "sources update":
                report = _sources_update_report(config)
                print(dumps_ascii(report, indent=2))
                return 0 if report.get("ok") else 1
            if task in {"sources", "sources status", "sources status --strict"}:
                strict = task == "sources status --strict"
                report = _sources_status_report(config, strict=strict)
                print(dumps_ascii(report, indent=2))
                return 0 if not strict or report.get("ok") else 1
            print(dumps_ascii({"command": task, "ok": False, "error": "Usage: sources | sources status [--strict] | sources update"}, indent=2))
            return 1
        response = _handle_sources_command(task, config)
        if response is None or response.startswith("Usage:"):
            print(response or "Usage: sources | sources status [--strict] | sources update")
            return 1
        print(response)
        return 0 if task != "sources status --strict" or _sources_status_report(config, strict=True).get("ok") else 1
    if task in {"update status", "update check", "update check --json", "update apply", "update apply --yes"} or task.startswith("update "):
        if args.json or task == "update check --json":
            if task in {"update status"}:
                report = _update_status_report(config)
            elif task in {"update check", "update check --json"}:
                report = _update_status_report(config, fetch=True)
            elif task in {"update apply", "update apply --yes"}:
                report = _update_apply_report(config, confirmed=task.endswith(" --yes"))
            else:
                report = {"command": task, "ok": False, "error": "Usage: update status | update check [--json] | update apply --yes"}
            print(dumps_ascii(report, indent=2))
            return 0 if report.get("ok") else 1
        response = _handle_update_command(task, config)
        if response is None or response.startswith("Usage:"):
            print(response or "Usage: update status | update check [--json] | update apply --yes")
            return 1
        print(response)
        return 0 if "\n- ok: false" not in response else 1
    if task == "extensions" or task.startswith("extension ") or task.startswith("extensions "):
        if args.json:
            if task == "extensions":
                report = discover_extensions(config.workspace_root)
            elif task.startswith("extension scaffold "):
                try:
                    report = scaffold_extension(config.workspace_root, task.split(maxsplit=2)[2])
                    _record_handoff_action(
                        config,
                        phase="extension_scaffold",
                        task=task,
                        summary=f"Created extension scaffold {report['name']}.",
                        details=report,
                    )
                except ValueError as exc:
                    report = {"command": "extension scaffold", "ok": False, "error": str(exc)}
            else:
                report = {"command": task, "ok": False, "error": "Usage: extensions | extension scaffold <name>"}
            print(dumps_ascii(report, indent=2))
            if task == "extensions":
                return 0
            return 0 if report.get("ok") else 1
        response = _handle_extension_command(task, config)
        if response is None or response.startswith("Usage:") or response.startswith("Extension scaffold failed"):
            print(response or "Usage: extensions | extension scaffold <name>")
            return 1
        print(response)
        return 0
    if task.startswith("file "):
        report = _file_command_report(task, config)
        if args.json:
            print(dumps_ascii(report or {"command": task, "ok": False, "error": "Unsupported file command"}, indent=2))
            return 0 if report and report.get("ok") else 1
        response = _handle_file_command(task, config)
        print(response or "Usage: file inspect <path> | file stat <path> | file copy <source> <destination> [--overwrite] [--dry-run] | file move <source> <destination> [--overwrite] [--dry-run] | file delete <path> [--recursive] [--dry-run] | file chmod <path> <mode> [--recursive] [--dry-run] | file chown <path> <user> [group] [--recursive] [--dry-run]")
        return 0 if report and report.get("ok") else 1
    if (
        task.startswith("web search ")
        or task.startswith("download ")
        or task.startswith("checksum ")
        or task.startswith("compress ")
        or task.startswith("archive verify ")
        or task in {"download", "checksum", "compress", "archive", "web"}
    ):
        if args.json:
            report = _external_io_report(task, config)
            print(dumps_ascii(report or {"command": task, "ok": False, "error": "Unsupported external IO command"}, indent=2))
            return 0 if report and report.get("ok") else 1
        response = _handle_external_io_command(task, config)
        print(response or "Usage: web search <query> | download <url> [path] [--max-bytes N] | checksum <path> | compress <path> [target.gz] | archive verify <path.gz>")
        return 0 if response and ": OK " in response else 1
    if task == "permissions":
        if args.json:
            print(dumps_ascii({"command": "permissions", "report": _permissions_report(config)}, indent=2))
        else:
            print(_render_permissions(config))
        return 0
    if task in {"board", "stage review"}:
        if args.json:
            print(dumps_ascii(_board_report(config), indent=2))
        else:
            print(_render_board(config))
        return 0
    if task in {"sessions", "session list"}:
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_shell_sessions_report(agent), indent=2))
        else:
            shell_session_message = _handle_shell_session_command(task, agent)
            print(shell_session_message or "No active shell sessions.")
        return 0
    if task.startswith("git "):
        if args.json:
            report = _git_command_report(task, config)
            print(dumps_ascii(report or {"command": "git", "ok": False, "error": "Unsupported git command"}, indent=2))
        else:
            git_message = _handle_git_command(task, config)
            if git_message is not None:
                print(git_message)
            else:
                print("Usage: git status | git log [limit] | git history <path> [limit] | git show [--stat] [revision]")
        return 0
    if task == "boundary":
        if args.json:
            print(dumps_ascii(_boundary_report(config), indent=2))
        else:
            print(_render_boundary(config))
        return 0
    if task == "risks":
        if args.json:
            print(dumps_ascii(_risks_report(config), indent=2))
        else:
            print(_render_risks(config))
        return 0
    if task == "issues":
        if args.json:
            print(dumps_ascii(_issues_report(config), indent=2))
        else:
            print(_render_issues(config))
        return 0
    if task == "quality":
        if args.json:
            print(dumps_ascii(_quality_report(config), indent=2))
        else:
            print(_render_quality(config))
        return 0
    if task == "exception":
        if args.json:
            print(dumps_ascii(_exception_report(config), indent=2))
        else:
            print(_render_exception(config))
        return 0
    if task == "lessons":
        if args.json:
            print(dumps_ascii(_lessons_report(config), indent=2))
        else:
            print(_render_lessons(config))
        return 0
    if task == "todo":
        if args.json:
            print(dumps_ascii(_todo_report(config), indent=2))
        else:
            print(_render_todo(config))
        return 0
    if task in {"transcript", "trace"}:
        if args.json:
            print(dumps_ascii(_transcript_report(config), indent=2))
        else:
            print(_render_transcript(config))
        return 0
    if task == "handoff":
        if args.json:
            print(dumps_ascii(_handoff_report(config), indent=2))
        else:
            print(_render_handoff(config))
        return 0
    if task == "handoff actions" or task.startswith("handoff actions "):
        parts = task.split()
        limit = _parse_optional_limit(parts)
        if args.json:
            print(dumps_ascii(_handoff_actions_report(config, limit=limit), indent=2))
        else:
            print(_render_handoff_actions(config, limit=limit))
        return 0
    if task in {"handoff export", "handoff md"}:
        if args.json:
            print(dumps_ascii(_export_handoff_markdown_report(config), indent=2))
        else:
            print(_export_handoff_markdown(config))
        return 0
    if task == "resume --show":
        if args.json:
            print(dumps_ascii(_resume_show_report(config), indent=2))
        else:
            print(_render_resume_show(config))
        return 0
    if task == "resume context":
        if args.json:
            print(dumps_ascii(_resume_context_payload(config), indent=2))
        else:
            print(_render_resume_context(config))
        return 0
    if task == "resume --clear":
        if args.json:
            print(dumps_ascii(_archive_and_clear_handoff_report(config), indent=2))
        else:
            print(_archive_and_clear_handoff(config))
        return 0
    if task in {"models usage", "cost"}:
        if args.json:
            print(dumps_ascii(_model_usage_report(config), indent=2))
        else:
            print(_render_model_usage(config))
        return 0

    agent = _configure_agent_for_workspace(config)
    result = agent.run(task)
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
