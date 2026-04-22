from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from ..config import AgentConfig


@dataclass(slots=True)
class GitResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""


class GitTool:
    RUNTIME_IGNORES = (
        ".stagewarden_memory.json",
        ".stagewarden_caveman.json",
        ".stagewarden_trace.ljson",
        ".stagewarden_prince2_pid.json",
        ".stagewarden_models.json",
        ".stagewarden_settings.json",
        ".stagewarden_handoff.json",
    )

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def ensure_ready(self) -> GitResult:
        available = self.ensure_available()
        if not available.ok:
            return available
        initialized = self.ensure_repository()
        if not initialized.ok:
            return initialized
        ignored = self.ensure_runtime_ignores()
        if not ignored.ok:
            return ignored
        return GitResult(True, stdout="Git ready.")

    def ensure_available(self) -> GitResult:
        if shutil.which("git") is None:
            return GitResult(False, error="Git is required but was not found in PATH. Install git before running Stagewarden.")
        version = self._run(["git", "--version"], cwd=str(self.config.workspace_root))
        if not version.ok:
            return GitResult(False, error=version.error or "Git is required but is not usable.")
        return version

    def ensure_repository(self) -> GitResult:
        probe = self._run(["git", "rev-parse", "--is-inside-work-tree"])
        if probe.ok and probe.stdout.strip() == "true":
            return GitResult(True, stdout="Repository already initialized.")
        init = self._run(["git", "init"])
        if not init.ok:
            return init
        return GitResult(True, stdout=init.stdout or "Repository initialized.")

    def ensure_runtime_ignores(self) -> GitResult:
        ignore_path = self.config.workspace_root / ".gitignore"
        existing = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
        lines = existing.splitlines()
        changed = False
        for item in self.RUNTIME_IGNORES:
            if item not in lines:
                lines.append(item)
                changed = True
        if changed:
            ignore_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return GitResult(True, stdout=".gitignore ready.")

    def diff(self, *, staged: bool = False) -> GitResult:
        return self._run(["git", "diff", "--cached"] if staged else ["git", "diff"])

    def status(self) -> GitResult:
        return self._run(["git", "status", "--short", "--branch"])

    def status_porcelain(self) -> GitResult:
        return self._run(["git", "status", "--porcelain"])

    def log(self, *, limit: int = 20, path: str | None = None) -> GitResult:
        safe_limit = self._safe_limit(limit)
        command = [
            "git",
            "log",
            "--oneline",
            "--decorate",
            f"--max-count={safe_limit}",
        ]
        if path:
            command.extend(["--", path])
        return self._run(command)

    def show(self, *, revision: str = "HEAD", stat: bool = False) -> GitResult:
        rev = revision.strip() or "HEAD"
        command = ["git", "show", "--no-ext-diff"]
        if stat:
            command.append("--stat")
        command.append(rev)
        return self._run(command)

    def file_history(self, path: str, *, limit: int = 20) -> GitResult:
        if not path.strip():
            return GitResult(False, error="Path is required for git file history.")
        return self.log(limit=limit, path=path)

    def head(self, *, revision: str = "HEAD") -> GitResult:
        rev = revision.strip() or "HEAD"
        return self._run(["git", "rev-parse", rev])

    def has_changes(self) -> bool:
        result = self.status_porcelain()
        return result.ok and bool(result.stdout.strip())

    def commit(self, message: str) -> GitResult:
        add_result = self._run(["git", "add", "-A"])
        if not add_result.ok:
            return add_result
        staged = self._run(["git", "diff", "--cached", "--quiet"])
        if staged.ok:
            return GitResult(True, stdout="No changes to commit.")
        return self._run([
            "git",
            "-c",
            "user.name=Stagewarden",
            "-c",
            "user.email=stagewarden@local",
            "commit",
            "-m",
            message,
        ])

    def commit_if_changed(self, message: str) -> GitResult:
        if not self.has_changes():
            return GitResult(True, stdout="No changes to commit.")
        return self.commit(message)

    def _safe_limit(self, limit: int) -> int:
        return max(1, min(int(limit), 200))

    def _run(self, command: list[str], *, cwd: str | None = None) -> GitResult:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd or self.config.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.config.shell_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return GitResult(False, error="Git command timed out.")
        except OSError as exc:
            return GitResult(False, error=str(exc))

        return GitResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            error="" if completed.returncode == 0 else (completed.stderr.strip() or "Git command failed."),
        )
