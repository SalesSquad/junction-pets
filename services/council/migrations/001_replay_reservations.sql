-- Host-admin migration only. Never run automatically from an incoming request.
-- PostgreSQL 14+. Stores scoped identifiers and digests; no raw user/model data.
CREATE SCHEMA IF NOT EXISTS junction_council;

CREATE TABLE IF NOT EXISTS junction_council.replay_reservations (
    tenant_id varchar(100) NOT NULL CHECK (tenant_id ~ '^[a-z0-9][a-z0-9._:-]{1,99}$'),
    user_id varchar(100) NOT NULL CHECK (user_id ~ '^[a-z0-9][a-z0-9._:-]{1,99}$'),
    first_request_id varchar(100) NOT NULL CHECK (first_request_id ~ '^[a-z0-9][a-z0-9._:-]{1,99}$'),
    active_pet varchar(100) NOT NULL CHECK (active_pet ~ '^[a-z0-9][a-z0-9._:-]{1,99}$'),
    run_id uuid NOT NULL UNIQUE,
    envelope_digest char(64) NOT NULL CHECK (envelope_digest ~ '^[a-f0-9]{64}$'),
    handoffs_digest char(64) NOT NULL CHECK (handoffs_digest ~ '^[a-f0-9]{64}$'),
    idempotency_key varchar(100) NOT NULL UNIQUE,
    fence_token bigint NOT NULL DEFAULT 1 CHECK (fence_token > 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, user_id, first_request_id),
    CHECK (idempotency_key = 'host.run.' || replace(run_id::text, '-', ''))
);

-- Scope and both digests are immutable. The only update is a terminal fence
-- advance, so a stale worker cannot make an invalidated reservation current.
CREATE OR REPLACE FUNCTION junction_council.guard_replay_reservation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Replay reservation tombstones cannot be deleted'
            USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.tenant_id, NEW.user_id, NEW.first_request_id, NEW.active_pet,
           NEW.run_id, NEW.envelope_digest, NEW.handoffs_digest,
           NEW.idempotency_key, NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.tenant_id, OLD.user_id, OLD.first_request_id, OLD.active_pet,
           OLD.run_id, OLD.envelope_digest, OLD.handoffs_digest,
           OLD.idempotency_key, OLD.created_at)
       OR NOT (OLD.active AND NOT NEW.active AND NEW.fence_token = OLD.fence_token + 1)
    THEN
        RAISE EXCEPTION 'Replay reservation is immutable except terminal invalidation'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS replay_reservation_immutable ON junction_council.replay_reservations;
CREATE TRIGGER replay_reservation_immutable
    BEFORE UPDATE OR DELETE ON junction_council.replay_reservations
    FOR EACH ROW EXECUTE FUNCTION junction_council.guard_replay_reservation();
