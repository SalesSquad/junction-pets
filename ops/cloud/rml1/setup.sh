#!/usr/bin/env bash
set -Eeuo pipefail

# Bounded, noninteractive developer bootstrap for the RML1 portable lane.
readonly MAX_SECONDS="${RML1_SETUP_TIMEOUT_SECONDS:-1200}"
readonly MAX_INSTALL_KIB="${RML1_SETUP_MAX_INSTALL_KIB:-1572864}"
readonly MIN_FREE_KIB="${RML1_SETUP_MIN_FREE_KIB:-2097152}"
readonly REQUIRED=(build-essential pkg-config clang llvm libseccomp-dev libcap2-bin python3-venv python3-pip jq git ca-certificates)
readonly OPTIONAL=(skopeo umoci podman buildah uidmap fuse-overlayfs slirp4netns)

fail() { printf 'RML1_SETUP_ERROR type=%s detail=%q\n' "$1" "${2:-unspecified}" >&2; exit "${3:-1}"; }
have() { command -v "$1" >/dev/null 2>&1; }
version() { if have "$1"; then printf '%-12s %s\n' "$1" "$(timeout 5 "$1" --version 2>&1 | head -n 1 || printf unavailable)"; else printf '%-12s absent\n' "$1"; fi; }

if [[ "${1:-}" == "--help" ]]; then
  echo 'Usage: setup.sh  # probe and install bounded apt packages for portable RML1 development'
  exit 0
