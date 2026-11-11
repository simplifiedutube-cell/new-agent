# Task — implement the approved matching specification

The approved specifications are at `documentation/team-engine/11-participant-matching-algorithm.md`
and `12-advisor-matching-algorithm.md`. Their approval markers, content hashes and the
`algorithm_version` you must stamp are listed at the end of this brief.

## 1. Turn the specification into a checklist first

Delegate to `spec-reader`. It returns a numbered requirement list with stable IDs
(`R1`, `R2`, …), each traceable to a section of a specification. Work from that list.
Do not start editing before it exists — the point of the ID scheme is that at the end
you can account for every clause.

## 2. What you are replacing

`searchTalentProfiles()` in `src/services/profile.service.js` is the live search path.
Today it is a filter-and-sort: fields narrow a Sequelize query, and results are ordered
by a static per-person probability. There is no pairwise scoring anywhere in the
codebase — `match.service.js` reads `compatibility_score` straight off the contributor
record rather than computing it.

Read it before you change it, and preserve its existing callers' contract unless the
specification explicitly changes it.

## 3. Build on what is already there

Do not reimplement these:

- `src/services/skill-registry.service.js` — the skill vocabulary, with an `aliases`
  array. This is the backbone of the exact-match pass; the specification's "exact match
  first" strategy means going through this, not string-comparing raw input.
- `src/services/role-fit.service.js` — role classes and the probability vector. Where
  the specification wants role coverage from the full distribution rather than just the
  top prediction, this is where the distribution lives.
- `src/services/llm.service.js` — the existing LLM proxy, with JSON-schema-constrained
  responses. If the specification's semantic fallback is LLM-powered, it goes through
  here.
- `models/talent_profiles.js` — the available columns. Check what exists before
  proposing a migration for something that is already there.

## 4. Instrumentation is part of the work, not a follow-up

The specification requires each match to record its score components and the
`algorithm_version` that produced them. Implement that from the start: a scoring
change that cannot be attributed to a version is not measurable, and `10 §(d)` is
explicit that this is what makes the algorithm improvable later.

## 5. Tests

There is no test runner configured — `npm test` exits 1. Add tests using the built-in
`node:test` module and run them with `node --test test/`. Do not install a framework;
package installation is blocked, deliberately.

At minimum, cover:

1. **Empty is not zero** — an unscored person surfaces as "Pending", never 0.
2. **Multi-skill search** — a query with several skills returns candidates that today's
   single-substring path would miss. This is the concrete bug the specification fixes;
   test it explicitly.
3. **"Works across industries"** — an advisor with that setting matches an arbitrary
   industry query.
4. **The documented tie-break** — two candidates with identical scores come back in the
   specified order, deterministically.
5. **The threshold boundary** — a candidate just below the floor and one just above.
6. **Score components** — populated, and their keys match the specification's scoring
   table.

## 6. Migrations are written, not run

If the specification needs a schema change, write the migration file. Do not run it,
and do not run `sequelize`. Say clearly in your summary what a human needs to apply.

## 7. Report against the checklist

Finish with a table: every requirement ID, and whether it is implemented, partially
implemented, or not implemented — with a reason for anything short of done. Then have
`impl-reviewer` check your work against the same list, and report what it found.
