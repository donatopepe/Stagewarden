from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

from .agent import Agent
from .auth import CodexBrowserLoginFlow, CodexBrowserLogoutFlow, OpenAIDeviceCodeFlow
from .config import AgentConfig
from .json_schema_registry import json_schema
from .modelprefs import ModelPreferences, SUPPORTED_MODELS, account_key
from .provider_registry import provider_capability
from .secrets import SecretStore
from .textcodec import read_text_utf8


def _main():
    from . import main as _main_module

    return _main_module


def _render_account_lines(prefs: ModelPreferences, model: str) -> list[str]:
    lines: list[str] = []
    accounts = (prefs.accounts_by_model or {}).get(model, [])
    active_account = (prefs.active_account_by_model or {}).get(model)
    for account in accounts:
        key = account_key(model, account)
        blocked_until = (prefs.blocked_until_by_account or {}).get(key)
        env_var = (prefs.env_var_by_account or {}).get(key)
        keychain = " token=stored" if SecretStore().has_token(model, account) else ""
        active = " active-account" if active_account == account else ""
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        env_text = f" env={env_var}" if env_var else ""
        lines.append(f"  account {account}:{active}{blocked}{env_text}{keychain}")
    return lines


def _render_accounts(config: AgentConfig) -> str:
    prefs = _main()._load_model_preferences(config)
    lines = ["Account profiles:"]
    found = False
    for model in SUPPORTED_MODELS:
        rendered = _render_account_lines(prefs, model)
        if rendered:
            found = True
            lines.append(f"- {model}")
            lines.extend(rendered)
    if not found:
        lines.append("- none configured")
    return "\n".join(lines)


def _accounts_report(config: AgentConfig) -> dict[str, object]:
    prefs = _main()._load_model_preferences(config)
    models: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        accounts = []
        for account in (prefs.accounts_by_model or {}).get(model, []):
            key = account_key(model, account)
            accounts.append(
                {
                    "name": account,
                    "active": (prefs.active_account_by_model or {}).get(model) == account,
                    "blocked_until": (prefs.blocked_until_by_account or {}).get(key),
                    "env": (prefs.env_var_by_account or {}).get(key),
                    "token_stored": SecretStore().has_token(model, account),
                }
            )
        if accounts:
            models.append({"model": model, "accounts": accounts})
    return {
        "command": "accounts",
        "schema": json_schema("accounts"),
        "models": models,
    }


def _account_usage() -> str:
    return (
        "Usage: accounts | account add <model> <name> [ENV_VAR] | account login <model> <name> | "
        "account login-device <chatgpt|openai> <name> | "
        "account logout <model> <name> | account env <model> <name> <ENV_VAR> | account import <model> <name> [PATH] | "
        "account use <model> <name> | account choose [model] | account remove <model> <name> | "
        "account block <model> <name> until YYYY-MM-DDTHH:MM | account unblock <model> <name> | "
        "account limit-record <model> <name> <message> | account limit-clear <model> <name> | account clear <model>"
    )


def _default_claude_credentials_path() -> Path | None:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / ".credentials.json"
    home = Path.home()
    if not str(home):
        return None
    return home / ".claude" / ".credentials.json"


