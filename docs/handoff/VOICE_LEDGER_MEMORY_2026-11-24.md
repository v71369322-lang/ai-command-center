# Voice ledger memory repair — 2026-11-24

Owner explicitly requested fixing exit137, restoring Telegram intake and completing
offline voice operation, without paid API calls. This bounded repair continues
PR105; no merge, Google consent or additional privileges are authorized.

Fresh VPS reconciliation: VERIFIED predecessor9f6297b after failed6ed4b0a
activation/compatible stock rollback. Failed activation receipts preserved.
Kernel journal confirms three maintenance-container MEMCG OOM kills at about
260MiB anonymous RSS under256MiB limit. Voice itself stayed running until rollback.
PlanningUpdate.postcheck calls Gateway.check_ledger, whose unbounded ORM scan of
all Audit rows materialized unrelated history. Store.check_audit already streams
and must not be bypassed or incorrectly blamed.

Repair selects only Audit.event for supplied action IDs, streams256 rows, and
preserves latest matching ledger_digest per action and rejection of missing or
changed anchors. Caller audit-chain checks remain unchanged. No memory/service/
permission/network/financial limit increases. Empty action collections remain valid.
Local real PG regression with20000 unrelated12KB events plus matching anchors,
latest-anchor selection and tampering/missing rejection, and existing planning/
Git/voice coverage:89 passed in a256MiB/1CPU container. No paid calls.

Real owner Telegram /resume confirmation restored normal intake on predecessor;
no old cancelled tasks restarted. Full CI/new exact source image/package and live
voice readback/save acceptance still required before completion. User authorization
for this repair is current; record exact candidate and a fresh bounded deadline
only after final CI/prepare/inspect. Do not replay either failed apply.
