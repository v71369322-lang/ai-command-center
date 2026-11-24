# Offline voice live checkpoint — 2026-11-24

Implementation PR106 exact956c19f28dee91b6b4edf3491f74405af62113bf is installed on
176.12.75.135. This documentation checkpoint is a separate descendant branch;
it is NOT a new application image or deployment. Implementation CI45318928341
attempt2 SUCCESS on mergee246849709ca00a7d145cd4e0e571e30c8665dd6, same tree
6ac6b3931be55c878d658353273c7d16330c137a as implementation HEAD.2473 application
passed,1 optional-runtime skip; separately1014 infra; speech23 passed. Do not add
the overlapping local89 or repeated attempts. First attempt completed all2473
and core smokes but was cancelled at25min after slow Ubuntu mirror downloads;
last prerequisite probe was not completed then. Attempt2 completed it normally.
No CI is claimed for this later documentation-only checkpoint commit.

Owner's current request explicitly authorizes fixing exit137, restoring intake
and completing offline voice, without paid calls. No merge was performed. No
Google consent, new credentials/access, SSH/firewall/users/units changes or other
business-project/CRM changes. Paid calls0. Google remains deferred.

## Cause and repair

Kernel journal proves maintenance MEMCG OOM under256MiB (exit137). The problematic
Gateway.check_ledger eagerly fetched all audit ORM entities.956c19f selects only
matching action event projections with256-row streaming, preserving latest
anchors and missing/tampered rejection. Full Store.check_audit remains mandatory
and already streamed before this repair. No memory/CPU/SQL timeout or permission
limit increase. Local real PG89 checks passed under256MiB/1CPU, including20000
unrelated12KB events. Actual VPS checkpoint/snapshot/financial check with the
exact new image passed in256MiB, peakRSS72.9MiB,6.02s. Exact-image networkless
rootless synthetic Ogg ASR:4.214s audio,1.008s inference after0.755s load,
359.3MiB RSS, correct Russian text. This is not phone/Telegram voice acceptance.

## Actual activation

Release/home/acc-control/offline-voice-956c19f-release, clean source/head pinned.
Candidate85910918ebe5903a832c8157f813ad5bdff4232ad883bd3318208d52e2534531.
Preparationc0b6410abf0a969dfb57b497c5059c1c29ab34e7017959c5debf4326fe7df7f3.
Voice capabilitya7babfb213807f46c185c1f509941faa0af474df446eafa661a34a3cf234abe7.
Previous2e59a20229b55824fd2aebcbc95ef8a6b1b91fd3bdfc9d314a5aa39c5b21fd93.
Source/profile/model/images/execution-daemon copies/stock inspect checked before
ONE stock apply. Apply ended1 because maintenance Control FOR UPDATE acquisition
hit its3s SQL timeout, not OOM. Eight exact-target services remained running.
Apply was NOT replayed. Standard read-only reconcile initially hit the same
entry contention. All runtime/source/binding/preparation guards remained intact.

Bounded operator repair: maintenance-only Python prelude retries ONLY transaction
ENTRY when the existing exact admission_busy predicate recognizes SQLSTATE57014
or55P03 on the exact compiled Control row1 FOR UPDATE statement AND parameters.
Five attempts,1s delay; original3s SQL timeout/256MiB/.5CPU/120s container limit.
Session body is yielded outside retry catch, so body/commit errors are NEVER
replayed; unrelated SQL/audit errors propagate. Five local operator tests pass
(entry resource cleanup, exact bounds, non-admission failure, body failure).
Protected helper and SHA receipt are outside the clean source checkout:
maintenance_admission.py / maintenance-retry-receipt.json. This retry helper is
an OPERATOR workaround, not code shipped in956c19f. Persisted application code,
images, bindings and journals were not replaced by this helper. Existing stock
reconcile, using all unchanged preflight/postcheck checks, wrote BOTH journals
VERIFIED. Result:reconcile-result.json, runtime_changedfalse, binding_changedfalse,
paid_calls0. Never manually rewrite deployment/activation phases or replay apply.
Earlier failedc27/6ed activation records remain preserved with rollback receipts.

## Telegram resume and limitations

Readonly voice heartbeat is not in telegram_control.TRANSPORT_EVENTS. It therefore
invalidated a resume card even before TTL. This remains a code limitation in956;
do not describe repeated /stop→/resume as independently fixed by the ledger patch.
For this activation, a bounded same-container voice stop prevented new heartbeat
events while genuine owner Telegram /resume and its observed confirmation ran.
Then the SAME pinned voice container was started again, with no binding/image/
source change. Protected receipts:voice-resume-coordination*.json. No owner grant
was injected in the database. Future normal resume may require this coordination
until an explicitly tested narrow readonly-heartbeat projection fix ships.
Maintenance entry retry should also become a reviewed stock operator feature.
Do not silently apply these workarounds to effectful task bodies or other services.

Latest post-resume read-only health:normal admission OPEN, epoch50, recoveryfalse,
activeTasks0; fresh exact956 voice heartbeatIDLE age7.0s. Telegram/voice running,
OOMKilledfalse, exit0; all8 services running at verified activation. Financial
postcheck verified4 historical ExternalActions COMPLETE/reserved0. Activation
journal task_admission_resumedfalse records that INSTALLER did not resume;
subsequent owner UI resume is separate audited consent and must not be forged
into the activation record. post-resume-health.json records current observation.

## Remaining acceptance

No new voice notes since the explicit cutoff2026-11-23T14:59:23.606264+00:00.
Phone microphone→real Telegram voice→download→offline ASR→delivered readback→
confirmed saved request is therefore NOT observed yet. Owner was asked to send
one short nonsensitive test voice note; no commands/copied server scripts needed.
Telegram Web test-file preview only offers an audio attachment, not a voice;
preview was cancelled, not sent. Do not inject fake Telegram updates, modify
inbox/grants, or call synthetic tests genuine owner acceptance. On receipt,
inspect real metadata/results without exposing voice/file IDs or private text;
verify one readback and exact confirmation creates one saved request and no
Task/paid action. Existing owner-delegated bot UI operation is authorized.

Private local checkpoint.runtime/voice-release-956c19f/checkpoint.json and
INSTALLATION_HANDOFF.txt; server receipts retained under the exact release.
Do fresh reconciliation on continuation; reports are not current server state.
