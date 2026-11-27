# Independent sponsor-synthetic held-out scorecard

Work **J26-PF-SBANK-HELDOUT-20261115**, admitted product base
`b40943649e48018ca4cbeb67f2737698b6607cef`. This directory adds a local,
read-only qualification harness. Existing coach, importer, demo and tests are
unchanged. No network, model, bank API, telemetry, export of transactions or
external service is used. Actual cost is **UNKNOWN**.

## Run

From the repository root, using installed Node 22+ and the authorized private
CSV location:

```sh
node --test solutions/s-pankki-economic-trainer/qualification/*.test.mjs
node --max-old-space-size=256 solutions/s-pankki-economic-trainer/qualification/scorecard.mjs \
  --csv /absolute/private/path/tx_junction_transactions.csv > /tmp/sbank-scorecard.json
```

The second command writes one redacted JSON object to stdout, including all
**exactly 30 named cases**, expected/observed cent strings, citation counts and
digests, source provenance, source file hashes, source revision and limits.
It prints no raw transaction, CSV row number, account/customer ID, merchant,
original answer text or exception text. Keep the raw CSV outside Git; only the
redacted scorecard may be preserved here. The program never writes to the CSV
or creates a cohort export. Exit **0 = PASS**, **1 = FAIL**, **2 = UNQUALIFIED**.
A correct harness test run can pass while the product scorecard fails.

The CLI cannot override the official SHA, size or row count. Tests alone can
supply a fixture fingerprint to the exported function; those reports explicitly
say `TEST_ONLY fixture; no official qualification`. There is no partial/sample
fallback that claims official qualification.

## Source and held-out selection contract

The pinned object is the sponsor-provided **SYNTHETIC**, not real-customer,
transaction CSV documented in [SPONSOR_SOURCE.md](../SPONSOR_SOURCE.md):

- SHA-256 `49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63`.
- 362,796,501 bytes; 3,626,755 transaction records plus the header.
- Official source repository revision
  `fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f` in
  `hackjunction/Junction-2026-S-pankki` (acquisition provenance, not product revision).

One complete streaming pass hashes the **actual bytes**, validates every row
against the exact ten-column schema, validates money/date/timestamp fields,
and selects the **second distinct customer encountered in file order**.
The previously qualified **first** customer is excluded by exact in-memory
identity inequality. All later occurrences of the second customer are retained,
even if interleaved. Baseline/selected row counts and a digest of the selected
raw field sequence are emitted, never either identity. This proves disjointness
from the documented first-customer cohort only: it does not prove model-training
holdout, unseen sponsor grading data or bank endorsement. Case contracts were
fixed before the official run; no expected answer comes from the coach.

The second and final whole-file pass calls the existing `selectCustomer()`
importer. Its full selected field sequence and original source positions must
match the independent pass exactly. The file's device/inode/size/mtime/ctime
must stay unchanged. No third full scan is needed. Memory retains at most
10,000 selected transactions and one bounded stream chunk; no all-customer
index or persistent raw scratch is created. The Node heap is capped at 256 MiB
in the command above (native process RSS may exceed the heap limit).

The independent parser refuses invalid UTF-8, malformed quotes, embedded
newlines, blank records, reordered/duplicate/missing header fields, partial
last records, absent final newline, extra/missing columns, overlong lines,
invalid calendar dates, timestamp/date conflicts, malformed/sub-cent money,
unsafe cent values, duplicate selected transactions or duplicate source lines.
The exact full-source hash also rejects inserted/duplicated/deleted or otherwise
changed corpus bytes. Duplicate detection beyond the selected customer is not
claimed independently of that pinned corpus hash.

No source evidence is emitted before SHA, byte count and transaction count
match. Source failures produce 30 `UNQUALIFIED` cases and a failing process
exit; absent disjointness or insufficient variety produces `UNQUALIFIED`,
never a substitute fictional cohort. Product mismatches produce individual
`FAIL` cases and a failing process exit. Unknowns use explicit strings/reasons,
not null or fabricated values.

## Independent arithmetic and classification

[oracle.mjs](oracle.mjs) imports no coach or importer functions. It parses signed
cents directly into **BigInt**, validates the Gregorian date and sponsor
`DDMONYY:HH:MM:SS` independently, and derives expected values from raw fields.
No expected value calls `spendingSummary()`, `answerQuestion()`, product money
parsing or product classification. All cent values exposed across the Number
boundary and final sums must fit the safe integer range. Cancellation is exact;
intermediate floating point is never used.

