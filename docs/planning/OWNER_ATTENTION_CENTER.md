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

## Explicitly not connected

- automatic reminders and scheduled reports;
- quiet-hours enforcement or an owner timezone;
- AI planning of saved requests;
- CRM/repository access for project labels;
- Telegram push delivery for the summary.

The UI states these gaps directly. A later reminder slice must reuse this summary,
store an owner-selected timezone and schedule, honor quiet hours, deduplicate
durably and use the existing Telegram delivery/outbox authority. Merely opening
the summary or choosing a schedule cannot authorize AI, resume tasks or access a
project system.
