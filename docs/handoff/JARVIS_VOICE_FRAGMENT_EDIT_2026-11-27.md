# Owner-requested literal fragment correction

Owner requested continuation after real82s voice review. Clarified migration
wording; meeting was ONLY a test and must not be scheduled. Site spelling remains
ambiguous, no inferred correction. No live voice acceptance/correction/scheduling
performed by this development slice; original proposal remains unaccepted.

Existing owner Reply correction required resending the entire transcript. Add
bounded literal replacement on the same observed Reply path:
Замени «старый фрагмент» на «новый».
Straight double quotes and curly double quotes also accepted. Exact case-sensitive
fragment must occur once, including overlapping occurrences; no fuzzy matching,
inferred spelling, regex replacement, multiple instructions or word normalization.
Malformed/missing/repeated fragment refuses with a useful receipt. Reserved prefix
Замени begins this bounded grammar; ordinary full-text replies and /stop remain
data. Result must satisfy existing2000UTF8 byte/secret guard; oversize result gets
refusal rather than an uncaught poller failure. No automatic save or scheduling.

Reuse the existing CORRECTED event and one-save family, observed-card binding,
owner incoming fingerprint/anchor, source/audio/epoch/revision checks. Partial
correction records edit_mode=replace_once and previous_text_hash; acceptance
reconstructs the exact requested replacement from the anchored owner instruction
and observed predecessor delivery. Original ASR remains unchanged. Older full-text
correction events without edit_mode retain their existing equality validation;
full and fragment edits can be combined. No second permissions mechanism.

Public synthetic tests only; no private owner transcript/audio in fixtures.
Local16 unit cases PASS;7 new PostgreSQL cases and final CI pending. Full Linux
container/DB unavailable locally. Static/contract checks pass. No mock is live
Telegram/phone acceptance. This improves correction usability, not acoustic ASR
or punctuation quality. No model/API/Google change, paid call, VPS access, merge,
deployment, cleanup, quota increase or new external integration. Stage2 incomplete.
Base is unmerged PR127/codex/voice-quality-corpus at4f51e27, preserving docs chain.


## Release preparation and compatibility boundary

No release prepared/installed in this local slice. Fresh exact owner approval
is required before VPS release work. Reconcile actual source/journals/images,
Calendar/voice custody, admission and backup capacity first; last dated26November
quota headroom was10889021bytes. Do not delete old backups, bypass the256MiB
quota or reuse old staging/apply authorizations. Any required retention operation
needs a concrete verified-copy inventory, recovery plan and separate exact approval.
Use stock prepare/inspect/exact approval/install/postcheck and protected backup.

No SQL migration, but new pending partial CORRECTED provenance has an owner command
different from resulting text. Code inspection indicates predecessor4f51e27 would
reject accepting such a pending card via its full-text equality check. Do not
claim rollback compatibility just from unchanged schema; preserve raw source,
correction/audit chain and backups, prefer reviewed forward recovery if necessary.
No live old-reader rollback/restore-over-primary test or authorization is claimed.


## Verification correction checkpoint

Superseded CI46047539863 on87d6f11 reported4 test-harness failures: three refusal
checks read fake.sent before delivery instead of the persisted outbox, and one
fault injection attempted to UPDATE the append-protected audit as f1_app. Other
3020 cases passed, but that run is FAILED and not final evidence. Corrected tests
use the existing persisted-receipt helper and synthetic admin-only fault injection;
then directly exercise the partial-correction integrity check. No application
permissions, audit protection, assertions or production code were weakened.
Final applicationc837c2e54961b72989fe47bf5505f32b01d8bb0e;
merge935774e64fd565563bfd3c604e2ed52492b99c0c;
identical treeaf16641ad686b0441543da460e916e1994696f44.
Final CI46049662208 pending. Do not add/sum superseded and final suites.


## Final verification (supersedes pending CI above)

Final CI46049662208 SUCCESS for applicationc837c2e54961b72989fe47bf5505f32b01d8bb0e
and merge935774e64fd565563bfd3c604e2ed52492b99c0c; identical tree
 af16641ad686b0441543da460e916e1994696f44. PR128 remains Draft, unmerged,
base codex/voice-quality-corpus at4f51e270a0513f2c01ab1301e7796929ef8c5098.
Full suite3024passed/1skipped/1warning in569.88s; infra1014passed;
speech44passed. Overlapping suites and superseded runs are not summed. All7 new
PostgreSQL cases pass, including persisted refusal receipts, single-save/raw source,
chained/stale cards, full/partial compatibility, byte budget and direct integrity
guard after synthetic admin fault injection. Static checks, source-pinned image,
container/restart, isolated restore and deployment prerequisite probes pass.
This is synthetic CI, NOT VPS/rootless/phone acceptance or an acoustic quality gain.
[Final run](https://github.com/v71369322-lang/ai-command-center/actions/runs/46049662208).

Separate codex/voice-fragment-final-verification docs checkpoint leaves tested
application HEAD frozen. Candidate is READY FOR CODE REVIEW, NOT INSTALLED; no
VPS staging/bundle/image pins or live fragment-edit acceptance claimed. Next gate:
exact approved server preparation, read-only reconciliation/backup capacity and
reviewable stock release package; retention/install require their own concrete
permissions. Sample meeting remains test-only and unrecorded by operator.
