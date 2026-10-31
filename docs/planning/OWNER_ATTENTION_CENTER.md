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

## Explicitly not connected

- AI planning of saved requests;
- CRM/repository access for project labels;
- escalation or automatic action based on a reminder.

The UI states these gaps directly. Merely opening the summary or choosing a
schedule cannot authorize AI, resume tasks or access a project system.
