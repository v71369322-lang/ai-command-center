# Observed Telegram content confirmation and coding specification

Branch `codex/telegram-plan-coding-preparation` depends on Draft #97 at exact
`e5795b4ef8f0146004f8c07de505561b35b87bc0`. Parent CI 43194715902 was freshly
rechecked SUCCESS. Origin fetched; main still f5ff8b2, initial tree clean.
No worktree, merge or VPS operation was performed in this stage.

Adds observed owner content confirmation over the previous acceptance contract:
`/plan_accept NUMBER`, full paginated proposal and fixed callback, then
`/plan_acceptance NUMBER`. All pages and card must match immutable expected bodies
and queued/observed SENT anchors in the same source/profile/connection. Nonce,
private owner/message, original command timestamp and five-minute deadline are
checked. Expiry/revocation at finalization rolls back receipt/consumption/reply.
Negative stale/delivery outcomes explain that nothing was accepted. No uncertain
send is retried. API and Telegram share locked helpers on the same Control/audit.

Adds owner-scoped coding specification API and `/coding_prepare NUMBER {JSON}`.
Only explicit canonical Python paths and pytest files under Command Center are
accepted; verification argv and rootless isolation requirements are server-fixed.
Preparation pins the exact accepted reference, source and declared repository
revision. Telegram intake records the current acceptance digest; delayed/restarted
commands cannot retarget newer accepted content. API save requires both exact
acceptance and specification digests. History is bounded, idempotent and validated
against the original acceptance and fixed policy, including rehashed tampering.

This is deliberately a non-runnable specification, not a fake real-repository
F2 task. The current executor supports only its fixed synthetic repository.
Repository capability, actual workspace/image/runtime, F1 task/approval and
independent verifier are blocking checks for the next adapter. No Task, Approval,
ExternalGrant, executor Outbox, provider credential, AI call, execution or publisher
is created. TelegramDelivery only transports owner pages and replies. Existing
API owner/session-CSRF and strict Bot API envelope/keyboard boundaries remain.

Regression uses actual PostgreSQL and public mock Bot API/provider fixtures:
full/partial/fake/uncertain delivery, multi-page Cyrillic content, owner/group/
forwarded scope, wrong message/body, expiry during finalization, rollback and
concurrent clicks; plus owner file limits, path traversal/secret-shaped filenames,
no authority/ledger changes, policy/command tampering, restart/capacity and delayed
command retarget prevention. Earlier broad 367-case run predates final negative
reply/intake-pin adjustments; final changed scope 158 passed, overlapping the
broad run. Ruff, locked Linux OpenAPI render and existing Bandit triage passed.
Exact full CI is recorded in the resulting dependent Draft PR. Do not add
overlapping scopes.

Help descriptions were shortened to keep all commands inside the unchanged
transport envelope; incoming/secret guards and Bot API limits were not raised.
OpenAPI contains additive preparation routes/models. No real Telegram, isolated
coding, verifier or PR publication acceptance is claimed. This code is not deployed.
See [workflow](../planning/TELEGRAM_ACCEPTANCE_AND_CODING_PREPARATION.md).
