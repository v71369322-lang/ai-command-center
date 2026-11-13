# Telegram review of one offline coding task

This continues [the isolated F1 adapter](ISOLATED_CODING_F1.md). It adds owner review
of an **already prepared F1 task**, not repository upload, AI generation, a new
permission system or a deployment operation.

## Owner flow

1. Prepare and accept the plan content, choose the coding specification and create
   its exact `WAITING_APPROVAL` F1 task using the prior operator/API workflow.
2. In the bound private owner chat send `/coding_authorize UUID`. The original
   received-command audit freezes task ID/version/payload hash/epoch/source and
   specification/request identity. A delayed command cannot select a later version
   or become eligible after the task changes. An unavailable task produces an
   explicit reply; it never creates a task, approval or execution.
3. Read every review part: all baseline source and immutable test bytes are shown,
   followed by the complete diff of explicit replacements. Scope, exact declared
   Git commit, fixed checks and required isolation are included. Codepoints and
   long Cyrillic lines are preserved, with no truncated preview. At most 50 parts
   fit the unchanged text/JSON envelopes. Remote repository membership/access is
   explicitly unverified. Rootless runtime readiness is checked later by broker;
   delivery of this card does not establish it.
4. Press the fixed **Разрешить один offline coding-запуск** button only for the
   displayed operation. The card lasts five minutes from original intake, never
   from a replay. F1 approval is at most 120 seconds from the click and ends no
   later than the original card deadline. Late review can leave too little time
   for execution; expiry does not authorize an automatic repeat.
5. `/coding_status UUID` reads this task without admission/resume/approval. It
   reports the F1 state and confirms a result only when exact artifact/hash,
   verifier audit/fence/source and expected report shape agree. F1 state alone is
   not proof of actual execution or container stop. `/cancel UUID` and `/stop`
   retain their existing F1 semantics. Generic `/tasks` and `/status` retain their
   previous synthetic-task scope; no misleading synthetic readback is added here.

## Atomic authority and delivery proof

Every review part and final button must match exact queued and observed SENT
anchors, source/profile/owner/connection, expected body hash and message identity.
Mutable `SENT` alone, uncertain/missing/modified pages and another message cannot
authorize anything. Delivery proves sending, not that a person read the content.
Wrong owner/group/forwarded inputs remain rejected by the existing normalizer.
No URL button, second button, changed label, arbitrary callback or new Bot API
method is allowed. Transport envelopes, secret screening and uncertain-send policy
are unchanged. Explicitly request a new card after an uncertain delivery.

Under the existing Control transaction the callback rechecks original intake,
nonce/card binding, current exact F1 task and latest accepted specification, expiry,
all delivered review content and the bot connection. It then uses the same F1
approval implementation through an internal locked composition helper. Approval,
Outbox, card consumption and reply commit together. Reply failure, revocation or
expiry during finalization rolls all of them back. Approval expiry is checked
again before commit even when the review card itself has not expired yet.
Concurrent/repeated clicks consume once. Changed plan/setup/task version, normal
stop, cancellation or independent earlier approval prevents card reuse/retargeting.

The waiting task's immutable payload already fixes zero provider cost, no network
or credentials, explicit patch/check scope and required sandbox limits. This
confirmation permits that isolated execution through F1. It does not authorize
AI/provider calls, API spending, remote repository access, publishing, merge or
deployment. No ExternalGrant or financial/provider ledger entry is installed.
Only the existing broker can claim and launch; source pinning, watchdog, rootless
preflight, leases/fencing and independent verification remain unchanged.

Status is scoped to this private bot profile using the immutable creation event
and payload hash. It remains readable when plan context is stale, and does not
attempt to fix, approve or execute the task. Unconfirmed artifacts are not exposed
as success. No arbitrary code/log/credential text is echoed in the status reply.

## Validation boundaries

Tests use actual PostgreSQL and existing mock Bot API delivery. They exercise
observed complete/multipart review, uncertain/fabricated/modified delivery, wrong
message/owner/profile, stale state/version, finalization rollback/expiry/revocation,
concurrency/replay, exact keyboard, read-only status and forged result rejection.
The existing public F1 approval API delegates to the same implementation; legacy
planning approvals are included in regression. No real Telegram message, provider
call, VPS operation, rootless live execution or publication is performed here.
