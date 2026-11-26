# Attachment reference Inbox — local development, not installed

Owner asked to continue Stage2 after successful phone voice -> personal task.
Bounded slice: receive owner-private Telegram photos/documents with captions;
retain checked references in existing TelegramInbox/Audit, reply clearly, and
reopen from existing /requests and /request. No new table, service or dependency.
Base0fdb1b567e06add7574e2a3e66078f3ab25fbc3b on codex/undated-release-review,
preserving unmerged PR121/120 chain. Production remains source75776b0.

## Behavior and limits

Only owner private messages, same authorization and audit/outbox/idempotency.
Photos retain largest supplied size reference, not duplicate resolution records.
Documents retain original display filename (never used as filesystem path),
caption, Telegram message ID, file ID/unique ID and reported size. Limit10MiB;
strict bounded field validation, known-secret checks before durable content intake.
Invalid owner attachments receive a fixed explanation without retaining or echoing
filename/caption/file IDs; foreign messages still reject before admission.
Repeated update creates one saved item and one acknowledgement; changed payload
with same update ID is rejected. Existing project picker, queue, assignment and
archive/restore readers use the same checked immutable source. Captions are data:
/stop, reminders, AI instructions or code in a caption never become commands.
No file download, binary persistence, OCR, document extraction, URL fetch,
execution, model call, calendar write or new reminder. No personal task inferred
from an attached document's caption. User-visible receipt explicitly says the
reference/caption were saved, contents not read, original must remain in Telegram.

This is NOT full document storage or attachment backup. A DB backup retains the
reference/metadata, not the file bytes; Telegram availability/deletion still
matters. Search by contents and independent encrypted binary custody require a
separate bounded follow-up with retention/limits/recovery acceptance. Albums are
independent message records; no inferred grouping or summary. No admin expansion.
Invalid photo/document metadata returns fixed owner feedback and the next valid
message still processes in the same poll. Other unsupported media keeps existing
rejection behavior; support is not claimed.

## Checks

Local10 metadata/summary/secret/oversize/ambiguous-media tests PASS; Ruff whole
source/tests/scripts/infra, contract export, scoped Bandit and diff check PASS.
Four PostgreSQL/configured-polling cases PASS in final CI: durable reopen, duplicate,
authority unchanged, foreign rejection before intake, fixed secret-content rejection
without content retention/echo, caption not command,
no getFile/download calls. No local DB/container runtime assumed available.
Mock transport and PG acceptance do not prove live phone attachments/VPS.
Final source03b4aab1d2968f469679571365f191985b92821a / Draft PR122.
Source bundle.runtime/attachment-inbox-release/source.bundle SHA256
EAABAFC9EFBB6E99A85EFE02380B089FB43F30833008C9EB08CB52227B193737.
Final CI45785579447 SUCCESS: main2871passed/1skipped/2warnings (542.35s),
infrastructure1014passed, speech44passed; overlapping sets not summed. Earlier
superseded runs not counted. Final cloud verification passed for merge-ref
4ad9a449f896da7e888776d81976111071371d3f. Head/base/merge freshly checked;
head and merge share tree301604219ccb5c4e6bf58e5d52d3cd495c426146.
Five additional normalization probes passed without DB/network/model: valid owner,
secret caption fixed rejection, invalid boolean size, malformed Unicode caption,
foreign sender denial. Local Docker engine checked unavailable; PG cases use CI.
Final CI reconciled against the final PR head/merge-ref. No live VPS acceptance
or deployment is implied by configured HTTP/PG or cloud container tests.

## Voice quality request

Owner likes current voice path but requests punctuation and long dictation
quality. Preserve source and owner edits separately; no regex guesses of names,
dates, negations or sentence boundaries. Next quality acceptance needs an actual
longer owner recording and confirmed reference. No new speech model/provider,
paid AI or production configuration was enabled in this slice. Do not call the
current short sample a general quality benchmark.

No VPS access, deployment, archive deletion, paid AI, merge or new integrations
performed in this development stage. Stage2 remains open for actual attachment,
failure and broader speech quality acceptance; Stage3 not started.
