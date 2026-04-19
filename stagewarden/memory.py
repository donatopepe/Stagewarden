from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .ljson import LJSONOptions, decode as decode_ljson, encode as encode_ljson
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


@dataclass(slots=True)
class AttemptRecord:
    iteration: int
    step_id: str
    model: str
    action_type: str
    action_signature: str
    success: bool
    observation: str
    error_type: str | None = None


@dataclass(slots=True)
class ToolTranscriptRecord:
    iteration: int
    step_id: str
    tool: str
    action_type: str
    success: bool
    summary: str
    detail: str = ""
    duration_ms: int = 0
    error_type: str | None = None


@dataclass(slots=True)
class MemoryStore:
    attempts: list[AttemptRecord] = field(default_factory=list)
    tool_transcript: list[ToolTranscriptRecord] = field(default_factory=list)
    failures_by_step: dict[str, int] = field(default_factory=dict)
    models_by_step: dict[str, list[str]] = field(default_factory=dict)

    def record_attempt(
        self,
        *,
        iteration: int,
        step_id: str,
        model: str,
        action_type: str,
        action_signature: str,
        success: bool,
        observation: str,
        error_type: str | None = None,
    ) -> None:
        self.attempts.append(
            AttemptRecord(
                iteration=iteration,
                step_id=step_id,
                model=model,
                action_type=action_type,
                action_signature=action_signature,
                success=success,
                observation=observation,
                error_type=error_type,
            )
        )
        self.models_by_step.setdefault(step_id, []).append(model)
        if success:
            self.failures_by_step.setdefault(step_id, 0)
        else:
            self.failures_by_step[step_id] = self.failures_by_step.get(step_id, 0) + 1

    def failure_count(self, step_id: str) -> int:
        return self.failures_by_step.get(step_id, 0)

    def record_tool_transcript(
        self,
        *,
        iteration: int,
        step_id: str,
        tool: str,
        action_type: str,
        success: bool,
        summary: str,
        detail: str = "",
        duration_ms: int = 0,
        error_type: str | None = None,
    ) -> None:
        self.tool_transcript.append(
            ToolTranscriptRecord(
                iteration=iteration,
                step_id=step_id,
                tool=tool,
                action_type=action_type,
                success=success,
                summary=summary[:500],
                detail=detail[:2000],
                duration_ms=duration_ms,
                error_type=error_type,
            )
        )

    def recent_attempts(self, step_id: str, limit: int = 3) -> list[AttemptRecord]:
        return [item for item in self.attempts if item.step_id == step_id][-limit:]

    def last_model(self, step_id: str) -> str | None:
        models = self.models_by_step.get(step_id, [])
        return models[-1] if models else None

    def should_abort_step(self, step_id: str, threshold: int = 3) -> bool:
        attempts = self.recent_attempts(step_id, limit=threshold)
        if len(attempts) < threshold:
            return False
        signatures = {item.action_signature for item in attempts}
        return len(signatures) == 1

    def summarize(self, limit: int = 8) -> str:
        if not self.attempts:
            return "No prior attempts."
        lines: list[str] = []
        for item in self.attempts[-limit:]:
            status = "ok" if item.success else f"failed:{item.error_type or 'unknown'}"
            lines.append(
                f"[iter={item.iteration}] step={item.step_id} model={item.model} "
                f"action={item.action_type} status={status}"
            )
        return "\n".join(lines)

    def detailed_summary(self, limit: int = 8) -> str:
        if not self.attempts:
            return "No execution log."
        lines: list[str] = []
        for item in self.attempts[-limit:]:
            status = "ok" if item.success else f"failed:{item.error_type or 'unknown'}"
            observation = item.observation.strip().replace("\n", " ")
            lines.append(
                f"[iter={item.iteration}] step={item.step_id} model={item.model} "
                f"action={item.action_type} status={status} observation={observation[:160]}"
            )
        return "\n".join(lines)

    def transcript_summary(self, limit: int = 12) -> str:
        if not self.tool_transcript:
            return "No tool transcript."
        lines: list[str] = ["Tool transcript:"]
        for item in self.tool_transcript[-limit:]:
            status = "ok" if item.success else f"failed:{item.error_type or 'unknown'}"
            detail = item.detail.strip().replace("\n", " ")
            suffix = f" detail={detail[:180]}" if detail else ""
            duration = f" duration_ms={item.duration_ms}" if item.duration_ms else ""
            lines.append(
                f"- [iter={item.iteration}] step={item.step_id} tool={item.tool} "
                f"action={item.action_type} status={status}{duration} summary={item.summary}{suffix}"
            )
        return "\n".join(lines)

    def model_usage_summary(self) -> str:
        if not self.attempts:
            return "Model usage:\n- no model attempts recorded"
        cost_tiers = {
            "local": "free/local",
            "cheap": "low",
            "chatgpt": "plan",
            "openai": "high",
            "claude": "high/fallback",
        }
        counts: dict[str, int] = {}
        failures: dict[str, int] = {}
        steps: dict[str, set[str]] = {}
        for attempt in self.attempts:
            counts[attempt.model] = counts.get(attempt.model, 0) + 1
            steps.setdefault(attempt.model, set()).add(attempt.step_id)
            if not attempt.success:
                failures[attempt.model] = failures.get(attempt.model, 0) + 1
        lines = ["Model usage:"]
        for model in sorted(counts, key=lambda item: (cost_tiers.get(item, "unknown"), item)):
            lines.append(
                f"- {model}: calls={counts[model]} failures={failures.get(model, 0)} "
                f"steps={len(steps.get(model, set()))} cost_tier={cost_tiers.get(model, 'unknown')}"
            )
        lines.append("Budget policy: prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.")
        return "\n".join(lines)

    def budget_summary(self) -> str:
        if not self.attempts:
            return "\n".join(
                [
                    "Cost and budget:",
                    "- no model attempts recorded",
                    "- policy: prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.",
                ]
            )
        cost_rank = {
            "free/local": 0,
            "low": 1,
            "plan": 2,
            "high": 3,
            "high/fallback": 4,
        }
        cost_tiers = {
            "local": "free/local",
            "cheap": "low",
            "chatgpt": "plan",
            "openai": "high",
            "claude": "high/fallback",
        }
        counts: dict[str, int] = {}
        failures: dict[str, int] = {}
        for attempt in self.attempts:
            counts[attempt.model] = counts.get(attempt.model, 0) + 1
            if not attempt.success:
                failures[attempt.model] = failures.get(attempt.model, 0) + 1
        ordered_models = sorted(counts, key=lambda item: (cost_rank.get(cost_tiers.get(item, "high/fallback"), 99), item))
        usage = ", ".join(f"{model}={counts[model]}" for model in ordered_models)
        highest_model = max(
            ordered_models,
            key=lambda item: cost_rank.get(cost_tiers.get(item, "high/fallback"), 99),
        )
        total_failures = sum(failures.values())
        lines = [
            "Cost and budget:",
            "- policy: prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.",
            f"- usage: {usage}",
            f"- highest_tier_used: {cost_tiers.get(highest_model, 'unknown')} ({highest_model})",
            f"- failed_model_calls: {total_failures}",
        ]
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempts": [asdict(item) for item in self.attempts],
            "tool_transcript": [asdict(item) for item in self.tool_transcript],
            "failures_by_step": dict(self.failures_by_step),
            "models_by_step": dict(self.models_by_step),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_format": "stagewarden_memory",
            "_version": 1,
            "attempts_ljson": encode_ljson(
                [asdict(item) for item in self.attempts],
                options=LJSONOptions(version=1, normalize_missing=True),
            ),
            "tool_transcript_ljson": encode_ljson(
                [asdict(item) for item in self.tool_transcript],
                options=LJSONOptions(version=1, normalize_missing=True),
            ),
            "failures_by_step": dict(self.failures_by_step),
            "models_by_step": dict(self.models_by_step),
        }
        write_text_utf8(path, dumps_ascii(payload, indent=2))

    @classmethod
    def load(cls, path: Path) -> "MemoryStore":
        if not path.exists():
            return cls()

        payload = loads_text(read_text_utf8(path))
        store = cls()
        attempts = payload.get("attempts")
        if "attempts_ljson" in payload:
            attempts = decode_ljson(payload["attempts_ljson"])
        for item in attempts or []:
            store.attempts.append(AttemptRecord(**item))
        transcript = payload.get("tool_transcript")
        if "tool_transcript_ljson" in payload:
            transcript = decode_ljson(payload["tool_transcript_ljson"])
        for item in transcript or []:
            store.tool_transcript.append(ToolTranscriptRecord(**item))
        store.failures_by_step = {
            str(key): int(value) for key, value in payload.get("failures_by_step", {}).items()
        }
        store.models_by_step = {
            str(key): [str(model) for model in value]
            for key, value in payload.get("models_by_step", {}).items()
        }
        return store

    def attempts_as_ljson(self, *, numeric_keys: bool = False) -> dict[str, Any]:
        return encode_ljson(
            [asdict(item) for item in self.attempts],
            options=LJSONOptions(numeric_keys=numeric_keys, normalize_missing=True),
        )

    def tool_transcript_as_ljson(self, *, numeric_keys: bool = False) -> dict[str, Any]:
        return encode_ljson(
            [asdict(item) for item in self.tool_transcript],
            options=LJSONOptions(numeric_keys=numeric_keys, normalize_missing=True),
        )
