# F2.3 validation checkpoint

Implementation is in progress; no actual VPS has been contacted or changed.

* 34 new release-policy/failure tests passed locally; one existing upstream
  Starlette/httpx deprecation warning.
* Ruff and unchanged OpenAPI contract check passed.
* New container deployment/restore/recreate smoke and pinned Ubuntu 24.04
  prerequisite probe are implemented but have not yet completed execution.
* Full regression, dependency/security audit and final-SHA CI remain pending.
* Existing F2.2 test results are historical evidence, not proof of F2.3.

The production deployment controller has no rootful fallback. The separate
cloud smoke deliberately adapts only its disposable test profile to the managed
rootful daemon; it cannot establish rootless/systemd/AppArmor/cgroup delegation,
cross-user ACL, real reboot, network policy, iPhone VPN/HTTPS/MFA or offsite custody.
Final results must distinguish these boundaries, and no skipped check is a pass.
