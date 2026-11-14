-- Valio Aimo's own isolated, read-only retrieval projection. No BIM/Valmet data.
-- Apply only to an authorized PostgreSQL/Aiven database; NOT part of npm start.
-- The trade core is the only authority for price, stock, allergen and order state.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS aimo_retrieval;

CREATE TABLE IF NOT EXISTS aimo_retrieval.product_documents (
  tenant_id TEXT NOT NULL,
  buyer_scope TEXT NOT NULL,
  sku TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  product_title TEXT NOT NULL,
  family TEXT NOT NULL,
  lactose_free BOOLEAN, -- NULL = unknown. Never infer dietary safety from embeddings.
  search_text TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('AIMO_MOCK_CATALOG', 'AIMO_PRODUCT_DOCUMENT', 'AIMO_FIXTURE')),
  source_ref TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  source_observed_at TIMESTAMPTZ NOT NULL,
  valid_until TIMESTAMPTZ,
  embedding_model TEXT,
  embedding vector(384),
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'WITHDRAWN')),
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  document_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, search_text)) STORED,
  PRIMARY KEY (tenant_id, buyer_scope, sku, catalog_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS product_documents_current_sku
  ON aimo_retrieval.product_documents (tenant_id, buyer_scope, sku)
  WHERE is_current AND status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS product_documents_scope
  ON aimo_retrieval.product_documents (tenant_id, buyer_scope, status, is_current);
CREATE INDEX IF NOT EXISTS product_documents_lexical
  ON aimo_retrieval.product_documents USING gin (document_tsv);
-- Do not introduce approximate HNSW until enough real rows and a recall
-- benchmark justify it. Exact pgvector cosine scanning keeps perfect recall.

ALTER TABLE aimo_retrieval.product_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE aimo_retrieval.product_documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS product_documents_scoped_read ON aimo_retrieval.product_documents;
CREATE POLICY product_documents_scoped_read ON aimo_retrieval.product_documents
  FOR SELECT USING (
    tenant_id = current_setting('aimo.tenant_id', true)
    AND buyer_scope = current_setting('aimo.buyer_scope', true)
  );
-- FORCE RLS also applies to the table owner. These narrowly scoped policies
-- permit an explicitly GRANTED ingest role to seed and supersede documents.
-- The API retrieval role must receive SELECT ONLY, never INSERT/UPDATE.
DROP POLICY IF EXISTS product_documents_scoped_insert ON aimo_retrieval.product_documents;
CREATE POLICY product_documents_scoped_insert ON aimo_retrieval.product_documents
  FOR INSERT WITH CHECK (
    tenant_id = current_setting('aimo.tenant_id', true)
    AND buyer_scope = current_setting('aimo.buyer_scope', true)
  );
DROP POLICY IF EXISTS product_documents_scoped_update ON aimo_retrieval.product_documents;
CREATE POLICY product_documents_scoped_update ON aimo_retrieval.product_documents
  FOR UPDATE USING (
    tenant_id = current_setting('aimo.tenant_id', true)
    AND buyer_scope = current_setting('aimo.buyer_scope', true)
  ) WITH CHECK (
    tenant_id = current_setting('aimo.tenant_id', true)
    AND buyer_scope = current_setting('aimo.buyer_scope', true)
  );
REVOKE ALL ON aimo_retrieval.product_documents FROM PUBLIC;
-- A dedicated non-owner, non-BYPASSRLS application role needs SELECT on
-- this table and USAGE on this schema, provisioned by the database owner.
-- A DISTINCT non-BYPASSRLS ingest role needs narrowly scoped INSERT/UPDATE
-- and SELECT plus USAGE grants from the database owner, also per tenant.
-- Ingestion uses BEGIN, set_config('aimo.tenant_id',...), and
-- set_config('aimo.buyer_scope',...) before writes in the SAME transaction.
-- There is deliberately no DELETE policy and no public grant.
