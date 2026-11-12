"""Synthetic-only security tests: no Chibi, Aiven, provider or private data."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import Lock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from council.api import create_app
from council.artifacts import ParentArtifactAccess, require_parent_receipt
from council.core import (
    Caller, Decision, Handoff, InvalidRun, PolicyDenied, build_graph, new_run_state
)
from council.replay import (
    ReplayConflict, ReplayReservation, deterministic_run_id, valid_reservation
)


DIGEST = "a" * 64
SOURCE_SHA = "b" * 40
CALLER = Caller("tenant.demo", "user.test", "junction.openai-codex")
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def utc(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def handoff(request_id, source, recipient, capability, authority, depth, parent):
    return Handoff(
        request_id=request_id, from_pet=source, to_pet=recipient,
        capability_id=capability, context_sha256=DIGEST, data_class="synthetic",
        authority_ref=authority, context_ref="host.context.redacted",
        source_sha=SOURCE_SHA, conversation_id="conversation.demo",
        parent_request_id=parent, depth=depth, max_depth=2, max_tokens=500,
        requested_effect="read", created_at=utc(NOW),
        expires_at=utc(NOW + timedelta(minutes=5)),
    )


FIRST = handoff("work.step1", "junction.openai-codex", "junction.mariadb",
                "query-review", "host.authority.one", 0, None)
SECOND = handoff("work.step2", "junction.mariadb", "junction.aiven",
                 "integration-review", "host.authority.two", 1, FIRST.request_id)


class FakeClock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


class FakeAtomicReplayStore:
    """Locked, ephemeral TEST store; never a production durability claim."""
    def __init__(self):
        self._lock = Lock()
        self._entries = {}
        self.created_count = 0
        self.invalid_fence = False
        self.unavailable = False

    def reserve(self, caller, first_request_id, envelope_digest, proposed_run_id):
        if self.unavailable:
            raise RuntimeError("SECRET_RESERVATION_STORE_FAILURE")
        key = (caller.tenant_id, caller.user_id, first_request_id)
        with self._lock:
            if key in self._entries:
                original = self._entries[key]
                if original.envelope_digest != envelope_digest:
                    raise ReplayConflict("different envelope")
                return ReplayReservation(**{**vars(original), "created": False})
            reservation = ReplayReservation(
                run_id=proposed_run_id, envelope_digest=envelope_digest,
                idempotency_key="host.run." + proposed_run_id.hex,
                fence_token=1, created=True, durable=True,
            )
            self._entries[key] = reservation
            self.created_count += 1
            return reservation

    def is_current(self, caller, reservation):
        if self.unavailable:
            raise RuntimeError("SECRET_FENCE_VERIFIER_FAILURE")
        with self._lock:
            return not self.invalid_fence and any(
                key[0] == caller.tenant_id and key[1] == caller.user_id
                and existing.run_id == reservation.run_id
                and existing.idempotency_key == reservation.idempotency_key
                and existing.fence_token == reservation.fence_token
                and existing.envelope_digest == reservation.envelope_digest
                for key, existing in self._entries.items()
            )


class HostPolicyFake:
    def __init__(self, clock):
        self.clock = clock
        self.revoke = set()
        self.invalid = False
        self.expire = False
        self.override_scope = {}
        self.seen = []

    def decide(self, caller, h, reservation):
        self.seen.append(h.request_id)
        if h.request_id in self.revoke:
            return None
        expiry = min(self.clock() + timedelta(seconds=60),
                     datetime.fromisoformat(h.expires_at.replace("Z", "+00:00")))
        if self.expire:
            expiry = self.clock() - timedelta(seconds=1)
        fields = dict(
            allowed=True, decision_id="host.grant.mock",
            tenant_id=caller.tenant_id, user_id=caller.user_id,
            request_id=h.request_id, from_pet=h.from_pet, to_pet=h.to_pet,
            capability_id=h.capability_id, context_sha256=DIGEST if not self.invalid else "c"*64,
            data_class=h.data_class, authority_ref=h.authority_ref,
            context_ref=h.context_ref, source_sha=h.source_sha,
            conversation_id=h.conversation_id, parent_request_id=h.parent_request_id,
            depth=h.depth, max_depth=h.max_depth, max_tokens=h.max_tokens,
            requested_effect=h.requested_effect, created_at=h.created_at,
            request_expires_at=h.expires_at,
            idempotency_key=reservation.idempotency_key,
            fence_token=reservation.fence_token, expires_at=expiry,
            allows_external_effects=False,
        )
        fields.update(self.override_scope)
        return Decision(**fields)


class FakeHostArtifactStore:
    """Ephemeral host-private TEST store. The graph only sees refs + digests."""
    PRIVATE_PARENT = "SENSITIVE_PRIVATE_PARENT_OUTPUT_CANARY: Kafka lag evidence"

    def __init__(self, clock):
        self.clock = clock
        self.records = {}
        self.reads = []
        self.fail = False
        self.override = {}
        self.after_authorize = None

    def save_first(self, caller, h, decision, reservation, receipt):
        self.records[receipt["artifact_ref"]] = {
            "tenant_id": caller.tenant_id, "user_id": caller.user_id,
            "request_id": h.request_id, "source_sha": h.source_sha,
            "run_id": reservation.run_id, "fence_token": reservation.fence_token,
            "decision_id": decision.decision_id,
            "receipt": deepcopy(receipt), "raw": self.PRIVATE_PARENT,
        }

    def authorize_parent_read(self, caller, parent, receipt, child, decision, reservation):
        if self.fail:
            raise RuntimeError("SENSITIVE_HOST_ARTIFACT_STORE_FAILURE")
        meta = receipt["execution"]
        record = self.records.get(meta["artifact_ref"])
        # This is an independent host-store verification: checkpoint metadata
        # alone cannot create or extend a grant or invent producer artifacts.
        if not record or any((
            record["tenant_id"] != caller.tenant_id,
            record["user_id"] != caller.user_id,
            record["request_id"] != parent.request_id,
            record["source_sha"] != parent.source_sha,
            record["run_id"] != reservation.run_id,
            record["fence_token"] != reservation.fence_token,
            record["decision_id"] != receipt["host_decision_id"],
            record["receipt"] != meta,
            child.parent_request_id != parent.request_id,
        )):
            return None
        expiry = min(self.clock() + timedelta(seconds=30),
                     decision.expires_at)
        access = ParentArtifactAccess(
            artifact_ref=meta["artifact_ref"],
            output_digest=meta["output_digest"],
            parent_request_id=parent.request_id,
            child_request_id=child.request_id,
            parent_decision_id=receipt["host_decision_id"],
            child_decision_id=decision.decision_id,
            tenant_id=caller.tenant_id, user_id=caller.user_id,
            run_id=reservation.run_id, fence_token=reservation.fence_token,
            source_sha=parent.source_sha, conversation_id=child.conversation_id,
            context_ref=child.context_ref, context_sha256=child.context_sha256,
            data_class=child.data_class, max_tokens=child.max_tokens,
            expires_at=expiry,
        )
        if self.override:
            access = replace(access, **self.override)
        if self.after_authorize:
            self.after_authorize()
        return access

    def read_private(self, caller, h, decision, reservation, access):
        # A stand-in for the actual host-private read and its mandatory
        # independently enforced scope checks at the consumption boundary.
        record = self.records.get(access.artifact_ref)
        if not record or any((
            record["tenant_id"] != caller.tenant_id,
            record["user_id"] != caller.user_id,
            record["run_id"] != reservation.run_id,
            record["fence_token"] != reservation.fence_token,
            record["request_id"] != h.parent_request_id,
            record["source_sha"] != decision.source_sha,
            access.child_decision_id != decision.decision_id,
            access.child_request_id != h.request_id,
            access.max_tokens != h.max_tokens,
            self.clock() >= access.expires_at,
        )):
            raise PolicyDenied("Host-private artifact read denied")
        self.reads.append((h.request_id, access.artifact_ref))
        return record["raw"]


class ReadOnlyExecutorFake:
    def __init__(self, policy=None):
        self.calls = []
        self.policy = policy
        self.return_effect = False
        self.tamper_source = False
        self.secret_canary = False
        self.raise_secret = False
        self.tokens_override = None
        self.after_first = None
        self.artifacts = None

    def invoke(self, caller, h, decision, reservation, *, prior_artifact=None):
        self.calls.append((h.request_id, h.max_tokens, reservation.idempotency_key,
                           reservation.fence_token))
        if (h.request_id == FIRST.request_id and prior_artifact is not None or
                h.request_id == SECOND.request_id and prior_artifact is None):
            raise PolicyDenied("Second pet must receive exactly its trusted parent artifact")
        if self.raise_secret:
            raise RuntimeError("SENSITIVE_TOOL_RESPONSE_CANARY")
        if self.policy and h.request_id == FIRST.request_id:
            self.policy.revoke.add(SECOND.request_id)
        if self.after_first and h.request_id == FIRST.request_id:
            self.after_first()
        if prior_artifact is not None:
            private_parent = self.artifacts.read_private(
                caller, h, decision, reservation, prior_artifact
            )
            # The second pet's output actually depends on its predecessor's
            # host-private content, not merely a second independent invocation.
            output_digest = "sha256:" + sha256(
                ("reviewed:" + private_parent).encode("utf-8")
            ).hexdigest()
        else:
            output_digest = "sha256:" + sha256(
                self.artifacts.PRIVATE_PARENT.encode("utf-8")
            ).hexdigest()
        receipt = {
            "kind": "read-only",
            "artifact_ref": "host.artifact." + h.request_id,
            "output_digest": output_digest,
            "provider_receipt_ref": None,
            "source_sha": "c" * 40 if self.tamper_source else h.source_sha,
            "external_effects": self.return_effect,
            "tokens_used": self.tokens_override if self.tokens_override is not None else 20,
        }
        if h.request_id == FIRST.request_id:
            self.artifacts.save_first(caller, h, decision, reservation, receipt)
        if self.secret_canary:
            receipt["raw_model_text"] = "SENSITIVE_TOOL_RESPONSE_CANARY"
        return receipt


def setup(policy=None, executor=None, clock=None, reserve=True):
    clock = clock or FakeClock()
    store = FakeAtomicReplayStore()
    policy = policy or HostPolicyFake(clock)
    executor = executor or ReadOnlyExecutorFake()
    artifact_store = FakeHostArtifactStore(clock)
    executor.artifacts = artifact_store
    graph = build_graph(
        policy, executor, MemorySaver(), store, clock,
        artifact_store=artifact_store,
    )
    reservation = None
    if reserve:
        reservation = store.reserve(CALLER, FIRST.request_id, "d" * 64,
                                    deterministic_run_id(CALLER, FIRST.request_id))
    return policy, executor, graph, store, reservation, clock


def state(reservation, clock=NOW, first=FIRST, second=SECOND):
    return new_run_state(CALLER, [first, second], reservation, now=clock)


def config(thread):
    return {"configurable": {"thread_id": str(thread)}}


def test_scope_and_durable_fence_required_before_graph():
    p, e, graph, store, reservation, clock = setup()
    assert state(reservation)["handoffs"][0]["max_tokens"] == 500
    assert state(reservation)["reservation"]["fence_token"] == 1
    with pytest.raises(InvalidRun, match="Exactly two"):
        new_run_state(CALLER, [FIRST], reservation)
    with pytest.raises(InvalidRun, match="durable"):
        new_run_state(CALLER, [FIRST, SECOND], None)
    with pytest.raises(InvalidRun, match="chain"):
        state(reservation, first=SECOND, second=FIRST)
    with pytest.raises(InvalidRun, match="Context requires"):
        state(reservation, second=Handoff(**{**vars(SECOND), "context_sha256": "raw private data"}))
    with pytest.raises(InvalidRun, match="context change"):
        state(reservation, second=Handoff(**{**vars(SECOND), "context_ref": "host.other"}))
    with pytest.raises(InvalidRun, match="Cross-source"):
        state(reservation, second=Handoff(**{**vars(SECOND), "source_sha": "c"*40}))
    with pytest.raises(InvalidRun, match="maxDepth"):
        state(reservation, first=Handoff(**{**vars(FIRST), "max_depth": 0}))
    with pytest.raises(InvalidRun, match="Parent/depth"):
        state(reservation, second=Handoff(**{**vars(SECOND), "parent_request_id": None}))
    assert valid_reservation(reservation, CALLER, FIRST.request_id, "d"*64)


def test_graph_two_handoffs_review_and_budget_fence_propagation():
    p, e, graph, store, reservation, clock = setup()
    thread = reservation.run_id
    graph.invoke(state(reservation), config(thread))
    snap = graph.get_state(config(thread))
    assert len(snap.values["results"]) == 2
    assert len(snap.tasks[0].interrupts) == 1
    assert [x[0] for x in e.calls] == [FIRST.request_id, SECOND.request_id]
    assert all(x[1:] == (500, reservation.idempotency_key, 1) for x in e.calls)
    # The second pet really consumes the first host-private result.
    assert e.artifacts.reads == [(SECOND.request_id, "host.artifact.work.step1")]
    expected = "sha256:" + sha256(
        ("reviewed:" + e.artifacts.PRIVATE_PARENT).encode("utf-8")
    ).hexdigest()
    assert snap.values["results"][1]["execution"]["output_digest"] == expected
    assert "SENSITIVE_PRIVATE_PARENT_OUTPUT_CANARY" not in str(snap.values)
    assert "SENSITIVE_PRIVATE_PARENT_OUTPUT_CANARY" not in str(snap.tasks)
    graph.invoke(Command(resume={"action": "approve"}), config(thread))
    assert graph.get_state(config(thread)).values["review_status"] == "approved"
    assert len(e.calls) == 2


def test_unknown_host_policy_denies_first_handoff_before_executor():
    p, e, graph, store, reservation, clock = setup()
    p.revoke.add(FIRST.request_id)
    with pytest.raises(PolicyDenied, match="missing or denied"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert e.calls == []


@pytest.mark.parametrize("bad", [
    {"conversation_id": "conversation.other"},
    {"parent_request_id": "work.other"},
    {"depth": 2},
    {"max_depth": 0},
    {"max_tokens": 501},
    {"requested_effect": "write"},
    {"request_expires_at": utc(NOW + timedelta(hours=1))},
    {"idempotency_key": "host.other"},
    {"fence_token": 2},
])
def test_host_decision_must_bind_full_scope(bad):
    p, e, graph, store, reservation, clock = setup()
    p.override_scope = bad
    with pytest.raises(PolicyDenied, match="complete requested scope"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert e.calls == []


def test_expired_host_decision_denied():
    p, e, graph, store, reservation, clock = setup()
    p.expire = True
    with pytest.raises(PolicyDenied, match="Host decision expired"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert not e.calls


def test_revocation_between_handoffs_and_explicit_checkpoint_resume():
    clock = FakeClock()
    p = HostPolicyFake(clock)
    e = ReadOnlyExecutorFake(policy=p)
    # Build with same injected fakes but no preexisting store.
    _, _, graph, store, reservation, _ = setup(p, e, clock)
    with pytest.raises(PolicyDenied, match="missing or denied"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert len(e.calls) == 1
    assert len(graph.get_state(config(reservation.run_id)).values["results"]) == 1
    p.revoke.clear()
    graph.invoke(None, config(reservation.run_id))
    assert len(e.calls) == 2


def test_expiry_between_steps_and_on_resume_fails_closed():
    clock = FakeClock()
    e = ReadOnlyExecutorFake()
    e.after_first = lambda: setattr(clock, "now", NOW + timedelta(minutes=5, seconds=1))
    p, e, graph, store, reservation, _ = setup(executor=e, clock=clock)
    with pytest.raises(PolicyDenied, match="TTL expired"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert len(e.calls) == 1
    assert len(graph.get_state(config(reservation.run_id)).values["results"]) == 1
    with pytest.raises(PolicyDenied, match="TTL expired"):
        graph.invoke(None, config(reservation.run_id))
    assert len(e.calls) == 1


def test_fence_revocation_and_clock_failure_fail_closed():
    p, e, graph, store, reservation, clock = setup()
    store.invalid_fence = True
    with pytest.raises(PolicyDenied, match="fence is stale"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert not e.calls
    store.invalid_fence = False
    store.unavailable = True
    with pytest.raises(PolicyDenied, match="fence verifier unavailable"):
        graph.invoke(None, config(reservation.run_id))
    assert not e.calls


@pytest.mark.parametrize("mode", ["return_effect", "tamper_source", "secret_canary", "raise_secret", "tokens_override"])
def test_executor_cannot_effect_tamper_leak_or_exceed_budget(mode):
    p, e, graph, store, reservation, clock = setup()
    setattr(e, mode, 501 if mode == "tokens_override" else True)
    with pytest.raises(PolicyDenied) as error:
        graph.invoke(state(reservation), config(reservation.run_id))
    assert "SENSITIVE_TOOL_RESPONSE_CANARY" not in str(error.value)
    assert "SENSITIVE_TOOL_RESPONSE_CANARY" not in str(graph.get_state(config(reservation.run_id)).values)


def test_missing_host_adapters_fail_at_initialization():
    p, e, graph, store, reservation, clock = setup()
    with pytest.raises(ValueError, match="Host policy"):
        build_graph(None, e, MemorySaver(), store)
    with pytest.raises(ValueError, match="Host policy"):
        build_graph(p, e, MemorySaver(), None)
    with pytest.raises(ValueError, match="parent artifact store"):
        build_graph(p, e, MemorySaver(), store)
    with pytest.raises(ValueError, match="ReplayStore"):
        create_app(graph, None, None)
    with pytest.raises(ValueError, match="ReplayStore"):
        create_app(graph, FakeAuthenticator(), None)


class FakeAuthenticator:
    def identify(self, request):
        if request.headers.get("X-Test-Identity") == "owner":
            return CALLER
        if request.headers.get("X-Test-Identity") == "intruder":
            return Caller("tenant.other", "user.other", CALLER.active_pet)
        return None


def canonical(h):
    return {
        "schemaVersion": "pet-collaboration.v1", "kind": "request",
        "requestId": h.request_id, "conversationId": h.conversation_id,
        "tenantId": CALLER.tenant_id, "actorPetId": h.from_pet,
        "recipientPetId": h.to_pet, "capabilityId": h.capability_id,
        "authorityRef": h.authority_ref, "sourceSha": h.source_sha,
        "requestedEffect": h.requested_effect,
        "createdAt": h.created_at, "expiresAt": h.expires_at,
        "depth": h.depth,
        "context": {"ref": h.context_ref, "digest": "sha256:" + h.context_sha256,
                    "dataClass": h.data_class},
        "budget": {"maxTokens": h.max_tokens, "maxDepth": h.max_depth},
        **({"parentRequestId": h.parent_request_id} if h.parent_request_id else {}),
    }


def app_fixture(executor=None):
    p, e, graph, store, _, clock = setup(executor=executor, reserve=False)
    app = create_app(graph, FakeAuthenticator(), store)
    return app, e, store


def test_authenticated_api_replay_same_id_no_second_invoke_and_human_review():
    app, e, store = app_fixture()
    client = TestClient(app)
    body = {"requests": [canonical(FIRST), canonical(SECOND)]}
    assert client.post("/runs", json=body).status_code == 401
    headers = {"X-Test-Identity": "owner"}
    created = client.post("/runs", json=body, headers=headers)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["status"] == "awaiting_review" and data["checkpoint_id"]
    run_id = data["id"]
    assert run_id == str(deterministic_run_id(CALLER, FIRST.request_id))
    assert store.created_count == 1
    assert len(e.calls) == 2
    assert "SENSITIVE_PRIVATE_PARENT_OUTPUT_CANARY" not in created.text
    again = client.post("/runs", json=body, headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == run_id
    assert len(e.calls) == 2
    assert client.get(f"/runs/{run_id}", headers={"X-Test-Identity": "intruder"}).status_code == 404
    assert client.post(f"/runs/{run_id}/review", json={
        "action": "approve", "checkpoint_id": "old"
    }, headers=headers).status_code == 409
    approved = client.post(f"/runs/{run_id}/review", json={
        "action": "approve", "checkpoint_id": data["checkpoint_id"]
    }, headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert len(e.calls) == 2


def test_same_request_id_conflicting_payload_denied_before_provider():
    app, e, store = app_fixture()
    client = TestClient(app)
    headers = {"X-Test-Identity": "owner"}
    body = {"requests": [canonical(FIRST), canonical(SECOND)]}
    assert client.post("/runs", json=body, headers=headers).status_code == 201
    modified = deepcopy(body)
    modified["requests"][1]["budget"]["maxTokens"] = 501
    conflict = client.post("/runs", json=modified, headers=headers)
    assert conflict.status_code == 409
    assert len(e.calls) == 2


def test_concurrent_duplicate_post_claims_exactly_one_graph_executor():
    app, e, store = app_fixture()
    body = {"requests": [canonical(FIRST), canonical(SECOND)]}
    def submit(_):
        with TestClient(app) as client:
            response = client.post("/runs", json=body, headers={"X-Test-Identity": "owner"})
            return response.status_code, response.json()
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(submit, range(6)))
    assert sorted(status for status, _ in responses) == [200]*5 + [201]
    assert len({item["id"] for _, item in responses}) == 1
    assert store.created_count == 1
    assert len(e.calls) == 2


def test_crash_gap_no_automatic_replay_or_false_exactly_once_claim():
    e = ReadOnlyExecutorFake()
    e.raise_secret = True  # Simulates provider invocation then pre-checkpoint crash.
    app, e, store = app_fixture(executor=e)
    with TestClient(app) as client:
        headers = {"X-Test-Identity": "owner"}
        body = {"requests": [canonical(FIRST), canonical(SECOND)]}
        first = client.post("/runs", json=body, headers=headers)
        assert first.status_code == 403
        assert "SENSITIVE_TOOL_RESPONSE_CANARY" not in first.text
        again = client.post("/runs", json=body, headers=headers)
        assert again.status_code == 200
        assert again.json()["id"] == str(deterministic_run_id(CALLER, FIRST.request_id))
        assert len(e.calls) == 1
        assert store.created_count == 1
        # A separate recovery worker could still replay after crash; actual
        # provider side effects need external outbox/idempotent key enforcement.


@pytest.mark.parametrize("forgery", [
    {"tenant_id": "tenant.intruder"},
    {"user_id": "user.intruder"},
    {"run_id": UUID("00000000-0000-0000-0000-000000000000")},
    {"parent_request_id": "work.forged"},
    {"child_request_id": "work.forged"},
    {"parent_decision_id": "host.forged"},
    {"child_decision_id": "host.forged"},
    {"artifact_ref": "host.artifact.forged"},
    {"output_digest": "sha256:" + "f" * 64},
    {"fence_token": 2},
    {"source_sha": "c" * 40},
    {"conversation_id": "conversation.intruder"},
    {"context_ref": "host.context.intruder"},
    {"context_sha256": "c" * 64},
    {"data_class": "private"},
    {"max_tokens": 5000},
    {"expires_at": NOW + timedelta(minutes=6)},
])
def test_forged_parent_artifact_access_never_reaches_second_pet(forgery):
    p, e, graph, store, reservation, clock = setup()
    e.artifacts.override = forgery
    with pytest.raises(PolicyDenied, match="Parent artifact grant"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert [x[0] for x in e.calls] == [FIRST.request_id]
    assert e.artifacts.reads == []
    snapshot = graph.get_state(config(reservation.run_id)).values
    assert len(snapshot["results"]) == 1
    assert "SENSITIVE_PRIVATE_PARENT_OUTPUT_CANARY" not in str(snapshot)


def test_parent_artifact_host_lookup_failure_denies_without_secret_leak():
    p, e, graph, store, reservation, clock = setup()
    e.artifacts.fail = True
    with pytest.raises(PolicyDenied, match="authorization unavailable") as exc:
        graph.invoke(state(reservation), config(reservation.run_id))
    assert "SENSITIVE_HOST_ARTIFACT_STORE_FAILURE" not in str(exc.value)
    assert [x[0] for x in e.calls] == [FIRST.request_id]
    assert e.artifacts.reads == []


def test_revoke_after_artifact_authorization_before_second_execution():
    p, e, graph, store, reservation, clock = setup()
    e.artifacts.after_authorize = lambda: p.revoke.add(SECOND.request_id)
    with pytest.raises(PolicyDenied, match="missing or denied"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert [x[0] for x in e.calls] == [FIRST.request_id]
    assert not e.artifacts.reads


def test_fence_turnover_after_artifact_authorization_denies():
    p, e, graph, store, reservation, clock = setup()
    e.artifacts.after_authorize = lambda: setattr(store, "invalid_fence", True)
    with pytest.raises(PolicyDenied, match="fence is stale"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert [x[0] for x in e.calls] == [FIRST.request_id]


def test_ttl_expires_during_artifact_authorization_denies_before_second():
    clock = FakeClock()
    p, e, graph, store, reservation, _ = setup(clock=clock)
    e.artifacts.after_authorize = lambda: setattr(
        clock, "now", NOW + timedelta(minutes=5, seconds=1)
    )
    with pytest.raises(PolicyDenied, match="Parent artifact grant expired"):
        graph.invoke(state(reservation), config(reservation.run_id))
    assert [x[0] for x in e.calls] == [FIRST.request_id]


def test_parent_receipt_rejects_forgery_or_wrong_canonical_parent():
    p, e, graph, store, reservation, clock = setup()
    graph.invoke(state(reservation), config(reservation.run_id))
    original = graph.get_state(config(reservation.run_id)).values["results"][0]
    for change in (
        {"request_id": "work.forged"},
        {"source_sha": "c" * 40},
        {"host_decision_id": "not a valid ref"},
        {"execution": {**original["execution"], "raw": "private canary"}},
    ):
        with pytest.raises(PolicyDenied):
            require_parent_receipt(FIRST, SECOND, [{**original, **change}])
    # An opaque forged reference is well-formed but never proves ownership:
    # the independent host artifact store has no matching producer record.
    forged = {
        **original, "execution": {
            **original["execution"], "artifact_ref": "host.artifact.forged",
        },
    }
    assert require_parent_receipt(FIRST, SECOND, [forged]) == forged
    decision = p.decide(CALLER, SECOND, reservation)
    assert e.artifacts.authorize_parent_read(
        CALLER, FIRST, forged, SECOND, decision, reservation
    ) is None
    with pytest.raises(PolicyDenied, match="Parent handoff chain"):
        require_parent_receipt(
            FIRST, Handoff(**{**vars(SECOND), "parent_request_id": "work.forged"}),
            [original],
        )


def test_live_public_context_without_provider_receipt_is_denied():
    p, e, graph, store, reservation, clock = setup()
    public_first = Handoff(**{**vars(FIRST), "data_class": "public"})
    public_second = Handoff(**{**vars(SECOND), "data_class": "public"})
    with pytest.raises(PolicyDenied, match="receipt reference"):
        graph.invoke(state(reservation, first=public_first, second=public_second),
                     config(reservation.run_id))
