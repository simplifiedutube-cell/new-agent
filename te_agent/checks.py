"""Mechanical verification of what each phase produced.

The quote verifier is the point of the whole exercise: it is what turns "no
quote, no decision" from an instruction the model may or may not follow into a
property of the artefact that can be checked. Fabrication that is detectable is
fabrication that is pointless.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

from .paths import (
    BE,
    BE_WRITABLE_DIRS,
    DOCS,
    FE,
    SPEC_ADVISOR,
    SPEC_NOTES,
    SPEC_PARTICIPANT,
    TRANSCRIPTS,
)

RULE = "─" * 72

STATUS_EMOJI = {"🟢", "🟡", "🔴", "⏸"}
CODE_FENCE_LANGS = {"sql", "js", "javascript", "python", "py", "json", "ts", "typescript"}

# A citation blockquote: > *"…"* — `file` · time (date)
QUOTE_RE = re.compile(r'^>\s*\*"(?P<quote>.+?)"\*', re.MULTILINE | re.DOTALL)
TABLE_ROW_RE = re.compile(r"^\|(?P<cells>.+)\|\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"^```(\w+)", re.MULTILINE)
# Any heading level, not just ##: the specs nest to ### and GitHub anchors them all.
HEADING_RE = re.compile(r"^#{2,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\]\((?P<file>[0-9A-Za-z_.\-]+\.md)(?:#(?P<anchor>[^)]+))?\)")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  ✓ {label}" + (f" — {detail}" if detail else ""))

    def fail(self, label: str, detail: str) -> None:
        print(f"  ✗ {label} — {detail}")
        self.failures.append(label)

    def warn(self, label: str, detail: str) -> None:
        print(f"  ! {label} — {detail}")
        self.warnings.append(label)

    def finish(self, what: str) -> int:
        print("\n" + RULE)
        if self.failures:
            print(f"{what} FAILED: {len(self.failures)} check(s) — {', '.join(self.failures)}")
            return 1
        if self.warnings:
            print(f"{what} PASSED with {len(self.warnings)} warning(s).")
        else:
            print(f"{what} PASSED.")
        print("A human still has to read it. Nothing above is sufficient.")
        return 0


# --- text normalisation ----------------------------------------------------


def _norm(text: str) -> str:
    """NFC-normalise and collapse whitespace.

    Never lowercase: the transcripts are code-mixed and casefolding Devanagari
    is meaningless at best. Whitespace collapsing is needed because a quote may
    span a line break in the markdown but not in the source.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _transcript_corpus() -> str:
    parts = []
    for path in sorted(TRANSCRIPTS.glob("*.txt")):
        parts.append(_norm(path.read_text(encoding="utf-8", errors="replace")))
    return "\n".join(parts)


# --- individual checks -----------------------------------------------------


def check_quotes(spec: Path, corpus: str, rep: Report) -> None:
    """Every citation blockquote must appear literally in some transcript."""
    text = spec.read_text(encoding="utf-8")
    quotes = [m.group("quote") for m in QUOTE_RE.finditer(text)]
    if not quotes:
        rep.warn(f"{spec.name} quotes", "no citation blockquotes at all")
        return

    misses = []
    for quote in quotes:
        needle = _norm(quote)
        # An ellipsis marks an elision; check the longest run around it instead.
        if "…" in needle or "..." in needle:
            fragments = [f.strip() for f in re.split(r"…|\.\.\.", needle) if len(f.strip()) > 25]
            if fragments and all(f in corpus for f in fragments):
                continue
        if needle not in corpus:
            misses.append(needle)

    if misses:
        detail = f"{len(misses)}/{len(quotes)} not found verbatim in transcription/"
        rep.fail(f"{spec.name} quotes", detail)
        for miss in misses[:5]:
            print(f'        “{miss[:110]}…”')
    else:
        rep.ok(f"{spec.name} quotes", f"all {len(quotes)} verified verbatim")


def _is_separator(line: str) -> bool:
    m = TABLE_ROW_RE.match(line)
    return bool(m) and set(m.group("cells")) <= set("-: |")


