"""Phase 2 — implement the approved specification in flightcrew-be.

The gate is enforced in Python, before any agent starts: without a hand-written
approval marker on both specifications, this refuses to run. That is the whole
point of the two-phase split — Phase 2 cannot begin on a design a human has not
read.
"""

from __future__ import annotations

import hashlib
import re
import subprocess

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from .guards import bash_guard, secret_guard, write_guard_tree
from .paths import (
    BE,
    BE_WRITABLE_DIRS,
    DOCS,
    FE,
    SPEC_ADVISOR,
    SPEC_PARTICIPANT,
    assert_layout,
)
from .prompts import load, load_section
from .runner import failed, new_run_dir, run

# **Spec status:** approved · v1 · 12 Aug 2026 · approved by X · `algorithm_version: te-match-v1`
APPROVAL_RE = re.compile(
    r"^\*\*Spec status:\*\*\s+approved\s+·\s+v(?P<version>\d+)\b"
    r".*?`algorithm_version:\s*(?P<alg>[a-z0-9\-]+)`",
    re.MULTILINE,
)

APPROVAL_TEMPLATE = (
    "**Spec status:** approved · v1 · <date> · approved by <name> · "
    "`algorithm_version: te-match-v1`"
)

IMPL_AGENTS: dict[str, AgentDefinition] = {
    "spec-reader": AgentDefinition(
        description=(
            "Reads the two approved matching specifications and returns a numbered "
            "implementation checklist with stable requirement IDs. Run this first."
        ),
        prompt=load_section("impl_agents.md", "spec-reader"),
        tools=["Read", "Grep", "Glob"],
        disallowedTools=["Write", "Edit", "MultiEdit", "Bash", "WebSearch", "WebFetch"],
        model="sonnet",
        maxTurns=40,
    ),
    "impl-reviewer": AgentDefinition(
        description=(
            "Diffs written code against the requirement checklist and reports every "
            "unimplemented, mis-implemented or over-implemented clause. Run last."
        ),
        prompt=load_section("impl_agents.md", "impl-reviewer"),
        tools=["Read", "Grep", "Glob"],
        disallowedTools=["Write", "Edit", "MultiEdit", "WebSearch", "WebFetch"],
        model="opus",
        maxTurns=60,
        effort="high",
    ),
}


def resolve_approved_spec() -> dict[str, object]:
    """Refuse to proceed unless a human signed off both specifications."""
    resolved: dict[str, dict[str, str]] = {}

    for spec in (SPEC_PARTICIPANT, SPEC_ADVISOR):
        if not spec.exists():
            raise SystemExit(
                f"{spec.name} does not exist. Run `uv run te-agent spec` first."
            )
        text = spec.read_text(encoding="utf-8")
        match = APPROVAL_RE.search(text)
        if not match:
            raise SystemExit(
                f"{spec.name} is not approved.\n\n"
                f"Read it, correct it, then add this line immediately under the title:\n\n"
                f"    {APPROVAL_TEMPLATE}\n\n"
                f"Phase 2 will not run on a specification nobody has read."
            )
        resolved[spec.name] = {
            "algorithm_version": match.group("alg"),
            "sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        }

    versions = {v["algorithm_version"] for v in resolved.values()}
    if len(versions) != 1:
        raise SystemExit(
            f"The two specifications disagree on algorithm_version: {sorted(versions)}. "
            f"They implement one algorithm family and must share a version."
        )

    head = subprocess.run(
        ["git", "-C", str(FE), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return {
        "specs": resolved,
        "algorithm_version": versions.pop(),
        "fe_head": head.stdout.strip() or "unknown",
    }


def build_options(*, model: str, resume: str | None, fork: bool) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(BE),  # a DIFFERENT git repo from flightcrew-fe
        # Grants read access to the specifications. No write rule can resolve
        # into DOCS, because every write rule below is relative to cwd=BE.
        add_dirs=[str(DOCS)],
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": load("impl_system.md"),
        },
        permission_mode="dontAsk",
        allowed_tools=[
            "Read",
            "Grep",
            "Glob",
            "TodoWrite",
            "Task",
            "Agent",
            "Write(src/**)",
            "Edit(src/**)",
            "Write(models/**)",
            "Edit(models/**)",
            "Write(migrations/**)",
            "Write(test/**)",
            "Edit(test/**)",
            "Bash(node:*)",
            "Bash(npx:*)",
            "Bash(git status:*)",
            "Bash(git diff:*)",
            "Bash(git log:*)",
            "Bash(ls:*)",
            "Bash(rg:*)",
        ],
        disallowed_tools=[
            "WebFetch",
            "WebSearch",
            "NotebookEdit",
            "Skill",
            "Bash(git commit:*)",
            "Bash(git push:*)",
            "Bash(git add:*)",
            "Bash(git checkout:*)",
            "Bash(git reset:*)",
            "Bash(git clean:*)",
            "Bash(npm install:*)",
            "Bash(npm ci:*)",
            "Bash(npm publish:*)",
            "Bash(npx sequelize*)",
            "Bash(psql:*)",
            "Bash(pg_dump:*)",
            "Bash(curl:*)",
            "Bash(ssh:*)",
            "Bash(aws:*)",
            "Bash(railway:*)",
            "Bash(rm:*)",
        ],
        setting_sources=[],
        mcp_servers={},
        strict_mcp_config=True,
        skills=[],
        model=model,
        fallback_model="sonnet",
        max_turns=300,
        max_budget_usd=20.0,
        hooks={
            "PreToolUse": [
                write_guard_tree(
                    allow_dirs=BE_WRITABLE_DIRS,
                    deny_dirs=[DOCS, FE / "src"],
                    label="phase2",
                ),
                bash_guard(),
                secret_guard(),
            ]
        },
        include_hook_events=True,
        agents=IMPL_AGENTS,
        resume=resume,
        fork_session=fork,
    )


async def run_impl(*, model: str, resume: str | None, fork: bool) -> int:
    assert_layout()
    approved = resolve_approved_spec()  # raises SystemExit if unapproved

    run_dir = new_run_dir("impl")
    specs: dict[str, dict[str, str]] = approved["specs"]  # type: ignore[assignment]

    print(f"run dir      {run_dir}")
    print(f"cwd          {BE}")
    print(f"version      {approved['algorithm_version']}")
    print(f"fe HEAD      {approved['fe_head']}")
    for name, meta in specs.items():
        print(f"approved     {name}@{meta['sha256'][:12]}")
    print()

    stamps = "\n".join(
        f"- `{name}` → stamp `// spec: {name}@{meta['sha256'][:12]} "
        f"({approved['algorithm_version']})`"
        for name, meta in specs.items()
    )
    prompt = (
        load("impl_task.md")
        + "\n\n---\n\n## Approved specification identity\n\n"
        + f"`algorithm_version`: **{approved['algorithm_version']}** — record this with "
        f"every score you compute.\n\n"
        + stamps
        + "\n"
    )

    result = await run(prompt, build_options(model=model, resume=resume, fork=fork), run_dir)

    exit_code = 0
    reason = failed(result)
    if reason:
        print(f"\nRUN DID NOT COMPLETE CLEANLY: {reason}")
        exit_code = 1
    else:
        print("\nNext: uv run te-agent verify-code")

    return exit_code
