# Fable 5.2 independent architecture advice — 13 November 2026

Source reviewed: `61f10a44cfd833e02fa64462dfc7429046fff210`; excerpts only, before implementation diff review. Executor: owner's existing signed-in first-party Claude CLI on MacBook Pro, requested alias `fable`, reported canonical model `claude-fable-5-2`. Completed 2026-11-13 15:48 UTC, exit 0. This is advisory model output, not independent verification of source defects, model quality, Chibi authority or deployment.

Assessment is from the pasted excerpts only; I have not seen the registry, WebMCP or PG-store diffs, so every path-level claim below is a check to make, not a verified defect.

```json
{
  "verdict": {
    "highest_leverage": "No. All four are sound, but three are 34-wide hygiene and the fourth (PG replay store) has no caller. Nothing in the set produces a runnable end-to-end product.",
    "decision": "Keep all four, apply the P0 corrections, and add one integration target now: a single Aiven vertical that runs with a real pinned-doc fetch, a real model call and real PostgreSQL.",
    "tiers_kept_separate": {
      "source_checks": "validate/test/build at exact SHA 61f10a4 (tree 9eaf211); says nothing about quality or runtime",
      "measured_quality": "0 today; the CLI capture yields `candidate-pass`, `qualified:false`, `supplied-unverified` at best",
      "actual_runtime": "0 today; Chibi seam disabled, Council has only fakes",
      "competition_eligibility": "unknown for all 34; owner/organizer decision per docs/JUNCTION_SUBMISSION.md. Chibi pre-exists and must be disclosed; no brief is recovered, so 'Aiven-centered' is not an Aiven challenge entry"
    }
  },
  "p0": [
    {
      "risk": "No runnable spine: Council needs authenticator, HostPolicy, PetExecutor, HostArtifactStore and ReplayStore, and only fakes exist.",
      "fix": "Add one small, loudly labelled synthetic demo host (e.g. services/demo-host/): fixed synthetic tenant, public/synthetic data only, read-only, localhost, receipts marked `hostAttested:false`. Needs a short design record per ARCHITECTURE.md; never call it Chibi."
    },
    {
      "risk": "Eval capture contamination: the Claude CLI loads global CLAUDE.md, repo AGENTS.md, hooks, MCP tools and memory, so you would measure the dev harness, not the pet.",
      "fix": "Run from an empty directory with pets/<co>/AGENTS.md as the whole system prompt, tools off, and no settings, hooks, MCP or memory (confirm flags with `claude --help`). Record the resolved model ID and add a no-persona control run."
    },
    {
      "risk": "Provenance mislabel: services/eval-runner/runner.mjs `runBatch` requires `issuer:'chibi-host'` verdicts, and the docs/BEHAVIOR_EVALS.md example uses `method:'human'`.",
      "fix": "Never stub a chibi-host policy. Use the `scripts/behavior-eval.mjs check` submission path, add an explicit model-review method value (integrator-owned), and report `candidate-pass`, never `pass`."
    },
    {
      "risk": "Reviewer independence is weak: responder and reviewer are the same model family via the same CLI.",
      "fix": "Use a different model in a fresh context that sees only prompt, response and criteria. Add a human check of one case per company plus every reviewer disagreement, and publish the agreement rate."
    },
    {
      "risk": "PG store may return `durable=True` (required by `valid_reservation` in services/council/council/replay.py) on fake-only tests, and the Protocol has no way to advance a fence, so `is_current` would always be true.",
      "fix": "Test against a real Postgres and report skipped, not passed, when there is no DSN. Use unique key (tenant_id, user_id, first_request_id), INSERT … ON CONFLICT under READ COMMITTED, a DB-issued fence and immutable digests. Exclude `created` from `is_current`, add a host-only supersede/revoke method outside the Protocol, and test stale-fence denial."
    },
    {
      "risk": "Aiven citation drift: pets/aiven/AGENTS.md cites `identify-pg-slow-queries` and `repair-pg-index`, but services/pet-adapters/aiven/adapter.mjs pins only `optimize-pg-slow-queries` and `monitor-consumer-group` (persona says three pages reviewed).",
      "fix": "Align the persona and the pins so every cited URL is byte-verifiable. Route it through PR55 if that PR owns the pins; do not open a competing change."
    }
  ],
  "p1": [
    "adapter.mjs `OUT_OF_SCOPE_ACTIONS` refuses benign read questions ('lag after we remove a consumer', 'drop in throughput'). Return the docs with an advisory flag instead, or measure the false-abstention rate.",
    "Registry: use one descriptor per lane with an integrator-generated aggregate, and test that each entry maps to a real export with round-trip fixtures. Suggested fields: `effect:none`, `network:none|pinned-public-get`, `liveProvider:false`, `evidenceTier`. A listing is never a grant.",
    "WebMCP: feature-detect it as progressive enhancement over the same visible handlers, keep tool descriptions static, and treat pet-authored text as bounded untrusted data. A mocked `navigator.modelContext` test is a source check; one real-browser run is needed for a runtime claim. The API is still moving, so check the current spec.",
    "services/dispatch-ledger/ already has lease/fence primitives. Reuse its schema or declare a separate namespace; do not ship two fence authorities.",
    "Keep the replay tables in a separate schema and role from the LangGraph PostgresSaver, so a checkpoint cannot self-attest.",
    "The six authored cases per pet measure restraint, not usefulness. 204/204 would not show the pets are useful.",
    "Pilot 12 cases (Aiven and AfterQuery) to prove the harness, then run all 204 once from a fresh worktree at 61f10a4. The local checkout is 93 commits behind. Fix the run count in advance and keep failures.",
    "runner.mjs `KNOWN_PROVIDERS` lists 'aiven', which is not a model provider. Remove it or it invites a misleading receipt.",
    "The demo must say at-least-once, not exactly-once (per services/council/README.md)."
  ],
  "winning_demo": {
    "title": "Slow query to a cited, reviewed, replay-proof answer",
    "script_90s": [
      "0-10s: catalog; an in-browser agent or a click selects the Aiven companion with visible navigation. Banner: independent, not endorsed, no Aiven account connected.",
      "10-30s: paste a synthetic, labelled slow-query bundle (SQL, EXPLAIN, pg_stat_statements row). `searchAivenPublicDocs` fetches the pinned page and shows `VERIFIED_SOURCE_BYTES`, commit and SHA-256.",
      "30-55s: real model call returns Observed / Hypothesis / Next check, citing only byte-verified pages.",
      "55-75s: Council second handoff: the AfterQuery companion checks the answer for unsupported success claims using pets/afterquery's rubric, then the human-review interrupt is approved.",
      "75-90s: resubmit and get the same run ID with no second invocation; change one byte and get HTTP 409. Show the PG row (fence, two digests). Close on one measured number against the no-persona baseline."
    ],
    "needs": [
      "the demo host (P0)",
      "the PG replay store on real Postgres",
      "the Aiven pin alignment (P0)",
      "an owner decision to use the Claude CLI as the local executor; otherwise replay a recorded response labelled 'recorded at SHA, not live'"
    ],
    "datastore": {
      "choice": "PostgreSQL only",
      "why": "The actual need is atomic reserve, a unique constraint, a monotonic fence, immutable records, the LangGraph checkpointer, eval records and a corpus of a few pinned pages (tsvector is enough).",
      "kafka": "No. There is no stream, consumer fan-out or throughput need; a future outbox starts as a PG table.",
      "opensearch": "No. Revisit only beyond roughly 100k chunks or if hybrid ranking is needed.",
      "valkey": "No. Fences and idempotency need durable transactional state; it would only suit ephemeral rate limiting, which is not needed yet.",
      "hosting": "Local Postgres now. Say 'PostgreSQL', not 'on Aiven', until the owner provisions an Aiven service (credential and spend decision)."
    }
  },
  "next_waves": {
    "per_company_rubric": {
      "S_source": "S0 authored; S1 gates pass at exact SHA; S2 capability descriptor, fixtures and independent review",
      "Q_quality": "Q0 none; Q1 6/6 captured and model-reviewed (candidate); Q2 three or more golden tasks with ground truth, beats the no-persona baseline, zero mustNotClaim violations, human spot-check; Q3 held-out set, three or more repeat runs stable",
      "R_runtime": "R0 none; R1 analyzer on real public input in the demo host; R2 full Council path with real model and durable PG; R3 Chibi host-signed receipts",
      "E_eligibility": "E0 unknown; E1 dated primary-source brief recovered; E2 owner decides to enter with pre-existing work disclosed; E3 submitted",
      "rule": "Report the four axes separately, never as one status. Invest only in companies with a pinnable public corpus and an objectively checkable task; the rest stop at S1/Q1 with honest labels."
    },
    "wave_1": "Land the four with P0 fixes, plus the demo host and the Aiven vertical. Exit: one command reproduces the 90s flow, including the 409. Target: Aiven at S2/Q1/R2.",
    "wave_2": "Measured usefulness for Aiven, AfterQuery, MariaDB and at most two more: golden tasks, baseline delta, fixes for the top failures, Aiven corpus to about 10 pinned pages after PR55. Target: Q2.",
    "wave_3": "Enable the Chibi seam for this one workflow (signed receipts, real tenant; R3), and the owner eligibility decision with a submission pack. The other 31 get no bespoke demos."
  },
  "training_evaluation": {
    "training": "No fine-tuning is justified. 'Training' here means persona and analyzer iteration only.",
    "split": "The 204 authored cases become the dev set once used for iteration. Have a different author write a held-out set, and never tune against it.",
    "key_metric": "Delta against the same model with no persona on ground-truth tasks. If a pet does not beat plain Claude, it adds friction, not value.",
    "also_track": [
      "mustNotClaim violation rate",
      "false-abstention rate",
      "citation validity (cited URL is in the byte-verified set)",
      "reviewer-human agreement"
    ],
    "claim_ceiling": "CLI captures are real model calls with self-reported receipts, so they stay `supplied-unverified` with `providerInvocationsVerified:0`. They are not provider-qualified or host-qualified."
  }
}
```

## Reported usage

```json
{
  "claude-fable-5-2": {
    "inputTokens": 2,
    "outputTokens": 15087,
    "cacheReadInputTokens": 649,
    "cacheCreationInputTokens": 52219,
    "webSearchRequests": 0,
    "costUSD": 1.4391298,
    "contextWindow": 1000000,
    "maxOutputTokens": 128000,
    "thinkingTokens": 11220,
    "cacheCreationEphemeral5mInputTokens": 0,
    "cacheCreationEphemeral1hInputTokens": 52219,
    "canonicalModel": "claude-fable-5-2",
    "provider": "firstParty",
    "costBasis": "list"
  }
}
```

CLI-reported list cost: 1.4391298 USD; actual billing unknown.

