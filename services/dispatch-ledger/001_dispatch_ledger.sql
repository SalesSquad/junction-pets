-- Junction Council durable dispatch ledger (PostgreSQL 14+).
-- This migration stores digests and opaque identifiers only; never tool payloads or secrets.
-- Apply only to an owner-designated, isolated database/schema after review.

CREATE SCHEMA IF NOT EXISTS junction_dispatch;

CREATE TABLE IF NOT EXISTS junction_dispatch.jobs (
  job_id uuid PRIMARY KEY,
  tenant_id text NOT NULL CHECK (length(tenant_id) BETWEEN 1 AND 160),
  pet_id text NOT NULL CHECK (length(pet_id) BETWEEN 1 AND 160),
  source_commit char(40) NOT NULL CHECK (source_commit ~ '^[0-9a-f]{40}$'),
  input_sha256 char(64) NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
  idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 240),
  state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'leased', 'completed', 'dead_letter')),
  priority integer NOT NULL DEFAULT 0,
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 100),
  fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  lease_owner text,
  lease_expires_at timestamptz,
  next_run_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT jobs_tenant_pet_idempotency UNIQUE (tenant_id, pet_id, idempotency_key),
  CONSTRAINT jobs_lease_shape CHECK (
    (state = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (state <> 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS jobs_claim_queue
  ON junction_dispatch.jobs (priority DESC, next_run_at, created_at)
  WHERE state = 'queued';
CREATE INDEX IF NOT EXISTS jobs_expired_leases
  ON junction_dispatch.jobs (lease_expires_at)
  WHERE state = 'leased';

-- An outbox intent is NOT a provider call. The Chibi host must recheck grant,
-- revocation and scopes immediately before performing the actual effect.
-- External exactly-once delivery additionally requires downstream idempotency.
CREATE TABLE IF NOT EXISTS junction_dispatch.effect_outbox (
  effect_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES junction_dispatch.jobs(job_id) ON DELETE RESTRICT,
  tenant_id text NOT NULL,
  effect_idempotency_key text NOT NULL CHECK (length(effect_idempotency_key) BETWEEN 1 AND 240),
  scope text NOT NULL CHECK (length(scope) BETWEEN 1 AND 240),
  payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  host_grant_receipt_sha256 char(64) NOT NULL CHECK (host_grant_receipt_sha256 ~ '^[0-9a-f]{64}$'),
  state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'delivered')),
  provider_receipt_sha256 char(64),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  delivered_at timestamptz,
  CONSTRAINT effect_tenant_idempotency UNIQUE (tenant_id, effect_idempotency_key),
  CONSTRAINT effect_delivery_shape CHECK (
    (state = 'pending' AND provider_receipt_sha256 IS NULL AND delivered_at IS NULL)
    OR (state = 'delivered' AND provider_receipt_sha256 IS NOT NULL AND delivered_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS effects_by_job
  ON junction_dispatch.effect_outbox (job_id, state);

CREATE TABLE IF NOT EXISTS junction_dispatch.results (
  job_id uuid PRIMARY KEY REFERENCES junction_dispatch.jobs(job_id) ON DELETE RESTRICT,
  fencing_token bigint NOT NULL,
  result_sha256 char(64) NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
  completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON SCHEMA junction_dispatch IS 'Council durable work records, not Chibi authorization';
