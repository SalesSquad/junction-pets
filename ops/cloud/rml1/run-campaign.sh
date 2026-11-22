#!/usr/bin/env bash
set -Eeuo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
root=$(cd -- "$here/../../.." && pwd -P)
verified=$(bash "$here/workspace.sh" verify) || exit $?
printf '%s\n' "$verified"
factory=$(printf '%s\n' "$verified" | sed -n 's/^FACTORY_ROOT=//p')
[[ -n "$factory" && -d "$factory/.git" || -f "$factory/.git" ]] || {
  echo 'RML1_WORKSPACE=BLOCKED reason=verified_factory_path_invalid' >&2
  exit 2
}
export RUSTUP_TOOLCHAIN=1.98.1
output=${RML1_CAMPAIGN_OUTPUT:-/tmp/rml1-integration}
seeds=${RML1_CAMPAIGN_SEEDS:-4096}
workers=${RML1_CAMPAIGN_WORKERS:-8}
args=(--factory-root "$factory" --seeds "$seeds" --workers "$workers" --out "$output")
if [[ -n ${RML1_CHIBI_ROOT:-} ]]; then
  if [[ ! -d $RML1_CHIBI_ROOT || -L $RML1_CHIBI_ROOT ]]; then
    echo 'RML1_WORKSPACE=BLOCKED reason=chibi_root_missing_or_symlink' >&2
    exit 2
  fi
  args+=(--chibi-root "$RML1_CHIBI_ROOT")
  args+=(--chibi-market-seeds "${RML1_CHIBI_MARKET_SEEDS:-10000}")
fi
exec python3 "$root/tools/rml1-sim/integration_campaign.py" "${args[@]}"
