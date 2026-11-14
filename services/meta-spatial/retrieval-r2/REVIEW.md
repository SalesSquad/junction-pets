# R2 review and execution notes

The coordinator integrated source ownership and runtime execution; a separate read-only reviewer inspected the numerical and provenance boundaries. These are local source reviews, not signed hosted qualification or a universal model assessment.

## Before the real model run

A P2 defect in the earlier draft selected only the first query from each product family during policy calibration and evaluation. Stable top-1 tie-breaking could then hide wrong accepted variants. The reviewer supplied a 320-family × 2-variant counterexample. The owner corrected the implementation before executing the sealed campaign:

- Present errors are evaluated on every query, with a separate family-any-error count.
- An absent-family error is any accepted query among every variant of the removed family.
- The 1% risk target applies to absent-family events; conditional accepted-error certification remains false.

Reviewed final numerical source SHA256:

| File | SHA256 |
|---|---|
| `retrieval.py` | `ef0103867c05d920a587dae858e6d25fc62f748ae294851bff48c3d19417e813` |
| `train_retrieval.py` | `abf1f4158d2fa668e8b931594d760bfe59ea8dd08c27e7f924a4533ae5c4d286` |
| `test_retrieval.py` | `929b578867e3857600221158679abbe7897f633b75717cd44892a183818ae0e2` |
| `dino_baseline.py` | `e55079f2bf3da19e3cea6e3746e29eccae48e5934941157d816f8eba793c434d` |

The reviewer closed the identified defect on these bytes. No open P1/P2 source finding remained in the reviewed core paths. The coordinator's real execution, source snapshot and output hashes are retained separately; the source reviewer did not claim to execute the models.

## Arbitration review

| File | SHA256 |
|---|---|
| `arbitration.py` | `1ce0dbc10c740d94d397c1c7528765a2ed14b6a04b38b19af164570fed0ea8fc` |
| `test_arbitration.py` | `570a913ac030f4a2dfda3364ebed8070bc7a3cbec5bbf8f17548338492237d28` |

No concrete P1/P2 issue was found in the reviewed gate, calibration, family aggregation or cache-binding paths. The reviewer verified that absent-family masking precedes reranking and agreement; thresholds are fixed on calibration before heldout matrices; every query variant contributes; the coverage-only and 5% tracks do not replace the original gate; and a recommendation grants no camera or identity authority.

The worker designed this fixed study without seeing the main test metrics. The coordinator had already seen them. This is explicitly exploratory reuse of the holdout, not a new independent confirmation.

## Runtime verification

Core actual execution: `6103e6d09141090348ff213d850192b895c6cc8a`.
Arbitration and numerical tests: `9b799ed80acaae0a099e9f84c247e9aeb38deaf8`.

Twelve targeted tests passed in the actual cloud Python environment. The retained test log SHA256 is `a12ccbfb09687cc7f818303dff7292643c6e84f5be3432b5fd0f8a5e6c2269ea`. Tests exercise family isolation, image leakage, variant ties, abstention bounds, residual identity, nonfinite inputs, rank fusion and decision authority. Runtime inference, model-weight checksums and trained checkpoint updates provide additional evidence beyond synthetic unit tests.

Initial environment creation failed because the Python venv package was missing. Installing the OS venv support resolved that setup problem; the original logs remain. A report-submission wrapper also hit a local Python quoting error before any command receipt was accepted; its corrected submission did not duplicate the experiment. Neither incident is presented as a scientific model failure.

The first artifact-verifier run also found a verifier schema assumption error: DINO preserves all 6,000 product IDs, while the frozen Nemotron track deliberately encodes only the 1,960 calibration/test/OOD rows. The verifier was corrected to require that exact source-defined subset in its exact dataset order. Historical model reports were unchanged. The failed verification receipt is retained separately; no equality check was removed or replaced by an unchecked allowance.

## Preserved conclusion

The trained adapter's research gate is **FAIL**. The fixed fusion also underperforms the strong frozen visual baseline. Nemotron improves metadata candidate recall in this catalog task, with substantial remaining abstention and dataset limitations. No gate was relaxed, no historical report rewritten, and no production model activated to make the campaign appear successful.
