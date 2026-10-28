# F32: prepare-only disabled Telegram release

Application: PR #26, 316dc1615dea224bcf4bd595d87048d19820bd21.
Successful application CI: https://github.com/v71369322-lang/ai-command-center/actions/runs/40639614754
(479 Python tests, separately 32 infrastructure tests and cloud container drills).
Includes PR #24 deployment/migration, #25 task status and #26 request receipts;
these dependent PRs remain open and unmerged.
Operational base: F31 trigger 4ecbfa666324d630244df291cca3b976db13d1fe.

This separate channel delivers only the reviewed source and builds/prepares a
new disabled Telegram bundle under /home/acc-control/f32. Active state remains
/home/acc-control/f30/state; current release must still be 4cc6ec4 and bundle
1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106.
Existing F30/F31 source, helpers, units, state and bundles are preserved.

Registration reuses the existing ephemeral acc-bootstrap-only runner without
new permissions, dependency download, sudo or daemon socket grant. Only a
reviewed push to ops/f32-telegram-prepare with [run-f32] starts the job.
Ordinary preparation commits run only the new `verify` job on a GitHub-hosted
Ubuntu 24.04 runner. The VPS `prepare` job needs successful source verification
AND the explicit marker; it is skipped on this readiness-only commit.
Owner separately snapshots/verifies the root bootstrap SHA-256 in trusted SSH.
A root-owned fixed service runs as acc-control. It checks existing rootless
daemons and free space, rehydrates the exact source from validated Git objects,
compares requirements.lock to the active F31 source and reuses F30 tools.
No programming credentials or bot token are needed by this prepare job.

Default prepare has no Telegram flag. It cannot run deployment update,
telegram_transition stage/apply/reconcile, init-state, live API, admission
resume or database DDL. Its only output is an inspect receipt with a new local
bundle digest. Current application keeps running during preparation.
The inspected digest is not permission for schema migration or live calls.

Future separate operator stage/apply uses the exact new digest and exact
previous bundle through command_center.telegram_transition. Read the approved
application docs/telegram/DEPLOYMENT_PROFILE.md: stage deliberately stops apps;
plan approval expires after 15 minutes; response loss never replays DDL.
Live credentials/binding and activation remain a later exact-bundle action.
The working password is reused; it is not supplied to the runner.

The runner can read source/inspect receipt only; the fixed operator service has
control/execution daemon access needed for build as in F31. This is trusted
operator authority, never coding-agent permission. An attempted build or
existing destination requires explicit reconciliation, not silent overwrite.

Offline tests: set F32_SOURCE_REPOSITORY to a local checkout containing the
exact approved application Git objects, then run pytest infra/vps/tests/test_f32.py.
They verify packet hydration, tamper rejection, bootstrap hashes, source/state
pins and absence of install/update operations. They are not host execution proof.
`verify_release.py --source CHECKOUT` additionally checks complete Git ancestry,
unchanged locked dependencies against F31, exact old/new migration fingerprints,
required application files and the deterministic packet digest. It needs local
history; it is not run on the intentionally shallow VPS handoff checkout.

Consolidated packet: 2,720,819 bytes, SHA-256
`a694506a5d767c0cbab308bc43a820ecaa7dad832352841cedfee0a11f92be28`.
Root bootstrap `infra/vps/f32/enable_prepare_channel.sh` SHA-256:
`f2da4ce4738b5c05a087e90c820fdf4e7b286b2ba89ed983952bb57137bab909`.
Previous a994de9/9d2544... bootstrap instructions are obsolete for this new packet.
No image IDs or target bundle digest are invented: they are produced on the VPS
only after a separately authorized rootless build/inspect.

Operator sequence and gates: [F32_OPERATOR_HANDOFF.md](F32_OPERATOR_HANDOFF.md).
No server has been changed by preparing this branch. No merge or live bot call.
