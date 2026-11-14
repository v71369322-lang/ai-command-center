# Telegram request to bounded AI code and verified result

This continues PR #100's offline review and isolated executor. It connects a
purpose-specific AI proposal to that executor. No paid request or installation
is performed by this development task. The default AI code profile is disabled.

## Owner path

`/develop NUMBER` reads the current request and gives the exact next step. Project
classification grants no access. Only AI Command Center is supported. The route
requires a current accepted plan, explicit bounded Python file/test specification
and exact offline Git capsule. It creates/reuses one `saved_request_code` F1 task
in `WAITING_APPROVAL`; command intake pins the capsule so delayed commands cannot
select later material. Original `/plan_prepare`, `/plan_authorize`, `/plan_accept`
and `/coding_prepare` retain their own requirements. Nothing silently approves
an AI plan, source access, expenses or execution.

`/code_authorize UUID` prepares a purpose-specific, observed owner card for one
code proposal. The original intake pins task/version/hash/workspace/profile.
The card discloses model, bounded calculated reserve, files/tests transmitted,
workspace and exact provider-request hashes. A 120-second deadline starts at the
original command, not at a retry. Confirmation requires exact SENT body/message,
queued and observed anchors, private owner, connection, source and nonce. F1
Approval, existing ExternalGrant, consumption and reply are atomic under Control.
Old planning or offline-execution permission cannot authorize this purpose.

Broker generates one strict-schema advisory response through its existing HTTP
gateway. The request contains the original request, accepted plan, explicit scope
and proved file bytes. Only full replacements of selected source files are
accepted. Tests, paths, scope, checks, commands and isolation remain fixed. Tools,
arbitrary endpoints, repository fetch, publication, merge and deployment are not
provided. JSON duplicates, wrong bindings/model/usage, test writes, no-op patches,
oversize data and decoded credential echoes are rejected before COMPLETE. Unknown
outcomes retain money reservations and cannot trigger a repeated request.

The complete response and new isolated task commit atomically with F1 finish.
The child remains `WAITING_APPROVAL`, without financial grant or execution
approval. Telegram notifies the owner and offers `/coding_authorize UUID`, which
shows every source/test byte and the complete diff using PR #100's existing flow.
Only its separate confirmation admits the existing rootless two-stage executor.
No provider credentials enter either sandbox. Fixed Ruff/pytest checks run in
fresh agent and verifier sandboxes; files, patch, result and stopped-container
proof retain the existing verification requirements.

`/develop NUMBER` follows this child; `/coding_status UUID` reports its exact
verified artifact, checks and files. Idempotent notifications use the existing
Telegram delivery table. Provider/action/profile/task/child hashes are rechecked
for proposal readback; execution success additionally requires the original
creation pins, expected report, artifact hash and verifier source/fence anchor.
An HTTP mock proposal is explicitly labeled and is never reported as a real AI
call. Verified local code is not a published PR or an installed production change.

## Operator preparation and production composition

Existing owner-only authenticated/CSRF-protected API adds:

- `POST /api/project-inbox/coding/workspace-preview`, then `/workspace` with
  `expected_workspace_digest`. Inputs are request ID, current specification digest
  and bounded Git objects; no replacements, paths to host secrets or remote URLs.
- `GET/POST /api/project-inbox/coding/ai-profile`. Configuration requires the
  exact previous/current profile digest and mode-specific confirmation. It is
  reviewed metadata, never an Approval, grant, key or provider call. Configuration
  remains subject to the owner's separate authorization; this task configures
  no live profile.

`scripts/prepare_isolated_coding.py` without `--replacements` exports the offline
capsule from an already authorized local repository's declared Git commit. It
reads objects only; working-tree changes, hooks and remotes are not used. Output
is exclusively created in a private operator path and must not be committed.
Both review/save and original task admission require the current accepted plan,
setup/repository revision, specification, request text/project/version and Control
epoch. Existing 8192-byte API/transport limits are unchanged: choose a small slice;
oversized snapshots require a separately reviewed transport design.

The live code profile requires fresh reviewed model/tariff/funding/data-sharing
evidence, explicit code-purpose opt-in and the exact installed PlanningProfile
digest/tariff/runtime. An old balance report or planning approval is insufficient.
The installed profile must also be fresh. It reuses only the existing
`planning-openai` broker-owned credential reference and existing attested HTTP
host; no new secret mount, environment binding, socket or access is introduced.

`CodeFactory` checks this profile before claim/client creation and composes
`CodeGateway` with `PlanningCredentials` and the same host guard. Mock profiles
cannot use the production factory. Tests explicitly inject MockTransport factories.
`PlanningHostRunner` accepts a trusted gateway factory; its default planning path
is unchanged. Durable runtime kind `planning_http` is the historical name for
this broker-owned HTTP lifecycle: watchdog/worker admission, host preflight,
heartbeat/lease/fence, deadline and explicit HTTP-return proof are reused. Docker
absence is never accepted as proof that an HTTP operation ended.

## Acceptance and limits

Tests use real PostgreSQL/F1/audit/grant/financial state, observed mock Bot API,
one mock Responses request and real Ruff/pytest subprocesses twice in fresh local
directories. Broker lifecycle tests use synthetic host metadata, not host
attestation. Existing actual-container tests remain separate. None establish
live AI, Telegram, rootless/systemd or VPS acceptance for this new release.

This supports one explicitly selected small Python slice in Command Center.
Automatic repository discovery, unrestricted project development, publishing and
installation remain outside the adapter. Before real use: finish exact CI, prepare
and inspect a specific release, obtain exact installation authorization, verify
rootless/VPS behavior, then obtain fresh code-purpose evidence and separate paid
test permission. The current instruction forbids paid calls.
