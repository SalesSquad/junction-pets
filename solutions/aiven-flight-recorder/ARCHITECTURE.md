# aiven-flight-recorder architecture

core.mjs owns the fault schedule and measurements; memory.mjs is the deterministic Kafka-like adapter; live.mjs uses Aiven for Apache Kafka (certificate auth) and Aiven for PostgreSQL; cli.mjs compares the no-service baseline with the recorder.

No provider, host or Aiven write is performed by this code; live paths are read-only or need an explicit host grant.
