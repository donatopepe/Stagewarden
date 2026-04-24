from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AgentConfig
from ..permissions import PermissionPolicy
from ..textcodec import contains_raw_non_ascii, detect_confusables, read_text_utf8, to_ascii_safe_text, write_text_utf8


@dataclass(slots=True)
class FileResult:
    ok: bool
    path: str = ""
    content: str = ""
    error: str = ""
    matches: list[str] | None = None
    warnings: list[str] | None = None
    report: dict[str, Any] | None = None


class FileTool:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.permissions = PermissionPolicy.load(config.settings_path, config.session_permission_settings)

    def refresh_permissions(self) -> None:
        self.permissions = PermissionPolicy.load(self.config.settings_path, self.config.session_permission_settings)

    def read(self, path: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        try:
            return FileResult(True, path=str(resolved), content=read_text_utf8(resolved))
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))

    def inspect(self, path: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        try:
            text, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        warnings = detect_confusables(text)
        report = {
            "command": "file inspect",
            "path": str(resolved),
            "encoding": meta["encoding"],
            "encoding_confidence": meta["encoding_confidence"],
            "byte_count": meta["byte_count"],
            "char_count": len(text),
            "line_count": len(text.splitlines()),
            "newline": meta["newline"],
            "has_bom": meta["has_bom"],
            "ascii_only": not contains_raw_non_ascii(text),
            "warnings": warnings,
        }
        return FileResult(True, path=str(resolved), content=text, warnings=warnings, report=report)

    def inspect_metadata(self, path: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="Path does not exist.")
        try:
            report = self._stat_report(resolved)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        return FileResult(True, path=str(resolved), content="", report=report)

    def write(self, path: str, content: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            final_content, warnings = self._prepare_output_text(resolved, content)
            write_text_utf8(resolved, final_content)
            return FileResult(True, path=str(resolved), content=final_content, warnings=warnings)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))

    def _approve_permission(self, capability: str, detail: str, decision: object) -> bool:
        approver = self.config.permission_approver
        if approver is None:
            return False
        try:
            approved = bool(approver(capability, detail, decision))  # type: ignore[arg-type]
        except (OSError, EOFError):
            return False
        if approved:
            self.refresh_permissions()
        return approved

    def _check_write_permission(self, resolved: Path) -> FileResult | None:
        detail = str(resolved.relative_to(self.config.workspace_root_resolved))
        decision = self.permissions.decide("file:write", detail)
        if decision.allowed:
            return None
        if decision.source.startswith("ask:") and self._approve_permission("file:write", detail, decision):
            return None
        return FileResult(False, path=str(resolved), error=decision.message or "Permission denied.")

    def apply_patch(self, path: str, search: str, replace: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied

        try:
            original = read_text_utf8(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))

        if search not in original:
            return FileResult(False, path=str(resolved), error="Search text not found.")

        updated = original.replace(search, replace, 1)
        try:
            final_content, warnings = self._prepare_output_text(resolved, updated)
            write_text_utf8(resolved, final_content)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        return FileResult(True, path=str(resolved), content=final_content, warnings=warnings)

    def search_replace(self, path: str, search: str, replace: str, *, count: int = 1, dry_run: bool = False) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if not search:
            return FileResult(False, path=str(resolved), error="Search text must not be empty.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        match_count = original.count(search)
        if match_count == 0:
            return FileResult(False, path=str(resolved), error="Search text not found.")
        applied_count = match_count if count <= 0 else min(match_count, count)
        updated = original.replace(search, replace, applied_count)
        return self._finalize_text_edit(
            resolved,
            original,
            updated,
            operation="search_replace",
            dry_run=dry_run,
            encoding=str(meta["encoding"]),
            newline=str(meta["newline"]),
            extra_report={
                "search": search,
                "replace": replace,
                "match_count": match_count,
                "applied_count": applied_count,
            },
        )

    def replace_range(self, path: str, start_line: int, end_line: int, content: str, *, dry_run: bool = False) -> FileResult:
        return self._line_edit(
            path,
            operation="replace_range",
            dry_run=dry_run,
            start_line=start_line,
            end_line=end_line,
            new_content=content,
        )

    def convert_encoding(
        self,
        path: str,
        target_encoding: str,
        *,
        source_encoding: str | None = None,
        dry_run: bool = False,
    ) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original_text, meta = self._read_text_with_metadata(resolved, forced_encoding=source_encoding)
        except (OSError, UnicodeDecodeError, LookupError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        normalized_target = self._normalize_encoding_name(target_encoding)
        try:
            original_text.encode(normalized_target)
        except UnicodeEncodeError as exc:
            return FileResult(
                False,
                path=str(resolved),
                error=f"Target encoding cannot represent file contents: {exc}",
                report={
                    "operation": "convert_encoding",
                    "path": str(resolved),
                    "dry_run": dry_run,
                    "changed": False,
                    "source_encoding": meta["encoding"],
                    "target_encoding": normalized_target,
                    "newline": meta["newline"],
                },
            )
        changed = self._normalize_encoding_name(str(meta["encoding"])) != normalized_target
        report = {
            "operation": "convert_encoding",
            "path": str(resolved),
            "dry_run": dry_run,
            "changed": changed,
            "source_encoding": meta["encoding"],
            "target_encoding": normalized_target,
            "newline": meta["newline"],
            "byte_count": meta["byte_count"],
        }
        if not changed:
            return FileResult(True, path=str(resolved), content="No changes.", report=report)
        if dry_run:
            return FileResult(
                True,
                path=str(resolved),
                content=f"Dry-run preview for convert_encoding: {meta['encoding']} -> {normalized_target}",
                report=report,
            )
        try:
            final_content, warnings = self._prepare_preserving_text(resolved, original_text)
            self._write_text_with_encoding(resolved, final_content, normalized_target)
            report["written"] = True
            return FileResult(True, path=str(resolved), content=final_content, warnings=warnings, report=report)
        except (OSError, UnicodeEncodeError, LookupError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc), report=report)

    def normalize_line_endings(
        self,
        path: str,
        newline: str,
        *,
        dry_run: bool = False,
    ) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if newline not in {"lf", "crlf", "cr"}:
            return FileResult(False, path=str(resolved), error="newline must be one of: lf, crlf, cr.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        target_newline = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[newline]
        normalized = original.replace("\r\n", "\n").replace("\r", "\n").replace("\n", target_newline)
        return self._finalize_text_edit(
            resolved,
            original,
            normalized,
            operation="normalize_line_endings",
            dry_run=dry_run,
            encoding=str(meta["encoding"]),
            newline=target_newline,
            preserve_content=True,
            extra_report={
                "source_newline": meta["newline"],
                "target_newline": target_newline,
            },
        )

    def copy_path(self, source: str, destination: str, *, overwrite: bool = False, dry_run: bool = False) -> FileResult:
        resolved_source = self.config.resolve_path(source)
        resolved_destination = self.config.resolve_path(destination)
        source_error = self._validate_workspace_path(resolved_source, require_exists=True, noun="Source")
        if source_error is not None:
            return source_error
        destination_error = self._validate_workspace_path(resolved_destination, require_exists=False, noun="Destination")
        if destination_error is not None:
            return destination_error
        denied = self._check_write_permission(resolved_destination)
        if denied is not None:
            return denied
        destination_exists = resolved_destination.exists()
        if destination_exists and not overwrite:
            return FileResult(False, path=str(resolved_destination), error="Destination already exists.")
        report = {
            "operation": "copy_path",
            "source_path": str(resolved_source),
            "destination_path": str(resolved_destination),
            "source_kind": self._path_kind(resolved_source),
            "destination_exists": destination_exists,
            "overwrite": overwrite,
            "dry_run": dry_run,
            "changed": True,
        }
        if dry_run:
            return FileResult(True, path=str(resolved_destination), content="Dry-run preview for copy_path.", report=report)
        try:
            if destination_exists:
                self._remove_path(resolved_destination, recursive=True)
            resolved_destination.parent.mkdir(parents=True, exist_ok=True)
            if resolved_source.is_dir():
                shutil.copytree(resolved_source, resolved_destination)
            else:
                shutil.copy2(resolved_source, resolved_destination)
            report["written"] = True
            return FileResult(True, path=str(resolved_destination), content=f"Copied {source} -> {destination}", report=report)
        except OSError as exc:
            return FileResult(False, path=str(resolved_destination), error=str(exc), report=report)

    def move_path(self, source: str, destination: str, *, overwrite: bool = False, dry_run: bool = False) -> FileResult:
        resolved_source = self.config.resolve_path(source)
        resolved_destination = self.config.resolve_path(destination)
        source_error = self._validate_workspace_path(resolved_source, require_exists=True, noun="Source")
        if source_error is not None:
            return source_error
        destination_error = self._validate_workspace_path(resolved_destination, require_exists=False, noun="Destination")
        if destination_error is not None:
            return destination_error
        denied = self._check_write_permission(resolved_source)
        if denied is not None:
            return denied
        denied = self._check_write_permission(resolved_destination)
        if denied is not None:
            return denied
        destination_exists = resolved_destination.exists()
        if destination_exists and not overwrite:
            return FileResult(False, path=str(resolved_destination), error="Destination already exists.")
        report = {
            "operation": "move_path",
            "source_path": str(resolved_source),
            "destination_path": str(resolved_destination),
            "source_kind": self._path_kind(resolved_source),
            "destination_exists": destination_exists,
            "overwrite": overwrite,
            "dry_run": dry_run,
            "changed": True,
        }
        if dry_run:
            return FileResult(True, path=str(resolved_destination), content="Dry-run preview for move_path.", report=report)
        try:
            if destination_exists:
                self._remove_path(resolved_destination, recursive=True)
            resolved_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved_source), str(resolved_destination))
            report["written"] = True
            return FileResult(True, path=str(resolved_destination), content=f"Moved {source} -> {destination}", report=report)
        except (OSError, shutil.Error) as exc:
            return FileResult(False, path=str(resolved_destination), error=str(exc), report=report)

    def delete_path(self, path: str, *, recursive: bool = False, dry_run: bool = False) -> FileResult:
        resolved = self.config.resolve_path(path)
        error = self._validate_workspace_path(resolved, require_exists=True, noun="Path")
        if error is not None:
            return error
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied
        is_dir = resolved.is_dir() and not resolved.is_symlink()
        if is_dir and any(resolved.iterdir()) and not recursive:
            return FileResult(False, path=str(resolved), error="Directory is not empty; use recursive delete.")
        report = {
            "operation": "delete_path",
            "path": str(resolved),
            "kind": self._path_kind(resolved),
            "recursive": recursive,
            "dry_run": dry_run,
            "changed": True,
        }
        if dry_run:
            return FileResult(True, path=str(resolved), content="Dry-run preview for delete_path.", report=report)
        try:
            self._remove_path(resolved, recursive=recursive)
            report["written"] = True
            return FileResult(True, path=str(resolved), content=f"Deleted {path}", report=report)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc), report=report)

    def chmod_path(self, path: str, mode: str | int, *, recursive: bool = False, dry_run: bool = False) -> FileResult:
        resolved = self.config.resolve_path(path)
        error = self._validate_workspace_path(resolved, require_exists=True, noun="Path")
        if error is not None:
            return error
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied
        try:
            normalized_mode = self._parse_mode(mode)
        except ValueError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        targets = self._iter_permission_targets(resolved, recursive=recursive)
        report = {
            "operation": "chmod_path",
            "path": str(resolved),
            "mode": f"{normalized_mode:04o}",
            "recursive": recursive,
            "dry_run": dry_run,
            "target_count": len(targets),
            "changed": True,
        }
        if dry_run:
            return FileResult(True, path=str(resolved), content="Dry-run preview for chmod_path.", report=report)
        try:
            for target in targets:
                target.chmod(normalized_mode)
            report["written"] = True
            return FileResult(True, path=str(resolved), content=f"Updated mode to {normalized_mode:04o}", report=report)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc), report=report)

    def chown_path(
        self,
        path: str,
        *,
        user: str | int | None = None,
        group: str | int | None = None,
        recursive: bool = False,
        dry_run: bool = False,
    ) -> FileResult:
        resolved = self.config.resolve_path(path)
        error = self._validate_workspace_path(resolved, require_exists=True, noun="Path")
        if error is not None:
            return error
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied
        if not hasattr(os, "chown"):
            return FileResult(False, path=str(resolved), error="chown is not supported on this platform.")
        try:
            uid, gid = self._resolve_owner_group(resolved, user=user, group=group)
        except (KeyError, ValueError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        targets = self._iter_permission_targets(resolved, recursive=recursive)
        report = {
            "operation": "chown_path",
            "path": str(resolved),
            "uid": uid,
            "gid": gid,
            "recursive": recursive,
            "dry_run": dry_run,
            "target_count": len(targets),
            "changed": True,
        }
        if dry_run:
            return FileResult(True, path=str(resolved), content="Dry-run preview for chown_path.", report=report)
        try:
            for target in targets:
                os.chown(target, uid, gid)
            report["written"] = True
            return FileResult(True, path=str(resolved), content=f"Updated owner to uid={uid} gid={gid}", report=report)
        except PermissionError as exc:
            return FileResult(False, path=str(resolved), error=f"chown permission denied: {exc}", report=report)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc), report=report)

    def delete_range(self, path: str, start_line: int, end_line: int, *, dry_run: bool = False) -> FileResult:
        return self._line_edit(
            path,
            operation="delete_range",
            dry_run=dry_run,
            start_line=start_line,
            end_line=end_line,
            new_content="",
        )

    def insert_text(
        self,
        path: str,
        content: str,
        *,
        line_number: int | None = None,
        pattern: str | None = None,
        position: str = "after",
        occurrence: int = 1,
        dry_run: bool = False,
    ) -> FileResult:
        if position not in {"before", "after"}:
            return FileResult(False, error="position must be before or after.")
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        lines = original.splitlines(keepends=True)
        anchor_index = self._resolve_anchor_index(lines, line_number=line_number, pattern=pattern, occurrence=occurrence)
        if anchor_index is None:
            return FileResult(False, path=str(resolved), error="Anchor not found.")
        insert_at = anchor_index if position == "before" else anchor_index + 1
        block = self._coerce_block(content, str(meta["newline"]))
        updated_lines = list(lines)
        updated_lines[insert_at:insert_at] = block
        updated = "".join(updated_lines)
        return self._finalize_text_edit(
            resolved,
            original,
            updated,
            operation="insert_text",
            dry_run=dry_run,
            encoding=str(meta["encoding"]),
            newline=str(meta["newline"]),
            extra_report={
                "line_number": line_number,
                "pattern": pattern,
                "position": position,
                "occurrence": occurrence,
                "inserted_lines": len(block),
                "anchor_line": anchor_index + 1,
            },
        )

    def delete_backward(
        self,
        path: str,
        count: int,
        *,
        line_number: int | None = None,
        pattern: str | None = None,
        occurrence: int = 1,
        dry_run: bool = False,
    ) -> FileResult:
        if count <= 0:
            return FileResult(False, error="count must be positive.")
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        lines = original.splitlines(keepends=True)
        anchor_index = self._resolve_anchor_index(lines, line_number=line_number, pattern=pattern, occurrence=occurrence)
        if anchor_index is None:
            return FileResult(False, path=str(resolved), error="Anchor not found.")
        start = max(0, anchor_index - count)
        end = anchor_index
        if start == end:
            return FileResult(False, path=str(resolved), error="No lines available before the anchor.")
        updated_lines = list(lines)
        del updated_lines[start:end]
        updated = "".join(updated_lines)
        return self._finalize_text_edit(
            resolved,
            original,
            updated,
            operation="delete_backward",
            dry_run=dry_run,
            encoding=str(meta["encoding"]),
            newline=str(meta["newline"]),
            extra_report={
                "count": count,
                "line_number": line_number,
                "pattern": pattern,
                "occurrence": occurrence,
                "deleted_start_line": start + 1,
                "deleted_end_line": end,
                "anchor_line": anchor_index + 1,
            },
        )

    def patch(self, path: str, diff: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        denied = self._check_write_permission(resolved)
        if denied is not None:
            return denied
        try:
            original = read_text_utf8(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))

        hunks = self._parse_hunks(diff.splitlines())
        if not hunks:
            return FileResult(False, path=str(resolved), error="No valid hunks found.")
        updated = self._apply_unified_patch(original, hunks)
        if updated is None:
            return FileResult(False, path=str(resolved), error="Unable to apply patch.")
        try:
            final_content, warnings = self._prepare_output_text(resolved, updated)
            write_text_utf8(resolved, final_content)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        return FileResult(True, path=str(resolved), content=final_content, warnings=warnings)

    def patch_files(self, diff: str) -> FileResult:
        prepared = self._prepare_file_patches(diff, require_write_permission=True)
        if not prepared.ok:
            return prepared

        staged_writes: dict[Path, str] = {}
        staged_deletes: list[Path] = []
        summaries = prepared.matches or []

        for patch in self._parse_file_patches(diff):
            target = self._target_path(patch["old_path"], patch["new_path"])
            if target is None:  # Already validated by _prepare_file_patches.
                return FileResult(False, error="Patch target is invalid.")

            operation = patch["operation"]
            hunks = patch["hunks"]
            try:
                current = read_text_utf8(target) if target.exists() else ""
            except (OSError, UnicodeDecodeError) as exc:
                return FileResult(False, error=str(exc))

            if operation == "add":
                if target.exists():
                    return FileResult(False, error=f"Cannot add existing file: {target}")
                updated = self._apply_unified_patch("", hunks)
                if updated is None:
                    return FileResult(False, error=f"Unable to apply add patch: {target}")
                staged_writes[target] = updated
                continue

            if operation == "delete":
                if not target.exists():
                    return FileResult(False, error=f"Cannot delete missing file: {target}")
                updated = self._apply_unified_patch(current, hunks)
                if updated is None or updated != "":
                    return FileResult(False, error=f"Unable to apply delete patch: {target}")
                staged_deletes.append(target)
                continue

            if not target.exists():
                return FileResult(False, error=f"Cannot patch missing file: {target}")
            updated = self._apply_unified_patch(current, hunks)
            if updated is None:
                return FileResult(False, error=f"Unable to apply patch: {target}")
            staged_writes[target] = updated

        for path, content in staged_writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            final_content, _warnings = self._prepare_output_text(path, content)
            write_text_utf8(path, final_content)
        for path in staged_deletes:
            path.unlink()
        return FileResult(True, content="\n".join(summaries), matches=summaries)

    def preview_patch_files(self, diff: str) -> FileResult:
        return self._prepare_file_patches(diff, require_write_permission=False)

    def list_files(self, base_path: str = ".", pattern: str = "*", limit: int = 200) -> FileResult:
        base = self.config.resolve_path(base_path)
        workspace_root = self.config.workspace_root_resolved
        if not self.config.is_within_workspace(base):
            return FileResult(False, path=str(base), error="Base path is outside the workspace.")
        if not base.exists():
            return FileResult(False, path=str(base), error="Base path does not exist.")

        matches: list[str] = []
        for item in sorted(base.rglob("*")):
            if len(matches) >= limit:
                break
            if item.is_dir():
                continue
            rel = str(item.resolve().relative_to(workspace_root))
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(item.name, pattern):
                matches.append(rel)
        return FileResult(True, path=str(base), content="\n".join(matches), matches=matches)

    def search(self, pattern: str, base_path: str = ".", glob: str = "*", limit: int = 100) -> FileResult:
        base = self.config.resolve_path(base_path)
        workspace_root = self.config.workspace_root_resolved
        if not self.config.is_within_workspace(base):
            return FileResult(False, path=str(base), error="Base path is outside the workspace.")
        if not base.exists():
            return FileResult(False, path=str(base), error="Base path does not exist.")

        regex = re.compile(pattern, re.MULTILINE)
        hits: list[str] = []
        for item in sorted(base.rglob("*")):
            if len(hits) >= limit:
                break
            if item.is_dir():
                continue
            rel = str(item.resolve().relative_to(workspace_root))
            if not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(item.name, glob)):
                continue
            try:
                content = read_text_utf8(item)
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{rel}:{line_number}:{line.strip()}")
                    if len(hits) >= limit:
                        break
        return FileResult(True, path=str(base), content="\n".join(hits), matches=hits)

    def _target_path(self, old_path: str, new_path: str) -> Path | None:
        chosen = new_path if new_path != "/dev/null" else old_path
        if not chosen or chosen == "/dev/null":
            return None
        normalized = chosen[2:] if chosen.startswith(("a/", "b/")) else chosen
        return self.config.resolve_path(normalized)

    def _prepare_file_patches(self, diff: str, *, require_write_permission: bool) -> FileResult:
        file_patches = self._parse_file_patches(diff)
        if not file_patches:
            return FileResult(False, error="No valid file patches found.")

        summaries: list[str] = []
        seen_targets: set[Path] = set()
        for patch in file_patches:
            target = self._target_path(patch["old_path"], patch["new_path"])
            if target is None:
                return FileResult(False, error="Patch target is invalid.")
            if not self.config.is_within_workspace(target):
                return FileResult(False, error=f"Path is outside the workspace: {target}")
            if target in seen_targets:
                rel = target.relative_to(self.config.workspace_root_resolved)
                return FileResult(False, error=f"Ambiguous patch target appears more than once: {rel}")
            seen_targets.add(target)
            if require_write_permission:
                denied = self._check_write_permission(target)
                if denied is not None:
                    return FileResult(False, error=denied.error or f"Permission denied: {target}")

            operation = str(patch["operation"])
            rel_path = str(target.relative_to(self.config.workspace_root_resolved))
            hunks = patch["hunks"]
            try:
                current = read_text_utf8(target) if target.exists() else ""
            except (OSError, UnicodeDecodeError) as exc:
                return FileResult(False, error=str(exc))

            if operation == "add":
                if target.exists():
                    return FileResult(False, error=f"Cannot add existing file: {target}")
                updated = self._apply_unified_patch("", hunks)
                if updated is None:
                    return FileResult(False, error=f"Unable to apply add patch: {target}")
            elif operation == "delete":
                if not target.exists():
                    return FileResult(False, error=f"Cannot delete missing file: {target}")
                updated = self._apply_unified_patch(current, hunks)
                if updated is None or updated != "":
                    return FileResult(False, error=f"Unable to apply delete patch: {target}")
            else:
                if not target.exists():
                    return FileResult(False, error=f"Cannot patch missing file: {target}")
                updated = self._apply_unified_patch(current, hunks)
                if updated is None:
                    return FileResult(False, error=f"Unable to apply patch: {target}")
            summaries.append(f"{operation} {rel_path}")

        return FileResult(True, content="\n".join(summaries), matches=summaries)

    def _apply_unified_patch(self, original: str, hunks: list[tuple[int, int, int, int, list[tuple[str, str]]]]) -> str | None:
        lines = original.splitlines(keepends=True)
        offset = 0
        for start_old, _old_count, _start_new, _new_count, hunk_lines in hunks:
            pointer = max(start_old - 1 + offset, 0)
            if pointer > len(lines):
                return None

            cursor = pointer
            rebuilt: list[str] = []
            for marker, text in hunk_lines:
                normalized = text if text.endswith("\n") else f"{text}\n"
                if marker == " ":
                    if cursor >= len(lines) or lines[cursor] != normalized:
                        return None
                    rebuilt.append(lines[cursor])
                    cursor += 1
                elif marker == "-":
                    if cursor >= len(lines) or lines[cursor] != normalized:
                        return None
                    cursor += 1
                elif marker == "+":
                    rebuilt.append(normalized)
                else:
                    return None

            consumed = cursor - pointer
            lines[pointer:cursor] = rebuilt
            offset += len(rebuilt) - consumed
        return "".join(lines)

    def _parse_file_patches(self, diff: str) -> list[dict[str, object]]:
        lines = diff.splitlines()
        patches: list[dict[str, object]] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            if not line.startswith("--- "):
                index += 1
                continue
            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                return []

            old_path = lines[index][4:].strip()
            new_path = lines[index + 1][4:].strip()
            index += 2
            hunk_lines: list[str] = []

            while index < len(lines) and not lines[index].startswith("--- "):
                hunk_lines.append(lines[index])
                index += 1

            hunks = self._parse_hunks(hunk_lines)
            if not hunks:
                return []

            if old_path == "/dev/null":
                operation = "add"
            elif new_path == "/dev/null":
                operation = "delete"
            else:
                operation = "update"

            patches.append(
                {
                    "old_path": old_path,
                    "new_path": new_path,
                    "operation": operation,
                    "hunks": hunks,
                }
            )

        return patches

    def _parse_hunks(self, lines: list[str]) -> list[tuple[int, int, int, int, list[tuple[str, str]]]]:
        hunks: list[tuple[int, int, int, int, list[tuple[str, str]]]] = []
        current: tuple[int, int, int, int, list[tuple[str, str]]] | None = None

        for raw_line in lines:
            if raw_line.startswith("@@"):
                if current is not None:
                    hunks.append(current)
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw_line)
                if not match:
                    return []
                current = (
                    int(match.group(1)),
                    int(match.group(2) or "1"),
                    int(match.group(3)),
                    int(match.group(4) or "1"),
                    [],
                )
                continue
            if current is None:
                continue
            if raw_line.startswith("\\ No newline at end of file"):
                continue
            if not raw_line or raw_line[0] not in {" ", "+", "-"}:
                return []
            current[4].append((raw_line[0], raw_line[1:]))

        if current is not None:
            hunks.append(current)
        return hunks

    def _prepare_output_text(self, path: Path, content: str) -> tuple[str, list[str]]:
        warnings = detect_confusables(content)
        sensitive = path.name.startswith(".") or any(path.name.endswith(pattern) for pattern in self.config.sensitive_ascii_patterns)
        if self.config.strict_ascii_output:
            return to_ascii_safe_text(content), warnings
        if sensitive and contains_raw_non_ascii(content):
            return to_ascii_safe_text(content), warnings + ["sensitive_file_ascii_forced"]
        return content, warnings

    def _prepare_preserving_text(self, path: Path, content: str) -> tuple[str, list[str]]:
        warnings = detect_confusables(content)
        return content, warnings

    def _line_edit(
        self,
        path: str,
        *,
        operation: str,
        dry_run: bool,
        start_line: int,
        end_line: int,
        new_content: str,
    ) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
        if start_line <= 0 or end_line < start_line:
            return FileResult(False, path=str(resolved), error="Invalid line range.")
        if not dry_run:
            denied = self._check_write_permission(resolved)
            if denied is not None:
                return denied
        try:
            original, meta = self._read_text_with_metadata(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return FileResult(False, path=str(resolved), error=str(exc))
        lines = original.splitlines(keepends=True)
        if end_line > len(lines):
            return FileResult(False, path=str(resolved), error="Line range exceeds file length.")
        replacement = self._coerce_block(new_content, str(meta["newline"]))
        updated_lines = list(lines)
        updated_lines[start_line - 1 : end_line] = replacement
        updated = "".join(updated_lines)
        return self._finalize_text_edit(
            resolved,
            original,
            updated,
            operation=operation,
            dry_run=dry_run,
            encoding=str(meta["encoding"]),
            newline=str(meta["newline"]),
            extra_report={
                "start_line": start_line,
                "end_line": end_line,
                "replacement_lines": len(replacement),
            },
        )

    def _resolve_anchor_index(
        self,
        lines: list[str],
        *,
        line_number: int | None,
        pattern: str | None,
        occurrence: int,
    ) -> int | None:
        if line_number is not None:
            if line_number <= 0 or line_number > len(lines):
                return None
            return line_number - 1
        if pattern:
            seen = 0
            for index, line in enumerate(lines):
                if pattern in line:
                    seen += 1
                    if seen == occurrence:
                        return index
        return None

    def _read_text_with_metadata(self, path: Path, *, forced_encoding: str | None = None) -> tuple[str, dict[str, object]]:
        raw = path.read_bytes()
        detected = self._detect_encoding(raw, forced_encoding=forced_encoding)
        text = raw.decode(str(detected["encoding"]))
        return text, {
            "encoding": detected["encoding"],
            "encoding_confidence": detected["encoding_confidence"],
            "byte_count": len(raw),
            "newline": self._detect_newline(text),
            "has_bom": detected["has_bom"],
        }

    def _detect_encoding(self, raw: bytes, *, forced_encoding: str | None = None) -> dict[str, object]:
        if forced_encoding:
            return {
                "encoding": self._normalize_encoding_name(forced_encoding),
                "encoding_confidence": "forced",
                "has_bom": raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")),
            }
        if raw.startswith(b"\xef\xbb\xbf"):
            return {"encoding": "utf-8-sig", "encoding_confidence": "bom", "has_bom": True}
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return {"encoding": "utf-16", "encoding_confidence": "bom", "has_bom": True}
        try:
            raw.decode("utf-8")
            return {"encoding": "utf-8", "encoding_confidence": "strict", "has_bom": False}
        except UnicodeDecodeError:
            pass
        if b"\x00" in raw:
            try:
                raw.decode("utf-16")
                return {"encoding": "utf-16", "encoding_confidence": "heuristic", "has_bom": False}
            except UnicodeDecodeError:
                pass
        return {"encoding": "latin-1", "encoding_confidence": "fallback", "has_bom": False}

    def _normalize_encoding_name(self, value: str) -> str:
        lowered = value.strip().lower().replace("_", "-")
        aliases = {
            "utf8": "utf-8",
            "utf-8": "utf-8",
            "utf-8-sig": "utf-8-sig",
            "utf16": "utf-16",
            "utf-16": "utf-16",
            "latin1": "latin-1",
            "latin-1": "latin-1",
            "cp1252": "cp1252",
            "windows-1252": "cp1252",
            "ascii": "ascii",
        }
        return aliases.get(lowered, lowered)

    def _detect_newline(self, text: str) -> str:
        if "\r\n" in text:
            return "\r\n"
        if "\r" in text:
            return "\r"
        return "\n"

    def _coerce_block(self, content: str, newline: str) -> list[str]:
        if not content:
            return []
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        if not normalized.endswith(newline):
            normalized += newline
        return normalized.splitlines(keepends=True)

    def _render_diff_preview(self, path: Path, original: str, updated: str) -> str:
        diff = difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=str(path),
            tofile=str(path),
            lineterm="",
            n=3,
        )
        preview = "\n".join(diff)
        return preview[:4000]

    def _write_text_with_encoding(self, path: Path, content: str, encoding: str) -> None:
        path.write_text(content, encoding=encoding, newline="")

    def _validate_workspace_path(self, path: Path, *, require_exists: bool, noun: str) -> FileResult | None:
        if not self.config.is_within_workspace(path):
            return FileResult(False, path=str(path), error=f"{noun} is outside the workspace.")
        if require_exists and not path.exists():
            return FileResult(False, path=str(path), error=f"{noun} does not exist.")
        return None

    def _path_kind(self, path: Path) -> str:
        if path.is_symlink():
            return "symlink"
        if path.is_dir():
            return "directory"
        if path.is_file():
            return "file"
        return "other"

    def _stat_report(self, path: Path) -> dict[str, object]:
        stats = path.stat()
        report: dict[str, object] = {
            "command": "file stat",
            "path": str(path),
            "kind": self._path_kind(path),
            "exists": path.exists(),
            "size": stats.st_size,
            "mode_octal": f"{stats.st_mode & 0o7777:04o}",
            "uid": getattr(stats, "st_uid", None),
            "gid": getattr(stats, "st_gid", None),
            "mtime": stats.st_mtime,
            "atime": stats.st_atime,
            "ctime": stats.st_ctime,
            "is_symlink": path.is_symlink(),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
            "executable": os.access(path, os.X_OK),
        }
        if path.is_symlink():
            try:
                report["symlink_target"] = str(path.resolve(strict=False))
            except OSError:
                report["symlink_target"] = "unresolved"
        return report

    def _remove_path(self, path: Path, *, recursive: bool) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return
        if path.is_dir():
            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()
            return
        raise OSError(f"Unsupported path type: {path}")

    def _iter_permission_targets(self, path: Path, *, recursive: bool) -> list[Path]:
        if not recursive or not path.is_dir() or path.is_symlink():
            return [path]
        targets = [path]
        targets.extend(sorted(item for item in path.rglob("*")))
        return targets

    def _parse_mode(self, mode: str | int) -> int:
        if isinstance(mode, int):
            if mode < 0:
                raise ValueError("mode must be a positive integer.")
            return mode
        raw = str(mode).strip().lower()
        if raw.startswith("0o"):
            raw = raw[2:]
        if not raw or any(char not in "01234567" for char in raw):
            raise ValueError("mode must be an octal value like 644 or 0755.")
        return int(raw, 8)

    def _resolve_owner_group(self, path: Path, *, user: str | int | None, group: str | int | None) -> tuple[int, int]:
        current = path.stat()
        uid = current.st_uid
        gid = current.st_gid
        if user is not None:
            uid = self._resolve_user(user)
        if group is not None:
            gid = self._resolve_group(group)
        if user is None and group is None:
            raise ValueError("At least one of user or group must be provided.")
        return uid, gid

    def _resolve_user(self, value: str | int) -> int:
        if isinstance(value, int):
            return value
        raw = str(value).strip()
        if raw.isdigit():
            return int(raw)
        try:
            import pwd

            return pwd.getpwnam(raw).pw_uid
        except ImportError as exc:
            raise ValueError("Named users are not supported on this platform.") from exc
        except KeyError as exc:
            raise KeyError(f"Unknown user: {raw}") from exc

    def _resolve_group(self, value: str | int) -> int:
        if isinstance(value, int):
            return value
        raw = str(value).strip()
        if raw.isdigit():
            return int(raw)
        try:
            import grp

            return grp.getgrnam(raw).gr_gid
        except ImportError as exc:
            raise ValueError("Named groups are not supported on this platform.") from exc
        except KeyError as exc:
            raise KeyError(f"Unknown group: {raw}") from exc

    def _finalize_text_edit(
        self,
        path: Path,
        original: str,
        updated: str,
        *,
        operation: str,
        dry_run: bool,
        encoding: str,
        newline: str,
        preserve_content: bool = False,
        extra_report: dict[str, Any],
    ) -> FileResult:
        changed = updated != original
        preview = self._render_diff_preview(path, original, updated) if changed else ""
        report = {
            "operation": operation,
            "path": str(path),
            "dry_run": dry_run,
            "changed": changed,
            "encoding": encoding,
            "newline": newline,
            "preview": preview,
            **extra_report,
        }
        if not changed:
            return FileResult(True, path=str(path), content="No changes.", report=report)
        if dry_run:
            return FileResult(True, path=str(path), content=f"Dry-run preview for {operation}:\n{preview}", report=report)
        try:
            if preserve_content:
                final_content, warnings = self._prepare_preserving_text(path, updated)
            else:
                final_content, warnings = self._prepare_output_text(path, updated)
            self._write_text_with_encoding(path, final_content, encoding)
            report["written"] = True
            return FileResult(True, path=str(path), content=final_content, warnings=warnings, report=report)
        except (OSError, UnicodeEncodeError) as exc:
            return FileResult(False, path=str(path), error=str(exc), report=report)
