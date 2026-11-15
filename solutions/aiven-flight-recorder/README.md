# Aiven flight recorder — measured demo

Part of the `junction.aiven` companion's **event-flight-recorder** capability
(Best Use of Aiven). The same 200-action agent run executes twice:

- **Baseline (no Aiven):** in-process queue, blind producer retries, one process crash.
- **Flight recorder (Aiven):** PostgreSQL transactional outbox → relay (at-least-once,
  re-publishes every 10th row) → Aiven for Apache Kafka (keyed by tenant) → idempotent
  consumer that records processed keys in PostgreSQL, crashes once after its database
  commit but before its offset commit, restarts, then a separate consumer group
  replays the whole log.

Measured: executed effects, duplicates, lost actions, redelivered messages,
duplicates suppressed, effects a full replay would add, and per-tenant order.

```sh
npm ci
npm test                 # offline, deterministic, no external service
npm run demo             # offline comparison
npm run demo:live        # Aiven for Kafka + Aiven for PostgreSQL
```

Live configuration is read only from the environment: `AIVEN_KAFKA_BROKER`,
`AIVEN_KAFKA_CA`, `AIVEN_KAFKA_CERT`, `AIVEN_KAFKA_KEY` (file paths, certificate
auth), `AIVEN_PG_URL`, `AIVEN_PG_CA` (file path) and optional
`AIVEN_KAFKA_TOPIC` (pre-created topic; free Kafka plans allow at most two
partitions per topic and topic creation through the Aiven API). Each live run
uses its own PostgreSQL schema and tags messages with its run id.

The relay in this demo polls the outbox. Debezium in Kafka Connect is the
production replacement for the relay (see the companion's AGENTS.md); it was not
used here. Results are from synthetic actions; no email is sent.

See `RESULTS.md` for recorded runs.
