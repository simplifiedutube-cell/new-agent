"""sha256 snapshots of the documents Phase 1 must not touch.

This is the rail that sits *outside* the agent. The permission rules and the
PreToolUse hooks stop a write; this catches the case where one of those was
misconfigured and a write got through anyway. Ten lines, and it is the only
check that does not depend on the sandbox being correct.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import frozen_docs


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> dict[str, str]:
    """Map absolute path -> sha256 for every frozen document."""
    return {str(p): _sha256(p) for p in frozen_docs()}


def save(snap: dict[str, str], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(snap, indent=2, sort_keys=True), encoding="utf-8")


def compare(before: dict[str, str]) -> list[str]:
    """Return human-readable descriptions of every drift. Empty list == clean."""
    after = snapshot()
    problems: list[str] = []

    for path, digest in sorted(before.items()):
        if path not in after:
            problems.append(f"DELETED  {path}")
        elif after[path] != digest:
            problems.append(f"MODIFIED {path}\n           was {digest[:16]}…\n           now {after[path][:16]}…")

    for path in sorted(set(after) - set(before)):
        problems.append(f"NEW      {path} (appeared during the run and is not a spec output)")

    return problems
