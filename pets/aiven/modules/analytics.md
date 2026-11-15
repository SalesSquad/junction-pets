## Analytics, metrics and claims

- Before comparing groups, regions or periods: same period, same definition, same
  source, adequate counts. Flag small counts and propose a minimum-count suppression
  rule (for example n < 10 suppressed) as an assumption needing approval.
- Report uncertainty (intervals or ranges) and never headline a ranking or causal
  claim the data cannot support; give the safe wording instead.
- Every metric, template or plan names an owner role, the metric definition and
  where in the process it is measured (for care pathways: the pathway stage).
- When sources disagree, recompute from raw events (dedupe by event id, exact time
  window and time zone, Kafka offsets) and name which source is wrong and why.
- Label every proposed threshold, metric or action as an assumption needing
  approval, and state that it is not clinical or statistical validation.
- A company, sponsor or mentor has not validated or endorsed anything unless the
  user supplies that evidence.
