#!/usr/bin/env bash
# Offline platform/credential-free admission regression; never installs Rust.
set -Eeuo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/junction/ops/cloud/rml1" "$tmp/junction/.git" "$tmp/factory/.git"
mkdir -p "$tmp/factory/tools/factory_os/r_evaluator/linux_broker" "$tmp/home/.cargo/bin" "$tmp/bin"
cp -- "$here/workspace.sh" "$tmp/junction/ops/cloud/rml1/workspace.sh"
printf '[package]\nname = "fixture"\n' > "$tmp/factory/tools/factory_os/r_evaluator/linux_broker/Cargo.toml"
cat > "$tmp/bin/uname" <<'EOF'
#!/bin/sh
case "$1" in
  -s) echo "${MOCK_OS:-Linux}";;
  -m) echo "${MOCK_ARCH:-x86_64}";;
  *) exit 2;;
esac
EOF
cat > "$tmp/home/.cargo/bin/rustup" <<'EOF'
#!/bin/sh
case "$*" in
  "run 1.98.1 rustc --version") echo "rustc ${MOCK_RUST_VERSION:-1.98.1} (fixture)";;
  "run 1.98.1 cargo --version") echo "cargo 1.98.1 (fixture)";;
  *) exit 2;;
esac
EOF
cat > "$tmp/bin/git" <<'EOF'
#!/bin/sh
case "$*" in
  *junction*) printf '%040d\n' 1;;
  *factory*) printf '%040d\n' 2;;
  *) exit 2;;
esac
EOF
chmod +x "$tmp/bin/"* "$tmp/home/.cargo/bin/rustup"
export PATH="$tmp/bin:$PATH" HOME="$tmp/home"
runner="$tmp/junction/ops/cloud/rml1/workspace.sh"
bash "$runner" verify > "$tmp/result"
grep -Fx 'RML1_WORKSPACE=READY mode=verify' "$tmp/result"
grep -Fx 'RUNTIME_AUTHORIZED=false' "$tmp/result"
if MOCK_RUST_VERSION=1.97.0 bash "$runner" verify > "$tmp/out" 2>&1; then
  echo 'ERROR: wrong Rust accepted' >&2; exit 1
fi
grep -F 'reason=rust_version_mismatch' "$tmp/out"
if MOCK_ARCH=aarch64 bash "$runner" verify > "$tmp/out" 2>&1; then
  echo 'ERROR: wrong architecture accepted' >&2; exit 1
fi
grep -F 'reason=linux_amd64_required' "$tmp/out"
if MOCK_OS=Darwin bash "$runner" verify > "$tmp/out" 2>&1; then
  echo 'ERROR: macOS accepted' >&2; exit 1
fi
grep -F 'reason=native_linux_required' "$tmp/out"
mv "$tmp/factory" "$tmp/not-factory"
set +e
bash "$runner" verify > "$tmp/out" 2>&1
code=$?
set -e
[[ $code -eq 2 ]] || { echo "ERROR: missing Factory exit=$code" >&2; exit 1; }
grep -F 'reason=factory_checkout_missing' "$tmp/out"
echo RML1_TWO_REPO_WORKSPACE_REGRESSION=passed
