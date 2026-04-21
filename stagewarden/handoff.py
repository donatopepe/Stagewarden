from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable

from .provider_registry import (
    available_model_variants,
    canonicalize_model_variant,
    model_backends,
    model_name_env,
    model_token_env,
    model_variant_catalog,
)
from .secrets import SecretStore


MODEL_BACKENDS = model_backends()
MODEL_VARIANT_CATALOG = model_variant_catalog()
MODEL_TOKEN_ENV = model_token_env()
MODEL_NAME_ENV = model_name_env()


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
        self.model_variant_by_model: dict[str, str] = {}
        self.model_params_by_model: dict[str, dict[str, str]] = {}
        self.stream_callback: Callable[[str], None] | None = None

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
        if self.stream_callback is not None:
            return self._invoke_streaming(
                model=model,
                backend=backend,
                prompt=prompt,
                command=command,
                env=env,
                rendered=rendered,
                account_label=account_label,
            )

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

    def _invoke_streaming(
        self,
        *,
        model: str,
        backend: str,
        prompt: str,
        command: list[str],
        env: dict[str, str],
        rendered: str,
        account_label: str,
    ) -> ModelResult:
        callback = self.stream_callback
        stream_header = f"[model-stream {model}{':' + account_label if account_label else ''}] "
        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
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

        stdout_chunks: list[str] = []
        try:
            if callback is not None:
                callback(stream_header)
            while True:
                chunk = process.stdout.read(1) if process.stdout is not None else ""
                if chunk == "":
                    break
                stdout_chunks.append(chunk)
                if callback is not None:
                    callback(chunk)
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
            returncode = process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            if callback is not None:
                callback("\n")
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                account=account_label,
                error=f"Model call timed out after {self.timeout_seconds}s.",
            )
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            if callback is not None:
                callback("\n")

        stdout = "".join(stdout_chunks).strip()
        if returncode != 0:
            return ModelResult(
                ok=False,
                model=model,
                backend=backend,
                prompt=prompt,
                command=rendered,
                account=account_label,
                output=stdout,
                error=stderr or f"run_model exited with status {returncode}.",
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
        variant = self.model_variant_by_model.get(model)
        if variant:
            env["STAGEWARDEN_MODEL_VARIANT"] = variant
            provider_model_env = MODEL_NAME_ENV.get(model)
            if provider_model_env:
                env[provider_model_env] = variant
        params = self.model_params_by_model.get(model, {})
        reasoning_effort = params.get("reasoning_effort")
        if reasoning_effort:
            env["STAGEWARDEN_REASONING_EFFORT"] = reasoning_effort
        if not account:
            return env
        target = f"{model}:{account}"
        env["STAGEWARDEN_MODEL_ACCOUNT"] = account
        env["STAGEWARDEN_MODEL_TARGET"] = target
        source_env = self.account_env_by_target.get(target)
        provider_env = MODEL_TOKEN_ENV.get(model)
        if source_env and provider_env and source_env in os.environ:
            if model == "claude" and "AUTH_TOKEN" in source_env.upper():
                env["ANTHROPIC_AUTH_TOKEN"] = os.environ[source_env]
            else:
                env[provider_env] = os.environ[source_env]
        elif provider_env:
            loaded = SecretStore().load_token(model, account)
            if loaded.ok:
                token = loaded.secret
                try:
                    payload = json.loads(loaded.secret)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    if model == "claude":
                        api_key = str(
                            payload.get("api_key", "") or payload.get("anthropic_api_key", "")
                        ).strip()
                        auth_token = str(
                            payload.get("auth_token", "") or payload.get("anthropic_auth_token", "")
                        ).strip()
                        if api_key:
                            env["ANTHROPIC_API_KEY"] = api_key
                        if auth_token:
                            env["ANTHROPIC_AUTH_TOKEN"] = auth_token
                        if api_key or auth_token:
                            env["STAGEWARDEN_AUTH_TOKENS_JSON"] = loaded.secret
                            return env
                    access_token = str(payload.get("access_token", "")).strip()
                    if access_token:
                        env[provider_env] = access_token
                    env["STAGEWARDEN_AUTH_TOKENS_JSON"] = loaded.secret
                else:
                    env[provider_env] = token
        return env
