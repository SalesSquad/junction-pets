#!/usr/bin/env bash
# Synthetic seccomp-mode regression: mode 2 + filters > 0 is NOT BPF byte proof.
set -Eeuo pipefail
here=$(cd "$(dirname "$0")" && pwd -P)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/awk" <<'AWK'
#!/bin/sh
case "$1" in
  '/^Seccomp:/{print $2}') printf '2\n' ;;
  '/^Seccomp_filters:/{print $2}') printf '5\n' ;;
  *) exec /usr/bin/awk "$@" ;;
esac
AWK
chmod 700 "$work/awk"
PATH="$work:$PATH" bash "$here/verify.sh" > "$work/result"
grep -Fq 'seccomp_mode_observed=2 seccomp_filters_count_observed=5' "$work/result"
grep -Fq 'loaded_bpf_seccomp_filter_bytes_verified=false' "$work/result"
grep -Fq 'trusted_running_oci_image_digest_verified=false' "$work/result"
if grep -Eq 'loaded_bpf_seccomp_filter_(readback|bytes_verified)=available|trusted_running_oci_image_digest_verified=true' "$work/result"; then
  echo 'RML1_VERIFY_REGRESSION unexpected_runtime_qualification' >&2
  exit 1
fi
echo 'RML1_VERIFY_REGRESSION=passed no_BPF_or_OCI_authorization_from_mode_or_count'
