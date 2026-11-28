# PR128 — installation and live fragment correction, 28 November 2026

## Scope and final state

Owner explicitly approved the exact four-file retention plan and PR128/source
`c837c2e54961b72989fe47bf5505f32b01d8bb0e`, 12:07:15–13:07:15 UTC
(15:07:15–16:07:15 Moscow). No paid calls, merge, new model, access expansion,
other project changes or test meeting scheduling. This window is not renewable
by the operator. Stage2/6 remains incomplete.

At12:33:12 UTC actual sourcec837c2e, both journals VERIFIED, OPENepoch101;
Telegram heartbeat12:33:03 and voice12:33:11/IDLE. Exact five-service boundary,
Calendar read/write binding and voice custody checks PASS. No new Google write
or agenda acceptance in this stage; model and keys/scopes unchanged.

## Exact release and CI

- Previous source4f51e27, bundleea3ca20867b99356ff5765802e7f69c04d2841a77f4710c7c8e8ca5867eaba49.
- Candidateb0c5037f2450764648dd96b10f3f94871c0d3eb2653dac824c28c269373532d0.
- Preparation5cc70880e996740061378c000018f6752533fba63f9db5067399e733a2f6a3eb.
- Appsha256:cdc77adfdd50a4d3fb4767ee56651ba9a20970b840f9d8da628576e72c61c814.
- Speechsha256:2b6af090b9bffc5c28a25e1195fe48092513ae10f67299042135789c719e901e.
- Source archiveSHA256d0f00fd2d15594217423cd0bdce42504df01b63a8137f6ab343ebf5c7f2072ac.
- CI46049662208 SUCCESS rechecked:3024passed/1skipped/1warning;
  infra1014passed and speech44passed overlap, not summed.
- Merge935774e64fd565563bfd3c604e2ed52492b99c0c; identical head/merge tree
  af16641ad686b0441543da460e916e1994696f44. PR128 stays draft/unmerged,
  based on PR127; verified actual mainf5ff8b2757b1b759b08a173fdac9d3e51f84d227.

## Exact retention and recovery

The [reviewed four-file plan](../jarvis-2/evidence/PR128_RETENTION_PROPOSAL_2026-11-27.json)
SHA25609131b549f286830f6c0051f7e4bcee01cfcb3eb75dd2ad57c0ef869538c18af
was executed once. Four superseded server archives removed:21,679,134bytes.
Protected matching PC originals retained and freshly decrypted/checksummed before
removal; all four had full isolated audit restores during preparation. No other
files removed. Latest pointer unchanged by retention; stock backups later advanced it.
Fresh authorizationSHA2567dbca154b0a907d87925022fcbd5f471914e44152b1fefea133347f172c1f94b.

Independent prebackup backup_63e731a7126a4b6eb541c598e62d6e13.enc:6,756,501B,
previous bundle; isolated restore/audit and protected PC decryption PASS before apply.
Stock apply also created backup_84a054604fda45f7ab380b4f9a0341c4.enc once.
Postbackup backup_307d29088cae48cf9c16c33fe89238d4.enc:6,767,234B,
new bundle; isolated networkless rootless PostgreSQL restore/audit anchor PASS,
primary unchanged. Encrypted recovery delta2,549,989B. PC independently verified
postdump checksum, both VERIFIED journals, model/Calendar/source pins and live
fragment proof; no plaintext dump extracted. Protected custody:
C:/Users/Zver/.codex/private-backups/jarvis-2/fragment-install-20261128-1207.
Latest backup quota usage256,148,414/268,435,456B, free12,287,042B.
No offsite recovery, RPO/RTO or automatic old-reader rollback compatibility claimed.

## Apply and bounded repairs — material remaining reliability risk

ONE exact stock apply exited1 after target Telegram stopped at12:11:21 UTC,
exit1/noOOM. Apply was NEVER repeated. Independent same-image startup diagnostic
passed; same exact Telegram container started once at12:13:28. Full runtime and
Calendar/voice pre/postchecks passed. First stock reconcile failed because strict
voice heartbeat acceptance sampled BUSY, not PAUSED. After observed consecutive
PAUSED heartbeats, second stock reconcile succeeded, runtime_changedFalse and
binding_changedFalse; both journals VERIFIED. No journal substitution, fake
heartbeat, weakened guard or compose-up shortcut.

Telegram stopped again12:18:21, exit1/noOOM. A bounded original poller diagnostic
ran12 real cycles with the main poller stopped, advisory single-leader protection,
same image/privileges and no fake owner Updates. It passed and removed itself;
its12:22:39 service-stop record is expected diagnostic shutdown. Same main
Telegram container started a second time after this diagnostic. Actual fresh
owner web resume challenge/confirmation opened admission at epoch101; old tasks
were not resumed. No further unexpected stop observed through12:33:12 UTC.

Read-only database diagnostics confirm3second statement timeouts on the exact
control admission SELECT FOR UPDATE query during maintenance, including12:11:17
and12:18:19. Telegram loop lacks OperationalError recovery; voice already has a
narrow admission-busy guard. Sanitized launcher did not expose the original
exception per stopped PID: correlation is strong, individual causal attribution
is NOT proven. Recovery is observed, permanent reliability is NOT accepted.
Next priority: bounded transaction-ENTRY-only contention handling and safe startup
failure observability, with no transaction-body replay, lock weakening or silent
source replacement. A new release needs its own exact approval. Do not loop
restarts or repeat apply if a later failure occurs.

## Actual Telegram acceptance

Observed owner Reply to real82second voice131179347/card464 created corrected
proposal b2f0e028-8a55-5c1d-881e-f5a6d7b7b14e/card471 via owner input131179351.
The owner-confirmed CRM wording was replaced exactly once; original raw audio,
raw text, source and every surrounding character retained. Live readback visible;
server intake to SENT receipt7.582seconds, receipt12:25:59.554431UTC. This is
server delivery evidence, not phone latency or a fresh ASR/model decode.

Original textSHA256b3c4a233b6fd8c565b9d19b38f06ec84013697c405d6334b42d0d67851e74ade;
correctedSHA25635be5616395f616050463e5630c572591a0daf31952719748d914d2f4043d770.
Full audit/source proof PASS. Both proposals remain unaccepted/undecided;
no personal/F1 record, Calendar draft/sync/action or test meeting created.
Uncertain site name was not guessed. No transcript or client data published here.
Control actual4/reserved0/uncertain0 unchanged; paid calls0 during this operation.

Private receipts/scripts are under .runtime/voice-fragment-install and the exact
protected server release root /home/acc-control/jarvis-fragment-c837c2e-release.
Postupdate encrypted delta preserves release/repair/reconciliation/retention and
fragment evidence. Preparation-only historical documents below remain historical.
