# F2.3 closed VPS deployment kit

Base: PR #15, `e047b2977d82ab7511edb6532afbc7687da1b887`. This stage changes
only the repository and the isolated cloud lab. No contact with either VPS is
authorized. A purchased FirstVDS plan is not evidence of the actual OS/security.

## Audit of available components

| Component | Implemented behavior | Remaining evidence / limit |
|---|---|---|
| F1 | PostgreSQL authority, Outbox, Redis transport, deterministic permissions, approvals, cancellation, fencing, audit | Real host isolation and emergency access untested |
| F2 | Real isolated Git workspace and tests, bounded repair, separate verifier | Reproducible provider is a mock; permitted Python grammar is narrow |
| F2.1 | Responses HTTP adapter, trusted credential gateway, reservation journal, REST draft publisher/reconciliation | Real credentials, billing, external calls and real publication untested and disabled |
| F2.2 | Bounded first-experiment profile, nine expiring gates, exact final consent, budget calculation, mobile screen | Account access, payment bounds, repository/App and final paid consent missing |
| Auth | Standard JWT/OIDC verification, MFA claim, revocable secure session and CSRF checks | No real IdP enrollment or convenient browser redirect login; production access blocked |
| Runtime | Restricted broker, independent worker watchdog, resource limits and stop ledger | Rootless host/cgroups/AppArmor and separate-UID socket ACL not proven |
| Recovery | AES-GCM, verified local archives, disposable restore and audit checks | External immutable custody/key recovery, WAL/PITR, full-host disaster drill absent |

The old `infra/vps/compose.control-plane.json` remains historical preparation,
not a deployable current release. This kit derives its services from the exact
current `compose.yaml`, then narrows and freezes them into a release bundle.

## Deployment architecture

Two local rootless Docker daemons, separate accounts/subordinate-ID ranges:
`acc-control` runs PostgreSQL, Redis, API/web, worker, broker and watchdog;
`acc-exec` runs only disposable executors. Only broker/watchdog receive the
execution socket; neither sees the control daemon socket. The host operator can
administer both; it is a trusted role, not available to coding agents.

Service UID 0 **inside the control rootless user namespace** maps to the
unprivileged host control UID, allowing 0600 bind secrets without broad file
permissions. It is not host root. Application containers drop all capabilities,
are read-only and have no administrative socket. A rootful daemon is refused.
Broker compromise still grants broad control over the execution daemon; rootless
Docker is not a complete hostile-code kernel escape boundary. Only synthetic
tasks are eligible. An additional sandbox/VM remains a gate for broader threats.

Database/worker/runtime service networking is internal. API additionally has an
access bridge because Docker internal-only bridges do not reliably publish host
ports. This bridge is **not an egress firewall**; host-specific egress controls
remain to be audited. API publication is exactly
`127.0.0.1:8000`; PostgreSQL/Redis/broker/watchdog have no host ports. Real AI
and GitHub integrations have no mounted credentials/config and remain disabled.
The API is fixed to unconfigured OIDC and rejects owner access. This is a closed
service installation, **not owner-facing go-live**. No VPN/HTTPS/IdP is invented.

## Future authorized clean Ubuntu 24.04 sequence

The following commands are for the authorized cloud operator in a later stage;
the owner is not required to type them or use a PC. Never run them during F2.3.

1. First obtain independent SSH host-key evidence and separate read-only audit
   permission. Use `infra/vps/read_only_probe.py` locally on the audited server.
   Check Ubuntu 24.04, 4 CPUs, at least 7 GiB RAM, >=15 GiB free installation
   space, load, package audit/update state, userns/AppArmor, cgroup v2 delegation,
   listening ports, SSH keys/firewall and unrelated workloads. Stop on conflicts.
   No automatic updates, server resets or firewall changes are part of a probe.
2. Select exact available Docker CE/containerd/buildx/Compose package versions
   from the official Docker Ubuntu repository. Record their origin/version and
   compare official signing-key fingerprint. `bootstrap_f23.py` prints a plan
   without mutation when `--approved-plan` is absent. Versions have no fabricated
   defaults. Its apply mode requires the exact printed digest and root operator
   authorization, Ubuntu/systemd/capacity and absence of an existing rootful
   daemon. Partial failure stops; do not rerun blindly over created accounts.
3. After separate host-change permission, apply the reviewed plan. It installs
   prerequisites, masks the unused rootful daemon *before* Docker package install,
   creates the two accounts with subordinate IDs, enables lingering rootless
   daemons and grants only control-UID access to the execution socket. Socket ACL
   is reapplied by the execution daemon's user-service drop-in after reboot.
   It never opens ports, alters SSH/firewall, or changes unrelated services.
   Official references: <https://docs.docker.com/engine/install/ubuntu/>,
   <https://docs.docker.com/engine/security/rootless/>. Ubuntu 24.04 AppArmor and
   restricted unprivileged user namespaces must be checked; do not disable these
   protections globally to force a passing rootless check.
4. As control user, create a protected Python 3.12 tools virtual environment:
   `python3.12 -m venv /home/acc-control/tools`, then install using
   `/home/acc-control/tools/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r CHECKOUT/requirements.lock`.
   Use `PYTHONPATH=CHECKOUT/src` for operator commands. Do **not** use `pip install .`:
   the project's unpinned build backend is not included in this runtime lock.
   User-service templates set PYTHONPATH to the immutable operator checkout;
   adjust that protected absolute path during authorized setup. A missing wheel
   blocks setup rather than permitting an unreviewed source build.
   Keep each release checkout immutable
   and clean. A later release/rollback needs its original source/artifacts.
   Build via `sh infra/vps/build_release.sh` with the two audited UIDs; it refuses
   rootful endpoints, builds exact-source images and transfers only executor
   image objects into the execution daemon. No registry pushes are performed.
