# F2.3 validation checkpoint

Implementation is in progress; no actual VPS has been contacted or changed.

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
