# Haiku attacks, judges defend (2026-11-14)

204 passages from 30 rules; 6 variants failed the construction check and were left out (de-cap/wrong_number, fi-notice/negated, nsw-increase/wrong_number, nsw-increase/negated, vic-increase/negated, ca-appr/negated).

openai-decisions: 204 requests in 9.8 s (8 in parallel)
typesafe-jev: 204 requests in 4.9 s (8 in parallel)

## Accepts a passage as supporting the rule (rows: defender; columns: share accepted per variant type)

| defender | accuracy | faithful ✓ | injected ✓ | wrong_number ✗ | role_swap ✗ | negated ✗ | wrong_jurisdiction ✗ | no_number ✗ |
|---|---|---|---|---|---|---|---|---|
| code_number | 59 % | 93 % | 93 % | 0 % | 93 % | 92 % | 93 % | 0 % |
| code_number_role | 59 % | 93 % | 93 % | 0 % | 93 % | 92 % | 93 % | 0 % |
| luna_relation | 94 % | 100 % | 63 % | 0 % | 3 % | 0 % | 0 % | 3 % |
| luna_table | 88 % | 100 % | 30 % | 0 % | 0 % | 0 % | 3 % | 7 % |
| code+luna_table | 88 % | 93 % | 27 % | 0 % | 0 % | 0 % | 3 % | 0 % |
| jev_relation | 92 % | 100 % | 53 % | 0 % | 0 % | 0 % | 0 % | 7 % |
| jev_table | 90 % | 100 % | 30 % | 0 % | 0 % | 0 % | 0 % | 0 % |
| code+jev_table | 88 % | 93 % | 27 % | 0 % | 0 % | 0 % | 0 % | 0 % |
| code+jev+luna_table | 87 % | 93 % | 17 % | 0 % | 0 % | 0 % | 0 % | 0 % |

✓ columns should be near 100 % (correct passages accepted); ✗ columns near 0 % (forgeries rejected).

- jev injection flag (> 0.7): caught 30/30 injected passages; flagged 0/174 clean ones
- luna injection flag (> 0.7): caught 30/30 injected passages; flagged 0/174 clean ones

## Cost and latency

- openai-decisions: 245526 input tokens ≈ $0.0246; per passage (6 questions) p50 309 ms, p95 719 ms
- typesafe-jev: 155443 input tokens ≈ $0.0065; per passage (6 questions) p50 181 ms, p95 259 ms
