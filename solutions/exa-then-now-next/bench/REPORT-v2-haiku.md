# Benchmark v2: semantic support (rater: haiku)

Run: run2-2026-11-14T06-10-31-712Z.json · labels: 380/380 · judges blind to arm · Haiku swarm (Claude Code subagents) + OpenAI gpt-5.4-mini; consensus = both agree

| Metric | keywords | question | citation | auto_en | auto_native (n=0) |
|---|---|---|---|---|---|
| Results stating the rule, top 5 (mean) | 3.16 | 3.63 | 2.63 | 3.11 | NaN |
| Legal text stating the rule, top 5 (mean) | 1.47 | 0.37 | 2.16 | 2.42 | NaN |
| At least one result states the rule (share) | 1.00 | 1.00 | 0.89 | 0.89 | NaN |
| At least one LEGAL TEXT states the rule (share) | 0.68 | 0.37 | 0.89 | 0.89 | NaN |
| Top result states the rule (share) | 0.63 | 0.79 | 0.53 | 0.68 | NaN |
| Results contradicting the reference, top 5 (mean) | 0.05 | 0.16 | 0.11 | 0.00 | NaN |

Same metrics on the non-English subset only ():

| Metric | keywords | question | citation | auto_en | auto_native |
|---|---|---|---|---|---|
| Results stating the rule, top 5 (mean) | NaN | NaN | NaN | NaN | NaN |
| Legal text stating the rule, top 5 (mean) | NaN | NaN | NaN | NaN | NaN |
| At least one result states the rule (share) | NaN | NaN | NaN | NaN | NaN |
| At least one LEGAL TEXT states the rule (share) | NaN | NaN | NaN | NaN | NaN |
| Top result states the rule (share) | NaN | NaN | NaN | NaN | NaN |
| Results contradicting the reference, top 5 (mean) | NaN | NaN | NaN | NaN | NaN |

## Paired comparisons (wins / ties / losses, sign test p)

| Metric | Comparison | W | T | L | p |
|---|---|---|---|---|---|
| Results stating the rule, top 5 (mean) | citation vs keywords | 3 | 6 | 10 | 0.0923 |
| Results stating the rule, top 5 (mean) | citation vs question | 4 | 1 | 14 | 0.0309 |
| Results stating the rule, top 5 (mean) | auto_en vs question | 6 | 2 | 11 | 0.3323 |
| Results stating the rule, top 5 (mean) | auto_en vs keywords | 6 | 6 | 7 | 1.0000 |
| Results stating the rule, top 5 (mean) | auto_en vs citation | 9 | 7 | 3 | 0.1460 |
| Results stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Legal text stating the rule, top 5 (mean) | citation vs keywords | 11 | 5 | 3 | 0.0574 |
| Legal text stating the rule, top 5 (mean) | citation vs question | 17 | 1 | 1 | 0.0001 |
| Legal text stating the rule, top 5 (mean) | auto_en vs question | 16 | 2 | 1 | 0.0003 |
| Legal text stating the rule, top 5 (mean) | auto_en vs keywords | 11 | 5 | 3 | 0.0574 |
| Legal text stating the rule, top 5 (mean) | auto_en vs citation | 7 | 8 | 4 | 0.5488 |
| Legal text stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one result states the rule (share) | citation vs keywords | 0 | 17 | 2 | 0.5000 |
| At least one result states the rule (share) | citation vs question | 0 | 17 | 2 | 0.5000 |
| At least one result states the rule (share) | auto_en vs question | 0 | 17 | 2 | 0.5000 |
| At least one result states the rule (share) | auto_en vs keywords | 0 | 17 | 2 | 0.5000 |
| At least one result states the rule (share) | auto_en vs citation | 1 | 17 | 1 | 1.0000 |
| At least one result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | citation vs keywords | 5 | 13 | 1 | 0.2188 |
| At least one LEGAL TEXT states the rule (share) | citation vs question | 11 | 7 | 1 | 0.0063 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs question | 11 | 7 | 1 | 0.0063 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs keywords | 4 | 15 | 0 | 0.1250 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs citation | 1 | 17 | 1 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Top result states the rule (share) | citation vs keywords | 2 | 13 | 4 | 0.6875 |
| Top result states the rule (share) | citation vs question | 2 | 10 | 7 | 0.1797 |
| Top result states the rule (share) | auto_en vs question | 2 | 13 | 4 | 0.6875 |
| Top result states the rule (share) | auto_en vs keywords | 2 | 16 | 1 | 1.0000 |
| Top result states the rule (share) | auto_en vs citation | 5 | 12 | 2 | 0.4531 |
| Top result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs keywords | 1 | 17 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs question | 1 | 15 | 3 | 0.6250 |
| Results contradicting the reference, top 5 (mean) | auto_en vs question | 0 | 16 | 3 | 0.2500 |
| Results contradicting the reference, top 5 (mean) | auto_en vs keywords | 0 | 18 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs citation | 0 | 18 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |

## Cross-family agreement (Haiku vs OpenAI, n=380)

states_rule 3-way agreement 79 % (kappa 0.56); yes-vs-not agreement 84 % (kappa 0.65); source_type agreement 88 %.
Confusion (haiku>openai): {"partial>partial":71,"yes>yes":222,"partial>yes":38,"yes>partial":20,"no>partial":12,"partial>no":9,"no>no":7,"no>yes":1}
