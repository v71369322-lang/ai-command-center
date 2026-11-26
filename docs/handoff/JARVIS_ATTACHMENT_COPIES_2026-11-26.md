# Independent attachment copies — local development, not installed

Owner requested the next Stage2 step after reference Inbox PR122. Base is
78706150bd668e6c58e04f184c1e33fbd3205aa1 on codex/attachment-inbox-review,
which retains unmerged PR122/121/120 dependencies. No server work in this stage.

## Reused architecture

Existing voice-service process performs one attachment copy only after its voice
queue is idle, under the SAME worker advisory leadership, protected profile,
source-bound connection and Control epoch/audit admission. Bot polling does not
download files. New behavior is enabled by the new exact source in assistant-only
runtime; production activation requires a new exact release grant. No new service,
mount, credential, database table, migration, host shell/executor or provider.
Voice profile/model, broker/watchdog boundaries and existing rights preserved.

Checked binary data uses existing persistent TelegramInbox with kind
attachment_copy/stateSTORED_ATTACHMENT, in a deterministic DATA profile namespace
bound to the source bot profile/update number. It is NOT another authorization
profile: every write uses the original bridge/worker control guard and every read
requires original profile, immutable source, audited copy binding and byte digest.
Poller offsets, user Inbox/projects and personal tasks do not interpret these
storage-only records as owner messages/commands. Global1000-row admission remains.
Audit holds metadata/hash, not file bytes; routine audit scans do not serialize
binary payload. No API/public view exposes data64; trusted read_copy returns bytes
with integrity verification. Telegram resend/download UI is not added in this slice.

## Limits, data protection and failure behavior

Maximum10MiB/file,16MiB raw total and32 copies per bot profile. Base64 is encoding,
NOT encryption. DB access custody is the same as existing personal records; the
existing AES-GCM encrypted full PostgreSQL dump includes binary records. No claim
of separate per-file encryption or disk encryption. Prepare future backup quota
for worst-case16MiB extra data before activation; no automatic eviction, quota
increase or deletion. Archiving retains copies. User deletion/retention policy and
independent offsite custody are not silently implemented or claimed proven.

Downloader reuses bounded HTTP response helper, exact approved connection and
fixed Telegram TLS host; metadata binds file ID/unique ID/size, path cannot escape
photos/documents. Redirects, compression, changed size/hash/reference reject.
Raw provider exceptions/URLs/token never enter audit or user replies. Data is
opaque: no OCR, parsing, MIME execution, AI, calendar action or caption command.
Downloads happen outside admission lock; store/hash computed before final write.
Re-check source/profile/epoch and quotas before atomic copy+audit+receipt commit.
Lost COMMIT response reconciles actual stored copy before claiming failure.
A failed download emits one fixed failure receipt and keeps the source reference;
no unbounded automatic retry. Owner can resend later. Normal stop prevents new
work; changed epoch/profile prevents publishing bytes or success. Older-source
references are not automatically backfilled by a new release. Idle scanning has
5second cooldown and voice has priority. No latency/RAM guarantee without VPS
acceptance under actual existing1GiB speech-service limit.

The /request display distinguishes registered copy, pending/unavailable copy and
future backup inclusion; no claim that a fresh production backup already ran.

## Verification

14 local codec/download/bounds/token-safety checks PASS. Ruff whole tree, contract
export, scoped Bandit and diff check PASS. Seven PostgreSQL cases await final CI:
persisted read from fresh DB client without Telegram, unchanged authority/one copy,
corruption and scope refusal, stop/revoked epoch, quota before download, voice
priority, lost COMMIT response, stale source no backfill and shared leadership.
Existing isolated-restore CI drill now seeds one public inert binary DATA record
and metadata audit anchor, encrypts full PG dump, restores into another networkless
PostgreSQL instance and verifies byte equality/fingerprint. It is NOT a real phone
file, independent offsite recovery proof, or activation of a new capability.
No local Docker engine assumed; final CI/head/merge pin review still required.

Production remains75776b0; PR122 references are not installed either. New source
would consolidate both slices. No VPS access/deployment/merge/retention/paid AI or
new integration performed. Stage2 still needs actual phone attachment and recovery/
resource acceptance; general document understanding and punctuation are separate.
