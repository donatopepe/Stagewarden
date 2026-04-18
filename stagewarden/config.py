from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AgentConfig:
    workspace_root: Path
    max_steps: int = 20
    max_retries_per_step: int = 2
    model_timeout_seconds: int = 120
    shell_timeout_seconds: int = 120
    verbose: bool = False
    prefer_local: bool = True
    strict_ascii_output: bool = True
    memory_filename: str = ".stagewarden_memory.json"
    caveman_state_filename: str = ".stagewarden_caveman.json"
    trace_filename: str = ".stagewarden_trace.ljson"
    prince2_pid_filename: str = ".stagewarden_prince2_pid.json"
    model_prefs_filename: str = ".stagewarden_models.json"
    sensitive_ascii_patterns: tuple[str, ...] = (
        ".json",
        ".ljson",
        ".toml",
        ".yaml",
        ".yml",
        ".env",
        ".md",
        ".txt",
    )
    allowed_shell_prefixes: tuple[str, ...] = (
        "ls",
        "pwd",
        "cat",
        "echo",
        "find",
        "rg",
        "grep",
        "sed",
        "awk",
        "python",
        "python3",
        "pytest",
        "npm",
        "node",
        "git",
        "make",
        "bash",
        "sh",
        "pwsh",
        "powershell",
        "cmd",
        "where",
        "dir",
        "type",
        "copy",
        "move",
        "del",
    )
    blocked_shell_tokens: tuple[str, ...] = (
        "rm -rf /",
        "Remove-Item -Recurse -Force /",
        "Remove-Item -Recurse -Force C:\\",
        "rmdir /s C:\\",
        "del /s C:\\",
        "shutdown",
        "reboot",
        "mkfs",
        ">:",
        "dd if=",
        "chmod -R 777 /",
    )
    system_prompt: str = field(
        default=(
            "You are a production CLI coding agent. "
            "Return strict JSON only. "
            "Pick one tool action at a time. "
            "Prefer minimal safe changes and validate progress."
        )
    )

    def resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        return candidate.resolve()

    def is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False

    @property
    def memory_path(self) -> Path:
        return (self.workspace_root / self.memory_filename).resolve()

    @property
    def workspace_root_resolved(self) -> Path:
        return self.workspace_root.resolve()

    @property
    def caveman_state_path(self) -> Path:
        return (self.workspace_root / self.caveman_state_filename).resolve()

    @property
    def trace_path(self) -> Path:
        return (self.workspace_root / self.trace_filename).resolve()

    @property
    def prince2_pid_path(self) -> Path:
        return (self.workspace_root / self.prince2_pid_filename).resolve()

    @property
    def model_prefs_path(self) -> Path:
        return (self.workspace_root / self.model_prefs_filename).resolve()
