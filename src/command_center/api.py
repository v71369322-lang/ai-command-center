import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator, SecretStr
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .limits import RateLimit
from .store import Denied, Store
from .worker import broker
from .owner_auth import OwnerAuth
from .coding.contract import CodingRequest, payload as coding_payload, template as coding_template
from .project_setup import ProjectId, PreviewRequest, SaveRequest, RestoreRequest, EVENT as PROJECT_SETUP_EVENT
from .request_plan_store import ManualRequest, ManualSaveRequest, EVENT as PLAN_DRAFT_EVENT
from .plan_acceptance import AcceptanceRequest
from .coding_preparation import CodingPreparationRequest, CodingPreparationSave
from .isolated_coding import BindRequest, BindSave


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["render", "approved_render"] = "render"
    values: dict[str, str] = Field(min_length=1, max_length=16)
    cost: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    dependency: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")

    @field_validator("values")
    @classmethod
    def bounded_values(cls, values):
        if len(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()) > 7000:
            raise ValueError("synthetic input byte limit")
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


class ProjectAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[a-f0-9]{64}:[0-9]{1,16}$')
    project_id: Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'] | None
    expected_version: int = Field(ge=0, le=1000, strict=True)
    operation_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')


class AttentionScheduleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    timezone: str = Field(min_length=1, max_length=64)
    report_times: list[str] = Field(min_length=1, max_length=3)
    quiet_start: str = Field(pattern=r'^[0-2][0-9]:[0-5][0-9]$')
    quiet_end: str = Field(pattern=r'^[0-2][0-9]:[0-5][0-9]$')
    expected_version: int = Field(ge=0, le=1000, strict=True)
    operation_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')


class ErrorResponse(BaseModel):
    detail: str


class AssertionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    assertion: str = Field(min_length=32, max_length=7000)


class PasswordLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


class ExternalApprovalRequest(ApprovalRequest):
    budget_nano_rub: int = Field(gt=0, le=10_000_000_000_000, strict=True)


class BillingReconciliation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    input_tokens: int = Field(ge=0, le=10_000_000, strict=True)
    output_tokens: int = Field(ge=0, le=4096, strict=True)
    evidence_reference: str = Field(min_length=1, max_length=300)


class FinalExperimentApproval(ExternalApprovalRequest):
    budget_nano_rub: int = Field(default=100_000_000_000, gt=0, le=100_000_000_000, strict=True)
    confirmation: Literal['AUTHORIZE_FIRST_PAID_EXPERIMENT']
    profile_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class FinalRecoveryApproval(ExternalApprovalRequest):
    budget_nano_rub: int = Field(gt=0, le=34_786_800_000, strict=True)
    confirmation: Literal['AUTHORIZE_ONE_PAID_RECOVERY']
    profile_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


