# Telegram memory recovery checkpoint — 2026-10-31

> Superseded for deployment on 2026-11-01: read-only reconciliation found that
> Telegram remained healthy at 256 MiB, while the independent watchdog was again
> OOM-killed at 128 MiB. Candidate `1d7ab452…04d21` therefore must not be applied.
> A replacement release must bound **both** Telegram and watchdog at 256 MiB and
> pass the same exact reconciliation, rootless image and postcheck interlocks.

This checkpoint records the owner-observed VPS state and the reviewed recovery
path. It is not deployment authorization and does not extend an expired approval.

## Fixed evidence

- Operator source: `5524da505227b581ba6898b73eccadb11bc2f8d7`.
- Application candidate source: `912cad8f9c85485c1bdd5e7a5804efc5d01c43b0`.
- Reconciled predecessor bundle:
  `ac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d`.
- Prepared candidate bundle:
  `1d7ab4526278d9a821daddd43c64205249cfb4ab4233e0d059433192bf604d21`.
- Candidate Telegram connection digest:
  `e59eb8ac9edc1bc4c2201e55c64853889c294466ebcac238235254634f642fe5`.
- Candidate directory: `/home/acc-control/telegram-memory-fix-candidate`.
- Predecessor directory:
  `/home/acc-control/first-experiment-github-capability-release/integration-preparation/candidate`.
- Candidate has a 256 MiB Telegram limit, no `first_experiment` binding and no
  task-admission resume.
- The current old release is operational only because of a temporary 256 MiB
  runtime containment. Its deployment journal remains `INTENT`.

The candidate was prepared without deployment or paid calls. The application
images for `912cad8f` were owner-observed on both rootless daemons. Draft PR #68
CI is successful at the later operator revision; it does not itself deploy the
candidate or authorize the two operations below.

## Recovery sequence

The owner performs this as two separately bounded actions. A result from one
action is inspected before authorization of the next action.

### 1. Reconcile the exact predecessor intent

Use `infra/vps/reconcile_deployment_intent.py` from an exact private checkout of
the operator source. Supply a new expiry no more than one hour ahead and the
exact predecessor digest. The command:

- validates release-file custody and the exact digest;
- performs existing source, image, secret, rootless and Telegram preflight;
- performs the current release postcheck under the deployment lock;
- changes only the exact journal from `INTENT` to `VERIFIED`;
- does not start, stop or replace services, change Telegram binding, resume task
  admission or make a paid call.

Expected status: `EXACT_DEPLOYMENT_INTENT_RECONCILED`. Any other status blocks
the deployment. Do not retry after an unknown result before read-only inspection.

### 2. Apply the exact Telegram memory candidate

Only after stage 1 is verified, use
`infra/vps/apply_reconciled_telegram_candidate.py` with a new bounded approval,
both exact bundle digests and the fixed directories above. The operator:

- rechecks the verified predecessor and the live Telegram connection;
- validates unchanged DB/Redis/migration/owner/UID boundaries;
- rejects an AI integration, Telegram identity change or a limit other than
  256 MiB;
- stops only the exact predecessor poller before switching the binding;
- delegates quiesce, encrypted backup, stopped-service replacement and postcheck
  to the existing deployment interlocks;
- preserves `activation.json` at the last known phase after any uncertain result;
- leaves task admission halted and performs no paid provider call.

Expected status: `TELEGRAM_MEMORY_FIX_APPLIED`. Final evidence must show the
candidate bundle in `deployment.json` with phase `VERIFIED`, activation phase
`VERIFIED`, all required containers running on the candidate image set, Telegram
memory limit 256 MiB, `live_connected=true`, and task admission still halted.

## Stop conditions

Stop for inspection without overwriting receipts if any of these occur:

- `BLOCKED_REQUIRES_INSPECTION`;
- a changed bundle, source revision, directory, connection digest or migration;
- an existing activation receipt;
- failure to confirm the predecessor Telegram container stopped;
- an `INTENT` deployment after the apply command;
- failed broker, watchdog or Telegram postcheck;
- any unexpected provider call, paid-call count or task-admission change.

Do not use a direct `docker compose up`, delete the candidate/activation receipt,
resume tasks, or restore the database as part of this recovery.
