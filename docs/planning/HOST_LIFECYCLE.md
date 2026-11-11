# Planning host lifecycle on the existing broker

The internal RuntimeBroker can now receive an explicitly supplied PlanningHost.
Without it the existing planning_runtime_not_connected gate remains unchanged,
before claim or runtime access. create_broker_app does not load or install a
planning host automatically. The RPC schema has no host, key, endpoint or
Docker-policy override.

## Rootless attestation

A private raw-byte-pinned HostDeclaration binds source revision, fixed broker
name, exact image ID, permitted local Unix endpoint, runtime ledger path and a
policy metadata digest. Its semantic digest must already be in the operator
planning profile before the owner review. Container name/image/policy can be
prepared before deployment; the actual container ID is measured and recorded
at attestation, avoiding a declaration/restart/container-ID bootstrap loop.

Admission requires rootless-required and the existing RuntimeBackend rootless,
cgroup-v2/systemd preflight. cloud-rootful-test is rejected. The actual running
broker must match this process's hostname/user, pinned image/source label,
immutable application path, exact UDS broker command, image interpreter/PATH
environment and bounded read-only/no-new-privileges/cap-drop policy. Source/system
code mounts, injected interpreter hooks, host namespaces/network, public port
bindings, devices and explicit unconfined security options are rejected even
if an operator metadata pin matches them. No AppArmor/TLS/rootless guard is
disabled to pass this gate.

Only selected public environment fields enter metadata; credential values are
excluded. Mount paths/policy and actual image identity are checked without
printing complete Docker inspection documents. Subsequent guards recheck the
private declaration/profile binding, runtime ledger, operation phase/deadline,
watchdog and worker freshness. Docker attestation is repeated before execution;
it is not performed during every database transaction or network chunk.

## HTTP operation, not executor absence

After existing F1 claim, the same RuntimeLedger registers kind=planning_http.
The trusted broker performs HTTP itself; no executor container receives the key,
no model code is executed and no second task or authority queue is introduced.
The dedicated runner serializes ACTIVE admission with the existing launch lock,
maintains F1 pulse/operation heartbeat, and passes the attested guard to the
existing LivePlanningGateway. The same one-call financial INTENT/reservation,
lease/fence/source/card/context checks still apply.

The runtime deadline/guard is checked during response reads as well as before
I/O and result acceptance. The transport retains its bounded read timeout and
response-size cap. Revocation is cooperative for an in-flight read; this is not
an OS-level proof that a blocked broker process was killed. A late/partial reply
can remain financially UNCERTAIN instead of being parsed for settlement.

The durable planning_operation_returned marker is written only after the HTTP
client is closed and the F1 pulse thread has exited. Kind and returned fields
are checked against the ledger hash-chain events. Normal success can close
runtime DONE. Uncertain external outcomes remain RECONCILING/UNCERTAIN with
their reservations and no automatic retry, even after the local client returns.

Watchdog explicitly handles planning_http. It revokes authority and halts
admission; Docker rm/inspect absence is never HTTP stop evidence. It can confirm
local termination only from the returned marker, preserving financial unknowns.
An operator reconcile also requires that marker and keeps admission halted.
A broker crash with no return marker remains blocked for separate host/process
investigation; restarting does not synthesize evidence or resend the request.

## Compatibility and validation

RuntimeLedger adds kind/container default and returned=0 in its normal writable
constructor. Existing container operations retain their path. Read-only legacy
inspection uses a container/zero projection when both columns are absent; it
never calls the constructor or migrates a file. Incomplete schemas or conflicting
operation events fail closed. An older watchdog must not be rolled onto active
planning_http records: release/rollback coordination must quiesce and verify
the host lifecycle first.

Local validation uses PostgreSQL, the real SQLite ledger, synthetic rootless
Docker metadata and public mock HTTP/key files. This proves control flow and
evidence checks, not actual rootless/AppArmor/VPS acceptance. Coverage includes
pre-claim denials, unsafe pins, heartbeat, wall deadline, crash/restart, unknown
money, operator reconcile, operation-kind tampering and legacy read-only access.
Exact final counts and CI are recorded with the resulting dependent Draft PR.
Final local PG/control scope: 383 passed, one existing Starlette warning;
separate read-only infrastructure scope: 23 passed. API contract/Ruff/diff checks
passed. A clean committed Linux source rerun addresses the minimal helper's
missing Docker CLI/Compose prerequisite; its result is recorded by the PR.

No VPS/daemon/credential change, production planning host, paid call, deployment
or merge was performed. Next is protected release-package prepare/inspect wiring
and independently observed rootless host acceptance under a separate exact owner
deployment decision. Key presence or an enabled flag alone cannot activate a
staged grant.
