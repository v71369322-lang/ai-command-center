# Offline voice release binding, 23 November 2026

Owner scope remains ordinary Telegram voice intake without paid calls, Google
Calendar onboarding after their return, and their own future task sections.
This is a dependent implementation on PR103 exact
`2fcf472dc0968a671f989960b1bc740775ddd8aa`, branch
`codex/offline-voice-release-20261123`. Do not retarget to main or drop PR102/103.
No deployment permission for an unknown future version is inferred from prior
installations. Exact candidate approval is required after preparation/review.

Implemented optional voice manifest/render/strict validation, separate image and
model/profile custody checks, runtime container checks, shared strict profile,
non-mutating profile/prepare/inspect tooling, and first-addition apply/reconcile
composition through the existing deployment transaction. Normal-stop PAUSED
heartbeat is required before declaring activation verified. Generic Telegram
update rejects voice unless its explicit capability scope is supplied. Existing
boot/update stops the predecessor voice service; independent backup/restore
inspection survives optional voice revocation. Idle polling no longer does full
audit scans or N+1 historical-voice queries; every effect still verifies history.

Validation is recorded against final HEAD/merge-ref in its PR and private
preparation checkpoint. Early local unprivileged deployment scope: 235 passed
before the final additional operator/custody/proxy/idle tests (overlap, do not add).
Final changed deployment/operator scope: **37 passed**. Final PG voice/readback
scope, including idle/audit guards: **23 passed**. These overlap with the broad run.
Ruff all source/tests/scripts/infra PASS. Retained LOW Bandit B105 findings are
fixed environment flags/in-container filenames, documented in SECURITY_REVIEW;
no new MEDIUM/HIGH or ignored vulnerability. Full CI remains mandatory.

Earlier genuine synthetic Ogg/Opus recognition ran successfully in a networkless,
read-only, one-CPU/1GiB Docker container from exact source5f3c764: correct Russian
text, 4.214s audio, 4.727s inference after4.047s load, peakRSS371.5MiB. This was a
local Docker Desktop smoke, not rootless/VPS/user voice acceptance. The successful
build used the actual Git SHA read from git, verified against the image label.
Subsequent2fcf472 disabled ONNX telemetry before initialization; real model/code
behavior is rechecked for a final exact release rather than claiming old-image
evidence for new code.

Latest read-only VPS state before any new preparation: deployment/activation both
VERIFIED on9f6297b; seven current services running. 4vCPU, ~7.8GiB RAM/~4.8GiB
available and41GiB free disk. No Google consent, server install, runtime restart,
paid call, task execution or business-project change occurred during that check.
Prepare a new source/model/profile/image/candidate through the fixed operator,
retain before/after journal evidence, and request only final exact installation
approval when the package and final CI can be reviewed. Google terms/country
selection still waits for the owner. New sections are not guessed.
