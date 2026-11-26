# Personal tasks, ideas and Telegram reminders — local implementation

Owner approved next bounded development step after PR119 Calendar acceptance.
No new deployment, server maintenance, paid AI, external access or merge granted.
Base is checked codex/calendar-card-fix-activation-review at1947749, retaining
the unmerged PR119 dependency. Installed VPS remains b808144; no VPS operations
or new Calendar writes performed for this development step.

## User behavior implemented

- «Купить упаковку для кондитерской» saves an active personal task without an
  invented deadline, assigns existing vanilla-sugar category through existing
  project_inbox authority, and returns its number. It does not buy anything.
- «Идея: новая подарочная коробка» saves an idea without a deadline or execution.
  «Мои идеи», «Мои задачи», «Мои заметки», «Мои напоминания» show separate lists.
- «Напомни завтра в11 позвонить поставщику» requires configured owner timezone,
  explicit date/time/text, pins relative dates at original intake (original voice
  intake for accepted speech), and queues a Telegram notification when due.
  No Google event, model call or business action. Invalid/past/ambiguous inputs
  return a clear refusal and example instead of inventing a schedule.
- «Готово №N», «Отложи задачу №N», «Возобнови задачу №N» and bounded delegated,
  waiting/blocked transitions update personal status. «Это идея №N», «Это задача
  №N», «Это заметка №N» correct classification without rewriting the source.
  «Раздел №N: автосервис» corrects existing project classification. Saved records
  get a short plain-text receipt instead of forcing project-picker interaction.
  Ideas/notes cannot be completed as tasks without explicit reclassification.
- «Что у меня сегодня?» / existing agenda today/tomorrow/week combine existing
  Google read result with bounded local task/reminder lists. Missing/unavailable
  Google remains explicit; local records remain visible. Undated tasks stay
  explicitly undated, deferred/blocked state stays visible.
- Voice uses existing observed owner transcription confirmation. No personal
  task/reminder is inferred from raw ASR before acceptance. Card explains that
  accepting a dated reminder schedules Telegram notification; Google meetings
  still need separate existing calendar confirmation.

## Reuse and boundaries

One new personal_inbox module over existing checked TelegramInbox records,
versioned Audit events and TelegramDelivery outbox. No tables/migrations,
dependencies, services, AI provider or independent authority mechanism.
Project classifier split into shared classify_locked plus unchanged public
transaction wrapper so intake + metadata + existing project assignment + reply
commit atomically under existing global lock/audit chain.

Only Jarvis assistant mode interprets personal phrases. Developer-mode intake
is preserved. Original source/fingerprint, owner/profile and history versions
are checked; archived intake cannot keep producing reminders. Existing project
picker remains available through existing request view with its observed-card
protections; the natural explicit project edit uses the same owner classifier.
One unambiguous explicit project hint selects an EXISTING category; multiple
project hints stay unassigned. No access to project code/CRM or executor granted.

Due reminders use the existing Telegram polling loop/outbox, not a scheduler
service. A selective due-record query avoids walking all tasks/ideas on every
poll. Enqueue is once per reminder/source ID, serialized under existing lock;
the durable queued event excludes re-enqueue across restarts. Unknown sends
inherit existing UNCERTAIN/no-blind-retry behavior. Just before HTTP, personal
reminder validity is rechecked: completed, reclassified, archived, changed or
stopped records suppress a still-pending notification. Sending cannot recall a
notification already handed to Telegram. A queued/suppressed/sent one-shot is
not recreated by merely toggling status; new reminder requires a new message.

## Validation and limits

21 local pure parser/date/project checks PASS, Ruff/contract export/scoped
Bandit PASS. Local Docker daemon unavailable; PostgreSQL/outbox integration
tests MUST pass final Linux CI before release. Tests added for configured
transport polling, atomic project assignment, original request preservation,
task completion/classification, voice observed confirmation, stop guard,
due delivery once across bridge restart, pending-notification suppression,
foreign profiles, changed source, missing dates/timezone and offline agenda.
Synthetic HTTP is NOT live Telegram/voice acceptance.

Final checked source e238589a1585dd8fb3dd3c2b7a1dc15294454213, PR120 Draft,
CI45768463214 SUCCESS:2842PASS/1skipped/1warning, infrastructure1014PASS,
speech44PASS plus pinned image/import smoke, full security/container gates.
The33 new tests (including12 PostgreSQL/integration tests) passed in the main
suite. Head and merge-ref2ace45a203784bfad490bd03f16cbd7469bfbd28 have identical
tree2a82504ee6758493718b1f08f8e8fe868a50e8e1; metadata rechecked after CI.
Existing assistant-policy test now expects an explicit classified idea receipt
while retaining every developer route/permission prohibition. Receipt is plain
text; project picker remains optional in the original request view. Natural
project correction uses existing owner assignment checks. Help and reminders
menu reflect the new personal scenario. No production/server operation in this
development step. [Exact release review](JARVIS_PERSONAL_INBOX_RELEASE_2026-11-26.md).

This is a bounded deterministic first slice, not general natural-language AI.
No splitting of long mixed messages; no guessed project/deadline. Reminder
grammar: today/tomorrow/day-after/ISOdate + numeric hour or HH:MM + text, up to
366days. Ambiguity/conditional alternatives rejected. Incomplete reminder asks
for the complete natural phrase; it does not silently attach the next unrelated
message. Changing reminder time, full-text search, general task text editing,
dynamic project registry and full daily voice quality acceptance remain later
work. Existing storage/history/delivery capacity limits retained.

Stage2/6 remains unfinished. Next: final exact head/merge-ref CI, review release,
then separate exact deployment approval and new quota-compliant backup retention
plan (current VPS free backup quota1042342bytes per last installed handoff).
Real task/idea/reminder/voice and restart acceptance must follow installation;
do not assert this code is already available in the bot.
