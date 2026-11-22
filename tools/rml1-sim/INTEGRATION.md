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

## Measured model-only throughput

Compile exactly once and compare fixed seed ranges across worker counts without creating additional Cargo builds:

```sh
cd tools/rml1-sim
cargo build --offline --release
python3 benchmark.py --seeds 100000 --repeats 3 --out /tmp/rml1-performance
```

The benchmark records wall time, scenarios/second and serial speedup for 1, 2, 4, 8 and 16 workers in `perf.json` and `PERF.md`. It validates byte-exact JSONL replay for every repetition and fails on mismatches. Generated files are deleted between worker counts to avoid unbounded disk accumulation. Results are environment-specific and describe the **synthetic simulator**, not agent model execution, Chibi's Rust market, or Factory runtime performance.

## Cross-environment receipt reconciliation (source-only)

The modern Codex Cloud `junction-verda-rml1` environment and the separate `chibi-pro` environment may execute independently. Use `reconcile_evidence.py` to compare their actual exported machine-readable evidence *without* asserting the same host, signing authority, privileged sandbox, or production runtime. It accepts an existing Junction `receipt.json` and Chibi `tools/ci/seeded_factory.py` `result.json`. Both must be exact source-pinned.

```sh
python3 tools/rml1-sim/reconcile_evidence.py \
  --junction /private/receipts/junction/receipt.json \
  --junction-sha FULL_40_HEX_JUNCTION_HEAD \
  --chibi /private/receipts/chibi/result.json \
  --chibi-sha FULL_40_HEX_CHIBI_HEAD \
  --out /private/receipts/reconciled.json
```

The reconciler validates Junction's 100,000 simulated seeds and actual 34-agent registry checks, Chibi's independently executed minimum 10,000-seed Rust market campaign, source SHAs, scenario counts, signed-off exclusion of live egress and external credentials, and exact market trace SHA shape. A Factory source check + fixed benign canary must also have passed in the **same Junction Linux developer receipt** to produce `coverage=pass`. Absent Chibi or Factory keeps `coverage=incomplete` and exits 2; falsified authority, unexpected source, incomplete output or contradictory states are rejected with exit 1.

This is **untrusted development evidence**, not independently signed host attestation. A complete developer coverage result always says `authenticated_host_evidence=false`, `qualified=false`, and `runtime_authorized=false`. If Cloud tasks produce no downloadable receipts, do not fabricate them or treat a mere task READY state as test proof.
