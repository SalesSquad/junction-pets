# junction-verda-rml1: Cloud workspace source contract

The **modern**, published `junction-verda-rml1` environment is distinct from the old CLI `junction-verda` environment (legacy identifier `6af658b75f108191a8e1d9db406f7456`). Do not interpret a legacy CLI task labelled `junction-verda` as evidence from the modern environment.

## Required repositories and setup

Select BOTH private GitHub repositories in the *same* published environment:
- `SalesSquad/junction-pets` at `/workspace/junction-pets` (primary)
- `SalesSquad/factory` at `/workspace/factory`

Install script on Linux/amd64, **non-root**:

```sh
cd /workspace/junction-pets
bash ops/cloud/rml1/workspace.sh setup
npm ci --ignore-scripts --no-audit --no-fund
```

The workspace script explicitly checks the Factory source checkout **before** downloading Rust. It installs Rust 1.98.1 by the existing SHA-verified rootless bootstrap, then checks exact Rust/Cargo versions, Node/Python, both Git source identities and the unqualified runtime flag. Missing Factory is INCOMPLETE with exit 2. The script never downloads the private Factory repository, bypasses authentication, runs OCI/R candidates, or alters kernel policy.

At the start of each task:

```sh
cd /workspace/junction-pets
bash ops/cloud/rml1/workspace.sh verify
```

For a full, bounded developer campaign:

```sh
cd /workspace/junction-pets
bash ops/cloud/rml1/run-campaign.sh
```

This actually runs the existing 34-pet fixture suite, Rust simulation and Factory broker source + fixed benign canary. It must report `overall=pass` **only** if every step including native Linux ran; `fail` and `incomplete` remain distinct. Evidence is written under `/tmp/rml1-integration`, not into the source tree. It remains **developer evidence only**; OCI running manifest, loaded seccomp BPF bytes, independent host identity and signed process attestation are separate security gates.

## Publication and version identity

`ops/environments/junction-verda-rml1.json` is a desired configuration declaration. GitHub commits **do not** republish a Cloud environment. Edit the installed environment's setup script and start skill in the Codex Cloud environment panel, verify the new setup, and use **Publish/Republish**. Only a fresh task plus checked source SHAs proves the published revision is active. Do not change the old `ops/environments/verda.json` legacy environment or the separate Pro/Plus CLI profiles.

The earlier modern environment already proved Rust 1.98.1 and both source checkouts; its fixed PIDFD probe has separately encountered a `cgroup_path_invalid` refusal. That refusal is a diagnostic result and must not be rewritten as a successful security qualification.
