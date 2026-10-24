# F2 validation record

Initial implementation evidence is pending the final clean-commit cloud run and
GitHub CI. This file will be updated with actual results, not inferred success.

Offline checks already performed during development: Ruff, TypeScript/Vite,
OpenAPI export comparison and 19 coding tests passed. These include real local
Git edits/commits, actual four-case acceptance execution and independent replay,
forged evidence/path/pin/budget rejection, and HTTP adapter mock tests. They do
not prove real AI-provider access, real GitHub publication, rootless VPS isolation,
external backup storage, real MFA or production readiness.

Planned final gates: full F1/F2 pytest regression suite, mobile Chromium flow,
real two-stage broker execution and cancellation/deadline/watchdog-loss cases,
all infrastructure tests, dependency/static audits, container API/worker cycle,
backup/restore, restart/recovery and final-head GitHub CI.
