# Claims against a photo of a document (2026-11-14)

20 synthetic boarding passes, 160 claims (true or false by construction), jev-1.14.0 with `TypeSafe-Danger-Zone-Images: true`, all claims about one pass in one request.

| claim type | right | mean p(yes) |
|---|---|---|
| flight_true | 20/20 | 1.00 |
| flight_false | 20/20 | 0.00 |
| route_true | 20/20 | 1.00 |
| route_reversed | 20/20 | 0.00 |
| arrival_true | 20/20 | 0.99 |
| arrival_false | 20/20 | 0.00 |
| stamp | 20/20 | 0.84 |
| seat_false | 20/20 | 0.00 |

- overall 160/160 right; Brier 0.000
- outside the 0.3–0.7 band: 160/160 right; inside it (would go to a person): 0
- Box on the actual-arrival field: median IoU 0.29, IoU >= 0.5 in 0/20
- 20 requests (9 questions each): 9.4 s total incl. rendering; request p50 290 ms; 86650 input tokens ≈ $0.0036