def create_app(settings=None, gateway_factory=None):
    settings = settings or Settings.load()
    store = Store(settings)
    owner_auth = OwnerAuth(store)
    queue = broker(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.engine.dispose()
        queue.close()

    app = FastAPI(title="AI Command Center — synthetic F1", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None,
                  responses={422: {"model": ErrorResponse, "description": "Invalid request; input is not echoed"},
                             429: {"model": ErrorResponse, "description": "Bounded request rate exceeded"}})
    app.state.store = store
    limiter = RateLimit()

    def external_gateway():
        from .coding.gateway import Gateway
        return gateway_factory() if gateway_factory else Gateway(store)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        from fastapi.responses import JSONResponse
        # Never echo an invalid body's input values (which may contain secrets).
        return JSONResponse(status_code=422, content={"detail": "invalid_request"})

    def record_denial(request, reason):
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        actor = next((r for r, token in settings.identities.items()
                      if hmac.compare_digest(supplied.encode(), token.encode())), "unauthenticated")
        try:
            with store.transaction() as session:
                store.audit(session, "request_denied", actor, reason=reason)
        except Exception:
            pass  # No authority is granted when durable logging is unavailable.

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        from fastapi.responses import JSONResponse
        if error.status_code in {401, 403, 404}:
            await run_in_threadpool(record_denial, request, "http_" + str(error.status_code))
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @app.exception_handler(Denied)
    async def denied_handler(request, error):
        from fastapi.responses import JSONResponse
        await run_in_threadpool(record_denial, request, str(error))
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"detail": "database_unavailable"})

    @app.middleware("http")
    async def security_headers(request, call_next):
        if not limiter.admit(request.client.host if request.client else "unknown"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"detail": "rate_limited"},
                                headers={"Retry-After": "60", "Cache-Control": "no-store"})
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

    def identity(request: Request, authorization: str = Header(default="")):
        if settings.auth_mode in {'oidc', 'password'}:
            return owner_auth.authenticate(request)
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "authentication_required")
        token = authorization[7:]
        if len(token) > 256:
            raise HTTPException(401, "invalid_identity")
        for role, expected in settings.identities.items():
            if hmac.compare_digest(token.encode(), expected.encode()):
                return role
        raise HTTPException(401, "invalid_identity")

    def human(role=Depends(identity)):
        if role == "agent":
            raise HTTPException(403, "role_forbidden")
        return role

    @app.get('/api/auth/mode')
    def auth_mode():
        return {'mode': settings.auth_mode,
                'identity_provider_configured': settings.auth_mode == 'oidc' and owner_auth.trusted(),
                'owner_login_configured': owner_auth.trusted(), 'mfa_verified': False,
                'production_access_verified': False}

    @app.post('/api/auth/exchange')
    def exchange(body: AssertionRequest, request: Request, response: Response):
        if request.url.scheme != 'https':
            raise HTTPException(403, 'https_required')
        if request.headers.get('origin') not in {None, settings.web_origin}:
            raise HTTPException(403, 'origin_rejected')
        token, csrf, seconds = owner_auth.exchange(body.assertion)
        response.set_cookie(owner_auth.cookie, token, max_age=seconds, secure=True, httponly=True, samesite='strict', path='/')
        return {'csrf_token': csrf, 'expires_in': seconds}

    @app.post('/api/auth/login')
    def password_login(body: PasswordLogin, request: Request, response: Response):
        token, csrf, seconds = owner_auth.password_login(request, body.username, body.password.get_secret_value())
        response.set_cookie(owner_auth.cookie, token, max_age=seconds, secure=owner_auth.secure_cookie,
                            httponly=True, samesite='strict', path='/')
        return {'csrf_token': csrf, 'expires_in': seconds, 'mfa_verified': False}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, role=Depends(identity)):
        if settings.auth_mode not in {'oidc', 'password'} or role != 'owner':
            raise HTTPException(403, 'owner_session_required')
        owner_auth.revoke(request.cookies.get(owner_auth.cookie))
        response.delete_cookie(owner_auth.cookie, secure=owner_auth.secure_cookie, httponly=True, samesite='strict', path='/')
        return {'revoked': True}

    @app.get('/api/auth/csrf')
    def session_csrf(request: Request, role=Depends(identity)):
        if settings.auth_mode not in {'oidc', 'password'} or role != 'owner':
            raise HTTPException(403, 'owner_session_required')
        return {'csrf_token': owner_auth.csrf(request.cookies.get(owner_auth.cookie, ''))}

    @app.post('/api/auth/revoke-all')
    def revoke_sessions(role=Depends(identity)):
        if settings.auth_mode not in {'oidc', 'password'} or role != 'owner':
            raise HTTPException(403, 'owner_required')
        owner_auth.revoke(all_sessions=True)
        return {'revoked': True}

    @app.get("/api/state")
    def state(role=Depends(human)):
        result = store.snapshot()
        # Keep the protected audit unchanged. Generic timelines are projections;
        # draft values are read only through the screened owner setup/plan endpoints.
        for item in result['events']:
            event = item['event']
            if event.get('kind') in {PROJECT_SETUP_EVENT, PLAN_DRAFT_EVENT}:
                item['event'] = {'kind': event['kind'], 'details_redacted': True}
        from .coding.integration_config import IntegrationConfig
        if gateway_factory:
            gateway = external_gateway()
            try:
                result['integration'] = gateway.config.public()
            finally:
                gateway.close()
        else:
            result['integration'] = IntegrationConfig.load().public()
        for task in result['tasks']:
            if task['payload'].get('coding', {}).get('provider') == 'openai':
                gateway = external_gateway()
                try:
                    task['integration'] = gateway.status(task['id'])
                finally:
                    gateway.close()
        return result

    @app.get('/api/integration/status')
    def integration_status(role=Depends(human)):
        from .coding.integration_config import IntegrationConfig
        return IntegrationConfig.load().public()

    @app.get('/api/experiments/first')
    def first_experiment_status(role=Depends(human)):
        from .coding.first_experiment import FirstExperiment, EXPERIMENT_ID
        from .store import digest
        gateway = external_gateway()
        try:
            config = gateway.config
            result = (config.first_experiment or FirstExperiment()).report()
            result.update(mode=config.mode, connected=config.connected(), repository=config.synthetic_repository or None,
                          profile_hash=digest(config.model_dump()),
                          credential_refs_configured=bool(config.credential_files))
            active_id = config.first_experiment.id if config.first_experiment else EXPERIMENT_ID
            task = next((t for t in store.snapshot()['tasks'] if t['payload'].get('coding', {}).get('experiment_id') == active_id), None)
            result['task_state'] = task
            if task:
                result['integration'] = gateway.status(task['id'])
            return result
        finally:
            gateway.close()

    @app.post('/api/experiments/first/task', status_code=201)
    def create_first_experiment(role=Depends(identity)):
        from .coding.first_experiment import create_task
        # Stable request identity makes repeated phone taps return the same task.
        return create_task(store, role)

    @app.post('/api/experiments/first/{task_id}/authorize')
    def authorize_first_experiment(task_id: str, command: FinalExperimentApproval, role=Depends(identity)):
        from .coding.first_experiment import EXPERIMENT_ID
        if store.get(task_id)['payload'].get('coding', {}).get('experiment_id') != EXPERIMENT_ID:
            raise Denied('not_first_experiment_task')
        gateway = external_gateway()
        try:
            return gateway.authorize(role, task_id, command.version, budget_nano_rub=command.budget_nano_rub,
                                     seconds=command.seconds, final_confirmation=True,
                                     expected_config_hash=command.profile_hash)
        finally:
            gateway.close()

    @app.post('/api/experiments/recovery/task', status_code=201)
    def create_recovery_experiment(role=Depends(identity)):
        from .coding.first_experiment import RECOVERY_ID, create_task
        return create_task(store, role, experiment_id=RECOVERY_ID)

    @app.post('/api/experiments/recovery/{task_id}/authorize')
    def authorize_recovery_experiment(task_id: str, command: FinalRecoveryApproval, role=Depends(identity)):
        from .coding.first_experiment import RECOVERY_ID
        if store.get(task_id)['payload'].get('coding', {}).get('experiment_id') != RECOVERY_ID:
            raise Denied('not_recovery_experiment_task')
        gateway = external_gateway()
        try:
            return gateway.authorize(role, task_id, command.version, budget_nano_rub=command.budget_nano_rub,
                                     seconds=command.seconds, final_confirmation=True,
                                     expected_config_hash=command.profile_hash)
        finally:
            gateway.close()

    @app.post('/api/coding/tasks/{task_id}/authorize')
    def authorize_external(task_id: str, command: ExternalApprovalRequest, role=Depends(identity)):
        gateway = external_gateway()
        try:
            return gateway.authorize(role, task_id, command.version,
                                     budget_nano_rub=command.budget_nano_rub, seconds=command.seconds)
        finally:
            gateway.close()

    @app.post('/api/integration/reconcile-billing')
    def reconcile_billing(command: BillingReconciliation, role=Depends(identity)):
        gateway = external_gateway()
        try:
            return gateway.reconcile_usage(role, command.action_id, command.input_tokens,
                                           command.output_tokens, command.evidence_reference)
        finally:
            gateway.close()

    @app.get('/api/coding/template')
    def coding_scope(role=Depends(human)):
        return coding_template()

    @app.post('/api/coding/tasks', status_code=201)
    def create_coding(command: CodingRequest, role=Depends(identity),
                      idempotency_key: str = Header(..., min_length=1, max_length=100)):
        try:
            value = coding_payload(command)
        except ValueError:
            raise Denied('synthetic_source_pin_mismatch') from None
        return store.create(role, idempotency_key, value)

    @app.get('/api/tasks/{task_id}/pull-request')
    def coding_pull_request(task_id: str, role=Depends(human)):
        task = store.get(task_id)
        if task['state'] != 'SUCCEEDED' or 'pr' not in task['coding']:
            raise Denied('verified_pull_request_not_available')
        return task['coding']['pr']

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
        task_payload = store.get(task_id)['payload']
        if task_payload['kind'] == 'saved_request_plan' or task_payload.get('coding', {}).get('provider') == 'openai':
            raise Denied('external_scope_approval_required')
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

    @app.get('/api/telegram/status')
    def telegram_status(role=Depends(identity)):
        from .telegram_health import status
        if role != 'owner':
            raise Denied('owner_required')
        return status(store, os.environ.get('F1_TELEGRAM_SCOPE', ''))

    @app.get('/api/project-inbox')
    def project_inbox(project: Literal['all', 'unassigned', 'command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'] = 'all',
                      role=Depends(identity)):
        from .project_inbox import inbox
        return inbox(store, role, project)

    @app.get('/api/projects/{project_id}')
    def project_status(project_id: Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'],
                       role=Depends(identity)):
        if role != 'owner':
            raise Denied('owner_required')
        from .project_catalog import summary
        from .project_connections import statuses
        with store.transaction() as session:
            store.check_audit(session)
            connection = statuses(session).get(project_id)
            return {'project': summary(project_id), 'connection': connection,
                    'execution_connected': False, 'repair_plan_available': connection is not None,
                    'merge_enabled': False, 'deployment_enabled': False}

    @app.get('/api/attention')
    def attention(role=Depends(identity)):
        from .attention import summary
        return summary(store, role)

    @app.get('/api/attention/schedule')
    def attention_schedule(role=Depends(identity)):
        from .attention_schedule import current
        if role != 'owner':
            raise Denied('owner_required')
        with store.transaction() as session:
            store.check_audit(session)
            return current(session)

    @app.post('/api/attention/schedule')
    def update_attention_schedule(body: AttentionScheduleRequest, role=Depends(identity)):
        from .attention_schedule import configure
        document = body.model_dump(exclude={'expected_version', 'operation_id'})
        return configure(store, role, document, body.expected_version, body.operation_id)

    @app.post('/api/project-inbox/assign')
    def project_assignment(body: ProjectAssignment, role=Depends(identity)):
        from .project_inbox import classify
        return classify(store, role, **body.model_dump())

    @app.get('/api/project-inbox/preparation')
    def preparation_queue(project: Literal['all', 'unassigned', 'command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'] = 'all',
                          stage: Literal['all', 'select_project', 'complete_setup', 'prepare_plan', 'refresh_plan', 'answer_questions', 'verify_scope'] = 'all',
                          page: int = Query(default=1, ge=1, le=100),
                          snapshot: str | None = Query(default=None, pattern=r'^[a-f0-9]{64}$'), role=Depends(identity)):
        from .request_preparation import read
        return read(store, role, project=project, stage=stage, page=page, snapshot=snapshot)

    @app.get('/api/project-inbox/review')
    def request_review(request_id: str = Query(pattern=r'^[a-f0-9]{64}:(0|[1-9][0-9]{0,15})$', max_length=81),
                       role=Depends(identity)):
        from .request_review import read
        return read(store, role, request_id)

    @app.post('/api/project-inbox/plan/preview')
    def manual_plan_preview(body: ManualRequest, role=Depends(identity)):
        from .manual_plan import preview
        return preview(store, role, body)

    @app.post('/api/project-inbox/plan')
    def manual_plan_save(body: ManualSaveRequest, role=Depends(identity)):
        from .manual_plan import save
        return save(store, role, ManualRequest.model_validate(body.model_dump(exclude={'operation_id'})), body.operation_id)

    @app.get('/api/project-inbox/plan/acceptance-preview')
    def plan_acceptance_preview(request_id: str = Query(pattern=r'^[a-f0-9]{64}:(0|[1-9][0-9]{0,15})$', max_length=81),
                                role=Depends(identity)):
        from .plan_acceptance import preview
        return preview(store, role, request_id)

    @app.post('/api/project-inbox/plan/acceptance')
    def plan_content_acceptance(body: AcceptanceRequest, role=Depends(identity)):
        from .plan_acceptance import accept
        return accept(store, role, body)

    @app.get('/api/project-inbox/plan/acceptance')
    def plan_acceptance_read(request_id: str = Query(pattern=r'^[a-f0-9]{64}:(0|[1-9][0-9]{0,15})$', max_length=81),
                             role=Depends(identity)):
        from .plan_acceptance import read
        return read(store, role, request_id)

    @app.post('/api/project-inbox/coding/task-preview')
    def coding_task_preview(body: BindRequest, role=Depends(identity)):
        from .isolated_coding import preview
        return preview(store, role, body.model_dump())

    @app.post('/api/project-inbox/coding/task')
    def coding_task_create(body: BindSave, role=Depends(identity)):
        from .isolated_coding import create
        return create(store, role, body.model_dump())

    @app.post('/api/project-inbox/coding/preparation-preview')
    def coding_preparation_preview(body: CodingPreparationRequest, role=Depends(identity)):
        from .coding_preparation import preview
        return preview(store, role, body)

    @app.post('/api/project-inbox/coding/preparation')
    def coding_preparation_save(body: CodingPreparationSave, role=Depends(identity)):
        from .coding_preparation import prepare
        return prepare(store, role, body)

    @app.get('/api/project-inbox/coding/preparation')
    def coding_preparation_read(request_id: str = Query(pattern=r'^[a-f0-9]{64}:(0|[1-9][0-9]{0,15})$', max_length=81),
                                role=Depends(identity)):
        from .coding_preparation import read
        return read(store, role, request_id)

    @app.get('/api/projects/{project_id}/connection-plan')
    def project_connection_plan(project_id: Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'],
                                role=Depends(identity)):
        from .project_connections import connection_plan
        return connection_plan(role, project_id)

    @app.get('/api/project-setup')
    def project_setup_catalog(role=Depends(identity)):
        from .project_setup import catalog
        return catalog(store, role)

    @app.get('/api/projects/{project_id}/setup')
    def project_setup_read(project_id: ProjectId, version: int | None = Query(default=None, ge=0, le=500),
                           role=Depends(identity)):
        from .project_setup import read
        return read(store, role, project_id, selected=version)

    @app.post('/api/projects/{project_id}/setup/preview')
    def project_setup_preview(project_id: ProjectId, body: PreviewRequest, role=Depends(identity)):
        from .project_setup import preview
        return preview(store, role, project_id, body.expected_version, body.draft)

    @app.post('/api/projects/{project_id}/setup')
    def project_setup_save(project_id: ProjectId, body: SaveRequest, role=Depends(identity)):
        from .project_setup import save
        return save(store, role, project_id, body.expected_version, body.draft, body.operation_id)

    @app.post('/api/projects/{project_id}/setup/restore')
    def project_setup_restore(project_id: ProjectId, body: RestoreRequest, role=Depends(identity)):
        from .project_setup import restore
        return restore(store, role, project_id, body.expected_version, body.target_version,
                       body.target_digest, body.operation_id)

    @app.get('/api/telegram/requests')
    def telegram_requests(role=Depends(identity)):
        from sqlalchemy import select
        from .models import TelegramInbox
        if role != 'owner':
            raise Denied('owner_required')
        with store.transaction() as session:
            store.check_audit(session)
            rows = session.execute(select(TelegramInbox).where(TelegramInbox.state == 'NEEDS_PLANNING')
                                   .order_by(TelegramInbox.created_at.desc()).limit(50)).scalars()
            return {'requests': [{'id': r.id, 'state': r.state, 'text': r.intent['text']} for r in rows],
                    'ai_planning_connected': False}

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api(path: str):
        raise HTTPException(404, "unknown_action")

    dist = Path("web/dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
