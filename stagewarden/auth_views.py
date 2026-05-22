from __future__ import annotations

import shutil
import subprocess

from .textcodec import loads_text

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

