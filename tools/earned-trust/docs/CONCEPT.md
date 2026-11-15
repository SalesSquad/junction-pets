# Concept card: Earned Trust

## Recommendation

Present an AI change as a small set of requirement-linked claims. For each claim,
show the exact source, the best available evidence, what the evidence cannot
establish, and what a human still needs to examine. Preserve the person's decision
without pretending that the software has delegated their accountability.

## Principles

1. **Claims need the right kind of evidence.** A fix demonstration, a regression
   invariant and a structural inspection answer different questions.
2. **Compare identical experiments.** Freeze the test, input and toolchain;
   change only the declared source revision. Report environment problems apart
   from behavior. Never manufacture a red baseline.
3. **Explain uncertainty at the decision.** The human sees why a claim is ready
   for review, needs evidence or is inspection only. No invented confidence score.
4. **Review causes and verify consequences.** A generator change can create
   hundreds of output files. Group the consequences and surface the meaningful
   sources, while retaining every changed path for inspection.
5. **Bind decisions to immutable evidence.** A changed packet or evidence file
   cannot inherit a decision silently. Export exact digests and a declared name.

## Live reference

The native macOS desk imports bounded local JSON packets, verifies local evidence
bytes, explains each claim and exports a local declaration. It operates offline;
the separate developer verifier runs the official #2283 base/head experiment.

The supplied #2297 diff is the scale example: 237 changed files, 222 generated
snapshots and 15 other files. The requirement's coverage-tool behavior remains a
separate check; recognizing generated output cannot prove that requirement.

## Explicit trade-offs

- Local hashes make tampering and stale artifacts visible but do not establish a
  trusted runner. A future authenticated CI adapter needs its own trust model.
- One frozen example provides focused evidence, not exhaustive correctness.
- Human attention is directed, not eliminated. A named declaration is not an
  authenticated identity or merge grant.
- Structural grouping may reduce noise, but review time saved and defect escape
  rate require a real user study. They are not estimated from file counts.
- Frontend state, import validation and evidence rules are part of the reference.
  Deployment, account management, production permissions and vendor selection are
  intentionally outside it.

## Measurement

The current reference measures actual observed outcomes, artifact integrity and
file classification. In a future review study, predeclare the same cases and
compare an ordinary AI summary with this evidence view. Measure false assurance,
missed defects, human time and decisions changed after seeing missing evidence.
Do not train on the held-out examples or choose only flattering results.
