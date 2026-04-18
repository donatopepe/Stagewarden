from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass


MODEL_BACKENDS = {
    "local": {"provider": "ollama", "label": "local/ollama"},
    "cheap": {"provider": "openrouter", "label": "cheap/openrouter"},
    "gpt": {"provider": "GPT-5.4", "label": "gpt/GPT-5.4"},
    "claude": {"provider": "Claude Sonnet", "label": "claude/sonnet"},
}


@dataclass(slots=True)
class ModelResult:
    ok: bool
    model: str
    backend: str
    prompt: str
    command: str
    output: str = ""
    error: str = ""


def parse_run_model_command(command: str) -> tuple[str, str]:
    prefix = "RUN_MODEL:"
    if not command.startswith(prefix):
        raise ValueError("Expected command to start with 'RUN_MODEL:'.")

    payload = command[len(prefix) :].strip()
    if not payload:
        raise ValueError("RUN_MODEL command is missing model and prompt.")

    parts = payload.split(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("RUN_MODEL command must include model and prompt.")

    model, prompt = parts
    if model not in MODEL_BACKENDS:
        raise ValueError(f"Unsupported model '{model}'.")
    return model, prompt


def format_run_model(model: str, prompt: str) -> str:
    if model not in MODEL_BACKENDS:
        raise ValueError(f"Unsupported model '{model}'.")
    return f"RUN_MODEL: {model} {prompt}"


class HandoffManager:
    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds
        self.run_model_binary = os.environ.get("RUN_MODEL_BIN", "run_model")

    def execute(self, command: str) -> ModelResult:
        model, prompt = parse_run_model_command(command)
        return self.invoke(model=model, prompt=prompt)

    def invoke(self, *, model: str, prompt: str) -> ModelResult:
        if model not in MODEL_BACKENDS:
            raise ValueError(f"Unsupported model '{model}'.")

        command = [self.run_model_binary, model, prompt]
        rendered = " ".join(shlex.quote(part) for part in command)
        backend = MODEL_BACKENDS[model]["label"]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                error="run_model executable not found in PATH.",
            )
        except subprocess.TimeoutExpired:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                error=f"Model call timed out after {self.timeout_seconds}s.",
            )
        except OSError as exc:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                error=str(exc),
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                output=stdout,
                error=stderr or f"run_model exited with status {completed.returncode}.",
            )

        if not stdout:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                error="Model returned empty output.",
            )

        return ModelResult(
            ok=True,
            model=model,
            backend=backend,
            prompt=prompt,
            command=rendered,
            output=stdout,
        )
