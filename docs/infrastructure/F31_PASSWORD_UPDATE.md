# F31: prepare the password login update without touching the installed release

Application dependency: PR #20 HEAD `4cc6ec46bf461d65958f013bb23ac2234b9a7fd3`,
CI https://github.com/v71369322-lang/ai-command-center/actions/runs/40504857532
success. Operational base: F30 `93dcb68429c24879cccec533f6439695788551ab`.
F31 reuses the bounded F30 handoff implementation with a new explicit source
pin and separate paths. It does not silently copy/change the application, merge
PRs or change F30's installed authority. Owner authorized continuation after
password-login implementation and successful VPS F30 trial.

## Sequence

1. Re-register the existing stopped one-job runner in the owner's trusted SSH
   session with a fresh GitHub registration token, entered masked, never in chat,
   argv, history or repository. Refuse if service is still active or local
   `.runner` config remains; reconcile rather than deleting its registration.
   No repeat runner download, dependency installation, sudo or Docker socket grant.
2. A reviewed push to `ops/f31-password-prepare` with `[run-f31]` schedules one
   job on label `acc-bootstrap-only`. Read-only GITHUB_TOKEN checks out the exact
   approved application and stages a bounded Git object packet and helper files.
3. Owner snapshots/verifies the new bootstrap SHA-256 in root SSH. New root-owned
   units/scripts/handoff/receipts use separate `acc-password-*` names and
   `/home/acc-control/f31`. No overwrite of F30 helpers, source, bundle or state.
4. Fixed service runs as acc-control: checks free space/rootless/resource support,
   rehydrates only the approved Git commit, and verifies requirements.lock matches
   old clean pinned source before reusing its tools environment. Existing Docker
   cache is reused by the ordinary build script; image IDs/revision remain pinned.
5. Prepare/inspect a new password-bound bundle, **same** `/home/acc-control/f30/state`,
   origin `http://127.0.0.1:18000`, explicit SSH-loopback HTTP option. No init-state,
   install, update, automatic resume, public port or real credential is included.
6. After source arrives, owner provisions the real password using the PR #20
   interactive CLI in SSH. The verifier goes to existing private state; password
   is never supplied to runner or this chat. This file is not needed to render
   the new bundle but is mandatory at update preflight.
7. Review exact bundle digest, approve compatible update, retain old checkout,
   images and bundle, take verified backup through the existing update controller.
   Invoke **update**, not install/init-state. Update and postcheck need the new
   PYTHONPATH plus existing pinned tools. Login/browser verification follows.

Only prepare is authorized by this workflow. The final credential provision and
exact-bundle update are explicit operator actions; no broad remote shell is added.
Workload/loopback controls remain in place. The runner is still ephemeral; a
persistent constrained automation lifecycle is not claimed. No public HTTPS,
real Telegram/AI calls, CRM data, paid services or production readiness.

## Failure handling and evidence

Existing attempt/destination blocks overwrites. A failed build must be reconciled
before retry, including daemon-side builders. Private logs stay under f31; only
inspect receipt is readable by runner. Watcher is not enabled for automatic boot.
Cloud tests validate the source pin, tampering rejection, bootstrap digests and
preservation of old paths; they do not prove actual VPS build or password update.
