# Russian ASR installation — phase 2/6

Owner approved the concrete PR117 / 1e5dd99 / fixed GigaAM installation with
«Делай». Bounded window recorded 2026-11-25 14:36:51–15:36:51 UTC.
No merge, paid API, Calendar writes, permission expansion or retention deletion.

## Exact installed release

- Application source: `1e5dd99f03b2e7bcb17f29164994b2d136118057`.
- PR117 remains Draft, base preserves the unmerged predecessor chain.
- CI45621267384 and45621267808 rechecked SUCCESS before installation.
- Previous source42b8238, bundle
  `751d859a53913acbdc34ff3570abde96c10a380e45969e066a6f3ea5ee5adaf6`.
- Target bundle: `498a05e77dd064f72f68215cbd3cd5114e43f7b9be24cfd16ee50e850b1383a4`.
- Preparation: `d17faaf3ab066c3fe5e6cd13e6581a8a5007e62aece6e235eb99326b80395d18`.
- App image: `sha256:810bbfbbdea138267e1bb76509d44917ad89579e5dd0b696cdeb00ce04a5649d`.
- Speech image: `sha256:5eb57af5414cbef9e20dac950ff18051480d84893530b4f0bc6ca4ff85498475`.
- Release root: `/home/acc-control/jarvis-voice-1e5dd99-release`.
- Fixed model snapshot322c3b29492673eb7d0b434bfa9dfb8653e34d02,
  manifest digest515e892df96c91b5bcd6234d61655836c1891585fcb8d3966d96b9e3462428b6.
- Model host directory: `/home/acc-control/f30/state/voice/gigaam-v3-322c3b29`;
  container `/models/gigaam-v3`. Four file hashes verified before extraction.

Exact source bundle checksum was verified locally and remotely. Images were
built from detached exact source with a clean worktree and checked revision
labels, not relabelled predecessor/CI images. Stock profile prepare explicitly
selected the fixed model, preserving owner, connection, enabled flag and cutoff.
Calendar key and read-only configuration were reused with the new source binding.
Stock prepare/inspect/apply/postcheck used unchanged interlocks. One apply only,
OPERATOR_EXIT0; deployment.json and activation.json both VERIFIED. No journal
substitution or reconcile was necessary.

## Linux resource check before apply

Actual GigaamSpeech decoder, new exact speech image, rootless Docker, network
none, no credentials, read-only root/model/fixture/script mounts, no capabilities,
no-new-privileges, pids64, 1CPU, memory/swap1GiB. Container UID0 maps to the
rootless control user, matching the stock voice service. An initial UID1000
smoke could not read the private bind-mounted script; this was an operator
fixture configuration error, not model failure. Retest used the stock UID mapping.

Public synthetic recording only, no private phone audio uploaded for this probe:

- Model load1.485s.
- 5s input:1.172s,62-byte transcript, contract passed.
- 120s input:10.614s,1322-byte transcript, contract passed.
- Peak RSS595.0MiB; cgroup memory.peak864276480bytes (~824.2MiB), below1GiB.
- Exit0, OOMKilled=false, CPU quota100000/100000, memory.max1073741824.

ONNX emitted a warning that the telemetry device identifier could not be
persisted on the read-only filesystem. Runtime telemetry is explicitly disabled;
this probe had no network. This is a synthetic isolated decoder result, not a
phone-to-Telegram latency measurement or road-speech accuracy guarantee.

## Backup and recovery

Pre-update encrypted backup42d2ef9df640436d9e7a892a6fd8a630 passed stock verification
and full disposable network-none PostgreSQL restore/audit-anchor check. Existing
operator restore adapter retained512MiB scratch,1GiB memory and final TCP
readiness; primary database was not restored over or otherwise modified by drill.
Copy on owner-only PC independently decrypted in memory; dump checksum and old
bundle matched. No plaintext written.

Stock apply's own backup retained. Post-update backup96e9f805aa174337be064c3a13ce304b
and encrypted recovery delta copied to owner-only PC custody
`C:/Users/Zver/.codex/private-backups/jarvis-2/20261124`. Independent DPAPI-key
decryption verified dump checksum, target bundle, VERIFIED activation, Calendar
key/source binding and exact new voice model/profile. Delta includes source
bundle, release receipts, model manifest and Linux smoke evidence; pinned model
bytes also remain in the local release kit and on the VPS. Old models, profiles
and images retained. No RPO/RTO promise or offsite_verified flag substitution.

