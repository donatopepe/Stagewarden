from __future__ import annotations


class ModelRouter:
    ORDER = ("local", "cheap", "gpt", "claude")

    def choose_model(self, task: str, step_text: str, failure_count: int = 0) -> str:
        if failure_count >= 3:
            return "claude"
        if failure_count >= 2:
            return "gpt"

        text = f"{task} {step_text}".lower()
        risky_tokens = ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security")
        if any(token in text for token in risky_tokens):
            return "gpt"
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
            return "gpt"
        if complexity <= 1:
            return "local"
        if complexity <= 3:
            return "cheap"
        return "gpt"

    def escalate(self, current: str) -> str:
        if current == "gpt":
            return "claude"
        try:
            index = self.ORDER.index(current)
        except ValueError:
            return "cheap"
        return self.ORDER[min(index + 1, len(self.ORDER) - 1)]

    def fallback_for_api_failure(self, current: str) -> str:
        if current == "gpt":
            return "cheap"
        if current == "claude":
            return "gpt"
        if current == "cheap":
            return "local"
        return "local"
