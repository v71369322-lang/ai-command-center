# Owner retrieval of independent attachment copies

Local development; not installed. Stage2 remains in progress.
Base0259ce4549aab013ffb6a55574ae7365015bd843 (PR123), plus preserved installed
release handoff0769810. Separate branchcodex/attachment-retrieval. No VPS access,
new deployment, merge, paid call or external integration authorized in this slice.

## User result and reused authority

After an independent copy is saved, a Get file button requests that copy. Opening
an attachment card offers the button too. Owner can say "Пришли файл №123" or
use /file123 (with a space before the number). Callback and text use the same
normal private owner authorization, immutable intake and durable idempotent update.
A new explicit request can retrieve previously admitted source copies after a
code upgrade; there is no automatic backfill or automatic resend on upgrade.

Existing TelegramDelivery stores only source/hash/epoch/revision metadata, never
binary payload. Existing queued-body audit anchor, profile scope, Control stop/
recovery/epoch and source revision gate delivery. read_copy validates original
and DATA/audit fingerprints and exact bytes before upload. File sent as document
from the database, not forwarded or re-downloaded from Telegram. Photos preserve
the stored Telegram rendition; original pre-upload image equality is not claimed.
Safe fixed nameattachment-N with a common original extension, otherwise.bin;
photo.jpg. No untrusted path/URL, destination selector, OCR, execution or AI.

Fixed Telegram TLS host and exact current connection/credential guard, private
owner recipient, multipart bytes only, max10MiB, no redirects and bounded65536byte
response. Upload outside admission lock, same single-leader delivery semantics.
Normal stop/epoch/revision/copy changes before admission suppress queued upload.
In-flight external HTTP cannot be recalled. SENDING crash/timeout or unknown
receipt remains UNCERTAIN, never automatically re-sent; owner may explicitly
request a new send. No exactly-once claim for the external network operation.
No new DB schema, service, key, mount, table, authority system or API file endpoint.

## Verification and activation boundary

Five local HTTP/codec/button tests PASS; Ruff whole tree, scoped Bandit, contract
and diff checks PASS. Nine PG cases added: real storage to upload after new bridge,
duplicate update, callback/outsider scope, stop/epoch/revision/corruption, uncertain
no-retry, unavailable copy and queued-body tampering. Local Docker Linux engine
not available; database/container acceptance requires final clean CI.
These are public synthetic fixtures, not an actual Telegram send or VPS test.
Final source/PR/merge-ref CI pins must be recorded after completion.

Production last verified PR123/source0259ce4; no server operation performed.
Future install requires fresh exact release approval, backup capacity and current
reconciliation, then real disposable file retrieval and restart/no-duplicate test.
Do not start paid document interpretation, other projects or Stage3 from this slice.
