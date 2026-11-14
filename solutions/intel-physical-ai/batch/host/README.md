# Intel M330 M6 — durable LOCAL software admission host

**Scope:** `solutions/intel-physical-ai/batch/host/**` exclusively; stacked on
[PR #172](https://github.com/SalesSquad/junction-pets/pull/172), whose source HEAD at
admission was `2dc36794fec597afaf78eee792746c790b399a89`.
Authenticated main was `16947f0ccd33d6e3895f08619b7ba425bf453a59`.
`junction.intel` / `junction.ignite-next` → `partnerEvidenceKey=ignite-next-and-intel`,
`ownedBriefRefs=[M330]`. The official latest 14 Nov Intel clarification still
contains conflicting GitHub/PDF judging weights; neither has been reconciled.

## What works now

M4 provides **synthetic batch-scoped STOP**, M5 provides the pure cross-batch
epoch/revision state machine. **M6 is the previously missing durable, single-host
filesystem transport.** The owner process opens a local directory (mode 0700)
and stores an append-only, fsynced JSONL *admitted* journal; each committed
record contains the complete independently replayable M5 snapshot. A separate
bounded `denied.jsonl` contains only reason, event ID, revision and prior root,
not camera imagery or untrusted raw input. Access control is **not** derived
from this disk journal.

The host serializes all mutations under an exclusive OS directory lock and
verifies the full journal before each operation. Each caller supplies the last
observed `expectedRoot`; M5 additionally requires the correct revision/epoch.
It acknowledges an admitted event only **after** append and fsync. If a caller
loses the acknowledgement, an identical request ID/payload returns the
original `CACHED` receipt after restart. Conflicting IDs or stale roots are
denied. If a journal ends in a torn line or any record cannot be replayed, the
host fails closed, **without deleting or auto-repairing evidence**. An abandoned
lock is never auto-stolen; a trusted administrator must inspect the associated
process and disk evidence before recovery.

The upstream M5 global-latch semantics are preserved: a fresh batch is denied
after an emergency STOP, dropped grip, missing/disagreeing camera, stale
synthetic capture or low confidence. Merely creating another host object or
restarting a Node process cannot erase the latch. Local per-item STOP remains
local. Rearm remains a two-step proposal + **host-injected** approval, bound to
M5's exact epoch/revision/root, never a client-supplied `approved=true`.

## How to use (local fixture only)

Node.js 22+ and no dependencies:

```sh
node --test solutions/intel-physical-ai/batch/host/host.test.mjs
node solutions/intel-physical-ai/batch/host/demo.mjs
node solutions/intel-physical-ai/batch/host/preflight.mjs
```

The `localHost(dir,{authorize})` interface is **not** a network service,
plugin or production endpoint. A test-only in-process `authorize` callback can
be faked by a caller running arbitrary code in the same process; it is
appropriate solely for the synthetic offline demo and tests. A real host must
keep authorization code and any provider credentials strictly on the trusted
server, verify operator/device/rearm authority with official means, and reject
caller-supplied approval material. No real keys or authenticated operator
paths are implemented here.

## Important limitations

- This code has **no robot connection or motor command**. There is no actual
  physical emergency-stop circuit, safety PLC, robot braking, camera,
  LeRobot leader/follower control, real estate/person data or model inference.
- Local `mkdir` locking and fsync provide practical **single-machine**
  serialization and acknowledged filesystem durability. They are not a
  distributed lock, consensus transaction or power-loss proof across NFS
  mounts/cloud replicas. Multi-host deployments are unsupported.
- The full journal is replayed on reads (bounded at 64 admissions and 32 MiB);
  exhausted caps and stale locks **fail closed**. A crash that leaves an
  incomplete append blocks future admission until reviewed. Never auto-truncate
  or silently replace it.
- Hashes are **UNSIGNED**. A privileged host attacker can rewrite/truncate
  entire files or roll back storage; detecting malicious rollback requires an
  independent monotonic seal outside this prototype. No such seal is claimed.
- Authorizer decisions are provided by a trusted host callback. This software
  does not issue credentials, authenticate operators, prove physical item IDs,
  or fulfill external compliance certification.
- Timestamps, synthetic anomaly scores and uncertainty are not calibrated
  real-world sensor probabilities. The previous 18-case result (144 simulated
  extra post-latch outputs vs 0 with M5) is a fixed fixture comparison, not a
  hardware success rate or inference benchmark.
- File system is local, disposable and private; no new daemon, cloud provider,
  GPU lease, CRACI run, production deployment or paid inference is started.

## Physical station handoff, deliberately unqualified

Current authorized Mac Mini inspection on 14 Nov found no installed
`openvino`, `anomalib` or `lerobot` Python modules and no identified SO-101
or RealSense USB hardware. These are observations of **that Mac only**, not an
inventory of an event station.

For a sponsor-authorized station, the independent equipment owner must first:

1. Inspect and register SO-101 follower/leader hardware and disconnect motion
   power before testing, then verify calibration and a physical E-stop.
   The official [LeRobot SO-101 guide](https://huggingface.co/docs/lerobot/so101)
   explains assembly, USB-port discovery and calibration; reading it does not
   establish access.
2. Freeze consented real top+inspection camera identifiers and timestamps,
   safety boundaries, fault-injection plan and a separately controlled
   physical rearm proof. No cloud-generated motion commands.
3. Pin actual licensed Anomalib + VLA model artifacts and held-out training/test
   partitions. Verify source hashes, independent defects and confidence
   calibration; synthetic fixture scores do not qualify.
4. Install the correct official Intel OpenVINO stack **on its authorized Intel
   hardware**. Record actual supported devices and identical workload
   correctness before benchmarking CPU/GPU/NPU. The
   [OpenVINO 2026 benchmark tool](https://docs.openvino.ai/2026/get-started/learn-openvino/openvino-samples/benchmark-tool.html)
   uses device-specific flags; do not claim Intel NPU execution from a Mac.
5. Execute supervised safe stop/restart/camera-lost cases behind the real
   physical interlock, measure correct-bowl rate, abstention, unsafe placement,
   latency, energy and heat separately from software-only receipts.
6. Reconcile the official Intel rubric with sponsor personnel before claiming
   competition acceptance or an external submission.

These are **external acceptance dependencies**, not completed integrations.
Portfolio PR Recovery exclusively owns integration of the PR stack
#169 → #172 → this host milestone; no merge/production release here.
