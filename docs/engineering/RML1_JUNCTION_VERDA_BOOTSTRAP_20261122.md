# Junction Verda RML1 portable bootstrap — 2026-11-22

## Scope and source binding

- Work target: Codex Cloud environment `junction-verda`, recorded environment
  ID `6af658b75f108191a8e1d9db406f7456`.
- Repository/base checked before writes: `SalesSquad/junction-pets` at
  `5e9ef6cd997c38a84c1553380c655fd32d0d8d71`; the worktree was clean.
- This is task-local developer tooling evidence. No environment publication API,
  push, merge, deploy, image download/build/run, model, GPU, paid service, SSH
  key, credential, host-security, or account change was performed.

## Actual task execution

The first invocation exposed a `pipefail`/SIGPIPE defect while reading
`apt-cache policy`; it exited **141** before package installation. The defect was
fixed by consuming the complete policy output. The corrected invocation exited
**0** and selected 42 not-yet-installed packages in its simulated plan.

| Observation | Before | After corrected setup |
| --- | ---: | ---: |
| UTC | 2026-11-22T07:37:06Z | 2026-11-22T07:39:13Z |
| `dpkg-query` installed package rows | 533 | 574 |
| `/` free space (`df -Pk`, KiB) | 30,653,540 | 30,069,488 |
| setup exit | — | 0 |

The 584,052 KiB free-space delta includes the apt metadata refresh and package
installation. The package-row delta is 41; apt's pre-install simulation reported
42 `Inst` actions. Available optional tools were `skopeo`, `umoci`, `podman`,
`buildah`, `uidmap`, `fuse-overlayfs`, and `slirp4netns`. Existing `rustup` was
preserved; Rust 1.98.1 was not requested or installed.

Observed host facts were Ubuntu 24.04.4, 18,440,436 KiB reported memory, 3 online
CPUs, UID 0, no Docker CLI, and no Docker socket. These task observations do not
replace the earlier environment description and do not establish a durable host
shape.

## Read-only verification result

`verify.sh` exited **0**. It observed Node 22.22.2, Python 3.12.13, Cargo/Rust
1.89.0, Clang 17, LLVM 18.1.3, GCC 13.3.0, Git 2.43.0, jq 1.7, skopeo 1.13.3,
umoci 0.4.7, Podman 4.9.3, and Buildah 1.33.7. Podman's read-only information
query succeeded and reported rootless false with overlay storage; no engine was
started and no container was run.

The capability distinctions were:

- Docker CLI: **unavailable**.
- Docker daemon: **unavailable** (no socket and no CLI).
- Local OCI digest readback: **unavailable**, because no existing OCI layout was
  supplied; verification intentionally did not pull or build one.
- Loaded BPF seccomp filter readback: **unavailable** (`Seccomp: 0`, zero filters
  in the verifier process).

Local source review after applying the task added a test_verify.sh negative
regression: synthetic Seccomp=2 and five filters still leave loaded BPF
filter-byte verification and trusted running-OCI identity FALSE. It also
separates a caller-provided local OCI index checksum from the OCI manifest
digest of a qualified running container. This test ran on the Mac, not inside
the published Codex environment, and does not upgrade any live qualification.

These results are **not RML1 host qualification**. In particular, installing
OCI inspection clients does not prove a usable Docker daemon, portable rootless
container execution, host ptrace, a loaded seccomp policy, or an RML1 runtime.

## Desired Cloud setting after merge

An authorized human should set the published setup command in Cloud environment
Settings to exactly:

```sh
bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts
```

The `ops/environments/verda.json` row now records that desired source
configuration and preserves `npm ci --ignore-scripts`. It is **not** evidence
that the external Cloud environment setting has been published.
