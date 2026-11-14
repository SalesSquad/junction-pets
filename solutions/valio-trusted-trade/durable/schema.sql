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
CREATE FUNCTION assert_balanced_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n bigint; total bigint;
BEGIN
  SELECT count(*), coalesce(sum(delta_cents),0)
    INTO n,total FROM ledger_entries WHERE batch_id = NEW.batch_id;
  IF n < 2 OR total <> 0 THEN
    RAISE EXCEPTION 'UNBALANCED_LEDGER_BATCH %: count %, net %',NEW.batch_id,n,total
      USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_batch_balanced
AFTER INSERT ON ledger_batches DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_balanced_batch();
CREATE FUNCTION forbid_ledger_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'IMMUTABLE_LEDGER_ROWS' USING ERRCODE='23514';
END $$;
CREATE TRIGGER entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
FOR EACH ROW EXECUTE FUNCTION forbid_ledger_rewrite();
CREATE TRIGGER batches_append_only BEFORE UPDATE OR DELETE ON ledger_batches
FOR EACH ROW EXECUTE FUNCTION forbid_ledger_rewrite();