5. Initialize state once with `python -m command_center.deployment init-state
   --data-root /home/acc-control/state`. Files are private synthetic DB/runtime
   credentials and backup key, not OpenAI/GitHub credentials. Existing state is
   never overwritten. Copy the backup key to independently approved custody
   before relying on backups. Losing the host and its only key loses recovery.
6. `prepare --bundle /home/acc-control/releases/RELEASE --source CHECKOUT
   --control-uid UID --execution-uid UID --data-root /home/acc-control/state`
   freezes a manifest and normalized Compose JSON. It checks clean source,
   immutable image IDs/source labels and migration fingerprint. It does not
   install or start services. `inspect --bundle RELEASE` prints the review digest.
7. After exact release permission, `install --bundle RELEASE --approved-bundle
   DIGEST` rechecks both socket identities, rootless/cgroup resource support,
   image labels in both daemons, private files and local port availability.
   An existing data volume without a deployment journal blocks installation.
   It starts DB/Redis, explicitly bootstraps current additive schema/roles via a
   bounded trusted maintenance job, halts admission, starts all services and
   checks DB/audit, Redis, container state and watchdog freshness. All subsequent
   operations recheck the checkout because `redis.sh` remains a host bind.
8. Install the reviewed user-service examples with actual protected tools paths;
   enable `acc-f23.service` and `acc-f23-backup.timer`. Boot selects the verified
   bundle from the atomic deployment journal, refuses partial installs and
   halts admission before workers start. Only DB/Redis use `unless-stopped`;
   application containers use `restart: no`, so Docker cannot bypass the boot
   interlock. Boot and updates take the same exclusive deployment lock. Test a
   real reboot after separate permission. A crashed app is intentionally stopped:
   watchdog expiry blocks unsafe work; availability requires supervised operator
   recovery and host monitoring. This kit does not claim automatic app recovery.

All CLI examples are `python -m command_center.deployment ACTION ...`. No SSH
client, remote target or provider credential is embedded in the kit.

## Updates, rollback and failure handling

Build a new clean, reviewed release first; prepare a new bundle and retain the
old one. `update --bundle NEW --approved-bundle DIGEST` takes an exclusive local
lock, halts new work, waits for PG state and verified runtime ledger to have no
active/uncertain runs, checks the execution daemon is empty, encrypts/verifies a
backup, then stops only application services. It never removes the PG volume.
Durable INTENT is fsynced before replacement. Checks run before VERIFIED is
recorded. Admission is never automatically reopened.

`rollback --bundle OLD --approved-bundle OLD_DIGEST` permits only the recorded
predecessor, with identical DB image and migration fingerprint. It repeats safe
quiescence/backup and replaces application images; it does not restore a database
or reverse migrations. A failed update's INTENT may roll back only to that exact
predecessor after the same absence checks. Failure to confirm stopping blocks
rollback and requires investigation. An interrupted initial installation needs
explicit local reconciliation; deleting journal/volume is not recovery.

Changing schema/admin code or PostgreSQL image requires a separately reviewed
migration/compatibility plan. Even additive migrations must not be silently
reversed. Keep two verified releases. No auto-prune, `down -v`, data-directory
deletion, automatic task resumption or approval renewal exists in the operator.

## Backups and capacity

`backup`, `verify-backup`, `backup-status`, `restore-check` are working operator
commands. Archives include dump checksum, source bundle and audit checkpoint;
AES-GCM read-back authentication precedes success. `restore-check` creates a
fresh networkless tmpfs PostgreSQL instance, checks the complete audit chain
and checkpoint, interlocks restored tasks/approvals/sessions, then removes only
that disposable target. It cannot restore over primary `f1`.

Timer attempts a local dump every five minutes. Local quota is 256 MiB, dump
limit 64 MiB, free-disk floor 1 GiB; no old archive is silently deleted. A stale
receipt (>900 seconds), corrupt copy or missing backup is an incident, not a
successful RPO claim. Alert delivery/timer OnFailure and offsite transfer remain
deployment gates. No local receipt is labelled independent. Offsite immutable
storage, isolated key custody and full-VPS loss recovery require separate setup.
RPO <=15 min / RTO <=4 h remain provisional and unproven; dump schedules alone
do not establish them. WAL/PITR is not implemented by this kit.

Calculated starting allocation: PG 1 GiB, Redis 128 MiB, API/worker/broker 256 MiB
each, watchdog 128 MiB, one executor 128 MiB; reserve >=2 GiB for OS/runtime and
extra capacity for maintenance/builds. Limits and actual host enforcement must
be tested. Work filesystem is bounded tmpfs, services use 2x5 MiB logs, executor
limits remain stricter. Monitor disk at 15/10/5 GiB free, prohibit concurrent
builds/large restore near limits; current runtime admission floor is 1 GiB.
No performance or 80-GB disk durability guarantee follows from this estimate.

## Owner actions, in dependency order

1. Authorize read-only host audit after access/host identity is restored.
2. Review its findings and approve the exact local setup/release plan, including
   package installation, accounts, rootless daemons and a later reboot trial.
3. Separately authorize closed iPhone access: reviewed VPN, HTTPS certificate
   trust, real IdP/MFA enrollment and recovery of a lost phone. Existing JWT
   adapter alone does not provide a convenient complete login flow.
4. Approve independent backup/key/checkpoint custody and off-host alerting; new
   paid commitments need separate approval within the existing spending ceiling.
5. Review synthetic VPS trial evidence and explicitly accept the stage. Real
   AI/GitHub experiment permissions remain the separate F2.2 gates.

No production readiness, real API execution or actual server configuration is
claimed. The owner approves boundaries; the cloud operator performs authorized
ordinary technical steps without per-command architecture questions.
