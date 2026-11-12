"""Fail-closed boundary for the monorepo's canonical v1 request envelope.

Canonical schema owner: contracts/pet-collaboration/v1/request.schema.json.
This is an extra runtime validation layer, NOT a replacement for Cedar/PEP
or cryptographic validation of authorityRef.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from .core import Caller, Handoff, InvalidRun


_ID = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,99}$")
_DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")
_SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,3})?Z$")
_FIELDS = {
    "schemaVersion", "kind", "requestId", "conversationId", "parentRequestId",
    "tenantId", "actorPetId", "recipientPetId", "capabilityId", "authorityRef", "sourceSha",
    "requestedEffect", "createdAt", "expiresAt", "depth", "context", "budget",
}
_CONTEXT_FIELDS = {"ref", "digest", "dataClass"}
_BUDGET_FIELDS = {"maxTokens", "maxDepth"}


def _id(value):
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _time(value, label):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise InvalidRun(f"{label} must be canonical UTC with millisecond precision")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidRun(f"{label} must be a valid UTC timestamp") from None
    return result.astimezone(timezone.utc)


def _decode(request: object, caller: Caller, index: int, now: datetime) -> tuple[Handoff, str, str | None]:
    if not isinstance(request, dict) or set(request) - _FIELDS:
        raise InvalidRun("Unknown or invalid canonical request fields")
    required = _FIELDS - {"parentRequestId"}
    if not required.issubset(request):
        raise InvalidRun("Required canonical request fields missing")
    if request["schemaVersion"] != "pet-collaboration.v1" or request["kind"] != "request":
        raise InvalidRun("Unsupported canonical request version")
    if not isinstance(request["sourceSha"], str) or not _SOURCE_SHA.fullmatch(request["sourceSha"]):
        raise InvalidRun("Request source requires exact 40-character commit SHA")
    if request["requestedEffect"] != "read":
        raise InvalidRun("Council executor accepts only read-only requests")
    if request["tenantId"] != caller.tenant_id:
        raise InvalidRun("Host tenant disagrees with canonical request")
    for field in ("requestId", "conversationId", "actorPetId", "recipientPetId",
                  "capabilityId", "authorityRef"):
        if not _id(request[field]):
            raise InvalidRun(f"Invalid canonical {field}")
    if "parentRequestId" in request and not _id(request["parentRequestId"]):
        raise InvalidRun("Invalid canonical parentRequestId")
    if type(request["depth"]) is not int or request["depth"] != index:
        raise InvalidRun("Invalid delegation depth")
    context = request["context"]
    if not isinstance(context, dict) or set(context) != _CONTEXT_FIELDS:
        raise InvalidRun("Invalid canonical scoped context")
    if not _id(context["ref"]):
        raise InvalidRun("Context requires opaque host reference")
    digest = context["digest"]
    match = _DIGEST.fullmatch(digest) if isinstance(digest, str) else None
    if match is None:
        raise InvalidRun("Context digest must be prefixed SHA-256")
    # The real host must explicitly authorize private context access separately.
    if context["dataClass"] not in ("synthetic", "public"):
        raise InvalidRun("Private context requires a Chibi host integration")
    budget = request["budget"]
    if not isinstance(budget, dict) or set(budget) != _BUDGET_FIELDS:
        raise InvalidRun("Invalid bounded task budget")
    if (type(budget["maxTokens"]) is not int or not 1 <= budget["maxTokens"] <= 4096
            or type(budget["maxDepth"]) is not int or not 0 <= budget["maxDepth"] <= 2):
        raise InvalidRun("Task budget exceeds Council pilot limits")
    created = _time(request["createdAt"], "createdAt")
    expires = _time(request["expiresAt"], "expiresAt")
    if created > now + timedelta(seconds=30) or created < now - timedelta(hours=1):
        raise InvalidRun("Stale or future request")
    if not created <= expires or not now < expires <= created + timedelta(minutes=5):
        raise InvalidRun("Expired or excessive request lifetime")
    return Handoff(
        request_id=request["requestId"],
        from_pet=request["actorPetId"],
        to_pet=request["recipientPetId"],
        capability_id=request["capabilityId"],
        context_sha256=match.group(1),
        data_class=context["dataClass"],
        authority_ref=request["authorityRef"],
        context_ref=context["ref"],
        source_sha=request["sourceSha"],
    ), request["conversationId"], request.get("parentRequestId")


def handoffs_from_v1(caller: Caller, requests: list[dict], *, now: datetime | None = None) -> list[Handoff]:
    """Check the portable envelope before passing to host authorization.

    authorityRef and sourceSha are **not** authenticated by their presence in
    JSON. Only the injected Chibi host may verify the exact canonical source
    commit, signed authority, adoption and current policy. The host decision
    must bind the same sourceSha before execution.
    """
    if not isinstance(requests, list) or len(requests) != 2:
        raise InvalidRun("Exactly two canonical requests are required")
    current = now or datetime.now(timezone.utc)
    first, conversation_a, parent_a = _decode(requests[0], caller, 0, current)
    second, conversation_b, parent_b = _decode(requests[1], caller, 1, current)
    if conversation_a != conversation_b:
        raise InvalidRun("Cross-conversation delegation denied")
    if parent_a is not None or parent_b != first.request_id:
        raise InvalidRun("Missing or mismatched parent request")
    if second.context_sha256 != first.context_sha256 or second.context_ref != first.context_ref:
        raise InvalidRun("Unapproved cross-pet context change")
    if second.source_sha != first.source_sha:
        raise InvalidRun("Mixed source commits across the Council run are denied")
    return [first, second]
