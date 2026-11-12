"""Authenticated FastAPI adapter with mandatory host-atomic replay reservation."""
from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from .bridge import handoffs_from_v1
from .core import Caller, InvalidRun, PolicyDenied, new_run_state
from .replay import ReplayConflict, ReplayStore, deterministic_run_id, envelope_sha256, valid_reservation


class Authenticator(Protocol):
    def identify(self, request: Request) -> Caller | None:
        """Resolve a verified host-side account, tenant and active pet."""


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requests: list[dict]


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    checkpoint_id: str
    action: Literal["approve", "reject"]


def _thread(run_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(run_id)}, "recursion_limit": 10}


def _project(snapshot) -> dict:
    values = dict(snapshot.values or {})
    if not values:
        raise HTTPException(404, "Run not found")
    pending_review = any(task.interrupts for task in snapshot.tasks)
    status = (
        "awaiting_review" if pending_review
        else "completed" if values.get("review_status") in ("approved", "rejected")
        else "needs_continue"
    )
    return {
        "status": status,
        "review_status": values.get("review_status", "not-reviewed"),
        "results": values.get("results", []),
        "checkpoint_id": (snapshot.config or {}).get("configurable", {}).get("checkpoint_id"),
    }


def create_app(graph, authenticator: Authenticator, replay_store: ReplayStore | None = None) -> FastAPI:
    """Production host MUST inject durable atomic ReplayStore and fence verifier.

    No anonymous identity, replay fallback, grant or model adapter is installed.
    """
    if graph is None or authenticator is None or replay_store is None:
        raise ValueError("Council graph, verified host authenticator and durable ReplayStore are required")
    app = FastAPI(title="Chibi Council (host-integrated only)", version="0.2.0")

    def identity(request: Request) -> Caller:
        try:
            caller = authenticator.identify(request)
        except Exception:
            raise HTTPException(401, "Host authentication required") from None
        if caller is None or not isinstance(caller, Caller):
            raise HTTPException(401, "Host authentication required")
        return caller

    def owned_run(run_id: UUID, caller: Caller):
        snapshot = graph.get_state(_thread(run_id))
        values = dict(snapshot.values or {})
        if values.get("caller") != vars(caller):
            raise HTTPException(404, "Run not found")
        return snapshot

    @app.get("/health/live")
    def live():
        return {"status": "ok", "host_authorization": "injected-required",
                "replay_reservation": "durable-host-required"}

    @app.post("/runs", status_code=201)
    def create_run(body: StartInput, request: Request):
        caller = identity(request)
        try:
            handoffs = handoffs_from_v1(caller, body.requests)
            digest = envelope_sha256(body.requests)
            handoffs_digest = envelope_sha256([vars(h) for h in handoffs])
        except (InvalidRun, ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from None
        expected_run_id = deterministic_run_id(caller, handoffs[0].request_id)
        # Atomic claim happens before any provider invocation. The host store
        # permanently keys (tenant,user,firstRequestId) to one exact payload.
        try:
            reservation = replay_store.reserve(caller, handoffs[0].request_id,
                                               digest, expected_run_id, handoffs_digest)
        except ReplayConflict:
            raise HTTPException(409, "Request ID reused with a different envelope") from None
        except Exception:
            raise HTTPException(503, "Durable Chibi replay reservation unavailable") from None
        if not valid_reservation(reservation, caller, handoffs[0].request_id,
                                 digest, handoffs_digest):
            raise HTTPException(503, "Host returned an invalid durable replay reservation")

        if not reservation.created:
            # A replay must NEVER invoke the graph again. If the first worker
            # has not checkpointed yet, expose its reservation ID as pending.
            try:
                snapshot = graph.get_state(_thread(expected_run_id))
                if not snapshot.values:
                    return JSONResponse(status_code=200, content={
                        "id": str(expected_run_id), "status": "reserved",
                        "review_status": "not-reviewed", "results": [],
                        "checkpoint_id": None,
                    })
                if snapshot.values.get("caller") != vars(caller):
                    raise HTTPException(404, "Run not found")
                return JSONResponse(status_code=200, content={
                    "id": str(expected_run_id), **_project(snapshot),
                })
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(503, "Checkpoint read unavailable") from None

        try:
            state = new_run_state(caller, handoffs, reservation)
            graph.invoke(state, config=_thread(expected_run_id))
            result = {"id": str(expected_run_id), **_project(graph.get_state(_thread(expected_run_id)))}
        except (InvalidRun, PolicyDenied):
            # The durable reservation remains held even when execution fails.
            # Never blindly call the provider again on duplicate POST.
            raise HTTPException(403, "Chibi host execution denied") from None
        except Exception:
            raise HTTPException(503, "Chibi Council execution unavailable") from None
        return result

    @app.get("/runs/{run_id}")
    def read_run(run_id: UUID, request: Request):
        caller = identity(request)
        return {"id": str(run_id), **_project(owned_run(run_id, caller))}

    @app.post("/runs/{run_id}/review")
    def review_run(run_id: UUID, body: ReviewInput, request: Request):
        caller = identity(request)
        snapshot = owned_run(run_id, caller)
        current = _project(snapshot)
        if current["status"] != "awaiting_review":
            raise HTTPException(409, "Run is not awaiting review")
        if not body.checkpoint_id or body.checkpoint_id != current["checkpoint_id"]:
            raise HTTPException(409, "Stale review: refresh checkpoint")
        try:
            graph.invoke(Command(resume={"action": body.action}), config=_thread(run_id))
        except PolicyDenied:
            raise HTTPException(403, "Review rejected") from None
        except Exception:
            raise HTTPException(503, "Chibi Council review unavailable") from None
        return {"id": str(run_id), **_project(graph.get_state(_thread(run_id)))}

    return app
