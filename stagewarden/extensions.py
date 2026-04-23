from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .textcodec import dumps_ascii, read_text_utf8, write_text_utf8


EXTENSION_ROOT = ".stagewarden/extensions"
EXTENSION_MANIFEST = "extension.json"
EXTENSION_SUBDIRS = ("commands", "roles", "skills", "hooks", "mcp")


@dataclass(frozen=True)
class ExtensionRecord:
    name: str
    path: str
    manifest_path: str
    ok: bool
    message: str
    version: str | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    schema_version: str | None = None
    execution: str | None = None
    entrypoints: dict[str, str] | None = None
    missing_entrypoints: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "manifest_path": self.manifest_path,
            "ok": self.ok,
            "message": self.message,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities or []),
            "schema_version": self.schema_version,
            "execution": self.execution,
            "entrypoints": dict(self.entrypoints or {}),
            "missing_entrypoints": list(self.missing_entrypoints or []),
        }


def safe_extension_name(name: str) -> str:
    cleaned = name.strip().lower().replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", cleaned):
        raise ValueError("Extension name must match [a-z0-9][a-z0-9._-]{0,63}.")
    if ".." in cleaned or cleaned.startswith("."):
        raise ValueError("Extension name must not contain traversal or hidden-path prefixes.")
    return cleaned


def extension_root(workspace: Path) -> Path:
    return (workspace / EXTENSION_ROOT).resolve()


def _default_entrypoints() -> dict[str, str]:
    return {name: f"{name}/" for name in EXTENSION_SUBDIRS}


def _validate_extension_manifest(workspace: Path, candidate: Path, payload: dict[str, Any]) -> ExtensionRecord:
    name = safe_extension_name(str(payload.get("name") or candidate.name))
    capabilities = payload.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be a list")
    execution = str(payload.get("execution") or "disabled-by-default").strip()
    if execution not in {"disabled-by-default", "manual-only"}:
        raise ValueError("execution must be disabled-by-default or manual-only")
    entrypoints = payload.get("entrypoints") or _default_entrypoints()
    if not isinstance(entrypoints, dict):
        raise ValueError("entrypoints must be an object")
    validated_entrypoints: dict[str, str] = {}
    missing_entrypoints: list[str] = []
    for subdir in EXTENSION_SUBDIRS:
        raw_value = entrypoints.get(subdir)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"entrypoints.{subdir} must be a non-empty string")
        relative = raw_value.strip()
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError(f"entrypoints.{subdir} must stay inside the extension directory")
        validated_entrypoints[subdir] = relative
        target = (candidate / relative).resolve()
        if not target.exists():
            missing_entrypoints.append(subdir)
    if missing_entrypoints:
        message = f"missing entrypoints: {', '.join(missing_entrypoints)}"
        ok = False
    else:
        message = "ok"
        ok = True
    return ExtensionRecord(
        name=name,
        path=str(candidate.relative_to(workspace)),
        manifest_path=str((candidate / EXTENSION_MANIFEST).relative_to(workspace)),
        ok=ok,
        message=message,
        version=str(payload.get("version") or ""),
        description=str(payload.get("description") or ""),
        capabilities=[str(item) for item in capabilities],
        schema_version=str(payload.get("schema_version") or "1"),
        execution=execution,
        entrypoints=validated_entrypoints,
        missing_entrypoints=missing_entrypoints,
    )


def scaffold_extension(workspace: Path, name: str) -> dict[str, Any]:
    safe_name = safe_extension_name(name)
    root = extension_root(workspace)
    target = (root / safe_name).resolve()
    if root not in target.parents:
        raise ValueError("Extension path must stay inside the extension root.")
    target.mkdir(parents=True, exist_ok=True)
    created_dirs: list[str] = []
    for subdir in EXTENSION_SUBDIRS:
        path = target / subdir
        path.mkdir(exist_ok=True)
        created_dirs.append(str(path.relative_to(workspace)))
    manifest = target / EXTENSION_MANIFEST
    if not manifest.exists():
        payload = {
            "name": safe_name,
            "schema_version": "1",
            "version": "0.1.0",
            "description": "Stagewarden extension scaffold.",
            "capabilities": [],
            "entrypoints": _default_entrypoints(),
            "execution": "disabled-by-default",
        }
        write_text_utf8(manifest, dumps_ascii(payload, indent=2) + "\n")
    return {
        "command": "extension scaffold",
        "ok": True,
        "name": safe_name,
        "path": str(target.relative_to(workspace)),
        "manifest": str(manifest.relative_to(workspace)),
        "created_dirs": created_dirs,
    }


def discover_extensions(workspace: Path) -> dict[str, Any]:
    root = extension_root(workspace)
    records: list[ExtensionRecord] = []
    if not root.exists():
        return {"command": "extensions", "root": EXTENSION_ROOT, "ok": True, "count": 0, "extensions": []}
    for candidate in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest = candidate / EXTENSION_MANIFEST
        if not manifest.exists():
            records.append(
                ExtensionRecord(
                    name=candidate.name,
                    path=str(candidate.relative_to(workspace)),
                    manifest_path=str(manifest.relative_to(workspace)),
                    ok=False,
                    message="manifest missing",
                )
            )
            continue
        try:
            payload = json.loads(read_text_utf8(manifest))
            if not isinstance(payload, dict):
                raise ValueError("manifest root must be an object")
            records.append(_validate_extension_manifest(workspace, candidate, payload))
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            records.append(
                ExtensionRecord(
                    name=candidate.name,
                    path=str(candidate.relative_to(workspace)),
                    manifest_path=str(manifest.relative_to(workspace)),
                    ok=False,
                    message=str(exc),
                )
            )
    return {
        "command": "extensions",
        "root": EXTENSION_ROOT,
        "ok": all(record.ok for record in records),
        "count": len(records),
        "extensions": [record.as_dict() for record in records],
    }
