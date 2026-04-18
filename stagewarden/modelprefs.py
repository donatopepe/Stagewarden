from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timedelta
from pathlib import Path

from .handoff import MODEL_BACKENDS
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


SUPPORTED_MODELS = tuple(MODEL_BACKENDS.keys())


def extract_blocked_until(text: str, *, now: datetime | None = None) -> str | None:
    reference = now or datetime.now()
    patterns = (
        r"(?:blocked|unavailable|rate.?limited|quota|credits?).{0,80}?(?:until|until:|retry after|retry-after)\s+([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?)",
        r"(?:until|until:|retry after|retry-after)\s+([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        candidate = match.group(1).replace(" ", "T")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed.isoformat(timespec="minutes")
    time_match = re.search(
        r"(?:try again at|retry at|available at)\s+([0-9]{1,2}:[0-9]{2})\s*([AP]\.?M\.?)",
        text,
        flags=re.IGNORECASE,
    )
    if time_match:
        clock = time_match.group(1)
        meridiem = time_match.group(2).replace(".", "").upper()
        hour_text, minute_text = clock.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if meridiem == "PM" and hour != 12:
            hour += 12
        if meridiem == "AM" and hour == 12:
            hour = 0
        candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= reference:
            candidate += timedelta(days=1)
        return candidate.isoformat(timespec="minutes")
    return None


@dataclass(slots=True)
class ModelPreferences:
    enabled_models: list[str]
    preferred_model: str | None = None
    blocked_until_by_model: dict[str, str] | None = None

    @classmethod
    def default(cls) -> "ModelPreferences":
        return cls(enabled_models=list(SUPPORTED_MODELS), preferred_model=None, blocked_until_by_model={})

    def normalize(self) -> "ModelPreferences":
        enabled = [item for item in self.enabled_models if item in SUPPORTED_MODELS]
        if not enabled:
            enabled = list(SUPPORTED_MODELS)
        preferred = self.preferred_model if self.preferred_model in enabled else None
        blocked = {
            str(model): str(until)
            for model, until in (self.blocked_until_by_model or {}).items()
            if model in SUPPORTED_MODELS and self._is_valid_date(until)
        }
        self.enabled_models = enabled
        self.preferred_model = preferred
        self.blocked_until_by_model = blocked
        return self

    def is_blocked(self, model: str, at_time: datetime | None = None) -> bool:
        raw = (self.blocked_until_by_model or {}).get(model)
        if not raw:
            return False
        check_time = at_time or datetime.now()
        return check_time <= datetime.fromisoformat(raw)

    def active_models(self, at_time: datetime | None = None) -> list[str]:
        return [model for model in self.enabled_models if not self.is_blocked(model, at_time=at_time)]

    def as_dict(self) -> dict[str, object]:
        return {
            "_format": "stagewarden_model_preferences",
            "_version": 2,
            "enabled_models": list(self.enabled_models),
            "preferred_model": self.preferred_model,
            "blocked_until_by_model": dict(self.blocked_until_by_model or {}),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, dumps_ascii(self.as_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "ModelPreferences":
        if not path.exists():
            return cls.default()
        payload = loads_text(read_text_utf8(path))
        return cls(
            enabled_models=[str(item) for item in payload.get("enabled_models", [])],
            preferred_model=str(payload["preferred_model"]) if payload.get("preferred_model") else None,
            blocked_until_by_model={
                str(key): str(value) for key, value in payload.get("blocked_until_by_model", {}).items()
            },
        ).normalize()

    @staticmethod
    def _is_valid_date(value: str) -> bool:
        try:
            datetime.fromisoformat(str(value))
            return True
        except ValueError:
            return False
