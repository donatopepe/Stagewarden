from __future__ import annotations

import atexit
import sys
from pathlib import Path
from typing import Callable, TextIO

from .agent import Agent
from .config import AgentConfig
from . import agent_setup_views as _agent_setup_views
from . import extension_views as _extension_views
from . import mode_views as _mode_views
from .commands import command_catalog, command_phrases, command_specs_by_query, render_command_catalog
from .permissions import PermissionSettings
from .modelprefs import PRINCE2_ROLE_IDS, SUPPORTED_MODELS
from . import model_views as _model_views
from . import project_handoff_views as _project_handoff_views
from . import ui_views as _ui_views
from .ui_views import _guided_slash_choice
from . import status_views as _status_views
from .provider_registry import provider_capability, provider_model_spec, provider_model_specs
from .runtime_env import detect_runtime_capabilities, select_shell_backend
from .command_dispatch import (
    execute_external_io_command as _external_io_execute,
    execute_system_command as _system_execute,
)
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8
from . import json_schema_registry as _json_schema_registry
from . import account_views as _account_views
from . import command_views as _command_views
from . import tool_reports as _tool_reports
from .project import flow as _project_flow
from .project import role_command_flow as _project_role_command_flow
from .project import tree_flow as _project_tree_flow

try:
    import readline
except ImportError:  # pragma: no cover - platform dependent
    readline = None


INTERACTIVE_COMMAND_PREFIX = "/"

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


def _interactive_command_phrases() -> tuple[str, ...]:
    return INTERACTIVE_COMMAND_PHRASES


def _provider_model_candidates(provider: str, partial: str) -> list[str]:
    try:
        specs = provider_model_specs(provider)  # type: ignore[name-defined]
    except ValueError:
        return []
    lowered = partial.strip().lower()
    return [spec.id for spec in specs if spec.id.lower().startswith(lowered)]


def _reasoning_effort_candidates(provider: str, provider_model: str, partial: str) -> list[str]:
    spec = provider_model_spec(provider, provider_model)  # type: ignore[name-defined]
    if spec is None:
        return []
    lowered = partial.strip().lower()
    return [effort for effort in spec.reasoning_efforts if effort.lower().startswith(lowered)]


def _account_name_candidates(config: AgentConfig, provider: str, partial: str) -> list[str]:
    try:
        prefs = _model_views._load_model_preferences(config)
    except OSError:
        return []
    accounts = list((prefs.accounts_by_model or {}).get(provider, []))
    return _prefixed_candidates(f"account use {provider} ", accounts, partial)


def _workspace_relative_candidates(config: AgentConfig, partial: str) -> list[str]:
    root = config.workspace_root
    prefix = partial.strip()
    if not prefix:
        return []
    results: list[str] = []
    try:
        for entry in sorted(root.rglob(f"{prefix}*")):
            try:
                relative = entry.relative_to(root)
            except ValueError:
                continue
            if relative.name.startswith(".stagewarden_"):
                continue
            text = str(relative)
            if entry.is_dir():
                text += "/"
            results.append(text)
    except OSError:
        return []
    return results


def _prefixed_candidates(prefix: str, options: list[str], partial: str) -> list[str]:
    lowered = partial.strip().lower()
    return [f"{INTERACTIVE_COMMAND_PREFIX}{prefix}{item}" for item in options if item.lower().startswith(lowered)]


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
                return [f"{INTERACTIVE_COMMAND_PREFIX}model param set {provider} reasoning_effort "]  # type: ignore[name-defined]
        if len(parts) >= 5:
            provider = parts[3].strip().lower()
            key = parts[4].strip().lower()
            if provider in SUPPORTED_MODELS and key == "reasoning_effort":
                prefs = _model_views._load_model_preferences(config)
                provider_model = prefs.variant_for_model(provider) or provider_capability(provider).default_model  # type: ignore[name-defined]
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
                    prefs = _model_views._load_model_preferences(config)
                    return _prefixed_candidates(f"{prefix}{provider} ", list((prefs.accounts_by_model or {}).get(provider, [])), partial)
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
    for phrase in _interactive_command_phrases():
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
    except Exception:  # pragma: no cover - readline platform behavior
        return False

    def save_history() -> None:
        try:
            readline.write_history_file(str(history_path))
        except Exception:  # pragma: no cover - history persistence best effort
            pass

    atexit.register(save_history)
    return True


