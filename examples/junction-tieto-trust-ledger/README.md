# Tieto 351 — Earned Trust in AI Code

Junction 2026 event-created **reference concept**, not a production AI reviewer or a Chibi capability. It illustrates how requirement-linked evidence can replace some line-by-line reading while a named human keeps responsibility. It never executes code, calls a model, authenticates test logs or approves changes.

## Run

From this directory with Node 22+:

```sh
node --test ledger.test.mjs
node demo.mjs
```

The demo uses a deliberately **synthetic** set of check outcomes. Although the sample source SHA values and changed paths are real GitHub provenance, the purported pass/fail results are **not** test executions. The sample illustrates a favorable claimed fail→pass check and a deceptive pass→pass check; the gate refuses both as proven evidence and explicitly flags the second as nondiscriminating. Do not report the fictional outcomes as MessagePack test results.

## Official challenge mapping

| Tieto judge criterion | Our reference concept and limitation |
| --- | --- |
| Clarity 30% | Requirement → claim → specific check → exact base/head → refusal and human-owned decision. Clear limits and failure reasons. |
| Practicality 25% | Pure deterministic JSON evaluator can sit next to a PR but does not claim hosted GitHub integration, model execution or authenticated reviewers. |
| Measurement 25% | Counts reviewable vs refused claims; demo surfaces nondiscriminating evidence. Actual review-time, defect/incident/revert and merge-time effects remain **unmeasured**. |
| Evidence 20% | Rejects missing check, stale SHA, non-discriminating checks and synthetic-only proof. Returns human-review paths. No log-content or digital-signature validation yet. |

## Real provenance, synthetic checks

Official [challenge #351](https://hackjunction.app/participate/45/challenges/351) requests a concept and reference implementation, with synthetic or cleared data and a named human. The organizers provide [MessagePack C# sample](https://github.com/te-industry-tech-office/junction26-messagepack-csharp), an MIT-licensed repository with four AI-change branches. Branch refs were independently read on 14 Nov 2026:

| Sample branch | Base SHA | Head SHA | Changed files |
| --- | --- | --- | ---: |
| `ju26-issue-2283` | `32258fdbee4bcd653c79f51b4376b5103c6f4d27` | `9df83c38409c8bfad0517aebffe48211eda4a5b4` | 4 |
| `ju26-issue-2234` | same | `9007cee1163c4a274fd60c3cc20c21ae63622786` | 4 |
| `ju26-issue-2129` | same | `083afd994c1c9a994cb2cd5aa0b6ad805a621457` | 28 |
| `ju26-issue-2297` | same | `a0aa5ab2de7f5a669d97e37184a89034c1de82b6` | 237 |

The `fixture.json` selects #2283 and uses actual changed paths from its commit. Sample source remains in the upstream repository; **no external code is copied** into this reference. Its license was read, not modified or granted anew. The `baseSha` refers to the common merge-base observed with GitHub's compare endpoint, not a compiled failing baseline.

## Design decisions and failure modes

1. A change claim is never accepted merely because an AI describes a test as green. A meaningful *differentiating* check fails on the declared base and passes on the declared head. Pass→pass, fail→fail and missing runs are not proof of that change.
2. Checks bind to exact commit SHAs and requirement IDs. Different SHAs, unrelated requirements and missing checks are refused.
3. Synthetic results are clearly ineligible to prove behavior. A self-reported run needs a log digest before it is even ready for manual validation, but the digest is not authenticated or checked in this slice.
4. A named reviewer's recorded acceptance can never perform an actual merge or grant authority. The real identity, run artifacts and code review are separate human responsibilities.
5. Returned `humanReviewSet` points to minimal relevant files; no measured claim is made about actual lines or time saved.

**Next high-value experiment:** execute a focused .NET sample check on exact upstream base/head #2283, preserve real log bytes and hashes, confirm the expected fail→pass differential, then measure false assurances caught and human lines read against a plain AI summary. Until then, this is a working reference **of decision rules**, not proof that MessagePack issue #2283 is fixed.
