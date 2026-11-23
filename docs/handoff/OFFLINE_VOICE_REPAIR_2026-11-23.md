# Offline voice admission repair — 2026-11-23

PR104/c27b2ce passed final CI (45198637466; 2462 application passed,
1 optional-module skip, separately1014 infra; speech23 passed). Owner explicitly
approved exact installation. One stock voice activation was attempted. Seven
standard services started; speech exited1, not OOM. Postcheck correctly refused
verification. Deployment remained INTENT and activation DEPLOYMENT_ATTEMPTED;
apply was not replayed. One bounded same-container start reproduced the failure.

Protected diagnostic traceback identified Store.transaction's Control FOR UPDATE
acquisition timeout (SQLSTATE57014; lock_timeout and statement_timeout both3s).
Existing audit history contained66781 rows; competing poller transactions held
the admission row beyond3s. Synthetic standalone rootless ASR was fast (0.777s
inference for4.214s audio), but this did not prove live worker admission.

A compatible stock Deployment.apply('rollback') restored exact predecessor
9f6297b / bundle2e59a20229b55824fd2aebcbc95ef8a6b1b91fd3bdfc9d314a5aa39c5b21fd93.
Migration/database/Redis/data root/users/owner binding were identical, and the
archived exact connection was restored under the deployment lock. No database
restore or manual deployment/activation journal replacement. Failed activation
remains DEPLOYMENT_ATTEMPTED; rollback-result.json records restored VERIFIED
predecessor. Seven services run; failed voice container remains exited.

Repair branch depends on PR104, preserving its source chain. Voice processing
returns BUSY only for SQLSTATE55P03/57014 on the exact compiled Control row1
FOR UPDATE statement AND parameters. Each retry reacquires leadership and current
profile/connection/epoch checks. A missed heartbeat does not update its timer or
create health evidence. Contention after a read-only download does not mark a
voice permanently failed. No global timeout, permission, audit, lease, model,
network, spending or deployment interlock is weakened.

Local real PostgreSQL voice/readback suite:32 passed, including real competing
transactions, no download/false heartbeat while locked, recovery after release,
exact SQLSTATE/query/parameter rejection, audit timeout remains fatal, and retry
after download. Ruff all source/tests/scripts/infra PASS. Final CI must be checked
against the final repair HEAD and PR merge-ref before claiming release readiness.
No repaired-source deployment or genuine owner voice acceptance yet. Paid calls0.
The earlier c27b2ce approval is not an approval for a different future SHA.
