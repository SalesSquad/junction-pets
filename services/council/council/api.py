"""Authenticated FastAPI adapter. The Chibi host must inject identity resolution."""
from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from .bridge import handoffs_from_v1
from .core import Caller, InvalidRun, PolicyDenied, new_run_state


class Authenticator(Protocol):
    def identify(self, request: Request) -> Caller | None:
        """Resolve a verified host-side account, tenant and active pet."""


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Exact canonical request objects; shape and host identity are checked by bridge.
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


def create_app(graph, authenticator: Authenticator) -> FastAPI:
    """No default authentication, policy or model adapter is ever installed."""
    if graph is None or authenticator is None:
        raise ValueError("Council graph and verified host authenticator are required")
    app = FastAPI(title="Chibi Council (host-integrated only)", version="0.1.0")

    def identity(request: Request) -> Caller:
        try:
            caller = authenticator.identify(request)
        except Exception:
            # No raw auth/session exception details leave the host.
            raise HTTPException(401, "Host authentication required") from None
        if caller is None or not isinstance(caller, Caller):
            raise HTTPException(401, "Host authentication required")
        return caller

    def owned_run(run_id: UUID, caller: Caller):
        snapshot = graph.get_state(_thread(run_id))
        values = dict(snapshot.values or {})
        # Do not reveal to another tenant/user whether the run exists.
        if values.get("caller") != vars(caller):
            raise HTTPException(404, "Run not found")
        return snapshot

    @app.get("/health/live")
    def live():
        return {"status": "ok", "host_authorization": "injected-required"}

    @app.post("/runs", status_code=201)
    def create_run(body: StartInput, request: Request):
        caller = identity(request)
        try:
            handoffs = handoffs_from_v1(caller, body.requests)
            state = new_run_state(caller, handoffs)
        except InvalidRun as exc:
            raise HTTPException(422, str(exc)) from None
        run_id = uuid4()
        try:
            graph.invoke(state, config=_thread(run_id))
        except PolicyDenied:
            raise HTTPException(403, "Chibi host authorization denied") from None
        return {"id": str(run_id), **_project(graph.get_state(_thread(run_id)))}

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
        return {"id": str(run_id), **_project(graph.get_state(_thread(run_id)))}

    return app
