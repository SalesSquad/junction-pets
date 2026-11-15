| errand | reference | premises (role: value) | covered | model prior vs explainer |
|---|---|---|---|---|
| eu261-amount | EUR 250 | t: three hours; t: 1,500km; o: €250; o: 50% | ✓ | agree/none |
| eu-crd-withdrawal | 14 days | o: 14-day | ✓ | agree/none |
| eu-guarantee | two years | o: 2-year | ✓ | agree/none |
| gdpr-access | one month | o: 1 month | ✓ | agree/none |
| eu-rail | 25 % | t: 60 minutes; o: € 1.50; o: 25% | ✓ | flag: 60 minutes |
| eu-bus | 120 minutes | t: two hours; o: 250 km | ✓ | agree/none |
| eu-late-payment | 60 calendar days | o: 60 days | ✓ | agree/none |
| uk-cra-reject | 30 days | o: 30 days | ✓ | agree/none |
| uk-deposit | 30 days | o: 30 days | ✓ | agree/none |
| uk261 | £220 | t: three hours; o: £220 | ✓ | agree/none |
| us-dot-refund | six hours | t: 6 hours; o: 7 business days | ✓ | agree/none |
| us-fcba | 60 days | o: 60 days | ✓ | agree/none |
| us-cooling-off | third business day | o: third business day | ✓ | agree/none |
| us-fdcpa | five days | o: five days | ✓ | agree/none |
| us-flsa | $7.25 | o: $7.25 | ✓ | agree/none |
| ca-deposit | 21 days | o: 21 days | ✓ | agree/none |
| ny-deposit | 14 days | o: 14 days | ✓ | agree/none |
| ny-notice | 90 days | o: 30 days | ✗ | agree/none |

errands 18: reference covered by some premise 17/18; primary outcome correct 14/18
tiers: 2 resolved from the question, 2 errands would ask a clarifying question
  - eu261-amount: tiers €250/€400 resolved to €250 by condition
  - eu-rail: tiers 25%/50% resolved to 25% by condition
  - uk261: ASK "How long is the flight, in kilometres?" options: Up to 1,500km 3+ hours → £220 | 1,500km to 3,500km 3+ hours → £350
  - ny-notice: ASK "How long have you lived in the unit, and how long is your lease term?" options: ase term of one year or longer → 30 days |  year, but less than two years → 60 days | ase term is at least two years → 90 days
model-vs-explainer flags 1/18; of the 1 errands where extraction missed the reference, 0 were flagged