Backup directory now267657777 of268435456bytes, only777679bytes remaining.
Another normal full backup will not fit. Do not raise quota, delete old backups,
or start another deployment blindly. Next release needs an explicitly approved
retention/archive plan with independently verified retained recovery copies.
Disk free about29.9GB is distinct from this application backup quota.

## Telegram and operational follow-up

The previous Telegram process exited1, OOMKilled=false, at14:42:17UTC during
preparation. The newly installed process also exited1 around14:45:25UTC after
its initial postcheck. Protected logs only report failed-closed; no new poll-error
event at either stop. Exact cause is not established and must not be claimed fixed.

With the normal poller confirmed stopped, one bounded diagnostic poller at a
time used the exact installed image/config/mounts through compose run. Safe
instrumentation emitted exception type/structural frames only, never credentials,
raw provider errors or messages. Runs of3 and20 real polling cycles completed
normally; no synthetic incoming updates or concurrent second poller. Diagnostic
containers removed by their normal --rm flow. Original exact installed Telegram
container restarted14:50:59UTC after proving no other poller running. It remained
running beyond the earlier30s failure interval and through actual command tests.
This is operational recovery, not proof of permanent failure elimination.

Read-only PostgreSQL log classification subsequently found statement_timeout
at14:42:12.958905UTC and14:45:22.792090UTC. Both statements were SELECTs of
control, not model operations or audit reads. Configured statement/lock timeout
is3000ms. These align with the two poller stops and point to contention during
backup/postcheck maintenance; correlation is not a captured Python exception.
Raw SQL/parameters were not exposed. Do not increase timeouts or disable data
interlocks as an ad hoc repair. A later reviewed fix should handle only bounded
transaction-entry contention without replaying network/business operations.
At14:54:31UTC the normal exact poller had run over3.5minutes since restart,
with fresh heartbeat14:54:23 and voice IDLE14:54:16. No new poller stop then.
Final15:01:50UTC read-only check: OPEN epoch65/recovery=false, Telegram heartbeat
15:01:40UTC, voice IDLE15:01:50UTC; normal poller over10minutes since restart.
Stock voice model custody/profile/runtime boundary checks passed again on exact
installed bundle/model/image. The last real /help reply was visibly confirmed
in Telegram. Fresh owner phone recording still not received at this checkpoint.

Owner browser /resume plus actual confirmation restored OPEN epoch65,
recovery=false. Voice was briefly stopped in bounded120s owner windows so its
heartbeat would not invalidate the confirmation, then same exact container was
restored early. Voice is IDLE on the new source/model. API, Telegram, voice,
PostgreSQL and Redis running; database healthy; no OOM. Legacy developer worker
and watchdog remain stopped as required by assistant-only mode (their old137
exit is not a new assistant OOM); broker absent. No developer services resumed.

Real /help after restoring the normal process: inbox14:52:38.164707UTC →
SENT14:52:42.125047UTC,3.96034s. Not UI-to-SENT or an SLA. Actual natural-language
Calendar read reply was also visible in Telegram; no events changed.
Ledger remains actual4 historical units/reserved0/uncertain0. No paid call.

Fresh3s phone voice was received17:36:46.704342UTC; owner supplied its actual
wording in this chat. Installed ASR proposal17:36:58.836942UTC matched all owner
words exactly, with punctuation added; text hash verified and the same card
visibly read in Telegram. SENT17:37:03.568942UTC: intake→proposal12.1326s and
intake→SENT16.8646s, not model-only speed or phone UI-to-SENT latency.
Worker STARTED17:36:53.318404UTC:6.614062s before worker start,5.518538s from
start through download/guards/ASR/proposal,4.732s proposal→SENT. Current evidence
does not isolate inference alone. This reveals remaining pipeline overhead.
No ACCEPTED event for this proposal; Save was not pressed, no request/task or
Calendar event created from it. Ledger unchanged, actual4/reserved0/uncertain0.
At17:37:58UTC OPEN epoch65, fresh Telegram/voice IDLE heartbeats on1e5dd99.
No telegram_service_stopped or voice transcription failure event since15:02UTC;
this is over2.5hours of observed operation after recovery, not an uptime SLA.
This passes one short real-phone transcription/readback example, not general
road-speech or Calendar acceptance. Calendar integration remains read-only;
the test phrase also omitted a meeting time, which must not be invented.
Do not claim automatic tasks, Calendar writes, road-speech quality or phase2
completion. Next product work remains voice acceptance, safe Calendar writes,
tasks/reminders and the complete usable phase2 scenario.
