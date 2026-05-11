from __future__ import annotations

import argparse
import atexit
import copy
import io
from dataclasses import replace
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

try:
    import readline
except ImportError:  # pragma: no cover - platform dependent
    readline = None

from .agent import Agent
from .auth import CodexBrowserLoginFlow, CodexBrowserLogoutFlow, OpenAIDeviceCodeFlow
from .executor import ALLOWED_MODEL_ACTIONS, Executor
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
from .model_catalog import catalog_entry_for_provider_model, catalog_entries_for_provider, catalog_path, load_ai_models_catalog, search_ai_models_catalog, write_ai_models_catalog
from .openrouter_benchmark import run_openrouter_benchmark
from .prince2_benchmark import run_prince2_benchmark
from .json_schema_registry import json_schema
from .permissions import PermissionPolicy, PermissionSettings, VALID_PERMISSION_MODES
from .planner import PlanStep
from .project import (
    PROJECT_BRIEF_FIELDS,
    handle_project_brief_command,
    project_brief_guidance,
    project_brief_missing_fields,
    project_brief_report,
    project_gap_to_brief_field,
    render_project_brief,
)
from .project import model_recommendation as _project_model_recommendation
from .project import design_flow as _project_design_flow
from . import project_handoff_views as _project_handoff_views
from . import account_views as _account_views
from . import command_views as _command_views
from . import report_views as _report_views
from . import mode_views as _mode_views
from . import model_views as _model_views
from .project import role_views as _project_role_views
from .project import role_runtime_views as _project_role_runtime_views
from .project import role_tree_views as _project_role_tree_views
from . import status_views as _status_views
from .project import start_flow as _project_start_flow
from .project import role_command_flow as _project_role_command_flow
from .project import role_flow as _project_role_flow
from . import cli_dispatch as _cli_dispatch
from .project.flow import (
    _assignment_for_role,
    _enrich_tree_with_local_execution_candidates,
    _handle_project_brief_command,
    _project_brief_guidance,
    _project_brief_missing_fields,
    _project_brief_report,
    _project_gap_to_brief_field,
    _project_tree_adaptation_snapshot,
    _project_tree_brief_complexity,
    _project_tree_decomposition_nodes,
    _render_project_brief,
    _role_node_from_template,
    _route_from_local_execution_candidate,
)
from .project import tree as _project_tree
from .project import tree_flow as _project_tree_flow
from .command_dispatch import (
    execute_browser_command as _browser_execute,
    execute_external_io_command as _external_io_execute,
    execute_system_command as _system_execute,
    execute_watch_command as _watch_execute,
)
from . import ui_views as _ui_views
from .tool_reports import (
    browser_report as _browser_report,
    handle_browser_command as _handle_browser_command,
    handle_external_io_command as _handle_external_io_command,
    handle_system_command as _handle_system_command,
    handle_watch_command as _handle_watch_command,
    external_io_report as _external_io_report,
    system_report as _system_report,
    watch_report as _watch_report,
)
from . import project_state_views as _project_state_views
from .provider_registry import (
    SUPPORTED_MODELS as REGISTRY_MODELS,
    provider_capability,
    provider_model_preset,
    provider_model_spec,
    provider_model_specs,
)
from .router import ModelRouter
from .role_tree import (
    ROLE_CONTEXT_RULES,
    STATUS_COLOR_LEGEND,
    build_prince2_role_flow,
    build_prince2_role_matrix,
    build_prince2_role_matrix_payload,
    build_prince2_role_tree,
    build_prince2_role_tree_with_tolerance,
    check_prince2_role_tree,
    check_prince2_role_tree_payload,
    prince2_node_description,
    prince2_role_mnemonic,
    prince2_role_team_name,
    prince2_status_color,
    render_prince2_role_check,
    render_prince2_role_flow,
    render_prince2_role_matrix,
    render_prince2_role_tree,
)
from .prince2 import Prince2AgentPolicy, Prince2ToleranceProfile
from .project_handoff import HandoffEntry, ProjectHandoff
from .roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS
from .runtime_env import detect_runtime_capabilities, select_shell_backend
from .secrets import SecretStore
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8
from .tools.files import FileTool
from .tools.git import GitTool
from .tools.external_io import ExternalIOResult
from .tools.browser import BrowserResult
from .tools.system import SystemResult
from .tools.watch import WatchResult


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
    "roles menu",
    "roles tree menu",
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
    "role menu",
    "role model",
    "role tolerance",
    "role remove",
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
    parser.add_argument("--openrouter-benchmark", action="store_true", help="Run the live OpenRouter benchmark baseline and report accuracy by suite.")
    parser.add_argument("--openrouter-benchmark-output", metavar="OUT_PATH", help="Write the live OpenRouter benchmark report to a JSON file.")
    parser.add_argument("--openrouter-benchmark-history", metavar="HISTORY_PATH", help="Append a JSONL history snapshot and compare the current benchmark against the latest prior run.")
    parser.add_argument("--prince2-benchmark", action="store_true", help="Run the local PRINCE2 benchmark baseline and report accuracy by suite.")
    parser.add_argument("--prince2-benchmark-output", metavar="OUT_PATH", help="Write the local PRINCE2 benchmark report to a JSON file.")
    parser.add_argument("--interactive", action="store_true", help="Start an interactive Stagewarden shell.")
    parser.add_argument("--json", action="store_true", help="Emit JSON for machine-readable commands such as `doctor`.")
    parser.add_argument("--full", action="store_true", help="Show expanded status dashboard sections.")
    return parser


def interactive_help_text(topic: str | None = None) -> str:
    if topic:
        return _interactive_help_topic(topic)
    return _interactive_help_overview()


def _interactive_help_overview() -> str:
    return _ui_views._interactive_help_overview()


def _slash_palette_report(config: AgentConfig, prefix: str = "") -> dict[str, object]:
    return _ui_views._slash_palette_report(config, prefix)


def _slash_match_report(spec: object, query: str) -> dict[str, object]:
    return _ui_views._slash_match_report(spec, query)


def _slash_fuzzy_score(query: str, candidate: str) -> int | None:
    return _ui_views._slash_fuzzy_score(query, candidate)


def _highlight_fuzzy_match(query: str, candidate: str) -> str:
    return _ui_views._highlight_fuzzy_match(query, candidate)


def _wrap_description(text: str, *, width: int = 88, initial_indent: str = "  ", subsequent_indent: str = "  ") -> list[str]:
    return _ui_views._wrap_description(
        text,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
    )


def _render_slash_palette(config: AgentConfig, prefix: str = "") -> str:
    return _ui_views._render_slash_palette(config, prefix)


