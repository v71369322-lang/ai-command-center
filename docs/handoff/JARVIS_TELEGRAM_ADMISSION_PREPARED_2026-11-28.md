# PR129 — prepared release, Telegram failure and exact approval boundary

**Prepared, NOT INSTALLED. Current Telegram stopped on predecessorc837c2e at
14:17:20UTC (17:17:20 Moscow); no automatic restart or installation authorized.**
At14:21:37UTC both application journals still VERIFIED, four other services
running, but Telegram stopped/exit1/noOOM. VERIFIED journals are not health PASS.
Owner continuation covered the concrete proposed server preparation/reconciliation
step, not deployment, backup deletion or restart. Preparation window14:13:34–
15:13:34UTC (17:13:34–18:13:34 Moscow); do not renew/reuse as an install window.
No paid calls, Calendar actions, Telegram sends, model change/download, service
stop/restart, quota change, merge, access expansion or other project modifications.

## Verified release

PR129 Draft/unmerged, base PR128/codex/voice-fragment-correctionc837c2e.
Final source8239478068faac40e7d238e9caf263d83ac03f25;
merge8fb074bdf197fb31d5e60afdfb0a2e17d4758344;
identical treee52db3d723935b3c0b3e20149bf3e90296732fb4.
Final CI46148204798 SUCCESS rechecked:3036passed/1skipped/1warning,
infra1014passed/speech44passed (overlapping, not summed).
Origin/fetch verified; actual mainf5ff8b2757b1b759b08a173fdac9d3e51f84d227.
No implementation changes or new CI needed for this documentation checkpoint.

Private root /home/acc-control/jarvis-admission-8239478-release.
Source archiveSHA256255dc997904b18a961e5742e0e34f167681f4ea2293e186e55ab5ccdd19fefd3.
Previous bundleb0c5037f2450764648dd96b10f3f94871c0d3eb2653dac824c28c269373532d0.
Candidate788296d4d3cadff54c384ebade21c2e6d6948ebd69b0779bb111b39412038ad9.
Preparation2d244095b11714713f9096cc5d31fdba40c28a8c76141396f95b11bd6e09b14a.
Appsha256:234768adb02e56ccc851ae44b96ffdc2877ee582e8b552d39752fee11e6cc4bf.
Speechsha256:f463ad755ea7a8cb034304360c223a40d4f07da3892b0cbfd9a0c52825275a81.
Both images built from exact source, no relabelled old image. Explicit detached
checkout followed the bundle's absent-default-ref warning; actual HEAD checked.
Stock prepare/profile/inspect PASS; STAGED_NOT_ACTIVATED/deployment_authorizedFalse.
New model/Calendar profiles preserve keys/capabilities, changing only source/digest
bindings. Existing acc-f1-app:local tag restored after stock prepare.

Encrypted prepared-package.enc2,572,762B,
SHA2562dd262feca5d591e1c1cb9dd479940ad8a61cccb12d340a9c804f621e6fdb5b4.
Protected PC owner-only custody:
C:/Users/Zver/.codex/private-backups/jarvis-2/admission-prepare-20261128-1413.
Independent in-memory PC decrypt verifies exact archive/candidate/preparation and
all preparation file hashes, retained raw model manifest and profile equality,
Calendar keys/scopes unchanged compared with protectedc837c2e recovery delta.
PC proof explicitly expects Telegram stopped and live_readyFalse, not health PASS.
Package contains source/profiles/keys/receipts and image/model references, NOT
DBdump or image/model payloads; no full independent/offsite recovery claim.

## Three-file retention proposal — NONE DELETED

All19 server DB archives independently decrypted/checksummed; all62 protected PC
archive copies independently decrypted/checksummed. Three selected older copies
match name/size/ciphertextSHA/bundle/timestamp/dumpSHA. Newest per bundle, every
current and prior bundle archive, latest pointer and other counted files remain.

| Proposed server file only | Created UTC26November | Bytes |
| --- | --- | ---: |
| backup_5d406f6dee5742eb8a708c15a11ff5a3.enc | 12:32:50 | 5569079 |
| backup_7a12ed2e6cbb44fda81c476157133133.enc | 13:46:29 | 5615239 |
| backup_93f86c60ea684c309f94e8baa2941ca7.enc | 15:24:25 | 5677379 |

