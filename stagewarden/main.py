from __future__ import annotations

import argparse
import atexit
from dataclasses import replace
import os
import platform
import re
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
from .config import AgentConfig
from .handoff import MODEL_BACKENDS, MODEL_VARIANT_CATALOG, available_model_variants, canonicalize_model_variant
from .ljson import LJSONOptions, benchmark_sizes, decode, dump_file, encode, load_file
from .memory import MemoryStore
from .modelprefs import (
    ModelPreferences,
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
from .project_handoff import ProjectHandoff
from .secrets import SecretStore
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8
from .tools.git import GitTool


INTERACTIVE_COMMAND_PHRASES: tuple[str, ...] = (
    "help",
    "help core",
    "help models",
    "help accounts",
    "help permissions",
    "help handoff",
    "help git",
    "help caveman",
    "help ljson",
    "exit",
    "quit",
    "reset",
    "overview",
    "health",
    "report",
    "status",
    "status full",
    "statusline",
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
)


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
    return "\n".join(
        [
            "Stagewarden interactive shell",
            "",
            "Core commands:",
            "- help",
            "  Show this full help with examples.",
            "- exit | quit",
            "  Close the interactive session.",
            "- reset",
            "  Start a fresh in-memory agent session in the same workspace.",
            "- status",
            "  Show workspace, mode, model routing, and state file locations.",
            "- handoff",
            "  Show the current persisted PRINCE2 handoff context for this workspace.",
            "- resume context",
            "  Show the latest implicit resume context: model attempt, tool evidence, and git snapshot.",
            "- handoff export | handoff md",
            "  Export the runtime handoff into the generated section of HANDOFF.md.",
            "- boundary",
            "  Show only the current PRINCE2 stage boundary recommendation.",
            "- risks | issues | quality | exception",
            "  Show the dedicated PRINCE2 registers from the persisted handoff.",
            "- lessons",
            "  Show the persistent lessons log derived from execution outcomes.",
            "- transcript | trace",
            "  Show the recent tool invocation transcript from workspace memory.",
            "- todo",
            "  Show the persisted implementation backlog tracked in handoff.",
            "- permissions",
            "  Show the active workspace permission settings.",
            "- permission mode <default|accept_edits|plan|auto|dont_ask>",
            "  Set the default permission mode for this workspace.",
            "- permission session mode <default|accept_edits|plan|auto|dont_ask>",
            "  Set a temporary permission mode for the current shell session only.",
            "- permission allow <rule>",
            "  Add an allow rule to the workspace permission settings.",
            "- permission ask <rule>",
            "  Add an ask rule to the workspace permission settings.",
            "- permission deny <rule>",
            "  Add a deny rule to the workspace permission settings.",
            "- permission session allow <rule> | permission session ask <rule> | permission session deny <rule>",
            "  Add a temporary session-only permission rule.",
            "- permission session reset",
            "  Clear all temporary session permission overrides.",
            "- permission reset",
            "  Reset workspace permission settings to defaults.",
            "- sessions | session list",
            "  List active persistent shell sessions in this process.",
            "- session create [cwd]",
            "  Start a persistent shell session in the workspace or relative cwd.",
            "- session send <id|last> <command>",
            "  Execute one command inside a persistent shell session with normal permission checks.",
            "- session close <id|last>",
            "  Close a persistent shell session.",
            "- commands",
            "  Alias for help.",
            "",
            "Model commands:",
            "- models",
            "  Show enabled providers, preferred provider, and current provider-model selection.",
            "- model use <local|cheap|chatgpt|openai|claude>",
            "  Set the preferred provider and persist it in this workspace.",
            "- model choose [local|cheap|chatgpt|openai|claude]",
            "  Guided menu: choose provider, provider-model, and supported parameters interactively.",
            "- model preset <provider> [fast|balanced|deep|plan]",
            "  Apply a preset directly; without the preset value, open a guided provider-model picker.",
            "- model add <local|cheap|chatgpt|openai|claude>",
            "  Enable a provider in this workspace.",
            "- model list <local|cheap|chatgpt|openai|claude>",
            "  Show the official provider-model aliases or model IDs for one provider.",
            "- model variant <local|cheap|chatgpt|openai|claude> <variant>",
            "  Pin the provider-specific model alias or model ID for that provider.",
            "- model variant-clear <local|cheap|chatgpt|openai|claude>",
            "  Clear the provider-model pin and return to automatic/provider-default selection.",
            "- model remove <local|cheap|chatgpt|openai|claude>",
            "  Disable a provider in this workspace.",
            "- model block <local|cheap|chatgpt|openai|claude> until YYYY-MM-DDTHH:MM",
            "  Keep the provider in the list but block routing to it until the given date and time.",
            "- model unblock <local|cheap|chatgpt|openai|claude>",
            "  Remove the temporary block from a provider.",
            "- model clear",
            "  Clear the preferred provider and restore automatic routing.",
            "- accounts",
            "  Show configured account profiles for each model.",
            "- account add <model> <name> [ENV_VAR]",
            "  Add an account profile. Optional ENV_VAR points to the token variable for that account.",
            "- account login <model> <name>",
            "  Log in to a provider and save credentials in the OS secret store. chatgpt uses browser login; openai can use device-code OAuth.",
            "- account login-device <chatgpt|openai> <name>",
            "  Alias for the Codex-style OpenAI/ChatGPT device-code login.",
            "- account logout <model> <name>",
            "  Delete the saved token for one profile.",
            "- account env <model> <name> <ENV_VAR>",
            "  Set or change the environment variable used as token source for a profile.",
            "- account import <model> <name> [PATH]",
            "  Import credentials from a provider-owned credentials file. For claude the default is ~/.claude/.credentials.json or $CLAUDE_CONFIG_DIR/.credentials.json.",
            "- account use <model> <name>",
            "  Prefer one account profile for a model.",
            "- account choose [model]",
            "  Guided menu: choose provider and one configured account profile interactively.",
            "- account remove <model> <name>",
            "  Remove an account profile.",
            "- account block <model> <name> until YYYY-MM-DDTHH:MM",
            "  Temporarily block one account profile after usage limits.",
            "- account unblock <model> <name>",
            "  Remove a temporary account block.",
            "- account clear <model>",
            "  Clear the preferred account for one model.",
            "",
            "Caveman commands:",
            "- /caveman help",
            "- /caveman <lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra> <task>",
            "- /caveman commit",
            "- /caveman review",
            "- /caveman compress <file>",
            "- stop caveman | normal mode",
            "- mode caveman <lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra>",
            "- mode normal",
            "- mode plan | mode auto | mode accept-edits | mode dont-ask | mode default",
            "- caveman help | caveman on [level] | caveman off",
            "- caveman commit | caveman review | caveman compress <file>",
            "",
            "Git commands:",
            "- git status",
            "  Show branch and working-tree changes.",
            "- git log [limit]",
            "  Show recent commits, default 20.",
            "- git history <path> [limit]",
            "  Show commit history for one file or directory.",
            "- git show [revision]",
            "  Show a revision, default HEAD.",
            "- git show --stat [revision]",
            "  Show revision summary with file stats.",
            "",
            "Task execution:",
            "- Any other input is executed as a task in the current workspace.",
            "",
            "Examples:",
            "- stagewarden> models",
            "- stagewarden> account login chatgpt personale",
            "- stagewarden> model choose",
            "- stagewarden> model choose chatgpt",
            "- stagewarden> model preset chatgpt",
            "- stagewarden> model use openai",
            "- stagewarden> model list claude",
            "- stagewarden> model variant claude opus",
            "- stagewarden> model variant openai gpt-5.4-mini",
            "- stagewarden> model remove claude",
            "- stagewarden> model block openai until 2026-05-01T18:30",
            "- stagewarden> account add openai lavoro OPENAI_API_KEY_WORK",
            "- stagewarden> account login openai lavoro",
            "- stagewarden> account add openai personale OPENAI_API_KEY_PERSONAL",
            "- stagewarden> account use openai lavoro",
            "- stagewarden> account choose openai",
            "- stagewarden> account block openai lavoro until 2026-05-01T18:30",
            "- stagewarden> model unblock openai",
            "- stagewarden> status",
            "- stagewarden> handoff",
            "- stagewarden> handoff export",
            "- stagewarden> boundary",
            "- stagewarden> risks",
            "- stagewarden> issues",
            "- stagewarden> quality",
            "- stagewarden> exception",
            "- stagewarden> lessons",
            "- stagewarden> transcript",
            "- stagewarden> todo",
            "- stagewarden> permissions",
            "- stagewarden> permission mode plan",
            "- stagewarden> permission session mode auto",
            "- stagewarden> permission allow shell:git status",
            "- stagewarden> permission session allow shell:python3 -m pytest",
            "- stagewarden> permission deny shell:rm",
            "- stagewarden> mode caveman ultra",
            "- stagewarden> mode normal",
            "- stagewarden> mode plan",
            "- stagewarden> mode auto",
            "- stagewarden> mode accept-edits",
            "- stagewarden> mode dont-ask",
            "- stagewarden> mode default",
            "- stagewarden> caveman on ultra",
            "- stagewarden> /caveman review",
            "- stagewarden> git status",
            "- stagewarden> git log 5",
            "- stagewarden> git history stagewarden/main.py 10",
            "- stagewarden> git show --stat HEAD",
            "- stagewarden> fix failing tests in router.py",
        ]
    )


def _interactive_help_overview() -> str:
    return "\n".join(
        [
            "Stagewarden interactive shell",
            "",
            "Use `help <topic>` for full commands and examples.",
            "",
            "Topics:",
            "- help core: exit, reset, overview, health, report, status, stream, sessions, transcript",
            "- help models: provider routing, provider models, blocks",
            "- help accounts: provider profiles, login, env vars, usage limits",
            "- help permissions: plan/auto modes, allow/ask/deny rules",
            "- help handoff: overview, PRINCE2 handoff, board review, registers, backlog",
            "- help git: status, log, file history, show",
            "- help caveman: Caveman aliases and modes",
            "- help ljson: encode, decode, benchmark",
            "",
            "Fast examples:",
            "- stagewarden> overview",
            "- stagewarden> health",
            "- stagewarden> report",
            "- stagewarden> stream status",
            "- stagewarden> help models",
            "- stagewarden> models",
            "- stagewarden> models usage",
            "- stagewarden> session create",
            "- stagewarden> session send last pwd",
            "- stagewarden> patch preview changes.diff",
            "- stagewarden> board",
            "- stagewarden> handoff",
            "- stagewarden> fix failing tests",
        ]
    )


def _interactive_help_topic(topic: str) -> str:
    normalized = topic.strip().lower()
    aliases = {
        "model": "models",
        "account": "accounts",
        "permission": "permissions",
        "perm": "permissions",
        "prince2": "handoff",
        "history": "git",
        "sessions": "core",
        "session": "core",
    }
    normalized = aliases.get(normalized, normalized)
    topics = {
        "core": [
            "Core commands",
            "",
            "- help [topic]",
            "- exit | quit",
            "- reset",
            "- overview",
            "- health",
            "- report",
            "- status",
            "- status full",
            "- statusline",
            "- auth status <chatgpt|claude>",
            "- stream on | stream off | stream status",
            "- transcript | trace",
            "- doctor",
            "- sessions | session list",
            "- session create [cwd]",
            "- session send <id|last> <command>",
            "- session close <id|last>",
            "- patch preview <diff-file>",
            "",
            "Examples:",
            "- stagewarden> overview",
            "- stagewarden> health",
            "- stagewarden> report",
            "- stagewarden> status",
            "- stagewarden> status full",
            "- stagewarden> statusline",
            "- stagewarden> auth status chatgpt",
            "- stagewarden> stream off",
            "- stagewarden> doctor",
            "- stagewarden> session create",
            "- stagewarden> session send last pwd",
            "- stagewarden> patch preview changes.diff",
            "- stagewarden> transcript",
        ],
        "models": [
            "Model commands",
            "",
            "- models",
            "- models usage | cost",
            "- models limits | model limits",
            "- model use <local|cheap|chatgpt|openai|claude>",
            "- model choose [local|cheap|chatgpt|openai|claude]",
            "- model add <local|cheap|chatgpt|openai|claude>",
            "- model remove <local|cheap|chatgpt|openai|claude>",
            "- model list <local|cheap|chatgpt|openai|claude>",
            "- model params <local|cheap|chatgpt|openai|claude>",
            "- model variant <provider> <variant>",
            "- model variant-clear <provider>",
            "- model preset <provider> [fast|balanced|deep|plan]",
            "- model param set <provider> <key> <value>",
            "- model param clear <provider> <key>",
            "- model block <model> until YYYY-MM-DDTHH:MM",
            "- model unblock <model>",
            "- model limit-record <model> <provider message>",
            "- model limit-clear <model>",
            "- model clear",
            "",
            "Examples:",
            "- stagewarden> models usage",
            "- stagewarden> model limits",
            "- stagewarden> model choose",
            "- stagewarden> model choose chatgpt",
            "- stagewarden> model use openai",
            "- stagewarden> model list claude",
            "- stagewarden> model params chatgpt",
            "- stagewarden> model variant openai gpt-5.4-mini",
            "- stagewarden> model preset chatgpt",
            "- stagewarden> model preset chatgpt deep",
            "- stagewarden> model param set chatgpt reasoning_effort high",
            "- stagewarden> model block openai until 2026-05-01T18:30",
            "- stagewarden> model limit-record chatgpt You've hit your usage limit. Try again at 8:05 PM.",
        ],
        "accounts": [
            "Account commands",
            "",
            "- accounts",
            "- account add <model> <name> [ENV_VAR]",
            "- account login <chatgpt|openai> <name>",
            "- account login-device <chatgpt|openai> <name>",
            "- account import <model> <name> [PATH]",
            "- account env <model> <name> <ENV_VAR>",
            "- account use <model> <name>",
            "- account choose [model]",
            "- account logout <model> <name>",
            "- account remove <model> <name>",
            "- account block <model> <name> until YYYY-MM-DDTHH:MM",
            "- account unblock <model> <name>",
            "- account limit-record <model> <name> <provider message>",
            "- account limit-clear <model> <name>",
            "- account clear <model>",
            "",
            "Examples:",
            "- stagewarden> account login chatgpt personale",
            "- stagewarden> account choose",
            "- stagewarden> account choose openai",
            "- stagewarden> account login-device openai lavoro",
            "- stagewarden> account add openai lavoro OPENAI_API_KEY_WORK",
            "- stagewarden> account import claude lavoro ~/.claude/.credentials.json",
        ],
        "permissions": [
            "Permission commands",
            "",
            "- permissions",
            "- permission mode <default|accept_edits|plan|auto|dont_ask>",
            "- permission allow <rule>",
            "- permission ask <rule>",
            "- permission deny <rule>",
            "- permission session mode <default|accept_edits|plan|auto|dont_ask>",
            "- permission session allow <rule>",
            "- permission session ask <rule>",
            "- permission session deny <rule>",
            "- permission session reset",
            "- permission reset",
            "",
            "Examples:",
            "- stagewarden> permission mode plan",
            "- stagewarden> permission ask shell:python3 -m unittest",
            "- stagewarden> permission session allow shell:git status",
        ],
        "handoff": [
            "Handoff and PRINCE2 commands",
            "",
            "- overview",
            "- health",
            "- report",
            "- handoff",
            "- handoff export | handoff md",
            "- board | stage review",
            "- resume",
            "- resume --show",
            "- resume context",
            "- resume --clear",
            "- boundary",
            "- todo",
            "- risks",
            "- issues",
            "- quality",
            "- exception",
            "- lessons",
            "",
            "Examples:",
            "- stagewarden> overview",
            "- stagewarden> health",
            "- stagewarden> report",
            "- stagewarden> handoff",
            "- stagewarden> board",
            "- stagewarden> resume --show",
            "- stagewarden> resume context",
            "- stagewarden> resume --clear",
            "- stagewarden> boundary",
            "- stagewarden> handoff export",
        ],
        "git": [
            "Git commands",
            "",
            "- git status",
            "- git log [limit]",
            "- git history <path> [limit]",
            "- git show [revision]",
            "- git show --stat [revision]",
            "",
            "Examples:",
            "- stagewarden> git status",
            "- stagewarden> git log 5",
            "- stagewarden> git history stagewarden/main.py 10",
        ],
        "caveman": [
            "Caveman commands",
            "",
            "- /caveman help",
            "- /caveman <lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra> <task>",
            "- /caveman commit",
            "- /caveman review",
            "- /caveman compress <file>",
            "- caveman help | caveman on [level] | caveman off",
            "- mode caveman <level>",
            "- mode normal",
            "",
            "Examples:",
            "- stagewarden> caveman on ultra",
            "- stagewarden> /caveman review",
            "- stagewarden> mode normal",
        ],
        "ljson": [
            "LJSON commands",
            "",
            "- stagewarden --ljson-encode records.json [--ljson-output out.ljson]",
            "- stagewarden --ljson-decode records.ljson [--ljson-output records.json]",
            "- stagewarden --ljson-encode records.json --ljson-numeric --ljson-gzip",
            "- stagewarden --ljson-benchmark records.json",
            "",
            "Examples:",
            "- python3 -m stagewarden.main --ljson-encode data.json",
            "- python3 -m stagewarden.main --ljson-benchmark data.json",
        ],
    }
    lines = topics.get(normalized)
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
        "workspace": {
            "cwd": status["workspace"],
            "files": status["files"],
        },
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
        },
        "usage": _model_usage_report(config)["report"],
        "quality_gates": {
            "wet_run_required": True,
            "dry_run_valid_checkpoint": False,
            "git_snapshot_required": True,
            "provider_limits_stale_after_minutes": 15,
        },
    }