def _guided_slash_choice(
    config: AgentConfig,
    query: str,
    *,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _ui_views._guided_slash_choice(
        config,
        query,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _render_slash_choice_candidates(config: AgentConfig, query: str = "") -> str:
    return _ui_views._render_slash_choice_candidates(config, query)


def _help_json_report(topic: str | None = None) -> dict[str, object]:
    return _ui_views._help_json_report(topic)


def _with_json_schema(command: str, payload: dict[str, object]) -> dict[str, object]:
    if "schema" in payload:
        return payload
    try:
        result = dict(payload)
    except TypeError:
        return payload
    try:
        result["schema"] = json_schema(command)
    except KeyError:
        return payload
    return result


def _interactive_help_topic(topic: str) -> str:
    return _ui_views._interactive_help_topic(topic)


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
    return _status_views._render_model_status(agent, config)


def _render_model_params(config: AgentConfig, model: str) -> str:
    return _model_views._render_model_params(config, model)


def _apply_model_preset(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    model: str,
    preset: str,
) -> tuple[str, dict[str, str]]:
    return _model_views._apply_model_preset(config, prefs, model=model, preset=preset)


def _catalog_entry_display(entry: dict[str, object] | None, spec: object | None = None) -> dict[str, object]:
    if isinstance(entry, dict) and entry:
        return {
            "model_name": entry.get("model_name"),
            "context_window": entry.get("context_window"),
            "cost_per_input_token_usd": entry.get("cost_per_input_token_usd"),
            "cost_per_output_token_usd": entry.get("cost_per_output_token_usd"),
            "blended_price_usd_per_1m_tokens": entry.get("blended_price_usd_per_1m_tokens"),
            "pricing_source": entry.get("pricing_source"),
            "intelligence_rank": entry.get("intelligence_rank"),
            "speed_rank": entry.get("speed_rank"),
            "latency_rank": entry.get("latency_rank"),
            "openness": entry.get("openness"),
            "features": list(entry.get("features", [])) if isinstance(entry.get("features"), list) else [],
            "catalog_source": entry.get("source"),
        }
    return {
        "model_name": getattr(spec, "label", None) if spec is not None else None,
        "context_window": getattr(spec, "context_window_hint", None) if spec is not None else None,
        "cost_per_input_token_usd": None,
        "cost_per_output_token_usd": None,
        "blended_price_usd_per_1m_tokens": None,
        "pricing_source": None,
        "intelligence_rank": None,
        "speed_rank": None,
        "latency_rank": None,
        "openness": None,
        "features": [],
        "catalog_source": None,
    }


def _catalog_option_suffix(entry: dict[str, object] | None) -> str:
    if not isinstance(entry, dict) or not entry:
        return ""
    parts: list[str] = []
    if entry.get("intelligence_rank") is not None:
        parts.append(f"I#{entry.get('intelligence_rank')}")
    if entry.get("speed_rank") is not None:
        parts.append(f"S#{entry.get('speed_rank')}")
    price = entry.get("blended_price_usd_per_1m_tokens")
    if isinstance(price, (int, float)):
        parts.append(f"${price}/1M")
    return f" [{' | '.join(parts)}]" if parts else ""


def _render_account_lines(prefs: ModelPreferences, model: str) -> list[str]:
    return _account_views._render_account_lines(prefs, model)


def _sync_prince2_roles_to_handoff(config: AgentConfig, prefs: ModelPreferences) -> None:
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    if prefs.prince2_role_tree_baseline:
        handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline))
    handoff.save(config.handoff_path)


def _sync_prince2_role_tree_baseline_back_to_preferences(
    config: AgentConfig,
    prefs: ModelPreferences,
    handoff: ProjectHandoff,
) -> None:
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    if not baseline:
        return
    prefs.set_prince2_role_tree_baseline(dict(baseline))
    prefs.save(config.model_prefs_path)


