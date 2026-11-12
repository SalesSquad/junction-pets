"""Bounded LangGraph pet-to-pet workflow, with host-owned per-step authorization.

Design adapted from MIT-licensed carabaestlein/aiven-prototype-agent:
workflow.py @ db5755c00080aff6fa0e7aee76685d6f42de265d.
No Chibi authority or provider credentials are implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Callable, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .artifacts import (
    HostArtifactStore, ParentArtifactAccess, require_parent_access,
    require_parent_receipt,
)


_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,99}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,3})?Z$")


class PolicyDenied(Exception):
    """A current trusted Chibi decision/fence is missing, stale or mismatched."""


class InvalidRun(ValueError):
    """Invalid source-independent public run contract."""


def _id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise InvalidRun("Timestamp must be canonical UTC Z with <=3 fractional digits")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidRun("Invalid UTC timestamp") from None


def _now(clock: Callable[[], datetime]) -> datetime:
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError()
        return value.astimezone(timezone.utc)
    except Exception:
        raise PolicyDenied("Host clock unavailable") from None


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
    conversation_id: str
    parent_request_id: str | None
    depth: int
    max_depth: int
    max_tokens: int
    requested_effect: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class Decision:
    # All fields returned by the trusted Chibi host, not a model/HTTP body.
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
    conversation_id: str
    parent_request_id: str | None
    depth: int
    max_depth: int
    max_tokens: int
    requested_effect: str
    created_at: str
    request_expires_at: str
    idempotency_key: str
    fence_token: int
    expires_at: datetime
    allows_external_effects: bool = False


class HostPolicy(Protocol):
    def decide(self, caller: Caller, handoff: Handoff, reservation) -> Decision | None:
        """Re-check consent/Cedar/source, including exact run fence, NOW."""


class PetExecutor(Protocol):
    def invoke(self, caller: Caller, handoff: Handoff, decision: Decision, reservation,
               *, prior_artifact: ParentArtifactAccess | None = None) -> dict:
        """Read-only execution; second pet resolves a host-verified parent artifact.

        The host executor rechecks fence, grant, tenancy and this artifact scope
        at the moment of reading it. Metadata is never a bearer authorization.
        """


class CouncilState(TypedDict, total=False):
    caller: dict
    handoffs: list[dict]
    reservation: dict
    results: list[dict]
    review_status: str


def _validate_caller(caller: Caller) -> None:
    if not all(_id(x) for x in (caller.tenant_id, caller.user_id, caller.active_pet)):
        raise InvalidRun("Invalid host-supplied caller identity")


def _validate_handoff(h: Handoff) -> None:
    if not all(_id(x) for x in (
        h.request_id, h.from_pet, h.to_pet, h.capability_id, h.authority_ref,
        h.context_ref, h.conversation_id
    )):
        raise InvalidRun("Invalid handoff identity")
    if h.parent_request_id is not None and not _id(h.parent_request_id):
        raise InvalidRun("Invalid parent request")
    if h.from_pet == h.to_pet:
        raise InvalidRun("Self-delegation is prohibited")
    if not isinstance(h.context_sha256, str) or not _SHA256.fullmatch(h.context_sha256):
        raise InvalidRun("Context requires SHA-256 digest, never raw private memory")
    if not isinstance(h.source_sha, str) or not _SHA40.fullmatch(h.source_sha):
        raise InvalidRun("Source requires exact 40-character commit SHA")
    if h.data_class not in ("synthetic", "public"):
        raise InvalidRun("Data class is not host-approved")
    if h.requested_effect != "read":
        raise InvalidRun("Council slice permits only read-only tasks")
    if (type(h.depth) is not int or type(h.max_depth) is not int
            or not 0 <= h.depth <= h.max_depth <= 2):
        raise InvalidRun("Delegation exceeds maxDepth")
    if type(h.max_tokens) is not int or not 1 <= h.max_tokens <= 4096:
        raise InvalidRun("Invalid bounded maxTokens")
    created, expires = _utc(h.created_at), _utc(h.expires_at)
    if expires <= created or expires > created + timedelta(minutes=5):
        raise InvalidRun("Handoff TTL exceeds five-minute contract")


def _require_fresh_request(h: Handoff, now: datetime) -> None:
    if _utc(h.created_at) > now + timedelta(seconds=30):
        raise PolicyDenied("Delegation timestamp is in the future")
    if now >= _utc(h.expires_at):
        raise PolicyDenied("Delegation TTL expired")


def new_run_state(caller: Caller, handoffs: list[Handoff], reservation, *,
                  now: datetime | None = None) -> CouncilState:
    """Validate the complete A -> B -> C chain and host replay reservation.

    The caller must already be authenticated; a client cannot supply a
    reservation. Its durability/fencing remains the responsibility of the
    injected host's atomic ReplayStore.
    """
    from .replay import ReplayReservation, valid_reservation
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
    if first.conversation_id != second.conversation_id:
        raise InvalidRun("Cross-conversation handoff denied")
    if first.depth != 0 or second.depth != 1 or first.parent_request_id is not None or second.parent_request_id != first.request_id:
        raise InvalidRun("Parent/depth scope mismatch")
    if first.max_depth < second.depth:
        raise InvalidRun("First pet has insufficient maxDepth for delegation")
    if first.context_sha256 != second.context_sha256 or first.context_ref != second.context_ref:
        raise InvalidRun("Unapproved context change across handoffs")
    if first.source_sha != second.source_sha:
        raise InvalidRun("Cross-source pet handoff is prohibited")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise InvalidRun("Current time must be timezone aware")
    for h in handoffs:
        if _utc(h.created_at) < current - timedelta(hours=1):
            raise InvalidRun("Stale request timestamp")
        try:
            _require_fresh_request(h, current)
        except PolicyDenied as exc:
            raise InvalidRun(str(exc)) from None
    if not isinstance(reservation, ReplayReservation) or not valid_reservation(
        reservation, caller, first.request_id, reservation.envelope_digest
    ) or reservation.created is not True:
        raise InvalidRun("Missing valid, durable host reservation")
    return {
        "caller": vars(caller).copy(),
        "handoffs": [vars(h).copy() for h in handoffs],
        "reservation": {
            "run_id": str(reservation.run_id),
            "envelope_digest": reservation.envelope_digest,
            "idempotency_key": reservation.idempotency_key,
            "fence_token": reservation.fence_token,
            "created": reservation.created,
            "durable": reservation.durable,
        },
        "results": [],
        "review_status": "not-reviewed",
    }


def _require_current_decision(caller: Caller, handoff: Handoff, reservation,
                              value: object, now: datetime) -> Decision:
    if not isinstance(value, Decision) or value.allowed is not True:
        raise PolicyDenied("Chibi host authorization missing or denied")
    fields = (
        (value.tenant_id, caller.tenant_id), (value.user_id, caller.user_id),
        (value.request_id, handoff.request_id),
        (value.from_pet, handoff.from_pet), (value.to_pet, handoff.to_pet),
        (value.capability_id, handoff.capability_id),
        (value.context_sha256, handoff.context_sha256),
        (value.data_class, handoff.data_class),
        (value.authority_ref, handoff.authority_ref),
        (value.context_ref, handoff.context_ref),
        (value.source_sha, handoff.source_sha),
        (value.conversation_id, handoff.conversation_id),
        (value.parent_request_id, handoff.parent_request_id),
        (value.depth, handoff.depth), (value.max_depth, handoff.max_depth),
        (value.max_tokens, handoff.max_tokens),
        (value.requested_effect, handoff.requested_effect),
        (value.created_at, handoff.created_at),
        (value.request_expires_at, handoff.expires_at),
        (value.idempotency_key, reservation.idempotency_key),
        (value.fence_token, reservation.fence_token),
    )
    if any(actual != expected for actual, expected in fields):
        raise PolicyDenied("Host decision does not bind the complete requested scope and fence")
    if not _id(value.decision_id):
        raise PolicyDenied("Host decision identifier missing")
    if value.allows_external_effects is not False:
        raise PolicyDenied("This Council slice cannot perform external writes")
    if not isinstance(value.expires_at, datetime) or value.expires_at.tzinfo is None:
        raise PolicyDenied("Host decision has no valid absolute expiry")
    if value.expires_at <= now or value.expires_at > _utc(handoff.expires_at):
        raise PolicyDenied("Host decision expired or exceeds request TTL")
    return value


def _bounded_receipt(handoff: Handoff, decision: Decision, value: object) -> dict:
    # Strict projection: no raw text/tool data ever enters checkpoint/API.
    if not isinstance(value, dict) or set(value) != {
        "kind", "artifact_ref", "output_digest", "provider_receipt_ref",
        "source_sha", "external_effects", "tokens_used"
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
    if handoff.data_class != "synthetic" and value["provider_receipt_ref"] is None:
        raise PolicyDenied("Live task needs a provider/tool receipt reference")
    if type(value["tokens_used"]) is not int or not 0 <= value["tokens_used"] <= handoff.max_tokens:
        raise PolicyDenied("Provider exceeded maxTokens or omitted usage")
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


def build_graph(policy: HostPolicy, executor: PetExecutor, checkpointer, replay_store,
                clock: Callable[[], datetime] | None = None, *,
                artifact_store: HostArtifactStore | None = None):
    """Compile checkpointed LangGraph; all sensitive adapters are host-injected."""
    if (policy is None or executor is None or checkpointer is None or
            replay_store is None or artifact_store is None):
        raise ValueError("Host policy, executor, checkpointer, durable ReplayStore and parent artifact store are all required")
    now_fn = clock or (lambda: datetime.now(timezone.utc))

    def delegate_at(index: int):
        def node(state: CouncilState) -> dict:
            from uuid import UUID
            from .replay import ReplayReservation, valid_reservation
            caller = Caller(**state["caller"])
            handoff = Handoff(**state["handoffs"][index])
            _validate_caller(caller)
            _validate_handoff(handoff)
            first_id = state["handoffs"][0]["request_id"]
            try:
                raw_fence = dict(state["reservation"])
                reservation = ReplayReservation(
                    run_id=UUID(raw_fence["run_id"]),
                    envelope_digest=raw_fence["envelope_digest"],
                    idempotency_key=raw_fence["idempotency_key"],
                    fence_token=raw_fence["fence_token"],
                    created=raw_fence["created"],
                    durable=raw_fence["durable"],
                )
            except Exception:
                raise PolicyDenied("Invalid checkpointed reservation") from None
            if not valid_reservation(reservation, caller, first_id, reservation.envelope_digest):
                raise PolicyDenied("Invalid checkpointed durable execution fence")
            if any(r["request_id"] == handoff.request_id for r in state.get("results", [])):
                return {"results": state["results"]}
            # Exact reservation must remain current before each invocation, on
            # every resume. Old leases never authorize calls after takeover.
            try:
                if replay_store.is_current(caller, reservation) is not True:
                    raise PolicyDenied("Host durable execution fence is stale")
            except PolicyDenied:
                raise
            except Exception:
                raise PolicyDenied("Host durable replay/fence verifier unavailable") from None
            now = _now(now_fn)
            _require_fresh_request(handoff, now)
            try:
                raw_decision = policy.decide(caller, handoff, reservation)
            except Exception:
                raise PolicyDenied("Chibi host policy unavailable") from None
            decision = _require_current_decision(caller, handoff, reservation, raw_decision, _now(now_fn))
            _require_fresh_request(handoff, _now(now_fn))
            prior_artifact = None
            if index == 1:
                # The sole allowable source is the completed parent's
                # metadata-only receipt. Never accept artifactRef from HTTP,
                # model output, or unchecked LangGraph checkpoint bytes.
                try:
                    parent = Handoff(**state["handoffs"][0])
                    _validate_handoff(parent)
                    receipt = require_parent_receipt(parent, handoff, state.get("results"))
                except (TypeError, ValueError, KeyError):
                    raise PolicyDenied("Invalid checkpointed parent handoff") from None
                try:
                    raw_access = artifact_store.authorize_parent_read(
                        caller, parent, receipt, handoff, decision, reservation
                    )
                except Exception:
                    raise PolicyDenied("Host parent artifact authorization unavailable") from None
                prior_artifact = require_parent_access(
                    caller, parent, receipt, handoff, decision, reservation,
                    raw_access, _now(now_fn)
                )
                # Lookup and consumption are separate host operations; close
                # their revocation/fence window here, and require the executor
                # to revalidate immediately at actual artifact read time.
                try:
                    if replay_store.is_current(caller, reservation) is not True:
                        raise PolicyDenied("Host durable execution fence is stale")
                    refreshed = policy.decide(caller, handoff, reservation)
                except PolicyDenied:
                    raise
                except Exception:
                    raise PolicyDenied("Chibi host policy/fence unavailable") from None
                decision = _require_current_decision(
                    caller, handoff, reservation, refreshed, _now(now_fn)
                )
                _require_fresh_request(handoff, _now(now_fn))
                require_parent_access(
                    caller, parent, receipt, handoff, decision, reservation,
                    prior_artifact, _now(now_fn)
                )
            try:
                if prior_artifact is None:
                    result = executor.invoke(caller, handoff, decision, reservation)
                else:
                    result = executor.invoke(
                        caller, handoff, decision, reservation,
                        prior_artifact=prior_artifact,
                    )
            except Exception:
                raise PolicyDenied("Chibi host executor failed") from None
            receipt = _bounded_receipt(handoff, decision, result)
            return {"results": [*state.get("results", []), receipt]}
        return node

    def human_review(state: CouncilState) -> dict:
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
