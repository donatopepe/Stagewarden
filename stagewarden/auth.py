from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .secrets import LOGIN_URLS


@dataclass(slots=True)
class AuthResult:
    ok: bool
    message: str
    token: str = ""
    code: str = ""


class BrowserCallbackFlow:
    def __init__(self, *, model: str, account: str, timeout_seconds: int = 120) -> None:
        self.model = model
        self.account = account
        self.timeout_seconds = timeout_seconds
        self.state = os.urandom(12).hex()
        self._result = AuthResult(False, "Login did not complete.")
        self._event = threading.Event()

    def run(self) -> AuthResult:
        try:
            server = self._start_server()
        except PermissionError:
            return self._fallback_without_listener()
        callback_url = f"http://127.0.0.1:{server.server_port}/callback"
        launch_url = f"http://127.0.0.1:{server.server_port}/"
        try:
            self._open_browser(launch_url, callback_url)
            self._trigger_auto_callback(callback_url)
            if not self._event.wait(self.timeout_seconds):
                return AuthResult(
                    False,
                    (
                        f"Timed out waiting for browser callback on {callback_url}. "
                        "Configure a provider login URL template or callback helper."
                    ),
                )
            if self._result.code and not self._result.token:
                exchanged = self._exchange_code(self._result.code, callback_url)
                if exchanged.ok:
                    return exchanged
                return exchanged
            return self._result
        finally:
            server.shutdown()
            server.server_close()

    def _fallback_without_listener(self) -> AuthResult:
        token = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN", "").strip()
        if token:
            return AuthResult(True, "Local callback listener unavailable; used configured callback token.", token=token)
        code = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_CODE", "").strip()
        if code:
            exchanged = self._exchange_code(code, "http://127.0.0.1/callback")
            if exchanged.ok:
                exchanged.message = "Local callback listener unavailable; used configured authorization code."
            return exchanged
        return AuthResult(
            False,
            "Unable to bind local callback listener on 127.0.0.1. Run outside the sandbox or configure callback automation.",
        )

    def _start_server(self) -> ThreadingHTTPServer:
        flow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/callback":
                    self._write(200, flow._render_launch_page())
                    return
                params = urllib.parse.parse_qs(parsed.query)
                ok, body, status = flow._consume_params(params)
                self._write(status, body)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/complete":
                    self._write(404, "<html><body><h1>Not found</h1></body></html>")
                    return
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(content_length).decode("utf-8") if content_length else ""
                params = urllib.parse.parse_qs(raw)
                ok, body, status = flow._consume_params(params)
                self._write(status, body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

            def _write(self, status: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def _open_browser(self, launch_url: str, callback_url: str) -> None:
        template = (
            os.environ.get(f"STAGEWARDEN_{self.model.upper()}_LOGIN_URL_TEMPLATE")
            or os.environ.get("STAGEWARDEN_LOGIN_URL_TEMPLATE")
        )
        if os.environ.get("STAGEWARDEN_SKIP_BROWSER") == "1":
            return
        webbrowser.open(launch_url)
        if template:
            provider_url = template.format(
                callback_url=callback_url,
                callback_url_encoded=urllib.parse.quote(callback_url, safe=""),
                state=self.state,
                model=self.model,
                account=self.account,
            )
            webbrowser.open_new_tab(provider_url)

    def _consume_params(self, params: dict[str, list[str]]) -> tuple[bool, str, int]:
        if params.get("state", [""])[0] != self.state:
            self._result = AuthResult(False, "Invalid callback state.")
            self._event.set()
            return False, "<html><body><h1>Invalid state</h1></body></html>", 400
        token = params.get("token", [""])[0].strip()
        code = params.get("code", [""])[0].strip()
        if token:
            self._result = AuthResult(True, "Browser flow completed.", token=token)
            self._event.set()
            return True, "<html><body><h1>Login completed</h1>You can return to Stagewarden.</body></html>", 200
        if code:
            self._result = AuthResult(True, "Authorization code received.", code=code)
            self._event.set()
            return True, "<html><body><h1>Code received</h1>You can return to Stagewarden.</body></html>", 200
        self._result = AuthResult(False, "Callback missing token or code.")
        self._event.set()
        return False, "<html><body><h1>Missing token or code</h1></body></html>", 400

    def _render_launch_page(self) -> str:
        provider_url = LOGIN_URLS.get(self.model, "")
        callback_hint = f"/callback?state={self.state}&token=..."
        provider_link = ""
        if provider_url:
            provider_link = f'<p><a href="{self._escape_html(provider_url)}" target="_blank" rel="noreferrer">Open provider login page</a></p>'
        return (
            "<html><body>"
            "<h1>Stagewarden browser login</h1>"
            f"<p>Model: {self._escape_html(self.model)}</p>"
            f"<p>Account: {self._escape_html(self.account)}</p>"
            f"{provider_link}"
            "<p>If the provider can redirect to localhost, complete login and return here automatically.</p>"
            "<p>If not, paste a token or authorization code below to finish the login in the browser.</p>"
            f"<p>Callback hint: <code>{self._escape_html(callback_hint)}</code></p>"
            f'<form method="post" action="/complete">'
            f'<input type="hidden" name="state" value="{self._escape_html(self.state)}"/>'
            '<label>Token<br/><input type="password" name="token" style="width: 32rem" autocomplete="off"/></label>'
            "<br/><br/>"
            '<label>Authorization code<br/><input type="text" name="code" style="width: 32rem" autocomplete="off"/></label>'
            "<br/><br/>"
            '<button type="submit">Complete login</button>'
            "</form>"
            "</body></html>"
        )

    def _escape_html(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _trigger_auto_callback(self, callback_url: str) -> None:
        token = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN", "").strip()
        code = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_CODE", "").strip()
        if not token and not code:
            return

        def _send() -> None:
            time.sleep(0.2)
            query = {"state": self.state}
            if token:
                query["token"] = token
            if code:
                query["code"] = code
            url = f"{callback_url}?{urllib.parse.urlencode(query)}"
            try:
                with urllib.request.urlopen(url, timeout=5):
                    pass
            except Exception:
                return

        threading.Thread(target=_send, daemon=True).start()

    def _exchange_code(self, code: str, callback_url: str) -> AuthResult:
        raw = os.environ.get(f"STAGEWARDEN_{self.model.upper()}_CODE_EXCHANGE_CMD") or os.environ.get(
            "STAGEWARDEN_CODE_EXCHANGE_CMD"
        )
        if not raw:
            return AuthResult(False, "Authorization code received, but no code exchange command is configured.")
        env = dict(os.environ)
        env["STAGEWARDEN_AUTH_CODE"] = code
        env["STAGEWARDEN_AUTH_STATE"] = self.state
        env["STAGEWARDEN_AUTH_CALLBACK_URL"] = callback_url
        import subprocess

        completed = subprocess.run(raw, shell=True, capture_output=True, text=True, env=env, check=False)
        if completed.returncode != 0:
            return AuthResult(False, completed.stderr.strip() or "Code exchange command failed.")
        stdout = completed.stdout.strip()
        if not stdout:
            return AuthResult(False, "Code exchange command returned empty output.")
        try:
            payload = json.loads(stdout)
            token = str(payload.get("token", "")).strip()
        except json.JSONDecodeError:
            token = stdout
        if not token:
            return AuthResult(False, "Code exchange command did not return a token.")
        return AuthResult(True, "Authorization code exchanged successfully.", token=token, code=code)
