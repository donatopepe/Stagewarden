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
from .handoff import MODEL_BACKENDS, MODEL_VARIANT_CATALOG, available_model_variants, format_run_model
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
from . import json_schema_registry as _json_schema_registry
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
from . import agent_setup_views as _agent_setup_views
from . import extension_views as _extension_views
from .project import role_views as _project_role_views
from .project import role_runtime_views as _project_role_runtime_views
from .project import role_tree_views as _project_role_tree_views
from . import status_views as _status_views
from .project import start_flow as _project_start_flow
from .project import role_command_flow as _project_role_command_flow
from .project import role_flow as _project_role_flow
from . import cli_dispatch as _cli_dispatch
from . import auth_views as _auth_views
from . import model_inspection_views as _model_inspection_views
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
from . import shell_views as _shell_views
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
    return _cli_dispatch._build_parser()


def interactive_help_text(topic: str | None = None) -> str:
    return _ui_views.interactive_help_text(topic)


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
    return _json_schema_registry.with_json_schema(command, payload)


def _interactive_help_topic(topic: str) -> str:
    return _ui_views._interactive_help_topic(topic)


def _load_model_preferences(config: AgentConfig) -> ModelPreferences:
    return _model_views._load_model_preferences(config)


def _save_model_preferences(config: AgentConfig, prefs: ModelPreferences) -> None:
    _model_views._save_model_preferences(config, prefs)


def _sync_handoff_preferences(agent: Agent, prefs: ModelPreferences) -> None:
    _model_views._sync_handoff_preferences(agent, prefs)


def _apply_model_preferences(agent: Agent, config: AgentConfig) -> ModelPreferences:
    return _model_views._apply_model_preferences(agent, config)


def _provider_model_display(prefs: ModelPreferences, provider: str) -> tuple[str, str, str]:
    return _model_views._provider_model_display(prefs, provider)


def _provider_model_params_display(prefs: ModelPreferences, provider: str) -> dict[str, str]:
    return _model_views._provider_model_params_display(prefs, provider)


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
    return _model_views._catalog_entry_display(entry, spec)


def _catalog_option_suffix(entry: dict[str, object] | None) -> str:
    return _model_views._catalog_option_suffix(entry)


def _render_account_lines(prefs: ModelPreferences, model: str) -> list[str]:
    return _account_views._render_account_lines(prefs, model)


def _sync_prince2_roles_to_handoff(config: AgentConfig, prefs: ModelPreferences) -> None:
    _model_views._sync_prince2_roles_to_handoff(config, prefs)


def _sync_prince2_role_tree_baseline_back_to_preferences(
    config: AgentConfig,
    prefs: ModelPreferences,
    handoff: ProjectHandoff,
) -> None:
    _model_views._sync_prince2_role_tree_baseline_back_to_preferences(config, prefs, handoff)


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
    return _project_role_views._render_prince2_roles(config)


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
    return _project_role_flow._parse_project_tolerance_margin_percent(value, default=default)


def _project_accountable_owner(handoff: ProjectHandoff) -> str:
    return _project_role_flow._project_accountable_owner(handoff)


def _project_tolerance_margin_percent(handoff: ProjectHandoff, default: float = 25.0) -> float:
    return _project_role_flow._project_tolerance_margin_percent(handoff, default=default)


def _project_tolerance_profile(handoff: ProjectHandoff, *, task: str | None = None) -> Prince2ToleranceProfile:
    return _project_role_flow._project_tolerance_profile(handoff, task=task)


def _build_prince2_role_tree_baseline(config: AgentConfig, *, source: str) -> dict[str, object]:
    return _project_role_flow._build_prince2_role_tree_baseline(config, source=source)


def _approve_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    return _project_role_flow._approve_prince2_role_tree_baseline(config, prefs, source=source)


def _refresh_prince2_role_tree_baseline_checks(baseline: dict[str, object], prefs: ModelPreferences) -> dict[str, object]:
    return _project_role_flow._refresh_prince2_role_tree_baseline_checks(baseline, prefs)


def _persist_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, baseline: dict[str, object]) -> None:
    _project_role_flow._persist_prince2_role_tree_baseline(config, prefs, baseline)


def _ensure_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    return _project_role_flow._ensure_prince2_role_tree_baseline(config, prefs, source=source)


