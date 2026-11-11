"""The shared query() driver: stream -> print -> JSONL -> report.

Both phases go through here so the logging, the cost report and the pass/fail
gate cannot drift apart.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .paths import RUNS

RULE = "─" * 72

# A run that ends this way produced a half-finished artefact, whatever it wrote.
BAD_TERMINALS = {"max_turns", "aborted_streaming", "aborted"}
BAD_SUBTYPES = {"error_max_budget_usd", "error_max_turns", "error_during_execution"}


def new_run_dir(phase: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RUNS / f"{phase}-{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _brief(name: str, tool_input: dict[str, Any]) -> str:
    """Show what a tool call is AIMED at, never its payload.

    Printing tool input floods the terminal with transcript excerpts and whole
    draft documents; the target is the only part worth watching live.
    """
    for key in ("file_path", "pattern", "command", "path", "subagent_type", "description"):
        value = tool_input.get(key)
        if value:
            text = str(value).replace("\n", " ")
            return f"{key}={text[:110]}"
    return ""


def _jsonable(message: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(message) and not isinstance(message, type):
        return dataclasses.asdict(message)
    if isinstance(message, dict):
        return message
    return {"type": type(message).__name__, "raw": repr(message)}


async def run(prompt: str, options: ClaudeAgentOptions, run_dir: Path) -> ResultMessage | None:
    """Drive one query to completion, logging everything. Returns the result."""
    run_dir.mkdir(parents=True, exist_ok=True)

    errlog = (run_dir / "stderr.log").open("w", encoding="utf-8")
    options.stderr = lambda line: (errlog.write(line + "\n"), errlog.flush())

    log = (run_dir / "session.jsonl").open("w", encoding="utf-8")
    result: ResultMessage | None = None

    try:
        async for message in query(prompt=prompt, options=options):
            log.write(json.dumps(_jsonable(message), default=str, ensure_ascii=False) + "\n")
            log.flush()

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)
                    elif isinstance(block, ToolUseBlock):
                        print(f"  · {block.name}({_brief(block.name, block.input)})")
            elif isinstance(message, ResultMessage):
                result = message
    finally:
        log.close()
        errlog.close()

    if result is not None:
        report(result, run_dir)
    return result


def report(r: ResultMessage, run_dir: Path) -> None:
    print("\n" + RULE)
    print(f"subtype        {r.subtype}   is_error={r.is_error}")
    print(f"terminal       {r.terminal_reason}   stop_reason={r.stop_reason}")
    print(f"turns          {r.num_turns}")
    print(f"wall / api     {r.duration_ms / 1000:.1f}s / {r.duration_api_ms / 1000:.1f}s")

    # On Max-subscription auth this is a usage equivalent, not a charge. Label it
    # so nobody panics, or worse, concludes the API key is in play.
    cost = r.total_cost_usd if r.total_cost_usd is not None else 0.0
    print(f"cost (equiv)   ${cost:.4f}")

    if r.usage:
        u = r.usage
        print(
            f"tokens         in={u.get('input_tokens')} out={u.get('output_tokens')} "
            f"cache_r={u.get('cache_read_input_tokens')} "
            f"cache_w={u.get('cache_creation_input_tokens')}"
        )
    for model, usage in (r.model_usage or {}).items():
        print(f"  {model}: {usage}")

    denials = r.permission_denials or []
    if denials:
        print(f"\nRAILS FIRED ({len(denials)}):")
        for d in denials:
            print(f"  ✋ {d}")
    if r.errors:
        print(f"\nerrors: {r.errors}")
    if r.api_error_status:
        print(f"api_error_status: {r.api_error_status}")

    print(f"\nsession_id     {r.session_id}")
    print(f"resume with    uv run te-agent spec --resume {r.session_id} --fork")
    print(RULE)

    (run_dir / "result.json").write_text(
        json.dumps(dataclasses.asdict(r), default=str, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def failed(r: ResultMessage | None) -> str | None:
    """Return a failure reason, or None if the run completed cleanly.

    A budget stop or a turn-limit stop is a FAILED run, not a finished one — it
    leaves a half-written document behind and must not be treated as success.
    """
    if r is None:
        return "the query produced no ResultMessage"
    if r.is_error:
        return f"is_error=True (subtype {r.subtype})"
    if r.subtype in BAD_SUBTYPES:
        return f"subtype={r.subtype}"
    if r.terminal_reason in BAD_TERMINALS:
        return f"terminal_reason={r.terminal_reason} — output is truncated"
    return None
