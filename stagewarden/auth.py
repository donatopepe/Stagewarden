from __future__ import annotations

import json
import os
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
import subprocess


@dataclass(slots=True)
class AuthResult:
    ok: bool
    message: str
    token: str = ""
    code: str = ""
    secret_payload: str = ""


class OpenAIDeviceCodeFlow:
    def __init__(self, *, model: str, account: str, timeout_seconds: int = 300) -> None:
        self.model = model
        self.account = account
        self.timeout_seconds = timeout_seconds

    def run(self) -> AuthResult:
        issuer = (
            os.environ.get(f"STAGEWARDEN_{self.model.upper()}_ISSUER")
            or os.environ.get("STAGEWARDEN_OPENAI_ISSUER")
            or "https://chatgpt.com/backend-api"
        ).rstrip("/")
        client_id = (
            os.environ.get(f"STAGEWARDEN_{self.model.upper()}_CLIENT_ID")
            or os.environ.get("STAGEWARDEN_OPENAI_CLIENT_ID")
            or ""
        ).strip()
        if not client_id:
            return AuthResult(False, "Device code login requires STAGEWARDEN_OPENAI_CLIENT_ID or model-specific CLIENT_ID.")
        try:
            usercode = self._post_json(
                f"{issuer}/api/accounts/deviceauth/usercode",
                {"client_id": client_id},
            )
            device_auth_id = str(usercode.get("device_auth_id", "")).strip()
            user_code = str(usercode.get("user_code", "")).strip()
            interval = self._parse_interval(usercode.get("interval", 5))
            if not device_auth_id or not user_code:
                return AuthResult(False, "Device code login did not return device_auth_id and user_code.")
            verification_url = (
                os.environ.get(f"STAGEWARDEN_{self.model.upper()}_DEVICE_VERIFICATION_URL")
                or os.environ.get("STAGEWARDEN_OPENAI_DEVICE_VERIFICATION_URL")
                or "https://chatgpt.com/device"
            )
            self._open_verification_browser(verification_url, user_code)
            authorization = self._poll_authorization(issuer, device_auth_id, interval)
            oauth = self._post_json(
                f"{issuer}/oauth/token",
                {
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": authorization["authorization_code"],
                    "code_verifier": authorization["code_verifier"],
                    "code_challenge": authorization["code_challenge"],
                },
            )
        except TimeoutError:
            return AuthResult(False, "Timed out waiting for device-code authorization.")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return AuthResult(False, body or f"Device code login failed with HTTP {exc.code}.")
        except urllib.error.URLError as exc:
            return AuthResult(False, str(exc.reason))
        except ValueError as exc:
            return AuthResult(False, str(exc))

        access_token = str(oauth.get("access_token", "")).strip()
        refresh_token = str(oauth.get("refresh_token", "")).strip()
        id_token = str(oauth.get("id_token", "")).strip()
        if not access_token:
            return AuthResult(False, "OAuth token exchange did not return an access_token.")
        payload = {
            "issuer": issuer,
            "client_id": client_id,
            "model": self.model,
            "account": self.account,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
        }
        return AuthResult(
            True,
            f"Device code login completed. Open {verification_url} and enter code {user_code}.",
            token=access_token,
            secret_payload=json.dumps(payload, separators=(",", ":")),
        )

    def _post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError(f"Unexpected response from {url}.")
        return decoded

    def _poll_authorization(self, issuer: str, device_auth_id: str, interval: float) -> dict[str, str]:
        deadline = time.time() + self.timeout_seconds
        url = f"{issuer}/api/accounts/deviceauth/token"
        while time.time() < deadline:
            try:
                payload = self._post_json(url, {"device_auth_id": device_auth_id})
            except urllib.error.HTTPError as exc:
                if exc.code in {400, 401, 403, 404, 428}:
                    time.sleep(interval)
                    continue
                raise
            code = str(payload.get("authorization_code", "")).strip()
            verifier = str(payload.get("code_verifier", "")).strip()
            challenge = str(payload.get("code_challenge", "")).strip()
            if code and verifier and challenge:
                return {
                    "authorization_code": code,
                    "code_verifier": verifier,
                    "code_challenge": challenge,
                }
            time.sleep(interval)
        raise TimeoutError

    def _parse_interval(self, raw: object) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 5.0
        return max(0.5, value)

    def _open_verification_browser(self, verification_url: str, user_code: str) -> None:
        if os.environ.get("STAGEWARDEN_SKIP_BROWSER") == "1":
            return
        url = verification_url
        separator = "&" if "?" in verification_url else "?"
        url_with_hint = f"{verification_url}{separator}code={urllib.parse.quote(user_code)}"
        webbrowser.open(url)
        webbrowser.open_new_tab(url_with_hint)
