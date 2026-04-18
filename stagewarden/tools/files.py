from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import AgentConfig
from ..textcodec import contains_raw_non_ascii, detect_confusables, read_text_utf8, to_ascii_safe_text, write_text_utf8


@dataclass(slots=True)
class FileResult:
    ok: bool
    path: str = ""
    content: str = ""
    error: str = ""
    matches: list[str] | None = None
    warnings: list[str] | None = None


class FileTool:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

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

    def write(self, path: str, content: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            final_content, warnings = self._prepare_output_text(resolved, content)
            write_text_utf8(resolved, final_content)
            return FileResult(True, path=str(resolved), content=final_content, warnings=warnings)
        except OSError as exc:
            return FileResult(False, path=str(resolved), error=str(exc))

    def apply_patch(self, path: str, search: str, replace: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")

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

    def patch(self, path: str, diff: str) -> FileResult:
        resolved = self.config.resolve_path(path)
        if not self.config.is_within_workspace(resolved):
            return FileResult(False, path=str(resolved), error="Path is outside the workspace.")
        if not resolved.exists():
            return FileResult(False, path=str(resolved), error="File does not exist.")
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
        file_patches = self._parse_file_patches(diff)
        if not file_patches:
            return FileResult(False, error="No valid file patches found.")

        staged_writes: dict[Path, str] = {}
        staged_deletes: list[Path] = []
        changed_paths: list[str] = []

        for patch in file_patches:
            target = self._target_path(patch["old_path"], patch["new_path"])
            if target is None:
                return FileResult(False, error="Patch target is invalid.")
            if not self.config.is_within_workspace(target):
                return FileResult(False, error=f"Path is outside the workspace: {target}")

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
                changed_paths.append(str(target.relative_to(self.config.workspace_root_resolved)))
                continue

            if operation == "delete":
                if not target.exists():
                    return FileResult(False, error=f"Cannot delete missing file: {target}")
                updated = self._apply_unified_patch(current, hunks)
                if updated is None or updated != "":
                    return FileResult(False, error=f"Unable to apply delete patch: {target}")
                staged_deletes.append(target)
                changed_paths.append(str(target.relative_to(self.config.workspace_root_resolved)))
                continue

            if not target.exists():
                return FileResult(False, error=f"Cannot patch missing file: {target}")
            updated = self._apply_unified_patch(current, hunks)
            if updated is None:
                return FileResult(False, error=f"Unable to apply patch: {target}")
            staged_writes[target] = updated
            changed_paths.append(str(target.relative_to(self.config.workspace_root_resolved)))

        for path, content in staged_writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            final_content, _warnings = self._prepare_output_text(path, content)
            write_text_utf8(path, final_content)
        for path in staged_deletes:
            path.unlink()
        return FileResult(True, content="\n".join(changed_paths), matches=changed_paths)

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