def check_provenance(spec: Path, rep: Report) -> None:
    """Rows of a provenance-bearing table must carry a citation or a Proposed marker.

    Two subtleties learned the hard way:

    - "Source" is only a column header when the NEXT line is a separator row.
      In a comparison table it is often a row *label* in column 0, and treating
      that as a header mis-columns every row beneath it.
    - The provenance may sit in a column named Source, Class or Provenance —
      the specs use `Input | Source | Class` where Source means "where the input
      comes from" and Class carries the citation. So scan the whole row rather
      than one column index; an ungrounded row has no citation anywhere in it.
    """
    text = spec.read_text(encoding="utf-8")
    lines = text.splitlines()

    provenance_headers = {"source", "class", "provenance", "status"}
    in_table = False
    bad: list[str] = []
    checked = 0

    for i, line in enumerate(lines):
        m = TABLE_ROW_RE.match(line)
        if not m:
            in_table = False
            continue

        cells = [c.strip() for c in m.group("cells").split("|")]
        lowered = {c.lower() for c in cells}

        # A header row is one immediately followed by a separator row.
        if i + 1 < len(lines) and _is_separator(lines[i + 1]):
            in_table = bool(lowered & provenance_headers)
            continue
        if not in_table or _is_separator(line):
            continue

        checked += 1
        row = " ".join(cells)
        grounded = (
            "Proposed" in row
            or "`" in row  # a transcript filename or a file:line reference
            or re.search(r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", row)
            or "§" in row
            # A status emoji IS the set's vocabulary for an existence claim: a
            # field-inventory row reading "🔴 does not exist" is grounded by it.
            or bool(set(row) & STATUS_EMOJI)
        )
        if not grounded:
            bad.append(line.strip()[:100])

    if not checked:
        rep.warn(f"{spec.name} provenance", "no Source-column tables found")
    elif bad:
        rep.fail(f"{spec.name} provenance", f"{len(bad)}/{checked} rows have an empty or vague Source")
        for row in bad[:5]:
            print(f"        {row}")
    else:
        rep.ok(f"{spec.name} provenance", f"all {checked} table rows sourced")


def check_conventions(spec: Path, number: str, rep: Report) -> None:
    text = spec.read_text(encoding="utf-8")
    problems: list[str] = []

    if not re.match(rf"^# {number} · ", text):
        problems.append(f"title must start '# {number} · ' (U+00B7 middle dot)")
    if "\n---\n" not in text[:1200]:
        problems.append("no `---` rule after the intro paragraph")
    if not re.search(r"^## 1\. ", text, re.MULTILINE):
        problems.append("no '## 1. ' section")
    if "**Next:**" not in text:
        problems.append("missing the closing **Next:** pointer")

    stray = {ch for ch in text if ch in "🔵🟠⚪✅❌⚠️"} - STATUS_EMOJI
    if stray:
        problems.append(f"non-standard status emoji: {''.join(sorted(stray))}")

    langs = {m.group(1).lower() for m in FENCE_RE.finditer(text)}
    offenders = langs & CODE_FENCE_LANGS
    if offenders:
        problems.append(f"the set contains zero code; found fenced {', '.join(sorted(offenders))}")

    if problems:
        rep.fail(f"{spec.name} conventions", "; ".join(problems))
    else:
        rep.ok(f"{spec.name} conventions")


def check_links(spec: Path, rep: Report) -> None:
    text = spec.read_text(encoding="utf-8")
    broken: list[str] = []

    for m in LINK_RE.finditer(text):
        target = DOCS / m.group("file")
        if not target.exists():
            broken.append(f"{m.group('file')} (no such file)")
            continue
        anchor = m.group("anchor")
        if not anchor:
            continue
        # GitHub's slug algorithm collapses whitespace around stripped characters
        # (emoji, em-dashes) in ways a naive strip does not reproduce exactly, so
        # compare with runs of hyphens collapsed on both sides.
        def slug(text: str) -> str:
            s = re.sub(r"[^a-z0-9\- ]", "", text.lower()).strip().replace(" ", "-")
            return re.sub(r"-+", "-", s)

        slugs = {slug(h) for h in HEADING_RE.findall(target.read_text(encoding="utf-8"))}
        if slug(anchor) not in slugs:
            broken.append(f"{m.group('file')}#{anchor}")

    if broken:
        rep.warn(f"{spec.name} links", f"{len(broken)} unresolved: {', '.join(broken[:4])}")
    else:
        rep.ok(f"{spec.name} links")


def check_git_state(rep: Report) -> None:
    """Only the three expected files may be new, and nothing may be modified."""
    proc = subprocess.run(
        ["git", "-C", str(FE), "status", "--porcelain", "--", "documentation/team-engine"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        rep.warn("git state", proc.stderr.strip()[:120])
        return

    expected_new = {p.name for p in (SPEC_PARTICIPANT, SPEC_ADVISOR, SPEC_NOTES)}
    modified: list[str] = []
    unexpected: list[str] = []

    for line in proc.stdout.splitlines():
        status, _, path = line.partition(" ")
        name = Path(path.strip()).name
        if line.startswith("??"):
            if name not in expected_new:
                unexpected.append(name)
        elif "M" in status:
            modified.append(name)

    if modified:
        rep.fail("git state", f"tracked documents MODIFIED: {', '.join(modified)}")
    elif unexpected:
        rep.warn("git state", f"unexpected new files: {', '.join(unexpected)}")
    else:
        rep.ok("git state", "no tracked document modified")


def check_questions_answered(rep: Report) -> None:
    """All seven open questions from 07 §2 get an answer somewhere in 11 or 12."""
    keys = {
        "weights": ("weight",),
        "score meaning": ("what the number means", "person-to-opening", "score mean"),
        "tie-breaks": ("tie-break", "tie break"),
        "threshold": ("threshold", "floor"),
        "semantic fallback": ("semantic fallback",),
        "team composition": ("team composition", "considering"),
        "precompute": ("precomputed", "on demand"),
    }
    blob = ""
    for spec in (SPEC_PARTICIPANT, SPEC_ADVISOR):
        if spec.exists():
            blob += spec.read_text(encoding="utf-8").lower()

    missing = [label for label, needles in keys.items() if not any(n in blob for n in needles)]
    if missing:
        rep.fail("07 §2 coverage", f"unaddressed: {', '.join(missing)}")
    else:
        rep.ok("07 §2 coverage", "all seven questions addressed")


def check_notes(rep: Report) -> None:
    if not SPEC_NOTES.exists():
        rep.fail("review notes", f"{SPEC_NOTES.name} was not written")
        return
    text = SPEC_NOTES.read_text(encoding="utf-8")
    required = ["## Decision sheet", "## Quote ledger", "## Paste-ready patches"]
    missing = [s for s in required if s not in text]
    if missing:
        rep.fail("review notes", f"missing sections: {', '.join(missing)}")
    else:
        rep.ok("review notes", "decision sheet, quote ledger and patches present")


# --- entry points ----------------------------------------------------------


def verify_docs() -> int:
    rep = Report()
    print("\nPhase 1 output\n" + RULE)

    missing = [p.name for p in (SPEC_PARTICIPANT, SPEC_ADVISOR) if not p.exists()]
    if missing:
        print(f"  ✗ not written: {', '.join(missing)}")
        print("\nRun `uv run te-agent spec` first.")
        return 1

    check_git_state(rep)

    print("\nQuote verification (the check that matters)")
    corpus = _transcript_corpus()
    print(f"  corpus: {len(list(TRANSCRIPTS.glob('*.txt')))} transcripts, {len(corpus):,} chars")
    for spec in (SPEC_PARTICIPANT, SPEC_ADVISOR):
        check_quotes(spec, corpus, rep)

    print("\nProvenance")
    for spec in (SPEC_PARTICIPANT, SPEC_ADVISOR):
        check_provenance(spec, rep)

    print("\nConventions")
    check_conventions(SPEC_PARTICIPANT, "11", rep)
    check_conventions(SPEC_ADVISOR, "12", rep)

    print("\nCross-references")
    for spec in (SPEC_PARTICIPANT, SPEC_ADVISOR):
        check_links(spec, rep)

    print("\nCoverage")
    check_questions_answered(rep)
    check_notes(rep)

    return rep.finish("verify-docs")


def verify_code() -> int:
    rep = Report()
    print("\nPhase 2 output\n" + RULE)

    # The docs repo must be untouched by a run whose cwd was the sibling repo.
    proc = subprocess.run(
        ["git", "-C", str(FE), "status", "--porcelain", "--", "documentation/team-engine"],
        capture_output=True,
        text=True,
    )
    dirty = [ln for ln in proc.stdout.splitlines() if not ln.startswith("??")]
    if dirty:
        rep.fail("docs untouched", f"{len(dirty)} modified: {dirty[:3]}")
    else:
        rep.ok("docs untouched", "no tracked documentation file modified")

    # Only the four writable subtrees may have changed, and nothing committed.
    proc = subprocess.run(
        ["git", "-C", str(BE), "status", "--porcelain"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        rep.fail("backend git", proc.stderr.strip()[:120])
        return rep.finish("verify-code")

    allowed_prefixes = tuple(str(d.relative_to(BE)) for d in BE_WRITABLE_DIRS)
    outside = [
        ln
        for ln in proc.stdout.splitlines()
        if ln.strip() and not ln[3:].strip().startswith(allowed_prefixes)
    ]
    if outside:
        rep.fail("write scope", f"changes outside {allowed_prefixes}: {outside[:3]}")
    else:
        changed = len([ln for ln in proc.stdout.splitlines() if ln.strip()])
        rep.ok("write scope", f"{changed} change(s), all inside {', '.join(allowed_prefixes)}")

    # Nothing may have been committed.
    staged = [ln for ln in proc.stdout.splitlines() if ln[:1] not in (" ", "?", "")]
    if staged:
        rep.warn("staging", f"{len(staged)} file(s) staged — the run should not have run `git add`")

    # Every generated file must name the spec it was built from.
    unstamped: list[str] = []
    for line in proc.stdout.splitlines():
        rel = line[3:].strip()
        if not rel.endswith(".js"):
            continue
        path = BE / rel
        if path.exists() and "// spec:" not in path.read_text(encoding="utf-8", errors="replace")[:600]:
            unstamped.append(rel)
    if unstamped:
        rep.fail("spec stamps", f"{len(unstamped)} file(s) lack a `// spec:` header: {unstamped[:3]}")
    elif proc.stdout.strip():
        rep.ok("spec stamps", "every changed .js names its source spec")

    print("\nRun the test suite yourself:")
    print(f"  cd {BE} && node --test test/")

    return rep.finish("verify-code")