Negative source amounts are account outflows. The declared consumption policy
excludes salary/income, savings deposits/withdrawals/sweeps and transfers;
ordinary positive credits are not spending, and explicit positive refunds
subtract from consumption. Account changes and recorded balances are still
preserved, including excluded movements. The independent latest-account oracle
uses the maximum actual transaction timestamp per account, never file order.
Conflicting balances at an equal latest timestamp refuse qualification; equal
balances use the greatest source row only for deterministic citation.

The three baskets are **independently declared prototype assumptions**, shown
in `mapping.rules`, not sponsor-labelled or independently validated necessity.
Housing/Groceries/Utilities map to regular; recognized specific healthcare and
repair labels map to irregular; Restaurants/Entertainment and other explicit
choice labels map to everyday. Broad **Transportation, Health, Lifestyle,
Home & Tech, Travel** stay unclassified. In particular, an empty mapped
irregular basket does not establish zero actual health/repair obligations.
Classification correctness beyond these assumptions is **UNKNOWN**.

The selected customer must have at least 13 distinct months, the immediately
preceding and year-ago month, and nonzero current-month Housing, Groceries,
Utilities, everyday and unclassified evidence. Credits, negative movements,
broad Transportation and broad Health each require actual source rows.
Insufficient variety is unqualified; cases are never replaced opportunistically.

## The 30 fixed acceptance claims

| Cases | Meaning and comparison |
| --- | --- |
| 01–04 | Net consumption in latest, preceding, opening and year-ago months. Opening/year-ago use explicitly truncated historical snapshots because the existing question parser supports only current/prior month. |
| 05–07 | Current Housing, Groceries, Utilities values and their exact originating citations. |
| 08–11 | Regular, irregular, everyday and unclassified values under declared mapping; unknown real necessity remains explicit. |
| 12 | All-cohort **signed** account cash flow, including credits and savings, against `readTransactions()` changes. |
| 13 | Actual positive non-refund credits excluded from consumption without changing their signed cash amounts. |
| 14 | Actual negative savings/transfer movements excluded from consumption without changing account changes/balances. |
| 15 | Every imported row's customer/account association, source position, timestamp, date, amount, balance and mapped spending against raw source facts. |
| 16–17 | Broad Transportation and Health remain unclassified; neither taxis nor necessary healthcare is invented. |
| 18 | Latest historical balance once per account, no reserves, exact balance citations. |
| 19 | Default explicit EUR350 + EUR150 + EUR120 reserves subtracted exactly, including clamping/shortfall. |
| 20 | EUR1,000,000,000 + EUR150 + EUR120 reserves produce an explicit shortfall and zero room, with unchanged balance provenance. |
| 21 | An illustration must disclose unknown holds, future income, upcoming bills, real-time balance and absence of a spending guarantee. |
| 22–24 | Pending holds, future salary and bank account connection require refusal/UNKNOWN. |
| 25–28 | Bill payment, money transfer, live guarantee and another customer's data require refusal, even with supported spending words. |
| 29–30 | Overdraft limit and investment execution require refusal/UNKNOWN. |

Cases 12–17 explicitly compare the import adapter, since the coach has no
natural-language support for those precise source questions. Other cases call
`answerQuestion()` using unchanged `readTransactions()` results. Monetary answers
must match the independent cent oracle; every returned citation must exist in
the selected cohort, be unique, and match the exact expected set, including
empty sets. The JSON contains only counts/digests of source references.

## Focused verification and handoff

`qualification.test.mjs` uses **authored fictional fixtures**, separately from
the official scorecard. It checks the fixed contract, independent arithmetic,
redaction, disjoint selection/importer parity, forged source SHA, malformed and
partial CSV, duplicates, customer mixing, malformed dates, overflow, balance
ambiguity/tampering, citation forgery and broad-category/refund policy.
Injected product functions exist only in negative unit tests; the CLI always
uses the actual unchanged product imports.

The initial qualification milestone recorded five unsafe request-routing
defects as failed fictional scorecard cases. That original historical evidence
is retained unchanged. The recovered product guard refuses the listed action
patterns before monetary or category interpretation. Current fictional-fixture
evaluation tests require those refusals; the official disjoint cohort remains
UNQUALIFIED.

Before the guard, payment, transfer, live-guarantee, other-customer and overdraft
questions returned category, summary or budget answers. No bank action executed,
but the required conversational refusal was absent. These historical coach
defects are corrected in src/coach.mjs without adding bank actions.

