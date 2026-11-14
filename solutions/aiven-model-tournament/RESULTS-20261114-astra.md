# Astra challenge — typed Aiven companion vs AstraZeneca-authored cases — 14 November 2026

Cases are written by the AstraZeneca companion ("Astra", `junction.astrazeneca` guidance, sonnet author) from its Equity Navigator project, not by the Aiven guidance author. The Aiven companion answers in typed form (`pets/aiven/schemas/response.v1.json`, CLI structured output). Code checks:
- schema validity, via the decision bridge
- no execution
- a proposal when the case expects one
- no echoed secret

An **opus** judge scores the rubric. A failed deterministic check halves the score and blocks a pass. 2 repeats. Unqualified developer measurement (Claude CLI, not the Aiven AI gateway, not a Chibi host).

| Round | Guidance | Case set | haiku pass | sonnet pass | haiku schema-valid | sonnet schema-valid |
|---|---|---|---|---|---|---|
| 1 | `c1b7dd3` | dev (10) | 30 % | 30 % | 18/20 | 16/20 |
| 2 | `35141b6` | dev (10) | 50 % | 55 % | 20/20 | 18/20 |
| 2 | `35141b6` | held-out (10, unread when the guidance changed) | 35 % | 50 % | 20/20 | 20/20 |

## Round 1 failures and fixes (commit `35141b6`)

| Failure | Fix |
|---|---|
| Proposals lacked owner and rollback | `owner_role` and `rollback` are now required |
| Changes were offered, not proposed | Workflow 9: propose now |
| A us-east replica was proposed for Finnish health data | Workflow 10: residency |
| Credential rotation rated medium | Risk guidance in the schema |
| Junction platform URL cited as a fact source | Official Aiven sources only |
| Personal data to the AI gateway without legal basis or provider region | Workflow 10 |

## Round 2 held-out failures, now fixed in workflow 11

Analytics hygiene:
- mismatched periods
- small counts without a suppression threshold
- headline rankings the data cannot support
- missing metric owner
- demo presented as validation
- prices "noted unverified" instead of sent to current pricing

Some rubric items are AstraZeneca-domain specific (for example clinical-validation disclaimers). They are kept because they reflect what that real user needs.

Next: a fresh Astra set, generated after workflow 11 and unread, as the next held-out validation.
