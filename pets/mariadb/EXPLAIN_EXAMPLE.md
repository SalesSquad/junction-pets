# Fictional inventory review — OFFLINE SYNTHETIC

This authored exercise is not MariaDB output, a model evaluation or a benchmark.
No SQL or DDL was executed. No database was contacted. Server version, engine,
schema, statistics and data distribution are unknown. These numbers are invented
teaching inputs, not claims about a particular MariaDB release's optimizer.

```sql
SELECT sku, quantity FROM inventory
WHERE warehouse_id = 7 AND quantity < 5;
```

The fictional request lists low-stock inventory in warehouse 7. Null quantities
do not satisfy the predicate. Whether negative quantities should count is a
business-rule question. The example assumes no ordering or pagination requirement.

Supplied synthetic `EXPLAIN EXTENDED` row (also in `explain-example.mjs`):

| table | type | possible_keys | key | rows | filtered | Extra |
| --- | --- | --- | --- | --- | --- | --- |
| inventory | ALL | idx_warehouse | NULL | 10000 | 2 | Using where |

## Read only what the evidence supports

According to the official [EXPLAIN reference](https://mariadb.com/docs/server/reference/sql-statements/administrative-sql-statements/analyze-and-explain-statements/explain),
`ALL` describes a full table scan. `possible_keys` lists candidate keys; `key`
identifies the selected key, with NULL meaning none. `rows` is an estimate;
`Using where` denotes a predicate check. Here the fixture supplies a candidate
index but selects none. This does not establish that the index is absent or bad.

The fixture's 2% `filtered` is an estimate. Multiplying 10000 by 0.02 gives an
illustrative estimate of 200 qualifying rows, not an observed result count.
Neither estimate establishes elapsed time or a bottleneck.

The official [ANALYZE statement reference](https://mariadb.com/docs/server/reference/sql-statements/administrative-sql-statements/analyze-and-explain-statements/analyze-statement)
distinguishes `r_rows` and `r_filtered` as execution observations. ANALYZE executes
the statement. Neither counter is supplied here; both remain unknown, not zero.
The checker can classify authored ANALYZE-shaped counters as supplied observations,
but even those synthetic inputs never prove real execution.

## Hypothesis and smallest next check

A warehouse/quantity index is a hypothesis to investigate, with unknown benefit.
There is no proposed DDL or promised index gain. First request the exact server
version, redacted table/index definitions and an existing matching plan from the
owner. Check whether the candidate index begins with warehouse_id and whether
the supplied plan matches the query and current statistics. If evidence differs,
revise the hypothesis. Only a separately authorized owner could later compare
plans and repeated timings on representative data with correctness checks and
controlled cache/load conditions. That work is outside this exercise.

## Reproduce the offline checks

Run `node --test tests/pet-mariadb.test.mjs` from the repository root.
`inspectEvidence` classifies supplied fields; `checkClaim` accepts only an exact
structured field/kind/value match and rejects execution and index-gain claims.
It is not a SQL parser, prose fact checker, general EXPLAIN validator, database
adapter or authentication mechanism. The limited format excludes JSON plans,
joins and rowid-filter notation. Supplied provenance labels are not attestations.

Official pages were retrieved through the hosted web tool on 2026-11-13;
direct runner HTTPS retrieval returned proxy HTTP 403. References support field
semantics, not these authored numbers. No live version compatibility was tested.
