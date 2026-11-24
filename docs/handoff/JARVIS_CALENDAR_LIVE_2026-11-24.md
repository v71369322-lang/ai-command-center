# Calendar read-only release on VPS

Owner's latest instruction explicitly requested entering the VPS and completing
the discussed PR113 server package. The operation was recorded with exact source,
previous/target/preparation pins, finite1800second activation window and no paid
calls, Calendar writes or merge. No SSH users/keys/firewall or other project changed.

## Installed version and verification

- Source7edc1d827da6f1dc91b6fdc502c8673d0d0a901a, PR113 Draft, not merged.
- CI45403493355 and45403493835 both SUCCESS for that exact head.
- Head/PR113 merge-ref tree060f938260dc295ac9107d7d4c06d8020d097f81.
- Final local release suite215 passed in one run; earlier overlapping counts are
  not additive. Ruff and Bandit medium/high passed.
- Previous verified source9351ba678c4a908169cf76fba81dec4fd5e3bc10,
  bundle ac5542f56c0155560cd35050f3adf9fcae6efb76310437274b0d782543ba8331.
- Installed bundle27ad64522d328e4041d497d85cb9f31714b898b2d35981d6b3ece0530d0f10be.
- Preparation f29fa1941bb9731ac12b4dde1b1287e0f9ec0a25f8eca36c04600468f406e6bf.
- API sha256:81d540721ffe9bced8f084116d6357d7272695e47edf64c466c0ec6fea267c4b.
- Speech sha256:e6406a299187a9293cfd0582105907c09b8bb6d4a53cd58553e60019a81fb927.
- Release/home/acc-control/jarvis-calendar-7edc1d8-release; active candidate-repaired.
- Both deployment.json and candidate-repaired/activation.json independently checked
  VERIFIED after stock reconcile. Runtime/binding were not rewritten by reconcile.
- Same Telegram owner/bot, offline voice model/cutoff, DB/Redis/migration/storage.
  Five services remain; developer worker/broker/watchdog stay stopped.

The shared key was securely transferred directly from owner-only local custody
to a new private host directory; no key appeared in Git, model output or arguments.
Only Telegram receives the exact read-only config/key mounts. Actual client creation
inside Telegram and strict runtime command/mount/custody checks passed.
Real signed Google HTTP from the running Telegram container passed in3.10seconds,
Europe/Moscow, no event writes. This is server transport timing, not bot round-trip.
Google deployment v1 and approved Bridge.gs source were unchanged.

## Bounded operator repair and journal history

The first attempt stopped at PREPARED before connection/source activation: the
already assistant-only predecessor received entry_retry_code twice, causing the
embedded original transaction reference to recursively point at its own wrapper.
Old Telegram/voice containers were restarted on their unchanged images immediately
after verifying the old VERIFIED deployment and connection were still active.

Fix: PreviousUpdate.tool delegates directly when Deployment.tool already applies
the assistant wrapper; non-assistant predecessors still get one wrapper. Two focused
regressions passed; the combined operator/assistant-candidate regression20 passed. The fixed operator was used outside the clean pinned application
checkout; SHA25641ac7c8d7d480c3915f75112df66c6b1a1f410bc217ac23b28247bb5fc76d7c4.
The runtime image source remains7edc1d8, not this later operator source change.

The failed PREPARED journal was preserved. Stock candidate.prepare/inspect created
candidate-repaired with identical bundle and preparation digests after independently
confirming the old connection, old VERIFIED predecessor and no binding activation.
After target services started, immediate postcheck awaited fresh PAUSED voice
evidence. Stock reconcile was used with the existing tested45second read-only
readiness waiter (11 regressions passed), unchanged exact heartbeat assertions,
source/profile/model identity, freshness, halt/recovery and financial ledger checks.
No journal was hand-edited, deleted or replaced to manufacture VERIFIED.

## Backup and resources

Pre-update encrypted backup10253e4c3c854806bc557c239b8150e0 created and verified;
independent disposable restore verified the full audit chain/anchor without changing
primary. Ciphertext copied to owner-only PC custody; server/local SHA256 matched
885971f68c5681fc8644b48390dfd712fde1af5c99d4b6d6082fe96ec89e69a9.
Existing DPAPI recovery key was retained, not published.

Restore diagnosis found two operator prerequisites: wait for final TCP PostgreSQL
(the initdb Unix-only server is temporary), and128MiB scratch filled during actual
pg_restore. A bounded operator adapter used network-none,512MiB disposable tmpfs,
1GiB memory and unchanged full stock audit verification. Disposable containers were
removed by the existing finally cleanup. Stock restore defaults are not yet fixed
in the installed app source; do not claim those defaults now support this data size.
Automatic apply also created a target-pinned encrypted DB backup; latest receipt
is separate from the pre-update backup above. Offsite RPO/RTO are not proven.

At initial reconciliation:31GiB disk free, approximately4493MiB available RAM;
five Jarvis containers around435MiB working set. Old exit137 worker/watchdog had
OOMKilled=false; no new OOM finding. No destructive disk cleanup was performed.

## Live Telegram acceptance

Installation left admission halted. Through the actual authenticated owner Telegram
browser, /resume was sent and its real button clicked. The first card was correctly
rejected after a voice heartbeat changed its checkpoint context. A bounded120second
same-container voice stop/automatic restore window allowed a fresh real owner card
to be confirmed. Control OPEN epoch56, recovery=false; real consumed event at
2026-11-24T16:00:33.272548Z. Same voice container was explicitly restored immediately
after success, with automatic restoration retained as a guard. No synthetic owner
Update/grant or direct control edit. Historical cancelled tasks were not resumed.
Real owner query «что у меня завтра?» produced a Google Calendar reply in the
actual browser; corresponding audit status read, delivery SENT, model_called=false,
events_changed=false. Read-only DB confirmation showed OPEN epoch56, recovery=false,
reserved/uncertain0 and unchanged historical actual4. Phone voice transcription
is not yet claimed; the same offline voice container is running again. The exact supported alias is «что у меня завтра?»; the broader
phrase «что у меня завтра в календаре?» currently falls through to normal Inbox.


## Measured limitation and next priority

The Google transport took3.10seconds, but this real Telegram query took53.31seconds
from UI send to server-observed SENT; from bot inbox registration to SENT24.60seconds.
The UI query was queued behind a broader unsupported wording, which was saved as
an ordinary test Inbox item. These are different timings; do not claim a3second bot
response. The final Telegram CPU point sample reached24.69% with a0.25CPU limit.
This is evidence to investigate audit/queue/CPU latency, not proof of one root cause.
Keep the full audit/integrity/stop checks; do not hide latency or weaken permissions.

All five final services were running; DB healthy. Point working set API69.23,
Telegram73.80, voice191.80, Redis5.883, DB93.14MiB. Same-container automatic voice
restore guard completed successfully. No event creation/editing, paid AI, external
CRM access, agent restart or merge. The installed Calendar feature is read-only.
Local screenshot .runtime/calendar-telegram-live.png is ignored and contains the
actual browser result; do not publish the owner's chat screenshot into Git.

The repository operator fix and this handoff are a later maintenance-only change,
not a claim that the VPS image source changed beyond7edc1d8. Stock restore readiness
and scratch defaults still need a reviewed maintenance fix; the proven bounded
adapter and its full restore evidence are preserved in private release custody.
