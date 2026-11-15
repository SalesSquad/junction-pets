# Haiku drafts, Jev verifies (2026-11-14)

Drafts: `bench/adversarial/haiku_closed_book_api.json`

Haiku closed-book, all errands with a numeric reference: 23/28 = 82 % (95 % CI 64–92)
Haiku's self-reported confidence: 17/20 right at >= 80; wrong answers had 80, 50, 90, 85, 60 (informative, but it cannot point at the evidence)

## typesafe-jev: 18 errands with stored Exa evidence (11.1 s)

| errand | reference | Haiku closed-book | evidence sentences judged | verdict | final | right? |
|---|---|---|---|---|---|---|
| eu261-amount | EUR 250 | EUR 250 ✓ | 8 (5 pass) | haiku verified | EUR 250 | ✓ |
| eu-crd-withdrawal | 14 days | 14 days ✓ | 24 (7 pass) | haiku verified | 14 days | ✓ |
| eu-guarantee | two years | 2 years ✓ | 24 (6 pass) | haiku verified | 2 years | ✓ |
| gdpr-access | one month | one month ✓ | 10 (0 pass) | corrected from evidence | one month | ✓ |
| eu-rail | 25 % | 25%, 50% ✓ | 19 (4 pass) | haiku verified | 25% | ✓ |
| eu-bus | 120 minutes | 2 hours ✓ | 10 (0 pass) | corrected from evidence | 50 % | ✗ |
| eu-late-payment | 60 calendar days | 60 calendar days, 30 days ✓ | 24 (3 pass) | haiku verified | 60 calendar days | ✓ |
| uk-cra-reject | 30 days | 30 days ✓ | 17 (5 pass) | haiku verified | 30 days | ✓ |
| uk-deposit | 30 days | 30 days ✓ | 11 (5 pass) | haiku verified | 30 days | ✓ |
| uk261 | £220 | GBP 220 ✓ | 9 (2 pass) | haiku verified | GBP 220 | ✓ |
| us-dot-refund | six hours | 7-hour ✗ | 0 (0 pass) | nothing verified | — | abstain |
| us-fcba | 60 days | 60 days ✓ | 18 (0 pass) | nothing verified | — | abstain |
| us-cooling-off | third business day | 3 business days ✓ | 12 (2 pass) | haiku verified | 3 business days | ✓ |
| us-fdcpa | five days | 5 days ✓ | 10 (2 pass) | haiku verified | 5 days | ✓ |
| us-flsa | $7.25 | USD 7.25 ✓ | 13 (0 pass) | corrected from evidence | $6.55 | ✗ |
| ca-deposit | 21 days | 21 days ✓ | 11 (3 pass) | haiku verified | 21 days | ✓ |
| ny-deposit | 14 days | 14 days ✓ | 13 (3 pass) | haiku verified | 14 days | ✓ |
| ny-notice | 90 days | 30 days, 60 days, 90 days ✓ | 13 (0 pass) | corrected from evidence | sixty days | ✗ |

- Haiku closed-book on these 18: 17/18 = 94 % (95 % CI 74–99)
- verify, else auto-correct from evidence: answered 16/18; right among answered 13/16 = 81 % (95 % CI 57–93); overall right 13/18 = 72 % (95 % CI 49–88)
- wrong Haiku answers that passed verification: 0; right Haiku answers not verified: 5; corrections right 1/4
- **verify or escalate** (recommended): answered 12/18, right 12/12 = 100 % (95 % CI 76–100); escalated 6 to the full compiler (gdpr-access (Haiku was right), eu-bus (Haiku was right), us-dot-refund (Haiku was wrong), us-fcba (Haiku was right), us-flsa (Haiku was right), ny-notice (Haiku was right))
- latency per errand (all judgments in parallel): median 649 ms

## openai-decisions: 18 errands with stored Exa evidence (20.3 s)

| errand | reference | Haiku closed-book | evidence sentences judged | verdict | final | right? |
|---|---|---|---|---|---|---|
| eu261-amount | EUR 250 | EUR 250 ✓ | 8 (3 pass) | haiku verified | EUR 250 | ✓ |
| eu-crd-withdrawal | 14 days | 14 days ✓ | 24 (6 pass) | haiku verified | 14 days | ✓ |
| eu-guarantee | two years | 2 years ✓ | 24 (9 pass) | haiku verified | 2 years | ✓ |
| gdpr-access | one month | one month ✓ | 10 (3 pass) | haiku verified | one month | ✓ |
| eu-rail | 25 % | 25%, 50% ✓ | 19 (9 pass) | haiku verified | 25% | ✓ |
| eu-bus | 120 minutes | 2 hours ✓ | 10 (0 pass) | corrected from evidence | 50 % | ✗ |
| eu-late-payment | 60 calendar days | 60 calendar days, 30 days ✓ | 24 (2 pass) | haiku verified | 60 calendar days | ✓ |
| uk-cra-reject | 30 days | 30 days ✓ | 17 (6 pass) | haiku verified | 30 days | ✓ |
| uk-deposit | 30 days | 30 days ✓ | 11 (4 pass) | haiku verified | 30 days | ✓ |
| uk261 | £220 | GBP 220 ✓ | 9 (3 pass) | haiku verified | GBP 220 | ✓ |
| us-dot-refund | six hours | 7-hour ✗ | 0 (0 pass) | corrected from evidence | 20 calendar days | ✗ |
| us-fcba | 60 days | 60 days ✓ | 18 (8 pass) | haiku verified | 60 days | ✓ |
| us-cooling-off | third business day | 3 business days ✓ | 12 (5 pass) | haiku verified | 3 business days | ✓ |
| us-fdcpa | five days | 5 days ✓ | 10 (2 pass) | haiku verified | 5 days | ✓ |
| us-flsa | $7.25 | USD 7.25 ✓ | 13 (3 pass) | haiku verified | USD 7.25 | ✓ |
| ca-deposit | 21 days | 21 days ✓ | 11 (2 pass) | haiku verified | 21 days | ✓ |
| ny-deposit | 14 days | 14 days ✓ | 13 (4 pass) | haiku verified | 14 days | ✓ |
| ny-notice | 90 days | 30 days, 60 days, 90 days ✓ | 13 (0 pass) | corrected from evidence | sixty days | ✗ |

- Haiku closed-book on these 18: 17/18 = 94 % (95 % CI 74–99)
- verify, else auto-correct from evidence: answered 18/18; right among answered 15/18 = 83 % (95 % CI 61–94); overall right 15/18 = 83 % (95 % CI 61–94)
- wrong Haiku answers that passed verification: 0; right Haiku answers not verified: 2; corrections right 0/3
- **verify or escalate** (recommended): answered 15/18, right 15/15 = 100 % (95 % CI 80–100); escalated 3 to the full compiler (eu-bus (Haiku was right), us-dot-refund (Haiku was wrong), ny-notice (Haiku was right))
- latency per errand (all judgments in parallel): median 1203 ms