def _guided_account_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided account selection is available in the interactive shell. Run `python3 -m stagewarden.main` and use `account choose`."
    models_with_accounts = [
        model
        for model in SUPPORTED_MODELS
        if (prefs.accounts_by_model or {}).get(model)
    ]
    if not models_with_accounts:
        return "No configured account profiles are available."
    model = requested_model
    if model is None:
        model = _main()._prompt_menu_choice(
            title="Choose provider for account:",
            options=[(item, item) for item in models_with_accounts],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if model is None:
            return "Guided account selection cancelled."
    accounts = list((prefs.accounts_by_model or {}).get(model, []))
    if not accounts:
        return f"No configured account profiles for {model}."
    chosen_account = _main()._prompt_menu_choice(
        title=f"Choose account for {model}:",
        options=[(name, name) for name in accounts],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if chosen_account is None:
        return "Guided account selection cancelled."
    prefs.set_active_account(model, chosen_account)
    _main()._save_model_preferences(config, prefs)
    return f"Active account for {model} set to {chosen_account}."


def _handle_account_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "accounts":
        return _render_accounts(config)
    if parts[0] != "account":
        return None
    if len(parts) < 2:
        return _account_usage()

    action = parts[1]
    prefs = _main()._load_model_preferences(config)
    try:
        if action == "limit-record":
            fields = command[len("account limit-record ") :].split(maxsplit=2)
            if len(fields) != 3:
                return "Usage: account limit-record <model> <name> <provider message>"
            model, name, message = fields
            result = _main()._record_limit_message(config, prefs, model=model, account=name, message=message)
            _main()._apply_model_preferences(agent, config)
            return result
        if action == "limit-clear":
            fields = command[len("account limit-clear ") :].split(maxsplit=1)
            if len(fields) != 2:
                return "Usage: account limit-clear <model> <name>"
            model, name = fields
            result = _main()._clear_limit_snapshot(config, prefs, model=model, account=name)
            _main()._apply_model_preferences(agent, config)
            return result
        if action == "add":
            if len(parts) not in {4, 5}:
                return "Usage: account add <model> <name> [ENV_VAR]"
            model, name = parts[2], parts[3]
            prefs.add_account(model, name, env_var=parts[4] if len(parts) == 5 else None)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            return f"Added account {model}:{name}."
        if action == "login":
            if len(parts) != 4:
                return "Usage: account login <model> <name>"
            model, name = parts[2], parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            capability = provider_capability(model)
            if model == "chatgpt" and not capability.supports_browser_login:
                return f"Interactive login is not supported for model '{model}'. {capability.login_hint}"
            if model == "openai" and not capability.supports_api_key:
                return f"Interactive login is not supported for model '{model}'. {capability.login_hint}"
            if model not in {"chatgpt", "openai"}:
                return f"Interactive login is not supported for model '{model}'. {capability.login_hint}"
            prefs.add_account(model, name)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            if model == "chatgpt":
                result = CodexBrowserLoginFlow(model=model, account=name).run()
            else:
                result = OpenAIDeviceCodeFlow(model=model, account=name).run()
            if not result.ok:
                return result.message
            if result.secret_payload or result.token:
                saved = SecretStore().save_token(model, name, result.secret_payload or result.token)
                if not saved.ok:
                    return saved.message
            prefs.set_active_account(model, name)
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            if result.secret_payload or result.token:
                return f"{result.message}\nSaved token for {model}:{name}."
            return result.message
        if action == "login-device":
            if len(parts) != 4:
                return "Usage: account login-device <chatgpt|openai> <name>"
            model, name = parts[2], parts[3]
            if model not in {"chatgpt", "openai"}:
                return "Device code login is supported only for chatgpt and openai."
            return _handle_account_command(
                f"account login {model} {name}",
                agent,
                config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "logout":
            if len(parts) != 4:
                return "Usage: account logout <model> <name>"
            model, name = parts[2], parts[3]
            browser_logout_message = ""
            if model == "chatgpt":
                browser_logout = CodexBrowserLogoutFlow(model=model).run()
                if not browser_logout.ok:
                    return browser_logout.message
                browser_logout_message = browser_logout.message
            result = SecretStore().delete_token(model, name)
            if model == "chatgpt":
                return f"{browser_logout_message}\n{result.message}"
            return result.message
        if action == "env":
            if len(parts) != 5:
                return "Usage: account env <model> <name> <ENV_VAR>"
            model, name, env_var = parts[2], parts[3], parts[4]
            if name not in (prefs.accounts_by_model or {}).get(model, []):
                prefs.add_account(model, name)
            prefs.set_account_env(model, name, env_var)
            _main()._save_model_preferences(config, prefs)
            return f"Set token env for {model}:{name} to {env_var}."
        if action == "import":
            if len(parts) not in {4, 5}:
                return "Usage: account import <model> <name> [PATH]"
            model, name = parts[2], parts[3]
            if model != "claude":
                return f"Import is not supported for model '{model}'."
            path = Path(parts[4]) if len(parts) == 5 else _default_claude_credentials_path()
            if path is None:
                return "No default Claude credentials path is available. Pass an explicit path."
            if not path.exists():
                return f"Credentials file not found: {path}"
            payload = read_text_utf8(path).strip()
            if not payload:
                return f"Credentials file is empty: {path}"
            prefs.add_account(model, name)
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            saved = SecretStore().save_token(model, name, payload)
            if not saved.ok:
                return saved.message
            prefs.set_active_account(model, name)
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            return f"Imported credentials for {model}:{name} from {path}."
        if action == "use":
            if len(parts) != 4:
                return "Usage: account use <model> <name>"
            model, name = parts[2], parts[3]
            prefs.set_active_account(model, name)
            _main()._save_model_preferences(config, prefs)
            return f"Active account for {model} set to {name}."
        if action == "choose":
            if len(parts) > 3:
                return "Usage: account choose [model]"
            requested_model = parts[2] if len(parts) == 3 else None
            return _guided_account_choice(
                requested_model=requested_model,
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "remove":
            if len(parts) != 4:
                return "Usage: account remove <model> <name>"
            model, name = parts[2], parts[3]
            prefs.remove_account(model, name)
            _main()._save_model_preferences(config, prefs)
            return f"Removed account {model}:{name}."
        if action == "block":
            if len(parts) != 6 or parts[4] != "until":
                return "Usage: account block <model> <name> until YYYY-MM-DDTHH:MM"
            model, name, until = parts[2], parts[3], parts[5]
            prefs.block_account(model, name, until)
            _main()._save_model_preferences(config, prefs)
            return f"Blocked account {model}:{name} until {until}."
        if action == "unblock":
            if len(parts) != 4:
                return "Usage: account unblock <model> <name>"
            model, name = parts[2], parts[3]
            prefs.unblock_account(model, name)
            _main()._save_model_preferences(config, prefs)
            return f"Unblocked account {model}:{name}."
        if action == "clear":
            if len(parts) != 3:
                return "Usage: account clear <model>"
            prefs.set_active_account(parts[2], None)
            _main()._save_model_preferences(config, prefs)
            return f"Cleared active account for {parts[2]}."
    except ValueError as exc:
        return str(exc)
    return _account_usage()
