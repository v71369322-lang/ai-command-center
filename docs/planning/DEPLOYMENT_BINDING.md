# Planning deployment binding and production factory

Consistent input/candidate construction and exact activation workflow:
[CANDIDATE_ACTIVATION.md](CANDIDATE_ACTIVATION.md).

This opt-in composition extends the existing deployment manifest and interlocks.
No enabled flag, RPC endpoint or second permission mechanism is added. A release
without `planning` renders no planning files, key mount, control socket or broker
egress; an unconfigured production factory still denies planning before claim.

## Protected inputs

The dedicated control user prepares two separate canonical private directories,
outside both source checkout and shared state root. Both are 0700, owned by that user; files are 0600,
regular, single-link and not symlinks. Directory inventory is exact:

| Directory | Files | Mounted into |
| --- | --- | --- |
| profile directory | `profile.json`, `host.json` | Telegram and broker, read-only at `/run/planning` |
| key directory | `openai.key` | Broker only, read-only at `/run/planning-key` |

The profile contains fresh operator-reviewed tariff/account/funding/data-sharing
evidence and existing bounded financial limits. Its runtime binds the target
source, semantic host declaration digest and operator-supplied SHA256 of exact
credential bytes. These are not generated from test values. Prepare/preflight
and factory startup inspect key metadata through a protected descriptor; they
never read key bytes or contact a provider. The existing guarded gateway verifies
the credential bytes only after exact task authority, before provider I/O.

The private host declaration binds the broker image ID/source, fixed
`acc-f23-runtime-broker-1` name, execution endpoint
`unix:///var/run/docker.sock`, ledger `/var/lib/f1-runtime/ledger.sqlite`, and
separate `attestation_endpoint=unix:///run/user/CONTROL_UID/docker.sock`.
Its metadata digest uses `planning_host.metadata_document`: selected public
environment, policy (including tmpfs), mount policy and attached network names.
It excludes future container ID/hostname and profile/host SHA environment values,
so exact declarations can be prepared before container creation without a hash
cycle. The actual running identity is measured later; a prediction is not host
acceptance. New source requires new declarations/profile pins.

## Deployment preparation

Use the existing `python -m command_center.deployment prepare` workflow and its
usual exact source/images/Telegram binding arguments, adding both:

```text
--planning-profile-directory /private/operator-planning-profile
--planning-key-directory /private/operator-planning-key
```

Partial options, absent Telegram binding, mixed first-experiment integrations,
overlapping directories, stale evidence, wrong source/image/host/socket/ledger,
unreviewed environment or mounts fail closed. Existing default deployment output
is unchanged. The resulting manifest pins raw file SHA256, semantic profile/host
digests and credential identity. It does not contain credential values.

Only broker receives `planning-access` egress. API, worker, watchdog and executor
receive no planning profile, credential or control socket. Telegram receives
only metadata and its existing Telegram access. Compose validators enforce exact
planning environment/mount/network scope. Runtime postcheck independently checks
actual mounts (including aliases and parent-directory leaks), environment and
network inventory for every service, loads Telegram's mounted profile and repeats
broker rootless/image/host attestation. File-only checks do not accept a runtime.

## Separate control attestation

Execution Docker and control Docker are separate rootless daemons. Broker cannot
attest its own control-plane container through the execution daemon. The planning
binding therefore gives only the trusted broker an additional control-user
socket bind at its exact `/run/user/CONTROL_UID/docker.sock` path. Host attestation
uses this daemon for fixed self-container/image inspections; job execution stays
on the original execution backend. Both daemons must pass rootless/cgroup-v2/
systemd checks. The factory requires the explicit separate attestation endpoint;
there is no production fallback to the execution daemon.

**A read-only socket bind does not make the Docker API read-only.** This socket
is administrative capability over the control user's rootless containers. No
untrusted executor/model code or public RPC receives it, but an actual deployment
must include this exact access addition in the owner's separate deployment/access
authorization. This implementation does not install the bind or widen live access.

## Factory and authority

`create_broker_app` loads the exact five installed `F1_PLANNING_*` variables.
Unknown variables, missing pins, alternate paths, bad custody, stale evidence,
missing runtime or an unbound declaration abort startup. Before creating the
broker/dispatcher, it attests source, actual broker image/command/policy/self
identity using the control daemon while retaining the execution backend.
Startup does not read provider credentials, claim a task, create a grant or
reserve money. Existing injected-service tests do not prove production installation.

Subsequent submission/runner attestation, F1 approvals and fencing, observed
Telegram consent, profile/context/source pins, financial reservation, one-call
INTENT and unknown-outcome handling remain mandatory. Directory inventory is
rechecked by installed host guards. Deployment preparation and postcheck confer
neither one paid call nor automatic resume. No old tasks are restarted.
Independent backup/status/restore inspection skips optional planning admission
evidence checks; expiry cannot disable backup. Source/image/state/security checks
remain. This does not bypass the planning gate on prepare, apply, boot or postcheck.

The offline review package now records supplied planning pins and deployment
binding is no longer a missing code prerequisite. It intentionally remains
`BLOCKED_NOT_ACTIVATABLE`: built/inspected exact images, fresh private evidence,
independent live rootless acceptance and exact deployment/access authorization
remain separate gates. Old review packages must be verified using their pinned
source/version, not silently reinterpreted by a changed verifier.
