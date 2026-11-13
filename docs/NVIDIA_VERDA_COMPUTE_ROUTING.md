# NVIDIA, Codex Cloud and Verda compute routing

Private developer handoff, 13 November 2026. These are source-bound observations, not grants to expose private data, change account permissions, activate production or incur unapproved charges.

## Default execution route

Use the existing Codex Cloud lanes for portable source work, builds and tests. This monorepo already records 34 Pro/Legacy lanes in `ops/cloud-provisioning-20261113.json` and per-company `ops/environments/*.json`. Read the current manifest, provider/account and exact source before dispatch; do not duplicate an existing CPU lane merely because Verda is now connected.

Keep NVIDIA Nemotron API access separate from Verda infrastructure. Verda supplies optional compute for workloads that actually need it, particularly authorized GPU/large-data jobs. A source/test pass does not qualify real NVIDIA inference. Existing GPU-training pauses remain in force; this setup did not resume another project's training.

| Route | Observation |
| --- | --- |
| Existing NVIDIA lane | Environment `6af6577d29dc8191afc1b3d0b2fe3cba`; [capacity task](https://chatgpt.com/codex/tasks/task_e_6af76bba2c408326b3543b26a73f248f), ready with no diff. Observed filesystem total 33,770,192,896 bytes, available 31,782,768,640 bytes. |
| Existing Verda developer lane | Environment `6af658b75f108191a8e1d9db406f7456`; [capacity task](https://chatgpt.com/codex/tasks/task_e_6af76bba0efc8326b95f1cbdd087250f), ready with no diff. Observed filesystem total 33,770,192,896 bytes, available 31,782,383,616 bytes. |
| Existing modern shared configuration | `chibi-marketplace-cloud` includes `SalesSquad/junction-pets`. Its read-only setup inspection measured 67,586,535,424-byte filesystem, 64,132,501,504 bytes available, 32 GiB memory cgroup limit and 4 CPU quota cores. This was a fresh running inspection executor, not proof that every existing executor currently has the same free space. No draft edit/save/publication occurred. |
| This root thread's later selected environment | Caller reported `ccarenv_b64_Y2NhcmVudl82YTlkZmU2YzZmNmM4MTkxYWIxNjYxMWYzZGMwMGFkMw` as unavailable. Do not conflate this selection with the working Legacy tasks or the separate modern inspection executor. |
| Verda infrastructure experiment | One task-owned CPU VM was created and then shut down in favor of the existing Codex Cloud CPU routes. See preserved resource state below. |

Both Legacy probes observed clean source HEAD `5852fa406a7ea38ed02f0f83ab9b904ad427bccc`; the repository commit/path was separately resolved through authenticated GitHub. Their local snapshots have no Git remote configured, so the runtime hostname is not independent provider-environment attestation. The provider task metadata labels the tasks `junction-nvidia` and `junction-verda`; requested IDs remain distinct from observed runtime identity.

CLI caveat: `codex cloud list --env ...` returned the same broad cross-environment task list with null environment IDs in this inspection. Do not infer lane attribution from that filtered list. Use the exact submitted task ID and its provider detail/result. Direct legacy task URLs redirected to the new ChatGPT home in the inspected browser; the supported Codex Cloud terminal detail view supplied the complete observations.

## Verda account, credits and access

The official [Junction Verda hacker pack](https://hackjunction.app/participate/45/hackerpacks/71) advertises €200 credits. The claim form was submitted, its emailed `JUNCTION-2026` coupon was redeemed after the owner added a payment method, and the CLI balance increased from USD 20 to USD 241.04. A later read returned USD 241.0023. No additional card payment or automatic top-up was submitted by this agent.

The owner reports unlimited hackathon access. **A provider entitlement for unlimited free usage has not been observed.** Keep that assertion pending a provider source; a high resource quota is not a billing exemption. The account quota page currently reports limits of 32 GPUs, 64 spot GPUs, 512 vCPUs, 10 serverless deployments, 29.2 TiB NVMe/block/shared storage, 30 storage items, 1 TiB object storage, 100 buckets and 100,000 objects. These are quota ceilings, not stock reservations, installed resources or spend authority.

Account: `mikael@ssquad.info`. Google is linked and explicitly reads Connected for that same identity. The MBP has Verda CLI 1.10.0; its default Cloud API credential is in the supported local store, mode 0600, provider expiry 13 December 2026. Do not copy credentials or private SSH keys into repositories, prompts, another executor or a plugin. Inference keys and Cloud API credentials are different.

## Preserved, offline Verda CPU experiment

- VM: `239f5760-48d7-462c-ad71-934f80957d35`, hostname `junction-cli-20261113`, FIN-01, CPU.4V.16G.
- Last verified provider status: **offline** following an explicit task-owned graceful shutdown.
- OS volume: `26c16893-9fc6-4d71-8f61-c9046d2cbe83`, 100 GiB, retained. No resource/data was irreversibly deleted.
- Quoted running estimate: USD 0.048/hour CPU + USD 0.0274/hour OS volume = USD 0.0754/hour. Stopping the VM does not prove retained storage is free. The CLI running-instance endpoint returned zero after shutdown; the account UI still displayed the old/allocated usage figure, so do not treat either as a complete storage bill.
- Installed tools: Ubuntu 24.04, Node 22.23.5, Codex CLI 0.167.0, Git 2.43.0, Python 3.12.3, tmux/build essentials.
- SSH as unprivileged `junction` was tested using the dedicated local key, pinned known_hosts and no agent forwarding.
- MBP access config: `~/.ssh/junction-verda-20261113.conf`; use through the already authorized RDC connection. The instance is offline; recheck owner intent before resuming it.
- Source-bound NVIDIA checks: **50/50 passed** on the VM at `090dc47b0b43bb12e51988361685cbf81065213c`. No inference/API call was executed.
- Codex was installed but remained unauthenticated. A supported device flow was started and ended without a grant when the experiment was shut down; no Mac OAuth/session database was transferred.
- Raw receipts and bootstrap/test logs: MBP `~/Developer/junction-verda-cli-20261113/`; persistent terminal `junction-verda-cli-20261113`. Source is preserved in the existing Git commit; receipt digests follow.

## Captured evidence

These original reported capacity observations distinguish requested route, actual runtime measurements and observed configuration. They are point-in-time free-space values, never a summed shared storage pool.

~~~json
{
  "codex-capacity-nvidia-result.json": {
    "work_id": "JUNCTION-CLOUD-CAPACITY-20261113-nvidia",
    "observed_at_utc": "2026-11-13T19:59:43.393628Z",
    "identity": {
      "requested_environment_id": "6af6577d29dc8191afc1b3d0b2fe3cba",
      "requested_identity_status": "routing hint; not independently attested",
      "observed_hostname": "e17bcb43456f",
      "observed_identity_status": "local hostname, kernel, and capacity observations only",
      "requested_matches_observed": null
    },
    "repository": {
      "configured_remote_url": null,
      "configured_remotes": [],
      "repository_url_status": "no Git remote is configured; URL cannot be observed from Git configuration",
      "repository_url_declared_by_root_AGENTS": "https://github.com/SalesSquad/junction-pets",
      "head": "5852fa406a7ea38ed02f0f83ab9b904ad427bccc",
      "branch": "work",
      "dirty": false,
      "dirty_baseline_porcelain_v1": []
    },
    "system": {
      "pwd": "/workspace/junction-pets",
      "hostname": "e17bcb43456f",
      "uname": "Linux e17bcb43456f 6.18.57 #1 SMP Tue Oct 20 21:56:04 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux",
      "cpu_logical_count": 3,
      "ram": {
        "total_bytes": 18883006464,
        "free_bytes": 17851916288,
        "available_bytes": 17858453504,
        "labels": {
          "total_bytes": "MemTotal",
          "free_bytes": "MemFree",
          "available_bytes": "MemAvailable"
        }
      }
    },
    "df_B1": {
      "root": {
        "path_queried": "/",
        "filesystem": "overlay",
        "fstype": "overlay",
        "total_bytes": 33770192896,
        "used_bytes": 252661760,
        "available_bytes": 31782768640,
        "used_percent": "1%",
        "mountpoint": "/"
      },
      "workspace": {
        "path_queried": "/workspace",
        "filesystem": "overlay",
        "fstype": "overlay",
        "total_bytes": 33770192896,
        "used_bytes": 252661760,
        "available_bytes": 31782768640,
        "used_percent": "1%",
        "mountpoint": "/"
      }
    },
    "python_os_statvfs_cwd": {
      "path": "/workspace/junction-pets",
      "block_size_bytes": 4096,
      "fragment_size_bytes": 4096,
      "total_blocks": 8244676,
      "free_blocks": 8182991,
      "available_blocks": 7759465,
      "total_bytes": 33770192896,
      "free_bytes": 33517531136,
      "available_bytes": 31782768640,
      "total_file_nodes": 2097152,
      "free_file_nodes": 2092502,
      "available_file_nodes": 2092502,
      "flags": 4096,
      "max_filename_length_bytes": 255
    },
    "scope_result": "bounded read-only observation completed; root and ops AGENTS instructions read; no edits, installs, tests, commits, PRs, provisioning, settings changes, training, or paid-provider calls"
  },
  "codex-capacity-verda-result.json": {
    "work_id": "JUNCTION-CLOUD-CAPACITY-20261113-verda",
    "observation_scope": "single_bounded_read_only_probe",
    "observed_at_utc": "2026-11-13T19:59:57.899475Z",
    "identity": {
      "requested_environment_id": "6af658b75f108191a8e1d9db406f7456",
      "requested_identity_status": "routing_hint_not_independently_attested",
      "observed_hostname": "dd7f0a533b28",
      "observed_identity_status": "hostname_observed_not_provider_environment_attestation"
    },
    "repository": {
      "actual_repository_url": null,
      "repository_url_status": "no_git_remote_configured",
      "configured_remote_urls": [],
      "head": "5852fa406a7ea38ed02f0f83ab9b904ad427bccc",
      "dirty_baseline": {
        "label": "clean",
        "porcelain_v1": []
      }
    },
    "pwd": "/workspace/junction-pets",
    "uname": "Linux dd7f0a533b28 6.18.57 #1 SMP Tue Oct 20 21:56:04 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux",
    "cpu_count_logical": 3,
    "ram": {
      "total_bytes": 18883006464,
      "free_bytes": 17852399616,
      "free_label": "MemFree from /proc/meminfo"
    },
    "df_B1": {
      "root": {
        "path_queried": "/",
        "filesystem": "overlay",
        "fstype": "overlay",
        "total_bytes": 33770192896,
        "used_bytes": 253046784,
        "available_bytes": 31782383616,
        "capacity_used_label": "1%",
        "mounted_on": "/"
      },
      "workspace": {
        "path_queried": "/workspace",
        "filesystem": "overlay",
        "fstype": "overlay",
        "total_bytes": 33770192896,
        "used_bytes": 253046784,
        "available_bytes": 31782383616,
        "capacity_used_label": "1%",
        "mounted_on": "/"
      }
    },
    "python_os_statvfs_cwd": {
      "path": "/workspace/junction-pets",
      "block_size_bytes": 4096,
      "fragment_size_bytes": 4096,
      "total_blocks": 8244676,
      "free_blocks": 8182897,
      "available_blocks_unprivileged": 7759371,
      "total_bytes": 33770192896,
      "free_bytes": 33517146112,
      "available_bytes_unprivileged": 31782383616,
      "total_file_nodes": 2097152,
      "free_file_nodes": 2092502,
      "available_file_nodes_unprivileged": 2092502,
      "mount_flags": 4096,
      "max_filename_length_bytes": 255
    },
    "instructions_read": [
      "AGENTS.md",
      "ops/AGENTS.md"
    ],
    "mutations": {
      "files_edited": false,
      "packages_installed": false,
      "tests_run": false,
      "commit_created": false,
      "pr_created": false,
      "resources_provisioned": false,
      "settings_changed": false
    }
  },
  "codex-modern-capacity-result.json": {
    "read_only": true,
    "configuration": {
      "source": "environment_status + read_environment_config_draft",
      "name": "chibi-marketplace-cloud",
      "environment_id": "ccarenv_b64_Y2NhcmVudl80MTA2NTQxN2JmNzA4MTkxOWQyMjRmNzM1NDY0MzI4Mg",
      "config_id": "d98470d573e1948808b18449c61e6c29032be75bb95fe3ea91a38e3614228cb5~cecfg_349b6563fbc881a0a188c55a32c0ff98",
      "source_version_id": "d98470d573e1948808b18449c61e6c29032be75bb95fe3ea91a38e3614228cb5~cecfgver_6af64e7674f081a0ba743c0309dc2efe",
      "draft_id": "d98470d573e1948808b18449c61e6c29032be75bb95fe3ea91a38e3614228cb5~cecfgdraft_5be01f65729c81a095c0986d6144f88d",
      "draft_revision": 1,
      "draft_base_matches_source_version": true,
      "published_state": "Version-backed runtime; explicit publication status not exposed",
      "draft_state": "Existing draft present",
      "runtime_state": "running",
      "observations_current": true,
      "configured_capacity": "Disk, RAM and CPU sizing not exposed by these configuration tools"
    },
    "executor_measurement": {
      "source": "statvfs(/workspace), /proc/meminfo, CPU affinity, cgroup limits",
      "disk_total_bytes": 67586535424,
      "disk_free_bytes": 67585249280,
      "disk_available_bytes": 64132501504,
      "ram_visible_total_bytes": 35743748096,
      "ram_visible_free_bytes": 35255779328,
      "ram_visible_available_bytes": 34985385984,
      "ram_cgroup_limit_bytes": 34359738368,
      "cpu_visible_logical": 5,
      "cpu_affinity_count": 5,
      "cpu_cgroup_quota_cores": 4,
      "capacity_note": "Measured filesystem free space differs from total capacity; cgroup limits constrain visible host resources."
    },
    "instance_freshness": {
      "source": "/proc/uptime",
      "uptime_seconds": 101.38,
      "new_ephemeral_instance": "Consistent with a freshly booted executor; ephemeral lifecycle and reuse history are not exposed."
    },
    "changes_made": false,
    "secret_values_printed": false
  },
  "cloud-test-receipt.json": {
    "instanceId": "239f5760-48d7-462c-ad71-934f80957d35",
    "sourceCommit": "090dc47b0b43bb12e51988361685cbf81065213c",
    "sourceArchiveSha256": "1fa4c046d5e7c0eb3e4255a6b07eb1f1f905bb9b62ab735325004c1911b4f041",
    "command": "cd /home/junction/workspaces/nvidia-smoke-090dc47 && node --test services/nemotron-vl/nemotron.test.mjs tests/pet-nvidia.test.mjs",
    "exit": 0,
    "testLogSha256": "a95290987969ca3a1a259a779e80fa89ec1459635e571461dc208ebd32a47cfe",
    "apiInferenceExecuted": false
  }
}
~~~
