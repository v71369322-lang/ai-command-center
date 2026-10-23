import hmac
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .store import Denied, Store
from .worker import broker


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["render", "approved_render"] = "render"
    values: dict[str, str] = Field(min_length=1, max_length=16)
    cost: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    dependency: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")

    @field_validator("values")
    @classmethod
    def bounded_values(cls, values):
        for key, value in values.items():
            if not re.fullmatch(r"[a-zA-Z0-9_]{1,32}", key) or len(value) > 128 or "\n" in value or "\r" in value:
                raise ValueError("bounded single-line synthetic values required")
        return values


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    epoch: int = Field(ge=1, strict=True)
    checkpoint_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, strict=True)
    seconds: int = Field(default=120, ge=1, le=300, strict=True)


def create_app(settings=None):
    settings = settings or Settings.load()
    store = Store(settings)
    queue = broker(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.engine.dispose()
        queue.close()

    app = FastAPI(title="AI Command Center — synthetic F1", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.store = store

    def record_denial(request, reason):
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        actor = next((r for r, token in settings.identities.items() if hmac.compare_digest(supplied, token)), "unauthenticated")
        try:
            with store.transaction() as session:
                store.audit(session, "request_denied", actor, reason=reason)
        except Exception:
            pass  # No authority is granted when durable logging is unavailable.

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        from fastapi.responses import JSONResponse
        if error.status_code in {401, 403, 404}:
            record_denial(request, "http_" + str(error.status_code))
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @app.exception_handler(Denied)
    async def denied_handler(request, error):
        from fastapi.responses import JSONResponse
        record_denial(request, str(error))
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"detail": "database_unavailable"})

    @app.middleware("http")
    async def security_headers(request, call_next):
        size = request.headers.get("content-length")
        if size and (not size.isdigit() or int(size) > 8192):
            return Response(status_code=413)
        # Bound streamed/chunked inputs as well, before Pydantic parses JSON.
        if request.method in {"POST", "PUT", "PATCH"}:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 8192:
                    return Response(status_code=413)
            request._body = bytes(data)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def identity(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "authentication_required")
        token = authorization[7:]
        for role, expected in settings.identities.items():
            if hmac.compare_digest(token, expected):
                return role
        raise HTTPException(401, "invalid_identity")

    def human(role=Depends(identity)):
        if role == "agent":
            raise HTTPException(403, "role_forbidden")
        return role

    @app.get("/api/state")
    def state(role=Depends(human)):
        return store.snapshot()

    @app.get("/api/health")
    def health(role=Depends(human)):
        result = {"postgres": "unknown", "redis": "unknown", "executor": "unknown",
                  "synthetic": True, "revision": settings.source_revision}
        try:
            snapshot = store.snapshot()
            result["postgres"] = "healthy"
            result["control"] = "paused" if snapshot["halted"] or snapshot["recovery"] else "healthy"
        except Exception:
            result["postgres"] = "failed"
        try:
            queue.ping()
            result["redis"] = "healthy"
        except Exception:
            result["redis"] = "failed"
        return result

    @app.post("/api/simulator/commands", status_code=201)
    def create(command: Command, role=Depends(identity), idempotency_key: str = Header(..., max_length=100, min_length=1)):
        return store.create(role, idempotency_key, command.model_dump())

    @app.post("/api/tasks/{task_id}/approve")
    def approve(task_id: str, approval: ApprovalRequest, role=Depends(identity)):
        return store.approve(role, task_id, approval.version, approval.seconds)

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str, role=Depends(identity)):
        return store.cancel(role, task_id)

    @app.post("/api/tasks/{task_id}/revoke")
    def revoke(task_id: str, role=Depends(identity)):
        return store.cancel(role, task_id, revoke=True)

    @app.post("/api/tasks/{task_id}/retry")
    def retry(task_id: str, role=Depends(identity)):
        return store.retry(role, task_id)

    @app.post("/api/control/stop")
    def stop(role=Depends(identity)):
        store.halt(role)
        return {"halted": True}

    @app.post("/api/control/resume")
    def resume(request: ResumeRequest, role=Depends(identity)):
        store.resume(role, request.epoch, request.checkpoint_digest)
        return {"halted": False}

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api(path: str):
        raise HTTPException(404, "unknown_action")

    dist = Path("web/dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
