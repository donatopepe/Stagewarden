from __future__ import annotations

import textwrap
from typing import TextIO

from .commands import command_specs_by_query, help_topic_catalog, help_topic_lines, help_topic_report
from .config import AgentConfig
from .json_schema_registry import json_schema
from .modelprefs import PRINCE2_ROLE_IDS
from .provider_registry import provider_model_specs


def _main():
    from . import main as _main_module

    return _main_module


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


def _slash_match_report(spec: object, query: str) -> dict[str, object]:
    phrases = [
        str(getattr(spec, "name", "")),
        str(getattr(spec, "usage", "")),
        str(getattr(spec, "description", "")),
        *[str(item) for item in getattr(spec, "aliases", ())],
        *[str(item) for item in getattr(spec, "examples", ())],
    ]
    if not query:
        phrase = str(getattr(spec, "name", ""))
        return {"query": "", "phrase": phrase, "highlight": phrase, "score": 0}
    scored = [
        (score, phrase)
        for phrase in phrases
        if phrase and (score := _slash_fuzzy_score(query, phrase)) is not None
    ]
    if not scored:
        return {"query": query, "phrase": "", "highlight": "", "score": None}
    score, phrase = min(scored, key=lambda item: (item[0], len(item[1])))
    return {
        "query": query,
        "phrase": phrase,
        "highlight": _highlight_fuzzy_match(query, phrase),
        "score": score,
    }


def _slash_fuzzy_score(query: str, candidate: str) -> int | None:
    lowered_query = query.strip().lower()
    lowered_candidate = candidate.strip().lower()
    if not lowered_query:
        return 0
    if lowered_candidate.startswith(lowered_query):
        return 0
    if lowered_query in lowered_candidate:
        return 10 + lowered_candidate.index(lowered_query)
    position = 0
    gaps = 0
    for char in lowered_query:
        found = lowered_candidate.find(char, position)
        if found < 0:
            return None
        gaps += max(0, found - position)
        position = found + 1
    return 100 + gaps + len(lowered_candidate)


def _highlight_fuzzy_match(query: str, candidate: str) -> str:
    clean_query = query.strip().lower()
    if not clean_query:
        return candidate
    lowered_candidate = candidate.lower()
    substring_index = lowered_candidate.find(clean_query)
    if substring_index >= 0:
        end = substring_index + len(clean_query)
        return f"{candidate[:substring_index]}[{candidate[substring_index:end]}]{candidate[end:]}"
    positions: list[int] = []
    search_from = 0
    for char in clean_query:
        found = lowered_candidate.find(char, search_from)
        if found < 0:
            return candidate
        positions.append(found)
        search_from = found + 1
    highlighted: list[str] = []
    position_set = set(positions)
    in_match = False
    for index, char in enumerate(candidate):
        if index in position_set and not in_match:
            highlighted.append("[")
            in_match = True
        if index not in position_set and in_match:
            highlighted.append("]")
            in_match = False
        highlighted.append(char)
    if in_match:
        highlighted.append("]")
    return "".join(highlighted)


def _wrap_description(text: str, *, width: int = 88, initial_indent: str = "  ", subsequent_indent: str = "  ") -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [initial_indent.rstrip()]


def _slash_palette_report(config: AgentConfig, prefix: str = "") -> dict[str, object]:
    main = _main()
    lowered = prefix.strip().lower()
    specs = command_specs_by_query(lowered)
    prefs = main._load_model_preferences(config)
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
                "match": _slash_match_report(spec, lowered),
            }
        )
    return {
        "command": "slash",
        "schema": json_schema("slash"),
        "prefix": f"/{lowered}" if lowered else "/",
        "context": {
            "enabled_providers": list(prefs.enabled_models or []),
            "active_accounts": active_accounts,
            "blocked_providers": blocked,
        },
        "no_match": not entries,
        "message": "" if entries else "No slash commands match the query. Use /slash to browse all commands.",
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
        lines.append(f"- message: {report['message']}")
        return "\n".join(lines)
    for item in entries[:20]:
        aliases = f" aliases={','.join(item['aliases'])}" if item["aliases"] else ""
        json_hint = " json" if item["json"] else ""
        hint = f" hint={item['hint']}" if item["hint"] else ""
        lines.append(f"- /{item['usage']}{aliases}{json_hint}{hint}")
        for line in _wrap_description(str(item["description"])):
            lines.append(line)
        match = item.get("match", {})
        if isinstance(match, dict) and match.get("query"):
            lines.append(f"  match: {match.get('highlight', '')}")
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
    main = _main()
    if input_stream is None or output_stream is None:
        return "Slash chooser unavailable without an interactive input/output stream."
    entries = list(_slash_palette_report(config, query)["entries"])[:20]
    if not entries:
        return "No slash commands match the query.\nUse /slash to browse all commands or try a broader query."
    options = [
        (str(item["usage"]), f"/{item['usage']} - {item['description']}")
        for item in entries
        if isinstance(item, dict)
    ]
    selected = main._prompt_menu_choice(
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
        lines.append("- message: Use /slash to browse all commands or try a broader query.")
        return "\n".join(lines)
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"{index}. /{item['usage']}")
        for line in _wrap_description(str(item["description"]), initial_indent="   ", subsequent_indent="   "):
            lines.append(line)
        match = item.get("match", {})
        if isinstance(match, dict) and match.get("query"):
            lines.append(f"   match: {match.get('highlight', '')}")
    lines.append("- note: use interactive /slash choose to select one item.")
    return "\n".join(lines)


def _help_json_report(topic: str | None = None) -> dict[str, object]:
    return help_topic_report(topic)


def _interactive_help_topic(topic: str) -> str:
    lines = help_topic_lines(topic)
    if lines is None:
        return _interactive_help_overview() + f"\n\nUnknown help topic: {topic}"
    return "\n".join(lines)
