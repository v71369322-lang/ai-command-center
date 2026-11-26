# Owner retrieval of independent attachment copies

Local development; not installed. Stage2 remains in progress.
Base0259ce4549aab013ffb6a55574ae7365015bd843 (PR123), plus preserved installed
release handoff0769810. Separate branchcodex/attachment-retrieval. No VPS access,
new deployment, merge, paid call or external integration authorized in this slice.

## User result and reused authority

After an independent copy is saved, a Get file button requests that copy. Opening
an attachment card offers the button too. Owner can say "Пришли файл №123" or
use `/file 123`. Callback and text use the same
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

Six local HTTP/codec/button tests PASS; Ruff whole tree, scoped Bandit, contract
and diff checks PASS. Nine PG cases passed in final CI: real storage to upload after new bridge,
duplicate update, callback/outsider scope, stop/epoch/revision/corruption, uncertain
no-retry, unavailable copy and queued-body tampering. Local Docker Linux engine
not available. The attempted local assistant-policy test module also requires
POSIX fcntl; it could not collect on Windows and is not reported as a local PASS.
Database/container acceptance passed in the Linux final clean CI.
These are public synthetic fixtures, not an actual Telegram send or VPS test.
Final sourcec25e2d30ec49bad7347cf3274714bbb520cffd3d, Draft PR124, base PR123
0259ce4549aab013ffb6a55574ae7365015bd843. Merge-ref
4c80409797f3f3507d7a407fed53b62e4f6676ed and head share tree
3f1866417e0a6216b6fccc27bbe66f4f6bf7010f. Final CI45815091382 SUCCESS:
main2909passed/1skipped/1warning (678.72s), infrastructure1014passed,
speech44passed. Includes15 new cases (6 local protocol/button cases and9 PG cases).
Encrypted dump to a distinct networkless PostgreSQL instance, byte fixture/audit
interlock, persistence/restart and container smokes PASS; final cloud verification
explicitly passed for the pinned merge-ref. Superseded runs and overlapping sets
not added. Local additional public HTTP/codec combined check21passed; this overlaps
CI and is not summed. Ruff, Bandit, contract, tracked-current-secret check and diff
PASS. Workflow Node deprecation warning is separate from the pytest warning.

Exact source bundle.runtime/attachment-retrieval-release/source.bundle:
SHA25694FAC36FB44C591536B286F521F5E1A69149F8E52C007BE7C0F4BEA74560766B.
Bundle verified complete, pointing at exact application source. This subsequent
documentation checkpoint does not change that source/PR head or claim a new
application CI result. No real Telegram file delivery performed in this slice.

Production last verified PR123/source0259ce4; no server operation performed.
Future install requires fresh exact release approval, backup capacity and current
reconciliation, then real disposable file retrieval and restart/no-duplicate test.
Do not start paid document interpretation, other projects or Stage3 from this slice.

## Concrete next release proposal (requires new owner approval)

Exact PR124/sourcec25e2d3; one hour from fresh explicit approval, deadline frozen
before activation, no extension inferred. Read-only reconcile only the named
Jarvis VPS176.12.75.135 using existing access. Preserve existing Telegram identity,
voice/model and Google keys/deployments, owner scope and other projects. Check
current backup quota, fresh protected prebackup/isolated restore and PC decrypt/
checksum before writes. If capacity is insufficient, stop and prepare an exact
retention decision; no additional archive deletion or quota increase authorized.
No new credentials, services, mounts, schema or server privileges are needed.

Build exact-source app/speech images, stock prepare/inspect, freeze derived
candidate/preparation pins and apply once inside the approved window. On timeout
or failure, inspect actual runtime/journals; stock reconcile only if every exact
precondition holds. No manual journal edits, ordinary compose up, blind retry,
blind rollback, or deleting user/audit data. Bounded same-container repair only;
unexplained repeated stops remain a blocker, not a passed uptime claim.

After verified gates, actual owner Telegram resume/button if needed. Request only
the two existing public disposable fixture copies131179278 (document75bytes) and
131179279 (photo rendition310bytes). Check real buttons, downloaded byte hashes
against the prior retained copy evidence, owner-only scope, one delivery per
update, status and persistence after the same poller restart, with no automatic
repeat. No source-file deletion required. Verify existing calendar read/custody,
voice health, unchanged paid ledger and final protected backup/PC recovery custody.
If a check fails, preserve evidence and report the exact remaining failure.

No paid AI/OCR, GitHub merge, new Google rights/events, business-system changes,
new server grants, extra cleanup or additional user documents in this proposal.
Owner approval of development alone has not authorized this server operation.
