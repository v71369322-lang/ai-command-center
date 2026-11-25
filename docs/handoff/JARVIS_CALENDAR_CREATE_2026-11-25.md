# Confirmed meeting creation — phase2/6, local development

Owner «Давай» approved implementing the next slice after the live phone ASR
check. This does not authorize a new server deployment, Google scope expansion,
Apps Script publication, live event creation, paid AI or backup deletion.
Installed runtime remains1e5dd99 / PR117; Calendar remains read-only there.

## User flow implemented

Natural text such as a meeting request without a time enters one short durable
dialogue, not a developer task. Relative dates are resolved from inbox receipt
time in the configured timezone. Missing date, clock and duration are requested;
they are not invented. A follow-up such as `В 15:00 на 30 минут` completes the
draft. An unrelated idea is still saved normally. `отмена` closes the dialogue.
One pending dialogue per Telegram profile,10minute lifetime; changed timezone,
epoch or source requires a new full request. The parser is deliberately bounded:
today/tomorrow/day after tomorrow/ISO date, explicit HH:MM, numeric minutes/hours.
It is not unrestricted natural-language understanding. Unsupported/ambiguous
details are not converted into an external write.

Voice still requires the observed readback card and owner Save before its text
can enter the same dialogue. The ASR result itself never authorizes a meeting.
Completed drafts show title, exact start/end, timezone and the visible20minute
default reminder, then use the existing owner confirmation card. Without a
separately configured writer, confirmation remains local only.

## Existing authority and durable state reused

Existing calendar_drafts, calendar_sync, owner authorization, Telegram observed
delivery binding and global transaction discipline remain authoritative. No
new DB tables, independent grants, AI calls or background service. Draft/card
creation now shares one authority transaction, including accepted voice routing.

Write cards bind the exact writer profile, current calendar binding version,
source, control epoch and10minute deadline. Stop/recovery, stale/unobserved cards,
key/calendar/profile changes block a write. Publication reconstructs the exact
existing prepared request. Before network I/O, an atomic claim durably changes
PREPARED to UNKNOWN. Only its first claimant may create; another callback or a
restart can only GET the deterministic event ID. ABSENT/timeout is not permission
to create again. Verified responses use existing SYNCED evidence and deduplication.

## Separate opt-in Google bridge

`infra/google-calendar-create` is a NEW local script package. Existing read-only
`infra/google-calendar/Bridge.gs` and its Google deployment are unchanged.
The create/get bridge uses a distinct HMAC purpose, connection and key, signs
the explicit calendar ID (not the account-dependent primary alias) and document hash, admits only create/get and one fixed calendar
from ScriptProperties, and calls only the fixed Google Calendar API origin.
TLS checks remain enabled; bearer credentials stay inside Apps Script and are
not returned to Telegram/VPS/AI. No update/delete/invite/attachments/guest writes.
Event ID is the draft UUID without hyphens, with private draft/document binding;
existing conflicting content is rejected. Lost insert responses are read back.
Google event time normalization is checked by instants, then projected back to
the exact confirmed timezone/offset. No raw provider error logging.

Separate ScriptWriteProfile/ScriptWriteConfig and optional runtime CLI arguments
are source/owner/config pinned. Existing read-only profile serialization and
CLI are unchanged. Optional nested `calendar_script.write` deployment binding
mounts only two separate read-only files into Telegram; API/voice/developer
containers receive no write key. Custody, path, fingerprint, distinct key and
connection checks remain mandatory. Existing prepare/inspect/exact install
interlocks cover the exact expanded bundle; do not replace them with compose up.

## Validation

Local cross-language transport/parser + existing read bridge:55 passed.
Ruff, contract export checks and changed-source Bandit medium/high passed.
New PostgreSQL dialogue/publisher/callback and Linux custody tests are included;
local Docker daemon is unavailable and Windows cannot import fcntl. Final Linux
CI is required, not assumed. Node harness simulates Google entirely in memory;
it is not a real Google acceptance or permission grant.

## Remaining activation gates

1. Final source HEAD/PR merge-ref CI, review and exact release package.
2. Concrete owner approval for selected Google calendar and new create scope,
   separate script publication/configuration, exact application release and one
   explicit test meeting. Present those concrete artifacts before approval.
3. Real owner Google consent/passkey when required. Do not bypass it. Verify
   Calendar API availability and selected calendar ownership; script code alone
   does not prove API activation. Install only the approved script version/key.
4. Provision protected separate key/config and existing calendar_sync owner
   binding metadata for that calendar/key fingerprint. Never seed fake owner
   Telegram messages or substitute audit rows. Existing read bridge is retained.
5. Current backup quota has only777679bytes free. A fresh full backup cannot fit.
   Obtain an exact retention/archive plan approval after checking retained PC
   recovery copies; do not delete or raise quota implicitly.
6. Fresh read-only server reconciliation, checked pre-update backup/restore,
   stock prepare/inspect/exact install/postcheck. No reuse of expired PR117 scope.
7. Real voice→readback→clarification→confirmation→one visible Google event,
   restart/repeated confirmation without duplication, and existing agenda read.
   Do not claim phase2 complete before tasks/reminders and overall acceptance.

Primary implementation references:
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/apps-script/reference/url-fetch/url-fetch-app
