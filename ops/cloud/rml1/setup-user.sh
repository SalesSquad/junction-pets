#!/usr/bin/env bash
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
rust=unavailable
if command -v rustup >/dev/null; then
  if rustup run 1.98.1 rustc --version >/dev/null 2>&1; then
    rust=installed
  elif [[ ${RML1_INSTALL_RUST_1_98_1:-0} == 1 ]]; then
    free_kib=$(df -Pk -- "${RUSTUP_HOME:-$HOME}" | awk 'NR == 2 {print $4}')
    (( free_kib >= 2097152 )) || { echo 'Rust setup requires 2 GiB free' >&2; exit 1; }
    timeout --kill-after=10s 600s rustup toolchain install 1.98.1 --profile minimal
    rustup run 1.98.1 rustc --version
    rust=installed
  else
    rust=not_requested
  fi
fi

python3 -I "$here/check-oci-layout.py" --help >/dev/null
printf 'rml1_local_oci_checker=available\nrml1_pinned_rust_1_98_1=%s\n' "$rust"
df -h -- "$here"
