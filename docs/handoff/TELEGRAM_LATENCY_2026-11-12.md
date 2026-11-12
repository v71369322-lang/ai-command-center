# Telegram polling latency repair

Owner reported replies taking 3–5 minutes. Parent #95/source
`9ed4fd0dcb66a98dffca85b242ef9e45b5297034` is actually installed on VPS:
candidate `7d731bc04de5d53400b54362351494bc8ff2c1a17b0d0c058c9d06f72e228821`.
The one apply reached its target but failed its initial Telegram health check.
Existing exact reconciliation subsequently closed both journals VERIFIED without
apply replay, binding replacement or manual journal edits. Actual rootless
planning/financial/worker/watchdog checks passed, Telegram polling was observed,
and a local encrypted post-install backup was verified. Admission remained halted;
no paid call or merge was performed. Private evidence remains on the control host.

Fresh read-only latency diagnostics found about 32,000 audit records, no NEW
delivery backlog, Telegram CPU limit 0.25, and heartbeat intervals around 70–105
seconds. A full audit scan in a maintenance container took 0.877 seconds; this is
not the Telegram container's differently CPU-limited scan time or end-to-end
message latency. No payloads, credentials or owner messages were exported.

The idle poll loop called `deliver_one` twenty times even after an empty result.
Every call performed a full history scan. The repair breaks at the first empty
result while retaining the twenty-delivery batch ceiling. Empty recovery and
pending-resume paths, and an empty delivery selection, return before an audit
scan; no row is modified, message sent or authority created on those no-op paths.
Any actual recovery, pending processing or delivery still verifies the full audit
under the same Control lock before mutation or external I/O. Polling itself still
checks the audit before fetching updates. There is no trusted-prefix cache.

Full history validation selects only sequence/previous/digest/event rather than
materializing ORM Audit entities. It still checks every historical link and any
supplied anchor, including middle-batch edits and missing/mismatched checkpoints.
No schema, resource bound, timeout, permission, lease, fencing, source/image pin,
financial interlock or runtime socket policy changes.

Locked Linux/PostgreSQL targeted regression: 162 passed, 3 Docker-executor cases
deselected locally; those cases remain enabled in normal CI. New coverage checks
idle termination, draining multiple replies, historical corruption before HTTP,
multi-batch validation and anchor failures. Ruff, native API contract and diff
checks passed. Earlier environment-only attempts lacked a local Redis endpoint,
runtime role or executor access; they are not counted as passed coverage.

Benchmark and final exact PR/merge-ref CI evidence are recorded in the dependent
Draft PR. Synthetic timing is not a live Telegram acceptance result. This repair
has not been deployed; a new exact release/access approval is required before
changing the installed candidate. Do not resume old tasks or invoke paid AI.
