from __future__ import annotations

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
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def diff(self, *, staged: bool = False) -> GitResult:
        return self._run(["git", "diff", "--cached"] if staged else ["git", "diff"])

    def commit(self, message: str) -> GitResult:
        add_result = self._run(["git", "add", "-A"])
        if not add_result.ok:
            return add_result
        return self._run(["git", "commit", "-m", message])

    def _run(self, command: list[str]) -> GitResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.workspace_root,
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
