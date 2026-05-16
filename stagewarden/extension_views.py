from __future__ import annotations

from .config import AgentConfig
from .extensions import discover_extensions, scaffold_extension
from . import project_handoff_views as _project_handoff_views


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
        _project_handoff_views._record_handoff_action(
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
