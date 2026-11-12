"""No provider, Chibi, network or production data is used in these tests."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from council.api import create_app
from council.core import (
    Caller, Decision, Handoff, InvalidRun, PolicyDenied, build_graph, new_run_state
)


DIGEST = "a" * 64
SOURCE_SHA = "b" * 40  # Synthetic SHA fixture, not a verified GitHub commit.
CALLER = Caller("tenant.demo", "user.test", "junction.openai-codex")
FIRST = Handoff("work.step1", "junction.openai-codex", "junction.mariadb", "query-review", DIGEST, "synthetic", "host.authority.one", "host.context.redacted", SOURCE_SHA)
SECOND = Handoff("work.step2", "junction.mariadb", "junction.aiven", "integration-review", DIGEST, "synthetic", "host.authority.two", "host.context.redacted", SOURCE_SHA)


class HostPolicyFake:
    def __init__(self):
        self.revoke = set()
        self.invalid = False
        self.invalid_source = False
        self.expire = False
        self.seen = []

    def decide(self, caller, handoff):
        self.seen.append(handoff.request_id)
        if handoff.request_id in self.revoke:
            return None
        return Decision(
            allowed=True,
            decision_id="host.grant.mock",
            tenant_id=caller.tenant_id,
            user_id=caller.user_id,
            request_id=handoff.request_id,
            from_pet=handoff.from_pet,
            to_pet=handoff.to_pet,
            capability_id=handoff.capability_id,
            context_sha256="b" * 64 if self.invalid else handoff.context_sha256,
            data_class=handoff.data_class,
            authority_ref=handoff.authority_ref,
            context_ref=handoff.context_ref,
            source_sha="c" * 40 if self.invalid_source else handoff.source_sha,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=-1 if self.expire else 60),
            allows_external_effects=False,
        )


class ReadOnlyExecutorFake:
    def __init__(self, policy=None):
        self.calls = []
        self.policy = policy
        self.return_effect = False
        self.tamper_source = False
        self.secret_canary = False
        self.raise_secret = False

    def invoke(self, caller, handoff, decision):
        self.calls.append(handoff.request_id)
        if self.raise_secret:
            raise RuntimeError("SENSITIVE_TOOL_RESPONSE_CANARY")
        # Simulates actual revocation between two separate delegated pet calls.
        if self.policy and handoff.request_id == FIRST.request_id:
            self.policy.revoke.add(SECOND.request_id)
        receipt = {
            "kind": "read-only",
            "artifact_ref": "host.artifact.mock",
            "output_digest": "sha256:" + "d" * 64,
            "provider_receipt_ref": None,
            "source_sha": "c" * 40 if self.tamper_source else handoff.source_sha,
            "external_effects": self.return_effect,
        }
        if self.secret_canary:
            receipt["raw_model_text"] = "SENSITIVE_TOOL_RESPONSE_CANARY"
        return receipt


def setup(policy=None, executor=None):
    policy = policy or HostPolicyFake()
    executor = executor or ReadOnlyExecutorFake()
    graph = build_graph(policy, executor, MemorySaver())
    return policy, executor, graph


def config(thread):
    return {"configurable": {"thread_id": thread}}


def test_bounded_handoffs_and_fail_closed_inputs():
    state = new_run_state(CALLER, [FIRST, SECOND])
    assert state["handoffs"][0]["to_pet"] == "junction.mariadb"
    with pytest.raises(InvalidRun, match="Exactly two"):
        new_run_state(CALLER, [FIRST])
    with pytest.raises(InvalidRun, match="chain"):
        new_run_state(CALLER, [SECOND, FIRST])
    with pytest.raises(InvalidRun, match="SHA-256"):
        new_run_state(CALLER, [FIRST, Handoff(**{**vars(SECOND), "context_sha256": "raw user private data"})])
    with pytest.raises(InvalidRun, match="context change"):
        new_run_state(CALLER, [FIRST, Handoff(**{**vars(SECOND), "context_sha256": "b" * 64})])
    with pytest.raises(InvalidRun, match="Cross-source"):
        new_run_state(CALLER, [FIRST, Handoff(**{**vars(SECOND), "source_sha": "c" * 40})])


def test_two_real_graph_nodes_then_human_review_without_reexecution():
    p, e, graph = setup()
    graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config("normal"))
    snapshot = graph.get_state(config("normal"))
    assert len(snapshot.values["results"]) == 2
    assert len(snapshot.tasks[0].interrupts) == 1
    assert e.calls == [FIRST.request_id, SECOND.request_id]
    graph.invoke(Command(resume={"action": "approve"}), config("normal"))
    final = graph.get_state(config("normal"))
    assert final.values["review_status"] == "approved"
    assert e.calls == [FIRST.request_id, SECOND.request_id]
    assert not final.tasks


def test_unknown_host_policy_denies_first_handoff_before_executor():
    p, e, graph = setup()
    p.revoke.add(FIRST.request_id)
    with pytest.raises(PolicyDenied, match="missing or denied"):
        graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config("unknown"))
    assert e.calls == []


def test_exact_scope_mismatch_and_expiry_deny():
    for change in ("invalid", "invalid_source", "expire"):
        p, e, graph = setup()
        setattr(p, change, True)
        with pytest.raises(PolicyDenied):
            graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config(change))
        assert e.calls == []


def test_revocation_between_handoffs_blocks_then_explicit_resume_from_checkpoint():
    p = HostPolicyFake()
    e = ReadOnlyExecutorFake(policy=p)
    _, _, graph = setup(p, e)
    with pytest.raises(PolicyDenied, match="missing or denied"):
        graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config("revoke"))
    assert e.calls == [FIRST.request_id]
    stalled = graph.get_state(config("revoke"))
    assert len(stalled.values["results"]) == 1
    assert stalled.values["results"][0]["request_id"] == FIRST.request_id

    # A new authorizing decision permits the same checkpointed run to continue.
    # This is explicit resume, not a self-running crash recovery worker.
    p.revoke.clear()
    graph.invoke(None, config("revoke"))
    assert e.calls == [FIRST.request_id, SECOND.request_id]
    assert len(graph.get_state(config("revoke")).values["results"]) == 2


def test_external_effect_receipt_is_rejected():
    p, e, graph = setup()
    e.return_effect = True
    with pytest.raises(PolicyDenied, match="unapproved effect"):
        graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config("effect"))


def test_host_executor_cannot_self_attest_a_different_source():
    p, e, graph = setup()
    e.tamper_source = True
    with pytest.raises(PolicyDenied, match="authorized commit"):
        graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config("tamper-source"))


@pytest.mark.parametrize("mode", ["secret_canary", "raise_secret"])
def test_raw_model_or_tool_canary_never_enters_checkpoint_or_error(mode):
    p, e, graph = setup()
    setattr(e, mode, True)
    with pytest.raises(PolicyDenied) as error:
        graph.invoke(new_run_state(CALLER, [FIRST, SECOND]), config(mode))
    assert "SENSITIVE_TOOL_RESPONSE_CANARY" not in str(error.value)
    assert "SENSITIVE_TOOL_RESPONSE_CANARY" not in str(graph.get_state(config(mode)).values)


def test_no_missing_host_adapter_can_install_allow_all_defaults():
    with pytest.raises(ValueError, match="Host policy"):
        build_graph(None, ReadOnlyExecutorFake(), MemorySaver())
    with pytest.raises(ValueError, match="Host policy"):
        build_graph(HostPolicyFake(), None, MemorySaver())
    with pytest.raises(ValueError, match="Host policy"):
        build_graph(HostPolicyFake(), ReadOnlyExecutorFake(), None)
    with pytest.raises(ValueError, match="authenticator"):
        create_app(build_graph(HostPolicyFake(), ReadOnlyExecutorFake(), MemorySaver()), None)


class TestAuthenticator:
    def identify(self, request):
        if request.headers.get("X-Test-Identity") == "owner":
            return CALLER
        if request.headers.get("X-Test-Identity") == "intruder":
            return Caller("tenant.other", "user.other", CALLER.active_pet)
        return None


def test_fastapi_host_identity_and_checkpoint_bound_review():
    p, e, graph = setup()
    app = create_app(graph, TestAuthenticator())
    client = TestClient(app)
    def canonical(h, depth):
        now = datetime.now(timezone.utc)
        request = {
            "schemaVersion": "pet-collaboration.v1", "kind": "request",
            "requestId": h.request_id, "conversationId": "conversation.demo",
            "tenantId": CALLER.tenant_id, "actorPetId": h.from_pet,
            "recipientPetId": h.to_pet, "capabilityId": h.capability_id,
            "authorityRef": h.authority_ref, "sourceSha": h.source_sha,
            "requestedEffect": "read",
            "createdAt": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "expiresAt": (now + timedelta(minutes=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "depth": depth,
            "context": {
                "ref": h.context_ref, "digest": "sha256:" + h.context_sha256,
                "dataClass": h.data_class
            },
            "budget": {"maxTokens": 500, "maxDepth": 2},
        }
        if depth:
            request["parentRequestId"] = FIRST.request_id
        return request
    body = {"requests": [canonical(FIRST, 0), canonical(SECOND, 1)]}
    assert client.post("/runs", json=body).status_code == 401
    created = client.post("/runs", json=body, headers={"X-Test-Identity": "owner"})
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["status"] == "awaiting_review"
    assert data["checkpoint_id"]
    run_id = data["id"]

    assert client.get(f"/runs/{run_id}", headers={"X-Test-Identity": "intruder"}).status_code == 404
    assert client.post(f"/runs/{run_id}/review", json={
        "action": "approve", "checkpoint_id": "old-checkpoint"
    }, headers={"X-Test-Identity": "owner"}).status_code == 409

    final = client.post(f"/runs/{run_id}/review", json={
        "action": "approve", "checkpoint_id": data["checkpoint_id"]
    }, headers={"X-Test-Identity": "owner"})
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "completed"
    assert final.json()["review_status"] == "approved"
    assert len(e.calls) == 2
