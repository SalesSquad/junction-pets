# Benchmark v2: semantic support (rater: consensus)

Run: run2-2026-11-14T06-10-31-712Z.json · labels: 380/380 · judges blind to arm · Haiku swarm (Claude Code subagents) + OpenAI gpt-5.4-mini; consensus = both agree

| Metric | keywords | question | citation | auto_en | auto_native (n=0) |
|---|---|---|---|---|---|
| Results stating the rule, top 5 (mean) | 3.00 | 3.32 | 2.42 | 2.74 | NaN |
| Legal text stating the rule, top 5 (mean) | 1.32 | 0.37 | 1.74 | 1.95 | NaN |
| At least one result states the rule (share) | 1.00 | 0.95 | 0.89 | 0.84 | NaN |
| At least one LEGAL TEXT states the rule (share) | 0.68 | 0.37 | 0.89 | 0.68 | NaN |
| Top result states the rule (share) | 0.63 | 0.68 | 0.53 | 0.58 | NaN |
| Results contradicting the reference, top 5 (mean) | 0.00 | 0.05 | 0.05 | 0.00 | NaN |

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
| Results stating the rule, top 5 (mean) | citation vs keywords | 2 | 8 | 9 | 0.0654 |
| Results stating the rule, top 5 (mean) | citation vs question | 4 | 2 | 13 | 0.0490 |
| Results stating the rule, top 5 (mean) | auto_en vs question | 6 | 2 | 11 | 0.3323 |
| Results stating the rule, top 5 (mean) | auto_en vs keywords | 6 | 5 | 8 | 0.7905 |
| Results stating the rule, top 5 (mean) | auto_en vs citation | 9 | 6 | 4 | 0.2668 |
| Results stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Legal text stating the rule, top 5 (mean) | citation vs keywords | 9 | 7 | 3 | 0.1460 |
| Legal text stating the rule, top 5 (mean) | citation vs question | 14 | 4 | 1 | 0.0010 |
| Legal text stating the rule, top 5 (mean) | auto_en vs question | 12 | 6 | 1 | 0.0034 |
| Legal text stating the rule, top 5 (mean) | auto_en vs keywords | 8 | 7 | 4 | 0.3877 |
| Legal text stating the rule, top 5 (mean) | auto_en vs citation | 7 | 3 | 9 | 0.8036 |
| Legal text stating the rule, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one result states the rule (share) | citation vs keywords | 0 | 17 | 2 | 0.5000 |
| At least one result states the rule (share) | citation vs question | 0 | 18 | 1 | 1.0000 |
| At least one result states the rule (share) | auto_en vs question | 1 | 15 | 3 | 0.6250 |
| At least one result states the rule (share) | auto_en vs keywords | 0 | 16 | 3 | 0.2500 |
| At least one result states the rule (share) | auto_en vs citation | 1 | 16 | 2 | 1.0000 |
| At least one result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | citation vs keywords | 5 | 13 | 1 | 0.2188 |
| At least one LEGAL TEXT states the rule (share) | citation vs question | 11 | 7 | 1 | 0.0063 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs question | 7 | 11 | 1 | 0.0703 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs keywords | 2 | 15 | 2 | 1.0000 |
| At least one LEGAL TEXT states the rule (share) | auto_en vs citation | 0 | 15 | 4 | 0.1250 |
| At least one LEGAL TEXT states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Top result states the rule (share) | citation vs keywords | 2 | 13 | 4 | 0.6875 |
| Top result states the rule (share) | citation vs question | 3 | 10 | 6 | 0.5078 |
| Top result states the rule (share) | auto_en vs question | 3 | 11 | 5 | 0.7266 |
| Top result states the rule (share) | auto_en vs keywords | 1 | 16 | 2 | 1.0000 |
| Top result states the rule (share) | auto_en vs citation | 3 | 14 | 2 | 1.0000 |
| Top result states the rule (share) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs keywords | 1 | 18 | 0 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | citation vs question | 1 | 17 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs question | 0 | 18 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs keywords | 0 | 19 | 0 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_en vs citation | 0 | 18 | 1 | 1.0000 |
| Results contradicting the reference, top 5 (mean) | auto_native vs auto_en | 0 | 0 | 0 | 1.0000 |

## Cross-family agreement (Haiku vs OpenAI, n=380)

states_rule 3-way agreement 79 % (kappa 0.56); yes-vs-not agreement 84 % (kappa 0.65); source_type agreement 88 %.
Confusion (haiku>openai): {"partial>partial":71,"yes>yes":222,"partial>yes":38,"yes>partial":20,"no>partial":12,"partial>no":9,"no>no":7,"no>yes":1}
