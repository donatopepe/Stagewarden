from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import AgentConfig
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


LEVELS = {"lite", "full", "ultra", "wenyan-lite", "wenyan", "wenyan-full", "wenyan-ultra"}


@dataclass(slots=True)
class CavemanDirective:
    active: bool = False
    level: str = "full"
    stripped_task: str = ""
    command: str | None = None
    argument: str | None = None


@dataclass(slots=True)
class CavemanState:
    active: bool = False
    level: str = "full"

    def save(self, path: Path) -> None:
        write_text_utf8(path, dumps_ascii({"active": self.active, "level": self.level}, indent=2))

    @classmethod
    def load(cls, path: Path) -> "CavemanState":
        if not path.exists():
            return cls()
        payload = loads_text(read_text_utf8(path))
        return cls(active=bool(payload.get("active", False)), level=str(payload.get("level", "full")))


class CavemanManager:
    def parse(self, task: str) -> CavemanDirective:
        lowered = task.lower()
        if "stop caveman" in lowered or "normal mode" in lowered:
            stripped = re.sub(r"stop caveman|normal mode", "", task, flags=re.IGNORECASE).strip()
            return CavemanDirective(active=False, stripped_task=stripped, command="deactivate")

        match = re.search(r"(?P<trigger>(?:^|\s)(?:/|\$|@)caveman)(?::(?P<sub>compress))?", task, flags=re.IGNORECASE)
        if match:
            remainder = task[match.end() :].strip()
            parts = remainder.split(maxsplit=1)
            arg1 = parts[0].lower() if parts else ""
            trailing = parts[1] if len(parts) > 1 else ""
            command = "activate"
            level = "full"
            argument: str | None = None

            if (match.group("sub") or "").lower() == "compress":
                command = "compress"
                argument = remainder or None
            elif arg1 in {"help", "commit", "review", "compress"}:
                command = arg1
                if command == "compress":
                    argument = trailing or None
            elif arg1 in LEVELS:
                level = "wenyan-full" if arg1 == "wenyan" else arg1

            stripped_remainder = trailing if arg1 in LEVELS else remainder if command == "activate" else ""
            stripped_task = f"{task[: match.start()]} {stripped_remainder}".strip()
            return CavemanDirective(
                active=True,
                level=level,
                stripped_task=stripped_task,
                command=command,
                argument=argument,
            )

        if any(phrase in lowered for phrase in ("talk like caveman", "caveman mode", "less tokens please", "be brief")):
            stripped = task
            for phrase in ("talk like caveman", "caveman mode", "less tokens please", "be brief"):
                stripped = re.sub(phrase, "", stripped, flags=re.IGNORECASE)
            return CavemanDirective(active=True, level="full", stripped_task=stripped.strip(), command="activate")

        return CavemanDirective(active=False, stripped_task=task)

    def augment_system_prompt(self, base_prompt: str, level: str) -> str:
        return (
            f"{base_prompt}\n\nCAVEMAN MODE ACTIVE.\n"
            f"Level: {level}.\n"
            "Cut filler. Keep technical accuracy.\n"
            "Drop articles, pleasantries, hedging. Fragments OK.\n"
            "Pattern: [thing] [action] [reason]. [next step].\n"
            "Code blocks, commands, file paths, URLs, exact errors unchanged.\n"
            "For security warnings and irreversible actions, be explicit first."
        )

    def help_text(self) -> str:
        return (
            "Caveman commands:\n"
            "- `/caveman [lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra]`\n"
            "- `$caveman ...`\n"
            "- `@caveman ...`\n"
            "- `/caveman help`\n"
            "- `/caveman commit`\n"
            "- `/caveman review`\n"
            "- `/caveman compress <file>`\n"
            "- `stop caveman` or `normal mode`\n"
            "Triggers also: `talk like caveman`, `caveman mode`, `less tokens please`."
        )

    def format_text(self, text: str, level: str) -> str:
        if level.startswith("wenyan"):
            return self._compress(text, ultra=level == "wenyan-ultra").replace(" because ", " 故 ").replace("->", "→")
        return self._compress(text, ultra=level == "ultra", keep_articles=level == "lite")

    def compress_file(self, path: str, config: AgentConfig) -> str:
        target = config.resolve_path(path)
        if not config.is_within_workspace(target):
            raise ValueError("Path outside workspace.")
        if target.suffix.lower() not in {".md", ".txt", ""}:
            raise ValueError("Compress supports only natural-language files.")
        if not target.exists():
            raise FileNotFoundError(str(target))

        original = read_text_utf8(target)
        backup = target.with_name(f"{target.stem}.original{target.suffix or '.md'}")
        if not backup.exists():
            write_text_utf8(backup, original)
        compressed = self._compress_document(original)
        valid, error = self._validate_compressed(original, compressed)
        if not valid:
            compressed = self._targeted_fix(original, compressed)
            valid, error = self._validate_compressed(original, compressed)
        if not valid:
            write_text_utf8(target, original)
            raise ValueError(f"Compression validation failed: {error}")
        write_text_utf8(target, compressed)
        return f"Compressed {target.name}. Backup: {backup.name}"

    def load_state(self, config: AgentConfig) -> CavemanState:
        try:
            return CavemanState.load(config.caveman_state_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return CavemanState()

    def save_state(self, config: AgentConfig, state: CavemanState) -> None:
        try:
            write_text_utf8(config.caveman_state_path, dumps_ascii({"active": state.active, "level": state.level}, indent=2))
        except OSError:
            pass

    def clear_state(self, config: AgentConfig) -> None:
        try:
            if config.caveman_state_path.exists():
                config.caveman_state_path.unlink()
        except OSError:
            pass

    def _compress_document(self, original: str) -> str:
        lines = []
        in_code = False
        for line in original.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                lines.append(line)
                continue
            if in_code or "`" in line or stripped.startswith("#") or re.search(r"https?://", line):
                lines.append(line)
                continue
            lines.append(self._compress(line, ultra=False, keep_articles=False))
        return "\n".join(lines) + ("\n" if original.endswith("\n") else "")

    def _validate_compressed(self, original: str, compressed: str) -> tuple[bool, str]:
        if original.count("```") != compressed.count("```"):
            return False, "Code fence count changed."
        if self._extract_inline_code(original) != self._extract_inline_code(compressed):
            return False, "Inline code changed."
        if self._extract_headings(original) != self._extract_headings(compressed):
            return False, "Heading structure changed."
        if self._extract_code_blocks(original) != self._extract_code_blocks(compressed):
            return False, "Code block content changed."
        return True, ""

    def _targeted_fix(self, original: str, compressed: str) -> str:
        original_lines = original.splitlines()
        compressed_lines = compressed.splitlines()
        fixed: list[str] = []
        in_code = False

        for index, original_line in enumerate(original_lines):
            compressed_line = compressed_lines[index] if index < len(compressed_lines) else ""
            stripped = original_line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                fixed.append(original_line)
                continue
            if in_code or stripped.startswith("#") or "`" in original_line or re.search(r"https?://", original_line):
                fixed.append(original_line)
            else:
                fixed.append(compressed_line if compressed_line else self._compress(original_line, ultra=False, keep_articles=False))
        return "\n".join(fixed) + ("\n" if original.endswith("\n") else "")

    def _extract_headings(self, text: str) -> list[str]:
        return [line for line in text.splitlines() if line.lstrip().startswith("#")]

    def _extract_inline_code(self, text: str) -> list[str]:
        return re.findall(r"`[^`]+`", text)

    def _extract_code_blocks(self, text: str) -> list[str]:
        return re.findall(r"```.*?```", text, flags=re.DOTALL)

    def _compress(self, text: str, *, ultra: bool, keep_articles: bool = False) -> str:
        if not text.strip():
            return text
        leader_match = re.match(r"^(\s*[-*+]?\s*|\s*\d+\.\s*)", text)
        leader = leader_match.group(0) if leader_match else ""
        body = text[len(leader) :]
        body = re.sub(
            r"\b(sure|certainly|of course|happy to|just|really|basically|actually|simply|essentially|generally)\b",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = re.sub(r"\b(it might be worth|you could consider|it would be good to|make sure to|you should|remember to)\b", "", body, flags=re.IGNORECASE)
        body = re.sub(r"\bin order to\b", "to", body, flags=re.IGNORECASE)
        if not keep_articles:
            body = re.sub(r"\b(a|an|the)\b\s*", "", body, flags=re.IGNORECASE)
        if ultra:
            for pattern, value in {
                r"\bdatabase\b": "DB",
                r"\bauthentication\b": "auth",
                r"\bconfiguration\b": "config",
                r"\brequest\b": "req",
                r"\bresponse\b": "res",
                r"\bfunction\b": "fn",
                r"\bbecause\b": "->",
            }.items():
                body = re.sub(pattern, value, body, flags=re.IGNORECASE)
        body = re.sub(r"\s+", " ", body).strip(" .")
        return f"{leader}{body}." if body else leader.rstrip()
