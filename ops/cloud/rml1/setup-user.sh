#!/usr/bin/env bash
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
python3 -I "$here/check-oci-layout.py" --help >/dev/null
echo 'rml1_local_oci_checker=available'

rust=unavailable
if [[ ${RML1_INSTALL_RUST_1_98_1:-0} == 1 ]]; then
  bash "$here/bootstrap-rust.sh"
  rust=installed
elif command -v rustup >/dev/null || [[ -x "$HOME/.cargo/bin/rustup" ]]; then
  rust=not_requested
fi
printf 'rml1_pinned_rust_1_98_1=%s\n' "$rust"
df -h -- "$here"
