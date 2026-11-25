# Voice correction release live — 25 November2026

Overall route remains phase2/6, unfinished. Owner replied «Разрешаю» to the
exact PR116/42b8238 installation request, observed11:10:04UTC; bounded approval
through12:10:04UTC. Scope: backup, exact install/postcheck and Telegram acceptance.
No merge, paid AI calls, Calendar write scope or destructive cleanup authorized.
This checkpoint is documentation only; installed application source is below.

## Exact source and installation

- Source42b82380b1fbba2a482e302df4a1e78f5755adb2, PR116 Draft, no merge.
- Final CI45592976672 SUCCESS; head and merge-ref
  d1a399b35d4eb8eb6470e7966b44e8b11b5db3f8 have identical tree
  9ef3519934dcd61ee6bede7911a57efde220cbff.
- Main suite2719 passed/1 skipped/1 dependency deprecation warning;
  separate infrastructure1014 passed; separate speech23 passed and image smoke.
  Overlapping checks are not summed. Infrastructure path-filter workflow not triggered.
- Root/home/acc-control/jarvis-voice-42b8238-release, active/candidate.
- Previous source3bcf8e4, bundleaca9a227e367db4c9bf5f0454993311d4f81fdf5f2ffbcec0176c5195deae70c.
- Candidate751d859a53913acbdc34ff3570abde96c10a380e45969e066a6f3ea5ee5adaf6.
- Preparation1cd3166b5dd45c91851b0246475182192cc603d56d10a7f5e39acfbd57a56bdc.
- App image sha256:1b9f8cae615ed3d32e61303b7775cb0845b85ed6933b723f45a3c90b860bc9cb.
- Speech image sha256:7cb0c5387bb9628a37726cd5b55277d98e98301787edfc3bd48d26acd7cfd510.

Fresh read-only reconciliation verified the exact predecessor before preparation.
Windows CRLF in the transferred build shell script initially prevented its first
line running; corrected to LF and restarted build, before any installation.
Source checkout was detached/exact and clean; no old-image relabelling as new source.
Stock prepare/inspect and stock activation were used. Apply ran once, OPERATOR_EXIT0;
deployment.json and activation.json both VERIFIED. No journal substitution or reconcile.

Actual API/Telegram/voice containers running on42b8238, no OOM. Telegram remains
1CPU/256MiB; voice remains the same pinned Whisper base/int8/1GiB bound.
No Small model switch. Developer services remain stopped under stock postcheck.
Google binding reused at the new source revision, same key and read-only scope.
Other projects and server security settings were not changed.

## Telegram and remaining user acceptance

Real owner web chat /resume and its actual confirmation button were used.
The same exact voice container was temporarily stopped with a120s auto-restore
guard to keep the owner card usable, then explicitly restarted immediately after
confirmation. No synthetic owner Update, direct Control edit or fabricated grant.
Fresh SQL at11:16:51UTC: OPEN epoch62, recovery=false, actual4 historical units,
reserved0, uncertain0; Telegram heartbeat fresh and voice IDLE on42b8238.

Real /help reply visibly observed in Telegram: received11:17:56.269678UTC,
SENT11:17:59.927714UTC, inbox→SENT3.658s. This is not UI→SENT or an SLA.
Real natural-language Calendar query also produced the Google Calendar read reply
visibly in Telegram after the upgrade. Events were not changed.
Later that day the owner sent a new5s phone voice and clarified its actual wording
in this chat. Intake12:44:49.175618UTC → actual ASR proposal12:44:59.194204UTC
(10.018586s, not a speed SLA). ASR made an inflection error; this was not silently
treated as a correct recognition or replaced with the operator's original test phrase.

Using the actual authenticated owner Telegram UI, replied to that specific ASR
card with the full wording confirmed by the owner, adding punctuation only. A new
owner-authored correction proposal appeared12:46:22.799075UTC. The initial ASR
record remained distinct and both text hashes validated. Clicking the original
card's Save returned the stale-card refusal; accepted_count was still0.

Confirmed the latest corrected card: one ACCEPTED12:47:19.400368UTC, one saved
NEEDS_PLANNING request, text exactly matching the owner correction, task_created=false.
Repeated Save returned already-processed/no duplicate; read-only family-bound SQL
still found exactly one ACCEPTED. Task count remained9 before/after, ledger actual4,
reserved0, uncertain0 unchanged. The saved request view was opened and the corrected
text visibly verified in Telegram. No fabricated incoming update or seeded audit rows.
No Calendar event or paid AI call. This closes the live correction/save acceptance
for this one real example; it does not validate noisy ASR, dates/addresses, idea-bank
classification, scheduled tasks or the whole phase2 MVP. Raw voice/text and request
identifiers are intentionally not copied into public Git evidence.

## Backup and recovery

Pre-update backup5aef724075d44f059fdd4aef79c37dad: stock checksum verification and
full disposable network-none PostgreSQL restore/audit-anchor check passed without
primary modification. Existing bounded operator adapter retains512MiB scratch,
1GiB memory and final TCP readiness, unchanged full stock audit checks.
Stock128MiB restore default is not claimed sufficient.

Post-update backupce38b2fc32014866ac68b8fe708745b2 and encrypted recovery delta
copied to owner-only PC custody C:/Users/Zver/.codex/private-backups/jarvis-2/20261124.
Independent DPAPI-key decryption verified both backup dump checksums, target bundle,
delta VERIFIED activation and Calendar key/source binding. No plaintext written.
No RPO/RTO guarantee. Stock apply's own target backup is retained as well.

Important compatibility gate: older3bcf8e4 does not understand owner correction
proposals or family-wide deduplication. Do not resume an older Telegram runtime
against data with corrected cards/events without a reviewed compatibility plan.
No schema migration is not proof of safe downgrade. Keep intake stopped during
any such recovery assessment; retain independent backups and original audit data.

Before this release backup directory238165074bytes of the configured256MiB quota;
no files removed and quota not bypassed. Future release preparation must recheck
capacity and obtain approval before irreversible retention cleanup.

Next product result is reliable ASR for road use and separately approved Calendar
writes, tasks/reminders and phase2
acceptance. Phases3–6 are not started by this installation.
