## Replayable agent event log ("flight recorder")

- Write the state change and an outbox row in one PostgreSQL transaction; Debezium
  (Kafka Connect) or a relay publishes it at least once.
- Message key = the ordering entity; every message carries an idempotency key.
- Consumers record the idempotency key and the effect in one database transaction,
  then commit the Kafka offset (database first, offset second). Redeliveries become
  no-ops; a lost consumer shows an explicit unavailable state.
- Kafka transactions do not make an external side effect (email, card charge)
  exactly-once.
- Prove it: inject duplicates, kill the consumer mid-run, replay, count side effects
  against a no-Kafka baseline.
