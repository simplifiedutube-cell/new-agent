# Task — write the two matching-algorithm specifications

`07 §2` has said the same thing for months:

> "Two documents were asked for — participant matching and advisor matching. Neither
> exists. What exists is the *criteria* and the *intent*, never the algorithm."

Backlog BE-06 and BE-07 are blocked on those two documents, and `CONTENT-04` is ⏸.
Write them.

---

## 1. Read in this order

Do this yourself, on this thread, before delegating anything:

1. `07-specs-to-settle.md` §2 — your contract. The settled constraints and the seven
   open questions are both there.
2. `08-decisions.md` — "Thread 5 · Matching" for the dated reversal history, and the
   28 March entry recording that the 1,000-person Prolific dataset showed no
   statistical signal (logistic regression, L1 regularisation and shuffled-label tests
   all at chance). That finding constrains how strong a claim any weighting scheme can
   make.
3. `10-metrics-and-analytics.md` §(d) "Match-quality / algorithm instrumentation" —
   **the richest prior art in the corpus and your best source of citable proposals.**
   It already sets out `score_components` (JSONB) plus `algorithm_version`, a
   five-component composite, a fairness audit, and minimum-n gates. A proposal derived
   from §(d) and cited to it is OBSERVED-derived, not invented. Read §1 too, for the
   blunt statement of where matching actually stands.
4. `09-status-and-backlog.md` — the exact current wording of BE-06, BE-07, CONTENT-04.
5. `03-data-model.md` §4 and `06-api-reference.md` — the profile shape and the search
   endpoint contract.

Then delegate: `code-reader` for what the backend does today, `transcript-miner` for
what was said.

## 2. Retrieval protocol — mandatory

**Never read a transcript whole.** The 17 files are 77–599 lines each, one paragraph
per `HH:MM` timestamp. Grep for a term, then read a ±15-line window around each hit
with `Read(offset=…, limit=…)`.

Better still, do not read them on this thread at all — that is what `transcript-miner`
is for. Its context is discarded when it reports; yours is not.

## 3. These are settled — honour them, do not re-derive them

From `07 §2`, "What is already decided". Restated here so there is no ambiguity:

| Decision | Detail |
|---|---|
| Participant match variables | Role · skills · location · collaboration mode |
| Advisor match variables | Skills · experience · industry · location |
| Strategy | Exact match first, semantic similarity as fallback for whatever misses |
| Why a fixed skill list | So most matching can be exact. The "Other" free-text box is deliberately the exception, and the list grows as we see what people type into it |
| Score source | `role_fit_score` is static per person — probability of the predicted role, 0–100, from the assessment. **Not pairwise** |
| Empty is not zero | An unscored person shows "Pending", never 0 |
| Advisor breadth | An advisor who selects "I work across industries" must match *every* industry query |

If your proposal contradicts one of these, your proposal is wrong. Change the proposal.

## 4. Verify the "what the code does today" claim — do not copy it

`07 §2` says: *"Location and collaboration mode are not part of the query."*

Treat that as **a claim to check, not a source to quote.** Have `code-reader` read
`searchTalentProfiles()` in `profile.service.js` and report what is actually filtered.
Write §1 of each specification from the code, with `file:line`. If the existing
document is out of date, that is a finding — record it under `## Corrections found` in
`SPEC-REVIEW-NOTES.md` with the evidence, and do not silently propagate it.

## 5. Answer the seven open questions

`07 §2` lists them. Each one gets an answer in §12 of the relevant specification, and
each answer carries five things:

1. **The proposal** — a specific, implementable value or mechanism.
2. **The alternatives considered** — and why you did not choose them.
3. **The consequence** — cost, latency, or the data it would require.
4. **The named decider** — who has to sign this off.
5. **What changes if it is reversed** — how much of the specification moves.

The questions:

1. **Weights.** Is a role match worth more than a skills match? Is location a hard
   filter or a soft factor?
2. **What does the returned score mean?** `role_fit_score` is person-to-role. A search
   result needs person-to-*opening*. Are these the same number? If not, what does the
   match card show?
3. **Tie-breaks.** Two candidates score identically — what orders them?
4. **Threshold.** Is there a floor below which a match is not shown, or is everything
   returned, ranked?
5. **What powers the semantic fallback?** An embedding model, an LLM call, or Postgres
   full-text search. This is a cost and latency decision; note that the application
   already calls both Anthropic and OpenAI.