def _add_child_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    parent_id: str,
    role_type: str,
    node_id: str | None = None,
) -> dict[str, object]:
    return _project_role_flow._add_child_prince2_role_node(
        config,
        prefs,
        parent_id=parent_id,
        role_type=role_type,
        node_id=node_id,
    )


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
    return _project_role_flow._assign_prince2_role_node(
        config,
        prefs,
        node_id=node_id,
        provider=provider,
        provider_model=provider_model,
        params=params,
        account=account,
        pool=pool,
    )


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
    return _status_views._agent_capability_surface_for_node(config)


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
    return _project_role_flow._send_prince2_role_message(
        config,
        source_node=source_node,
        target_node=target_node,
        edge_id=edge_id,
        payload_scope=payload_scope,
        evidence_refs=evidence_refs,
        summary=summary,
    )


def _set_prince2_role_node_waiting(
    config: AgentConfig,
    *,
    node_id: str,
    reason: str,
    wake_triggers: list[str] | None = None,
) -> dict[str, object]:
    return _project_role_flow._set_prince2_role_node_waiting(
        config,
        node_id=node_id,
        reason=reason,
        wake_triggers=wake_triggers,
    )


def _wake_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
    trigger: str,
) -> dict[str, object]:
    return _project_role_flow._wake_prince2_role_node(config, node_id=node_id, trigger=trigger)


def _tick_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
) -> dict[str, object]:
    return _project_role_flow._tick_prince2_role_node(config, node_id=node_id)


def _tick_prince2_role_runtime(
    config: AgentConfig,
    *,
    max_nodes: int | None = None,
) -> dict[str, object]:
    return _project_role_flow._tick_prince2_role_runtime(config, max_nodes=max_nodes)


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


