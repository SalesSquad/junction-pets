# Grounding benchmark: legalbench-contractnli.jsonl (2026-11-14)

1927 claims from 14 dataset(s); label balance 845 supported / 1082 not. Metric: balanced accuracy (mean of the two class recalls).

| verifier | overall | cnli_confidentiality_of_agreement | cnli_explicit_identification | cnli_inclusion_of_verbally_conveyed_information | cnli_limited_use | cnli_no_licensing | cnli_notice_on_compelled_disclosure | cnli_permissible_acquirement_of_similar_information | cnli_permissible_copy | cnli_permissible_development_of_similar_information | cnli_permissible_post-agreement_possession | cnli_return_of_confidential_information | cnli_sharing_with_employees | cnli_sharing_with_third-parties | cnli_survival_of_obligations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| code | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % | 50 % |
| jev:single | 83 % | 65 % | 68 % | 93 % | 85 % | 67 % | 85 % | 88 % | 85 % | 98 % | 92 % | 63 % | 97 % | 71 % | 89 % |
| jev:table | 72 % | 51 % | 53 % | 94 % | 75 % | 61 % | 70 % | 57 % | 86 % | 85 % | 80 % | 56 % | 94 % | 55 % | 81 % |
| jev:table+code | 72 % | 51 % | 53 % | 94 % | 75 % | 61 % | 70 % | 57 % | 86 % | 85 % | 80 % | 56 % | 94 % | 55 % | 81 % |
| luna:single | 87 % | 68 % | 53 % | 94 % | 86 % | 79 % | 90 % | 93 % | 91 % | 98 % | 97 % | 66 % | 97 % | 77 % | 96 % |
| luna:table | 80 % | 59 % | 53 % | 94 % | 74 % | 71 % | 75 % | 72 % | 82 % | 98 % | 98 % | 59 % | 97 % | 73 % | 92 % |
| luna:table+code | 80 % | 59 % | 53 % | 94 % | 74 % | 71 % | 75 % | 72 % | 82 % | 98 % | 98 % | 59 % | 97 % | 73 % | 92 % |
| jev+luna:single (mean p) | 87 % | 70 % | 53 % | 94 % | 86 % | 74 % | 89 % | 93 % | 90 % | 98 % | 98 % | 64 % | 98 % | 76 % | 95 % |

Abstaining in the 0.3–0.7 band (single question) or on any table row in it:

- jev:single: answers 80 % of claims, balanced accuracy on those 88 % (plain accuracy 91 %)
- jev:table: answers 78 % of claims, balanced accuracy on those 72 % (plain accuracy 83 %)
- luna:single: answers 93 % of claims, balanced accuracy on those 89 % (plain accuracy 90 %)
- luna:table: answers 92 % of claims, balanced accuracy on those 82 % (plain accuracy 85 %)

Cost and latency:

- jev: 1196762 input tokens ≈ $0.0503 for 1927 claims (6 questions each); p50 172 ms, p95 234 ms
- luna: 1952426 input tokens ≈ $0.1952 for 1927 claims (6 questions each); p50 311 ms, p95 642 ms

Cassette: 3854 calls (1116 replayed, 2738 live).
