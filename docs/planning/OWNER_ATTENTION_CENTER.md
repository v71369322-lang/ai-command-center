# Owner attention center

The first slice gives the owner one read-only view of work that still needs a
decision. It aggregates existing authoritative state and creates no second task
or notification authority.

## Included

- halted or recovery control state;
- tasks in `RECONCILING`, `CANCEL_REQUESTED`, `WAITING_APPROVAL` or `FAILED`;
- saved requests still in `NEEDS_PLANNING`;
- unassigned and per-project request counts;
- a bounded ordered list for the web control center.

The endpoint is owner-only, validates the audit chain and returns counts rather
than request bodies. Reading it does not create a task, approval, outbox row,
provider call, project access or execution grant.

## Scheduled Telegram summaries

The owner can store a versioned schedule with an IANA timezone, one to three
daily report times and quiet hours. The schedule is disabled until explicitly
enabled. Configuration is stored in the existing hash-chained audit ledger with
optimistic versioning and idempotency; no schema migration or second authority
is introduced.

The active Telegram bridge collects the latest due non-quiet slot and queues a
bounded summary through the existing durable `TelegramDelivery` path. The slot
and profile provide restart-safe deduplication. Unknown sends retain the existing
`UNCERTAIN` semantics. Collection does not resume tasks, authorize AI, or contact
project systems.

Each item also carries deterministic severity, urgency, confidence and impact
metadata derived from authoritative local state. A later scheduled slot is
recorded but does not send another Telegram message when the aggregate is
unchanged. A changed aggregate is delivered at the next due slot. A critical
control/reconciliation condition may use a due report slot during quiet hours;
the audit receipt records that bypass. These rules do not create escalation or
execution authority.

The owner view exposes up to five recent report receipts: local schedule slot,
queued or unchanged-suppressed outcome, durable delivery state, schedule version,
and critical quiet-hours bypass. It omits Telegram profile hashes, delivery IDs,
message bodies and request text. `UNCERTAIN` is shown as an unknown delivery
result and is never rewritten to success by a read.

When reminders are enabled, collection records aggregate state transitions. A
new critical recovery/reconciliation aggregate queues one proactive Telegram
notification immediately, including during quiet hours, and records the exact
observation sequence. Repeated polls of the same aggregate do not queue another
message. A return to normal state is observed without a notification, allowing a
later recurrence of the same critical aggregate to produce a new, separately
deduplicated notification.

## Explicitly not connected

- AI planning of saved requests;
- CRM/repository access for project labels;
- escalation or automatic action based on a reminder.

The UI states these gaps directly. Merely opening the summary or choosing a
schedule cannot authorize AI, resume tasks or access a project system.
