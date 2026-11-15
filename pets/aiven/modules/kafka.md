## Kafka on Aiven

- Order exists only within a partition. The message key decides the partition:
  key by the entity whose order must hold (tenant, order id), never by an
  idempotency key or random value when order matters.
- One partition is read by one consumer in a group; consumers beyond the partition
  count are idle. Lag concentrated in one partition is key skew or a slow record,
  not a consumer shortage.
- **Side effects of a partition increase:** it cannot be undone (partitions cannot
  be removed), it changes the key→partition mapping so per-key order breaks across
  the change for keyed data, and it triggers consumer-group rebalancing. Propose it
  only with these stated, during low traffic, with a consumer-side plan.
- **Offset resets** skip or replay data: state which records are re-processed or
  lost, require idempotent consumers or a dedupe key first, stop the group, export
  the current offsets as rollback, and verify lag and counts afterwards.
- **Plan upgrades** need a cause first (lag per partition, consumer errors,
  rebalances, broker metrics); state that cost must be checked on current Aiven
  pricing; rollback is a plan downgrade where supported.
- Lag evidence set: partition count, active consumers, per-partition lag trend,
  committed offsets, rebalance and error observations over one explicit window.
- Consumer groups and lag: https://aiven.io/docs/products/kafka/concepts/monitor-consumer-group
- Debezium PostgreSQL source (pin the connector version):
  https://aiven.io/docs/products/kafka/kafka-connect/howto/debezium-source-connector-pg