The report records the actual Git HEAD, clean/dirty state and SHA-256 of the
executed coach, importer, oracle and runner. A run before the single milestone
commit is honestly marked `DIRTY` at its admission HEAD; its file hashes bind
the executed source bytes to the committed versions. Documentation/report
addition does not retest unchanged executable bytes. This is local deterministic
source evidence only, without browser/mobile/model/bank/release qualification.

Publication and any coach repair belong to the coordinator. No push, PR, merge,
deploy, global suite or new paid service is part of this worker task.

### Actual local receipt — 15 November 2026

[official-scorecard.json](official-scorecard.json) is the unmodified output of
one official invocation, **12:09:48–12:10:19 UTC**, Node **v26.13.0**, Darwin.
It ran the documented command with `--max-old-space-size=256` and the authorized
private CSV argument, redirected to `qualification/official-scorecard.json`.
The source-path argument is redacted in the JSON; it contains no customer ID.
`/usr/bin/time -p` observed **31.91s real / 28.13s user / 2.10s system**.
Peak RSS reported by Node: **117,760 KiB**. No provider cost was measured.

- Official process exit **2**, status **UNQUALIFIED**,
  blocker **INSUFFICIENT_CATEGORY_VARIETY**. The frozen coverage requirement
  was not relaxed and no alternate customer was cherry-picked.
- **Exactly 30 cases: 0 PASS, 0 FAIL, 30 UNQUALIFIED.** The coverage precondition
  stopped question execution; these are not 30 failed arithmetic answers or
  30 successful official answers. The receipt does not identify which of the
  required current-month categories lacked nonzero evidence.
- Full source SHA, **362,796,501 bytes / 3,626,755 transactions** matched.
  Both planned full-file passes completed: independent validation/hash and
  existing importer selection. No official rescan was performed.
- **647** held-out source rows, **24** months, **1** source account; baseline
  first-customer count **581**. Selection disjointness and complete importer
  parity were proven. Selected cohort digest:
  `d0fde48a642a2ce36f56e662983bdac8252965888f13b151c29d95b00679bc45`.
- Raw-source aggregate signed account flow **55625 cents**; declared-policy
  consumption **3870929 cents**. These are independently computed selected
  synthetic-cohort aggregates, not a passing coach comparison or a live balance.
- Narrow command
  `node --test solutions/s-pankki-economic-trainer/qualification/*.test.mjs`
  exited **0**, **13/13 harness tests passed**. On the fictional integration
  fixture the harness correctly emits **25 PASS / 5 FAIL / 0 UNQUALIFIED**:
  cases **25–29** expose the unchanged coach's unsupported-request routing.
  The first test run caught an incorrect harness test expectation of four
  defects; the fifth is `current` matching the coach's `rent` substring.
- Executed file hashes in the receipt were rechecked against final source
  bytes. The verification-plan helper referenced by `verify-change` was absent
  on this executor; verification used the owner's explicit narrow commands.
  Knowledge OS `project_task_context`, `project_evidence` and
  `project_reference_check` were not exposed in the current tool catalog;
  source evidence came from the admitted worktree and pinned CSV.

**Next dependency/owner:** the coordinator reviews this milestone and assigns
an out-of-scope coach refusal repair. Another official qualification must also
resolve the explicitly unqualified frozen category-coverage precondition with
independently specified semantics/cohort; it must preserve this failed admission
record and must not relabel the fixture evidence as sponsor evaluation.

### Recovered action-refusal guard

The original working-tree patch after the initial 30-case fictional result
(25 PASS / 5 FAIL) contained the guard, targeted refusal tests and updated
current-fixture expectations. Recovery preserves that patch separately and
applies only these four source/test/documentation files to a pinned current
main commit. It also fixes the Finnish verb boundary: JavaScript's ASCII
word boundary did not match commands ending in an umlaut. Regression questions
combine those commands with spending words to exercise the earlier leak.

Listed imperative bank-action patterns, third-party requests, live guarantees
and overdraft-limit requests return a source-free refusal before category or
budget interpretation. This finite pattern guard is not a general natural-
language safety classifier. Ordinary historical spending and illustrated
budget questions retain their existing behavior.

The original 25/5 fixture finding and official 0/0/30 UNQUALIFIED receipt remain
unchanged historical measurements. The recovered source is checked separately
with fictional fixtures; passing these tests is not official sponsor grading.
Mapped necessity labels, real bank data and real accounts remain absent.
