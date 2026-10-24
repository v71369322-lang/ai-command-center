# F2.3 validation checkpoint

No actual VPS has been contacted or changed. The following chronological
checkpoints are retained rather than replacing failed checks with success claims.

* 37 new release-policy/failure tests passed locally; one existing upstream
  Starlette/httpx deprecation warning.
* Ruff and unchanged OpenAPI contract check passed.
* 32 existing infrastructure tests passed separately (not overlapping these 37).
* Pinned Ubuntu 24.04 image installed prerequisite packages and passed the
  networkless read-only OS inventory. This does not prove systemd/rootless.
* Intermediate locked dependency/security audit passed: 64 Python dependencies,
  zero known Python/npm advisories, zero MEDIUM/HIGH Bandit findings; 49 reviewed
  LOW findings. Final-SHA checks remain pending.
* New container smoke is NOT yet passing end to end. Failures exposed early PG
  Unix-only readiness, loopback forwarding and cloud namespace/proxy differences.
  Fixes are checkpointed; the latest run reached synthetic task admission but
  did not obtain SUCCEEDED. More task-reason diagnostics and a test-only executor
  scope adapter are added for continuation. Backup/restore/recreate success is
  not claimed from this failing run.
* Full regression was interrupted after cloud VFS disk pressure and while test
  causes were being corrected. Only owned dangling project images and explicit
  unused project build records were removed; no security/disk guard was lowered.
  A fresh full regression and final-SHA CI are required before removing draft.
* Existing F2.2 test results are historical evidence, not proof of F2.3.

The production deployment controller has no rootful fallback. The separate
cloud smoke deliberately adapts only its disposable test profile to the managed
rootful daemon; it cannot establish rootless/systemd/AppArmor/cgroup delegation,
cross-user ACL, real reboot, network policy, iPhone VPN/HTTPS/MFA or offsite custody.
Final results must distinguish these boundaries, and no skipped check is a pass.

## Subsequent verified progress

* Full local suite on `03030330b8f66cb3f602ba4ee83dd62b8ee6683c`: **242 passed**,
  one upstream warning. Existing API/worker, backup/restore, restart/cancellation,
  worker SIGKILL/watchdog, F2 repair/verifier and runtime boundary drills passed.
* CI run 40122461332 on that head passed 241/242 tests but failed the mandatory
  Docker OOM flag assertion. Exit 137 alone remains insufficient. The bounded
  asynchronous OOM evidence wait was increased from 3 to 10 seconds; neither
  expected OOMKilled nor exit-code assertions were removed or relaxed.
* At `0028366`, the new **real-container F2.3 smoke passed**: normalized API
  task contract -> execution/verifier -> quiescence -> encrypted backup ->
  separate networkless restored database with audit anchor -> application
  recreation -> complete service restart -> identical stored result.
* The fixture now uses the actual API command defaults (budget/time/resource
  fields); missing fields previously left its task READY. Loopback HTTP traffic
  explicitly avoids the cloud HTTP proxy. Plain HTTP session exchange must
  return `403 https_required`, not falsely bypass the HTTPS requirement.
* PostgreSQL readiness now checks TCP so initdb's Unix-only temporary server is
  not mistaken for readiness. API has a separate loopback-published access
  bridge; this is not an outbound firewall. Service images, secret scopes and
  mounts remain constrained by the manifest validator.

Final release CI and exact-SHA results are recorded on
[PR #16](https://github.com/v71369322-lang/ai-command-center/pull/16).
Do not treat the intermediate failing run as a successful full CI. The final
PR must remain draft unless its full verification and Ubuntu probe succeed.
Known warnings include upstream Starlette/httpx and Node action deprecations.
