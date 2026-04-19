from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


VALID_PERMISSION_MODES = ("default", "accept_edits", "plan", "auto", "dont_ask")


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    source: str
    message: str = ""


@dataclass(slots=True)
class PermissionSettings:
    default_mode: str = "default"
    allow: list[str] = field(default_factory=list)
    ask: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def normalize(self) -> "PermissionSettings":
        mode = (self.default_mode or "default").strip().lower().replace("-", "_")
        if mode not in VALID_PERMISSION_MODES:
            mode = "default"
        self.default_mode = mode
        self.allow = [item.strip() for item in self.allow if str(item).strip()]
        self.ask = [item.strip() for item in self.ask if str(item).strip()]
        self.deny = [item.strip() for item in self.deny if str(item).strip()]
        return self

    def as_dict(self) -> dict[str, object]:
        return {
            "permissions": {
                "defaultMode": self.default_mode,
                "allow": list(self.allow),
                "ask": list(self.ask),
                "deny": list(self.deny),
            }
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, dumps_ascii(self.as_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "PermissionSettings":
        if not path.exists():
            return cls()
        payload = loads_text(read_text_utf8(path))
        permissions = payload.get("permissions", {}) if isinstance(payload, dict) else {}
        if not isinstance(permissions, dict):
            permissions = {}
        return cls(
            default_mode=str(permissions.get("defaultMode", "default")),
            allow=[str(item) for item in permissions.get("allow", [])],
            ask=[str(item) for item in permissions.get("ask", [])],
            deny=[str(item) for item in permissions.get("deny", [])],
        ).normalize()

    def merged(self, override: "PermissionSettings | None" = None) -> "PermissionSettings":
        if override is None:
            return PermissionSettings(
                default_mode=self.default_mode,
                allow=list(self.allow),
                ask=list(self.ask),
                deny=list(self.deny),
            ).normalize()
        return PermissionSettings(
            default_mode=override.default_mode if override.default_mode else self.default_mode,
            allow=[*self.allow, *override.allow],
            ask=[*self.ask, *override.ask],
            deny=[*self.deny, *override.deny],
        ).normalize()


class PermissionPolicy:
    def __init__(self, settings: PermissionSettings | None = None) -> None:
        self.settings = (settings or PermissionSettings()).normalize()

    @classmethod
    def load(cls, path: Path, session_settings: PermissionSettings | None = None) -> "PermissionPolicy":
        return cls(PermissionSettings.load(path).merged(session_settings))

    def decide(self, capability: str, detail: str = "") -> PermissionDecision:
        subject = capability.strip().lower()
        detail_text = detail.strip().lower()

        for rule in self.settings.deny:
            if self._matches(rule, subject, detail_text):
                return PermissionDecision(False, f"deny:{rule}", "Denied by permission policy.")
        for rule in self.settings.ask:
            if self._matches(rule, subject, detail_text):
                return PermissionDecision(False, f"ask:{rule}", "Operation requires approval by permission policy.")
        for rule in self.settings.allow:
            if self._matches(rule, subject, detail_text):
                return PermissionDecision(True, f"allow:{rule}")

        mode = self.settings.default_mode
        if mode == "plan":
            if subject in {"shell:write", "file:write", "git:write"}:
                return PermissionDecision(False, "mode:plan", "Plan mode allows analysis only.")
            return PermissionDecision(True, "mode:plan")
        if mode == "dont_ask":
            if subject in {"shell:write", "file:write", "git:write"}:
                return PermissionDecision(False, "mode:dont_ask", "Operation denied unless explicitly allowed.")
            return PermissionDecision(True, "mode:dont_ask")
        if mode in {"default", "accept_edits", "auto"}:
            return PermissionDecision(True, f"mode:{mode}")
        return PermissionDecision(True, "mode:default")

    def _matches(self, rule: str, capability: str, detail: str) -> bool:
        raw = rule.strip().lower()
        if not raw:
            return False
        if ":" not in raw:
            return raw in {"*", capability, capability.split(":", 1)[0]}
        rule_capability, rule_detail = raw.split(":", 1)
        capability_family = capability.split(":", 1)[0]
        if rule_capability not in {"*", capability, capability_family}:
            return False
        if rule_detail in {"*", ""}:
            return True
        return detail.startswith(rule_detail)