Total16,861,697B. Free quota would increase12,287,042→29,148,739B without raising
268,435,456B limit. Fresh three-copy backup requirement must still be checked against
actual new dump size plus margin before apply. No deletion permitted by this stage.
[Exact hashes and preserved copies](../jarvis-2/evidence/PR129_RETENTION_PROPOSAL_2026-11-28.json).
PlanSHA256dc124e3ecaa87f13a413307fcf6031619beda6730ab996a6acde1b0ad0daff63.

Each selected archive fully restored into its own networkless rootless PostgreSQL;
stock audit-anchor validation PASS, primary_modifiedFalse, disposable targets
removed. Existing bounded512MiB tmpfs/1GiB adapter and final TCP readiness retained
all stock checks. No restore over primary, RPO/RTO, old-reader compatibility or
offsite proof. Exact inspection checks regular file/nonlink/owner/mode/nlink,
size/hash/latest/current/prior/newest preservation and unchanged quota usage.

An initial restore launch failed before creating a target because the newly
uploaded operation-scope artifact was root-owned0600. Corrected only this new
preparation artifact to intended acc-control ownership; failure log preserved,
then three isolated restores PASS. No daemon/service/credential changes.

## Failure observed during preparation

Initial14:13:43UTC: sourcec837c2e/both journals VERIFIED, all five original service
IDs/StartedAt unchanged, Telegram fresh heartbeat14:13:41, voiceIDLE14:13:29,
OPENepoch101/actual4/reserved0/uncertain0. Calendar/voice runtime custody PASS.

Existing main Telegram then stopped14:17:20.074498UTC, finished14:17:20.941624731,
exit1/noOOM. It remained sourcec837c2e; candidate8239478 was never run. Database
logs show exact control admission SELECT FOR UPDATE statement timeouts at
14:17:14.113 and14:17:17.552UTC. Raw SQL/params not exported. Strong correlation,
but old sanitized launcher still does not expose original stopped-process error;
no definitive causal attribution to its PID. No restart loop or old apply retry.

Original healthy-package check correctly failed on the actual stopped service.
A separate blocked-state packaging script records live_readyFalse; original
pre/postcheck guards were not weakened. Candidate file/profile inspection remains
PASS but runtime/installation acceptance is BLOCKED, never described as healthy.

Final14:21:37UTC check: same five IDs/StartedAt, same live images/config; API,
voice,DB,Redis running, Telegram stopped. Calendar file/key custody, voice/model
custody and existing privilege/resource boundaries PASS. Developer services remain
off. No isolated restore targets left. All19 backup ciphertexts unchanged;
latest backup_307d29088cae48cf9c16c33fe89238d4.enc retained. Backup usage256,148,414B,
free12,287,042B; host disk free19,932,934,144B. No current Telegram reception claim.

## Concrete next operation requiring fresh owner confirmation

Within one hour of NEW explicit confirmation, without paid calls/Calendar writes:

1. Read-only reconcile exact live/candidate pins and preserved files. One bounded
   start of the SAME stopped predecessor Telegram container only if exit1/noOOM,
   no duplicate poller, exact image/config/source/current VERIFIED receipts match;
   fresh read-only startup diagnosis first. Record own repair INTENT/result, no
   application journal fabrication. Do not loop starts if it fails.
2. Reverify matching protected PC copies and three full restore proofs. Execute
   only the three exact server-file removals above under the stock operator
   retention lock/preconditions and a new versioned authorization; latest/current/
   prior/newest retained. Preserve PC originals; no quota increase/other cleanup.
3. Fresh independent prebackup and isolated restore/PC verification; reserve enough
   for stock backup plus postbackup/margin. Halt admission through existing controls
   only under new exact installation authorization. New runtime requires real
   owner web resume after verified activation, no old tasks resumed.
4. Install exact PR129/source8239478/candidate788296d4/preparation2d244095 once
   through original stock exact gates. If timeout/failure, inspect actual outcome;
   no blind apply retry. Stock reconcile only when ALL preconditions/postchecks pass.
5. Verify real Telegram response and voice/Calendar custody without paid calls or
   scheduling the owner's test meeting. Postbackup, isolated restore and encrypted
   PC recovery evidence. No health PASS without actual fresh working reception.

No rollback to predecessor is assumed safe: pending fragment correction and prior
release history remain relevant; schema equality is not semantic compatibility.
Independent stop/backup and protected copies remain recovery options. Any unknown
state, differing pins, failed diagnosis/restore or insufficient space stops this
operation for a concrete blocker; do not enlarge scope silently. Stage2/6 incomplete.
