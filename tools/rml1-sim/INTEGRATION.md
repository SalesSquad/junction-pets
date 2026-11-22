# RML1 integration campaign

Combines **three distinct evidence levels** without silently promoting one to another:

1. Rust synthetic 4096-seed campaign, replayed byte-for-byte at worker counts 8 and 1.
2. Existing `services/pet-adapters/registry.test.mjs` that executes the 34 real Junction pet capability fixtures offline.
3. Existing Factory Rust broker tests. On native Linux only, an actual fixed benign child launch/refusal test using the Factory source-owned canary script.

```sh
python3 tools/rml1-sim/integration_campaign.py --out /tmp/rml1-integration
python3 tools/rml1-sim/integration_campaign.py --factory-root ../factory --out /tmp/rml1-with-factory
```

The second invocation requires a separately checked-out `SalesSquad/factory` repository. The runner does not clone repositories, install packages, download artifacts, access network services or execute generated R. Factory's benign canary requires Linux and a successfully built executable; on macOS it is recorded as **not_run**, never a synthetic pass.

`receipt.json` records each actual command status, exit code, bounded diagnostic tail, source commits and the always-false `runtime_authorized` flag. `simulation.jsonl` has all 4096 seed receipts and summary. Nonzero results fail the campaign. A missing Factory checkout or native-Linux canary is explicitly `not_run` and now makes the whole campaign `overall=incomplete` (exit 2). A failed check gives `overall=fail` (exit 1); only full measured coverage gives `overall=pass` (exit 0).

These are developer tests, **not signed host attestations**. A green campaign does not authorize arbitrary/hostile R execution. The Factory broker is benign-only, and the integration never loads OCI images or seccomp filters.

## V2: 100,000 seeded scenarios and real Chibi adapter

The bounded Rust simulator accepts up to 1,000,000 seeds, with replay independent of worker count. This measures synthetic deterministic behavior only. A default integration campaign still uses 4,096 seeds, while the larger explicitly selected campaign uses:

```sh
python3 tools/rml1-sim/integration_campaign.py --factory-root ../factory \
  --seeds 100000 --workers 16 --out /tmp/rml1-integration-100k
```

Every run writes `simulation.jsonl`, `receipt.json` and `REPORT.md`. Factory tests remain mandatory for a complete Linux developer campaign. `INCOMPLETE` is exit 2 rather than a green partial.

For *real Chibi source-based Rust simulation*, supply a separately authorized clean checkout of `SalesSquad/chibi`. The optional adapter invokes Chibi's existing `tools/ci/seeded_factory.py --lane market`, not a second reimplementation of Chibi state transitions:

```sh
python3 tools/rml1-sim/integration_campaign.py --factory-root ../factory \
  --chibi-root ../chibi --chibi-market-seeds 10000 \
  --seeds 100000 --workers 16 --out /tmp/rml1-with-chibi
```

Chibi checks its own exact clean source SHA, offline Cargo cache and independently checked market ledger. It requires sufficient disk headroom and may take longer on a cold Cargo build. Its output directory and source SHA are recorded separately. If the Chibi repository is missing, `chibi_integration.status=not_run`; a failing requested Chibi check makes overall FAIL. The modern published `junction-verda-rml1` contains Junction and Factory, not automatically Chibi; the command must not assume a third repository was connected. No credentials, live payment requests, production effects or untrusted R are needed.

The written markdown report distinguishes source-executed tests from synthetic simulator summaries. Even a complete green developer campaign never sets `runtime_authorized=true`.