6. **Does team composition affect ranking?** The "Considering" feature rests on an 84%
   individual match beating a 98% one because of team fit. Should search reflect that,
   or is it visible only after adding someone to the grid?
7. **Precomputed or on demand?** Affects whether `matches` rows are generated in a
   batch or at search time.

**On question 1 specifically:** `10` sets a minimum-n gate — empirical reweighting via
regression needs 100–150 outcome-labelled matches, not achievable within a single
Creighton cohort. The honest answer is therefore theory-set and judgment-adjusted
weights, empirically untunable until multi-cohort. That is a citable position, not a
guess. Say it plainly.

## 6. Both documents must be implementable *and* reversible

These pull against each other and the resolution is structural, not rhetorical.

**Implementable:** every parameter has a chosen default. A specification full of "TBD"
leaves BE-06 exactly where it has been.

**Reversible:** every proposed number lives in **one named weights table**, and
changing it is a one-place edit plus an `algorithm_version` bump. §11 must say so
explicitly, and name the table.

That is what makes it safe to build against a specification before every number is
agreed: the cost of the decider disagreeing is a single-line edit, not a rewrite.

## 7. Section skeleton

Use exactly this for `11-participant-matching-algorithm.md`:

```
# 11 · Participant matching algorithm
<one or two lines: what this is for>
---
## 1. What this replaces
## 2. Inputs
## 3. The exact pass — hard filters
## 4. The scoring pass
## 5. The semantic fallback
## 6. Ranking, tie-breaks and the threshold
## 7. What the number means, and what the card shows
## 8. Precomputed or on demand
## 9. Worked example
## 10. Instrumentation
## 11. Versioning — how to change a weight
## 12. Open questions carried forward
## 13. Open contradictions
## Sources
**Next:** [12 · Advisor matching algorithm](12-advisor-matching-algorithm.md).
```

Notes on individual sections:

- **§1** cites BE-06 and `07 §2`, and describes today's behaviour from code.
- **§2** names the exact columns, cited to `models/talent_profiles.js`.
- **§4** is the `| Component | Weight | Rule | Source |` table — the provenance column
  carries DECIDED / OBSERVED / PROPOSED per the epistemic rules.
- **§5** states the mechanism, when it fires, and its cost and latency budget.
- **§9** walks three candidates through the whole procedure with the arithmetic shown,
  in prose and tables. This section is what makes the document reviewable by someone
  who will not read §4 closely.
- **§10** ties to `10 §(d)` — `score_components`, `algorithm_version`.
- **§13** may legitimately be empty; say so rather than omitting the heading.

`12-advisor-matching-algorithm.md` follows the same skeleton with the advisor
variables, and closes `**Next:** [01 · Overview](01-overview.md).` Where the two
algorithms genuinely share a mechanism, `12` cites `11` rather than restating it —
duplicated prose drifts apart.

## 8. You may not edit the existing documents

Convention wants `11` and `12` linked from `README.md`, `07 §2` and `09`. You cannot
make those edits. Instead, append to `SPEC-REVIEW-NOTES.md`:

```
## Paste-ready patches
```

containing the exact replacement text for each of:

- the `README.md` "How to read this" table — the two new rows;
- the `07 §2` status line, 🔴 → 🟢, pointing at `11` and `12`;
- the `09` rows for BE-06, BE-07 and CONTENT-04.

Give enough surrounding context that each patch is unambiguous to apply by hand.

## 9. The rest of SPEC-REVIEW-NOTES.md

Four sections, in this order:

1. **`## Decision sheet`** — every PROPOSED item as a numbered checklist, each
   answerable in one sentence, carrying the five things from §5 above. `07`'s own
   guidance is that each question should be answerable in a sentence and the answer
   written straight in. Build for that.
2. **`## Quote ledger`** — every citation used, with file and timestamp, **plus the
   negative-evidence rows**: every term searched that returned nothing. "Searched
   *threshold*, *cutoff*, *tie break*, *weightage*, *embedding* across 17 transcripts:
   1 hit, 0, 0, 0, 0." Negative evidence is what licenses PROPOSED, so it is a
   first-class output, not an apology.
3. **`## Paste-ready patches`** — per §8.
4. **`## Corrections found`** — anything in `01`–`10` your reading showed to be stale,
   with the evidence.
