# Telegram polling latency repair

Owner reported replies taking 3–5 minutes. The pre-repair baseline was parent #95/source
`9ed4fd0dcb66a98dffca85b242ef9e45b5297034`, installed on VPS as
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

Subsequent completed evidence: [PR #96](https://github.com/v71369322-lang/ai-command-center/pull/96),
exact HEAD `67443ae297ed0d49de8d9086fd3347e054ad8231`, merge-ref
`3a88c17d281f329fbfa62400b8b5aee3b7e885a2`. Full CI SUCCESS: 2193 core tests and
separate 1013 infra tests; container/backup smoke and static gates passed.
Synthetic empty-cycle benchmark with 32,001 records, 0.25 CPU/256 MiB:
131.992 seconds / 24 scans before, 7.845 seconds / 2 scans after. This is not
an end-to-end live SLA.

Owner then explicitly approved installation of this exact repair. Candidate
`9e1a5daae43e1eb9ad407efb6bc321a9b0b69d778b8edc39d058237ca29bb231` was installed
through the existing planning activation adapter with one successful apply.
Both journals VERIFIED, actual rootless/planning/financial/worker/watchdog gates
passed, seven services running without restarts/OOM, local backup VERIFIED_LOCAL.
Admission remained halted. No merge, paid AI or access expansion.

The owner sent a real `/help` and reported approximately 10 seconds. Server audit
confirmed received-command → observed SENT in 6.844 seconds. New-source heartbeat
intervals sampled around 19–24 seconds. This is one live command sample, not a
latency SLA. Private installation/acceptance evidence is retained under
`/home/acc-control/telegram-latency-67443ae-release/installation-accepted.json`.
These are the installation-session observations, not a new server probe made by
the later content-acceptance stage. Do not resume old tasks or invoke paid AI.
