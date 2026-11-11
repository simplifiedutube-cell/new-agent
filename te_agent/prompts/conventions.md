# House style — documentation/team-engine/

You are writing into an existing documentation set of ten numbered documents. It has
strong, consistent conventions and a distinctive epistemic method. Match both. A
document that is correct but reads as foreign has failed.

## Format

- Filenames `NN-kebab-case.md`, zero-padded. The set currently ends at `10-`.
- Title line: `# 11 · Participant matching algorithm` — the number, U+00B7 MIDDLE DOT
  (`·`, not a hyphen and not a bullet), then the title.
- Sections: `## 1. Title`, numbered from 1.
- Every document opens with a one-or-two-line "what this is for" paragraph, then a
  `---` rule, then the numbered sections, and closes with
  `**Next:** [NN · Title](NN-file.md).`
- Status key — use only these four, inline in headings where relevant:
  🟢 built and working · 🟡 in progress · 🔴 not started · ⏸ blocked on someone named.
- Cross-references are relative, with a GitHub-style anchor:
  `[07 §2](07-specs-to-settle.md#2-the-matching-algorithm)`.
- Diagrams are Mermaid, inline, never an image. A solid box and solid arrow mean built
  and working today; a dashed box or arrow means agreed but waiting on the backend,
  with the backlog ID in the label.
- Backlog IDs use the one scheme defined in `09`: `BE-`, `FE-`, `CONTENT-`, `ADMIN-`,
  `OPS-`. The ones relevant here are BE-06, BE-07 and CONTENT-04.

## The set contains zero code

Not one line, across ten documents and 5,700 lines. This is deliberate: `04` explains
that everything is written so it "lives in git, diffs like text, and can be edited
without a drawing tool".

Express the algorithm as numbered prose procedures, tables, and Mermaid. **No SQL, no
JavaScript, no Python, no JSON payloads, no pseudocode blocks.** Naming a column
(`role_fit_score`) or a function (`searchTalentProfiles()`) in prose or a table cell is
right; a fenced code block is not. The implementation is a separate exercise carried
out against this document, by a different run, in a different repository.

---

# Epistemic rules

These override helpfulness. The documentation set earned its authority by being
unusually strict about what it claims, and `08` describes the method in its own words:
each source was read end to end by a pass that extracted decisions, each with a
verbatim supporting quote — no quote, no decision — and a second adversarial pass
re-read the raw text and deleted anything it could not ground.

## 1. No quote, no decision

A statement may be presented as something the team decided **only** if you can produce
a verbatim quote from a file under `transcription/`. Cite in this form:

> *"…the exact words…"* — `Transcript aug 5.txt` · 18:57 (5 Aug)

The quoted text must appear in the file **character for character**. Every quote is
grep-verified mechanically after the run. A quote that does not appear literally is
treated as a fabrication and fails the whole run — it is strictly worse than having no
quote at all, because it poisons a document whose entire value is that its claims can
be checked.

## 2. Three provenance classes, and every claim is exactly one

Use the `| … | Source |` table shape that `07 §1` already uses, so a reader sees
provenance in the column where they already expect it. Do not invent a new key.

| Class | What goes in the Source cell |
|---|---|
| **DECIDED** | A dated quote citation, per rule 1. |
| **OBSERVED** | A code reference (`profile.service.js:492`) or a document reference (`10 §(d) D3`). A fact about the system as it stands — not a decision anyone took. |
| **PROPOSED** | The literal text `**Proposed — needs <name>**`, naming the person who must decide. |

Never blend them. A weight with a code reference beside it is a lie: the code does not
contain that weight, you chose it.

## 3. Expect most of this document to be PROPOSED

This is measured, not guessed. Across all 17 transcripts (~177,000 words):

| Term | Hits | What that means |
|---|---|---|
| `tie break` / `tiebreak` | **0** | Never discussed at all |
| `embedding` / `vector` | **0** | Never discussed at all |
| `latency` / `precompute` | **0** | Never discussed at all |
| `weightage` | **0** | The team says "weights", not "weightage" — search both |
| `threshold` | 1 | An unrelated side-project. **0** about a match-score floor |
| `cutoff` | 7 | All display-truncation or noise. **0** about a score cutoff |
| `weight` / `weighted` | 1 each | Weights exist *in principle*; **one** proposed split was floated |
| `semantic` | 10 | Named mechanisms: *cosine similarity*, *elastic search* |

Read that table carefully, because it cuts two ways.

**Genuinely absent — do not go looking:** tie-breaks, a score threshold or floor,
embeddings, latency and cost budgets, and precomputed-vs-on-demand. Nobody ever said
anything about these. Searching harder will not produce them.

**Partially present — find it and cite it:** weights were discussed in principle, one
concrete split was floated in July, and two candidate semantic mechanisms were named
aloud. That evidence exists and must be cited where it applies. Proposing something the
team already half-decided is as wrong as inventing a citation.

The discipline is the same in both directions: cite what was said, propose what was
not, and never let one wear the other's clothes.

A specification that returns those items as DECIDED is wrong. A specification that
returns them as PROPOSED — with a recommendation, the alternatives, and the
consequence — is right, and is precisely what was asked for:

> *"Or you can build it and then you put together a document that says here is what we are doing."* — `Transcript aug 5.txt` · 18:57 (5 Aug)

That line is your mandate to propose. Use it. Do not apologise for proposing, and do
not retreat to "TBD" — an unanswered specification leaves BE-06 blocked, which is the
status quo that has already cost months.

## 4. Later beats earlier

Where two transcripts conflict, the later date wins, and say so. Watch for reversals
*inside* a single call: if a group decided X and then changed to Y before the call
ended, only Y survives.

## 5. Mark what you cannot verify

Unverifiable claims get `*(uncited)*` inline. Conflicts you cannot resolve go in a
`## Open contradictions` section — never silently pick a side.

## 6. The transcriber mangles names

Speech-to-text corrupts the proper nouns consistently. Grep for every variant:

- **Censio** → Sensio, Senseo, Sensei, Census
- **Creighton** → Kton, Kreton, Crichton
- **Team Engine** → "gaming engine", "machine engine"

## 7. The transcripts are code-mixed Hindi and English

No speaker labels; paragraphs are anchored by an `HH:MM` timestamp at the line start.
Quote verbatim, including Devanagari, and add a bracketed English gloss after it.
Attribute a quote to a named speaker only when the surrounding text makes it
unambiguous — otherwise cite the file and timestamp alone.
