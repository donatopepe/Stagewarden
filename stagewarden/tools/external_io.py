from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any
import tarfile
import zipfile
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
    hash_algorithm: str | None = None
    digest: str | None = None
    content_type: str | None = None
    duration_ms: int = 0
    items: list[dict[str, str]] | None = None
    retryable: bool = False
    error_type: str | None = None
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
            "hash_algorithm": self.hash_algorithm,
            "digest": self.digest,
            "content_type": self.content_type,
            "duration_ms": self.duration_ms,
            "items": list(self.items or []),
            "retryable": self.retryable,
            "error_type": self.error_type,
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
                hash_algorithm="sha256",
                digest=digest,
                content_type=mimetypes.guess_type(target.name)[0],
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, ValueError) as exc:
            return self._error("checksum", str(exc), started, path=path)

    def hash_file(self, path: str, *, algorithm: str = "sha256") -> ExternalIOResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise ValueError("Target path is not a file.")
            digest = self._hash_file(target, algorithm)
            size = target.stat().st_size
            return ExternalIOResult(
                ok=True,
                command="hash",
                message=f"{algorithm.upper()} computed for {self._display_path(target)}.",
                path=self._display_path(target),
                bytes_written=size,
                sha256=digest if algorithm.lower() == "sha256" else None,
                hash_algorithm=algorithm.lower().replace("-", ""),
                digest=digest,
                content_type=mimetypes.guess_type(target.name)[0],
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, ValueError) as exc:
            return self._error("hash", str(exc), started, path=path)

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
                hash_algorithm="sha256",
                digest=digest.hexdigest(),
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
                hash_algorithm="sha256",
                digest=digest,
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
                hash_algorithm="sha256",
                digest=digest,
                content_type="application/gzip",
                duration_ms=self._elapsed_ms(started),
            )
        except (OSError, EOFError, ValueError, gzip.BadGzipFile) as exc:
            return self._error("archive verify", str(exc), started, path=path)

    def archive_list(self, path: str) -> ExternalIOResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise ValueError("Archive path is not a file.")
            items = self._archive_members(target)
            return ExternalIOResult(
                ok=True,
                command="archive list",
                message=f"Listed {len(items)} archive member(s).",
                path=self._display_path(target),
                bytes_written=target.stat().st_size,
                content_type=mimetypes.guess_type(target.name)[0],
                duration_ms=self._elapsed_ms(started),
                items=items,
                hash_algorithm="sha256",
                digest=self._sha256_file(target)[0],
            )
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            return self._error("archive list", str(exc), started, path=path)

    def archive_extract(self, path: str, destination: str | None = None) -> ExternalIOResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise ValueError("Archive path is not a file.")
            extract_root = self._safe_path(destination or self._archive_stem_name(target))
            extract_root.mkdir(parents=True, exist_ok=True)
            extracted = self._extract_archive(target, extract_root)
            digest, size = self._sha256_file(target)
            return ExternalIOResult(
                ok=True,
                command="archive extract",
                message=f"Extracted {len(extracted)} member(s) to {self._display_path(extract_root)}.",
                path=self._display_path(extract_root),
                bytes_written=size,
                sha256=digest,
                hash_algorithm="sha256",
                digest=digest,
                content_type=mimetypes.guess_type(target.name)[0],
                duration_ms=self._elapsed_ms(started),
                items=extracted,
            )
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            return self._error("archive extract", str(exc), started, path=destination or path)

    def archive_create(self, source: str, destination: str | None = None, *, format: str | None = None) -> ExternalIOResult:
        started = time.monotonic()
        try:
            source_path = self._safe_path(source)
            if not source_path.exists():
                raise ValueError("Source path does not exist.")
            target = self._safe_path(destination or self._archive_default_name(source_path, format))
            target.parent.mkdir(parents=True, exist_ok=True)
            archive_format = self._resolve_archive_format(target, format)
            base_name = self._archive_base_name(target, archive_format)
            root_dir = str(source_path.parent)
            base_dir = source_path.name
            created = shutil.make_archive(base_name, archive_format, root_dir=root_dir, base_dir=base_dir)
            created_path = Path(created)
            digest, size = self._sha256_file(created_path)
            items = self._archive_members(created_path)
            return ExternalIOResult(
                ok=True,
                command="archive create",
                message=f"Created {archive_format} archive {self._display_path(created_path)}.",
                path=self._display_path(created_path),
                bytes_written=size,
                sha256=digest,
                hash_algorithm="sha256",
                digest=digest,
                content_type=mimetypes.guess_type(created_path.name)[0],
                duration_ms=self._elapsed_ms(started),
                items=items,
            )
        except (OSError, ValueError, shutil.Error, tarfile.TarError, zipfile.BadZipFile) as exc:
            return self._error("archive create", str(exc), started, path=destination or source)

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
                sha256=(digest := hashlib.sha256(raw).hexdigest()),
                hash_algorithm="sha256",
                digest=digest,
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

    def _hash_file(self, path: Path, algorithm: str) -> str:
        normalized = algorithm.strip().lower().replace("-", "")
        try:
            hasher = hashlib.new(normalized)
        except ValueError as exc:
            raise ValueError("Unsupported hash algorithm.") from exc
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def _archive_default_name(self, source: Path, format: str | None) -> str:
        return f"{source.name}{self._archive_suffix_for_format(format)}"

    def _archive_stem_name(self, path: Path) -> str:
        lowered = path.name.lower()
        for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".zip", ".tar", ".gz", ".bz2", ".xz"):
            if lowered.endswith(suffix):
                return path.name[: -len(suffix)]
        return path.stem or path.name

    def _archive_suffix_for_format(self, format: str | None) -> str:
        normalized = (format or "tar").strip().lower()
        return {
            "zip": ".zip",
            "tar": ".tar",
            "gztar": ".tar.gz",
            "bztar": ".tar.bz2",
            "xztar": ".tar.xz",
        }.get(normalized, ".tar")

    def _archive_base_name(self, target: Path, archive_format: str) -> str:
        suffix = self._archive_suffix_for_format(archive_format)
        name = target.name
        lowered = name.lower()
        if lowered.endswith(suffix):
            return str(target.with_name(name[: -len(suffix)]))
        return str(target)

    def _resolve_archive_format(self, target: Path, format: str | None) -> str:
        if format:
            normalized = format.strip().lower()
        else:
            suffix = "".join(target.suffixes).lower()
            normalized = {
                ".zip": "zip",
                ".tar": "tar",
                ".tar.gz": "gztar",
                ".tgz": "gztar",
                ".tar.bz2": "bztar",
                ".tbz2": "bztar",
                ".tar.xz": "xztar",
                ".txz": "xztar",
            }.get(suffix, "zip")
        if normalized not in {"zip", "tar", "gztar", "bztar", "xztar"}:
            raise ValueError("Unsupported archive format.")
        return normalized

    def _archive_members(self, path: Path) -> list[dict[str, str]]:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return [
                    {
                        "name": item.filename,
                        "size": str(item.file_size),
                        "compressed_size": str(item.compress_size),
                    }
                    for item in archive.infolist()
                ]
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                items: list[dict[str, str]] = []
                for member in archive.getmembers():
                    items.append(
                        {
                            "name": member.name,
                            "size": str(member.size),
                            "type": member.type.decode("utf-8", errors="ignore") if isinstance(member.type, bytes) else str(member.type),
                        }
                    )
                return items
        if path.suffix == ".gz":
            return [{"name": path.name, "size": str(path.stat().st_size), "compressed_size": str(path.stat().st_size)}]
        raise ValueError("Unsupported archive format.")

    def _extract_archive(self, path: Path, destination: Path) -> list[dict[str, str]]:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    extracted = (destination / member.filename).resolve()
                    if not str(extracted).startswith(str(destination.resolve())):
                        raise ValueError(f"Archive member '{member.filename}' attempts path traversal.")
                archive.extractall(destination)
                return [{"name": item.filename, "size": str(item.file_size)} for item in archive.infolist()]
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    extracted = (destination / member.name).resolve()
                    if not str(extracted).startswith(str(destination.resolve())):
                        raise ValueError(f"Archive member '{member.name}' attempts path traversal.")
                archive.extractall(destination)
                return [{"name": member.name, "size": str(member.size)} for member in archive.getmembers()]
        if path.suffix == ".gz":
            target = destination / path.with_suffix("").name
            with gzip.open(path, "rb") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            return [{"name": target.name, "size": str(target.stat().st_size)}]
        raise ValueError("Unsupported archive format.")

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
        retryable = self._is_transient_network_error(message)
        return ExternalIOResult(
            ok=False,
            command=command,
            message=message if not retryable else f"{message} The run is safe to resume when connectivity returns.",
            path=path,
            url=url,
            duration_ms=self._elapsed_ms(started),
            retryable=retryable,
            error_type="network_wait" if retryable else "external_io_error",
            error=message,
        )

    def _is_transient_network_error(self, message: str | None) -> bool:
        if not message:
            return False
        lowered = message.lower()
        patterns = (
            "connection refused",
            "connection reset",
            "connection aborted",
            "network is unreachable",
            "temporary failure in name resolution",
            "name or service not known",
            "no route to host",
            "host unreachable",
            "timed out",
            "timeout",
            "request timed out",
            "read timed out",
            "write timed out",
            "ssl",
            "tls",
            "certificate verify failed",
            "proxy error",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "network error",
            "network unavailable",
            "network outage",
            "outage",
            "blackout",
            "fetch failed",
            "failed to connect",
            "dns",
            "name resolution",
            "provider unavailable",
            "service outage",
            "maintenance",
        )
        return any(pattern in lowered for pattern in patterns)
