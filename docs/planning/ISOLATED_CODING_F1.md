# Offline coding specifications bound to F1

This dependent continuation of Telegram content acceptance and coding preparation
adds a real F1 `isolated_coding` Task and a broker-dispatched sandbox adapter.
It supports **owner-supplied replacements of existing Python source in an exact
Git slice**, not autonomous AI code generation, repository cloning or publication.
No new permission system, daemon, socket, credentials or production setting is added.

## Prepare, review and approve

1. Accept current plan content and prepare the explicit coding scope using the
   previous workflow. The immutable preparation remains `PREPARED_NOT_RUNNABLE`;
   executable state is represented by the separate F1 Task, never by editing it.
2. Supply the exact declared Git commit and only the trees/blobs needed to prove
   every scoped source/test file, plus explicit path-to-new-source replacements.
   `scripts/prepare_isolated_coding.py --repository LOCAL_PATH --preparation
   PRIVATE_PREPARATION_JSON --replacements PRIVATE_REPLACEMENTS_JSON --output
   NEW_PRIVATE_OUTPUT_JSON` materializes this input without network access. Run
   with the project's locked environment and `PYTHONPATH=src`; protect input/output
   files and keep them outside Git. It reads the Git object database, never the
   working tree, credentials, hooks or untracked files; it does not create a Task.
3. Owner-only `POST /api/project-inbox/coding/task-preview` accepts request ID,
   expected specification digest, snapshot and replacements. Inspect the returned
   complete payload/digest. Then `POST /api/project-inbox/coding/task` with the same
   input and `expected_payload_digest` creates an idempotent real F1 Task in
   `WAITING_APPROVAL`. Existing owner session/CSRF and **8192-byte API input limit**
   remain. Larger local materializations fail the API limit; there is no upload
   bypass. Internal payload/transport bounds remain 48000/65536 bytes.
4. Inspect/approve/cancel the resulting Task through existing F1 routes. Content
   acceptance, preparation and task creation are never execution approval. No
   Outbox, Approval or ExternalGrant is created with the waiting Task. Ordinary
   owner F1 approval creates the existing expiring Approval and Outbox; claim
   consumes it with current epoch, payload/version/source and lease/fence checks.
   This adapter makes no AI call and reserves zero financial cost.

The owner selects all context files explicitly (at most eight source files and
eight test files from the original scope). Include package `__init__.py` and
required modules when needed. Missing dependencies/imports fail checks; the adapter
does not fetch/install packages, expand scope or substitute a full-repository test.
Only existing regular non-executable Python blobs are accepted; symlinks, submodules,
executable modes, missing/extra/duplicate objects and altered Git proofs fail closed.
No new/deleted file or test replacement is supported in this bounded first adapter.
Non-empty source must end with a newline so the returned unified patch is usable.
The unchanged baseline test files are the reviewer's selected tests, not an assertion
that their coverage proves the whole plan. Git hashes prove exact content under
the owner-declared commit; **remote repository membership/access is not verified**.
No project connection record or remote capability is fabricated or needed for
owner-supplied offline bytes. A future fetch/publisher still needs its own evidence
and permissions.

## Runtime and verification

The existing RuntimeBroker checks rootless-required mode and resource caps before
claim. Its existing backend verifies the actual rootless/systemd-cgroup-v2 daemon.
This adapter rejects cloud-rootful-test production dispatch. It inherits CodingRunner
image/source checks and immutable inspected image ID, no mounts/network, read-only
root, UID/GID 65532, all caps dropped, no-new-privileges and bounded ephemeral tmpfs.
Existing runtime caps may be stricter than the specification's 256 MiB/0.5 CPU/64
pids ceilings. Shared wall deadline, watchdog and F1 pulses fence both stages.

The first container reconstructs only proved files, applies the explicit replacement
once and runs fixed Ruff/pytest argv. No arbitrary shell/environment/provider command
is accepted. Sandbox check tool versions/hashes come from `uv.lock` through
`requirements.coding.lock`; they are installed only in the coding image. Pytest
plugin autoload, repository config and cache are disabled. Check process groups
are killed after each check; logs are bounded by existing sandbox file/disk/output
limits and are not returned as artifacts. Tests modifying the workspace or adding
files fail. No repair iteration is invented for this owner-supplied patch path.

The trusted runner recomputes expected file hashes and bounded patch independently,
requires every exact check to pass, confirms the first container removed, then
uses existing `next_stage` to run a fresh verifier container from the original
input. The verifier receives no agent report/workspace. Both reports must exactly
match (including JSON types). Stop uncertainty or differing checks blocks success.
F1 finish again checks current specification/acceptance, audit, source, approval,
lease/fence/epoch and cancellation before storing the patch/report artifact. A
changed plan/setup/latest preparation cannot silently retarget an approved job.
Unknown outcomes remain bounded by existing reconciliation/watchdog mechanisms,
never automatic execution replay. Artifacts are not commits, PRs or deployments.

## Evidence boundaries

PostgreSQL tests cover owner/review/idempotency/concurrency, context changes at
create/approve/claim/pulse/finish, cancellation and payload tampering; byte-level
Git proofs, offline materialization, actual local patch/check replay, and mocked
runner/ledger success/failure/stop/forged-report composition. A separate full-CI
container smoke checks the real entrypoint/image and networkless mountless sandbox
on the cloud test daemon. It deliberately does not claim rootless or VPS acceptance.
No real project code is executed on production by this change. Telegram preparation
remains available, but binary Git input/task review uses the owner API/operator
workflow; no execution confirmation button is added to Telegram in this stage.
The dependent [Telegram review continuation](TELEGRAM_CODING_APPROVAL.md) adds
observed owner confirmation and a separately scoped status command for these tasks.
