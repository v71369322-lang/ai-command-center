# F30: one-shot rootless release preparation

Base: PR #17, `53565cc2ca232fb2cf6d6552a3ae04b462d92956`. This operational branch
does not change the application or merge prior PRs. Owner's F29 deployment scope
and confirmation of F30 runner registration authorize preparation. Host bootstrap
is performed by the owner in the existing SSH session, not by a claimed cloud SSH.

## Narrow authority

The runner has only label `acc-bootstrap-only` (no default self-hosted label).
The push workflow runs only on `ops/f30-vps-prepare` and an explicit `[run-f30]`
commit message. There is no PR trigger. Labels and branch conditions alone are
not a security boundary against repository writers. Actual authority is bounded
by root-owned service programs and a fixed approved source commit.

GitHub checkout uses read-only job token, persist-credentials=false. No deploy
key, PAT or root credential is supplied. A 2.3 MB object packet contains only
the approved commit/tree/blobs, never `.git/config`, hooks or checkout credentials.
An independent helper bounds input, verifies every object ID and the fixed commit,
reconstructs a clean shallow checkout and does not execute runner-provided shell.

The operator snapshots bootstrap files without following symlinks and verifies
fixed SHA-256 before installing root-owned scripts and units. A path watcher
accepts only a request to start this one service, not a command string. Runner
retains no sudo or Docker socket access. The service runs as acc-control and
uses its existing socket rights. It cannot install the application: only build,
init-state, prepare and inspect are implemented. No OIDC relaxation, network
publication, live integration or task admission occurs.

## Operational sequence

1. Push reviewed operational commit with `[run-f30]`; one registered runner stages
   scripts and source and logs BOOTSTRAP_FILES_READY. No root helper exists yet.
2. Owner runs the supplied checksum-verified bootstrap once in root SSH. It may
   install Git/python3.12-venv if missing, and registers two fixed systemd units.
   It does not modify existing Docker units, users or AppArmor. Existing targets
   block reruns rather than overwriting prior progress.
3. A root-owned snapshot of source and helper files is installed. Watcher starts,
   workflow requests preparation. Service checks >=25 GiB free, tools, rootless
   and cgroup limits and both socket rights before building the exact revision.
4. Private state is generated once under `/home/acc-control/f30`. Operator logs
   remain there, unreadable by the runner. Only inspect's non-secret receipt
   (revision/bundle_digest/go_live=false) is readable in acc-prepare-receipt.
5. Review digest and protected logs. Install requires a subsequent exact-bundle
   approval and is intentionally not implemented in this channel.

No automatic retries: a durable attempted marker blocks duplicate starts. On
failure investigate the private log and actual Docker state before any retry;
do not delete markers to claim recovery. Worker cancellation does not cancel this
independent preparation service. Root operator can stop acc-prepare-fixed.service;
this does not prove all daemon-managed build processes stopped. Reconcile builders
before retry. Source and services are not removed automatically.

## Honest limits

Only cloud tests are proven before the first host job: six new handoff tests,
38 infrastructure tests total, Ruff, Bash syntax and systemd-analyze verify.
These do not prove host ACLs, egress or successful VPS builds. Builds run in
separate Docker daemons; service cgroups would not bound daemon-managed builds.
The first attempt is serialized, reserves >=25 GiB and must be observed for
resource usage. No broad daemon policy or quota is silently changed.

The one-job runner is ephemeral and ends after this workflow; host service has
a separate two-hour timeout and remains root-owned. Watcher is started, not
enabled on boot. Partial preparation and reboot do not auto-resume. Persistent
deployment automation needs a later reviewed lifecycle, not reuse of registration
tokens. Real iPhone OIDC/MFA, external backups and install/postcheck remain gates.
