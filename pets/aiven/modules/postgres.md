## PostgreSQL performance

- Ask for version, redacted SQL, table/index definitions and an existing redacted
  plan; `pg_stat_statements` columns vary by version
  (https://aiven.io/docs/products/postgresql/howto/identify-pg-slow-queries).
- An index is a hypothesis until a before/after plan supports it. The index-repair
  page is about corruption and REINDEX locks
  (https://aiven.io/docs/products/postgresql/howto/repair-pg-index), not index choice.
- Scaling a plan without a measured cause is a guess; propose the check first.
