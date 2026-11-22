# junction-verda-rml1 Rust bootstrap receipt

22 November 2026, Codex Cloud instance
`ccarenv_b64_Y2NhcmVudl8zZTdjZjgyMDM4Njg4MTkxOGVlYzE4NTdmNjkzOWVjMQ`.
The Linux x86_64 checks ran as UID 1000 on source based on
`83e818eda88a8b88cbaec3c8e0cb768a4b49a883` (SalesSquad/junction-pets).
The published environment settings are outside this receipt.

The official Rustup archive checksum endpoint was reachable over HTTPS and
returned SHA-256
`4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10`.
The Rust 1.98.1 manifest checksum endpoint returned HTTP 200.
[Rustup checksum](https://static.rust-lang.org/rustup/archive/1.29.0/x86_64-unknown-linux-gnu/rustup-init.sha256)
· [Rust manifest checksum](https://static.rust-lang.org/dist/channel-rust-1.98.1.toml.sha256)

| Check | Result |
| --- | --- |
| `RML1_INSTALL_RUST_1_98_1=1 bash ops/cloud/rml1/setup-user.sh` | Exit 0 on install and repeat. The repeat reported versions without a download. |
| `bash ops/cloud/rml1/test-bootstrap-rust.sh` | Exit 0. Wrong OS and architecture refused, wrong SHA prevented execution, and partial install returned a typed error. |
| `bash ops/cloud/rml1/test-user.sh` | Exit 0. Offline OCI fixture accepted the valid layout and rejected corrupted bytes, a symlinked blob, and an oversized index. Synthetic seccomp regression passed. |
| `bash ops/cloud/rml1/verify.sh` with `~/.cargo/bin` on PATH | Exit 0. The verifier detected Rust 1.98.1. |
| `rustup run 1.98.1 cargo check --offline --locked` | Exit 0 on a temporary dependency-free Rust 2024 crate with a compile-time assertion. |
| `npm ci --ignore-scripts`, then `npm run build` | Both exited 0 on the pinned base in a temporary Git checkout with a writable temporary npm cache. Node v24.22.3, npm 11.19.1, 34 catalog packages. |

Rustup 1.29.0 (`28d1352db`), Cargo 1.98.1 (`797e8a9bc`), rustc
1.98.1 (`48a229cea`), rustfmt 1.9.0-stable (`48a229ceae`), and
Clippy 0.1.98 (`48a229ceae`). The verified binary rejected `--yes`
and accepted the supported noninteractive option `-y`.

`runtime_authorized=false`. Docker daemon OCI live manifest evidence and
loaded seccomp filter evidence both remain false.
