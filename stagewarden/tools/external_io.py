from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ExternalIOResult:
    ok: bool
    command: str
    message: str
    path: str | None = None
    url: str | None = None
    bytes_written: int = 0
    sha256: str | None = None
    content_type: str | None = None
    duration_ms: int = 0
    items: list[dict[str, str]] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "message": self.message,
            "path": self.path,
            "url": self.url,
            "bytes_written": self.bytes_written,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "duration_ms": self.duration_ms,
            "items": list(self.items or []),
            "error": self.error,
        }


class ExternalIOTool:
    def __init__(self, workspace_root: Path, *, timeout_seconds: int = 20, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def checksum(self, path: str) -> ExternalIOResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise ValueError("Target path is not a file.")
            digest, size = self._sha256_file(target)
            return ExternalIOResult(
                ok=True,
                command="checksum",
                message=f"SHA-256 computed for {self._display_path(target)}.",
                path=self._display_path(target),
                bytes_written=size,
                sha256=digest,
                content_type=mimetypes.guess_type(target.name)[0],
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, ValueError) as exc:
            return self._error("checksum", str(exc), started, path=path)

    def download(self, url: str, destination: str | None = None, *, max_bytes: int | None = None) -> ExternalIOResult:
        started = time.monotonic()
        try:
            self._validate_url(url)
            target = self._safe_path(destination or self._filename_from_url(url))
            limit = max(1, int(max_bytes or self.max_bytes))
            request = Request(url, headers={"User-Agent": "Stagewarden/1.0"})
            written = 0
            digest = hashlib.sha256()
            target.parent.mkdir(parents=True, exist_ok=True)
            with urlopen(request, timeout=self.timeout_seconds) as response, target.open("wb") as handle:
                content_type = response.headers.get_content_type()
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        handle.close()
                        target.unlink(missing_ok=True)
                        raise ValueError(f"Download exceeds max_bytes limit ({limit}).")
                    digest.update(chunk)
                    handle.write(chunk)
            return ExternalIOResult(
                ok=True,
                command="download",
                message=f"Downloaded {written} bytes to {self._display_path(target)}.",
                path=self._display_path(target),
                url=url,
                bytes_written=written,
                sha256=digest.hexdigest(),
                content_type=content_type,
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, ValueError) as exc:
            return self._error("download", str(exc), started, url=url, path=destination)

    def gzip_compress(self, source: str, destination: str | None = None) -> ExternalIOResult:
        started = time.monotonic()
        try:
            source_path = self._safe_path(source)
            if not source_path.is_file():
                raise ValueError("Source path is not a file.")
            target = self._safe_path(destination or f"{self._display_path(source_path)}.gz")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source_path.open("rb") as src, gzip.open(target, "wb") as dst:
                while True:
                    chunk = src.read(64 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            digest, size = self._sha256_file(target)
            return ExternalIOResult(
                ok=True,
                command="compress",
                message=f"Compressed {self._display_path(source_path)} to {self._display_path(target)}.",
                path=self._display_path(target),
                bytes_written=size,
                sha256=digest,
                content_type="application/gzip",
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, ValueError) as exc:
            return self._error("compress", str(exc), started, path=destination or source)

    def verify_archive(self, path: str) -> ExternalIOResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise ValueError("Archive path is not a file.")
            if target.suffix != ".gz":
                raise ValueError("Only .gz archives are supported by the current verifier.")
            total = 0
            with gzip.open(target, "rb") as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
            digest, size = self._sha256_file(target)
            return ExternalIOResult(
                ok=True,
                command="archive verify",
                message=f"Archive verified; compressed={size} bytes uncompressed={total} bytes.",
                path=self._display_path(target),
                bytes_written=size,
                sha256=digest,
                content_type="application/gzip",
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, EOFError, ValueError, gzip.BadGzipFile) as exc:
            return self._error("archive verify", str(exc), started, path=path)

    def web_search(self, query: str, *, endpoint: str | None = None, limit: int = 5) -> ExternalIOResult:
        started = time.monotonic()
        try:
            if not query.strip():
                raise ValueError("Search query is required.")
            url = endpoint or f"https://duckduckgo.com/html/?q={quote_plus(query.strip())}"
            self._validate_url(url)
            request = Request(url, headers={"User-Agent": "Stagewarden/1.0"})
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                raw = response.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                raise ValueError(f"Search response exceeds max_bytes limit ({self.max_bytes}).")
            text = raw.decode("utf-8", errors="replace")
            items = self._parse_search_results(text, content_type=content_type, limit=limit)
            return ExternalIOResult(
                ok=True,
                command="web search",
                message=f"Found {len(items)} result(s) for query.",
                url=url,
                bytes_written=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                content_type=content_type,
                duration_ms=self._elapsed_ms(started),
                items=items,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._error("web search", str(exc), started)

    def _parse_search_results(self, text: str, *, content_type: str, limit: int) -> list[dict[str, str]]:
        if content_type == "application/json":
            payload = json.loads(text)
            raw_items = payload.get("results", payload if isinstance(payload, list) else [])
            items: list[dict[str, str]] = []
            for item in raw_items[:limit]:
                if isinstance(item, dict):
                    title = str(item.get("title") or item.get("name") or "").strip()
                    url = str(item.get("url") or item.get("href") or "").strip()
                    snippet = str(item.get("snippet") or item.get("description") or "").strip()
                    if title or url:
                        items.append({"title": title, "url": url, "snippet": snippet})
            return items
        results: list[dict[str, str]] = []
        pattern = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
        for href, title_html in pattern.findall(text):
            title = re.sub(r"<[^>]+>", "", title_html)
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()
            url = self._unwrap_duckduckgo_url(html.unescape(href))
            if title and url:
                results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= limit:
                break
        return results

    def _unwrap_duckduckgo_url(self, href: str) -> str:
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
        return href

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are allowed.")
        if not parsed.netloc:
            raise ValueError("URL host is required.")

    def _safe_path(self, path: str) -> Path:
        if not str(path).strip():
            raise ValueError("Path is required.")
        candidate = (self.workspace_root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise ValueError("Path must stay inside the workspace.")
        return candidate

    def _filename_from_url(self, url: str) -> str:
        parsed = urlsplit(url)
        name = Path(unquote(parsed.path)).name
        if not name:
            name = "download.bin"
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return safe or "download.bin"

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace_root))
        except ValueError:
            return str(path)

    def _sha256_file(self, path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
        return digest.hexdigest(), size

    def _elapsed_ms(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _error(self, command: str, message: str, started: float, *, url: str | None = None, path: str | None = None) -> ExternalIOResult:
        return ExternalIOResult(
            ok=False,
            command=command,
            message=message,
            path=path,
            url=url,
            duration_ms=self._elapsed_ms(started),
            error=message,
        )
