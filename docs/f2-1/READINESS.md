# F2.1: real integration readiness, disabled by default

Source: owner's F2.1 development/finalization instructions. Base: PR #13,
`feat/f2-autonomous-coding-agent`, `e5b626609687459bf795fe62a55fec8e81259dc9`.
This package extends that implementation; earlier requirements/decisions and
PR #8–#13 remain unchanged and unmerged. No real AI call, new-publisher GitHub
write, VPS access, customer data, purchase or production deployment is authorized.

## Implemented path

Authenticated owner → bounded coding task → F1 exact approval → trusted gateway
→ Responses HTTP → networkless edit/test container → bounded repair → independent
replay container → GitHub Git Data and draft PR → durable report/mobile panel.

The exercise remains `f2-synthetic-sum` / `sum_positive_v1`, pinned to the fixed
F2 Git baseline; only `calculator.py` may change. Arbitrary repositories, shell
commands, modified tests and broader coding languages are not enabled by F2.1.
The existing narrow AST policy and synthetic acceptance contract remain intact.

`HttpCodingRunner` in the trusted broker owns orchestration and external calls.
Each model proposal is applied and tested in a fresh F1 sandbox; prior proposals
are replayed to reconstruct the real Git history. Failed test evidence becomes
the next bounded provider context. Final output is independently reconstructed
and tested in a separate container before any publication plan is admitted.
Executors receive source proposals, never credentials, HTTP clients or a raw
gateway endpoint. They retain no network, host mounts, Docker socket or admin
rights. Existing runtime lease/fencing/watchdog/cancellation remain authoritative.

## One authority, restricted gateway

`ExternalGrant` narrows an existing F1 approval; it does not replace owner
authentication or create a second execution authority. It binds task version,
payload hash, control-plane revision, synthetic Git base, configuration hash,
repository, model, call count, secret aliases and task budget. Grants are anchored
in the audit chain. Runtime DB role cannot create these owner grants.
F1 approval, narrowed grant and Outbox readiness are committed atomically;
a failed scope installation rolls all of them back before worker admission.

Every external call checks F1 task/approval state, cancellation, epoch, lease,
fence, source revision, grant/config identity and audit integrity. Live I/O also
requires a runtime guard. Requests are snapshotted and hashed; a durable PG
INTENT is committed before I/O, outside the network transaction. Credentials
are resolved only in the trusted service and attached to HTTPS headers.

The gateway permits only the documented Responses endpoint and a fixed subset
of GitHub Git Data/PR endpoints in an explicitly configured dedicated repository
named `<owner>/acc-f2-synthetic-<name>`. Main Command Center and CRM names are not
valid defaults. No generic HTTP, shell, merge or force-update route is exposed.
GitHub writes must match the independently verified, audit-anchored publication
plan; task branches and draft-only PR parameters have additional checks.

Source, comments, test results and model responses are untrusted data. They
cannot change the trusted model, tariff, endpoints, allowlist, tests, credentials
or approval. Tool calls and extra edit fields are rejected. Instructions in
repository text stay in the user data context; trusted developer instructions
are fixed. This is policy enforcement, not a claim that prompting prevents
injection. Responses that echo the active credential are blocked before storage.

## Credentials and activation

Default configuration is disabled, with no model, prices, repository or keys.
`F2_INTEGRATION_CONFIG_FILE` selects a protected operator-managed JSON file;
absence means disabled. API/task input cannot configure it. Configuration contains
secret aliases and paths, not values. File credential resolution uses O_NOFOLLOW,
regular-file/size checks and rejects group/world permissions. Inject short-lived
credentials with mode 0600, readable only by the trusted gateway UID. Do not put
credentials in Git, task JSON, browser forms, prompts, logs or executor mounts.

For future Compose use, mount the non-secret config read-only into API and runtime
broker, set the file selector on those services, and mount credential files only
into runtime broker. The worker and coding containers must retain their existing
credential boundaries. Configure approved egress for the trusted gateway only;
do not add network access to coding containers. This stage did not configure
real egress, VPN, MFA, credentials or any real host.

Live mode requires explicit `mode=live`, `live_authorized=true`, both credential
bindings, available-budget evidence, confirmed tariff and per-task owner approval.
HTTP-mock mode requires an actual `httpx.MockTransport`; it cannot silently fall
back to the network. Tests inject public fake credentials only. Live mode forbids
transport replacement. No actual activation configuration is committed.