def _render_status_full(agent: Agent, config: AgentConfig) -> str:
    report = _status_dashboard_report(agent, config)
    lines = [
        "Stagewarden full status:",
        "Identity:",
        f"- workspace: {report['identity']['workspace']}",
        f"- mode: {report['identity']['mode']}",
        f"- python: {report['identity']['python']}",
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
        lines.append(f"- {item['provider']}: {item['status']}{blocked}{reason}")
    lines.extend(
        [
            "Workspace:",
            f"- cwd: {report['workspace']['cwd']}",
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
            "Usage:",
            f"- calls: {report['usage']['totals']['calls']}",
            f"- failures: {report['usage']['totals']['failures']}",
            f"- escalation_path: {report['usage']['totals']['escalation_path']}",
            "Quality Gates:",
            "- wet_run_required: true",
            "- dry_run_valid_checkpoint: false",
            "- git_snapshot_required: true",
        ]
    )
    return "\n".join(lines)


def _statusline_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
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
        "context_window": {
            "total_input_tokens": None,
            "total_output_tokens": None,
            "context_window_size": None,
            "current_usage": None,
            "used_percentage": None,
            "remaining_percentage": None,
        },
        "rate_limits": [_statusline_rate_limit(item) for item in provider_limits],
        "handoff": status["handoff"]["stage_view"],
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
        "used_percentage": windows["utilization"],
        "resets_at": windows["blocked_until"] or windows["overage_resets_at"],
    }


