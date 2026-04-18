from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

from .secrets import SecretStore


MODEL_BACKENDS = {
    "local": {"provider": "ollama", "label": "local/ollama"},
    "cheap": {"provider": "openrouter", "label": "cheap/openrouter"},
    "gpt": {"provider": "GPT-5.4", "label": "gpt/GPT-5.4"},
    "claude": {"provider": "Claude Sonnet", "label": "claude/sonnet"},
}

MODEL_TOKEN_ENV = {
    "cheap": "OPENROUTER_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


@dataclass(slots=True)
class ModelResult:
    ok: bool
    model: str
    backend: str
    prompt: str
    command: str
    account: str = ""
    output: str = ""
    error: str = ""


def parse_run_model_command(command: str) -> tuple[str, str, str | None]:
    prefix = "RUN_MODEL:"
    if not command.startswith(prefix):
        raise ValueError("Expected command to start with 'RUN_MODEL:'.")

    payload = command[len(prefix) :].strip()
    if not payload:
        raise ValueError("RUN_MODEL command is missing model and prompt.")

    parts = payload.split(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("RUN_MODEL command must include model and prompt.")

    target, prompt = parts
    model, account = parse_model_target(target)
    return model, prompt, account


def parse_model_target(target: str) -> tuple[str, str | None]:
    model, separator, account = target.partition(":")
    if model not in MODEL_BACKENDS:
        raise ValueError(f"Unsupported model '{model}'.")
    clean_account = account.strip() if separator else None
    if clean_account == "":
        clean_account = None
    return model, clean_account


def format_run_model(model: str, prompt: str, *, account: str | None = None) -> str:
    if model not in MODEL_BACKENDS:
        raise ValueError(f"Unsupported model '{model}'.")
    target = f"{model}:{account}" if account else model
    return f"RUN_MODEL: {target} {prompt}"


class HandoffManager:
    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds
        self.run_model_binary = os.environ.get("RUN_MODEL_BIN", "run_model")
        self.account_env_by_target: dict[str, str] = {}

    def execute(self, command: str) -> ModelResult:
        model, prompt, account = parse_run_model_command(command)
        return self.invoke(model=model, prompt=prompt, account=account)

    def invoke(self, *, model: str, prompt: str, account: str | None = None) -> ModelResult:
        if model not in MODEL_BACKENDS:
            raise ValueError(f"Unsupported model '{model}'.")

        command = [self.run_model_binary, model, prompt]
        env = self._build_env(model, account)
        account_label = account or ""
        rendered_prefix = f"STAGEWARDEN_MODEL_ACCOUNT={shlex.quote(account_label)} " if account else ""
        rendered = rendered_prefix + " ".join(shlex.quote(part) for part in command)
        backend = MODEL_BACKENDS[model]["label"]

        try:
            completed = subprocess.run(
                command,
                env=env,
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
                account=account_label,
                error="run_model executable not found in PATH.",
            )
        except subprocess.TimeoutExpired:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                account=account_label,
                error=f"Model call timed out after {self.timeout_seconds}s.",
            )
        except OSError as exc:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                account=account_label,
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
                account=account_label,
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
                account=account_label,
                error="Model returned empty output.",
            )

        return ModelResult(
            ok=True,
            model=model,
            backend=backend,
            prompt=prompt,
            command=rendered,
            account=account_label,
            output=stdout,
        )

    def _build_env(self, model: str, account: str | None) -> dict[str, str]:
        env = dict(os.environ)
        if not account:
            return env
        target = f"{model}:{account}"
        env["STAGEWARDEN_MODEL_ACCOUNT"] = account
        env["STAGEWARDEN_MODEL_TARGET"] = target
        source_env = self.account_env_by_target.get(target)
        provider_env = MODEL_TOKEN_ENV.get(model)
        if source_env and provider_env and source_env in os.environ:
            env[provider_env] = os.environ[source_env]
        elif provider_env:
            loaded = SecretStore().load_token(model, account)
            if loaded.ok:
                env[provider_env] = loaded.secret
        return env
