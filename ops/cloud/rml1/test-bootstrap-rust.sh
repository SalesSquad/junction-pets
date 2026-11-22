#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir "$work/bin"
export PATH="$work/bin:$PATH" HOME="$work/home"
export EXEC_MARKER="$work/executed" CURL_MARKER="$work/downloaded"
export MOCK_OS=Linux MOCK_ARCH=x86_64

cat > "$work/bin/uname" <<'SH'
#!/bin/bash
case "$1" in
  -s) echo "$MOCK_OS" ;;
  -m) echo "$MOCK_ARCH" ;;
  *) exit 2 ;;
esac
SH
cat > "$work/bin/df" <<'SH'
#!/bin/bash
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\nfixture 4194304 0 4194304 0%% /\n'
SH
cat > "$work/bin/curl" <<'SH'
#!/bin/bash
set -eu
touch "$CURL_MARKER"
while [[ "$1" != --output ]]; do shift; done
cat > "$2" <<'PAYLOAD'
#!/bin/bash
touch "$EXEC_MARKER"
PAYLOAD
SH
chmod u+x "$work/bin/"*

expect_failure() {
  local reason=$1
  local status=0
  bash "$here/bootstrap-rust.sh" > "$work/result" 2>&1 || status=$?
  [[ $status == 1 ]] && grep -Fx "rml1_rust_bootstrap_error=$reason" "$work/result" || {
    cat "$work/result" >&2
    exit 1
  }
}

MOCK_OS=Darwin expect_failure unsupported_platform
MOCK_ARCH=aarch64 expect_failure unsupported_platform
[[ ! -e "$CURL_MARKER" && ! -e "$HOME" ]]
expect_failure installer_checksum_mismatch
[[ -f "$CURL_MARKER" && ! -e "$EXEC_MARKER" ]]
[[ -z $(find "$HOME/.cargo" -mindepth 1 -print -quit) ]]

# A pinned rustc alone is a partial installation. Do not download or report success.
rm "$CURL_MARKER"
mkdir "$HOME/.cargo/bin"
cat > "$HOME/.cargo/bin/rustup" <<'SH'
#!/bin/bash
[[ "$1" == run && "$2" == 1.98.1 && "$3" == rustc ]]
SH
chmod u+x "$HOME/.cargo/bin/rustup"
expect_failure partial_install
[[ ! -e "$CURL_MARKER" ]]
echo 'RML1_RUST_BOOTSTRAP_REGRESSION=passed'
