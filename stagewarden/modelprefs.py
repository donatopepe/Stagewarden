from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timedelta
from pathlib import Path

from .provider_registry import SUPPORTED_MODELS, canonicalize_model_variant, provider_model_spec, provider_model_specs
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


PRINCE2_ROLE_LABELS: dict[str, str] = {
    "project_executive": "Project Executive",
    "senior_user": "Senior User",
    "senior_supplier": "Senior Supplier",
    "project_manager": "Project Manager",
    "team_manager": "Team Manager",
    "project_assurance": "Project Assurance",
    "project_support": "Project Support",
    "change_authority": "Change Authority",
}

PRINCE2_ROLE_IDS: tuple[str, ...] = tuple(PRINCE2_ROLE_LABELS.keys())


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


def classify_limit_reason(text: str | None, *, fallback: str | None = None) -> str | None:
    message = (text or "").strip().lower()
    if message:
        if "purchase more credits" in message or "credits" in message:
            return "credits_exhausted"
        if "rate limit" in message or "rate-limit" in message or "too many requests" in message:
            return "rate_limit"
        if "service unavailable" in message or "provider unavailable" in message or "temporarily unavailable" in message:
            return "provider_unavailable"
        if "usage limit" in message or "usage limited" in message or "try again at" in message or "retry at" in message:
            return "usage_limit"
    return fallback


