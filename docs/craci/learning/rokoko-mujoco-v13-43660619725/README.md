# CRACI Rokoko MuJoCo V13 — original unsafe partial run, hard STOP

**This is safety-negative evidence from an INCOMPLETE/FAILED hosted experiment,
not a model evaluation, proof of general risk, or new independent physics
replay.** The original CRACI run stopped on its first real physics safety cost.
The SHA-only packet retains the negative result without committing private 18D
observations, seven-bit masks by option, full actions, or trajectory logs.

## Original immutable provenance

| Object | Exact original |
| --- | --- |
| Hosted [CRACI #43660619725](https://github.com/SalesSquad/junction-pets/actions/runs/43660619725) | FAILED; wrapper exit code **3** |
| Original artifact ID | `14139354188` |
| GitHub artifact outer ZIP SHA-256 | `cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0` |
| Source HEAD (V13 product) | `0751d78b93855bf70820b03b0a543e123d218baf` |
| Harness HEAD (PR #186 historical) | `dc6d745c5facb56eed85016830dfe8f19b25032f` |
| Original V12 source HEAD | `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f` |
| Original V12 public 48-world/144-trajectory SHA index | `24460b2ed49635b33db66233dd854f84593e6f65484cde229ee17ec483dd0245` |
| Original retained `partial_training.json` SHA | `8bbc9b7df5539c3d4cf10963c1ea098f7a488cd31c5e9d365f1df6fc8710e612` |
| Original retained `full_transitions.jsonl.gz` SHA | `6bb153cb699ebadd35ee32a3f940473341560855e512c4e174d0ab5990ba9e74` |
| Original retained `option_journal.jsonl.gz` SHA | `dfb479ea92cd97a57722fdb69719817011cb3ac192ed47aeccf6196734fc9d3d` |
| Recomputed SHA-only [unsafe-sha256.json](unsafe-sha256.json) | `5c3eae39e3a3bf6250c4713c42894034b1d27b64982b3e68c9c17e7f9d8c4d3a` |

The original ZIP is **not in Git**. Its unchanged private iCloud location was
verified on the Mac Mini, with SHA-256 equal to the original GitHub artifact:

`Junction/CRACI/rokoko-v13-43660619725-github-artifact.zip` (in iCloud Drive)

This hash verifies local file bytes, **not** cross-device iCloud sync or a signed
compute-provider attestation. Original billing is unknown.

## What the original source actually demonstrated

| Field | Original verified value |
| --- | ---: |
| Source status / scientific status | `INCOMPLETE_STOP` / `STOP_UNSAFE` |
| Preregistered branch maximum / actually journaled branches | 720 / **23** |
| Original journaled physics options / cross-checked hashes | **394 / 394** |
| Original full branch rows vs option journal group mapping | **23 / 23** |
| Distinct original **seen TRAIN** worlds | **2** (`518003`, `518006`) |
| Recorded cost-free option events before the hard stop | 393 |
| Recorded cost=1 and done=true terminal unsafe events | **1** |
| Model promotion / efficacy qualification | **not authorized / false** |

The **one and only** recorded unsafe event is world `518006`, branch **22**
(`v13-seen-train-518006-16`), zero-based option **37**, option action **2**,
all seven mask entries **1** (so it was **legal under the public shield**),
`cost=1`, `done=true`. Canonical original transition SHA-256:

`4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba`

The 23 branch histories and 394 option hashes are committed in
[`unsafe-sha256.json`](unsafe-sha256.json) without private observation vectors
or trajectories. The source verifier reconstructs the **full lossless
originals** from each nested authenticated ZIP part, validates wrapper,
retention, receipt, source pins and V12 world-hash matches, recomputes the
seven-action mask from 18D public state, verifies all 394 per-event canonical
SHA hashes and exact 23:23 branch-journal mapping, then independently counts
the **sole** unsafe terminal. Only these two original world seeds were reached
before the stop; the original V12 index's 48 worlds are **not** 48 new V13
physics samples.

### Scientific interpretation and STOP

- **STOP** further V13 replay/training dispatch and model promotion pending
  independent safety triage. The exact physical hazard *cause/type* is
  **UNKNOWN** from this evidence; legal mask status does not prove an acceptable
  action or a particular collision cause.
- **1/394 is not an empirical population risk rate**: options are serially
  dependent within 23 branched trajectories from only **two** world states.
  Likewise, 393 cost-free options are not 393 independent safe trials.
- The capture wrapper says `complete=true` because the **negative artifact was
  fully retained**. The scientific run says `INCOMPLETE_STOP`, 23/720 branches,
  and no full world/program efficacy qualification. No prospective goal250
  improvement, generalization or robust safety can be claimed.
- The original logs are source-reported physics with source/harness clean-HEAD
  verification. There was **no independent new MuJoCo replay** of these 394
  options after the failed run, no signed provider attestation, no verified
  bill, no sealed dev/cal/test/OOD opening and **no automatic retry**.
- These are already-opened TRAIN observations. They can guide a separate
  evidence-bound failure investigation; they must not be presented as a fresh
  independent confirmation or used to justify loosening the shield.

## Reproduce the offline safety-negative verification

This is a source-only Python/NumPy verifier; it does not dispatch CRACI, fetch
new data, need GPU/MuJoCo or access secrets. Keep original ZIP outside Git.

```bash
python3 -m unittest discover -s scripts/craci \
  -p 'test_v13_unsafe_evidence_*.py' -q
python3 docs/craci/learning/rokoko-mujoco-v13-43660619725/verify_original.py \
  '/private/original/rokoko-v13-43660619725-github-artifact.zip' \
  --verify-manifest \
  docs/craci/learning/rokoko-mujoco-v13-43660619725/unsafe-sha256.json
```

The verifier exits **0** only for the raw-source-bound `safety-negative`
packet. With `--claim efficacy` it deliberately returns nonzero
`INCOMPLETE_STOP_CANNOT_QUALIFY_EFFICACY`. The optional `--write-manifest`
uses exclusive creation of a new file, never overwrites the original ZIP.
An altered original ZIP, nested source hash, V12 index, mask, journal digest,
branch mapping, terminal unsafe flag, success claim or SHA-only manifest
fails closed. The focused unit tests use synthetic data only.
