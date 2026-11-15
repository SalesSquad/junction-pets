-- MariaDB 11.8 temporal schema candidate; corrected DDL still needs a runtime re-run (M307).
-- Wikipedia revision time is stored in revised_at_utc. Database SYSTEM_TIME
-- is the IMPORT/CORRECTION clock and MUST NOT be presented as Wikipedia edit time.
-- 
-- IMPORTANT: Dataset, source revision and page IDs are exact identifiers.
-- MariaDB's default utf8mb4_uca1400_ai_ci merges case/accent variants, including
-- distinct Wikipedia pages and dataset names. That produced five real SQL
-- verification failures at d0be3abf (CRACI 43564983185). A binary NO PAD
-- collation preserves distinct case, accents and trailing spaces in both
-- primary/index keys and the prepared as-of query (not just SELECT filters).
-- CREATE IF NOT EXISTS does NOT migrate existing collations. For an existing
-- table, first audit collisions and plan an explicit transactional migration;
-- never silently alter or drop a populated historical table.
CREATE TABLE IF NOT EXISTS wiki_revision_events (
  dataset_id VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_nopad_bin NOT NULL,
  source_revision_id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_nopad_bin NOT NULL,
  page_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_nopad_bin NOT NULL,
  article_title VARCHAR(255) NOT NULL,
  revised_at_utc DATETIME(6) NOT NULL,
  content_body MEDIUMTEXT NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  source_url VARCHAR(1024) NULL,
  dataset_license VARCHAR(250) NOT NULL,
  provenance VARCHAR(40) NOT NULL DEFAULT 'UNDECLARED',
  retrieved_at_utc DATETIME(3) NULL,
  source_uri VARCHAR(1024) NULL,
  snapshot_sha256 CHAR(64) NULL,
  attribution TEXT NULL,
  PRIMARY KEY (dataset_id, source_revision_id),
  KEY page_date (dataset_id, page_id, revised_at_utc, source_revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 WITH SYSTEM VERSIONING;

-- Bind dataset_id, page_id and UTC time with prepared parameters.
-- Read >=2 rows and explicitly refuse same-time revisions.
SELECT source_revision_id, revised_at_utc, content_body, content_sha256, source_url
FROM wiki_revision_events
WHERE dataset_id = ? AND page_id = ? AND revised_at_utc <= ?
ORDER BY revised_at_utc DESC, source_revision_id DESC LIMIT 2;

-- Different question: what was stored in this database at an import-time snapshot?
SELECT dataset_id, page_id, content_sha256
FROM wiki_revision_events FOR SYSTEM_TIME AS OF TIMESTAMP '2026-11-14 00:00:00'
WHERE dataset_id = 'example-dataset';
