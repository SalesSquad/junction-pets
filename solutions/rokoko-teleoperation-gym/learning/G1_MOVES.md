# G1 Moves — Rokoko motion-research handoff

**Logical lane owner:** `junction-dev-rokoko`. **Executor for the recorded
experiment:** CRACI. The two refer to different responsibilities; CRACI also
has its own independent [challenge lane](../../../docs/CRACI.md#independent-craci-challenge-lane).

## Existing evidence

- [G1 Moves](https://huggingface.co/datasets/exptech/g1-moves/tree/895d064b2385725e6aabf540461c219afc3e0916)
  is public data declared CC BY 4.0. The frozen selection uses 30 processed,
  retargeted G1 motion clips (15 dance and 15 karate); the preview is a
  rendered clip, not camera footage or a Rokoko capture. Attribute the source
  and comply with its license when reusing the data.
- [CRACI run 43672442214](https://github.com/SalesSquad/junction-pets/actions/runs/43672442214)
  completed the 15 G1 cells, five group-disjoint folds for each of three
  models. Its [complete results and audit](../../../docs/craci/learning/hf-open3d-20261115/RESULTS.md)
  remain the historical source of truth. The best displayed G1 model was Ridge:
  mean held-out-clip RMSE `0.09022 rad` versus constant velocity `0.11173 rad`,
  better on `27/30` clips. Model choice used those same folds.
- The target is a 0.1-second change in 29 joint angles. Splits hold out clips,
  not necessarily performers. This is offline forecasting on a retargeted
  dataset, not proof of live teleoperation, a Rokoko device stream, simulator
  control, robot safety or a deployable policy. No recorded model was promoted.

## Next Rokoko continuation

Review whether the G1 skeleton, coordinates, joint names, timing and license
fit the Rokoko retargeting task before proposing any integration. Preserve
the separately proposed invented partial-skeleton/root-motion mapping case.
A real Rokoko stream, explicit mapping and calibration, and separate evaluation
would be needed before claiming device or simulator integration. This is a
proposed continuation; no new worker or paid training job has been started.
