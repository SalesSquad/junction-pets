# Haiku drafts, Jev verifies (2026-11-14)

Drafts: `bench/adversarial/haiku_closed_book.json`

Haiku closed-book, all errands with a numeric reference: 25/28 = 89 % (95 % CI 73–96)
Haiku's self-reported confidence: 18/19 right at >= 80; wrong answers had 55, 95, 70 (informative, but it cannot point at the evidence)

## typesafe-jev: 18 errands with stored Exa evidence (11.5 s)

| errand | reference | Haiku closed-book | evidence sentences judged | verdict | final | right? |
|---|---|---|---|---|---|---|
| eu261-amount | EUR 250 | EUR 250 ✓ | 8 (5 pass) | haiku verified | EUR 250 | ✓ |
| eu-crd-withdrawal | 14 days | 14 days ✓ | 24 (4 pass) | haiku verified | 14 days | ✓ |
| eu-guarantee | two years | 2 years ✓ | 24 (6 pass) | haiku verified | 2 years | ✓ |
| gdpr-access | one month | one month ✓ | 10 (0 pass) | corrected from evidence | one month | ✓ |
| eu-rail | 25 % | 25% ✓ | 15 (1 pass) | haiku verified | 25% | ✓ |
| eu-bus | 120 minutes | 2-hour ✓ | 10 (0 pass) | corrected from evidence | 50 % | ✗ |
| eu-late-payment | 60 calendar days | 60 days ✓ | 19 (2 pass) | haiku verified | 60 days | ✓ |
| uk-cra-reject | 30 days | 30 days ✓ | 17 (5 pass) | haiku verified | 30 days | ✓ |
| uk-deposit | 30 days | 30 days ✓ | 11 (4 pass) | haiku verified | 30 days | ✓ |
| uk261 | £220 | GBP 220 ✓ | 9 (3 pass) | haiku verified | GBP 220 | ✓ |
| us-dot-refund | six hours | 6 hours ✓ | 7 (0 pass) | nothing verified | — | abstain |
| us-fcba | 60 days | 60 days ✓ | 18 (2 pass) | haiku verified | 60 days | ✓ |
| us-cooling-off | third business day | 3 business days ✓ | 12 (1 pass) | haiku verified | 3 business days | ✓ |
| us-fdcpa | five days | 5 days ✓ | 10 (2 pass) | haiku verified | 5 days | ✓ |
| us-flsa | $7.25 | USD 7.25 ✓ | 13 (1 pass) | haiku verified | USD 7.25 | ✓ |
| ca-deposit | 21 days | 21 days ✓ | 11 (4 pass) | haiku verified | 21 days | ✓ |
| ny-deposit | 14 days | 14 days ✓ | 13 (4 pass) | haiku verified | 14 days | ✓ |
| ny-notice | 90 days | 60 days, 30 days ✗ | 8 (0 pass) | corrected from evidence | ninety days | ✓ |

- Haiku closed-book on these 18: 17/18 = 94 % (95 % CI 74–99)
- verify, else auto-correct from evidence: answered 17/18; right among answered 16/17 = 94 % (95 % CI 73–99); overall right 16/18 = 89 % (95 % CI 67–97)
- wrong Haiku answers that passed verification: 0; right Haiku answers not verified: 3; corrections right 2/3
- **verify or escalate** (recommended): answered 14/18, right 14/14 = 100 % (95 % CI 78–100); escalated 4 to the full compiler (gdpr-access (Haiku was right), eu-bus (Haiku was right), us-dot-refund (Haiku was right), ny-notice (Haiku was wrong))
- latency per errand (all judgments in parallel): median 632 ms

## openai-decisions: 18 errands with stored Exa evidence (21.1 s)

| errand | reference | Haiku closed-book | evidence sentences judged | verdict | final | right? |
|---|---|---|---|---|---|---|
| eu261-amount | EUR 250 | EUR 250 ✓ | 8 (2 pass) | haiku verified | EUR 250 | ✓ |
| eu-crd-withdrawal | 14 days | 14 days ✓ | 24 (6 pass) | haiku verified | 14 days | ✓ |
| eu-guarantee | two years | 2 years ✓ | 24 (9 pass) | haiku verified | 2 years | ✓ |
| gdpr-access | one month | one month ✓ | 10 (5 pass) | haiku verified | one month | ✓ |
| eu-rail | 25 % | 25% ✓ | 15 (2 pass) | haiku verified | 25% | ✓ |
| eu-bus | 120 minutes | 2-hour ✓ | 10 (0 pass) | corrected from evidence | 50 % | ✗ |
| eu-late-payment | 60 calendar days | 60 days ✓ | 19 (4 pass) | haiku verified | 60 days | ✓ |
| uk-cra-reject | 30 days | 30 days ✓ | 17 (4 pass) | haiku verified | 30 days | ✓ |
| uk-deposit | 30 days | 30 days ✓ | 11 (4 pass) | haiku verified | 30 days | ✓ |
| uk261 | £220 | GBP 220 ✓ | 9 (3 pass) | haiku verified | GBP 220 | ✓ |
| us-dot-refund | six hours | 6 hours ✓ | 7 (3 pass) | haiku verified | 6 hours | ✓ |
| us-fcba | 60 days | 60 days ✓ | 18 (2 pass) | haiku verified | 60 days | ✓ |
| us-cooling-off | third business day | 3 business days ✓ | 12 (1 pass) | haiku verified | 3 business days | ✓ |
| us-fdcpa | five days | 5 days ✓ | 10 (2 pass) | haiku verified | 5 days | ✓ |
| us-flsa | $7.25 | USD 7.25 ✓ | 13 (4 pass) | haiku verified | USD 7.25 | ✓ |
| ca-deposit | 21 days | 21 days ✓ | 11 (3 pass) | haiku verified | 21 days | ✓ |
| ny-deposit | 14 days | 14 days ✓ | 13 (5 pass) | haiku verified | 14 days | ✓ |
| ny-notice | 90 days | 60 days, 30 days ✗ | 8 (0 pass) | corrected from evidence | sixty days | ✗ |

- Haiku closed-book on these 18: 17/18 = 94 % (95 % CI 74–99)
- verify, else auto-correct from evidence: answered 18/18; right among answered 16/18 = 89 % (95 % CI 67–97); overall right 16/18 = 89 % (95 % CI 67–97)
- wrong Haiku answers that passed verification: 0; right Haiku answers not verified: 1; corrections right 0/2
- **verify or escalate** (recommended): answered 16/18, right 16/16 = 100 % (95 % CI 81–100); escalated 2 to the full compiler (eu-bus (Haiku was right), ny-notice (Haiku was wrong))
- latency per errand (all judgments in parallel): median 1193 ms

