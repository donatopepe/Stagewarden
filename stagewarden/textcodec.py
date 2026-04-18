from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any


def dumps_ascii(data: Any, *, indent: int | None = None, sort_keys: bool = False, compact: bool = False) -> str:
    return json.dumps(
        data,
        ensure_ascii=True,
        indent=indent,
        sort_keys=sort_keys,
        separators=(",", ":") if compact and indent is None else None,
    )


def loads_text(text: str) -> Any:
    return json.loads(text)


def write_text_utf8(path: str | Path, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8", newline="")


def read_text_utf8(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def to_ascii_safe_text(content: str) -> str:
    return content.encode("ascii", "backslashreplace").decode("ascii")


def contains_raw_non_ascii(content: str) -> bool:
    return any(ord(char) > 127 for char in content)


def detect_confusables(content: str) -> list[str]:
    warnings: list[str] = []
    scripts: set[str] = set()
    confusable_chars: list[str] = []

    for char in content:
        if ord(char) <= 127:
            continue
        script = _guess_script(char)
        if script:
            scripts.add(script)
        if char in _COMMON_CONFUSABLES:
            confusable_chars.append(f"{char}({_COMMON_CONFUSABLES[char]})")

    if len(scripts) > 1:
        warnings.append(f"mixed_scripts:{','.join(sorted(scripts))}")
    if confusable_chars:
        warnings.append(f"confusables:{','.join(confusable_chars[:12])}")
    return warnings


_COMMON_CONFUSABLES = {
    "Α": "Greek Alpha vs Latin A",
    "Β": "Greek Beta vs Latin B",
    "Ε": "Greek Epsilon vs Latin E",
    "Η": "Greek Eta vs Latin H",
    "Ι": "Greek Iota vs Latin I",
    "Κ": "Greek Kappa vs Latin K",
    "Μ": "Greek Mu vs Latin M",
    "Ν": "Greek Nu vs Latin N",
    "Ο": "Greek Omicron vs Latin O",
    "Ρ": "Greek Rho vs Latin P",
    "Τ": "Greek Tau vs Latin T",
    "Χ": "Greek Chi vs Latin X",
    "а": "Cyrillic a vs Latin a",
    "е": "Cyrillic e vs Latin e",
    "о": "Cyrillic o vs Latin o",
    "р": "Cyrillic er vs Latin p",
    "с": "Cyrillic es vs Latin c",
    "у": "Cyrillic u vs Latin y",
    "х": "Cyrillic ha vs Latin x",
    "і": "Cyrillic i vs Latin i",
    "ј": "Cyrillic je vs Latin j",
}


def _guess_script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    if "LATIN" in name:
        return "LATIN"
    if "CYRILLIC" in name:
        return "CYRILLIC"
    if "GREEK" in name:
        return "GREEK"
    if "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name:
        return "CJK"
    return None