def _provider_limit_summary(agent: Agent, config: AgentConfig) -> str:
    report = _provider_limit_status_report(agent, config)
    providers = report["providers"]
    if not providers:
        return "none"
    blocked_models = [item["provider"] for item in providers if item["blocked_until"]]
    blocked_accounts = [
        f"{item['provider']}:{account['name']}"
        for item in providers
        for account in item["blocked_accounts"]
    ]
    last_errors = [
        f"{item['provider']}={item['last_error_reason']}"
        for item in providers
        if item["last_error_reason"]
    ]
    active_routes = [
        f"{item['provider']}:{item['active_account']}/{item['variant']}"
        for item in providers
    ]
    parts = [
        f"providers={len(providers)}",
        f"blocked_models={','.join(blocked_models) if blocked_models else 'none'}",
        f"blocked_accounts={','.join(blocked_accounts) if blocked_accounts else 'none'}",
        f"last_errors={','.join(last_errors) if last_errors else 'none'}",
        f"routes={','.join(active_routes)}",
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
    lines = [
        "Stagewarden status:",
        f"- workspace: {config.workspace_root}",
        f"- mode: {mode}",
        f"- memory: {config.memory_path.name}",
        f"- trace: {config.trace_path.name}",
        f"- handoff: {config.handoff_path.name}",
        f"- model_config: {config.model_prefs_path.name}",
        _render_model_status(agent, config),
        _render_provider_limit_status(agent, config),
        _render_resume_context(config),
        _render_permissions(config),
        "Handoff summary:",
        handoff.summary(),
        handoff.rendered_operational_posture(),
    ]
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
        "provider_limits": _provider_limit_status_report(agent, config),
        "permissions": _permissions_report(config),
        "handoff": {
            "summary": handoff.summary(),
            "operational_posture": handoff.rendered_operational_posture(),
            "stage_view": handoff.stage_view(),
        },
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
        "next_action": handoff.rendered_next_action(),
    }


