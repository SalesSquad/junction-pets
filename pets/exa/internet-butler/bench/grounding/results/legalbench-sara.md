# Grounding benchmark: legalbench-sara.jsonl (2026-11-14)

272 claims from 1 dataset(s); label balance 136 supported / 136 not. Metric: balanced accuracy (mean of the two class recalls).

| verifier | overall | sara_entailment |
|---|---|---|
| code | 51 % | 51 % |
| jev:single | 77 % | 77 % |
| jev:table | 62 % | 62 % |
| jev:table+code | 52 % | 52 % |
| luna:single | 65 % | 65 % |
| luna:table | 60 % | 60 % |
| luna:table+code | 53 % | 53 % |
| jev+luna:single (mean p) | 65 % | 65 % |

Abstaining in the 0.3–0.7 band (single question) or on any table row in it:

- jev:single: answers 64 % of claims, balanced accuracy on those 78 % (plain accuracy 83 %)
- jev:table: answers 66 % of claims, balanced accuracy on those 53 % (plain accuracy 68 %)
- luna:single: answers 89 % of claims, balanced accuracy on those 64 % (plain accuracy 65 %)
- luna:table: answers 85 % of claims, balanced accuracy on those 57 % (plain accuracy 61 %)

Cost and latency:

- jev: 173420 input tokens ≈ $0.0073 for 272 claims (6 questions each); p50 182 ms, p95 299 ms
- luna: 277294 input tokens ≈ $0.0277 for 272 claims (6 questions each); p50 364 ms, p95 749 ms

Cassette: 544 calls (0 replayed, 544 live).
