"""PreToolUse hooks — the third and innermost safety layer.

The other two layers are `permission_mode="dontAsk"` with a narrow
`allowed_tools` allowlist, and `disallowed_tools`. Those match on tool name and
command *prefix*. These hooks see the resolved path and the whole command
string, which is the only way to catch `../` traversal and
`node -e "...execSync('git push')..."`.

Three constraints the SDK imposes, all of which the code below obeys:

1.  Hooks registered for the same event fire CONCURRENTLY, not in sequence.
    Every hook here is stateless.
2.  Returning `permissionDecision: "allow"` short-circuits the rest of the
    permission system. These hooks only ever deny or abstain (`{}`).
3.  A hook that raises yields no decision at all, which fails OPEN. Every hook
    body is wrapped so an internal error denies instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookMatcher

# Matches the CLI's own matcher syntax: a pipe-joined set of tool names.
WRITE_TOOLS = "Write|Edit|MultiEdit|NotebookEdit"


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _abstain() -> dict[str, Any]:
    """No decision — let the normal permission rules apply."""
    return {}


def _who(inp: dict[str, Any]) -> str:
    """Attribute a denial to a subagent when the hook fired inside one."""
    agent = inp.get("agent_type") or inp.get("agent_id")
    return f" (from subagent {agent})" if agent else ""


def _target(tool_input: dict[str, Any], cwd: str) -> Path | None:
    """Resolve the file a write-shaped tool call is aimed at.

    `.resolve()` collapses `..` and follows symlinks, so a relative path that
    escapes the working directory is caught here rather than at the filesystem.
    """
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = Path(cwd) / candidate
            try:
                return candidate.resolve()
            except OSError:
                return candidate
    return None


def _guarded(fn):
    """Wrap a hook body so an internal error denies rather than abstains."""

    async def wrapper(inp, tool_use_id, ctx):  # noqa: ANN001
        try:
            return await fn(inp, tool_use_id, ctx)
        except Exception as exc:  # noqa: BLE001 - fail closed, deliberately broad
            return _deny(
                f"Guard raised {type(exc).__name__}: {exc}. Denying because a hook that "
                f"fails open is not a guard. Report this; it is a harness bug, not your fault."
            )

    return wrapper


# --- Phase 1: exact-file allowlist ------------------------------------------


def write_guard(allow_files: list[Path], *, label: str) -> HookMatcher:
    """Permit writes to exactly these files and nothing else."""
    allowed = {p.resolve() for p in allow_files}
    names = ", ".join(sorted(p.name for p in allowed))

    @_guarded
    async def hook(inp, tool_use_id, ctx):  # noqa: ANN001
        target = _target(inp.get("tool_input", {}), inp["cwd"])
        if target is None or target in allowed:
            return _abstain()
        return _deny(
            f"[{label}]{_who(inp)} Writing {target} is not permitted. The only writable "
            f"files this run are: {names}. The existing documents are frozen — if one of "
            f"them needs a change, append a paste-ready patch block to SPEC-REVIEW-NOTES.md "
            f"under '## Paste-ready patches' and a human will apply it."
        )

    return HookMatcher(matcher=WRITE_TOOLS, hooks=[hook], timeout=10)


# --- Phase 2: subtree allowlist with an explicit deny list ------------------


def write_guard_tree(
    *, allow_dirs: list[Path], deny_dirs: list[Path], label: str
) -> HookMatcher:
    """Permit writes inside `allow_dirs`; refuse `deny_dirs` even if nested."""
    allow = [d.resolve() for d in allow_dirs]
    deny = [d.resolve() for d in deny_dirs]

    @_guarded
    async def hook(inp, tool_use_id, ctx):  # noqa: ANN001
        target = _target(inp.get("tool_input", {}), inp["cwd"])
        if target is None:
            return _abstain()

        # Deny wins over allow, and is checked first.
        for d in deny:
            if target == d or d in target.parents:
                return _deny(
                    f"[{label}]{_who(inp)} {target} is inside {d}, which is READ-ONLY in "
                    f"this phase. The approved spec is an input, not an output — the "
                    f"documentation was settled in Phase 1 and reviewed by a human. "
                    f"If the spec is wrong, stop and say so; do not edit it."
                )

        if any(a == target or a in target.parents for a in allow):
            return _abstain()

        return _deny(
            f"[{label}]{_who(inp)} {target} is outside the writable subtrees for this "
            f"phase ({', '.join(str(a) for a in allow)})."
        )

    return HookMatcher(matcher=WRITE_TOOLS, hooks=[hook], timeout=10)


# --- Phase 2: whole-command bash inspection ---------------------------------

# Permission rules match a command PREFIX, so `Bash(node:*)` happily permits
# `node -e "require('child_process').execSync('git push')"`. This regex reads
# the entire string, which is the only defence against that shape.
_BANNED_CMD = re.compile(
    r"\bgit\s+(commit|push|add|checkout|switch|reset|clean|stash|tag|rebase|merge|restore)\b"
    r"|\bnpm\s+(install|i|ci|publish|link)\b"
    r"|\b(yarn|pnpm)\s+(add|install)\b"
    r"|\bsequelize\b|\bdb:migrate\b|\bdb:seed\b"
    r"|\bpsql\b|\bpg_dump\b|\bpg_restore\b|\bmysql\b"
    r"|\bcurl\b|\bwget\b|\bssh\b|\bscp\b|\brsync\b"
    r"|\baws\b|\brailway\b|\bgh\s+(pr|release|repo)\b"
    r"|\brm\s+-[rfRF]|\bchmod\s+777\b|\bsudo\b"
    r"|documentation/team-engine"
    r"|\.env\b|\bPROD\b|\bproduction\b",
    re.IGNORECASE,
)


def bash_guard() -> HookMatcher:
    """Read the whole bash command, not just its prefix."""

    @_guarded
    async def hook(inp, tool_use_id, ctx):  # noqa: ANN001
        command = str(inp.get("tool_input", {}).get("command", ""))
        match = _BANNED_CMD.search(command)
        if match:
            return _deny(
                f"[bash]{_who(inp)} Blocked: the command contains {match.group(0)!r}. "
                f"This run may not commit, push, install packages, run migrations, reach "
                f"the network, or touch the documentation repo. Write the code and the "
                f"tests; report anything you wanted to run and a human will run it."
            )
        return _abstain()

    return HookMatcher(matcher="Bash", hooks=[hook], timeout=10)


# --- Both phases: keep the runbook out of the deliverable -------------------

# INTERNAL-operations.md (prod access, bastion hosts, security findings) is
# readable this run, but documentation/team-engine/*.md is git-TRACKED and the
# README describes the set as shareable with the client. Nothing may transit.
_SECRET = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|\.rds\.amazonaws\.com"
    r"|ec2-\d+-\d+-\d+-\d+"
    r"|\bsk-[A-Za-z0-9_\-]{20,}"
    r"|(ANTHROPIC|OPENAI|GROQ|AWS_SECRET|DATABASE)[A-Z_]*\s*[=:]\s*\S"
    r"|\b[A-Za-z0-9._%+-]+:[^\s/@]{6,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"  # user:pass@host
    r"|\.pem\b"
)


def secret_guard() -> HookMatcher:
    """Scan every write payload for credential-shaped content."""

    @_guarded
    async def hook(inp, tool_use_id, ctx):  # noqa: ANN001
        tool_input = inp.get("tool_input", {})
        parts = [str(tool_input.get(k, "")) for k in ("content", "new_string", "new_str")]
        for edit in tool_input.get("edits", []) or []:
            if isinstance(edit, dict):
                parts.append(str(edit.get("new_string", "")))
        match = _SECRET.search(" ".join(parts))
        if match:
            return _deny(
                f"[secret]{_who(inp)} Blocked: the content matches a credential pattern "
                f"({match.group(0)[:14]}…). documentation/team-engine/*.md is git-tracked "
                f"and written to be shareable with the client — nothing from "
                f"INTERNAL-operations.md may appear in it. Describe the mechanism in prose "
                f"instead of pasting the value."
            )
        return _abstain()

    return HookMatcher(matcher=WRITE_TOOLS, hooks=[hook], timeout=10)
