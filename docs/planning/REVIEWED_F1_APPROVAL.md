# Reviewed planning approval on existing F1

`PlanningApproval` is an internal, client-free composition of
[exact review](TRUSTED_PLANNING_REVIEW.md) with `Store.approve`. It does not expose
an API or Telegram command, read credentials, construct an HTTP client, dispatch
runtime or invoke a provider. Only command-center planning contexts are allowed.

prepare reads the current waiting task and checked context under the existing
global Control lock and uses PostgreSQL time to create the review. authorize
requires owner and the separate literal
`AUTHORIZE_EXACT_SAVED_REQUEST_LIVE_PLANNING`, plus the exact displayed quote
digest. A digest is not authentication: a future Telegram transport must prove
an observed owner callback before calling this internal function.

The existing Store.approve transaction checks task/version/epoch/source/stop,
sets READY and creates Approval/Outbox. Its scope installer revalidates current
context/profile/quote and creates the narrowed ExternalGrant in the same
transaction. The approval deadline is capped at the original quote expiry;
review/profile validation is repeated after audit work. Any failure rolls back
task state, Approval, Outbox and grant together. Replays/concurrent confirmations
produce at most one grant. A different creation key cannot reauthorize the same
context, and changed context cannot bypass an unresolved action for that request.

Gateway.check_budget extracts the prior shared ledger admission without changing
its task/daily/monthly/90-percent thresholds or handling of disputed reserves.
The existing transport calls the same helper before provider INTENT; planning
approval uses it without constructing a client. Funding evidence additionally
counts all pending reserves and actual charges settled on or after the evidence's
UTC day. Day-level anchors require this conservative accounting: spend earlier
on the evidence day may be counted again. This can reject a request, never add
spending room. Missing settlement-day anchors conservatively count actual spend.

Approval performs a budget precheck, not a reservation. A future provider path
must repeat admission under the same F1 lock and durably reserve before I/O.
Pending approvals do not replace the external ledger or reserve money early.

The grant pins task/payload/source/profile/model/request/context/Responses digest,
review/expiry, a one-call budget, and business_execution=false. It has empty
secret_refs and no credential/runtime binding. Both existing coding and mock
planning gateways reject its scope; the production RuntimeBroker rejects
saved_request_plan before claim. These grants are not a runnable live capability.
Existing production tasks and grants are not modified by this implementation.

Validation on local Linux Python 3.12, locked dependencies, isolated PostgreSQL:
`test_planning_admission.py`, `test_planning_approval.py`, `test_planning_gateway.py`:
123 passed, one existing Starlette/httpx warning. Full repository Ruff and
git diff --check passed. Source mounted read-only in the test container; only
the dedicated local test DB/venv volume were used. An initial Windows PG run
exposed a wrong test expectation for normal stop (which cancels waiting tasks);
the test now checks preservation of the actual pre-approval state. Linux was
required for the existing fcntl-based runtime imports; no guard was mocked away.

Remaining before live planning: observed authenticated Telegram review callbacks,
protected operator profile/key bindings, live gateway dispatch with authority
and financial checks immediately before I/O and result acceptance, and bounded
unknown-outcome handling. Real operator evidence, paid consent, source/image
build and deployment require their own exact authorization. No model/tariff is
guessed and no paid call is made by these tests.
