# Exact owner confirmation for one advisory AI plan

Continuation of [reviewed F1 approval](../planning/REVIEWED_F1_APPROVAL.md).
`/plan_authorize NUMBER` requests a card for an existing `/plan_prepare NUMBER`
task in this Telegram profile. Requesting or delivering the card grants nothing.
This implementation is local development, not a deployed production command.

## Card and consent

The card shows the full saved request, AI Commander project, operator-provided
model, maximum reservation in rubles, task/version, context digest, source and
absolute UTC deadline. The maximum is the confirmed tariff's one-call bound,
not a provider-enforced billing cutoff. Only an advisory `/plan NUMBER` draft
is in scope; coding, execution and publication are excluded. There is no
automatic retry on an unknown provider outcome.

The deadline is at most 120 seconds from receipt of the command, not from a
later delivery or click. Pending replay after a restart cannot refresh it.
The complete request must fit the unchanged 8192-byte Bot API envelope; there
is no silent truncation. The maximum 2000-byte Cyrillic request is tested.

An owner click must be in the bound private chat, reference the exact bot
message and nonce, and match an append-only issued-card event in the same
profile/source/connection. The exact delivery body must have queued and
observed SENT anchors. NEW, SENDING, UNCERTAIN or a fabricated SENT state is
insufficient. Forwarded, foreign-owner/group, different-message and modified
body/button callbacks fail closed. Transport permits only the exact planning
keyboard; it does not enable arbitrary URLs, buttons or callbacks.

The trusted callback repeats current profile/context/expiry checks and calls
the existing PlanningApproval/Store.approve path. Card consumption, reply,
Approval, ExternalGrant and Outbox commit atomically under the same F1 lock.
A failed commit leaves no consumed card or authority. Duplicate updates,
restarts and concurrent clicks cannot issue a second grant. The original
quote deadline also caps the resulting F1 approval.

## Protected evidence profile

Default is disabled. Both `F1_PLANNING_PROFILE_FILE` and
`F1_PLANNING_PROFILE_SHA256` must be explicitly supplied by a future reviewed
deployment. The loader requires exact raw-byte SHA256, an absolute private
file in a private owned directory, regular file/single hardlink/no symlink,
owner-only access and at most 16384 bytes. Duplicate JSON keys and extra fields
(including credential_files) are rejected. Errors do not reveal file contents.
The profile contains operator-reviewed account/model/tariff/funding/data-sharing
evidence and its bounded freshness window. It contains no provider credential.
No price, model, balance or consent is inferred from prior experiments.

The loader is reread at issuance and confirmation, including inside the F1
transaction. Missing, changed or expired evidence invalidates approval. Request
lookup uses the existing exact-context planning idempotency key, so another
profile's request or an obsolete task cannot become the current target.

## Boundaries and validation

No production profile/mount/env binding has been installed. Existing release
packages and default settings are unchanged. No provider client/credential is
constructed by this flow. The resulting grant still has empty secret_refs;
production broker still rejects planning before claim. A real provider call
needs a separately reviewed protected live gateway/runtime binding and new
exact consent appropriate to that binding; these staged grants must not be
reused to enable it silently.

Local Linux/PG validation includes exact review, atomic approval, existing mock
planning gateway, pinned loader, new Telegram cards, planning preparation and
the earlier paid-experiment consent flow. Delivery loss, rollback/replay,
concurrency, changed conditions, maximum text, private-file custody and strict
keyboard scope are covered. All network/provider fixtures are synthetic.
The core locked Linux/PG scope passed 251 cases with one existing
Starlette/httpx warning; menu/help delivery is checked separately after keeping
the expanded help inside the unchanged transport limit. Full Ruff,
git diff --check and locked Linux API contract check passed. An unlocked Windows
environment reported contract drift; no contract was regenerated from it.
Final menu/help regression scope: 29 passed, reported separately. Exact-source
CI is recorded by the resulting dependent Draft PR.