def _planned_shell_route(agent: Agent, command: str) -> tuple[str, str, str]:
    if command.startswith("/model "):
        return "openai", "none", "provider-default"
    if command.startswith("/account "):
        return "openai", "none", "provider-default"
    active = set(agent.router.status().get("active_models", []))
    for candidate in ("chatgpt", "openai", "claude", "cheap", "local"):
        if candidate in active:
            return candidate, "none", "provider-default"
    return agent.router.choose_model("fallback cloud priority", "analysis", 0), "none", "provider-default"


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


def _rewrite_shell_command(command: str, agent: Agent) -> tuple[str | None, str | None]:
    lowered = command.lower().strip()
    if lowered == "help":
        return None, _ui_views.interactive_help_text()
    if lowered in {"help topics", "help topics --json", "help --json"}:
        return None, _ui_views.interactive_help_text() if not lowered.endswith("--json") else dumps_ascii(_json_schema_registry.with_json_schema("help", _ui_views._help_json_report()), indent=2)
    if lowered == "slash choose":
        return None, _ui_views._render_slash_choice_candidates(agent.config)
    if lowered.startswith("slash choose "):
        query = command.split(maxsplit=2)[2]
        return None, _ui_views._render_slash_choice_candidates(agent.config, query)
    if lowered == "slash":
        return None, _ui_views._render_slash_palette(agent.config)
    if lowered == "slash --json":
        return None, dumps_ascii(_json_schema_registry.with_json_schema("slash", _ui_views._slash_palette_report(agent.config)), indent=2)
    if lowered.startswith("slash "):
        prefix = command.split(maxsplit=1)[1]
        if prefix.endswith(" --json"):
            prefix = prefix[: -len(" --json")].strip()
            return None, dumps_ascii(_json_schema_registry.with_json_schema("slash", _ui_views._slash_palette_report(agent.config, prefix)), indent=2)
        return None, _ui_views._render_slash_palette(agent.config, prefix)
    if lowered == "commands":
        return None, render_command_catalog()
    if lowered == "commands --json":
        return None, dumps_ascii(_json_schema_registry.with_json_schema("commands", {"command": "commands", "commands": command_catalog()}), indent=2)
    if lowered.startswith("help "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii(_json_schema_registry.with_json_schema("help", _ui_views._help_json_report()), indent=2)
        if topic.lower().strip() == "caveman":
            return None, agent.caveman.help_text()
        if topic.lower().strip() == "topics":
            return None, _ui_views.interactive_help_text()
        if topic.lower().strip().endswith(" --json"):
            raw_topic = topic[: -len(" --json")].strip()
            if raw_topic.lower() == "caveman":
                return None, dumps_ascii(_json_schema_registry.with_json_schema("help", {"command": "help", "ok": True, "topic": "caveman", "title": "Caveman", "message": "Use `help caveman` for the rich caveman help surface."}), indent=2)
            return None, dumps_ascii(_json_schema_registry.with_json_schema("help", _ui_views._help_json_report(raw_topic)), indent=2)
        return None, _ui_views.interactive_help_text(topic)
    if lowered.startswith("commands "):
        topic = command.split(maxsplit=1)[1]
        if topic.lower().strip() == "--json":
            return None, dumps_ascii(_json_schema_registry.with_json_schema("commands", {"command": "commands", "commands": command_catalog()}), indent=2)
        return None, _ui_views.interactive_help_text(topic)
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
        choice = answer.strip().lower()
        if choice in {"wait", "w"}:
            return "wait"
        return "stop"

    return decide

def _run_interactive_shell_impl(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    shell_exports = {
        "_interactive_command_phrases": _interactive_command_phrases,
        "_provider_model_candidates": _provider_model_candidates,
        "_reasoning_effort_candidates": _reasoning_effort_candidates,
        "_account_name_candidates": _account_name_candidates,
        "_workspace_relative_candidates": _workspace_relative_candidates,
        "_prefixed_candidates": _prefixed_candidates,
        "_interactive_contextual_candidates": _interactive_contextual_candidates,
        "_ranked_command_phrase_matches": _ranked_command_phrase_matches,
        "_interactive_completion_candidates": _interactive_completion_candidates,
        "_configure_readline": _configure_readline,
        "_planned_shell_route": _planned_shell_route,
        "_render_shell_backend": _render_shell_backend,
        "_render_shell_progress": _render_shell_progress,
        "_render_last_step_outcome": _render_last_step_outcome,
        "_prompt_menu_choice": _prompt_menu_choice,
        "_is_known_interactive_command": _is_known_interactive_command,
        "_rewrite_shell_command": _rewrite_shell_command,
        "_permission_rule_from_decision": _permission_rule_from_decision,
        "_remove_rule": _remove_rule,
        "_make_permission_approver": _make_permission_approver,
        "_make_rate_limit_decider": _make_rate_limit_decider,
        "INTERACTIVE_COMMAND_PREFIX": INTERACTIVE_COMMAND_PREFIX,
    }
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    agent = _agent_setup_views._configure_agent_for_workspace(config)
    provider_limits = _status_views._provider_limit_status_report(agent, config)
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
            agent = _agent_setup_views._configure_agent_for_workspace(config)
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
        account_message = _account_views._handle_account_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if account_message is not None:
            sink.write(f"{account_message}\n")
            sink.flush()
            continue
        project_brief_message = _project_flow._handle_project_brief_command(shell_command, config)
        if project_brief_message is not None:
            sink.write(f"{project_brief_message}\n")
            sink.flush()
            continue
        if shell_command in {"project tree propose", "project tree propose --ai"}:
            use_ai = shell_command.endswith(" --ai")
            report = _project_tree_flow._project_tree_proposal_report(config, agent=agent, use_ai=use_ai)
            _project_tree_flow._record_project_tree_proposal_action(config, report, task=shell_command)
            sink.write(f"{_project_tree_flow._render_project_tree_proposal_report(report)}\n")
            sink.flush()
            continue
        if shell_command in {"project tree approve", "project tree approve --force"}:
            sink.write(f"{_project_tree_flow._render_project_tree_approval(config, force=shell_command.endswith(' --force'))}\n")
            sink.flush()
            continue
        role_message = _project_role_command_flow._handle_project_and_roles_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if role_message is None:
            role_message = _project_role_command_flow._handle_role_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if role_message is not None:
            sink.write(f"{role_message}\n")
            sink.flush()
            continue
        sources_message = _status_views._handle_sources_command(shell_command, config)
        if sources_message is not None:
            sink.write(f"{sources_message}\n")
            sink.flush()
            continue
        update_message = _status_views._handle_update_command(shell_command, config)
        if update_message is not None:
            sink.write(f"{update_message}\n")
            sink.flush()
            continue
        extension_message = _extension_views._handle_extension_command(shell_command, config)
        if extension_message is not None:
            sink.write(f"{extension_message}\n")
            sink.flush()
            continue
        external_io_message = _tool_reports.handle_external_io_command(
            shell_command,
            config,
            execute_external_io_command=_external_io_execute,
            record_handoff_action=_project_handoff_views._record_handoff_action,
        )
        if external_io_message is not None:
            sink.write(f"{external_io_message}\n")
            sink.flush()
            continue
        system_message = _tool_reports.handle_system_command(
            shell_command,
            config,
            execute_system_command=_system_execute,
            record_handoff_action=_project_handoff_views._record_handoff_action,
        )
        if system_message is not None:
            sink.write(f"{system_message}\n")
            sink.flush()
            continue
        mode_message = _mode_views._handle_mode_command(shell_command, agent, config)
        if mode_message is not None:
            sink.write(f"{mode_message}\n")
            sink.flush()
            continue
        resume_message = _project_handoff_views._handle_resume_command(shell_command, agent, config)
        if resume_message is not None:
            sink.write(f"{resume_message}\n")
            sink.flush()
            continue
        git_message = _command_views._handle_git_command(shell_command, config)
        if git_message is not None:
            sink.write(f"{git_message}\n")
            sink.flush()
            continue
        file_message = _command_views._handle_file_command(shell_command, config)
        if file_message is not None:
            sink.write(f"{file_message}\n")
            sink.flush()
            continue
        shell_session_message = _command_views._handle_shell_session_command(shell_command, agent)
        if shell_session_message is not None:
            sink.write(f"{shell_session_message}\n")
            sink.flush()
            continue
        patch_message = _command_views._handle_patch_command(shell_command, agent)
        if patch_message is not None:
            sink.write(f"{patch_message}\n")
            sink.flush()
            continue
        sink.write(f"Unknown slash command: /{shell_command}\n")
        sink.write("Use '/help' for available commands or remove '/' to send a task to the agent.\n")
        sink.flush()


def run_interactive_shell(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    return _run_interactive_shell_impl(config, input_stream=input_stream, output_stream=output_stream)
