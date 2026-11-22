#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'rml1_rust_bootstrap_error=%s\n' "$1" >&2
  exit 1
}

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  fail unsupported_platform
fi
[[ $(id -u) != 0 ]] || fail root_forbidden

export CARGO_HOME="$HOME/.cargo" RUSTUP_HOME="$HOME/.rustup"
export RUSTUP_DIST_SERVER=https://static.rust-lang.org
export RUSTUP_UPDATE_ROOT=https://static.rust-lang.org/rustup
umask 077
for directory in "$CARGO_HOME" "$RUSTUP_HOME"; do
  [[ ! -L "$directory" ]] || fail unsafe_home
  mkdir -p -- "$directory" || fail home_unavailable
  [[ -O "$directory" && -w "$directory" ]] || fail unsafe_home
done

# Serialize bootstrap attempts without locking other Rust commands.
exec 9<"$CARGO_HOME"
flock -w 30 9 || fail bootstrap_busy

rustup="$CARGO_HOME/bin/rustup"
pin=1.98.1
host=x86_64-unknown-linux-gnu
report_versions() {
  local tool
  for tool in cargo rustc rustfmt clippy-driver; do
    timeout --kill-after=5s 15s "$rustup" run "$pin" "$tool" --version || return 1
  done
}

if [[ -x "$rustup" ]] && timeout --kill-after=5s 15s "$rustup" run "$pin" rustc --version >/dev/null 2>&1; then
  report_versions || fail partial_install
  exit 0
fi

free_kib=$(df -Pk -- "$RUSTUP_HOME" | awk 'NR == 2 {print $4}') || fail disk_check_failed
[[ "$free_kib" =~ ^[0-9]+$ ]] && (( free_kib >= 2097152 )) || fail insufficient_disk

if [[ -x "$rustup" ]]; then
  timeout --kill-after=10s 600s "$rustup" toolchain install "$pin" --profile minimal || fail toolchain_install_failed
else
  url=https://static.rust-lang.org/rustup/archive/1.29.0/x86_64-unknown-linux-gnu/rustup-init
  sha256=4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10
  staging=$(mktemp -d "$CARGO_HOME/rml1-rustup.XXXXXXXX") || fail staging_failed
  trap 'rm -rf -- "$staging"' EXIT
  installer="$staging/rustup-init"
  curl --disable --proto '=https' --tlsv1.2 --fail --silent --show-error \
    --connect-timeout 10 --max-time 90 --max-filesize 33554432 \
    --output "$installer" "$url" || fail installer_download_failed
  printf '%s  %s\n' "$sha256" "$installer" | sha256sum --check --status || fail installer_checksum_mismatch
  chmod u+x -- "$installer" || fail installer_permissions_failed
  timeout --kill-after=10s 600s "$installer" -y --profile minimal \
    --default-host "$host" --default-toolchain "$pin" --no-modify-path || fail installer_failed
fi

timeout --kill-after=10s 600s "$rustup" component add --toolchain "$pin" rustfmt clippy || fail partial_install
report_versions || fail partial_install
