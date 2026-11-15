# Benchmark v2: semantic support (rater: openai)

Run: run2-2026-11-14T06-10-31-712Z.json · labels: 380/380 · judges blind to arm · Haiku swarm (Claude Code subagents) + OpenAI gpt-5.4-mini; consensus = both agree

| Metric | keywords | question | citation | auto_en | auto_native (n=0) |
|---|---|---|---|---|---|
| Results stating the rule, top 5 (mean) | 3.63 | 3.74 | 3.16 | 3.21 | NaN |
| Legal text stating the rule, top 5 (mean) | 1.68 | 0.42 | 2.26 | 2.37 | NaN |
| At least one result states the rule (share) | 1.00 | 1.00 | 1.00 | 0.95 | NaN |
| At least one LEGAL TEXT states the rule (share) | 0.84 | 0.42 | 0.95 | 0.89 | NaN |
| Top result states the rule (share) | 0.74 | 0.74 | 0.79 | 0.79 | NaN |
| Results contradicting the reference, top 5 (mean) | 0.11 | 0.05 | 0.11 | 0.05 | NaN |

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
| Results stating the rule, top 5 (mean) | citation vs keywords | 4 | 6 | 9 | 0.2668 |
| Results stating the rule, top 5 (mean) | citation vs question | 3 | 5 | 11 | 0.0574 |
| Results stating the rule, top 5 (mean) | auto_en vs question | 5 | 5 | 9 | 0.4240 |
| Results stating the rule, top 5 (mean) | auto_en vs keywords | 6 | 5 | 8 | 0.7905 |
| Results stating the rule, top 5 (mean) | auto_en vs citation | 9 | 3 | 7 | 0.8036 |
| Results stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Legal text stating the rule, top 5 (mean) | citation vs keywords | 10 | 5 | 4 | 0.1796 |
| Legal text stating the rule, top 5 (mean) | citation vs question | 15 | 3 | 1 | 0.0005 |
| Legal text stating the rule, top 5 (mean) | auto_en vs question | 16 | 2 | 1 | 0.0003 |
| Legal text stating the rule, top 5 (mean) | auto_en vs keywords | 11 | 2 | 6 | 0.3323 |
| Legal text stating the rule, top 5 (mean) | auto_en vs citation | 7 | 2 | 10 | 0.6291 |
| Legal text stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one result states the rule (share) | citation vs keywords | 0 | 19 | 0 | 1.0000 |
| At least one result states the rule (share) | citation vs question | 0 | 19 | 0 | 1.0000 |
| At least one result states the rule (share) | auto_en vs question | 0 | 18 | 1 | 1.0000 |
| At least one result states the rule (share) | auto_en vs keywords | 0 | 18 | 1 | 1.0000 |
| At least one result states the rule (share) | auto_en vs citation | 0 | 18 | 1 | 1.0000 |
| At least one result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | citation vs keywords | 3 | 15 | 1 | 0.6250 |
| At least one LEGAL TEXT states the rule (share) | citation vs question | 11 | 7 | 1 | 0.0063 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs question | 10 | 8 | 1 | 0.0117 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs keywords | 3 | 14 | 2 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs citation | 0 | 18 | 1 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Top result states the rule (share) | citation vs keywords | 4 | 12 | 3 | 1.0000 |
| Top result states the rule (share) | citation vs question | 4 | 12 | 3 | 1.0000 |
| Top result states the rule (share) | auto_en vs question | 3 | 14 | 2 | 1.0000 |
| Top result states the rule (share) | auto_en vs keywords | 3 | 14 | 2 | 1.0000 |
| Top result states the rule (share) | auto_en vs citation | 3 | 13 | 3 | 1.0000 |
| Top result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs keywords | 2 | 15 | 2 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs question | 2 | 16 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs question | 1 | 17 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs keywords | 1 | 16 | 2 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs citation | 0 | 18 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |

## Cross-family agreement (Haiku vs OpenAI, n=380)

states_rule 3-way agreement 79 % (kappa 0.56); yes-vs-not agreement 84 % (kappa 0.65); source_type agreement 88 %.
Confusion (haiku>openai): {"partial>partial":71,"yes>yes":222,"partial>yes":38,"yes>partial":20,"no>partial":12,"partial>no":9,"no>no":7,"no>yes":1}
