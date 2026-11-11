# te-agent

A two-phase Claude Agent SDK harness that first **specifies** and then **implements**
the Team Engine matching algorithm.

The target corpus is `/Users/dineshkadiam/flightcrew-fe/documentation/team-engine/` —
ten numbered documents describing Censio / Team Engine, a psychometric-assessment →
team-composition → co-founder matching product. Its largest gap is `07 §2`, *The
matching algorithm*: 🔴 not written, blocking BE-06, BE-07 and CONTENT-04.

## The protocol

```
uv run te-agent doctor        # pre-flight; run before every phase
uv run te-agent spec          # Phase 1 → writes 11-, 12- and SPEC-REVIEW-NOTES.md
uv run te-agent verify-docs   # mechanical checks on Phase 1 output
   … you read, correct, and sign off the specs by hand …
uv run te-agent impl          # Phase 2 → writes code in flightcrew-be
uv run te-agent verify-code   # mechanical checks on Phase 2 output
```

Phase 2 **cannot start** until you add this line under the title of both
specifications:

```markdown
**Spec status:** approved · v1 · <date> · approved by <name> · `algorithm_version: te-match-v1`
```

That gate is enforced in Python before any agent starts. It is the whole reason the
work is split in two: a matching algorithm encodes business decisions, and those get
made by a person, not inferred by a model.

## Authentication — read this before touching `.env`

`.env` holds a live `ANTHROPIC_API_KEY`, and **nothing loads it.** That is deliberate.

With no `ANTHROPIC_API_KEY` in the environment, the SDK falls through to the Claude
Code subscription credential, so runs bill against the **Max plan** rather than API
credits. `te-agent doctor` aborts if the variable is set.

Two consequences:

- **Never add `python-dotenv`.** It would silently switch billing.
- `options.env` *adds* variables to the subprocess; it cannot clear an inherited one.
  Aborting is the only reliable control, which is what `doctor` does.

The `cost (equiv)` figure in the run report is a usage equivalent under a subscription,
not a charge.

## What the sandbox actually enforces

Three redundant layers, plus two checks outside the agent:

| Layer | Phase 1 | Phase 2 |
|---|---|---|
| `permission_mode` | `dontAsk` — deny anything not pre-approved | same |
| Writable | exactly 3 filenames | `src/ models/ migrations/ test/` |
| Shell | **none** — no Bash at all, so no git, so no commit | `node`, `npx`, read-only git |
| PreToolUse hooks | path allowlist, secret scanner | subtree allow/deny, whole-command bash inspection, secret scanner |
| Outside the agent | sha256 freeze of all 12 existing docs, re-checked after | post-run `git status` on both repos |

`setting_sources=[]`, `mcp_servers={}`, `strict_mcp_config=True` and `skills=[]` are all
set, because `~/.claude/settings.json` carries `defaultMode: "auto"` and this machine
has railway, gmail, obsidian and pencil MCP servers plus a browser-control skill
installed. Without all four, they load into the run.

The hooks matter beyond the permission rules because rule matching is prefix-based:
`Bash(node:*)` happily permits `node -e "…execSync('git push')…"`. `bash_guard()` reads
the whole command string, which is the only thing that catches that shape.

## Why the epistemic rules exist

The documentation set earned its authority through a rule it states in `08`: *no quote,
no decision* — every decision carries a verbatim supporting quote, and a second
adversarial pass deletes anything it cannot ground.

That creates a trap. The transcripts **cannot** ground the answers this specification
needs. Measured across all 17 files (~177,000 words):

| Term | Hits |
|---|---|
| `semantic` | 10 |
| `matching algorithm` | 2 |
| `weighted` | 1 |
| `threshold` | 1 |
| `weightage` · `cutoff` · `tie break` · `embedding` | **0** |

An agent told both *"cite everything"* and *"answer the seven open questions"* will
manufacture citations. So `prompts/conventions.md` states the negative finding up
front, pre-authorises `**Proposed**` as a first-class provenance class, and quotes the
line that actually licenses proposing:

> *"Or you can build it and then you put together a document that says here is what we are doing."* — `Transcript aug 5.txt` · 18:57

Then `verify-docs` greps every citation against the transcripts, so fabrication is
detectable and therefore pointless.

## Layout

```
te_agent/
  cli.py          doctor | spec | verify-docs | impl | verify-code
  paths.py        every absolute path, with existence assertions
  guards.py       PreToolUse hooks — the only layer that reads whole commands
  runner.py       shared query() driver: stream → print → JSONL → report
  freeze.py       sha256 snapshot of the documents Phase 1 must not touch
  checks.py       quote verifier, convention linter, git-state checks
  doctor.py       pre-flight probes, including a negative probe
  phase1_spec.py  Phase 1 options + 3-agent roster
  phase2_impl.py  Phase 2 options + 2-agent roster + the approval gate
  prompts/*.md    loaded at runtime so a prompt change reviews as a prompt diff
runs/<phase>-<ts>/  session.jsonl, stderr.log, freeze-*.json, result.json
```

## Subagents

Phase 1 delegates to three, for two reasons: 250k tokens of transcript in the main
thread forces compaction mid-specification, and the adversarial second pass is already
the corpus's own documented method.

| Agent | Model | Job |
|---|---|---|
| `transcript-miner` | sonnet | Quote ledger for a topic, **plus explicit negative-evidence rows**. Its context is discarded; only the ledger returns. |
| `code-reader` | sonnet | What the backend does today, with `file:line`. Never speculates. |
| `spec-adversary` | opus | Greps every quote literally; deletes or downgrades what it cannot ground. Has `Edit` but not `Write`, so it can never create a document. |

Phase 2 uses `spec-reader` (specification → numbered requirement IDs) and
`impl-reviewer` (code vs. those IDs).

## Interpreting a run

- `permission_denials` in the report is the audit trail. Zero on a Phase 1 run is
  mildly suspicious — a diligent agent usually tries to fix a cross-reference in `07`.
  Many denials for the *same* path means the prompt and the rails disagree; fix the
  prompt, not the rails.
- A budget stop or `terminal_reason == "max_turns"` is a **failed** run, not a finished
  one — it leaves a truncated document. The runner exits non-zero on both.
- Resume with `uv run te-agent spec --resume <session_id> --fork`. Never
  `continue_conversation`: it picks the most recent conversation in the directory,
  which across two repos and two phases will eventually be the wrong one.
- `uv run te-agent spec --dry-run` grants no write rules at all — useful for watching
  what the agent would do without a byte changing.
