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
        server = self._start_server()
        callback_url = f"http://127.0.0.1:{server.server_port}/callback"
        try:
            self._open_browser(callback_url)
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

    def _start_server(self) -> ThreadingHTTPServer:
        flow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/callback":
                    self._write(
                        200,
                        (
                            "<html><body><h1>Stagewarden login waiting</h1>"
                            f"<p>Model: {flow.model}</p>"
                            f"<p>Account: {flow.account}</p>"
                            f"<p>Callback path: /callback?state={flow.state}&token=...</p>"
                            "</body></html>"
                        ),
                    )
                    return
                params = urllib.parse.parse_qs(parsed.query)
                if params.get("state", [""])[0] != flow.state:
                    flow._result = AuthResult(False, "Invalid callback state.")
                    flow._event.set()
                    self._write(400, "<html><body><h1>Invalid state</h1></body></html>")
                    return
                token = params.get("token", [""])[0].strip()
                code = params.get("code", [""])[0].strip()
                if token:
                    flow._result = AuthResult(True, "Browser callback completed.", token=token)
                    flow._event.set()
                    self._write(200, "<html><body><h1>Login completed</h1>You can return to Stagewarden.</body></html>")
                    return
                if code:
                    flow._result = AuthResult(True, "Authorization code received.", code=code)
                    flow._event.set()
                    self._write(200, "<html><body><h1>Code received</h1>You can return to Stagewarden.</body></html>")
                    return
                flow._result = AuthResult(False, "Callback missing token or code.")
                flow._event.set()
                self._write(400, "<html><body><h1>Missing token or code</h1></body></html>")

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

    def _open_browser(self, callback_url: str) -> None:
        template = (
            os.environ.get(f"STAGEWARDEN_{self.model.upper()}_LOGIN_URL_TEMPLATE")
            or os.environ.get("STAGEWARDEN_LOGIN_URL_TEMPLATE")
        )
        if template:
            url = template.format(
                callback_url=callback_url,
                callback_url_encoded=urllib.parse.quote(callback_url, safe=""),
                state=self.state,
                model=self.model,
                account=self.account,
            )
        else:
            url = f"http://127.0.0.1:{urllib.parse.urlparse(callback_url).port}/?state={self.state}"
        if os.environ.get("STAGEWARDEN_SKIP_BROWSER") == "1":
            return
        webbrowser.open(url)

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
