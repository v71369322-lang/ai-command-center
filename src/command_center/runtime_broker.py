"""Trusted typed runtime broker. Rootless required unless explicitly cloud-test."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request as HTTPRequest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .runtime_ledger import RuntimeLedger
from .runtime_policy import RuntimeBackend, RuntimeLimits
from .store import Denied, Store
from .worker import Runner, broker


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['submit', 'heartbeat', 'status', 'worker_online']
    task_id: UUID | None = None
    revision: str | None = Field(default=None, pattern='^[a-f0-9]{40}$')
    fence: int = Field(default=0, ge=0, strict=True)


class RuntimeBroker:
    def __init__(self, store, ledger, backend, limits=None):
        self.store, self.ledger, self.backend = store, ledger, backend
        self.limits = limits or RuntimeLimits()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.last_future = None

    def submit(self, task_id, revision):
        with self.lock:
            self.ledger.verify()
            if revision != self.store.settings.source_revision:
                raise Denied('broker_revision_mismatch')
            if not self.ledger.watchdog_ready(self.limits.watchdog_seconds):
                raise Denied('watchdog_unavailable')
            if self.ledger.runs():
                raise Denied('runtime_busy_or_uncertain')
            self.backend.preflight()
            task = self.store.claim(task_id)
            if not task:
                return {'phase': 'NOT_ADMITTED', 'fence': 0}
            task['revision'] = revision
            try:
                self.ledger.register(task, Runner.name(task), self.limits.wall_seconds)
            except Exception:
                self.store.abort(task_id, task['fence'], 'verified_no_effect', True)
                raise
            self.last_future = self.pool.submit(self.execute, task)
            return {'phase': 'INTENT', 'fence': task['fence']}

    def execute(self, task):
        runner = Runner(self.store, self.backend, self.limits, self.ledger)
        try:
            runner.execute(task)
        except Exception:
            self.ledger.record('runner_failed', task_id=task['id'], fence=task['fence'])
        finally:
            try:
                row = self.ledger.get(task['id'], task['fence'])
                state = self.store.get(task['id'])['state']
                if (row['observed'] or not runner.launch_attempted) and state in {'SUCCEEDED', 'FAILED', 'CANCELLED'} and runner.stop(row['name']):
                    self.ledger.phase(task['id'], task['fence'], 'DONE')
                else:
                    self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')
            except Exception:
                self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')

    def request(self, message):
        if message.action == 'worker_online':
            if message.task_id or message.fence or message.revision != self.store.settings.source_revision:
                raise Denied('invalid_worker_heartbeat')
            self.ledger.worker_beat(message.revision)
            return {'phase': 'ONLINE', 'fence': 0}
        if message.task_id is None:
            raise Denied('task_scope_required')
        task_id = str(message.task_id)
        if message.action == 'submit':
            if message.fence:
                raise Denied('unexpected_start_fence')
            return self.submit(task_id, message.revision)
        row = self.ledger.get(task_id, message.fence)
        if message.action == 'heartbeat':
            self.ledger.beat(task_id, message.fence)
            self.ledger.worker_beat(self.store.settings.source_revision)
        return {'phase': row['phase'], 'fence': row['fence']}


def create_broker_app(service=None, token=None):
    stop = Event()
    queue = None
    if service is None:
        settings = Settings.load(identities_required=False)
        store = Store(settings)
        queue = broker(settings)
        service = RuntimeBroker(store, RuntimeLedger(os.environ['F1_RUNTIME_LEDGER']), RuntimeBackend(), RuntimeLimits.load())
        token = Path(os.environ['F1_BROKER_TOKEN_FILE']).read_text().strip()

    def dispatch():
        while not stop.wait(.5):
            try:
                if service.ledger.watchdog_ready():
                    service.store.recover()
                    service.store.dispatch(queue)
            except Exception:
                # Policy and transport failure never grant starts.
                stop.wait(1)

    @asynccontextmanager
    async def lifespan(app):
        if queue:
            Thread(target=dispatch, daemon=True).start()
        yield
        stop.set()
        service.pool.shutdown(wait=False)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.runtime = service

    @app.middleware('http')
    async def bounded_rpc(request: HTTPRequest, call_next):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 2048:
                return JSONResponse(status_code=413, content={'detail': 'rpc_size_limit'})
        request._body = bytes(data)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_rpc(request, error):
        return JSONResponse(status_code=422, content={'detail': 'invalid_runtime_command'})

    @app.post('/rpc')
    def rpc(message: Request, authorization: str = Header(default='')):
        if not token or len(authorization) > 256 or not hmac.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
            raise HTTPException(401, 'broker_auth_required')
        try:
            return service.request(message)
        except (Denied, ValueError):
            raise HTTPException(409, 'runtime_request_denied') from None

    return app
