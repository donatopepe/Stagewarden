from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from .provider_registry import login_urls

LOGIN_URLS = login_urls()


@dataclass(slots=True)
class SecretResult:
    ok: bool
    message: str = ""
    secret: str = ""


class SecretStore:
    SERVICE = "stagewarden"

    def save_token(self, model: str, account: str, token: str) -> SecretResult:
        token = token.strip()
        if not token:
            return SecretResult(False, "Token is empty.")
        fallback = self._fallback_dir()
        if fallback:
            return self._save_file(fallback, model, account, token)
        if self._is_macos_keychain_available():
            return self._save_macos(model, account, token)
        return SecretResult(False, "No supported secret store found. On macOS, Keychain is required.")

    def load_token(self, model: str, account: str) -> SecretResult:
        fallback = self._fallback_dir()
        if fallback:
            return self._load_file(fallback, model, account)
        if self._is_macos_keychain_available():
            return self._load_macos(model, account)
        return SecretResult(False, "No supported secret store found.")

    def delete_token(self, model: str, account: str) -> SecretResult:
        fallback = self._fallback_dir()
        if fallback:
            path = self._file_path(fallback, model, account)
            if path.exists():
                path.unlink()
            return SecretResult(True, "Token deleted.")
        if self._is_macos_keychain_available():
            return self._delete_macos(model, account)
        return SecretResult(False, "No supported secret store found.")

    def has_token(self, model: str, account: str) -> bool:
        return self.load_token(model, account).ok

    def open_login_page(self, model: str) -> SecretResult:
        url = LOGIN_URLS.get(model)
        if not url:
            return SecretResult(False, f"No login URL configured for model '{model}'.")
        if os.environ.get("STAGEWARDEN_SKIP_BROWSER") == "1":
            return SecretResult(True, f"Browser skipped. Open manually: {url}")
        opened = webbrowser.open(url)
        if not opened:
            return SecretResult(False, f"Unable to open browser. Open manually: {url}")
        return SecretResult(True, f"Opened browser: {url}")

    def _is_macos_keychain_available(self) -> bool:
        return platform.system().lower() == "darwin" and shutil.which("security") is not None

    def _save_macos(self, model: str, account: str, token: str) -> SecretResult:
        completed = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                self._target(model, account),
                "-s",
                self.SERVICE,
                "-w",
                token,
                "-U",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return SecretResult(False, completed.stderr.strip() or "Unable to save token in Keychain.")
        return SecretResult(True, "Token saved in macOS Keychain.")

    def _load_macos(self, model: str, account: str) -> SecretResult:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                self._target(model, account),
                "-s",
                self.SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return SecretResult(False, "Token not found in Keychain.")
        return SecretResult(True, "Token loaded from Keychain.", completed.stdout.strip())

    def _delete_macos(self, model: str, account: str) -> SecretResult:
        completed = subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-a",
                self._target(model, account),
                "-s",
                self.SERVICE,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode not in {0, 44}:
            return SecretResult(False, completed.stderr.strip() or "Unable to delete token from Keychain.")
        return SecretResult(True, "Token deleted from Keychain.")

    def _fallback_dir(self) -> Path | None:
        raw = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
        if raw:
            return Path(raw)
        if os.environ.get("STAGEWARDEN_ALLOW_PLAINTEXT_TOKENS") == "1":
            return Path.home() / ".stagewarden" / "secrets"
        return None

    def _save_file(self, base: Path, model: str, account: str, token: str) -> SecretResult:
        path = self._file_path(base, model, account)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return SecretResult(True, "Token saved in local secret-store fallback.")

    def _load_file(self, base: Path, model: str, account: str) -> SecretResult:
        path = self._file_path(base, model, account)
        if not path.exists():
            return SecretResult(False, "Token not found.")
        return SecretResult(True, "Token loaded from local secret-store fallback.", path.read_text(encoding="utf-8").strip())

    def _file_path(self, base: Path, model: str, account: str) -> Path:
        return base / f"{self._target(model, account)}.token"

    def _target(self, model: str, account: str) -> str:
        return f"{model}:{account}"