def _remove_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    reparent_children: bool = True,
    source: str = "role_remove",
) -> dict[str, object]:
    return _project_role_flow._remove_prince2_role_node(
        config,
        prefs,
        node_id=node_id,
        reparent_children=reparent_children,
        source=source,
    )


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
    return _project_role_flow._assign_prince2_role_node(
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
    return _status_views._source_reference_manifest(config)


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
    return _status_views._sources_status_report(config, strict=strict)


def _render_sources_status(config: AgentConfig, *, strict: bool = False) -> str:
    return _status_views._render_sources_status(config, strict=strict)


def _sources_update_report(config: AgentConfig) -> dict[str, object]:
    return _status_views._sources_update_report(config)


def _render_sources_update(config: AgentConfig) -> str:
    return _status_views._render_sources_update(config)


def _handle_sources_command(command: str, config: AgentConfig) -> str | None:
    return _status_views._handle_sources_command(command, config)


def _update_status_report(config: AgentConfig, *, fetch: bool = False) -> dict[str, object]:
    return _status_views._update_status_report(config, fetch=fetch)


def _render_update_status(config: AgentConfig, *, fetch: bool = False) -> str:
    return _status_views._render_update_status(config, fetch=fetch)


def _update_apply_report(config: AgentConfig, *, confirmed: bool = False) -> dict[str, object]:
    return _status_views._update_apply_report(config, confirmed=confirmed)


def _render_update_apply(config: AgentConfig, *, confirmed: bool = False) -> str:
    return _status_views._render_update_apply(config, confirmed=confirmed)


def _handle_update_command(command: str, config: AgentConfig) -> str | None:
    return _status_views._handle_update_command(command, config)


def _render_extensions_report(report: dict[str, object]) -> str:
    return _extension_views._render_extensions_report(report)


def _handle_extension_command(command: str, config: AgentConfig) -> str | None:
    return _extension_views._handle_extension_command(command, config)


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
    return _status_views._record_limit_message(config, prefs, model=model, message=message, account=account)


def _clear_limit_snapshot(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    model: str,
    account: str | None = None,
) -> str:
    return _status_views._clear_limit_snapshot(config, prefs, model=model, account=account)

def _render_focus_snapshot(snapshot: dict[str, object]) -> str:
    return _status_views._render_focus_snapshot(snapshot)


def _provider_limit_summary(agent: Agent, config: AgentConfig) -> str:
    return _status_views._provider_limit_summary(agent, config)


def _render_accounts(config: AgentConfig) -> str:
    return _account_views._render_accounts(config)


def _accounts_report(config: AgentConfig) -> dict[str, object]:
    return _account_views._accounts_report(config)


def _auth_status_report(provider: str) -> dict[str, object]:
    return _auth_views._auth_status_report(provider)


def _render_auth_status(provider: str) -> str:
    return _auth_views._render_auth_status(provider)

def _render_status(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_status(agent, config)


def _render_remediations(remediations: object) -> str:
    return _status_views._render_remediations(remediations)


def _render_runtime_status(config: AgentConfig) -> str:
    return _status_views._render_runtime_status(config)


def _permissions_report(config: AgentConfig) -> dict[str, object]:
    return _status_views._permissions_report(config)


def _workspace_settings_payload(path: Path) -> dict[str, object]:
    return _shell_views._workspace_settings_payload(path)


def _configured_shell_backend(config: AgentConfig) -> str:
    return _shell_views._configured_shell_backend(config)


def _save_shell_backend(config: AgentConfig, backend: str) -> None:
    _shell_views._save_shell_backend(config, backend)


def _shell_backend_report(config: AgentConfig) -> dict[str, object]:
    return _shell_views._shell_backend_report(config)


def _render_shell_backend(config: AgentConfig) -> str:
    return _shell_views._render_shell_backend(config)


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
    return _status_views._agent_baseline_report(config)


def _render_agent_baseline(config: AgentConfig) -> str:
    return _status_views._render_agent_baseline(config)


def _model_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._model_status_report(agent, config)


def _selected_model_report(model_report: dict[str, object]) -> dict[str, object] | None:
    return _status_views._selected_model_report(model_report)


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    return _status_views._status_report(agent, config)


def _render_overview(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_overview(agent, config)


def _render_health(agent: Agent, config: AgentConfig) -> str:
    return _status_views._render_health(agent, config)


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
    return _agent_setup_views._configure_agent_for_workspace(config)


def _configure_readonly_agent_for_workspace(config: AgentConfig) -> Agent:
    return _agent_setup_views._configure_readonly_agent_for_workspace(config)


def _planned_shell_route(agent: Agent, command: str) -> tuple[str, str, str]:
    return _shell_views._planned_shell_route(agent, command)


def _choose_cloud_priority_model(agent: Agent, prefs: ModelPreferences) -> str:
    return _model_views._choose_cloud_priority_model(agent, prefs)


def _render_shell_progress(agent: Agent, *, phase: str, command: str | None = None) -> str:
    return _shell_views._render_shell_progress(agent, phase=phase, command=command)


def _refresh_runtime_permissions(agent: Agent) -> None:
    _agent_setup_views._refresh_runtime_permissions(agent)


def _prompt_menu_choice(
    *,
    title: str,
    options: list[tuple[str, str]],
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str | None:
    return _shell_views._prompt_menu_choice(title=title, options=options, input_stream=input_stream, output_stream=output_stream)


def _local_model_profile_from_spec(spec) -> dict[str, object]:
    return _model_inspection_views._local_model_profile_from_spec(spec)


def _local_model_inspection_prompt(catalog: list[dict[str, object]], selected_model: str | None) -> str:
    return _model_inspection_views._local_model_inspection_prompt(catalog, selected_model)


def _inspect_provider_models(
    agent: Agent,
    config: AgentConfig,
    *,
    provider: str,
    provider_model: str | None = None,
) -> dict[str, object]:
    return _model_inspection_views._inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)


def _render_provider_model_inspection(report: dict[str, object]) -> str:
    return _model_inspection_views._render_provider_model_inspection(report)


def _local_execution_candidates_report(
    config: AgentConfig,
    *,
    agent: Agent | None = None,
    use_ai: bool = False,
) -> dict[str, object]:
    return _project_design_flow._local_execution_candidates_report(config, agent=agent, use_ai=use_ai)


def _guided_model_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    agent: Agent,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    return _model_views._guided_model_choice(
        requested_model=requested_model,
        prefs=prefs,
        agent=agent,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


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
    return _model_views._catalog_usage()


def _parse_catalog_refresh_flags(parts: list[str]) -> bool:
    return _model_views._parse_catalog_refresh_flags(parts)


def _catalog_status_report() -> dict[str, object]:
    return _model_views._catalog_status_report()


def _catalog_search_report(
    query: str,
    provider: str | None = None,
    *,
    feature: str | None = None,
    limit: int = 10,
) -> dict[str, object]:
    return _model_views._catalog_search_report(query, provider, feature=feature, limit=limit)


def _catalog_refresh_report(catalog: dict[str, object]) -> dict[str, object]:
    return _model_views._catalog_refresh_report(catalog)


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
    return _account_views._default_claude_credentials_path()


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


def _rewrite_shell_command(command: str, agent: Agent) -> tuple[str | None, str | None]:
    return _shell_views._rewrite_shell_command(command, agent)


def _interactive_completion_candidates(text: str, config: AgentConfig) -> list[str]:
    return _shell_views._interactive_completion_candidates(text, config)


def _is_known_interactive_command(command: str) -> bool:
    return _shell_views._is_known_interactive_command(command)


def run_interactive_shell(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    return _shell_views._run_interactive_shell_impl(config, input_stream=input_stream, output_stream=output_stream)


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