def _prince2_roles_report(config: AgentConfig) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    return {
        "command": "roles",
        "roles": [
            {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "mnemonic": prince2_role_mnemonic(role),
                "team_name": prince2_role_team_name(role),
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
            lines.append(f"- {item['label']} ({item['role']}): unassigned team={prince2_role_team_name(item['role'])} mnemonic={prince2_role_mnemonic(item['role'])}")
            continue
        params = assignment.get("params", {})
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if isinstance(params, dict) and params
            else ""
        )
        lines.append(
            f"- {item['label']} ({item['role']}): mnemonic={prince2_role_mnemonic(item['role'])} "
            f"team={prince2_role_team_name(item['role'])} mode={assignment.get('mode', 'manual')} "
            f"provider={assignment.get('provider', 'unknown')} "
            f"provider_model={assignment.get('provider_model', 'unknown')} "
            f"account={assignment.get('account') or 'none'}"
            f"{params_text} source={assignment.get('source', 'manual')}"
        )
    return "\n".join(lines)


def _render_prince2_role_domains() -> str:
    return _project_role_tree_views._render_prince2_role_domains()


def _prince2_role_domains_report() -> dict[str, object]:
    return _project_role_tree_views._prince2_role_domains_report()


def _prince2_role_tree_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_tree_views._prince2_role_tree_report(config)


def _render_prince2_role_tree(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_tree(config)


def _prince2_role_check_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_tree_views._prince2_role_check_report(config)


def _render_prince2_role_check(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_check(config)


def _prince2_role_flow_report() -> dict[str, object]:
    return _project_role_tree_views._prince2_role_flow_report()


def _render_prince2_role_flow() -> str:
    return _project_role_tree_views._render_prince2_role_flow()


def _prince2_role_matrix_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_tree_views._prince2_role_matrix_report(config)


def _render_prince2_role_matrix(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_matrix(config)


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


def _parse_project_tolerance_margin_percent(value: object, default: float = 25.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        parsed = float(text)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return min(100.0, parsed)


def _project_accountable_owner(handoff: ProjectHandoff) -> str:
    value = handoff.project_brief.get("accountable_project_executive", "user")
    owner = str(value).strip() if value is not None else "user"
    return owner or "user"


def _project_tolerance_margin_percent(handoff: ProjectHandoff, default: float = 25.0) -> float:
    return _parse_project_tolerance_margin_percent(handoff.project_brief.get("tolerance_margin_percent"), default=default)


def _project_tolerance_profile(handoff: ProjectHandoff, *, task: str | None = None) -> Prince2ToleranceProfile:
    policy = Prince2AgentPolicy()
    effective_task = task or handoff.task or str(handoff.project_brief.get("objective", "")).strip() or "PRINCE2 role tree"
    margin = _project_tolerance_margin_percent(handoff)
    owner = _project_accountable_owner(handoff)
    checklist = policy.build_checklist(
        effective_task,
        project_brief=handoff.project_brief,
        base_margin_percent=margin,
        accountable_owner=owner,
    )
    return policy.build_tolerance_profile(
        effective_task,
        checklist,
        project_brief=handoff.project_brief,
        base_margin_percent=margin,
        accountable_owner=owner,
    )


def _build_prince2_role_tree_baseline(config: AgentConfig, *, source: str) -> dict[str, object]:
    prefs = _load_model_preferences(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_tolerance_profile(handoff)
    local_execution = _local_execution_candidates_report(config)
    tree = _enrich_tree_with_local_execution_candidates(
        build_prince2_role_tree_with_tolerance(
            prefs,
            tolerance_profile=tolerance_profile,
            accountable_owner=tolerance_profile.accountable_owner,
        ),
        local_execution,
    )
    brief = {str(key): str(value) for key, value in handoff.project_brief.items()}
    joined = " ".join(brief.values()).lower()
    _decomposition_nodes, decomposition = _project_tree_decomposition_nodes(
        proposal_prefs=prefs,
        active_models=list(prefs.active_models() or prefs.enabled_models),
        brief=brief,
        joined=joined,
        tolerance_profile=tolerance_profile,
    )
    adaptation = _project_tree_adaptation_snapshot(brief=brief, handoff=handoff, local_execution=local_execution)
    tree["decomposition_policy"] = "Decompose the project into the smallest independently verifiable work packages and keep widening only when evidence justifies it."
    tree["adaptation_policy"] = "Refresh the tree continuously from the latest brief, tolerance profile, runtime observation, and response-quality signals."
    tree["decomposition"] = decomposition
    tree["adaptation"] = adaptation
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
        "decomposition": decomposition,
        "adaptation": adaptation,
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
    return _project_role_tree_views._prince2_role_tree_baseline_report(config)


def _render_prince2_role_tree_baseline(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_tree_baseline(config)


def _delivery_local_fallback_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_tree_views._delivery_local_fallback_report(config)


def _prince2_role_tree_baseline_matrix_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_tree_views._prince2_role_tree_baseline_matrix_report(config)


def _prince2_role_runtime_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_runtime_views._prince2_role_runtime_report(config)


def _render_prince2_role_runtime(config: AgentConfig) -> str:
    return _project_role_runtime_views._render_prince2_role_runtime(config)


def _prince2_role_active_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_runtime_views._prince2_role_active_report(config)


def _render_prince2_role_active(config: AgentConfig) -> str:
    return _project_role_runtime_views._render_prince2_role_active(config)


def _prince2_role_queue_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_runtime_views._prince2_role_queue_report(config)


def _render_prince2_role_queues(config: AgentConfig) -> str:
    return _project_role_runtime_views._render_prince2_role_queues(config)


def _prince2_role_control_report(config: AgentConfig) -> dict[str, object]:
    return _project_role_runtime_views._prince2_role_control_report(config)


def _render_prince2_role_control(config: AgentConfig) -> str:
    return _project_role_runtime_views._render_prince2_role_control(config)


def _prince2_role_messages_report(config: AgentConfig, node_id: str | None = None) -> dict[str, object]:
    return _project_role_runtime_views._prince2_role_messages_report(config, node_id=node_id)


def _render_prince2_role_messages(config: AgentConfig, node_id: str | None = None) -> str:
    return _project_role_runtime_views._render_prince2_role_messages(config, node_id=node_id)


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
    return _project_role_views._prince2_role_context_report(config, node_id)


def _render_prince2_role_context(config: AgentConfig, node_id: str) -> str:
    return _project_role_views._render_prince2_role_context(config, node_id)


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
    _sync_prince2_role_tree_baseline_back_to_preferences(config, prefs, handoff)
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
    _sync_prince2_role_tree_baseline_back_to_preferences(config, prefs, handoff)
    _record_handoff_action(
        config,
        phase="roles_tick",
        task=f"roles tick {max_nodes if max_nodes is not None else ''}".strip(),
        summary=f"Batch advanced PRINCE2 runtime across {result.get('processed', 0)} node(s).",
        details=dict(result),
    )
    return result


def _render_prince2_role_tree_baseline_matrix(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_tree_baseline_matrix(config)


def _render_prince2_role_status_hint(config: AgentConfig) -> str:
    return _project_role_tree_views._render_prince2_role_status_hint(config)


def _project_design_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _project_design_flow._project_design_report(agent, config)


def _render_project_design(agent: Agent, config: AgentConfig) -> str:
    return _project_design_flow._render_project_design(agent, config)


def _project_tree_ai_needed(design: dict[str, object], proposal: dict[str, object]) -> bool:
    return _project_start_flow._project_tree_ai_needed(design, proposal)


def _project_start_clarification_record(
    config: AgentConfig,
    *,
    design_gaps: list[dict[str, str]],
    proposal_gaps: list[dict[str, str]],
) -> dict[str, object] | None:
    return _project_start_flow._project_start_clarification_record(
        config,
        design_gaps=design_gaps,
        proposal_gaps=proposal_gaps,
    )


def _project_tree_clarification_record(
    config: AgentConfig,
    *,
    gaps: list[dict[str, str]],
) -> dict[str, object] | None:
    return _project_start_flow._project_tree_clarification_record(config, gaps=gaps)


def _project_start_report(agent: Agent, config: AgentConfig, prefs: ModelPreferences, *, force_ai: bool = False) -> dict[str, object]:
    return _project_start_flow._project_start_report(agent, config, prefs, force_ai=force_ai)


def _render_project_start_report(report: dict[str, object], agent: Agent, config: AgentConfig, prefs: ModelPreferences) -> str:
    return _project_start_flow._render_project_start_report(report, agent, config, prefs)


def _render_project_start(agent: Agent, config: AgentConfig, prefs: ModelPreferences, *, force_ai: bool = False) -> str:
    return _project_start_flow._render_project_start(agent, config, prefs, force_ai=force_ai)


def _project_start_ready(config: AgentConfig) -> bool:
    return _project_start_flow._project_start_ready(config)


def _role_options() -> list[tuple[str, str]]:
    return _project_role_flow._role_options()


def _role_tree_node_options(config: AgentConfig) -> list[tuple[str, str]]:
    return _project_role_flow._role_tree_node_options(config)


def _role_tree_node_record(config: AgentConfig, node_id: str) -> dict[str, object] | None:
    return _project_role_flow._role_tree_node_record(config, node_id)


def _role_tree_nodes_by_parent(config: AgentConfig, parent_id: str | None) -> list[dict[str, object]]:
    return _project_role_flow._role_tree_nodes_by_parent(config, parent_id)


def _role_tree_node_children(config: AgentConfig, node_id: str) -> list[dict[str, object]]:
    return _project_role_flow._role_tree_node_children(config, node_id)


def _with_prince2_role_tree_baseline_mutation(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    source: str,
    mutator: Callable[[dict[str, object], dict[str, object], list[dict[str, object]]], None],
) -> dict[str, object]:
    return _project_role_flow._with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)


def _guided_role_node_assignment_context(config: AgentConfig, node_id: str, pool: str) -> str:
    return _project_role_flow._guided_role_node_assignment_context(config, node_id, pool)


def _role_tree_node_navigation(config: AgentConfig, node_id: str) -> dict[str, object]:
    return _project_role_flow._role_tree_node_navigation(config, node_id)


def _render_prince2_role_node_detail(config: AgentConfig, node_id: str) -> str:
    return _project_role_flow._render_prince2_role_node_detail(config, node_id)


def _render_prince2_role_node_shell(config: AgentConfig, node_id: str) -> str:
    return _project_role_flow._render_prince2_role_node_shell(config, node_id)


def _node_model_choice_options(config: AgentConfig, node_id: str) -> list[tuple[str, str]]:
    return _project_role_flow._node_model_choice_options(config, node_id)


def _guided_provider_options_for_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    return _project_role_flow._guided_provider_options_for_node(config, prefs, node_id=node_id, pool=pool)


def _guided_provider_model_options_for_node(
    config: AgentConfig,
    *,
    provider: str,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    return _project_role_flow._guided_provider_model_options_for_node(config, provider=provider, node_id=node_id, pool=pool)


def _guided_provider_context(prefs: ModelPreferences, provider: str | None = None) -> str:
    return _project_role_flow._guided_provider_context(prefs, provider)


def _route_pool_options() -> list[tuple[str, str]]:
    return _project_role_flow._route_pool_options()


def _guided_role_context(role: str) -> str:
    return _project_role_flow._guided_role_context(role)


def _guided_role_configure(
    *,
    requested_role: str | None,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_configure(
        requested_role=requested_role,
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_add_child(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_add_child(
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_assign(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_assign(
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _set_prince2_role_node_tolerance_margin(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    margin_percent: float,
    source: str = "role_tolerance_set",
) -> dict[str, object]:
    clean_margin = max(0.0, min(100.0, float(margin_percent)))

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            if str(node.get("node_id", "")).strip() != node_id:
                continue
            node["tolerance_margin_percent"] = round(clean_margin, 2)
            tolerance_profile = dict(node.get("tolerance_profile", {})) if isinstance(node.get("tolerance_profile", {}), dict) else {}
            tolerance_profile["margin_percent"] = round(clean_margin, 2)
            tolerance_profile["manual_override"] = True
            node["tolerance_profile"] = tolerance_profile
            node["autonomy_rule"] = str(node.get("autonomy_rule", "")).strip() or "work autonomously within the margin; escalate when pressure exceeds margin."
            break

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return _role_tree_node_record(config, node_id) or {}


def _reset_prince2_role_node_tolerance(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    source: str = "role_tolerance_reset",
) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_tolerance_profile(handoff)

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            if str(node.get("node_id", "")).strip() != node_id:
                continue
            role_type = str(node.get("role_type", "")).strip()
            profile = tolerance_profile.node_profile(role_type)
            node["accountable_owner"] = profile.get("accountable_owner", tolerance_profile.accountable_owner)
            node["tolerance_margin_percent"] = profile.get("margin_percent", tolerance_profile.project_margin_percent)
            node["tolerance_pressure_percent"] = profile.get("pressure_percent", tolerance_profile.project_pressure_percent)
            node["autonomy_rule"] = profile.get("autonomy_rule", node.get("autonomy_rule", ""))
            node["escalation_target"] = profile.get("escalation_target", node.get("escalation_target", "board.executive"))
            node["tolerance_profile"] = profile
            break

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return _role_tree_node_record(config, node_id) or {}


def _remove_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    reparent_children: bool = True,
    source: str = "role_remove",
) -> dict[str, object]:
    removed: dict[str, object] = {}

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        nonlocal removed
        target = next((node for node in nodes if str(node.get("node_id", "")).strip() == node_id), None)
        if target is None:
            raise ValueError(f"Role node '{node_id}' not found.")
        if node_id == "board.executive":
            raise ValueError("The Project Executive root node cannot be removed.")
        removed = dict(target)
        parent_id = str(target.get("parent_id")) if target.get("parent_id") not in {None, ""} else None
        if reparent_children:
            for child in nodes:
                if str(child.get("parent_id", "")).strip() == node_id:
                    child["parent_id"] = parent_id
        nodes[:] = [node for node in nodes if str(node.get("node_id", "")).strip() != node_id]
        flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
        edges = flow.get("edges", []) if isinstance(flow, dict) else []
        if isinstance(edges, list):
            flow["edges"] = [
                edge
                for edge in edges
                if isinstance(edge, dict)
                and str(edge.get("source_node", "")).strip() != node_id
                and str(edge.get("target_node", "")).strip() != node_id
            ]
            baseline["flow"] = flow

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return removed


def _assign_prince2_role_node_model(
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
    return _assign_prince2_role_node(
        config,
        prefs,
        node_id=node_id,
        provider=provider,
        provider_model=provider_model,
        params=params,
        account=account,
        pool=pool,
    )


def _guided_role_node_model_choice(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_node_model_choice(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_node_switch_agent(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_node_switch_agent(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_node_menu(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_node_menu(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_shell(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_shell(
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_node_shell(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_node_shell(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_tree_menu(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_role_tree_menu(
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_roles_setup(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _project_role_flow._guided_roles_setup(
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _handle_role_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    roles_result = _project_role_command_flow._handle_project_and_roles_command(
        command,
        agent,
        config,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if roles_result is not None:
        return roles_result
    parts = command.split()
    if not parts:
        return None
    role_result = _project_role_command_flow._handle_role_command(
        command,
        agent,
        config,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if role_result is not None:
        return role_result
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
        "updated_count": sum(1 for item in items if item.get("updated")),
        "failed_count": sum(1 for item in items if not item.get("ok")),
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


def _model_limits_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._model_limits_report(agent, config)


def _render_model_limits(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_model_limits(agent, config)


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
        "session_state": handoff.status or "none",
        "session_recoverable": handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
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
        "resume_ready": bool(handoff.task) and handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
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
    return _account_views._render_accounts(config)


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
        "schema": json_schema("accounts"),
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
        _render_resume_context(config),
        _project_state_views.render_goal_report(config),
        _project_state_views.render_budget_report(config),
        _project_state_views.render_question_report(config),
        _render_permissions(config),
        "PRINCE2 roles:",
        _render_prince2_role_status_hint(config),
        _render_prince2_roles(config),
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


BASELINE_CAPABILITY_GROUPS: tuple[dict[str, object], ...] = (
    {
        "id": "interactive_shell",
        "source": "codex_cli+claude_code",
        "required_commands": ("help", "slash", "slash choose", "status", "statusline", "preflight", "doctor"),
        "description": "Interactive shell, slash discovery, compact status, and readiness checks.",
    },
    {
        "id": "model_provider_control",
        "source": "codex_cli+claude_code",
        "required_commands": ("models", "model list", "model choose", "model params", "model limits", "model use"),
        "description": "Provider/model selection, parameter visibility, usage limits, and routing control.",
    },
    {
        "id": "account_auth",
        "source": "codex_cli+claude_code",
        "required_commands": ("accounts", "auth status", "account login", "account use", "account logout"),
        "description": "Provider account profiles, browser login where supported, status, selection, and logout.",
    },
    {
        "id": "workspace_tools",
        "source": "codex_cli+claude_code",
        "required_commands": ("shell backend", "sessions", "file inspect", "file stat", "file copy", "file move", "file delete", "git status", "git log", "git history"),
        "description": "Cross-platform shell execution, persistent sessions, file operations, and git history.",
    },
    {
        "id": "permission_safety",
        "source": "codex_cli+claude_code",
        "required_commands": ("permissions", "permission mode", "permission allow", "permission ask", "permission deny"),
        "description": "Explicit permission modes and allow/ask/deny governance.",
    },
    {
        "id": "handoff_resume_trace",
        "source": "codex_cli+claude_code",
        "required_commands": ("handoff", "handoff actions", "resume", "transcript", "report", "board"),
        "description": "Resume context, transcript visibility, action history, and board/report surfaces.",
    },
    {
        "id": "agent_governance",
        "source": "stagewarden_prince2+codex_goals",
        "required_commands": ("goal", "goal set", "goal status", "roles runtime", "roles control", "roles messages", "role message", "roles tick"),
        "description": "Persisted goal, PRINCE2 runtime nodes, governed node messaging, and orchestration.",
    },
    {
        "id": "external_sources_extensions",
        "source": "codex_cli+claude_code+caveman",
        "required_commands": ("sources", "sources update", "web search", "download", "extensions", "extension scaffold", "caveman help"),
        "description": "Source-study refresh, governed external IO, extension discovery, and Caveman mode.",
    },
)


BASELINE_REMEDIATION_BY_GROUP: dict[str, str] = {
    "interactive_shell": "Run `/help`, `/slash`, `/status`, and `/preflight`; restore missing command catalog entries before changing shell UX.",
    "model_provider_control": "Run `/models`, `/model list`, `/model choose`, and `/model limits`; restore provider routing surfaces before model work.",
    "account_auth": "Run `/accounts` and `/auth status <provider>`; restore account login/use/logout surfaces before auth changes.",
    "workspace_tools": "Run `/shell backend`, `/file stat <path>`, and `/git status`; restore file, shell, and git tools before delivery work.",
    "permission_safety": "Run `/permissions`; restore permission mode and allow/ask/deny controls before executing risky tools.",
    "handoff_resume_trace": "Run `/handoff`, `/handoff actions`, `/resume --show`, and `/transcript`; restore traceability before autonomous work.",
    "agent_governance": "Run `/goal`, `/roles runtime`, and `/roles control`; restore PRINCE2 goal/runtime governance before role-routed work.",
    "external_sources_extensions": "Run `/sources status --strict`, `/extensions`, and `/caveman help`; restore source and extension surfaces before source-derived changes.",
}


def _agent_baseline_report(config: AgentConfig) -> dict[str, object]:
    catalog = command_catalog()
    available: set[str] = set()
    for item in catalog:
        for value in (item.get("name"), item.get("usage"), *(item.get("aliases", []) if isinstance(item.get("aliases"), list) else [])):
            if value:
                available.add(str(value).split("[", 1)[0].split("<", 1)[0].strip())
                available.add(str(value).strip())
    groups: list[dict[str, object]] = []
    missing_total: list[str] = []
    for group in BASELINE_CAPABILITY_GROUPS:
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
                "remediation": "none" if not missing else BASELINE_REMEDIATION_BY_GROUP.get(str(group["id"]), "Restore missing command surfaces."),
            }
        )
    runtime = detect_runtime_capabilities(config.workspace_root)
    shell = _shell_backend_report(config)
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


def _model_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._model_status_report(agent, config)


def _selected_model_report(model_report: dict[str, object]) -> dict[str, object] | None:
    return _status_views._selected_model_report(model_report)


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    _apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    provider_limits = _provider_limit_status_report(agent, config)
    permissions = _permissions_report(config)
    stage_view = handoff.stage_view()
    local_fallback = _delivery_local_fallback_report(config)
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
        "runtime": detect_runtime_capabilities(config.workspace_root),
        "shell_backend": _shell_backend_report(config),
        "focus": _focus_snapshot(agent, config),
        "roles": _prince2_roles_report(config),
        "permissions": permissions,
        "pricing": pricing,
        "handoff": {
            "summary": handoff.summary(),
            "operational_posture": handoff.rendered_operational_posture(),
            "stage_view": stage_view,
        },
        "local_fallback": local_fallback,
        "remediations": _status_remediation_report(provider_limits=provider_limits, stage_view=stage_view, config=config),
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


def _render_handoff(config: AgentConfig) -> str:
    return _project_handoff_views._render_handoff(config)


def _handoff_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._handoff_report(config)


def _focus_snapshot(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._focus_snapshot(agent, config)


def _handoff_actions_report(config: AgentConfig, *, limit: int = 20) -> dict[str, object]:
    return _project_handoff_views._handoff_actions_report(config, limit=limit)


def _render_handoff_actions(config: AgentConfig, *, limit: int = 20) -> str:
    return _project_handoff_views._render_handoff_actions(config, limit=limit)


def _parse_optional_limit(parts: list[str], *, default: int = 20) -> int:
    return _project_handoff_views._parse_optional_limit(parts, default=default)


def _render_resume_show(config: AgentConfig) -> str:
    return _project_handoff_views._render_resume_show(config)


def _resume_context_payload(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._resume_context_payload(config)


def _render_resume_context(config: AgentConfig) -> str:
    return _project_handoff_views._render_resume_context(config)


def _resume_show_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._resume_show_report(config)


def _archive_and_clear_handoff(config: AgentConfig) -> str:
    return _project_handoff_views._archive_and_clear_handoff(config)


def _archive_and_clear_handoff_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._archive_and_clear_handoff_report(config)


def _load_handoff_into_agent(agent: Agent, config: AgentConfig) -> ProjectHandoff:
    return _project_handoff_views._load_handoff_into_agent(agent, config)


def _handle_resume_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    return _project_handoff_views._handle_resume_command(command, agent, config)


def _export_handoff_markdown(config: AgentConfig) -> str:
    return _project_handoff_views._export_handoff_markdown(config)


def _export_handoff_markdown_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._export_handoff_markdown_report(config)


def _render_boundary(config: AgentConfig) -> str:
    return _report_views._render_boundary(config)


def _boundary_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._boundary_report(config)


def _board_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._board_report(config)


def _render_board(config: AgentConfig) -> str:
    return _report_views._render_board(config)


def _render_permissions(config: AgentConfig) -> str:
    return _report_views._render_permissions(config)


def _render_risks(config: AgentConfig) -> str:
    return _report_views._render_risks(config)


def _risks_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._risks_report(config)


def _render_risks_close(config: AgentConfig, resolution: str) -> str:
    return _report_views._render_risks_close(config, resolution)


def _risks_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    return _report_views._risks_close_report(config, resolution)


def _render_issues(config: AgentConfig) -> str:
    return _report_views._render_issues(config)


def _issues_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._issues_report(config)


def _render_issues_close(config: AgentConfig, resolution: str) -> str:
    return _report_views._render_issues_close(config, resolution)


def _issues_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    return _report_views._issues_close_report(config, resolution)


def _render_quality(config: AgentConfig) -> str:
    return _report_views._render_quality(config)


def _quality_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._quality_report(config)


def _render_quality_close(config: AgentConfig, resolution: str) -> str:
    return _report_views._render_quality_close(config, resolution)


def _quality_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    return _report_views._quality_close_report(config, resolution)


def _render_exception(config: AgentConfig) -> str:
    return _report_views._render_exception(config)


def _exception_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._exception_report(config)


def _render_lessons(config: AgentConfig) -> str:
    return _report_views._render_lessons(config)


def _lessons_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._lessons_report(config)


def _render_todo(config: AgentConfig) -> str:
    return _report_views._render_todo(config)


def _todo_report(config: AgentConfig) -> dict[str, object]:
    return _report_views._todo_report(config)


def _render_transcript(config: AgentConfig) -> str:
    return _project_handoff_views._render_transcript(config)


def _transcript_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._transcript_report(config)


def _log_error_report(config: AgentConfig, *, limit: int = 20) -> dict[str, object]:
    return _project_handoff_views._log_error_report(config, limit=limit)


def _configure_agent_for_workspace(config: AgentConfig) -> Agent:
    agent = Agent(config)
    _apply_model_preferences(agent, config)
    provider_limits = _provider_limit_status_report(agent, config)
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
    # Allow tests to force OpenRouter auto-selection
    import os
    if os.environ.get("TEST_USE_OPENROUTER_AUTO", "").lower() in {"1", "true", "yes"}:
        # Use the cheap OpenRouter path with automatic model resolution
        return "cheap"
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
            f"- session_state: {view['session_state']}",
            f"- session_recoverable: {str(bool(view['session_recoverable'])).lower()}",
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
    devil_advocate_status = None
    if latest_tool is not None and latest_tool.action_type == "devil_advocate_review":
        review_text = f"{latest_tool.summary}\n{latest_tool.detail}\n{latest.observation}".lower()
        if latest.error_type == "critic_rejection" or "verdict=block" in review_text or '"verdict":"block"' in review_text or '"verdict": "block"' in review_text:
            devil_advocate_status = "rejected"
        elif "verdict=revise" in review_text or '"verdict":"revise"' in review_text or '"verdict": "revise"' in review_text:
            devil_advocate_status = "needs_revision"
        elif "devil_advocate_review" in latest_tool.action_type:
            devil_advocate_status = "approved"
    elif latest.error_type == "critic_rejection":
        devil_advocate_status = "rejected"
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
        (
            f"- devil_advocate: {devil_advocate_status}"
            if devil_advocate_status is not None
            else "- devil_advocate: none"
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
    catalog = load_ai_models_catalog()
    specs = list(provider_model_specs(model))
    provider_model = _prompt_menu_choice(
        title=f"Choose provider-model for {model}:",
        options=[
            (spec.id, f"{spec.id} | {spec.label}{_catalog_option_suffix(catalog_entry_for_provider_model(model, spec.id, catalog))}")
            for spec in specs
        ],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Guided model selection cancelled."
    spec = provider_model_spec(model, provider_model)
    reasoning_value = None
    if spec is not None and spec.reasoning_efforts:
        current_reasoning = prefs.params_for_model(model).get("reasoning_effort") or spec.reasoning_default or spec.reasoning_efforts[0]
        if provider_model == "gpt-5.3-codex":
            reasoning_options = [
                ("medium", "medium"),
                ("high", f"high{' (default)' if current_reasoning == 'high' else ''}"),
                ("high", "high"),
            ]
        else:
            ordered_reasoning_efforts = list(spec.reasoning_efforts)
            if provider_model and "mini" not in provider_model.lower():
                ordered_reasoning_efforts = list(reversed(ordered_reasoning_efforts))
            reasoning_options = [
                (effort, f"{effort}{' (default)' if effort == current_reasoning else ''}")
                for effort in ordered_reasoning_efforts
            ]
        reasoning_value = _prompt_menu_choice(
            title=f"Choose reasoning_effort for {model}:{provider_model}:",
            options=reasoning_options,
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
    return _model_views._handle_model_command(
        command,
        agent,
        config,
        input_stream=input_stream,
        output_stream=output_stream,
    )

def _model_usage() -> str:
    return (
        "Usage: model use <name> | model choose [name] | model add <name> | model list <name> | model inspect <provider> [provider_model] | "
        "model params <name> | model variant <name> <variant> | model variant-clear <name> | "
        "model preset <name> <fast|balanced|deep|plan> | "
        "model param set <name> <key> <value> | model param clear <name> <key> | "
        "model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | "
        "model unblock <name> | model limits | model limit-record <name> <message> | "
        "model limit-clear <name> | model clear | catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"
    )


def _catalog_usage() -> str:
    return "Usage: catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"


def _parse_catalog_refresh_flags(parts: list[str]) -> bool:
    include_artificial_analysis = False
    for token in parts:
        if token == "--aa":
            include_artificial_analysis = True
            continue
        raise ValueError(_catalog_usage())
    return include_artificial_analysis


def _catalog_status_report() -> dict[str, object]:
    catalog = load_ai_models_catalog()
    models = catalog.get("models", []) if isinstance(catalog, dict) else []
    model_count = len(models) if isinstance(models, list) else 0
    return {
        "command": "catalog status",
        "schema": json_schema("catalog status"),
        "ok": bool(catalog),
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at") if isinstance(catalog, dict) else None,
        "model_count": model_count,
        "source_urls": catalog.get("source_urls", {}) if isinstance(catalog, dict) else {},
    }


def _catalog_search_report(
    query: str,
    provider: str | None = None,
    *,
    feature: str | None = None,
    limit: int = 10,
) -> dict[str, object]:
    catalog = load_ai_models_catalog()
    results = search_ai_models_catalog(query, provider=provider, feature=feature, catalog=catalog, limit=limit)
    return {
        "command": "catalog search",
        "schema": json_schema("catalog search"),
        "query": query,
        "provider": provider,
        "feature": feature,
        "path": str(catalog_path()),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog, dict) and isinstance(catalog.get("models", []), list) else 0,
        "results": results,
    }


def _catalog_refresh_report(catalog: dict[str, object]) -> dict[str, object]:
    return {
        "command": "catalog refresh",
        "schema": json_schema("catalog refresh"),
        "ok": True,
        "include_artificial_analysis": bool(catalog.get("include_artificial_analysis", False)),
        "pricing_source": "artificial_analysis" if bool(catalog.get("include_artificial_analysis", False)) else "openrouter",
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at"),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog.get("models", []), list) else 0,
        "source_urls": catalog.get("source_urls", {}),
    }


def _handle_account_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    return _account_views._handle_account_command(
        command,
        agent,
        config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _account_usage() -> str:
    return _account_views._account_usage()


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
    return _account_views._guided_account_choice(
        requested_model=requested_model,
        prefs=prefs,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _handle_mode_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    return _mode_views._handle_mode_command(command, agent, config)


def _handle_permission_command(parts: list[str], config: AgentConfig, agent: Agent | None = None) -> str:
    return _command_views._handle_permission_command(parts, config, agent=agent)


def _handle_shell_command(parts: list[str], config: AgentConfig) -> str | None:
    return _command_views._handle_shell_command(parts, config)


def _handle_git_command(command: str, config: AgentConfig) -> str | None:
    return _command_views._handle_git_command(command, config)


def _git_command_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    return _command_views._git_command_report(command, config)


def _handle_shell_session_command(command: str, agent: Agent) -> str | None:
    return _command_views._handle_shell_session_command(command, agent)


def _handle_patch_command(command: str, agent: Agent) -> str | None:
    return _command_views._handle_patch_command(command, agent)


def _file_command_report(command: str, config: AgentConfig) -> dict[str, object] | None:
    return _command_views._file_command_report(command, config)


def _render_file_command(report: dict[str, object]) -> str:
    return _command_views._render_file_command(report)


def _handle_file_command(command: str, config: AgentConfig) -> str | None:
    return _command_views._handle_file_command(command, config)


def _resolve_shell_session_id(agent: Agent, requested: str) -> str | None:
    return _command_views._resolve_shell_session_id(agent, requested)


def _shell_sessions_report(agent: Agent) -> dict[str, object]:
    return _command_views._shell_sessions_report(agent)


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
        return None, dumps_ascii(_with_json_schema("help", _help_json_report()), indent=2) if lowered.endswith("--json") else interactive_help_text()
    if lowered == "slash choose":
        return None, _render_slash_choice_candidates(agent.config)
    if lowered.startswith("slash choose "):
        query = command.split(maxsplit=2)[2]
        return None, _render_slash_choice_candidates(agent.config, query)
    if lowered == "slash":
        return None, _render_slash_palette(agent.config)
    if lowered == "slash --json":
        return None, dumps_ascii(_with_json_schema("slash", _slash_palette_report(agent.config)), indent=2)
    if lowered.startswith("slash "):
        prefix = command.split(maxsplit=1)[1]
        if prefix.endswith(" --json"):
            prefix = prefix[: -len(" --json")].strip()
            return None, dumps_ascii(_with_json_schema("slash", _slash_palette_report(agent.config, prefix)), indent=2)
        return None, _render_slash_palette(agent.config, prefix)
    if lowered == "commands":
        return None, render_command_catalog()
    if lowered == "commands --json":
        return None, dumps_ascii(_with_json_schema("commands", {"command": "commands", "commands": command_catalog()}), indent=2)
    if lowered.startswith("help "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii(_with_json_schema("help", _help_json_report()), indent=2)
        if topic.lower().strip() == "caveman":
            return None, agent.caveman.help_text()
        if topic.lower().strip() == "topics":
            return None, interactive_help_text()
        if topic.lower().strip().endswith(" --json"):
            raw_topic = topic[: -len(" --json")].strip()
            if raw_topic.lower() == "caveman":
                return None, dumps_ascii(_with_json_schema("help", {"command": "help", "ok": True, "topic": "caveman", "title": "Caveman", "message": "Use `help caveman` for the rich caveman help surface."}), indent=2)
            return None, dumps_ascii(_with_json_schema("help", _help_json_report(raw_topic)), indent=2)
        return None, interactive_help_text(topic)
    if lowered.startswith("commands "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii(_with_json_schema("commands", {"command": "commands", "commands": command_catalog()}), indent=2)
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
        "catalog ",
        "auth status ",
        "model ",
        "account ",
        "goal ",
        "budget ",
        "question ",
        "answer ",
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
    provider_limits = _provider_limit_status_report(agent, config)
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

    def _run_task(task: str) -> None:
        sink.write(f"Running task: {task}\n")
        sink.write(f"{_render_shell_progress(agent, phase='before', command=task)}\n")
        sink.flush()
        result = agent.run(task)
        sink.write("Agent result:\n")
        sink.write(f"{result.message}\n")
        sink.write(f"{_render_last_step_outcome(agent)}\n")
        sink.write(f"{_render_shell_progress(agent, phase='after')}\n")
        sink.flush()

    suspended_task = str(agent.project_handoff.task or "").strip()
    waiting_reason = str(getattr(agent.project_handoff, "waiting_reason", "") or "").strip().lower()
    if agent.project_handoff.status == "waiting" and suspended_task and waiting_reason != "clarification":
        sink.write(f"Auto-resuming suspended task: {suspended_task}\n")
        sink.flush()
        _run_task(suspended_task)
    elif agent.project_handoff.status == "waiting" and waiting_reason == "clarification":
        pending_question = agent.project_handoff.user_question.get("question") if isinstance(agent.project_handoff.user_question, dict) else None
        if pending_question:
            sink.write(f"Pending clarification: {pending_question}\n")
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
            if agent.project_handoff.status == "waiting" and str(getattr(agent.project_handoff, "waiting_reason", "") or "").strip().lower() == "clarification":
                try:
                    agent.project_handoff.answer_user_question(answer=command)
                    agent.project_handoff.save(config.handoff_path)
                except ValueError as exc:
                    sink.write(f"{exc}\n")
                    sink.flush()
                    continue
                sink.write("Recorded answer for pending clarification.\n")
                sink.flush()
                if suspended_task:
                    _run_task(suspended_task)
                continue
            _run_task(command)
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
        model_message = _model_views._handle_model_command(shell_command, agent, config, input_stream=source, output_stream=sink)
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
        external_io_message = _handle_external_io_command(
            shell_command,
            config,
            execute_external_io_command=_external_io_execute,
            record_handoff_action=_record_handoff_action,
        )
        if external_io_message is not None:
            sink.write(f"{external_io_message}\n")
            sink.flush()
            continue
        system_message = _handle_system_command(
            shell_command,
            config,
            execute_system_command=_system_execute,
            record_handoff_action=_record_handoff_action,
        )
        if system_message is not None:
            sink.write(f"{system_message}\n")
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
    return _cli_dispatch.run_cli()

def _project_tree_proposal_report(config: AgentConfig, *, agent: Agent | None = None, use_ai: bool = False) -> dict[str, object]:
    return _project_tree_flow._project_tree_proposal_report(config, agent=agent, use_ai=use_ai)


def _project_tree_ai_prompt(design: dict[str, object], local_report: dict[str, object]) -> str:
    return _project_tree_flow._project_tree_ai_prompt(design, local_report)


def _merge_ai_project_tree_proposal(agent: Agent, config: AgentConfig, local_report: dict[str, object]) -> dict[str, object]:
    return _project_tree_flow._merge_ai_project_tree_proposal(agent, config, local_report)


def _render_project_tree_proposal(config: AgentConfig) -> str:
    return _project_tree_flow._render_project_tree_proposal(config)


def _render_project_tree_proposal_report(report: dict[str, object]) -> str:
    return _project_tree_flow._render_project_tree_proposal_report(report)


def _record_project_tree_proposal_action(config: AgentConfig, report: dict[str, object], *, task: str) -> None:
    return _project_tree_flow._record_project_tree_proposal_action(config, report, task=task)


def _approve_project_tree_proposal(
    config: AgentConfig,
    *,
    force: bool = False,
    proposal_report: dict[str, object] | None = None,
) -> dict[str, object]:
    return _project_tree_flow._approve_project_tree_proposal(config, force=force, proposal_report=proposal_report)


def _render_project_tree_approval_report(report: dict[str, object], config: AgentConfig) -> str:
    return _project_tree_flow._render_project_tree_approval_report(report, config)


def _render_project_tree_approval(config: AgentConfig, *, force: bool = False) -> str:
    return _project_tree_flow._render_project_tree_approval(config, force=force)


def _node_local_fallback_candidates(node: dict[str, object]) -> list[dict[str, object]]:
    return _project_model_recommendation._node_local_fallback_candidates(node)


def _catalog_power_score(entry: dict[str, object] | None) -> float | None:
    return _project_model_recommendation._catalog_power_score(entry)


def _catalog_model_choice_key(provider: str, provider_model: str) -> str:
    return _project_model_recommendation._catalog_model_choice_key(provider, provider_model)


def _parse_catalog_model_choice(choice: str) -> tuple[str, str] | None:
    return _project_model_recommendation._parse_catalog_model_choice(choice)


def _node_model_recommendation(config: AgentConfig, node: dict[str, object]) -> dict[str, object]:
    return _project_model_recommendation._node_model_recommendation(config, node)


def _status_pricing_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._status_pricing_report(agent, config)


def _status_cost_sidebar_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._status_cost_sidebar_report(agent, config)


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._status_report(agent, config)


def _status_dashboard_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._status_dashboard_report(agent, config)


def _statusline_rate_limit(item: dict[str, object]) -> dict[str, object]:
    return _status_views._statusline_rate_limit(item)


def _provider_limit_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._provider_limit_status_report(agent, config)


def _provider_limit_summary_report(provider_limits: dict[str, object]) -> dict[str, object]:
    return _status_views._provider_limit_summary_report(provider_limits)


def _render_provider_limit_status(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_provider_limit_status(agent, config)


def _statusline_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._statusline_report(agent, config)


def _overview_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._overview_report(agent, config)


def _health_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._health_report(agent, config)


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
    return _status_views._preflight_remediations(
        doctor=doctor,
        runtime=runtime,
        shell_backend=shell_backend,
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=role_check,
        provider_limits=provider_limits,
        sources=sources,
        stage_view=stage_view,
        log_errors=log_errors,
    )


def _status_remediation_report(
    *,
    provider_limits: dict[str, object],
    stage_view: dict[str, object],
    config: AgentConfig,
) -> list[dict[str, str]]:
    return _status_views._status_remediation_report(
        provider_limits=provider_limits,
        stage_view=stage_view,
        config=config,
    )


def _preflight_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._preflight_report(agent, config)


def _report_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._report_report(agent, config)


def _doctor_report(config: AgentConfig) -> dict[str, object]:
    return _status_views._doctor_report(config)


def _doctor_ok(rendered: str) -> bool:
    return _status_views._doctor_ok(rendered)


def _render_preflight(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_preflight(agent, config)


def _render_report(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_report(agent, config)


def _render_doctor(config: AgentConfig) -> str:
    return _status_views._render_doctor(config)


def _render_status_full(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_status_full(agent, config)


def _render_model_usage(config: AgentConfig) -> str:
    return _status_views._render_model_usage(config)


def _model_usage_report(config: AgentConfig) -> dict[str, object]:
    return _status_views._model_usage_report(config)


def _render_cost_sidebar(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_cost_sidebar(agent, config)


def _battery_views():
    from . import battery_views as battery_views_module

    return battery_views_module


def _battery_report(config: AgentConfig) -> dict[str, object]:
    return _battery_views()._battery_report(config)


def _render_battery(config: AgentConfig) -> str:
    return _battery_views()._render_battery(config)


if __name__ == "__main__":
    raise SystemExit(main())
