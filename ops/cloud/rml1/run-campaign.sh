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
exec python3 "$root/tools/rml1-sim/integration_campaign.py" --factory-root "$factory" --out "$output"
