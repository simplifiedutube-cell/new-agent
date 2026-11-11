"""Every absolute path this project touches, in one place.

Nothing here is discovered at runtime: if a path moves, this file is the single
edit. `assert_layout()` is called by every subcommand before an agent starts, so
a typo fails in Python rather than halfway through a paid run.
"""

from __future__ import annotations

from pathlib import Path

# --- repos -----------------------------------------------------------------

FE = Path("/Users/dineshkadiam/flightcrew-fe")
DOCS = FE / "documentation" / "team-engine"
BE = FE / "flightcrew-be"  # a DIFFERENT git repo, untracked from FE

TRANSCRIPTS = DOCS / "transcription"  # git-ignored; the primary sources
ARCHIVE = DOCS / "archive"  # git-ignored; superseded docs
INTERNAL_OPS = DOCS / "INTERNAL-operations.md"  # git-ignored; prod runbook

# --- phase 1 outputs -------------------------------------------------------

SPEC_PARTICIPANT = DOCS / "11-participant-matching-algorithm.md"
SPEC_ADVISOR = DOCS / "12-advisor-matching-algorithm.md"
SPEC_NOTES = DOCS / "SPEC-REVIEW-NOTES.md"  # scaffolding; delete after review

SPEC_WRITABLE: list[Path] = [SPEC_PARTICIPANT, SPEC_ADVISOR, SPEC_NOTES]

# --- phase 2 write scope ---------------------------------------------------

BE_WRITABLE_DIRS: list[Path] = [
    BE / "src",
    BE / "models",
    BE / "migrations",
    BE / "test",
]

# --- this project ----------------------------------------------------------

PROJECT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
RUNS = PROJECT / "runs"


def frozen_docs() -> list[Path]:
    """Every doc Phase 1 must not touch.

    Computed rather than hardcoded so a future `13-…md` is protected the moment
    it exists. Deliberately includes the git-ignored INTERNAL-operations.md.
    """
    writable = {p.resolve() for p in SPEC_WRITABLE}
    return sorted(p for p in DOCS.glob("*.md") if p.resolve() not in writable)


def assert_layout() -> None:
    """Fail loudly, in Python, before spending anything on a run."""
    required = {
        "flightcrew-fe": FE,
        "documentation/team-engine": DOCS,
        "flightcrew-be": BE,
        "transcription/": TRANSCRIPTS,
        "archive/": ARCHIVE,
        "flightcrew-be/src": BE / "src",
        "flightcrew-be/models": BE / "models",
    }
    missing = [f"{label} -> {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise SystemExit("Missing expected paths:\n  " + "\n  ".join(missing))

    if not frozen_docs():
        raise SystemExit(f"No documents found in {DOCS} — wrong path?")
