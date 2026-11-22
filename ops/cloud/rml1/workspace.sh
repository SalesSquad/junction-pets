#!/usr/bin/env bash
# Rootless, two-repository Codex Cloud workspace bootstrap and admission.
# No credentials, cloning, sudo, privileged containers, or policy changes.
set -Eeuo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
junction=$(cd -- "$here/../../.." && pwd -P)
mode=${1:-verify}
if [[ $# -gt 1 || ( "$mode" != setup && "$mode" != verify ) ]]; then
  echo 'RML1_WORKSPACE=BLOCKED reason=usage expected=setup_or_verify' >&2
  exit 2
fi

if [[ $(uname -s) != Linux ]]; then
  echo 'RML1_WORKSPACE=BLOCKED reason=native_linux_required' >&2
  exit 2
fi

find_factory() {
  local path
  local -a candidates=(
    "${RML1_FACTORY_ROOT:-}"
    "$junction/../factory"
    "$junction/../SalesSquad/factory"
    "/workspace/factory"
    "/workspaces/factory"
    "/app/factory"
    "/repos/factory"
  )
  for path in "${candidates[@]}"; do
    [[ -n "$path" && -d "$path" && ! -L "$path" ]] || continue
    [[ -f "$path/tools/factory_os/r_evaluator/linux_broker/Cargo.toml" ]] || continue
    (cd -- "$path" && pwd -P)
    return 0
  done
  return 1
}

if ! factory=$(find_factory); then
  echo 'RML1_WORKSPACE=INCOMPLETE reason=factory_checkout_missing required_repo=SalesSquad/factory' >&2
  exit 2
fi
if [[ ! -d "$junction/.git" && ! -f "$junction/.git" ]]; then
  echo 'RML1_WORKSPACE=BLOCKED reason=junction_git_checkout_missing' >&2
  exit 2
fi
if [[ ! -d "$factory/.git" && ! -f "$factory/.git" ]]; then
  echo 'RML1_WORKSPACE=BLOCKED reason=factory_git_checkout_missing' >&2
  exit 2
fi

if [[ "$mode" == setup ]]; then
  # The published setup must run on a non-root Linux x86_64 worker.
  # In particular it cannot silently succeed without the pinned toolchain.
  RML1_INSTALL_RUST_1_98_1=1 bash "$here/setup-user.sh"
fi

if [[ $(uname -m) != x86_64 ]]; then
  echo 'RML1_WORKSPACE=BLOCKED reason=linux_amd64_required' >&2
  exit 2
fi

export PATH="$HOME/.cargo/bin:$PATH"
if ! command -v rustup >/dev/null 2>&1; then
  echo 'RML1_WORKSPACE=BLOCKED reason=rustup_unavailable' >&2
  exit 2
fi
if ! rustup run 1.98.1 rustc --version | grep -Eq '^rustc 1\.98\.1([[:space:]]|$)'; then
  echo 'RML1_WORKSPACE=BLOCKED reason=rust_version_mismatch' >&2
  exit 2
fi
if ! rustup run 1.98.1 cargo --version | grep -Eq '^cargo 1\.98\.1([[:space:]]|$)'; then
  echo 'RML1_WORKSPACE=BLOCKED reason=cargo_version_mismatch' >&2
  exit 2
fi

if ! command -v node >/dev/null 2>&1; then
  echo 'RML1_WORKSPACE=BLOCKED reason=node_unavailable' >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo 'RML1_WORKSPACE=BLOCKED reason=python_unavailable' >&2
  exit 2
fi

junction_head=$(git -C "$junction" rev-parse --verify HEAD) || exit 2
factory_head=$(git -C "$factory" rev-parse --verify HEAD) || exit 2
[[ $junction_head =~ ^[0-9a-f]{40}$ && $factory_head =~ ^[0-9a-f]{40}$ ]] || {
  echo 'RML1_WORKSPACE=BLOCKED reason=source_revision_missing' >&2
  exit 2
}
printf 'RML1_WORKSPACE=READY mode=%s\n' "$mode"
printf 'JUNCTION_ROOT=%s\nJUNCTION_SHA=%s\n' "$junction" "$junction_head"
printf 'FACTORY_ROOT=%s\nFACTORY_SHA=%s\n' "$factory" "$factory_head"
printf 'RUST=%s\n' "$(rustup run 1.98.1 rustc --version)"
printf 'RUNTIME_AUTHORIZED=false\n'
