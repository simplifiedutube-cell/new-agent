"""Phase 1 — draft the two matching-algorithm specifications.

Writes exactly three files into documentation/team-engine/ and nothing else. The
existing twelve documents are frozen by three independent mechanisms: the
permission allowlist, a PreToolUse hook, and a sha256 snapshot checked after the
run finishes.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from . import freeze
from .guards import secret_guard, write_guard
from .paths import BE, DOCS, SPEC_ADVISOR, SPEC_NOTES, SPEC_PARTICIPANT, SPEC_WRITABLE
from .paths import assert_layout
from .prompts import load, load_section
from .runner import failed, new_run_dir, run

SPEC_AGENTS: dict[str, AgentDefinition] = {
    "transcript-miner": AgentDefinition(
        description=(
            "Mines documentation/team-engine/transcription/ for verbatim evidence about a "
            "named matching topic and returns a quote ledger plus explicit negative "
            "evidence. Use for EVERY transcript question; never read transcripts directly."
        ),
        prompt=load_section("spec_agents.md", "transcript-miner"),
        tools=["Read", "Grep", "Glob"],
        disallowedTools=["Write", "Edit", "MultiEdit", "Bash", "WebSearch", "WebFetch"],
        model="sonnet",
        maxTurns=60,
        effort="high",
    ),
    "code-reader": AgentDefinition(
        description=(
            "Reads flightcrew-be and reports exactly what the matching code does today, "
            "with file:line for every claim. Never speculates about intent."
        ),
        prompt=load_section("spec_agents.md", "code-reader"),
        tools=["Read", "Grep", "Glob"],
        disallowedTools=["Write", "Edit", "MultiEdit", "Bash", "WebSearch", "WebFetch"],
        model="sonnet",
        maxTurns=40,
    ),
    "spec-adversary": AgentDefinition(
        description=(
            "Second adversarial pass. Re-reads a drafted specification against the raw "
            "sources and DELETES or downgrades anything it cannot ground. Run last, once "
            "per specification file."
        ),
        prompt=load_section("spec_agents.md", "spec-adversary"),
        # Edit but not Write: it can only modify an existing document, never create one.
        tools=["Read", "Grep", "Glob", "Edit"],
        disallowedTools=["Write", "MultiEdit", "Bash", "WebSearch", "WebFetch"],
        model="opus",  # the judgement call of the run; do not economise here
        maxTurns=80,
        effort="high",
    ),
}


def build_options(*, model: str, resume: str | None, fork: bool, dry_run: bool) -> ClaudeAgentOptions:
    # Permission rules resolve relative to cwd, so bare filenames are correct here
    # and far less error-prone than the absolute form.
    writable_rules: list[str] = []
    for path in (SPEC_PARTICIPANT, SPEC_ADVISOR, SPEC_NOTES):
        writable_rules += [f"Write({path.name})", f"Edit({path.name})"]

    return ClaudeAgentOptions(
        cwd=str(DOCS),
        # The narrowest read scope that still lets §1 be written from code rather
        # than copied from a possibly-stale document. Not BE itself: that would
        # pull in node_modules, .env and py_files.
        add_dirs=[str(BE / "src"), str(BE / "models")],
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": load("conventions.md") + "\n\n---\n\n" + load("spec_system.md"),
        },
        # Deny-by-default. NOT acceptEdits, which would auto-accept every write
        # including the twelve frozen documents.
        permission_mode="default" if dry_run else "dontAsk",
        allowed_tools=(
            ["Read", "Grep", "Glob", "TodoWrite", "Task", "Agent"]
            + ([] if dry_run else writable_rules)
        ),
        # No shell means no git, which is what makes "cannot commit" a fact rather
        # than an instruction. Grep and Glob cover every retrieval need.
        disallowed_tools=[
            "Bash",
            "BashOutput",
            "KillShell",
            "WebFetch",
            "WebSearch",
            "NotebookEdit",
            "Skill",
        ],
        # Isolation: ~/.claude/settings.json carries defaultMode "auto", and the
        # machine has railway/gmail/obsidian/pencil MCP servers and a browser-control
        # skill installed. All four of these are needed to keep them out.
        setting_sources=[],
        mcp_servers={},
        strict_mcp_config=True,
        skills=[],
        model=model,
        fallback_model="sonnet",
        max_turns=250,
        # Observed: a full Phase 1 run costs ~$20-23 equivalent. A cap only a
        # little above that fires mid-document and leaves a truncated spec, so
        # this is set deliberately below the observed cost — a budget stop should
        # mean "something ran away", not "a normal run just finished".
        max_budget_usd=30.0,
        hooks={
            "PreToolUse": [
                write_guard(SPEC_WRITABLE, label="phase1"),
                secret_guard(),
            ]
        },
        include_hook_events=True,
        agents=SPEC_AGENTS,
        resume=resume,
        fork_session=fork,
    )


async def run_spec(*, model: str, resume: str | None, fork: bool, dry_run: bool) -> int:
    assert_layout()

    run_dir = new_run_dir("spec")
    before = freeze.snapshot()
    freeze.save(before, run_dir / "freeze-before.json")

    print(f"run dir      {run_dir}")
    print(f"cwd          {DOCS}")
    print(f"writable     {', '.join(p.name for p in SPEC_WRITABLE)}")
    print(f"frozen       {len(before)} documents (sha256 snapshotted)")
    if dry_run:
        print("MODE         dry run — permission_mode=default, no write rules granted")
    print()

    result = await run(load("spec_task.md"), build_options(
        model=model, resume=resume, fork=fork, dry_run=dry_run
    ), run_dir)

    freeze.save(freeze.snapshot(), run_dir / "freeze-after.json")
    drift = freeze.compare(before)

    exit_code = 0

    if drift:
        print("\nFROZEN DOCUMENT DRIFT — a rail did not hold:")
        for problem in drift:
            print(f"  {problem}")
        print("Restore from git before doing anything else.")
        exit_code = 1
    else:
        print(f"\n✓ all {len(before)} frozen documents unchanged")

    reason = failed(result)
    if reason:
        print(f"\nRUN DID NOT COMPLETE CLEANLY: {reason}")
        print("Treat any written document as truncated.")
        exit_code = 1

    if exit_code == 0:
        print("\nNext: uv run te-agent verify-docs")

    return exit_code
