from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timedelta
from pathlib import Path

from .provider_registry import SUPPORTED_MODELS, canonicalize_model_variant
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


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
    variant_by_model: dict[str, str] | None = None
    accounts_by_model: dict[str, list[str]] | None = None
    active_account_by_model: dict[str, str] | None = None
    blocked_until_by_account: dict[str, str] | None = None
    env_var_by_account: dict[str, str] | None = None

    @classmethod
    def default(cls) -> "ModelPreferences":
        return cls(
            enabled_models=list(SUPPORTED_MODELS),
            preferred_model=None,
            blocked_until_by_model={},
            variant_by_model={},
            accounts_by_model={},
            active_account_by_model={},
            blocked_until_by_account={},
            env_var_by_account={},
        )

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
        variants: dict[str, str] = {}
        for model, variant in (self.variant_by_model or {}).items():
            if model not in SUPPORTED_MODELS:
                continue
            try:
                variants[str(model)] = canonicalize_model_variant(str(model), str(variant))
            except ValueError:
                continue
        accounts_by_model: dict[str, list[str]] = {}
        for model, accounts in (self.accounts_by_model or {}).items():
            if model not in SUPPORTED_MODELS:
                continue
            normalized_accounts = []
            for account in accounts:
                account_name = str(account).strip()
                if self._is_valid_account_name(account_name) and account_name not in normalized_accounts:
                    normalized_accounts.append(account_name)
            if normalized_accounts:
                accounts_by_model[model] = normalized_accounts
        active_account_by_model = {
            str(model): str(account)
            for model, account in (self.active_account_by_model or {}).items()
            if model in accounts_by_model and str(account) in accounts_by_model[model]
        }
        blocked_until_by_account = {
            str(key): str(until)
            for key, until in (self.blocked_until_by_account or {}).items()
            if self._is_valid_account_key(key) and self._is_valid_date(until)
        }
        env_var_by_account = {
            str(key): str(value)
            for key, value in (self.env_var_by_account or {}).items()
            if self._is_valid_account_key(key) and self._is_valid_env_name(str(value))
        }
        self.enabled_models = enabled
        self.preferred_model = preferred
        self.blocked_until_by_model = blocked
        self.variant_by_model = variants
        self.accounts_by_model = accounts_by_model
        self.active_account_by_model = active_account_by_model
        self.blocked_until_by_account = blocked_until_by_account
        self.env_var_by_account = env_var_by_account
        return self

    def is_blocked(self, model: str, at_time: datetime | None = None) -> bool:
        raw = (self.blocked_until_by_model or {}).get(model)
        if not raw:
            return False
        check_time = at_time or datetime.now()
        return check_time <= datetime.fromisoformat(raw)

    def active_models(self, at_time: datetime | None = None) -> list[str]:
        return [model for model in self.enabled_models if not self.is_blocked(model, at_time=at_time)]

    def add_account(self, model: str, account: str, env_var: str | None = None) -> None:
        self._validate_model(model)
        self._validate_account(account)
        self.accounts_by_model = dict(self.accounts_by_model or {})
        accounts = list(self.accounts_by_model.get(model, []))
        if account not in accounts:
            accounts.append(account)
        self.accounts_by_model[model] = accounts
        self.active_account_by_model = dict(self.active_account_by_model or {})
        self.active_account_by_model.setdefault(model, account)
        if env_var:
            self.set_account_env(model, account, env_var)
        self.normalize()

    def set_variant(self, model: str, variant: str) -> None:
        self._validate_model(model)
        self.variant_by_model = dict(self.variant_by_model or {})
        self.variant_by_model[model] = canonicalize_model_variant(model, variant)
        self.normalize()

    def clear_variant(self, model: str) -> None:
        self._validate_model(model)
        self.variant_by_model = dict(self.variant_by_model or {})
        self.variant_by_model.pop(model, None)
        self.normalize()

    def variant_for_model(self, model: str) -> str | None:
        self._validate_model(model)
        return (self.variant_by_model or {}).get(model)

    def remove_account(self, model: str, account: str) -> None:
        self._validate_model(model)
        self.accounts_by_model = dict(self.accounts_by_model or {})
        accounts = [item for item in self.accounts_by_model.get(model, []) if item != account]
        if accounts:
            self.accounts_by_model[model] = accounts
        else:
            self.accounts_by_model.pop(model, None)
        self.active_account_by_model = dict(self.active_account_by_model or {})
        if self.active_account_by_model.get(model) == account:
            if accounts:
                self.active_account_by_model[model] = accounts[0]
            else:
                self.active_account_by_model.pop(model, None)
        key = account_key(model, account)
        self.blocked_until_by_account = dict(self.blocked_until_by_account or {})
        self.blocked_until_by_account.pop(key, None)
        self.env_var_by_account = dict(self.env_var_by_account or {})
        self.env_var_by_account.pop(key, None)
        self.normalize()

    def set_active_account(self, model: str, account: str | None) -> None:
        self._validate_model(model)
        self.active_account_by_model = dict(self.active_account_by_model or {})
        if account is None:
            self.active_account_by_model.pop(model, None)
            self.normalize()
            return
        if account not in (self.accounts_by_model or {}).get(model, []):
            raise ValueError(f"Account '{account}' is not configured for model '{model}'.")
        self.active_account_by_model[model] = account
        self.normalize()

    def set_account_env(self, model: str, account: str, env_var: str) -> None:
        self._validate_model(model)
        self._validate_account(account)
        if not self._is_valid_env_name(env_var):
            raise ValueError("Environment variable name must contain only letters, numbers, and underscores.")
        self.env_var_by_account = dict(self.env_var_by_account or {})
        self.env_var_by_account[account_key(model, account)] = env_var

    def account_for_model(self, model: str, at_time: datetime | None = None) -> str | None:
        accounts = list((self.accounts_by_model or {}).get(model, []))
        if not accounts:
            return None
        preferred = (self.active_account_by_model or {}).get(model)
        if preferred in accounts and not self.is_account_blocked(model, preferred, at_time=at_time):
            return preferred
        for account in accounts:
            if not self.is_account_blocked(model, account, at_time=at_time):
                return account
        return None

    def next_account_for_model(self, model: str, current: str | None, at_time: datetime | None = None) -> str | None:
        accounts = list((self.accounts_by_model or {}).get(model, []))
        for account in accounts:
            if account != current and not self.is_account_blocked(model, account, at_time=at_time):
                return account
        return None

    def is_account_blocked(self, model: str, account: str, at_time: datetime | None = None) -> bool:
        raw = (self.blocked_until_by_account or {}).get(account_key(model, account))
        if not raw:
            return False
        check_time = at_time or datetime.now()
        return check_time <= datetime.fromisoformat(raw)

    def block_account(self, model: str, account: str, until: str) -> None:
        self._validate_model(model)
        self._validate_account(account)
        if not self._is_valid_date(until):
            raise ValueError("Invalid date/time. Use YYYY-MM-DDTHH:MM.")
        self.blocked_until_by_account = dict(self.blocked_until_by_account or {})
        self.blocked_until_by_account[account_key(model, account)] = until

    def unblock_account(self, model: str, account: str) -> None:
        self.blocked_until_by_account = dict(self.blocked_until_by_account or {})
        self.blocked_until_by_account.pop(account_key(model, account), None)

    def as_dict(self) -> dict[str, object]:
        return {
            "_format": "stagewarden_model_preferences",
            "_version": 4,
            "enabled_models": list(self.enabled_models),
            "preferred_model": self.preferred_model,
            "blocked_until_by_model": dict(self.blocked_until_by_model or {}),
            "variant_by_model": dict(self.variant_by_model or {}),
            "accounts_by_model": {model: list(accounts) for model, accounts in (self.accounts_by_model or {}).items()},
            "active_account_by_model": dict(self.active_account_by_model or {}),
            "blocked_until_by_account": dict(self.blocked_until_by_account or {}),
            "env_var_by_account": dict(self.env_var_by_account or {}),
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
            variant_by_model={str(key): str(value) for key, value in payload.get("variant_by_model", {}).items()},
            accounts_by_model={
                str(key): [str(item) for item in value]
                for key, value in payload.get("accounts_by_model", {}).items()
                if isinstance(value, list)
            },
            active_account_by_model={
                str(key): str(value) for key, value in payload.get("active_account_by_model", {}).items()
            },
            blocked_until_by_account={
                str(key): str(value) for key, value in payload.get("blocked_until_by_account", {}).items()
            },
            env_var_by_account={
                str(key): str(value) for key, value in payload.get("env_var_by_account", {}).items()
            },
        ).normalize()

    def _validate_model(self, model: str) -> None:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model '{model}'.")

    def _validate_account(self, account: str) -> None:
        if not self._is_valid_account_name(account):
            raise ValueError("Account name must contain only letters, numbers, dot, dash, and underscore.")

    @staticmethod
    def _is_valid_account_name(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", str(value)))

    @staticmethod
    def _is_valid_env_name(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(value)))

    @classmethod
    def _is_valid_account_key(cls, value: str) -> bool:
        model, separator, account = str(value).partition(":")
        return bool(separator and model in SUPPORTED_MODELS and cls._is_valid_account_name(account))

    @staticmethod
    def _is_valid_date(value: str) -> bool:
        try:
            datetime.fromisoformat(str(value))
            return True
        except ValueError:
            return False


def account_key(model: str, account: str) -> str:
    return f"{model}:{account}"
