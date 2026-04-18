from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .agent import Agent
from .config import AgentConfig
from .handoff import MODEL_BACKENDS
from .ljson import LJSONOptions, benchmark_sizes, decode, dump_file, encode, load_file
from .modelprefs import ModelPreferences, SUPPORTED_MODELS
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8
from .tools.git import GitTool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stagewarden", description="Stagewarden: production-grade CLI coding agent.")
    parser.add_argument("task", nargs="?", default="", help='Task to execute, for example: stagewarden "fix the failing tests"')
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
    return parser


def interactive_help_text() -> str:
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
            "- commands",
            "  Alias for help.",
            "",
            "Model commands:",
            "- models",
            "  Show enabled models, preferred model, and backend mapping.",
            "- model use <local|cheap|gpt|claude>",
            "  Set the preferred model and persist it in this workspace.",
            "- model add <local|cheap|gpt|claude>",
            "  Enable a model in this workspace.",
            "- model remove <local|cheap|gpt|claude>",
            "  Disable a model in this workspace.",
            "- model block <local|cheap|gpt|claude> until YYYY-MM-DDTHH:MM",
            "  Keep the model in the list but block routing to it until the given date and time.",
            "- model unblock <local|cheap|gpt|claude>",
            "  Remove the temporary block from a model.",
            "- model clear",
            "  Clear the preferred model and restore automatic routing.",
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
            "- stagewarden> model use gpt",
            "- stagewarden> model remove claude",
            "- stagewarden> model block gpt until 2026-05-01T18:30",
            "- stagewarden> model unblock gpt",
            "- stagewarden> status",
            "- stagewarden> mode caveman ultra",
            "- stagewarden> mode normal",
            "- stagewarden> caveman on ultra",
            "- stagewarden> /caveman review",
            "- stagewarden> git status",
            "- stagewarden> git log 5",
            "- stagewarden> git history stagewarden/main.py 10",
            "- stagewarden> git show --stat HEAD",
            "- stagewarden> fix failing tests in router.py",
        ]
    )


def _load_model_preferences(config: AgentConfig) -> ModelPreferences:
    return ModelPreferences.load(config.model_prefs_path)


def _save_model_preferences(config: AgentConfig, prefs: ModelPreferences) -> None:
    prefs.normalize().save(config.model_prefs_path)


def _apply_model_preferences(agent: Agent, config: AgentConfig) -> ModelPreferences:
    prefs = _load_model_preferences(config)
    agent.router.configure(
        enabled_models=prefs.enabled_models,
        preferred_model=prefs.preferred_model,
        blocked_until_by_model=prefs.blocked_until_by_model or {},
    )
    return prefs


def _render_model_status(agent: Agent) -> str:
    status = agent.router.status()
    lines = ["Model configuration:"]
    for model in SUPPORTED_MODELS:
        backend = MODEL_BACKENDS[model]["label"]
        enabled = "enabled" if model in status["enabled_models"] else "disabled"
        blocked_until = status["blocked_until_by_model"].get(model)
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        active = " active" if model in status["active_models"] else " inactive"
        preferred = " preferred" if status["preferred_model"] == model else ""
        lines.append(f"- {model}: {enabled}{active}{preferred}{blocked} ({backend})")
    if status["preferred_model"] is None:
        lines.append("- preferred_model: automatic routing")
    return "\n".join(lines)


def _render_status(agent: Agent, config: AgentConfig) -> str:
    _apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    lines = [
        "Stagewarden status:",
        f"- workspace: {config.workspace_root}",
        f"- mode: {mode}",
        f"- memory: {config.memory_path.name}",
        f"- trace: {config.trace_path.name}",
        f"- model_config: {config.model_prefs_path.name}",
        _render_model_status(agent),
    ]
    return "\n".join(lines)


def _configure_agent_for_workspace(config: AgentConfig) -> Agent:
    agent = Agent(config)
    _apply_model_preferences(agent, config)
    return agent


def _handle_model_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "models":
        _apply_model_preferences(agent, config)
        return _render_model_status(agent)
    if parts[0] != "model":
        return None
    if len(parts) < 2:
        return "Usage: model use <name> | model add <name> | model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | model unblock <name> | model clear"

    action = parts[1]
    prefs = _load_model_preferences(config)
    try:
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
            return f"Preferred model set to {model}."
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
            return "Preferred model cleared. Automatic routing restored."
    except ValueError as exc:
        return str(exc)

    return "Usage: model use <name> | model add <name> | model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | model unblock <name> | model clear"


def _handle_mode_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "status":
        return _render_status(agent, config)
    if parts[0] != "mode":
        return None
    if len(parts) == 2 and parts[1] == "normal":
        result = agent.run("normal mode")
        return result.message
    if len(parts) == 3 and parts[1] == "caveman":
        result = agent.run(f"/caveman {parts[2]}")
        return result.message
    return "Usage: mode caveman <level> | mode normal"


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


def _parse_limit(raw: str, *, default: int) -> int:
    if not raw:
        return default
    try:
        return max(1, min(int(raw), 200))
    except ValueError:
        return default


def _rewrite_shell_command(command: str, agent: Agent) -> tuple[str | None, str | None]:
    lowered = command.lower().strip()
    if lowered in {"help", "commands"}:
        return None, interactive_help_text()
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


def run_interactive_shell(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    agent = _configure_agent_for_workspace(config)

    sink.write(f"Stagewarden interactive shell in {config.workspace_root}\n")
    sink.write("Type 'help' for commands.\n")
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
            agent = _configure_agent_for_workspace(config)
            sink.write("Session reset.\n")
            sink.flush()
            continue
        rewritten, immediate = _rewrite_shell_command(command, agent)
        if immediate is not None:
            sink.write(f"{immediate}\n")
            sink.flush()
            continue
        command = rewritten or command
        model_message = _handle_model_command(command, agent, config)
        if model_message is not None:
            sink.write(f"{model_message}\n")
            sink.flush()
            continue
        mode_message = _handle_mode_command(command, agent, config)
        if mode_message is not None:
            sink.write(f"{mode_message}\n")
            sink.flush()
            continue
        git_message = _handle_git_command(command, config)
        if git_message is not None:
            sink.write(f"{git_message}\n")
            sink.flush()
            continue

        result = agent.run(command)
        sink.write(f"{result.message}\n")
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
        records = loads_text(read_text_utf8(Path(args.ljson_encode)))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-encode must be a JSON array.")
        target = Path(args.ljson_output) if args.ljson_output else Path(args.ljson_encode).with_suffix(".ljson")
        dump_file(
            target,
            records,
            options=LJSONOptions(numeric_keys=args.ljson_numeric),
            gzip_enabled=args.ljson_gzip,
        )
        print(str(target))
        return 0

    if args.ljson_decode:
        records = load_file(args.ljson_decode, gzipped=args.ljson_gzip or str(args.ljson_decode).endswith(".gz"))
        target = Path(args.ljson_output) if args.ljson_output else Path(args.ljson_decode).with_suffix(".json")
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

    agent = _configure_agent_for_workspace(config)
    task = args.task
    if args.caveman_help:
        task = "/caveman help"
    elif args.caveman_commit:
        task = "/caveman commit"
    elif args.caveman_review:
        task = "/caveman review"
    elif args.caveman_compress:
        task = f"/caveman compress {args.caveman_compress}"
    elif args.caveman:
        task = f"/caveman {args.caveman} {args.task}".strip()
    elif args.interactive or not task:
        return run_interactive_shell(config)

    result = agent.run(task)
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