def limit_snapshot_from_message(
    text: str,
    *,
    blocked_until: str | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    message = str(text or "").strip().replace("\n", " ")[:240]
    until = blocked_until or extract_blocked_until(message)
    reason = classify_limit_reason(message, fallback="unknown")
    return normalize_limit_snapshot(
        {
            "status": "blocked" if until else "available",
            "reason": reason,
            "blocked_until": until,
            "primary_window": _detect_limit_window(message),
            "secondary_window": _detect_secondary_limit_window(message),
            "credits": _detect_credit_state(message),
            "rate_limit_type": _detect_rate_limit_type(message, fallback=reason),
            "utilization": _extract_percentage(message),
            "overage_status": _detect_overage_status(message),
            "overage_resets_at": None,
            "overage_disabled_reason": _detect_overage_disabled_reason(message),
            "stale": False,
            "captured_at": (captured_at or datetime.now()).isoformat(timespec="minutes"),
            "raw_message": message,
        }
    )


def normalize_limit_snapshot(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "status",
        "reason",
        "blocked_until",
        "primary_window",
        "secondary_window",
        "credits",
        "rate_limit_type",
        "utilization",
        "overage_status",
        "overage_resets_at",
        "overage_disabled_reason",
        "stale",
        "captured_at",
        "raw_message",
    }
    normalized: dict[str, object] = {}
    for key in allowed:
        value = raw.get(key)
        if value is None:
            normalized[key] = None
            continue
        if key == "stale":
            normalized[key] = bool(value)
            continue
        if key == "utilization":
            normalized[key] = _normalize_percentage(value)
            continue
        if key in {"blocked_until", "overage_resets_at", "captured_at"} and not _valid_iso_date(value):
            normalized[key] = None
            continue
        normalized[key] = str(value).strip().replace("\n", " ")[:240] or None
    if normalized.get("status") not in {"available", "blocked", "limited", "unknown"}:
        normalized["status"] = "blocked" if normalized.get("blocked_until") else "unknown"
    return normalized


def _detect_limit_window(message: str) -> str | None:
    lowered = message.lower()
    if "5-hour" in lowered or "five-hour" in lowered or "5 hour" in lowered or "five hour" in lowered:
        return "five_hour"
    if "7-day" in lowered or "seven-day" in lowered or "weekly" in lowered or "week" in lowered:
        return "seven_day"
    if "daily" in lowered or "24-hour" in lowered or "24 hour" in lowered:
        return "daily"
    return None


def _detect_secondary_limit_window(message: str) -> str | None:
    lowered = message.lower()
    if "sonnet" in lowered:
        return "sonnet"
    if "opus" in lowered:
        return "opus"
    if "gpt-5" in lowered:
        return "gpt-5"
    return None


def _detect_rate_limit_type(message: str, *, fallback: str | None) -> str | None:
    primary = _detect_limit_window(message)
    secondary = _detect_secondary_limit_window(message)
    if primary and secondary:
        return f"{primary}_{secondary}"
    if primary:
        return primary
    lowered = message.lower()
    if "overage" in lowered or "extra usage" in lowered:
        return "overage"
    return fallback


def _detect_credit_state(message: str) -> str | None:
    lowered = message.lower()
    if "purchase more credits" in lowered or "out of credits" in lowered or "no credits" in lowered:
        return "exhausted"
    if "credits" in lowered:
        return "limited"
    return None


def _detect_overage_status(message: str) -> str | None:
    lowered = message.lower()
    if "overage" not in lowered and "extra usage" not in lowered:
        return None
    if "disabled" in lowered or "not enabled" in lowered:
        return "disabled"
    if "enabled" in lowered:
        return "enabled"
    return "mentioned"


def _detect_overage_disabled_reason(message: str) -> str | None:
    lowered = message.lower()
    if "purchase more credits" in lowered or "out of credits" in lowered:
        return "out_of_credits"
    if "usage limit" in lowered:
        return "usage_limit"
    if "not enabled" in lowered:
        return "not_enabled"
    return None


def _extract_percentage(message: str) -> float | None:
    match = re.search(r"\b([0-9]{1,3})(?:\.[0-9]+)?\s*%", message)
    if not match:
        return None
    return _normalize_percentage(match.group(0).replace("%", ""))


def _normalize_percentage(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    if number < 0 or number > 100:
        return None
    return number


def _valid_iso_date(value: object) -> bool:
    try:
        datetime.fromisoformat(str(value))
        return True
    except ValueError:
        return False


@dataclass(slots=True)
class ModelPreferences:
    enabled_models: list[str]
    preferred_model: str | None = None
    blocked_until_by_model: dict[str, str] | None = None
    last_limit_message_by_model: dict[str, str] | None = None
    variant_by_model: dict[str, str] | None = None
    accounts_by_model: dict[str, list[str]] | None = None
    active_account_by_model: dict[str, str] | None = None
    blocked_until_by_account: dict[str, str] | None = None
    last_limit_message_by_account: dict[str, str] | None = None
    env_var_by_account: dict[str, str] | None = None
    provider_limit_snapshot_by_model: dict[str, dict[str, object]] | None = None
    provider_limit_snapshot_by_account: dict[str, dict[str, object]] | None = None
    params_by_model: dict[str, dict[str, str]] | None = None
    prince2_roles: dict[str, dict[str, object]] | None = None

    @classmethod
    def default(cls) -> "ModelPreferences":
        return cls(
            enabled_models=list(SUPPORTED_MODELS),
            preferred_model=None,
            blocked_until_by_model={},
            last_limit_message_by_model={},
            variant_by_model={},
            accounts_by_model={},
            active_account_by_model={},
            blocked_until_by_account={},
            last_limit_message_by_account={},
            env_var_by_account={},
            provider_limit_snapshot_by_model={},
            provider_limit_snapshot_by_account={},
            params_by_model={},
            prince2_roles={},
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
        last_limit_message_by_model = {
            str(model): str(message).strip()[:240]
            for model, message in (self.last_limit_message_by_model or {}).items()
            if model in SUPPORTED_MODELS and str(message).strip()
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
        last_limit_message_by_account = {
            str(key): str(message).strip()[:240]
            for key, message in (self.last_limit_message_by_account or {}).items()
            if self._is_valid_account_key(key) and str(message).strip()
        }
        env_var_by_account = {
            str(key): str(value)
            for key, value in (self.env_var_by_account or {}).items()
            if self._is_valid_account_key(key) and self._is_valid_env_name(str(value))
        }
        provider_limit_snapshot_by_model = {
            str(model): normalize_limit_snapshot(snapshot)
            for model, snapshot in (self.provider_limit_snapshot_by_model or {}).items()
            if model in SUPPORTED_MODELS and normalize_limit_snapshot(snapshot)
        }
        provider_limit_snapshot_by_account = {
            str(key): normalize_limit_snapshot(snapshot)
            for key, snapshot in (self.provider_limit_snapshot_by_account or {}).items()
            if self._is_valid_account_key(key) and normalize_limit_snapshot(snapshot)
        }
        params_by_model = {
            str(model): self._normalize_model_params(str(model), params)
            for model, params in (self.params_by_model or {}).items()
            if model in SUPPORTED_MODELS and self._normalize_model_params(str(model), params)
        }
        prince2_roles = {
            str(role): normalized
            for role, assignment in (self.prince2_roles or {}).items()
            if role in PRINCE2_ROLE_IDS
            for normalized in [self._normalize_role_assignment(str(role), assignment)]
            if normalized
        }
        self.enabled_models = enabled
        self.preferred_model = preferred
        self.blocked_until_by_model = blocked
        self.last_limit_message_by_model = last_limit_message_by_model
        self.variant_by_model = variants
        self.accounts_by_model = accounts_by_model
        self.active_account_by_model = active_account_by_model
        self.blocked_until_by_account = blocked_until_by_account
        self.last_limit_message_by_account = last_limit_message_by_account
        self.env_var_by_account = env_var_by_account
        self.provider_limit_snapshot_by_model = provider_limit_snapshot_by_model
        self.provider_limit_snapshot_by_account = provider_limit_snapshot_by_account
        self.params_by_model = params_by_model
        self.prince2_roles = prince2_roles
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

    def params_for_model(self, model: str) -> dict[str, str]:
        self._validate_model(model)
        return dict((self.params_by_model or {}).get(model, {}))

    def set_model_param(self, model: str, key: str, value: str) -> None:
        self._validate_model(model)
        normalized = self._normalize_single_param(model, key, value)
        self.params_by_model = dict(self.params_by_model or {})
        params = dict(self.params_by_model.get(model, {}))
        params[normalized[0]] = normalized[1]
        self.params_by_model[model] = params
        self.normalize()

    def clear_model_param(self, model: str, key: str) -> None:
        self._validate_model(model)
        self.params_by_model = dict(self.params_by_model or {})
        params = dict(self.params_by_model.get(model, {}))
        params.pop(str(key).strip(), None)
        if params:
            self.params_by_model[model] = params
        else:
            self.params_by_model.pop(model, None)
        self.normalize()

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
        self.last_limit_message_by_account = dict(self.last_limit_message_by_account or {})
        self.last_limit_message_by_account.pop(key, None)
        self.provider_limit_snapshot_by_account = dict(self.provider_limit_snapshot_by_account or {})
        self.provider_limit_snapshot_by_account.pop(key, None)
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
        self.last_limit_message_by_account = dict(self.last_limit_message_by_account or {})
        self.last_limit_message_by_account.pop(account_key(model, account), None)
        self.provider_limit_snapshot_by_account = dict(self.provider_limit_snapshot_by_account or {})
        self.provider_limit_snapshot_by_account.pop(account_key(model, account), None)

    def set_model_limit_snapshot(self, model: str, snapshot: dict[str, object]) -> None:
        self._validate_model(model)
        normalized = normalize_limit_snapshot(snapshot)
        if not normalized:
            return
        self.provider_limit_snapshot_by_model = dict(self.provider_limit_snapshot_by_model or {})
        self.provider_limit_snapshot_by_model[model] = normalized

    def set_account_limit_snapshot(self, model: str, account: str, snapshot: dict[str, object]) -> None:
        self._validate_model(model)
        self._validate_account(account)
        normalized = normalize_limit_snapshot(snapshot)
        if not normalized:
            return
        self.provider_limit_snapshot_by_account = dict(self.provider_limit_snapshot_by_account or {})
        self.provider_limit_snapshot_by_account[account_key(model, account)] = normalized

    def prince2_role_assignment(self, role: str) -> dict[str, object]:
        self._validate_prince2_role(role)
        return dict((self.prince2_roles or {}).get(role, {}))

    def set_prince2_role_assignment(
        self,
        role: str,
        *,
        mode: str,
        provider: str,
        provider_model: str,
        params: dict[str, str] | None = None,
        account: str | None = None,
        source: str = "manual",
    ) -> None:
        self._validate_prince2_role(role)
        self._validate_model(provider)
        clean_mode = str(mode).strip().lower()
        if clean_mode not in {"auto", "manual"}:
            raise ValueError("Role mode must be 'auto' or 'manual'.")
        if provider not in self.enabled_models:
            self.enabled_models.append(provider)
        canonical_model = canonicalize_model_variant(provider, provider_model)
        normalized_params = self._normalize_role_params(provider, canonical_model, params or {})
        if account is not None and account not in (self.accounts_by_model or {}).get(provider, []):
            raise ValueError(f"Account '{account}' is not configured for model '{provider}'.")
        self.prince2_roles = dict(self.prince2_roles or {})
        self.prince2_roles[role] = {
            "role": role,
            "label": PRINCE2_ROLE_LABELS[role],
            "mode": clean_mode,
            "provider": provider,
            "provider_model": canonical_model,
            "params": normalized_params,
            "account": account,
            "source": str(source).strip() or clean_mode,
        }
        self.normalize()

    def clear_prince2_role_assignment(self, role: str) -> None:
        self._validate_prince2_role(role)
        self.prince2_roles = dict(self.prince2_roles or {})
        self.prince2_roles.pop(role, None)
        self.normalize()

    def propose_prince2_roles(self) -> dict[str, dict[str, object]]:
        active_models = self.active_models()
        available = active_models or list(self.enabled_models) or list(SUPPORTED_MODELS)
        proposals: dict[str, dict[str, object]] = {}
        for role in PRINCE2_ROLE_IDS:
            provider = self._proposed_provider_for_role(role, available)
            provider_model = self._default_provider_model_for_role(provider, role)
            params = self._default_provider_params_for_role(provider, provider_model, role)
            account = self.account_for_model(provider)
            proposals[role] = {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "mode": "auto",
                "provider": provider,
                "provider_model": provider_model,
                "params": params,
                "account": account,
                "source": "auto_proposal",
            }
        return proposals

    def apply_prince2_role_proposal(self) -> dict[str, dict[str, object]]:
        proposals = self.propose_prince2_roles()
        for role, assignment in proposals.items():
            self.set_prince2_role_assignment(
                role,
                mode="auto",
                provider=str(assignment["provider"]),
                provider_model=str(assignment["provider_model"]),
                params=dict(assignment.get("params", {})),
                account=assignment.get("account"),
                source="auto_proposal",
            )
        return proposals

    def as_dict(self) -> dict[str, object]:
        return {
            "_format": "stagewarden_model_preferences",
            "_version": 7,
            "enabled_models": list(self.enabled_models),
            "preferred_model": self.preferred_model,
            "blocked_until_by_model": dict(self.blocked_until_by_model or {}),
            "last_limit_message_by_model": dict(self.last_limit_message_by_model or {}),
            "variant_by_model": dict(self.variant_by_model or {}),
            "accounts_by_model": {model: list(accounts) for model, accounts in (self.accounts_by_model or {}).items()},
            "active_account_by_model": dict(self.active_account_by_model or {}),
            "blocked_until_by_account": dict(self.blocked_until_by_account or {}),
            "last_limit_message_by_account": dict(self.last_limit_message_by_account or {}),
            "env_var_by_account": dict(self.env_var_by_account or {}),
            "provider_limit_snapshot_by_model": dict(self.provider_limit_snapshot_by_model or {}),
            "provider_limit_snapshot_by_account": dict(self.provider_limit_snapshot_by_account or {}),
            "params_by_model": {model: dict(params) for model, params in (self.params_by_model or {}).items()},
            "prince2_roles": {role: dict(assignment) for role, assignment in (self.prince2_roles or {}).items()},
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
            last_limit_message_by_model={
                str(key): str(value) for key, value in payload.get("last_limit_message_by_model", {}).items()
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
            last_limit_message_by_account={
                str(key): str(value) for key, value in payload.get("last_limit_message_by_account", {}).items()
            },
            env_var_by_account={
                str(key): str(value) for key, value in payload.get("env_var_by_account", {}).items()
            },
            provider_limit_snapshot_by_model={
                str(key): value
                for key, value in payload.get("provider_limit_snapshot_by_model", {}).items()
                if isinstance(value, dict)
            },
            provider_limit_snapshot_by_account={
                str(key): value
                for key, value in payload.get("provider_limit_snapshot_by_account", {}).items()
                if isinstance(value, dict)
            },
            params_by_model={
                str(key): {str(k): str(v) for k, v in value.items()}
                for key, value in payload.get("params_by_model", {}).items()
                if isinstance(value, dict)
            },
            prince2_roles={
                str(key): value
                for key, value in payload.get("prince2_roles", {}).items()
                if isinstance(value, dict)
            },
        ).normalize()

    def _validate_model(self, model: str) -> None:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model '{model}'.")

    def _validate_account(self, account: str) -> None:
        if not self._is_valid_account_name(account):
            raise ValueError("Account name must contain only letters, numbers, dot, dash, and underscore.")

    def _normalize_model_params(self, model: str, raw: object) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, value in raw.items():
            try:
                name, clean = self._normalize_single_param(model, str(key), str(value))
            except ValueError:
                continue
            normalized[name] = clean
        return normalized

    def _normalize_single_param(self, model: str, key: str, value: str) -> tuple[str, str]:
        clean_key = str(key).strip()
        clean_value = str(value).strip()
        if clean_key != "reasoning_effort":
            raise ValueError(f"Unsupported model parameter '{clean_key}'.")
        provider_model = self.variant_for_model(model) or provider_model_spec(model, "provider-default")
        active_provider_model = self.variant_for_model(model) or "provider-default"
        spec = provider_model_spec(model, active_provider_model)
        if spec is None or clean_value not in spec.reasoning_efforts:
            allowed = [] if spec is None else list(spec.reasoning_efforts)
            raise ValueError(
                f"Unsupported reasoning_effort '{clean_value}' for {model}:{active_provider_model}. "
                f"Allowed: {', '.join(allowed) or 'none'}"
            )
        return clean_key, clean_value

    def _normalize_role_assignment(self, role: str, raw: object) -> dict[str, object]:
        if not isinstance(raw, dict):
            return {}
        provider = str(raw.get("provider", "")).strip()
        provider_model = str(raw.get("provider_model", "")).strip()
        if provider not in SUPPORTED_MODELS or not provider_model:
            return {}
        try:
            canonical_model = canonicalize_model_variant(provider, provider_model)
        except ValueError:
            return {}
        mode = str(raw.get("mode", "manual")).strip().lower()
        if mode not in {"auto", "manual"}:
            mode = "manual"
        params = self._normalize_role_params(provider, canonical_model, raw.get("params", {}))
        account = raw.get("account")
        clean_account = None
        if account is not None and str(account) in (self.accounts_by_model or {}).get(provider, []):
            clean_account = str(account)
        return {
            "role": role,
            "label": PRINCE2_ROLE_LABELS[role],
            "mode": mode,
            "provider": provider,
            "provider_model": canonical_model,
            "params": params,
            "account": clean_account,
            "source": str(raw.get("source", mode)).strip() or mode,
        }

    def _validate_prince2_role(self, role: str) -> None:
        if role not in PRINCE2_ROLE_IDS:
            raise ValueError(f"Unsupported PRINCE2 role '{role}'.")

    def _normalize_role_params(self, provider: str, provider_model: str, raw: object) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        spec = provider_model_spec(provider, provider_model)
        normalized: dict[str, str] = {}
        for key, value in raw.items():
            clean_key = str(key).strip()
            clean_value = str(value).strip()
            if clean_key != "reasoning_effort":
                continue
            if spec is None or clean_value not in spec.reasoning_efforts:
                continue
            normalized[clean_key] = clean_value
        return normalized

    def _proposed_provider_for_role(self, role: str, available: list[str]) -> str:
        preference_order = {
            "project_executive": ("chatgpt", "openai", "claude", "cheap", "local"),
            "senior_user": ("cheap", "chatgpt", "openai", "claude", "local"),
            "senior_supplier": ("claude", "openai", "chatgpt", "cheap", "local"),
            "project_manager": ("chatgpt", "openai", "claude", "cheap", "local"),
            "team_manager": ("local", "cheap", "chatgpt", "openai", "claude"),
            "project_assurance": ("cheap", "local", "chatgpt", "openai", "claude"),
            "project_support": ("local", "cheap", "chatgpt", "openai", "claude"),
            "change_authority": ("chatgpt", "cheap", "openai", "claude", "local"),
        }
        for candidate in preference_order.get(role, SUPPORTED_MODELS):
            if candidate in available:
                return candidate
        return available[0]

    def _default_provider_model_for_role(self, provider: str, role: str) -> str:
        role_preference = {
            "project_executive": {
                "chatgpt": "gpt-5.4",
                "openai": "gpt-5.4",
                "claude": "sonnet",
            },
            "senior_user": {"chatgpt": "gpt-5.4-mini", "openai": "gpt-5.4-mini", "claude": "haiku"},
            "senior_supplier": {"chatgpt": "gpt-5.3-codex", "openai": "gpt-5.3-codex", "claude": "sonnet"},
            "project_manager": {"chatgpt": "gpt-5.3-codex", "openai": "gpt-5.3-codex", "claude": "sonnet"},
            "team_manager": {"chatgpt": "gpt-5.1-codex-mini", "openai": "gpt-5.1-codex-mini", "claude": "haiku"},
            "project_assurance": {"chatgpt": "gpt-5.4-mini", "openai": "gpt-5.4-mini", "claude": "haiku"},
            "project_support": {"chatgpt": "gpt-5.4-nano", "openai": "gpt-5.4-nano", "claude": "haiku"},
            "change_authority": {"chatgpt": "gpt-5.4", "openai": "gpt-5.4", "claude": "sonnet"},
        }
        candidate = role_preference.get(role, {}).get(provider)
        if candidate:
            try:
                return canonicalize_model_variant(provider, candidate)
            except ValueError:
                pass
        specs = provider_model_specs(provider)
        if not specs:
            return "provider-default"
        return specs[0].id

    def _default_provider_params_for_role(self, provider: str, provider_model: str, role: str) -> dict[str, str]:
        spec = provider_model_spec(provider, provider_model)
        if spec is None or not spec.reasoning_efforts:
            return {}
        preferred_effort = {
            "project_executive": "high",
            "senior_user": "medium",
            "senior_supplier": "high",
            "project_manager": "high",
            "team_manager": "medium",
            "project_assurance": "medium",
            "project_support": "low",
            "change_authority": "high",
        }.get(role, spec.reasoning_default or spec.reasoning_efforts[0])
        if preferred_effort not in spec.reasoning_efforts:
            preferred_effort = spec.reasoning_default or spec.reasoning_efforts[0]
        return {"reasoning_effort": preferred_effort}

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
