## Choosing and operating Aiven services

- Minimal set for stated needs only: ACID records → PostgreSQL; event stream with
  replay or many consumers → Kafka; full-text search, logs → OpenSearch
  (https://aiven.io/docs/products/opensearch); cache, sessions, rate limits →
  Valkey (https://aiven.io/docs/products/valkey); large analytics → ClickHouse
  (https://aiven.io/docs/products/clickhouse). Ignore "add it for later".
- Name the source of truth (normally PostgreSQL); search and cache are derived.
- Managed integrations: `clickhouse_kafka` and `clickhouse_postgresql` (no custom
  connector), `logs` → OpenSearch, `metrics` → Thanos/PostgreSQL,
  `application_service_credential` for Runtime apps, `autoscaler` for disk.
- Flink: new workloads go through the Aiven account manager
  (https://aiven.io/docs/products/flink); default to a plain Kafka consumer.
- AI gateway: early availability, must be enabled for the organization, named
  models are billed (https://aiven.io/docs/products/ai-gateway/use-sdks).
- ClickHouse error code 241 is MEMORY_LIMIT_EXCEEDED: hypotheses are smaller insert
  batches, memory settings (`max_memory_usage`) or a larger plan; propose, do not
  conclude the root cause from a few log lines.
- Infrastructure as code: Aiven Operator for Kubernetes
  (https://aiven.io/docs/tools/kubernetes) with `authSecretRef`, or Terraform.
- Prices and plan availability: never estimate; send the user to current Aiven
  pricing or the Console for the exact plan, cloud and date.
- Read-only inspection only with a host grant (https://aiven.io/docs/tools/mcp-server):
  cite each observation with tool and timestamp.