## Financial control

Amounts are integer nano-RUB, never floating-point prices. No real model or tariff
is invented. A confirmed profile must identify the exact model ID, full-context
input token ceiling, output cap, maximum input/output prices, fixed charges and
evidence covering currency conversion/taxes/other applicable billable components.
Use a pinned model ID that matches Responses `model`, not an unverified alias.

Before each paid call reserve the maximum confirmed context cost plus output cap
and fixed charge. This intentionally over-reserves rather than guessing tokenizer
overhead or relying on unconfirmed discounts. Actual bounded usage settles the
reserve after a valid response. Missing/malformed usage, HTTP failure, timeout
or PG loss preserves the disputed reserve. It is never automatically aged out.

The ledger enforces task, daily and monthly limits; monthly configured room is
at most 10,000 RUB and must account for separately committed essential costs.
Optional AI work is restricted at the 90% boundary. The existing F1 70/90/100
control policy remains unchanged; this ledger is real-provider accounting,
separate from the F1 synthetic demonstration counter. Unknown reserves from
earlier periods remain committed. All reservations serialize through the F1
global PG lock, and ledger rows are sealed against the audit chain. Call and
iteration counts, context/output sizes, tokens and total runtime are bounded.

An unresolved external write blocks new dependent writes. A duplicate completed
request returns durable evidence; an uncertain request is never resent. Usage
can be settled by an explicit owner billing-evidence attestation API, recorded
as `OWNER_BILLING_ATTESTATION`, not falsely labelled an independent provider API
measurement. This does not resume the task or authorize a repeat. No universal
per-request billing lookup or retrieval for `store:false` is invented.

## GitHub publication and reconciliation

Use a short-lived GitHub App installation token, limited to the dedicated
synthetic repository with Contents and Pull requests write and required metadata
read; no administration/workflow/other-repository rights. Token issuance/rotation
belongs to approved secure injection, not to the coding agent. A suitably scoped
expiring token is supported by the same credential binding.

The synthetic remote must first be seeded with the exact F2 baseline. Publisher
uploads bounded blobs/trees/commits via official Git Data endpoints, validates
returned content-addressed SHAs, creates `f2/task-<UUID>-<fence>` without force,
rechecks base/head and creates a draft PR. Returned repo, revisions, marker,
branch, draft state and URL must match. No merge operation exists.

Every write has durable intent. Reconciliation reads exact objects/refs or the
single matching PR and resolves only confirmed outcomes; absence/conflict stays
blocked. It never repeats an uncertain POST. Fresh base/head reads avoid stale
cached preflight results. Reconciliation requires current authority/lease; after
expiry/cancellation, no automatic renewal or resumption is granted. An owner
must arrange a separately authorized recovery/investigation when safe read
authority is no longer available. Money-only attestation remains possible without
remote calls and cannot claim a coding result succeeded.

## Mobile UI

The panel displays connection/tariff status, task description, synthetic repo,
scope, task budget, actual and disputed costs, AI call count, test history,
publication state, failure and PR URL. Creating a task performs no external call;
one exact bounded approval enables ordinary steps. Generic render approval is
rejected for external tasks. HTTP-mock links are labelled as test output and are
not live GitHub links. Only validated live GitHub publication exposes a clickable
PR. Synthetic authentication is not evidence of real MFA or production access.

## Contract provenance and remaining live conditions

Responses subset checked against official SDK source:
<https://github.com/openai/openai-python/blob/main/src/openai/resources/responses/responses.py>.
Contract fixtures include response ID, model, status, assistant message/output_text
and input/output/total usage; they do not treat arbitrary invented JSON as the API.
GitHub: <https://docs.github.com/en/rest/git> and
<https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request>.

For a first real run, separately authorize: a compatible exact model and evidenced
tariff/available budget; scoped secret injection; a seeded dedicated synthetic
GitHub repository/App installation; approved trusted-service egress and runtime;
then one exact bounded task. These are setup/authorization/live validation gates,
not a need to rewrite the integration. Actual account/region/API/model availability,
GitHub server normalization, real billing behavior and remote timing remain
unverified until that separately authorized pilot. No real AI success is claimed.
Rootless host isolation, VPN/MFA, offsite backups/checkpoints and external watchdog
retain their earlier unverified deployment gates. F1 acceptance is not granted.
