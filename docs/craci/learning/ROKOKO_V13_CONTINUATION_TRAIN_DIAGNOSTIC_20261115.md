# V13 continuation: local historical TRAIN diagnostic

**Scope: retrospective research only. No model promotion, safety qualification, independent test split or CRACI dispatch.**

On 15 November 2026, an isolated local MuJoCo 3.3.7 / NumPy 2.3.4 run compared V5, V12 and the continuation hypothesis introduced in #256 on the fixed historical TRAIN seed range 512001–512010. These previously exposed TRAIN seeds are not an independent or held-out cohort. There were five near and five clear worlds. Arms ran in V5, V12, continuation order, stopping on any observed unsafe episode or lost V5 safe goal; all 30 episodes completed.

| Observation | V5 | V12 | V13 continuation |
|---|---:|---:|---:|
| Safe 250-tick physical goals, out of 10 worlds | 3 | 3 | 3 |
| Novel safe goals versus paired V5 | — | 0 | 0 |
| Lost V5 goals | — | 0 | 0 |
| Observed unsafe episodes | 0 | 0 | 0 |
| Abstained episodes | 4 | 3 | 3 |

The three goals were the same three clear worlds in each arm. No near world reached a goal. V13 intervened for eight options in each of the five near worlds, with a changed full trace relative to V12 in each. V12 and V13 mean terminal distance on these five near worlds was 0.1437 m and 0.1531 m respectively. This is a small, retrospective description, not a population estimate or a causal comparison.

Reconstructing the candidate policy modes from the retained public observations and checking every chosen action against the recorded trace found **38 RETREAT actions, one PUSH_MEDIUM and one APPROACH_LEFT** among the 40 model-controlled options. RETREAT is a physical servo option, not an emergency stop. Its observed median change in object-to-goal distance was −0.102 mm per option. A forward mask was open in 22 of those 38 instances; mask legality alone does not establish that forcing a forward action would be safe. The result suggests that extending the existing one-step scorer did not form a productive multi-option goal path on these examples. It does not justify removing RETREAT or weakening V5's predictive safety checks.

The continuation candidate source was `960660121bf48fe455353e838866d2be3f4dbc4e` (ported to main in #256); the historical V5/V12 source and frozen weights came from `faec266d6d3a44af3a564f46e0778209c1dc3af1`. Their V12 policy bytes were checked for equality; frozen model SHA-256 was `82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e`. The local full-row and full-trace JSONL SHA-256 was `943622703298eb452b1c9324f21f3747461647f894afcbc757216fd2a10c5fe7`, and the execution script SHA-256 was `0dfa618c1cb7769a00d163ac69b61329a72e9c2b1549ebb4adb2258986a8f8f6`. Raw data and scripts remained in the local task workspace; they were not committed, independently replayed, provider-attested or confirmed synced elsewhere.

A separate local wiring smoke on previously observed TRAIN seed 512000 did replay the continuation policy and transitions with the original physics, but the continuation did not activate there. It is not evidence of candidate benefit. The distinct preregistered RIGHT4 burst study has not been run as a result of this diagnostic and does not test this continuation candidate.
