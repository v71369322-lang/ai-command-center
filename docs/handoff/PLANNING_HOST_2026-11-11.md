# Planning host checkpoint — 11 November 2026

- Repository v71369322-lang/ai-command-center. Canonical main fetched/checked:
  f5ff8b2757b1b759b08a173fdac9d3e51f84d227.
- Base: Draft #90, feat/trusted-live-planning-gateway,
  c0ca76911fb48fa3032f573db4ef80f4ef859e6f. Exact HEAD CI 42968328070 SUCCESS;
  prior verified merge-ref d849fcafc1ea133336b909f64f8f076650d23185.
- Current branch feat/planning-host-lifecycle; resulting Draft must target #90's
  branch until it is merged. No automatic retarget or merge.
- Scope: [host lifecycle](../planning/HOST_LIFECYCLE.md), explicit protected
  rootless broker attestation, planning_http ledger kind/returned proof,
  F1 heartbeat, cooperative bounded reads, watchdog and existing broker route.
  Default production factory remains closed. No executor/worker key handoff.
- Writable SQLite migration is confined to the normal constructor. Read-only
  historical inspection verifies old schemas without creating/migrating files.
  Never use container absence as HTTP-stop evidence or downgrade an active
  planning_http run to an old watchdog.
- Tests use dedicated local PG and public mock keys/HTTP/rootless metadata.
  Initial host scope 23 passed; expanded pre-final scope 379 passed. Runs overlap
  and are not added. Final local PG/control scope: 383 passed / one existing
  Starlette warning. A separate read-only infrastructure scope: 23 passed.
  API contract, Ruff and git diff --check passed. Final clean-source broader
  infrastructure results and exact source CI are reported by the resulting PR.
- A broad infrastructure run in the minimal Python helper failed with
  110 failed / 382 passed / 1 skipped / 520 setup errors; Docker CLI/Compose was
  absent (fixtures perform local compose rendering). This is not PASS. A pinned
  Docker CLI/Compose tool is prepared for a clean Linux snapshot rerun; final
  results remain independent of the PG/mock scope and rootless host acceptance.
- Final clean Linux infrastructure rerun at c9760ffa8d49ddb21f21420444e575edfeefca35:
  1013 passed. Pinned Docker CLI/Compose and a dedicated unprivileged UID 1000
  were required; the root helper correctly hit dedicated_unprivileged_operator
  guards. No guard was relaxed. The cloned snapshot was disposable inside the
  test container, with LF checkout and no Docker daemon socket mounted.
- Read-only VPS probe followed the local tests. Rootless Docker, cgroup v2 and
  systemd driver are confirmed on the existing release. Broker running/OOM=false,
  UID 0 inside rootless container, read-only rootfs, ALL caps dropped, nnp,
  256 MiB / 0.5 CPU / 64 PIDs, private IPC/no host namespace, no published ports,
  exact UDS command, /app working directory, no source mounts. Code environment
  matches the immutable image. Watchdog ready, worker fresh, zero unresolved
  runtime runs. SQLite was opened query-only/read-only after checking non-WAL
  journal format; no constructor/migration was used.
- Actual server revision/image label remains
  f5ff8b2757b1b759b08a173fdac9d3e51f84d227, image
  sha256:98fd46a92199b30b88235a7d5a166b1fb369dcfbae4a47e2d884607ddcf85d82.
  Deployment VERIFIED, bundle
  e7330efad3d1333205a0816c7153ed7fdd1c9b4fc55c888535bf6aea6f8a9918.
  This is a fresh prerequisite probe of the old source, not acceptance of new
  lifecycle code or an installed host declaration. SSH session closed afterward.
- No VPS runtime/configuration change; no real key connected, production task approved,
  paid request, daemon/security setting change, deployment or merge. Rootless
  declarations in tests are synthetic evidence only. Existing owner live task
  remains outside these local fixtures.
- Next safe work: protected release-package profile/key/host prepare/inspect and
  default-closed factory wiring, offline tests and exact source/image review.
  Actual rootless/AppArmor/systemd/VPS acceptance and deployment need their own
  concrete owner decision. Any unknown provider result stays non-retriable and
  its financial reservation is retained.
- Final commit/PR and exact HEAD/merge-ref CI accompany the new Draft PR. Keep
  the earlier VPS reconciliation and phone acceptance checkpoints as dated
  evidence, not current host probes.
