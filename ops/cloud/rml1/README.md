# RML1 portable developer bootstrap

This directory provides a bounded, reusable **developer-only** bootstrap for the
Codex Cloud environment `junction-verda`. It does not qualify an RML1 host and
does not modify kernel, account, capability, daemon, or network policy.

## Published setup command (desired source configuration)

After this source is merged, configure the Cloud environment Settings setup
command exactly as follows:

```sh
bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts
```

The repository declaration is desired configuration only. This task does not
call a Cloud publication API and does not prove the published setting changed.

## Rootless Codex Cloud setup

On a Linux cloud VM with Python 3 and no apt privileges, run:

```sh
RML1_INSTALL_RUST_1_98_1=1 bash ops/cloud/rml1/setup-user.sh
bash ops/cloud/rml1/verify.sh
bash ops/cloud/rml1/test-user.sh
```

The installer uses an existing rustup when available. It reuses an installed
Rust 1.98.1 toolchain, or with the opt-in and sufficient disk space requests the
minimal profile with a ten-minute timeout. Without rustup it reports Rust
unavailable and leaves the Python checker available.

Inspect a caller-supplied OCI layout with:

```sh
python3 -I ops/cloud/rml1/check-oci-layout.py /path/to/local-oci-layout
```

The checker reads the local index and verifies the sizes and SHA-256 digests of
its direct descriptors. Files are capped at 4 MiB each, with at most 64
descriptors and 16 MiB of descriptor content. It does not inspect transitive
layers or establish the provenance of a running image.

## Use

```sh
bash ops/cloud/rml1/setup.sh
bash ops/cloud/rml1/verify.sh
```

`setup.sh` uses only the existing OS `apt`, prints its package plan, applies
timeouts and a 1.5 GiB estimated-install bound, and skips available optional OCI
tools if the combined plan exceeds that bound. Set
`RML1_INSTALL_RUST_1_98_1=1` to ask an already-installed `rustup` to install
Rust 1.98.1; the default preserves the current toolchains and makes no rustup
network request.

`verify.sh` performs observations only: it makes no image download, image build,
or container run. It never infers loaded BPF bytes from Seccomp mode or
a positive filter count, and never treats a caller-supplied OCI index
checksum as evidence of a trusted running container. Run the optional
test_verify.sh regression: it feeds synthetic Seccomp=2 and five filters but
still requires a negative RML1 host-qualification result.

Pass a pre-existing local OCI image layout to inspect the untrusted index
checksum and attempt local manifest-byte inspection:

```sh
bash ops/cloud/rml1/verify.sh /path/to/local-oci-layout
```

Development image manifests must pin the base by immutable digest, for example
`FROM example.invalid/dev/toolchain@sha256:<64-hex-digest>`. Tags alone are not
accepted as reproducible evidence. This repository deliberately supplies no
candidate image, `R`, `Rscript`, pull, or build command.
