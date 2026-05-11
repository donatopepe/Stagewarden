from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .model_catalog import catalog_entry_for_provider_model, load_ai_models_catalog
from .provider_registry import SUPPORTED_MODELS, provider_model_preset, provider_model_specs


@dataclass(frozen=True, slots=True)
class RouteRecommendation:
    provider: str
    provider_model: str | None
    score: float
    rationale: str


class ModelRouter:
    CORE_ORDER = ("cheap", "chatgpt", "openai", "claude", "local")
    ORDER = tuple(dict.fromkeys((*CORE_ORDER, *SUPPORTED_MODELS)))

    def __init__(self) -> None:
        self.enabled_models = set(self.ORDER)
        self.preferred_model: str | None = None
        self.blocked_until_by_model: dict[str, str] = {}

    def configure(
        self,
        *,
        enabled_models: list[str] | tuple[str, ...],
        preferred_model: str | None = None,
        blocked_until_by_model: dict[str, str] | None = None,
    ) -> None:
        enabled = [item for item in enabled_models if item in self.ORDER]
        self.enabled_models = set(enabled or self.ORDER)
        self.blocked_until_by_model = {
            str(key): str(value) for key, value in (blocked_until_by_model or {}).items() if key in self.ORDER
        }
        self.preferred_model = preferred_model if preferred_model in self._active_models() else None

    def enable_model(self, model: str) -> None:
        if model not in self.ORDER:
            raise ValueError(f"Unsupported model '{model}'.")
        self.enabled_models.add(model)

    def disable_model(self, model: str) -> None:
        if model not in self.ORDER:
            raise ValueError(f"Unsupported model '{model}'.")
        if len(self.enabled_models) == 1 and model in self.enabled_models:
            raise ValueError("Cannot disable the last enabled model.")
        self.enabled_models.discard(model)
        if self.preferred_model == model:
            self.preferred_model = None

    def set_preferred_model(self, model: str | None) -> None:
        if model is None:
            self.preferred_model = None
            return
        if model not in self.enabled_models:
            raise ValueError(f"Model '{model}' is not enabled.")
        self.preferred_model = model

    def status(self) -> dict[str, object]:
        return {
            "enabled_models": [item for item in self.ORDER if item in self.enabled_models],
            "active_models": [item for item in self.ORDER if item in self._active_models()],
            "preferred_model": self.preferred_model,
            "blocked_until_by_model": dict(self.blocked_until_by_model),
        }

    def choose_model(self, task: str, step_text: str, failure_count: int = 0) -> str:
        if self.preferred_model and self.preferred_model in self._active_models():
            return self.preferred_model
        if failure_count >= 3:
            return self._best_available("claude")
        if failure_count >= 2:
            return self._best_available("openai")

        profile = self._task_profile(task, step_text)
        if profile["regulatory"]:
            return self.recommend_route(task, step_text, failure_count=failure_count).provider

        text = f"{task} {step_text}".lower()
        risky_tokens = ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security")
        if any(token in text for token in risky_tokens):
            return self._best_available("chatgpt")
        complexity = 0
        debug_tokens = ("debug", "failure", "bug", "traceback", "regression")
        complex_tokens = ("refactor", "complex", "architecture", "handoff", "planner", "executor")

        if len(text.split()) > 35:
            complexity += 1
        if any(token in text for token in debug_tokens):
            complexity += 2
        if any(token in text for token in complex_tokens):
            complexity += 1
        if any(token in text for token in ("test", "implement", "modify", "handoff", "router", "planner")):
            complexity += 1

        if any(token in text for token in debug_tokens) and any(token in text for token in ("complex", "traceback")):
            return self._best_available("chatgpt")
        if complexity <= 1:
            return self._best_available("cheap")
        if complexity <= 3:
            return self._best_available("chatgpt")
        return self._best_available("openai")

    def escalate(self, current: str) -> str:
        if current == "chatgpt":
            return self._best_available("openai")
        if current == "openai":
            return self._best_available("claude")
        return self._next_available_after(current, fallback="cheap")

    def fallback_for_api_failure(self, current: str) -> str:
        if current == "chatgpt":
            return self._best_available("openai")
        if current == "openai":
            return self._best_available("claude")
        if current == "claude":
            return self._best_available("local")
        if current == "cheap":
            return self._best_available("chatgpt")
        return self._next_available_after(current, fallback="local")

    def choose_variant(self, model: str, task: str, step_text: str, failure_count: int = 0) -> str | None:
        profile = self._task_profile(task, step_text)
        preset = self._variant_preset(profile, failure_count=failure_count)
        try:
            variant, _params = provider_model_preset(model, preset)
        except ValueError:
            return None
        return variant

    def recommend_route(self, task: str, step_text: str, failure_count: int = 0) -> RouteRecommendation:
        profile = self._task_profile(task, step_text)
        catalog = self._catalog()
        best: RouteRecommendation | None = None
        for provider in [item for item in self.ORDER if item in self._active_models()]:
            specs = self._provider_specs(provider)
            if not specs:
                continue
            best_variant: tuple[float, str] | None = None
            for spec in specs:
                variant_score = self._variant_score(provider, spec, profile, failure_count=failure_count, catalog=catalog)
                if best_variant is None or (variant_score, spec.id) > best_variant:
                    best_variant = (variant_score, spec.id)
            if best_variant is None:
                continue
            provider_score = self._provider_score(provider, profile, failure_count=failure_count, catalog=catalog)
            score = provider_score + best_variant[0]
            rationale = self._route_rationale(provider, best_variant[1], profile)
            candidate = RouteRecommendation(provider=provider, provider_model=best_variant[1], score=round(score, 3), rationale=rationale)
            if best is None or (candidate.score, candidate.provider, candidate.provider_model or "") > (best.score, best.provider, best.provider_model or ""):
                best = candidate
        if best is None:
            fallback = self._best_available("cheap")
            return RouteRecommendation(provider=fallback, provider_model=None, score=0.0, rationale="fallback to active provider")
        return best

    def _best_available(self, preferred: str) -> str:
        active_models = self._active_models()
        if preferred in active_models:
            return preferred
        try:
            preferred_index = self.ORDER.index(preferred)
        except ValueError:
            preferred_index = 0
        for index in range(preferred_index - 1, -1, -1):
            candidate = self.ORDER[index]
            if candidate in active_models:
                return candidate
        for candidate in self.ORDER[preferred_index + 1 :]:
            if candidate in active_models:
                return candidate
        return next(iter(active_models), self.ORDER[0])

    def _next_available_after(self, current: str, *, fallback: str) -> str:
        active_models = self._active_models()
        if current in self.ORDER:
            start = self.ORDER.index(current) + 1
            for candidate in self.ORDER[start:]:
                if candidate in active_models:
                    return candidate
        return self._best_available(fallback)

    def _task_profile(self, task: str, step_text: str) -> dict[str, object]:
        text = f"{task} {step_text}".lower()
        debug_tokens = ("debug", "failure", "bug", "traceback", "regression")
        complex_tokens = ("refactor", "complex", "architecture", "handoff", "planner", "executor")
        risky_tokens = ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security")
        planning_tokens = ("plan", "planner", "design", "architecture", "roadmap")
        regulatory_tokens = ("regulatory", "compliance", "audit", "lawful", "dpa", "dpia", "privacy", "records", "retention", "notice", "secure by design", "governance", "legal", "litigation", "discovery", "subpoena", "contract", "indemnity", "incident", "outage", "breach", "rollback", "vendor", "supplier", "third-party", "outsource", "multi-vendor", "dependency", "cascade", "crisis", "fallback", "supply chain", "logistics", "inventory", "procurement", "continuity", "board", "quorum", "authority", "executive")

        complexity = 0
        if len(text.split()) > 35:
            complexity += 1
        if any(token in text for token in debug_tokens):
            complexity += 2
        if any(token in text for token in complex_tokens):
            complexity += 1
        if any(token in text for token in ("test", "implement", "modify", "handoff", "router", "planner")):
            complexity += 1

        return {
            "text": text,
            "complexity": complexity,
            "debug": any(token in text for token in debug_tokens),
            "risky": any(token in text for token in risky_tokens),
            "planning": any(token in text for token in planning_tokens),
            "regulatory": any(token in text for token in regulatory_tokens),
        }

    def _catalog(self):
        try:
            return load_ai_models_catalog()
        except (OSError, ValueError, TypeError):
            return {}

    def _provider_specs(self, provider: str):
        try:
            return list(provider_model_specs(provider))
        except ValueError:
            return []

    def _variant_score(self, provider: str, spec, profile: dict[str, object], *, failure_count: int, catalog: dict[str, object]) -> float:
        entry = catalog_entry_for_provider_model(provider, spec.id, catalog) if catalog else None
        score = 0.0
        reasoning_default = str(getattr(spec, "reasoning_default", "") or "").lower()
        reasoning_efforts = {str(item).lower() for item in getattr(spec, "reasoning_efforts", ())}
        features = [str(item).lower() for item in (entry.get("features", []) if isinstance(entry, dict) else [])]
        intelligence_rank = entry.get("intelligence_rank") if isinstance(entry, dict) else None
        speed_rank = entry.get("speed_rank") if isinstance(entry, dict) else None
        blended = entry.get("blended_price_usd_per_1m_tokens") if isinstance(entry, dict) else None
        context_window = entry.get("context_window") if isinstance(entry, dict) else None

        if profile["regulatory"]:
            score += 3.0 if "structured_output" in features else 0.0
            score += 2.0 if "reasoning" in features else 0.0
            score += 1.5 if provider in {"openai", "claude"} else 0.5 if provider == "chatgpt" else 0.0
        if profile["planning"]:
            score += 2.5 if "reasoning" in features or reasoning_default == "high" or "high" in reasoning_efforts else 1.0
        if profile["debug"]:
            score += 2.0 if "tool_use" in features else 0.5
        if profile["risky"]:
            score += 1.5 if provider in {"openai", "claude", "chatgpt"} else 0.0
        if int(profile["complexity"]) >= 4:
            score += 1.5 if reasoning_default == "high" or "high" in reasoning_efforts else 0.5
        if int(profile["complexity"]) <= 1 and not profile["risky"] and not profile["regulatory"]:
            score += 2.0 if provider in {"cheap", "local"} else 0.5
        if failure_count >= 2:
            score += 1.5 if reasoning_default == "high" or "high" in reasoning_efforts else 0.75
        if intelligence_rank is not None:
            try:
                score += max(0.0, 5.0 - float(intelligence_rank) / 10.0)
            except (TypeError, ValueError):
                pass
        if speed_rank is not None and not profile["regulatory"]:
            try:
                score += max(0.0, 3.0 - float(speed_rank) / 20.0)
            except (TypeError, ValueError):
                pass
        if blended not in {None, "local"}:
            try:
                score -= min(float(blended), 10.0) / (2.0 if profile["regulatory"] else 4.0)
            except (TypeError, ValueError):
                pass
        if context_window is not None and int(profile["complexity"]) >= 3:
            try:
                score += min(float(context_window), 1_000_000.0) / 1_000_000.0
            except (TypeError, ValueError):
                pass
        if provider == "cheap":
            score += 0.5 if profile["regulatory"] or profile["risky"] else 1.5
        if provider == "local":
            score += 1.5 if int(profile["complexity"]) <= 1 and not profile["regulatory"] else 0.25
        return score

    def _provider_score(self, provider: str, profile: dict[str, object], *, failure_count: int, catalog: dict[str, object]) -> float:
        specs = self._provider_specs(provider)
        if not specs:
            return 0.0
        return max(
            self._variant_score(provider, spec, profile, failure_count=failure_count, catalog=catalog)
            for spec in specs
            if str(spec.id).strip()
        )

    def _route_rationale(self, provider: str, provider_model: str, profile: dict[str, object]) -> str:
        parts = [provider]
        if provider_model:
            parts.append(provider_model)
        if profile["regulatory"]:
            parts.append("regulatory")
        if profile["planning"]:
            parts.append("planning")
        if profile["debug"]:
            parts.append("debug")
        if profile["risky"]:
            parts.append("risky")
        return " / ".join(parts)

    def _variant_preset(self, profile: dict[str, object], *, failure_count: int) -> str:
        complexity = int(profile["complexity"])
        if profile["regulatory"]:
            if profile["planning"] or complexity >= 4 or failure_count >= 2:
                return "plan"
            return "deep"
        if profile["planning"] and complexity >= 3:
            return "plan"
        if profile["debug"] or profile["risky"] or complexity >= 4 or failure_count >= 2:
            return "deep"
        if complexity <= 1 and not profile["risky"]:
            return "fast"
        return "balanced"

    def _active_models(self) -> set[str]:
        now = datetime.now()
        active: set[str] = set()
        for model in self.enabled_models:
            blocked_until = self.blocked_until_by_model.get(model)
            if blocked_until:
                try:
                    if now <= datetime.fromisoformat(blocked_until):
                        continue
                except ValueError:
                    pass
            active.add(model)
        if not active:
            return set(self.enabled_models) or {self.ORDER[0]}
        return active
