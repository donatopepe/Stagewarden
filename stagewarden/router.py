from __future__ import annotations

from datetime import datetime

from .provider_registry import SUPPORTED_MODELS


class ModelRouter:
    ORDER = ("cheap", "chatgpt", "openai", "claude", "local")

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
        try:
            index = self.ORDER.index(current)
        except ValueError:
            return self._best_available("cheap")
        for candidate in self.ORDER[index + 1 :]:
            if candidate in self.enabled_models:
                return candidate
        return self._best_available(current)

    def fallback_for_api_failure(self, current: str) -> str:
        if current == "chatgpt":
            return self._best_available("openai")
        if current == "openai":
            return self._best_available("claude")
        if current == "claude":
            return self._best_available("local")
        if current == "cheap":
            return self._best_available("chatgpt")
        return self._best_available("local")

    def choose_variant(self, model: str, task: str, step_text: str, failure_count: int = 0) -> str | None:
        profile = self._task_profile(task, step_text)
        if model == "claude":
            if profile["planning"]:
                return "opusplan"
            if failure_count >= 2 or profile["debug"] or profile["risky"] or profile["complexity"] >= 4:
                return "opus"
            if profile["complexity"] <= 1 and not profile["risky"]:
                return "haiku"
            return "sonnet"
        if model == "openai":
            if failure_count >= 2 or profile["debug"] or profile["risky"] or profile["complexity"] >= 4:
                return "gpt-5.4"
            if profile["complexity"] <= 1 and not profile["risky"]:
                return "gpt-5.4-mini"
            return "gpt-5.2-codex"
        if model == "chatgpt":
            if failure_count >= 2 or profile["debug"] or profile["risky"] or profile["complexity"] >= 4:
                return "gpt-5.3-codex"
            if profile["complexity"] <= 1 and not profile["risky"]:
                return "codex-mini-latest"
            return "gpt-5.1-codex-mini"
        return None

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

    def _task_profile(self, task: str, step_text: str) -> dict[str, object]:
        text = f"{task} {step_text}".lower()
        debug_tokens = ("debug", "failure", "bug", "traceback", "regression")
        complex_tokens = ("refactor", "complex", "architecture", "handoff", "planner", "executor")
        risky_tokens = ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security")
        planning_tokens = ("plan", "planner", "design", "architecture", "roadmap")

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
        }

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
