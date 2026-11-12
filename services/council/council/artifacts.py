"""Host-private, metadata-only parent-result handoff for a second Council pet.

Council never reads or checkpoints the underlying artifact. The injected Chibi
host must authenticate the producer receipt against its durable artifact store,
re-check consumer authorization/revocation and re-authorize the artifact on
*every* read. The returned binding is not a bearer grant or signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from .core import Caller, Decision, Handoff
    from .replay import ReplayReservation


_REF = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,99}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ParentArtifactAccess:
    """Trusted host projection: exact producer, consumer, fence and TTL binding.

    A host executor MUST verify this against its own private store immediately
    before resolving the artifact; passing these bytes is never authorization.
    """
    artifact_ref: str
    output_digest: str
    parent_request_id: str
    child_request_id: str
    parent_decision_id: str
    child_decision_id: str
    tenant_id: str
    user_id: str
    run_id: UUID
    fence_token: int
    source_sha: str
    conversation_id: str
    context_ref: str
    context_sha256: str
    data_class: str
    max_tokens: int
    expires_at: datetime


class HostArtifactStore(Protocol):
    def authorize_parent_read(
        self, caller: Caller, parent: Handoff, parent_receipt: dict,
        child: Handoff, child_decision: Decision, reservation: ReplayReservation,
    ) -> ParentArtifactAccess | None:
        """Verify artifact is a durable, completed host output of this parent.

        Must cross-check the signed producer receipt, authenticated tenant/user,
        current consumer grant and fence, then issue an expiring read binding.
        Return only metadata; never raw content, credentials or memory.
        """


def require_parent_receipt(parent: Handoff, child: Handoff,
                           results: object) -> dict:
    """Reject forged, reordered or partial checkpoint metadata before host lookup."""
    from .core import PolicyDenied
    if (child.parent_request_id != parent.request_id or
            child.from_pet != parent.to_pet or
            child.conversation_id != parent.conversation_id or
            child.source_sha != parent.source_sha or
            child.context_ref != parent.context_ref or
            child.context_sha256 != parent.context_sha256 or
            child.depth != parent.depth + 1 or
            child.depth > parent.max_depth):
        raise PolicyDenied("Parent handoff chain changed")
    if not isinstance(results, list) or len(results) != 1:
        raise PolicyDenied("Exactly one completed parent receipt required")
    receipt = results[0]
    fields = {
        "request_id": parent.request_id, "from_pet": parent.from_pet,
        "to_pet": parent.to_pet, "capability_id": parent.capability_id,
        "context_sha256": parent.context_sha256, "source_sha": parent.source_sha,
    }
    if (not isinstance(receipt, dict) or
            set(receipt) != set(fields) | {"host_decision_id", "execution"} or
            any(receipt.get(k) != v for k, v in fields.items()) or
            not isinstance(receipt.get("host_decision_id"), str) or
            not _REF.fullmatch(receipt["host_decision_id"])):
        raise PolicyDenied("Missing or mismatched completed parent receipt")
    execution = receipt["execution"]
    if (not isinstance(execution, dict) or
            set(execution) != {"kind", "artifact_ref", "output_digest",
                               "provider_receipt_ref", "source_sha",
                               "external_effects", "tokens_used"} or
            execution["kind"] != "read-only" or
            execution["external_effects"] is not False or
            not isinstance(execution["artifact_ref"], str) or
            not _REF.fullmatch(execution["artifact_ref"]) or
            not isinstance(execution["output_digest"], str) or
            not _DIGEST.fullmatch(execution["output_digest"]) or
            (execution["provider_receipt_ref"] is not None and
             (not isinstance(execution["provider_receipt_ref"], str) or
              not _REF.fullmatch(execution["provider_receipt_ref"]))) or
            (parent.data_class != "synthetic" and
             execution["provider_receipt_ref"] is None) or
            execution["source_sha"] != parent.source_sha or
            type(execution["tokens_used"]) is not int or
            not 0 <= execution["tokens_used"] <= parent.max_tokens):
        raise PolicyDenied("Invalid completed parent artifact metadata")
    return receipt


def require_parent_access(
    caller: Caller, parent: Handoff, parent_receipt: dict,
    child: Handoff, decision: Decision, reservation: ReplayReservation,
    access: object, now: datetime,
) -> ParentArtifactAccess:
    """Validate a host-issued binding; reject stale, wider or forged metadata."""
    from .core import PolicyDenied, _utc
    if not isinstance(access, ParentArtifactAccess):
        raise PolicyDenied("Trusted parent artifact authorization unavailable")
    fields = (
        (access.artifact_ref, parent_receipt["execution"]["artifact_ref"]),
        (access.output_digest, parent_receipt["execution"]["output_digest"]),
        (access.parent_request_id, parent.request_id),
        (access.child_request_id, child.request_id),
        (access.parent_decision_id, parent_receipt["host_decision_id"]),
        (access.child_decision_id, decision.decision_id),
        (access.tenant_id, caller.tenant_id), (access.user_id, caller.user_id),
        (access.run_id, reservation.run_id),
        (access.fence_token, reservation.fence_token),
        (access.source_sha, decision.source_sha),
        (access.conversation_id, child.conversation_id),
        (access.context_ref, child.context_ref),
        (access.context_sha256, child.context_sha256),
        (access.data_class, child.data_class),
        (access.max_tokens, child.max_tokens),
    )
    if any(actual != expected for actual, expected in fields):
        raise PolicyDenied("Parent artifact grant does not bind exact host scope")
    if (not isinstance(access.expires_at, datetime) or
            access.expires_at.tzinfo is None or
            access.expires_at <= now or
            access.expires_at > decision.expires_at or
            access.expires_at > _utc(parent.expires_at) or
            access.expires_at > _utc(child.expires_at)):
        raise PolicyDenied("Parent artifact grant expired or exceeds delegated TTL")
    return access
