"""Bounded LangGraph pet-to-pet workflow, with host-owned per-step authorization.

Design adapted from MIT-licensed carabaestlein/aiven-prototype-agent:
workflow.py @ db5755c00080aff6fa0e7aee76685d6f42de265d.
No Chibi authority or provider credentials are implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,99}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PolicyDenied(Exception):
    """A host decision is missing, expired, mismatched or explicitly denied."""


class InvalidRun(ValueError):
    """Invalid source-independent public run contract."""


def _id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


@dataclass(frozen=True)
class Caller:
    tenant_id: str
    user_id: str
    active_pet: str


@dataclass(frozen=True)
class Handoff:
    request_id: str
    from_pet: str
    to_pet: str
    capability_id: str
    context_sha256: str
    data_class: str
    authority_ref: str
    context_ref: str
    source_sha: str


@dataclass(frozen=True)
class Decision:
    # Returned by the trusted Chibi host adapter, not a model/HTTP body.
    allowed: bool
    decision_id: str
    tenant_id: str
    user_id: str
    request_id: str
    from_pet: str
    to_pet: str
    capability_id: str
    context_sha256: str
    data_class: str
    authority_ref: str
    context_ref: str
    source_sha: str
    expires_at: datetime
    allows_external_effects: bool = False


class HostPolicy(Protocol):
    def decide(self, caller: Caller, handoff: Handoff) -> Decision | None:
        """Re-check Cedar/consent/installation *now*; absence means deny."""


class PetExecutor(Protocol):
    def invoke(self, caller: Caller, handoff: Handoff, decision: Decision) -> dict:
        """Host-injected, read-only operation; never accepts a model-issued grant."""


class CouncilState(TypedDict, total=False):
    caller: dict
    handoffs: list[dict]
    results: list[dict]
    review_status: str


def _validate_caller(caller: Caller) -> None:
    if not all(_id(x) for x in (caller.tenant_id, caller.user_id, caller.active_pet)):
        raise InvalidRun("Invalid host-supplied caller identity")


def _validate_handoff(handoff: Handoff) -> None:
    if not all(_id(x) for x in (
        handoff.request_id, handoff.from_pet, handoff.to_pet, handoff.capability_id,
        handoff.authority_ref, handoff.context_ref
    )):
        raise InvalidRun("Invalid handoff identity")
    if handoff.from_pet == handoff.to_pet:
        raise InvalidRun("Self-delegation is prohibited")
    if not isinstance(handoff.context_sha256, str) or not _SHA256.fullmatch(handoff.context_sha256):
        raise InvalidRun("Context requires SHA-256 digest, never raw private memory")
    if not isinstance(handoff.source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", handoff.source_sha):
        raise InvalidRun("Source requires exact 40-character commit SHA")
    if handoff.data_class not in ("synthetic", "public"):
        raise InvalidRun("Data class is not host-approved")


def new_run_state(caller: Caller, handoffs: list[Handoff]) -> CouncilState:
    """Only call with an identity already resolved by the host authenticator.

    Bounded to two handoffs. Enforces an explicit A -> B -> C chain:
    the second source must equal the first recipient. The host policy still
    independently authorizes the second pet acting as a delegator.
    """
    _validate_caller(caller)
    if len(handoffs) != 2 or not all(isinstance(h, Handoff) for h in handoffs):
        raise InvalidRun("Exactly two handoffs are required")
    for h in handoffs:
        _validate_handoff(h)
    first, second = handoffs
    if first.from_pet != caller.active_pet or second.from_pet != first.to_pet:
        raise InvalidRun("Handoff chain does not match host-selected pet")
    if len({first.request_id, second.request_id}) != 2:
        raise InvalidRun("Replayed handoff request identifier")
    if first.context_sha256 != second.context_sha256:
        raise InvalidRun("Unapproved context change across handoffs")
    if first.source_sha != second.source_sha:
        raise InvalidRun("Cross-source pet handoff is prohibited")
    return {
        "caller": vars(caller).copy(),
        "handoffs": [vars(h).copy() for h in handoffs],
        "results": [],
        "review_status": "not-reviewed",
    }


def _require_current_decision(caller: Caller, handoff: Handoff, value: object) -> Decision:
    if not isinstance(value, Decision) or value.allowed is not True:
        raise PolicyDenied("Chibi host authorization missing or denied")
    fields = (
        (value.tenant_id, caller.tenant_id),
        (value.user_id, caller.user_id),
        (value.request_id, handoff.request_id),
        (value.from_pet, handoff.from_pet),
        (value.to_pet, handoff.to_pet),
        (value.capability_id, handoff.capability_id),
        (value.context_sha256, handoff.context_sha256),
        (value.data_class, handoff.data_class),
        (value.authority_ref, handoff.authority_ref),
        (value.context_ref, handoff.context_ref),
        (value.source_sha, handoff.source_sha),
    )
    if any(actual != expected for actual, expected in fields):
        raise PolicyDenied("Host decision does not bind the exact requested scope")
    if not _id(value.decision_id):
        raise PolicyDenied("Host decision identifier missing")
    if value.allows_external_effects is not False:
        raise PolicyDenied("This Council slice cannot perform external writes")
    if not isinstance(value.expires_at, datetime) or value.expires_at.tzinfo is None:
        raise PolicyDenied("Host decision has no valid absolute expiry")
    if value.expires_at <= datetime.now(timezone.utc):
        raise PolicyDenied("Host decision is expired")
    return value


def _bounded_receipt(handoff: Handoff, decision: Decision, value: object) -> dict:
    # Only opaque host-private artifact references and SHA digests may enter a
    # checkpoint or owner API. Raw model/tool content must remain in Chibi storage.
    if not isinstance(value, dict) or set(value) != {
        "kind", "artifact_ref", "output_digest", "provider_receipt_ref",
        "source_sha", "external_effects"
    }:
        raise PolicyDenied("Invalid metadata-only host executor receipt")
    if value["kind"] != "read-only" or value["external_effects"] is not False:
        raise PolicyDenied("Host executor reported an unapproved effect")
    if not _id(value["artifact_ref"]):
        raise PolicyDenied("Missing opaque host artifact reference")
    if not isinstance(value["output_digest"], str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", value["output_digest"]
    ):
        raise PolicyDenied("Missing exact output digest")
    if value["provider_receipt_ref"] is not None and not _id(value["provider_receipt_ref"]):
        raise PolicyDenied("Invalid opaque provider receipt reference")
    if value["source_sha"] != decision.source_sha or value["source_sha"] != handoff.source_sha:
        raise PolicyDenied("Host receipt source is not the authorized commit")
    return {
        "request_id": handoff.request_id,
        "from_pet": handoff.from_pet,
        "to_pet": handoff.to_pet,
        "capability_id": handoff.capability_id,
        "context_sha256": handoff.context_sha256,
        "source_sha": handoff.source_sha,
        "host_decision_id": decision.decision_id,
        "execution": value.copy(),
    }


def build_graph(policy: HostPolicy, executor: PetExecutor, checkpointer):
    """Compile an explicit, checkpointed two-pet LangGraph execution.

    The graph intentionally has no built-in allow-all policy, bearer-grant
    parsing, model client or tool transport.
    """
    if policy is None or executor is None or checkpointer is None:
        raise ValueError("Host policy, executor and checkpointer are all required")

    def delegate_at(index: int):
        def node(state: CouncilState) -> dict:
            caller = Caller(**state["caller"])
            handoff = Handoff(**state["handoffs"][index])
            _validate_caller(caller)
            _validate_handoff(handoff)
            if any(r["request_id"] == handoff.request_id for r in state.get("results", [])):
                return {"results": state["results"]}
            # Re-check immediately before each separately scoped executor call.
            # Never let raw policy/provider exception messages reach API/logs.
            try:
                raw_decision = policy.decide(caller, handoff)
            except Exception:
                raise PolicyDenied("Chibi host policy unavailable") from None
            decision = _require_current_decision(caller, handoff, raw_decision)
            try:
                result = executor.invoke(caller, handoff, decision)
            except Exception:
                raise PolicyDenied("Chibi host executor failed") from None
            receipt = _bounded_receipt(handoff, decision, result)
            return {"results": [*state.get("results", []), receipt]}
        return node

    def human_review(state: CouncilState) -> dict:
        # No side effects before interrupt: LangGraph will re-enter on resume.
        answer = interrupt({
            "kind": "proposal-review",
            "pet_request_ids": [r["request_id"] for r in state.get("results", [])],
            "note": "Reviewing results never grants provider write permissions.",
        })
        if not isinstance(answer, dict) or answer.get("action") not in ("approve", "reject"):
            raise PolicyDenied("Unrecognized human review decision")
        if set(answer) != {"action"}:
            raise PolicyDenied("Unexpected review payload fields")
        return {"review_status": "approved" if answer["action"] == "approve" else "rejected"}

    graph = StateGraph(CouncilState)
    graph.add_node("first_handoff", delegate_at(0))
    graph.add_node("second_handoff", delegate_at(1))
    graph.add_node("human_review", human_review)
    graph.add_edge(START, "first_handoff")
    graph.add_edge("first_handoff", "second_handoff")
    graph.add_edge("second_handoff", "human_review")
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)
