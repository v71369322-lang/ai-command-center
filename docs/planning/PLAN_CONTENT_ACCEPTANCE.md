# Pinned owner acceptance of plan content

This is the first bounded part of the handoff's plan-acceptance → isolated-coding
sequence. It records which content the owner accepted. It is not F1 task
approval, an ExternalGrant, repository access, coding preparation, spending,
verification, publication or deployment permission. There is no new authority
mechanism and nothing consumes this receipt to dispatch work.

Only Command Center is supported. Other project names remain context, not grants.
Existing owner authentication, password/OIDC session CSRF rules and no-store
responses apply. No Telegram command or web execution button is enabled here.

## API workflow

1. `GET /api/project-inbox/plan/acceptance-preview?request_id=...` returns the full
   current proposal, a structured reference and its `snapshot_digest`. It writes
   no acceptance. The latest draft must be current, ready for review without
   questions, and the project's setup declaration must be complete.
2. The owner reviews the proposal and its reference. Submit
   `POST /api/project-inbox/plan/acceptance` with only `request_id` and
   `expected_snapshot_digest`. Under the existing Control lock the server checks
   the full audit and rebuilds the reference before appending one receipt.
3. `GET /api/project-inbox/plan/acceptance?request_id=...` returns `MISSING`,
   `CURRENT` or `STALE`. Historical receipts are not overwritten. A newer plan,
   changed setup, assignment, source or control context invalidates currentness.

The reference pins request/context/fingerprint, plan version/proposal ID and
whole document digest, project/setup version and digest, source/control epoch,
declared repository revision and original plan provenance. A hash is an integrity
pin, not proof of an observed Telegram delivery or an owner signature. Internal
callers must already have owner authority; API access uses the existing identity.

The append-only `saved_request_plan_content_accepted` audit entry contains only
the reference, digest and false authority flags; it does not duplicate request
text or proposal content. Readers verify strict shape, original draft and setup
references, provenance and flags, in addition to the whole audit chain. Matching
concurrent/restarted retries return the same receipt. Replays after a context
change fail rather than refreshing consent. Capacity is 100 receipts and cannot
overwrite earlier history.

Content acceptance may be recorded while admission is halted. It cannot clear
halt/recovery or make an old task runnable. The subsequent change of context makes
the acceptance stale. `provider_evidence_verified` remains false for both imported
AI-shaped and owner-authored documents; accepting content does not upgrade its
provenance, quality, billing evidence or setup compatibility.

## Remaining stage

The dependent [Telegram confirmation and coding preparation](TELEGRAM_ACCEPTANCE_AND_CODING_PREPARATION.md)
stage adds observed confirmation and non-runnable specifications. These acceptance
endpoints themselves still do not construct an executable coding task. Future dispatch must independently
check a current content receipt, exact repository capability and source, allowed
files/check commands/resources, and the existing F1 permissions/lease/fencing and
financial interlocks. Execution, provider I/O, verifier and Draft PR publication
remain separate, explicit steps. A CURRENT content receipt alone permits none.

Validation covers actual PostgreSQL serialization, repeat/concurrent requests,
staleness, cross-project/non-owner rejection, CSRF, transaction rollback, capacity,
historical audit and semantically resealed receipt tampering. All provider data
in tests is public synthetic fixture data; no network/provider/credentials are
used by acceptance. Exact scope and CI evidence are in the dependent Draft PR.
