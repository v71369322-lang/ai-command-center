# Telegram agenda runtime integration, 24 November 2026

Depends on PR110 exactf38069ff6eaa04c7454fd9e9fc908e95b7f40783; no merge,
VPS access/deployment, Google grant or paid calls in this continuation.

## Result

Telegram now supports bounded deterministic personal-calendar queries:
«что у меня сегодня?», «что у меня завтра?», «расписание на сегодня/завтра/неделю»
and /agenda [сегодня|завтра|неделя]. Other text keeps its existing Inbox behavior.
Week means the next seven days, beginning at today's midnight in Europe/Moscow.
This is primary-calendar-only, explicitly stated in each successful reply.
It is not a multi-calendar availability search or AI natural-language parser.

An optional Calendar client is injected through TelegramService/TelegramBridge.
It must match the authenticated private Telegram owner and exact source revision.
The protected runtime config has an exact externally supplied approval digest;
owner, source, enabled flag and client identity are checked before credential access.
Disabled-by-default service CLI options are --calendar-config and --approved-calendar;
both are required together. No environment/cookie/token autodiscovery.

The private config is CalendarRuntimeConfig: schema_version1, profile(CalendarAccess),
client_id, custody_directory. The0700 custody directory contains dedicated0600 files:
calendar.key(32bytes), calendar.enc(AES-GCM archive) and oauth-client.json with only
client_id and client_secret (null permitted for a public client). All are operator
provisioned, never generated or granted by a Telegram message. Do not put these files
in Git. The approved config also binds the custody directory. A bad explicitly supplied
startup config fails closed; omission leaves the prior Telegram-only runtime intact.

Agenda fetch runs outside the global Control/audit transaction. Before contact it
checks guard/audit and refuses normal stop/recovery. After contact it checks guard,
stop/recovery and epoch again; a changed epoch discards the provider data. No event
write, model call, F1 task/grant/dispatch or calendar_sync binding is created.
Only the existing owner delivery stores the bounded plain-text result; audit records
period/status and no event contents. Duplicate completed Updates reuse their receipt.
Crashes/concurrent pending readers may repeat a read, never an event mutation.

Replies show up to15 events, timezone and an explicit partial-result warning when
needed. All-day events and malformed records are distinguished; private provider
errors become a generic unavailable reply. No credentials, callback URLs or provider
error bodies are included. Google HTTP uses the existing bounded timeout; this is
outside the DB lock, but remains a synchronous request in the Telegram poller.

## Validation checkpoint

Focused PostgreSQL/Telegram/assistant-policy and runtime tests:110 passed. The
polling-loop Calendar test is also checked independently; repeat-run totals are
not added together.
Ruff and Bandit medium/high checks passed for the new runtime/agenda modules.
An initial broader service run stopped because the local Docker executor prerequisite
was absent (verified_no_effect), not because of Calendar logic. The exact unchanged
executor was built from archived sourcef38069f, without relabelling an existing image;
Docker socket access is confined to the local regression harness. The complete
focused rerun passed, including the prior failing executor/service scenario.
These local checks are not live Google/VPS acceptance or a pinned application release.

PR109 CI45365268198 completed SUCCESS for94fed29; its merge-ref
2d7878f8c3920601b54a4bb7e41d1cbe9c95f2fd remains unchanged from the equal-tree
check recorded in the preceding handoff. PR110 CI45366956138 still running.

## Live activation remains separate

No OAuth client, live credentials or dedicated calendar has been provisioned here.
The Windows-browser-to-Linux protected enrollment/operator bootstrap is still needed.
The new runtime is not yet mounted/enabled in a deployment candidate. Before use:
finish enrollment and dedicated-calendar verification; obtain concrete Google consent;
check final source/merge-ref CI; prepare a backup and an exact approved installation;
then perform a real owner Telegram schedule read. Existing Google events must remain
unchanged. Publication/deduplication workers and writes are deliberately not activated
by this read-only integration; existing draft confirmations remain local.
