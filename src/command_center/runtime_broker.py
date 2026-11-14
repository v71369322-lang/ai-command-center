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
    def __init__(self, store, ledger, backend, limits=None, gateway_factory=None, planning_host=None, code_factory=None):
        self.store, self.ledger, self.backend = store, ledger, backend
        self.limits = limits or RuntimeLimits()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.last_future = None
        self.gateway_factory = gateway_factory
        self.planning_host = planning_host
        from .code_factory import CodeFactory
        self.code_factory = code_factory or CodeFactory(store)

    def submit(self, task_id, revision):
        with self.lock:
            self.ledger.verify()
            if revision != self.store.settings.source_revision:
                raise Denied('broker_revision_mismatch')
            kind = self.store.get(task_id)['payload']['kind']
            planning = kind in {'saved_request_plan', 'saved_request_code'}
            if kind == 'saved_request_code':
                self.code_factory.preflight()
            if kind == 'isolated_coding':
                if self.backend.mode != 'rootless-required':
                    raise Denied('isolated_coding_rootless_required')
                if self.limits.memory_mib > 256 or self.limits.cpu > .5 or self.limits.pids > 64:
                    raise Denied('isolated_coding_runtime_limits')
            if planning and self.planning_host is None:
                raise Denied('planning_runtime_not_connected')
            if not self.ledger.watchdog_ready(self.limits.watchdog_seconds):
                raise Denied('watchdog_unavailable')
            if self.ledger.runs():
                raise Denied('runtime_busy_or_uncertain')
            self.backend.preflight()
            if planning:
                self.planning_host.preflight(self.store, self.ledger, self.backend)
                if not self.ledger.worker_fresh(revision, self.limits.heartbeat_seconds):
                    raise Denied('planning_worker_unavailable')
            task = self.store.claim(task_id)
            if not task:
                return {'phase': 'NOT_ADMITTED', 'fence': 0}
            task['revision'] = revision
            try:
                if planning:
                    self.ledger.register(task, Runner.name(task), self.limits.wall_seconds, kind='planning_http')
                else:
                    self.ledger.register(task, Runner.name(task), self.limits.wall_seconds)
            except Exception:
                self.store.abort(task_id, task['fence'], 'verified_no_effect', True)
                raise
            self.last_future = self.pool.submit(self.execute, task)
            return {'phase': 'INTENT', 'fence': task['fence']}

    def execute(self, task):
        if task['payload']['kind'] in {'saved_request_plan', 'saved_request_code'}:
            from .planning_host_runner import PlanningHostRunner
            try:
                PlanningHostRunner(self.store, self.ledger, self.backend, self.limits, self.planning_host,
                    gateway_factory=self.code_factory if task['payload']['kind'] == 'saved_request_code' else None).execute(task)
            except Exception:
                self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')
                self.ledger.record('planning_runner_failed', task_id=task['id'], fence=task['fence'])
            return
        if task['payload']['kind'] == 'isolated_coding':
            from .coding.isolated_runner import IsolatedCodingRunner
            runner = IsolatedCodingRunner(self.store, self.backend, self.limits, self.ledger)
        elif task['payload']['kind'] == 'coding_synthetic':
            if task['payload']['coding']['provider'] == 'openai':
                from .coding.http_runner import HttpCodingRunner
                gateway = self.gateway_factory() if self.gateway_factory else None
                runner = HttpCodingRunner(self.store, self.backend, self.limits, self.ledger, gateway)
            else:
                from .coding.runner import CodingRunner
                runner = CodingRunner(self.store, self.backend, self.limits, self.ledger)
        else:
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
        from .planning_host import configured_host
        planning_host = configured_host()
        settings = Settings.load(identities_required=False)
        store = Store(settings)
        ledger, backend = RuntimeLedger(os.environ['F1_RUNTIME_LEDGER']), RuntimeBackend()
        if planning_host is not None:
            planning_host.preflight(store, ledger, backend)
        queue = broker(settings)
        service = RuntimeBroker(store, ledger, backend, RuntimeLimits.load(), planning_host=planning_host)
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
