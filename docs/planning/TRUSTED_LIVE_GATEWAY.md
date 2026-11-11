# Trusted live Responses planning adapter

Continuation: [explicit rootless planning host lifecycle](HOST_LIFECYCLE.md)
composes this adapter with the existing broker, heartbeat, runtime ledger and
watchdog while preserving the default-closed production factory.

`LivePlanningGateway` is an explicit internal adapter on the existing F1 and
external-action ledger. It has no production factory, broker route or automatic
activation. Default operator profile remains absent/disabled. This change does
not deploy code, install a key, approve the owner's waiting task or make a paid
call.

## Binding before consent

PlanningProfile now optionally carries a PlanningRuntimeBinding: exact source
revision, trusted host binding_digest, fixed planning-openai reference and
SHA256 of the exact credential-file bytes. These fields are included in the
reviewed profile hash and therefore in the owner card/grant. The source must
match the planning snapshot. Staged grants with runtime=None/empty secret_refs
cannot become usable after adding a binding: the profile/grant hashes differ.
No old approval is silently upgraded. An actual source deployment also retains
the existing task source pinning rules.

The existing pinned private profile loader is reused. The provider key is read
only inside the trusted adapter from explicitly supplied
F1_PLANNING_OPENAI_KEY_FILE, using the existing private-file custody checks,
bounded ASCII shape and exact raw-byte SHA256. No key path comes from a task or
model. No provider key is mounted or read by the Telegram review flow. A caller
must supply a trusted runtime guard that independently attests the complete
binding; a task cannot supply or replace it. Actual host/rootless/watchdog
attestation and release-package integration are a separate remaining stage.

## Admission and I/O

Before reading the provider key, request validates current profile, runtime,
F1 Approval/lease/fence/epoch/source/ExternalGrant, exact request context and
exact Responses document. It also requires the existing consumed Telegram-card
audit event and repeats the same exact observed-delivery proof used by the
callback. A direct internal review authorization without an observed owner
Telegram click does not permit provider I/O. This narrows F1; it is not a second
authority mechanism.

Only POST https://api.openai.com/v1/responses with the existing planning/v1 key
is allowed. Query, reconciliation, another endpoint/key, tools or changed body
are rejected. HTTP redirects and ambient proxy settings are disabled; the
existing direct HTTP transport has no retry loop. No models/token-count call
or other provider endpoint is added.

The shared Gateway writes durable INTENT/reservation before network access.
Immediately before I/O the adapter repeats runtime/profile/key identity,
F1 authority and shared financial/funding admission under the existing Control
lock. Reservations and disputed reserves across tasks are counted. No second
spending counter or early approval reservation is introduced.

The request retains store=false, strict JSON plan format, service_tier=default
and the operator's model/output bound. The official [Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
documents that returned service_tier can differ from the requested tier. The
adapter therefore requires an actual default tier before financial settlement.
It does not guess a model, tariff, account balance or output price.

Responses are byte bounded; duplicate JSON keys, credential echoes, unknown
model/usage, missing/non-default pricing tier and incomplete envelopes preserve
the INTENT/UNCERTAIN reservation. They never trigger an automatic second call.
Existing status codes, 8-second I/O timeout and financial interlocks are kept.
Configured reservation limits are not provider-enforced billing cutoffs.

## Settlement and advisory result

Settlement uses the admitted tariff copy, even if the profile changes during
I/O. Revocation/stop/profile/runtime/expiry changes reject continuation while
preserving billed usage. A structurally rejected plan also preserves the
settled COMPLETE response and spend. A valid COMPLETE response can be reused
locally after a finalization failure while the original authority remains
valid; this is not another HTTP request.

Draft save, response/action binding audit and F1 completion are atomic. Authority
is repeated after result writes; loss during finalization rolls the draft back.
The artifact records mode=live and business_execution=false. Saved request
remains an advisory planning request; no coding task, verifier run, publication
or business execution is created. Existing draft schema/readback conservatively
retain owner_supplied_unverified/provider_evidence_verified=false; the exact
provider action is anchored separately in planning_proposal_bound and the
external ledger. This stage does not upgrade that public provenance schema or
claim the plan's quality/business correctness.

## Validation and remaining host stage

Tests use isolated Linux/PostgreSQL, frozen dependencies, public synthetic key
files, a fake trusted binding guard and httpx.MockTransport replacing the client
only inside tests. The production adapter exposes no transport override.
There are no live provider calls or real expenses in these tests. Coverage
includes observed consent, pre-key denials, source/key/profile changes,
pre-I/O revocation, unknown outcomes, concurrency, default-tier/usage/JSON/secret
checks, tariff changes during I/O, shared ledger room and atomic finalization.
Final local scope: 335 passed, one existing Starlette/httpx warning. Locked
Linux Ruff, API contract and git diff --check passed. Exact source/merge-ref
CI is recorded by the resulting dependent Draft PR.

Production RuntimeBroker still rejects saved_request_plan before claim. Next is
a separately reviewed trusted host lifecycle, actual watchdog/source/image/
binding attestation and protected release-package wiring. Deployment, merge,
real credential connection and each paid call still require their own concrete
owner authorization. No enabled flag or newly installed key may retroactively
activate a previous staged consent.
