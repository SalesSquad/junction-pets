-- Disposable lab schema only; configured per run by index.mjs.
-- All EUR amounts are exact integer cents. All identities/transactions are synthetic.
CREATE TABLE wallet_accounts (
  account_id text PRIMARY KEY,
  opening_balance_cents bigint NOT NULL CHECK (opening_balance_cents >= 0),
  balance_cents bigint NOT NULL CHECK (balance_cents >= 0),
  currency text NOT NULL DEFAULT 'EUR' CHECK (currency = 'EUR')
);
CREATE TABLE ledger_batches (
  batch_id uuid PRIMARY KEY,
  order_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('SIMULATED_PAYMENT','SIMULATED_REFUND')),
  intent_digest text NOT NULL CHECK (length(intent_digest) = 64),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ledger_entries (
  batch_id uuid NOT NULL REFERENCES ledger_batches(batch_id),
  account_id text NOT NULL REFERENCES wallet_accounts(account_id),
  delta_cents bigint NOT NULL CHECK (delta_cents <> 0),
  currency text NOT NULL DEFAULT 'EUR' CHECK (currency = 'EUR'),
  PRIMARY KEY(batch_id,account_id)
);
CREATE TABLE demo_settlements (
  order_id text PRIMARY KEY,
  payment_batch_id uuid NOT NULL UNIQUE REFERENCES ledger_batches(batch_id),
  refund_batch_id uuid UNIQUE REFERENCES ledger_batches(batch_id),
  payment_digest text NOT NULL,
  buyer_account text NOT NULL REFERENCES wallet_accounts(account_id),
  total_cents bigint NOT NULL CHECK (total_cents > 0),
  allocations jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ledger_commands (
  idempotency_key text PRIMARY KEY,
  kind text NOT NULL CHECK(kind IN ('SIMULATED_PAYMENT','SIMULATED_REFUND')),
  intent_digest text NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ledger_outbox (
  event_id uuid PRIMARY KEY,
  batch_id uuid NOT NULL UNIQUE REFERENCES ledger_batches(batch_id),
  event_kind text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  delivered_at timestamptz
);
-- The outbox event is the durable seal for a posted ledger batch. Only a
-- one-way delivery timestamp may change; deleting/repointing an event must
-- never reopen a committed batch for additional entries.
CREATE FUNCTION guard_outbox_seal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('DELETE','TRUNCATE') THEN
    RAISE EXCEPTION 'IMMUTABLE_OUTBOX_SEAL' USING ERRCODE='23514';
  END IF;
  IF NEW.event_id IS DISTINCT FROM OLD.event_id OR
     NEW.batch_id IS DISTINCT FROM OLD.batch_id OR
     NEW.event_kind IS DISTINCT FROM OLD.event_kind OR
     NEW.payload IS DISTINCT FROM OLD.payload OR
     NEW.created_at IS DISTINCT FROM OLD.created_at OR
     (OLD.delivered_at IS NOT NULL AND NEW.delivered_at IS DISTINCT FROM OLD.delivered_at) THEN
    RAISE EXCEPTION 'IMMUTABLE_OUTBOX_SEAL' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER outbox_seal_write_guard BEFORE UPDATE OR DELETE ON ledger_outbox
FOR EACH ROW EXECUTE FUNCTION guard_outbox_seal();
CREATE TRIGGER outbox_seal_truncate_guard BEFORE TRUNCATE ON ledger_outbox
FOR EACH STATEMENT EXECUTE FUNCTION guard_outbox_seal();
CREATE FUNCTION assert_balanced_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n bigint; total bigint;
BEGIN
  -- A trigger can fire from an explicitly schema-qualified DML statement
  -- while the caller's search_path points elsewhere. Bind its owning schema,
  -- quote it as an identifier and pass the batch value separately.
  EXECUTE format(
    'SELECT count(*), coalesce(sum(delta_cents),0) FROM %I.ledger_entries WHERE batch_id = $1',
    TG_TABLE_SCHEMA)
    INTO n,total USING NEW.batch_id;
  IF n < 2 OR total <> 0 THEN
    RAISE EXCEPTION 'UNBALANCED_LEDGER_BATCH %: count %, net %',NEW.batch_id,n,total
      USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_batch_balanced
AFTER INSERT ON ledger_batches DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_balanced_batch();
-- A batch becomes sealed when its atomic outbox receipt is written. No later
-- transaction may append entries without re-running the balance constraint.
CREATE FUNCTION reject_sealed_batch_append() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sealed boolean;
BEGIN
  EXECUTE format(
    'SELECT EXISTS (SELECT 1 FROM %I.ledger_outbox WHERE batch_id = $1)',
    TG_TABLE_SCHEMA)
    INTO sealed USING NEW.batch_id;
  IF sealed THEN
    RAISE EXCEPTION 'SEALED_LEDGER_BATCH %',NEW.batch_id USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER entries_no_append_after_outbox BEFORE INSERT ON ledger_entries
FOR EACH ROW EXECUTE FUNCTION reject_sealed_batch_append();
CREATE FUNCTION forbid_ledger_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'IMMUTABLE_LEDGER_ROWS' USING ERRCODE='23514';
END $$;
CREATE TRIGGER entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
FOR EACH ROW EXECUTE FUNCTION forbid_ledger_rewrite();
CREATE TRIGGER batches_append_only BEFORE UPDATE OR DELETE ON ledger_batches
FOR EACH ROW EXECUTE FUNCTION forbid_ledger_rewrite();
CREATE TRIGGER entries_no_truncate BEFORE TRUNCATE ON ledger_entries
FOR EACH STATEMENT EXECUTE FUNCTION forbid_ledger_rewrite();
CREATE TRIGGER batches_no_truncate BEFORE TRUNCATE ON ledger_batches
FOR EACH STATEMENT EXECUTE FUNCTION forbid_ledger_rewrite();
