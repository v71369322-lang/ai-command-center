# Predeployment audit of PR #8–#16

Audited baseline: PR #16 `de727afc90cbd4a9aab8806dae9323b75fd651dd`.
Scope: repository, failure tests and cloud containers only; no VPS, real secrets,
paid API, live publisher, account changes or merge. The author participated in
the implementation; this is a critical re-examination, **not an independent
third-party assurance or penetration-test certification**.

## Dependency evidence

GitHub metadata confirms all nine PRs remain open/unmerged. Consecutive heads
are ancestors of the next head (`git merge-base --is-ancestor`), for all eight
links. No tracked files are deleted between the PR #8 base and PR #16 head.
This establishes preserved cumulative Git history, not correctness of every
change. Use the cumulative head, not main or the PR #16 diff alone.

| PR | Abbreviated head | Base branch |
|---|---|---|
| 8 | ea7a580 | docs/stage-0c-5-master-plan-audit |
| 9 | 4cadfb5 | feat/f1-synthetic-control-plane |
| 10 | d551cfb | review/f1-security-autonomy |
| 11 | 7ab8a4f | audit/f1-full-system |
| 12 | 3d5dcd9 | infra/f1-vps-preparation |
| 13 | e5b6266 | feat/f1-infrastructure-hardening |
| 14 | fb1ed9e | feat/f2-autonomous-coding-agent |
| 15 | e047b29 | feat/f2-1-real-ai-readiness |
| 16 | de727af | feat/f2-2-first-live-experiment |

## Confirmed defects and corrections

**A1 HIGH — daemon restart bypasses boot interlock.** Renderer assigned
`unless-stopped` to API/worker/broker/watchdog. Docker can start these when the
daemon starts, before the After=docker.service boot unit halts admission. The
cloud smoke's explicit ordered start does not exercise this. Regression
`test_restart_policy_cannot_bypass_boot_interlock` failed against the baseline.
Only DB/Redis now restart automatically; apps require serialized boot. Validator
rejects a profile restoring unsafe restart policies. This favors fail-closed
behavior over availability: a crashed app needs supervised recovery. Actual
systemd boot ordering remains a host test, not proven by the unit test.

**A2 HIGH — boot and rollout can race.** `boot()` previously ignored
deployment.lock while apply() held it, allowing mixed service revisions or
control changes during rollout. `test_boot_cannot_race_update_lock` acquired the
rollout lock and reproduced boot proceeding. Boot now takes that same exclusive,
nonblocking lock and checks VERIFIED only while holding it.

**A3 MEDIUM — mutable source bypass on update/boot.** Only a fresh installation
checked the checkout; Redis executes a host-bound redis.sh. Editing it after
prepare could change behavior despite immutable image IDs and bundle consent.
`test_update_preflight_rejects_modified_bind_source` demonstrated acceptance
with fresh=False. Every operation now checks clean exact Git source and schema
fingerprint. Preserve the original immutable checkout for each release/rollback.
Regenerate bundles with the corrected renderer before first installation.

**A4 MEDIUM — clean host operator import/build ambiguity.** Installing the
source package using normal pip could invoke unpinned hatchling, outside the
hashed runtime lock; service templates did not show an alternative import path.
Instructions now use a Python 3.12 venv, hash-checked binary runtime wheels, no
implicit source build, and PYTHONPATH to a protected immutable operator checkout.
Both user-service templates explicitly set that path. No source-package build
is required for the trusted operator CLI.

All three executable regressions were observed failing before corrections and
passed afterwards: **40 deployment tests + 32 infrastructure tests passed**.
These counts overlap the full Python suite for the deployment cases.
Ruff and OpenAPI passed. Final container/full-suite/CI evidence belongs to the
fix PR; previous PR #16 CI is not evidence for these changes.
A new Python 3.12 venv successfully installed the binary-only hash-locked runtime
dependencies and imported/ran `command_center.deployment --help` through
PYTHONPATH. No source-package backend was invoked. This is a clean operator
environment check, not a clean rootless Ubuntu systemd installation.

## Working behavior versus simulations

Code examination confirms PostgreSQL authority and transactional Outbox,
restricted Redis scheduler, scoped broker/watchdog, lease/fencing/cancel intent,
separate sandbox verifier and durable external-operation intents. Runtime
configs pin Git revisions and images; API/worker receive no daemon socket.
Host rootless status, cgroup enforcement and cross-user socket custody still
require measurements on the actual Ubuntu host. Broker socket access is broad
authority over the dedicated execution daemon, not a harmless Docker proxy.

Git edits, tests, containers, local encrypted dumps and disposable restores are
real implementations. Coding proposals/publication in the reproducible cycle
use mocks. HTTP clients are implemented but no real model, billed usage or real
draft publication is proven. The Python edit grammar is deliberately narrow.
OIDC/JWT/session code exists; the deployment profile's identity provider is
unconfigured and owner access fails closed. It is not a complete iPhone login.

Gateway defaults disabled, checks trusted grants/version/lease/fence and permits
only fixed endpoints; live mode requires explicit permission, runtime authority,
protected credential references and confirmed tariffs. Funds are reserved before
POST, uncertain outcomes retain the reserve and block repeats. First-experiment
gates add exact final consent and 100-RUB cap. No real billing cutoff is proven;
internal reservations cannot guarantee provider/bank charges. Initial VPS
profile mounts no provider credential/config and cannot enable paid calls.

## Conditions and remaining host gates

1. After independently verified SSH identity and separate read-only permission,
   check actual OS, capacity, package state, other workloads, firewall/listeners,
   userns/AppArmor, rootless cgroup delegation and separate user/socket ACLs.
2. Approve exact package/setup/release plan; build pinned images, prepare a NEW
   corrected bundle, install closed services, and perform controlled real reboot
   and fault tests. No global security relaxation if rootless checks fail.
3. Initial install failure intentionally leaves durable INTENT and does not
   automatically overwrite existing data. Manual investigation is required.
   Same-schema application rollback is available; destructive DB rollback and
   database-major changes require a separate reviewed migration/recovery plan.
4. Before owner-facing use, establish authorized VPN/HTTPS/trusted proxy and
   real IdP/MFA enrollment/recovery. Loopback binding is not an egress firewall.
5. Establish independent off-host alerts, encrypted backup/checkpoint custody
   and separately recoverable keys. Current backups are local; WAL/PITR and
   complete VPS-loss restoration/RPO <=15min/RTO <=4h remain unproven.

Verdict for uncorrected PR #16: **do not deploy** (A1–A3). Corrected kit can be
considered for **closed synthetic trials only**, after fix review, successful
regression CI and the host gates above. This is not production readiness or
authorization to access the VPS. The owner needs no PC or manual shell work:
approve read-only audit, then the exact setup/trial scope; the cloud operator
performs routine work within that authorization. Real AI experiment remains a
separate permission with its own financial gates.
