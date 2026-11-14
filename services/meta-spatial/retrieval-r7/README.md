# Meta Lens R7: nonlinear ranking control

R6's three real six-feature linear refits reproduced frozen R4: 466/727
development queries correct at rank one. R7 tests a different model class
while the pinned NVIDIA extraction remains blocked by GPU availability.
It uses the same six real features and fixed top100 candidates. It adds no
OCR/RADIO observations and makes no accepted-coverage claim.

## Predeclared experiment

`protocol.json` freezes four histogram gradient-boosted classifiers before
training: 15 or 31 leaf nodes, crossed with L2 regularization 1 or 10. Each
fits 150 boosting iterations at learning rate 0.05 with minimum leaf size
100 and 127 bins. Early stopping is disabled; development labels never
control stopping or an adaptive search. The estimator is a pointwise
classifier; its raw decision score is used only to rank each query's candidates.

The immutable train/dev preparation has 3313/727 queries and 404000
candidate rows. The 3280 training queries containing a positive supply
328000 fit rows. Weights balance training families, queries within each
family, and positives against the 99 negatives within each query. All 33
training and eight development queries without a retained positive remain
in evaluation denominators. No correct candidate is inserted.

Selection uses development exact recall@1, then MRR, fewer leaf nodes and
stronger regularization. Frozen R4 remains selected unless recall@1 or its
MRR tie-break improves strictly. Four configurations are fixed in advance;
no additional fit is authorized by an observed development result.

## Runtime and input admission

The existing authorized CPU runtime has Python 3.15.2, NumPy 2.5.4 and
scikit-learn 1.9.1. Execution uses at most four threads and a ten-minute wall
budget, installs no packages, makes no provider inference call and allocates
no GPU. This is a bounded training experiment, not an Apple SDK build.

The preparation-manifest hash, candidate CSV, truth and frozen numeric R4
model are pinned in the protocol. The runner verifies exact input contracts,
train/dev separation, source bytes and the clean execution commit. It must
reproduce the frozen 466/727 rank-one result and 719/727 candidate recall.
Only the six allowed numeric features enter fitting; product/family identities
serve admission, training balance and evaluation, never model inputs.

```sh
python train_nonlinear.py \
  --prepared /work/prepared \
  --baseline-model /work/r4/model.json \
  --protocol protocol.json \
  --output /work/r7-new \
  --source-commit FULL_CLEAN_SOURCE_COMMIT
```

## Results and limits

All four actual fits completed on source commit
`58663aeb5bbdd879e18b1f544aed8f1f97bef907`, within a 30.52-second outer run.
Each trained 150 boosting iterations and reduced weighted training loss.
No candidate improved frozen R4, so R4 remains selected.

| Model | Dev exact rank1 | MRR |
|---|---:|---:|
| Frozen R4 | 466/727 (64.10%) | 0.743285 |
| 15 leaves, L2=1 | 449/727 (61.76%) | 0.731708 |
| 15 leaves, L2=10 | 455/727 (62.59%) | 0.735589 |
| 31 leaves, L2=1 | 449/727 (61.76%) | 0.731071 |
| 31 leaves, L2=10 | 452/727 (62.17%) | 0.733032 |

`results/report.json` preserves all four actual candidates, paired changes,
runtime versions, thread counts and source/input hashes. `results/model-summary.json`
separates the best trained HGB model from the selected frozen R4 model.
`results/verification.json` binds the actual 404000 prediction rows, 20200
query-metric rows and exact serialization/prediction parity. Original report
bytes are preserved. The fixed four-candidate search was not expanded after
seeing development results.

The independent source review and small admission/ranking checks preceded
execution. No unchanged R6 suite or additional model fit was repeated merely
to publish these results. This experiment shows that these four nonlinear
configurations did not improve the present six-feature ranking task; it does
not prove that no other model can improve it.

Raw candidate rows, truth, query-level predictions and serialized joblib
models remain on the authorized execution host. A joblib artifact must only
be loaded when its trusted source and recorded hash have been verified.

Development selection reuses historical data. A gain here would be research
evidence for the ranker, not qualification of >93% accepted coverage. The
experiment never calibrates an acceptance threshold, consumes calibration
or test rows, changes frozen image encoders, or authorizes physical identity
or actions. Stronger nonlinear fitting cannot create visual evidence absent
from the six existing features.

Related implementation and control: [R6 / PR207](https://github.com/SalesSquad/junction-pets/pull/207).
Estimator semantics: [official HistGradientBoostingClassifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