def _render_resume_show(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    lines = [
        "Resume target:",
        f"- task: {handoff.task or 'none'}",
        f"- current_step: {handoff.current_step_id or 'none'}",
        f"- current_step_status: {handoff.current_step_status or 'none'}",
        f"- next_action: {handoff.rendered_next_action()}",
        handoff.rendered_stage_view(),
    ]
    return "\n".join(lines)


def _resume_context_payload(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    memory = MemoryStore.load(config.memory_path)
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
        "latest_model_attempt": attempt_payload,
        "latest_tool_evidence": tool_payload,
        "latest_git_snapshot": snapshot_payload,
    }


def _render_resume_context(config: AgentConfig) -> str:
    payload = _resume_context_payload(config)
    lines = [
        "Resume context:",
        f"- task: {payload['task']}",
        f"- current_step: {payload['current_step']}",
        f"- current_step_status: {payload['current_step_status']}",
    ]
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
    return "\n".join(lines)


def _resume_show_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "resume --show",
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "next_action": handoff.rendered_next_action(),
        "stage_view": handoff.stage_view(),
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
                "routing_budget": "prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.",
            },
        }
    except (OSError, ValueError, TypeError):
        return {
            "command": "models usage",
            "report": MemoryStore().model_usage_stats(),
            "policy": {
                "routing_budget": "prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.",
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
            source = MODEL_VARIANT_CATALOG[model]["source"]
            specs = provider_model_specs(model)
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
        "Usage: model use <name> | model choose [name] | model add <name> | model list <name> | "
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


def _interactive_completion_candidates(text: str, config: AgentConfig) -> list[str]:
    normalized = text.lstrip()
    lowered = normalized.lower()
    path_prefixes = ("git history ", "patch preview ", "session create ")
    for prefix in path_prefixes:
        if lowered.startswith(prefix):
            partial = normalized[len(prefix) :]
            return [f"{prefix}{entry}" for entry in _workspace_relative_candidates(config, partial)]
    if lowered.startswith("git show "):
        return [item for item in ("git show HEAD", "git show --stat HEAD") if item.startswith(lowered)]
    matches = [phrase for phrase in INTERACTIVE_COMMAND_PHRASES if phrase.startswith(lowered)]
    return matches


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
    if lowered in {"help", "commands"}:
        return None, interactive_help_text()
    if lowered.startswith("help "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "caveman":
            return None, agent.caveman.help_text()
        return None, interactive_help_text(topic)
    if lowered.startswith("commands "):
        topic = command.split(maxsplit=1)[1]
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

    sink.write(f"Stagewarden interactive shell in {config.workspace_root}\n")
    sink.write("Type 'help' for commands.\n")
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
        if command in {"exit", "quit"}:
            sink.write("Session closed.\n")
            sink.flush()
            return 0
        if command == "reset":
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
        if command in {"stream on", "stream off", "stream status"}:
            if command == "stream status":
                sink.write(f"Model streaming is {'on' if stream_enabled else 'off'}.\n")
                sink.flush()
                continue
            stream_enabled = command == "stream on"
            apply_stream_callback(agent)
            sink.write(f"Model streaming {'enabled' if stream_enabled else 'disabled'} for this session.\n")
            sink.flush()
            continue
        rewritten, immediate = _rewrite_shell_command(command, agent)
        if immediate is not None:
            sink.write(f"{immediate}\n")
            sink.flush()
            continue
        command = rewritten or command
        model_message = _handle_model_command(command, agent, config, input_stream=source, output_stream=sink)
        if model_message is not None:
            sink.write(f"{model_message}\n")
            sink.flush()
            continue
        account_message = _handle_account_command(command, agent, config, input_stream=source, output_stream=sink)
        if account_message is not None:
            sink.write(f"{account_message}\n")
            sink.flush()
            continue
        mode_message = _handle_mode_command(command, agent, config)
        if mode_message is not None:
            sink.write(f"{mode_message}\n")
            sink.flush()
            continue
        resume_message = _handle_resume_command(command, agent, config)
        if resume_message is not None:
            sink.write(f"{resume_message}\n")
            sink.flush()
            continue
        git_message = _handle_git_command(command, config)
        if git_message is not None:
            sink.write(f"{git_message}\n")
            sink.flush()
            continue
        shell_session_message = _handle_shell_session_command(command, agent)
        if shell_session_message is not None:
            sink.write(f"{shell_session_message}\n")
            sink.flush()
            continue
        patch_message = _handle_patch_command(command, agent)
        if patch_message is not None:
            sink.write(f"{patch_message}\n")
            sink.flush()
            continue

        sink.write(f"Running task: {command}\n")
        sink.write(f"{_render_shell_progress(agent, phase='before', command=command)}\n")
        sink.flush()
        result = agent.run(command)
        sink.write("Agent result:\n")
        sink.write(f"{result.message}\n")
        sink.write(f"{_render_last_step_outcome(agent)}\n")
        sink.write(f"{_render_shell_progress(agent, phase='after')}\n")
        sink.flush()


def main() -> int:
    args = build_parser().parse_args()
    config = AgentConfig(
        workspace_root=Path.cwd(),
        max_steps=args.max_steps,
        verbose=args.verbose,
        strict_ascii_output=args.strict_ascii_output,
    )

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
