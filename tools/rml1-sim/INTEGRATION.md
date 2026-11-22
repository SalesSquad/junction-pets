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
