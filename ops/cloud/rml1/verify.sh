#!/usr/bin/env bash
set -u

status=0
have() { command -v "$1" >/dev/null 2>&1; }
one_line_version() { if have "$1"; then printf '%-14s %s\n' "$1" "$(timeout 8 "$1" --version 2>&1 | head -n1 || echo version-unavailable)"; else printf '%-14s unavailable\n' "$1"; fi; }

echo '== RML1 developer tool versions =='
for tool in node npm python3 pip3 cargo rustup rustc clang llvm-config gcc git jq skopeo umoci podman buildah newuidmap fuse-overlayfs slirp4netns; do one_line_version "$tool"; done

echo '== Capability observations (not RML1 host qualification) =='
if have docker; then echo 'docker_cli=available'; else echo 'docker_cli=unavailable'; fi
if [[ -S /var/run/docker.sock ]] && have docker && timeout 8 docker info >/dev/null 2>&1; then
  echo 'docker_daemon=usable'
else
  echo 'docker_daemon=unavailable'
fi

if have rustup; then
  if rustup toolchain list 2>/dev/null | grep -Eq '^1\.98\.1(-| |$)'; then
    echo 'rml1_pinned_rust_1_98_1=installed'
  else
    echo 'rml1_pinned_rust_1_98_1=not_installed (optional setup opt-in required)'
  fi
else echo 'rml1_pinned_rust_1_98_1=unavailable'; fi

if have podman; then
  if timeout 15 podman info --format 'podman_info=readable rootless={{.Host.Security.Rootless}} graph_driver={{.Store.GraphDriverName}}' 2>/dev/null; then :; else echo 'podman_info=unavailable'; fi
else echo 'podman_info=unavailable'; fi

oci_layout="${1:-${RML1_OCI_LAYOUT:-}}"
if [[ -n "$oci_layout" && -f "$oci_layout/oci-layout" && -f "$oci_layout/index.json" ]]; then
  index_digest=$(sha256sum "$oci_layout/index.json" | awk '{print "sha256:"$1}')
  printf 'local_oci_index_checksum=%s source=caller_supplied_untrusted_layout\n' "$index_digest"
  if have skopeo; then
    raw_manifest=$(mktemp)
    if timeout 15 skopeo inspect --raw "oci:${oci_layout}" >"$raw_manifest" 2>/dev/null; then
      manifest_digest=$(sha256sum "$raw_manifest" | awk '{print "sha256:"$1}')
      printf 'local_oci_manifest_bytes_sha256=%s source=caller_supplied_untrusted_layout\n' "$manifest_digest"
      echo 'local_oci_manifest_inspection=available'
    else
      echo 'local_oci_manifest_inspection=unavailable'
    fi
    rm -f "$raw_manifest"
  else echo 'local_oci_manifest_inspection=unavailable'; fi
else
  echo 'local_oci_index_checksum=unavailable (existing OCI layout absent; no pull/build attempted)'
  echo 'local_oci_manifest_inspection=unavailable'
fi
echo 'trusted_running_oci_image_digest_verified=false (no running OCI daemon/container verified)'

seccomp=$(awk '/^Seccomp:/{print $2}' /proc/self/status 2>/dev/null || true)
filters=$(awk '/^Seccomp_filters:/{print $2}' /proc/self/status 2>/dev/null || true)
printf 'seccomp_mode_observed=%s seccomp_filters_count_observed=%s\n' "${seccomp:-unknown}" "${filters:-unknown}"
# Mode=2 and a filter count do not prove the loaded filter bytes. This script
# intentionally does not perform privileged PTRACE_SECCOMP_GET_FILTER.
echo 'loaded_bpf_seccomp_filter_bytes_verified=false (not measured; mode/count insufficient)'

echo 'qualification=NOT_RUN (developer tooling observations only; no container was built, pulled, or run)'
exit "$status"
