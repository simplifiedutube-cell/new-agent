"""Pre-flight checks. Run this before either phase, every time.

The negative probe is the one that matters: it proves the sandbox actually
denies a write, rather than assuming the configuration is right.
"""

from __future__ import annotations

import os

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from . import paths
from .paths import DOCS

PROBE_FILE = DOCS / "PROBE.txt"

# Deliberately minimal: everything the real phases disable, disabled here too,
# so the probe exercises the same isolation the real run relies on.
_ISOLATION = dict(
    setting_sources=[],
    mcp_servers={},
    strict_mcp_config=True,
    skills=[],
)


async def _collect(prompt: str, options: ClaudeAgentOptions) -> tuple[str, ResultMessage | None]:
    text: list[str] = []
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text.extend(b.text for b in message.content if isinstance(b, TextBlock))
        elif isinstance(message, ResultMessage):
            result = message
    return "\n".join(text).strip(), result


async def run_doctor(*, model: str) -> int:
    failures: list[str] = []

    def ok(label: str, detail: str = "") -> None:
        print(f"  ✓ {label}" + (f" — {detail}" if detail else ""))

    def bad(label: str, detail: str) -> None:
        print(f"  ✗ {label} — {detail}")
        failures.append(label)

    # 1. versions ------------------------------------------------------------
    print("\nVersions")
    import claude_agent_sdk

    sdk_version = getattr(claude_agent_sdk, "__version__", "unknown")
    cli_version = getattr(claude_agent_sdk, "__cli_version__", "unknown")
    ok("claude_agent_sdk", sdk_version)
    ok("bundled CLI", cli_version)

    # 2. layout --------------------------------------------------------------
    print("\nLayout")
    try:
        paths.assert_layout()
        frozen = paths.frozen_docs()
        ok("all expected paths exist", f"{len(frozen)} frozen documents")
    except SystemExit as exc:
        bad("paths", str(exc))
        print("\nCannot continue without the corpus.")
        return 1

    # 3. auth ----------------------------------------------------------------
    print("\nAuthentication")
    if os.environ.get("ANTHROPIC_API_KEY"):
        # options.env ADDS variables to the subprocess; it cannot clear an
        # inherited one. Aborting is the only reliable control.
        bad(
            "ANTHROPIC_API_KEY is set",
            "this run would bill API credits instead of the Max subscription. "
            "Unset it (`unset ANTHROPIC_API_KEY`) and re-run. Never add python-dotenv.",
        )
        return 1
    ok("ANTHROPIC_API_KEY unset", "the Max subscription will authenticate this run")

    # 4. positive probe ------------------------------------------------------
    print("\nPositive probe (auth + cwd + model + isolation in one shot)")
    read_only = ClaudeAgentOptions(
        cwd=str(DOCS),
        permission_mode="dontAsk",
        allowed_tools=["Read"],
        disallowed_tools=["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"],
        model=model,
        max_turns=6,
        **_ISOLATION,
    )
    text, result = await _collect(
        "Read 07-specs-to-settle.md and reply with its first line, exactly, and nothing else.",
        read_only,
    )
    expected = "# 07 · Specs to settle"
    if expected in text:
        ok("read the corpus", repr(expected))
    else:
        bad("positive probe", f"expected {expected!r}, got {text[:160]!r}")

    # 5. negative probe — the one that matters -------------------------------
    print("\nNegative probe (proves the sandbox denies writes)")
    if PROBE_FILE.exists():
        PROBE_FILE.unlink()
    text, result = await _collect(
        "Create a file named PROBE.txt in the current directory containing the word hello.",
        read_only,
    )
    denials = (result.permission_denials or []) if result else []
    if PROBE_FILE.exists():
        PROBE_FILE.unlink()
        bad("negative probe", "PROBE.txt WAS CREATED — the sandbox is not holding")
    elif not denials:
        # No file and no denial usually means the model politely declined
        # without attempting the tool call, which proves nothing.
        print(
            "  ! no file created, but no permission_denials recorded either — "
            "the model may have declined without attempting the write. "
            "Inconclusive rather than failed."
        )
    else:
        ok("write denied", f"{len(denials)} permission_denial(s), no file created")

    # 6. subagent tool-name probe -------------------------------------------
    print("\nSubagent probe (settles Task vs Agent empirically)")
    with_agent = ClaudeAgentOptions(
        cwd=str(DOCS),
        permission_mode="dontAsk",
        allowed_tools=["Read", "Task", "Agent"],
        disallowed_tools=["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"],
        model=model,
        max_turns=10,
        agents={
            "echo-probe": AgentDefinition(
                description="Trivial probe agent. Replies with a fixed token.",
                prompt="Reply with exactly: PROBE-OK. Nothing else.",
                tools=["Read"],
                model="sonnet",
                maxTurns=3,
            )
        },
        **_ISOLATION,
    )
    text, result = await _collect(
        "Delegate to the echo-probe subagent and report exactly what it replied.",
        with_agent,
    )
    if "PROBE-OK" in text:
        ok("subagents dispatch", "roster reachable with allowed_tools=['Task','Agent']")
    else:
        print(
            f"  ! subagent probe inconclusive — got {text[:160]!r}. "
            "Phase 1 will still run, but check that delegation happens."
        )

    print("\n" + "─" * 72)
    if failures:
        print(f"DOCTOR FAILED: {', '.join(failures)}")
        return 1
    print("DOCTOR OK — safe to run a phase.")
    return 0
