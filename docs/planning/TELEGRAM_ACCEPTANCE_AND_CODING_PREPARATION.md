# Telegram content confirmation and isolated-coding preparation

This composes [content acceptance](PLAN_CONTENT_ACCEPTANCE.md) with the existing
private-owner Telegram inbox, durable delivery and F1 Control transaction. There
is no new execution authority or alternative permissions mechanism.

## Owner commands

- `/plan_accept NUMBER` queues every part of the latest current Command Center
  plan, followed by a fixed **accept content only** button. The card pins version,
  document/context/setup digest, declared baseline, source, owner/profile/bot
  connection and message identity. All parts must have exact queued and observed
  SENT anchors. Delivery is evidence of sending, not proof the human read it.
- `/plan_acceptance NUMBER` reads `MISSING`, `CURRENT` or `STALE` content acceptance.
- `/coding_prepare NUMBER {JSON}` records an explicitly scoped, non-runnable coding
  specification after current content acceptance. JSON contains `allowed_files`
  and `test_files`, optionally bounded `max_seconds`, `max_iterations` and
  `max_diff_bytes`. The owner selects actual paths; examples are never defaults.
  The current acceptance digest is frozen in the original received-command audit
  anchor. Pending/restarted commands cannot retarget a newer accepted plan.
- `/coding_prepare NUMBER` reads preparation status or explains the required
  explicit scope. It does not invent files, fetch a repository or run anything.

The existing 2000-byte incoming text limit applies to commands. API alternatives
allow the same bounded structure through existing owner/CSRF authentication.
No new reply keyboard, URL action or public administrative UI is added.

## Exact displayed content and replay

The full summary, steps and acceptance criteria are paginated without truncation.
Each page fits the existing UTF-8 text and Bot API envelope bounds. Original
owner-authored/unverified-AI provenance is retained. The final card is bounded to
300 seconds from the original received command, never from a replay or late click.
Callback nonce, source/connection, original inbox anchor, exact page/card bodies,
message ID and observed deliveries are rechecked under the existing Control lock.
Fabricated SENT rows, unobserved/UNCERTAIN pages and altered displays cannot count.

Expired or stale cards and missing delivery proof produce an explicit negative
reply without acceptance. The deadline and connection are rechecked before commit;
expiry/revocation during finalization rolls the acceptance/consumption/reply back.
The existing append-only content receipt and card consumption are atomic.
Duplicates, restart and competing clicks cannot create a second receipt or grant.
Uncertain sends are not automatically repeated; request a new card explicitly.

## Prepared specification, not an executable task

The current F2 contract supports only its fixed synthetic repository exercise.
It is not an executor for the real Command Center repository. This stage therefore
records `PREPARED_NOT_RUNNABLE` specifications in the existing audit, **not Task,
Approval, ExternalGrant or executor Outbox rows**. TelegramDelivery is used only
for the owner's pages and replies. The preparation cannot become runnable through
the existing generic task approval route.

Each specification pins the current accepted reference and declared repository
revision, explicit Python files and test paths, bounded iterations/time/diff, and
literal verification argv. It permits only canonical relative paths under
`src/command_center/` or `tests/`; tests start with `tests/test_`. Absolute/host
paths, traversal, hidden components, duplicate paths, command fragments and
credential-shaped text are rejected. No free-form shell, provider, environment,
credential path or permission override is accepted.

The declared isolation policy requires rootless/non-root, no privileges, all
capabilities dropped, no-new-privileges, no network/credentials/host-path mounts,
read-only base and ephemeral workspace; caps are 256 MiB, 0.5 CPU and 64 pids.
These are requirements for a future trusted adapter, not proof a runtime exists.
Verification commands are server-derived argv for Ruff and selected pytest files.
Actual repository access, workspace/image/runtime binding, F1 task/approval and
independent verification remain blocking checks. Publication is separately gated.

Owner API:

- `POST /api/project-inbox/coding/preparation-preview`: request ID, expected current
  acceptance digest and explicit scope → exact specification/digest, no write.
- `POST /api/project-inbox/coding/preparation`: same input plus reviewed
  `expected_spec_digest` → append-only idempotent preparation.
- `GET /api/project-inbox/coding/preparation?request_id=...`: latest preparation
  or `MISSING`/`STALE`, with all authority/verification flags false.

Receipts are bounded to 100 and semantically revalidated against original content
acceptance, source, scope and the fixed isolation/check policy. Rehashed policy or
command changes fail closed. A changed context invalidates the preparation. An
old idempotent save does not select an executable scope; none exists at this stage.

No actual coding, paid AI, repository probe, verifier, GitHub publication, resume,
merge or deployment is performed. Future dispatch must add a separately reviewed
real-repository adapter on the existing F1 broker/lease/fencing/financial path.
Tests use actual PostgreSQL and mock Bot API/fixture plans, not live acceptance.