fi
[[ $# -eq 0 ]] || fail invalid_argument "$*" 64
have timeout || fail missing_prerequisite timeout
have apt-get || fail unsupported_os apt-get-not-found
have apt-cache || fail unsupported_os apt-cache-not-found

echo '== RML1 portable setup: host probe =='
if [[ -r /etc/os-release ]]; then sed -n 's/^\(ID\|VERSION_ID\|PRETTY_NAME\)=/os.\1=/p' /etc/os-release; else echo 'os.release=unavailable'; fi
printf 'identity uid=%s gid=%s user=%s root=%s sudo=%s\n' "$(id -u)" "$(id -g)" "$(id -un)" "$([[ $(id -u) == 0 ]] && echo yes || echo no)" "$(have sudo && echo yes || echo no)"
printf 'resources cpu=%s memory_kib=%s disk_free_kib=%s\n' "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo unknown)" "$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo unknown)" "$(df -Pk / | awk 'NR==2{print $4}')"
for tool in node npm python3 cargo rustup clang gcc git jq; do version "$tool"; done
printf 'userns max_user_namespaces=%s unprivileged_clone=%s\n' "$(cat /proc/sys/user/max_user_namespaces 2>/dev/null || echo unavailable)" "$(cat /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || echo unavailable)"
printf 'docker socket=%s cli=%s\n' "$([[ -S /var/run/docker.sock ]] && echo present || echo absent)" "$(have docker && echo present || echo absent)"

runner=()
if [[ $(id -u) -ne 0 ]]; then
  have sudo || fail privilege_unavailable 'apt requires root or existing sudo'
  timeout 5 sudo -n true >/dev/null 2>&1 || fail privilege_unavailable 'passwordless existing sudo unavailable'
  runner=(sudo -n)
fi

free_kib=$(df -Pk / | awk 'NR==2{print $4}')
(( free_kib >= MIN_FREE_KIB )) || fail disk_pressure "free_kib=${free_kib},minimum_kib=${MIN_FREE_KIB}"

echo '== apt mirror/network refresh =='
apt_log=$(mktemp); trap 'rm -f "$apt_log"' EXIT
if ! timeout "$MAX_SECONDS" "${runner[@]}" env DEBIAN_FRONTEND=noninteractive apt-get \
  -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update >"$apt_log" 2>&1; then
  tail -n 30 "$apt_log" >&2
  fail apt_network_or_mirror_failure 'apt-get update failed or timed out' 70
fi

packages=("${REQUIRED[@]}")
optional_selected=()
for package in "${OPTIONAL[@]}"; do
  candidate=$(apt-cache policy "$package" 2>/dev/null | awk '/Candidate:/{candidate=$2} END{print candidate}')
  if [[ -n "$candidate" && "$candidate" != '(none)' ]]; then packages+=("$package"); optional_selected+=("$package"); fi
done
printf 'apt.plan required=%q optional_available=%q\n' "${REQUIRED[*]}" "${optional_selected[*]:-none}"

sim=$(mktemp); trap 'rm -f "$apt_log" "$sim"' EXIT
if ! "${runner[@]}" apt-get -s --no-install-recommends install "${packages[@]}" >"$sim" 2>&1; then
  tail -n 40 "$sim" >&2
  fail apt_plan_failure 'dependency resolution failed' 71
fi
new_count=$(awk '/^Inst /{n++} END{print n+0}' "$sim")
# apt-get -s does not consistently print a disk summary. Sum the candidate
# Installed-Size fields for every planned package instead (a conservative
# bound because replacements are not subtracted).
install_kib=0
while read -r planned; do
  [[ -n "$planned" ]] || continue
  size=$(apt-cache show --no-all-versions "$planned" 2>/dev/null | awk '/^Installed-Size:/{size=$2} END{print size}')
  [[ "$size" =~ ^[0-9]+$ ]] || fail footprint_estimate_unavailable "$planned" 72
  install_kib=$((install_kib + size))
done < <(awk '/^Inst /{print $2}' "$sim")
printf 'apt.plan new_package_count=%s estimated_extra_kib=%s max_extra_kib=%s\n' "$new_count" "$install_kib" "$MAX_INSTALL_KIB"
if (( install_kib > MAX_INSTALL_KIB )); then
  echo 'apt.plan optional packages skipped because the complete plan exceeds the footprint bound'
  packages=("${REQUIRED[@]}")
  "${runner[@]}" apt-get -s --no-install-recommends install "${packages[@]}" >"$sim" 2>&1 || fail apt_plan_failure required-packages
  new_count=$(awk '/^Inst /{n++} END{print n+0}' "$sim")
  install_kib=0
  while read -r planned; do
    [[ -n "$planned" ]] || continue
    size=$(apt-cache show --no-all-versions "$planned" 2>/dev/null | awk '/^Installed-Size:/{size=$2} END{print size}')
    [[ "$size" =~ ^[0-9]+$ ]] || fail footprint_estimate_unavailable "$planned" 72
    install_kib=$((install_kib + size))
  done < <(awk '/^Inst /{print $2}' "$sim")
  (( install_kib <= MAX_INSTALL_KIB )) || fail footprint_limit "required_estimated_kib=${install_kib},max_kib=${MAX_INSTALL_KIB}" 72
fi

echo '== bounded apt install =='
if ! timeout "$MAX_SECONDS" "${runner[@]}" env DEBIAN_FRONTEND=noninteractive apt-get \
  -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 \
  install -y --no-install-recommends "${packages[@]}" >"$apt_log" 2>&1; then
  tail -n 40 "$apt_log" >&2
  fail apt_install_failure 'apt-get install failed or timed out' 73
fi

rust_status=not-installed
if have rustup; then
  if [[ "${RML1_INSTALL_RUST_1_98_1:-0}" == 1 ]]; then
    if timeout "$MAX_SECONDS" rustup toolchain install 1.98.1 --profile minimal; then rust_status=installed-1.98.1; else fail rustup_network_or_toolchain_failure 1.98.1 74; fi
  else rust_status='existing-rustup-preserved (set RML1_INSTALL_RUST_1_98_1=1 to opt in)'; fi
fi
printf 'rust.status=%s\n' "$rust_status"
printf 'RML1_SETUP_OK installed_plan_count=%s disk_free_kib=%s\n' "$new_count" "$(df -Pk / | awk 'NR==2{print $4}')"
