# ContractNLI: compiled clause programs vs one question (2026-11-14)

1927 rows (stratified, 14 clause types). Programs compiled by Haiku from hypothesis text only. Balanced accuracy.

| verifier | overall | confidentiality_of_agreement | explicit_identification | inclusion_of_verbally_conveyed_information | limited_use | no_licensing | notice_on_compelled_disclosure | permissible_acquirement_of_similar_information | permissible_copy | permissible_development_of_similar_information | permissible_post-agreement_possession | return_of_confidential_information | sharing_with_employees | sharing_with_third-parties | survival_of_obligations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev: one question | 83 % | 65 % | 68 % | 93 % | 85 % | 67 % | 85 % | 88 % | 85 % | 98 % | 92 % | 63 % | 97 % | 71 % | 89 % |
| jev: compiled program | 90 % | 94 % | 78 % | 91 % | 87 % | 84 % | 97 % | 96 % | 88 % | 99 % | 89 % | 88 % | 98 % | 75 % | 87 % |
| luna: one question | 87 % | 68 % | 53 % | 94 % | 86 % | 79 % | 90 % | 93 % | 91 % | 98 % | 97 % | 66 % | 97 % | 77 % | 96 % |
| luna: compiled program | 93 % | 95 % | 68 % | 93 % | 90 % | 89 % | 99 % | 95 % | 86 % | 99 % | 96 % | 94 % | 98 % | 89 % | 95 % |
| jev + luna compiled (mean) | 93 % | 95 % | 68 % | 93 % | 90 % | 89 % | 99 % | 96 % | 86 % | 99 % | 94 % | 92 % | 98 % | 89 % | 94 % |

- jev compiled, abstaining in 0.3–0.7: answers 88 %, balanced accuracy on those 94 %

- luna compiled, abstaining in 0.3–0.7: answers 97 %, balanced accuracy on those 94 %
