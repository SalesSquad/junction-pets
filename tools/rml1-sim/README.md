# RML1 Rust Simulation Lab (development only)

Runs a dependency-free Rust 2024 deterministic campaign with four synthetic fault classes: process exit, timeout, duplicate delivery, and terminal resource denial. It emits one JSONL receipt per seed plus a summary. The `runtime_authorized` field is always `false`. This is **model-based simulation**, not execution of Chibi agents, the Factory broker, R, OCI containers or real seccomp profiles.

```sh
cd tools/rml1-sim
cargo +1.98.1 test --offline
cargo +1.98.1 run --offline --release -- --seeds 4096 --workers 8 --output /tmp/rml1-campaign.jsonl
cargo +1.98.1 run --offline --release -- --start 123 --seeds 1 --workers 1
```

All seed outcomes and fingerprints are independent of worker scheduling. The final JSONL line is an aggregate summary; denied outcomes are expected modeled refusals, not passing code execution. Compare complete files from runs with different worker counts to confirm deterministic replay. A command failure or malformed argument exits nonzero.

Next adapter boundary: connect actual Chibi scenario fixtures and Factory benign-only broker receipts, retaining their provenance separately from these synthetic outcomes. **Do not use this simulator as an RML1 host qualification or security attestation.**
