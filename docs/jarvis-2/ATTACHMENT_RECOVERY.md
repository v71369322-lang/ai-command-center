# Attachment copy custody and recovery — operator runbook

This is a reviewable procedure, NOT authorization to access VPS, export a real
file, decrypt private backups, change production or delete resources. Follow
AGENTS exact source/action/window approval and fresh reconciliation first.

## What is stored and who can read it

Original immutable owner Telegram attachment intake retains filename/caption/
message reference. Binary copies use existing TelegramInbox DATA records with
kindattachment_copy, stateSTORED_ATTACHMENT and a deterministic profile derived
from the original bot profile. No independent authorization grant exists. Audit
anchors original fingerprint, copy fingerprint, byte length and SHA-256. File
bytes are not audit events, AI context, commands, filesystem paths or public API
responses. read_copy requires the original bot profile/source, checked audit,
checked original intake and full stored bytes/hash. Filename is display data.

Copy records are base64 in the same PostgreSQL access boundary as existing
personal data. Base64 does NOT encrypt data. Full PostgreSQL backup is separately
AES-GCM encrypted by the existing operator backup mechanism/key. Telegram services
never receive the host backup key. No new credential or mount is needed.
A successful copy receipt proves DB persistence at that time, not a subsequent
successful backup/offsite copy. /request shows registration/pending/failure,
without loading the raw binary payload on the message-polling path.

## Quota and runtime acceptance before activation

10MiB/file,16MiB raw total,32 files/bot, shared1000 Inbox rows. Encoding adds about
one third to JSON size; PostgreSQL custom-dump compression is not a promised ratio.
Preflight current dump size plus full possible binary growth, three operation
backups, encrypted recovery delta, existing unchanged quota and free filesystem
reserve. Last known server backup quota was nearly full; that old report is not
current evidence. No quota increase, auto eviction or arbitrary archive deletion.
Any retention operation requires exact files/hashes, protected verified PC copies,
latest-pointer guard, recovery plan and fresh owner approval.

Exact-source images and existing prepare/inspect/approval/apply/postcheck only.
Existing1GiB speech service also hosts copier in assistant mode. Voice has
priority, file download outside admission lock; check actual cgroup peak memory,
poller delay, one small real file, maximum supported file/total quota boundaries
and recovery under the approved scope. Local Python and cloud rootful tests do
not prove VPS/rootless resources or phone acceptance. Do not claim latency or
memory bounds from the configured limits alone. Failed copy keeps reference,
announces failure once and requires owner resend; no hidden unbounded retries.

## Recovery of bytes

1. Keep exact source bundle/images, manifests, journals, connection/config custody
   and encrypted pre/post backups outside Git in the established protected vault.
   Do not copy keys/tokens/file IDs/private contents into chat, logs or prompts.
2. Independently decrypt/checksum the encrypted dump in memory using the existing
   operator key flow; restore into a NEW isolated networkless PostgreSQL instance,
   never over primary. Revoke execution/owner sessions and set halted/recovery
   interlock with normal recovery tooling. Verify whole audit chain/checkpoint.
3. Select source using an owner-authorized exact request ID and verified original
   bot profile from trusted deployment/intake evidence, never a caption-supplied
   profile. Use the restored exact source's read_copy(store, session, source,
   profile=verified_profile). Reads are allowed during recovery, writes/downloads
   are not. This checks original source and copied bytes/fingerprint without any
   Telegram request. Re-check returned length/SHA against the copied audit anchor.
4. If an actual file export is approved, write ONLY to an explicitly chosen new
   private operator output, outside Git, with exclusive creation and restrictive
   permissions/ACL. Never use Telegram filename as a path. Do not print bytes or
   open/execute content. Export files are personal-data artifacts, not test logs.
5. Keep evidence of byte equality, source/backup pins and recovery interlock. A
   cloud public fixture roundtrip is not private offsite RPO/RTO evidence.

Telegram re-send/download UI, OCR and content extraction are not part of this
slice. Trusted read_copy provides actual bytes for operator recovery. User-managed
retention/erase and copy cleanup remain explicit future operations; archive only
hides a source from the Inbox and intentionally preserves its binary copy.

## Rollback compatibility is more than migration hash equality

models.py/admin.py are unchanged, so existing schema/migration pin is preserved.
That does NOT make all earlier code compatible with the new attachment intent.
Production75776b0 predates attachment readers: after new attachments arrive it
cannot safely render those records in Inbox views. Do NOT roll back to75776b0
and do NOT delete/change intake or audit records to force compatibility. Even a
halted new poller can have received attachment references during activation.

PR122/source03b4aab reads reference metadata and naturally excludes DATA records;
PR123 is needed for binary-copy recovery/checking. Any proposed rollback must be
reviewed against actual stored formats/outbox and the exact approved target.
If install is uncertain, read-only reconcile both journals/runtime first; repair
forward or use stock reconcile ONLY with matching preconditions. Keep independent
stop/backup access. No automatic fallback or alternate install path is added.
