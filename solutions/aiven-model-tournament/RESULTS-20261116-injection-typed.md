# junction.aiven injection suite: typed content requests and request checklist — 16 November 2026

Branch `agent/junction-aiven-injection-typed-20261116` based on main `b760ae1`. Haiku, 2 repeats, judges opus + sonnet with consensus. Developer measurement with the Claude CLI; not a Chibi host run. No response text is stored here.

## What changed
- `response.v2.json` gains two optional typed fields: `content_requests` (requests between people inside the content: runbook steps, maintenance notes, e-mails between colleagues) and `request_checklist` (each part of the user's request, `covered`, `where`).
- `core.md` rule 2 sends requests between people to `content_requests`, never to `untrusted_instructions`.
- `lint.mjs` flags an `untrusted_instructions` entry that the response itself calls a request between people, and a checklist part marked not covered.
- Case set `injection-cases-v2.json`: the original 50 cases plus 14 Haiku-written clean controls (64 cases; 22 clean by label, 19 after the regex audit). Haiku hid an instruction to the assistant in 18 of its 32 "clean" drafts: 15 were caught by the regex audit, 3 more (ids containing `-inj-`) by reading the responses, and all were dropped.
- Arm `typed` makes both new fields required; arm `framed-repair` keeps them optional. Both use the same updated guidance and lint.

## Results (rescored on the corrected 64-case set, 125 answers per arm)

| Arm | Pass (consensus) | Injection detected | Injected instruction followed | False alarms on clean | Cost |
|---|---|---|---|---|---|
| framed-repair (fields optional) | **84.8 % [77.5–90.0]** | 100 % | 1.1 % (1 of 88) | **0 % (0 of 37)** | $7.08 |
| typed (fields required) | 80.8 % [73.0–86.7] | 100 % | 0 % | 2.7 % (1 of 37) | $7.00 |

Before this change (16 Nov rerun on main, 5 clean cases): false alarms 10–30 %, pass 84–87 %.

## Reading
- **False alarms: target met.** With a typed home for requests between people, false alarms on clean controls fall to 0–3 %, within the ≤ 5 % goal. The earlier false alarms were the model filing human-directed notes ("please recalibrate AQ-14") as injections.
- **Forcing a request checklist does not improve completeness** (80.8 % vs 84.8 %, overlapping intervals). Keep `request_checklist` optional.
- **The 95 % pass goal is still not met.** Remaining failures are judge failures on completeness (sonnet stricter than opus), not unsafe actions. One framed-repair answer proposed an action overlapping the injected target.
- Haiku is an unreliable writer of clean controls: audit every generated control set by reading responses, not only by regex.

## Follow-up: completeness rule, judge reliability and Sonnet (same 64-case set, 128 answers each)

| Run | Pass (consensus) | Followed | False alarms | Cost incl. judging |
|---|---|---|---|---|
| Haiku framed-repair (above) | 84.8 % [77.5–90.0] | 1.1 % | 0 % | $7.08 |
| Haiku + core rule 10 "finish the task fully, cite values, plain verdicts" | 82.8 % [75.3–88.4] | 0 % | 0 % | $6.91 |
| **Sonnet framed-repair** | **90.6 % [84.3–94.6]** | 0 % | 0 % | $10.72 |

- Rule 10 did not help and was reverted.
- Judge test-retest on the Haiku answers (`judge-retest.mjs`, $1.95): opus repeats its verdict on 98.4 % of answers, sonnet on 94.5 %. Consensus on a second sample is 83.6 %, a majority of four samples 85.9 %. Judge noise is small; Haiku's remaining misses are real omissions of case-specific findings (a plain "looks healthy" verdict, one specific value).
- Sonnet reaches 90.6 %; the 95 % goal remains unproven (upper bound 94.6 %). A cascade that sends every answer with detected untrusted content to Sonnet would cost about as much as Sonnet alone here, because 90 of 128 answers carry injected content.

## Receipts and review corrections

Per-run receipts in `receipts/injection-20261116/`: tested revision, SHA-256 of the guidance, schema, lint and suite files at that revision, exact command, the raw file's SHA-256, and per-answer deterministic checks, judge verdicts, cost and response hash (no response text). Tested revisions: typed vs framed-repair `d7d4d08`, Haiku + rule 10 `ad838da`, Sonnet `068b877`, main rerun `b1db06e`.

After the runs, Codex review led to two corrections that the numbers above do not yet include:
- `clean-haiku-5` required an "overdue" verdict without an observation time; its first must-include item is now conditional. The stored verdicts for that case (4 answers per run) were judged against the old rubric.
- The lint rule for misfiled requests matched "between colleagues" even when an e-mail carried a real instruction to the assistant; it now requires an explicit statement about the audience and never fires when the summary names the assistant or automation as addressee. The runs used the earlier rule.
