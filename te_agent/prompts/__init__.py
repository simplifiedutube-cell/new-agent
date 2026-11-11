"""Prompt loading.

Prompts live as .md files rather than Python string literals so a prompt change
shows up as a prompt diff in review, not as a wall of re-indented string.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load(name: str) -> str:
    path = _DIR / name
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_section(name: str, section: str) -> str:
    """Return one `## <section>` block from a prompt file.

    Subagent prompts share a file so they can be read side by side; each agent
    gets only its own block.
    """
    text = load(name)
    pattern = re.compile(
        rf"^##\s+{re.escape(section)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        available = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
        raise KeyError(f"section {section!r} not in {name}; available: {available}")
    return match.group(1).strip()
