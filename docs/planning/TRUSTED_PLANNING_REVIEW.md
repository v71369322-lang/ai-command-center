# Operator evidence and exact live-planning review

`command_center.planning_admission` is a pure, offline precursor to the trusted
live planning gateway in the [local handoff](../handoff/LOCAL_CODEX_2026-11-07.md).
It is separate from the existing closed HTTP-mock configuration. There is no
live client, environment loader, credential path, Telegram callback or runtime
dispatch in this step.

The operator supplies a confirmed Tariff and bounded account, model, funding
and data-sharing evidence references. These are operator attestations, not
provider verification. Evidence expires within 24 hours; no balance or price is
inferred. The reservation upper bound must fit the stated available, daily and
monthly amounts. The actual shared ledger remains responsible for outstanding
reservations and spent amounts in a future approval transaction.

prepare_review returns a quote with the task ID/version, exact request/context,
source revision, whole profile digest, exact Responses document digest, model,
maximum reservation, one call and expiry up to 120 seconds. Only command-center
contexts with admission open are accepted. validate_review checks current
inputs and the exact displayed quote digest; all inputs are revalidated,
including mutable nested tariff fields. The result always forbids business
execution.

Neither function changes F1 state, creates ExternalGrant/ExternalAction,
reserves money or proves an owner click. Quotes can be checked repeatedly;
single-use enforcement belongs to the existing durable F1 approval and external
ledger. A future trusted callback must authenticate the Telegram owner, obtain
the current context/task/profile under the existing Control lock, validate the
quote and atomically compose Store.approve with the narrowed ExternalGrant.
The same binding, expiry, current context, lease/fence/source and global ledger
checks must hold at provider admission. Unknown outcomes cannot be retried.

The runtime broker still rejects saved_request_plan. Existing mock behavior,
provider contract and deployment packages are unchanged. No real profile,
tariff, funding evidence or paid consent has been collected by these tests.

Validation: `python -m pytest tests/test_planning_admission.py -q` (45 passed);
`ruff check src/command_center/planning_admission.py tests/test_planning_admission.py`.
