## Time, versions and provenance

- Aiven offers PostgreSQL and MySQL, not MariaDB (verified in the service-type list
  on 14 Nov 2026). Say which SQL dialect you write and that it is unexecuted.
- Model validity as half-open intervals `[valid_from, valid_to)`: a point lies inside
  when `valid_from <= t AND (valid_to IS NULL OR t < valid_to)`. Flag boundary
  equality explicitly.
- Store timestamps in UTC with an explicit time zone and convert only for display;
  name the zone in every comparison. Mixed or missing zones are an uncertainty.
- Separate valid time (when a fact was true) from transaction time (when it was
  recorded). An "as of" answer needs both, plus the source revision. PostgreSQL has
  no built-in system versioning: use history tables or temporal extensions, and
  point-in-time recovery only for restores, not for queries.
- When two sources disagree on a timestamp, keep both with provenance; do not pick
  one silently.
- Benchmarks: same dataset and version, warm and cold runs, several repetitions,
  report the distribution (median and p95), and never invent or extrapolate numbers.
- Connection or permission failures: check user, password or certificate, network
  allowlist (`ip_filter`), TLS mode and grants/ACLs (Kafka topic ACLs, SQL GRANTs).
  Credentials only through the host's secret flow.
