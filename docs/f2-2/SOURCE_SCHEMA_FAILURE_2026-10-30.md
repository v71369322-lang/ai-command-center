# First real provider call: source contract rejection

Owner-provided SSH and Telegram outputs on 30 October 2026 confirm application
`322186dc180257c618d8b159c78faa6e5bbf0b43` was applied with bundle
`ac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d`.
The service exited successfully and returned CLOSED_SYNTHETIC_SERVICES_RUNNING;
go_live/MFA/offsite/full rootless-execution acceptance flags remain false. Telegram
readback confirmed the new source and the pinned live configuration. This is
owner evidence, not direct cloud SSH access.

Owner explicitly approved task `938e838d-54d4-470d-ad71-5c6a49a42c7d` through
the paid Telegram card with a limit of 69.5736 RUB. The task reached FAILED,
reason external_coding_blocked, coding stage external_stopped, failure
provider_or_verifier_contract_rejected. Three GitHub discovery/metadata operations
and one OpenAI operation are COMPLETE. The gateway ledger records actual cost
47,840,625 nano-RUB (0.047840625 RUB), reserved zero. These are local ledger
observations, not an independent statement of the current upstream account balance.
No publisher write/PR operation appears in the supplied action list.

Read-only decoding of the saved completed OpenAI response returned
synthetic_language_scope_violation. A further metadata-only AST inspection showed
131 bytes, one function, body Assign/For/Return, no generator and no docstring.
The model source text was not transferred into the cloud. Its correctness was
not evaluated and is not claimed. An ordinary loop implementation is outside
this fixed pilot's existing two-form AST allowlist.

## Correction

The previous strict JSON schema required a source string but allowed every string.
It did not tell the provider that only FIRST and CORRECT are executable in this
integration exercise. Bound the source property to those two canonical values
using JSON Schema enum, and identify the task as a fixed integration exercise in
the trusted instruction. Each request receives an independent schema copy.

The existing decoder, safe_source, tests, independent replay, F1 authority,
source/image/profile pins, financial ledger and no-repeat policy remain intact.
Malformed or nonconforming responses are still rejected. No source normalization,
arbitrary-code execution or retroactive success is introduced. This is a constrained
API integration test, not evidence of general-purpose autonomous coding capability.

Official [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
was retrieved on 30 October 2026; enum is supported and the two short string values
are within its documented limits. No dependency or API endpoint is added.

This cloud correction does not change the deployed source, reset/reopen the failed
task, copy stored responses into new task authority, issue another token, authorize
a replacement task or spend money. The original failure and financial record must
remain intact. A separately reviewed recovery task, fresh source/image/bundle
preparation and exact owner decisions are still needed before another paid attempt.
The previous credential expires at 2026-10-30T11:23:25Z, and its profile evidence
at 11:18:25Z. Neither expiry is extended by this change.

## Verification

The focused regression covers advertised enum bounds, all advertised choices
through the existing execution/independent verifier, rejection of out-of-contract
responses including loops, and isolation between mutable request schemas.
Local focused regression: 8 passed. The broader PG/strict-mock/profile suite:
81 passed /4 exact-source sandbox cases deselected /1 existing Starlette warning,
including those 8 cases, not added together. Ruff, OpenAPI export, tracked-secret
check and diff validation passed. Full fresh-source container CI remains required;
final source and its result are recorded in the Draft PR.

The existing first-pilot grant is deliberately single-use across tasks in live
mode. Recreating a task or changing a request key does not authorize a second
grant. A recovery design must be reviewed as a separate scope; it must preserve
the original task/grant/actions and must not weaken that single-use rule or
reset the financial ledger. At most one further call would remain inside the
original two-call envelope after the observed first call. That is a proposed
recovery bound, not permission to execute it.
