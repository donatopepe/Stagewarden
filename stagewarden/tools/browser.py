from __future__ import annotations

from dataclasses import dataclass
import html
from html.parser import HTMLParser
from pathlib import Path
import re
import time
import webbrowser
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:  # Optional dependency.
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None


@dataclass(slots=True)
class BrowserResult:
    ok: bool
    command: str
    message: str
    url: str | None = None
    path: str | None = None
    title: str | None = None
    content_type: str | None = None
    bytes_read: int = 0
    duration_ms: int = 0
    items: list[dict[str, str]] | None = None
    error_type: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "message": self.message,
            "url": self.url,
            "path": self.path,
            "title": self.title,
            "content_type": self.content_type,
            "bytes_read": self.bytes_read,
            "duration_ms": self.duration_ms,
            "items": list(self.items or []),
            "error_type": self.error_type,
            "error": self.error,
        }


class _HTMLSnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.links: list[dict[str, str]] = []
        self._text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: D401
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() == "a":
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = value
                    break
            if href:
                self.links.append({"href": href, "text": ""})

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text
        if len(self._text_chunks) < 32:
            self._text_chunks.append(text)
        if self.links and not self.links[-1]["text"]:
            self.links[-1]["text"] = text

    def snapshot(self) -> dict[str, str]:
        return {
            "title": self.title.strip(),
            "text": " ".join(self._text_chunks).strip(),
        }


class BrowserTool:
    def __init__(self, workspace_root: Path, *, timeout_seconds: int = 20, max_bytes: int = 2 * 1024 * 1024) -> None:
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def fetch(self, url: str, *, limit: int = 10) -> BrowserResult:
        started = time.monotonic()
        try:
            self._validate_url(url)
            request = Request(url, headers={"User-Agent": "Stagewarden/1.0"})
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                raw = response.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                raise ValueError(f"Response exceeds max_bytes limit ({self.max_bytes}).")
            text = raw.decode("utf-8", errors="replace")
            parsed = self._parse_html(text)
            items = parsed.get("links", [])[:limit]
            message = f"Fetched {len(raw)} bytes from {url}."
            if parsed.get("title"):
                message = f"Fetched page title: {parsed['title']}."
            return BrowserResult(
                ok=True,
                command="browser fetch",
                message=message,
                url=url,
                title=parsed.get("title"),
                content_type=content_type,
                bytes_read=len(raw),
                duration_ms=self._elapsed_ms(started),
                items=items,
            )
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return self._error("browser fetch", str(exc), started, url=url)

    def open(self, url: str) -> BrowserResult:
        started = time.monotonic()
        try:
            self._validate_url(url)
            opened = webbrowser.open(url, new=0, autoraise=False)
            if not opened:
                raise RuntimeError("No browser could be opened.")
            return BrowserResult(
                ok=True,
                command="browser open",
                message=f"Opened browser URL: {url}",
                url=url,
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return self._error("browser open", str(exc), started, url=url)

    def screenshot(self, url: str, path: str | None = None, *, full_page: bool = True, browser: str = "chromium") -> BrowserResult:
        started = time.monotonic()
        try:
            self._validate_url(url)
            if sync_playwright is None:
                raise RuntimeError("Playwright is required for browser screenshots.")
            output = self._resolve_output(path or self._default_screenshot_name(url))
            output.parent.mkdir(parents=True, exist_ok=True)
            title = None
            with sync_playwright() as playwright:
                browser_type = getattr(playwright, browser, None)
                if browser_type is None:
                    raise ValueError(f"Unsupported browser: {browser}.")
                instance = browser_type.launch(headless=True)
                try:
                    page = instance.new_page()
                    page.goto(url, wait_until="networkidle", timeout=self.timeout_seconds * 1000)
                    page.screenshot(path=str(output), full_page=full_page)
                    title = page.title()
                finally:
                    instance.close()
            return BrowserResult(
                ok=True,
                command="browser screenshot",
                message=f"Saved screenshot to {output}.",
                url=url,
                path=str(output),
                title=title,
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return self._error("browser screenshot", str(exc), started, url=url, path=path)

    def _parse_html(self, text: str) -> dict[str, Any]:
        parser = _HTMLSnapshotParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        snapshot = parser.snapshot()
        text_body = re.sub(r"\s+", " ", html.unescape(snapshot.get("text", ""))).strip()
        return {
            "title": snapshot.get("title", ""),
            "text": text_body,
            "links": parser.links,
        }

    def _resolve_output(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.workspace_root / candidate).resolve()
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise ValueError("Path must stay inside the workspace.")
        return candidate

    def _default_screenshot_name(self, url: str) -> str:
        parsed = urlsplit(url)
        stem = re.sub(r"[^A-Za-z0-9._-]", "_", parsed.netloc + parsed.path).strip("_")
        if not stem:
            stem = "page"
        return f"{stem[:80]}.png"

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are allowed.")
        if not parsed.netloc:
            raise ValueError("URL host is required.")

    def _elapsed_ms(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _error(self, command: str, message: str, started: float, *, url: str | None = None, path: str | None = None) -> BrowserResult:
        return BrowserResult(
            ok=False,
            command=command,
            message=message,
            url=url,
            path=path,
            duration_ms=self._elapsed_ms(started),
            error_type="browser_error",
            error=message,
        )
