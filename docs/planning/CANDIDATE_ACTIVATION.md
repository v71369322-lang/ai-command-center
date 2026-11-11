# Planning candidate preparation and exact activation

The operator path now creates a consistent candidate from existing release
contracts. It does not manufacture operator evidence or grant authority.
Preparation/inspection never starts services, swaps the live Telegram connection,
changes deployment/activation journals, resumes tasks, reads provider key bytes
or contacts a provider. The activation command is separate and must not be run
without exact owner deployment **and control-access** authorization.

## Inputs and preparation

Use the dedicated unprivileged Linux control user. Required inputs:

- A verified predecessor bundle, its exact digest, VERIFIED deployment and
  activation receipts, and its existing private Telegram connection.
- An existing disabled target bundle from the normal deployment `prepare`, with
  exact clean source, immutable images built from that revision and compatible
  migrations/state/users/owner scope. Prepare it without Telegram/planning/F2
  integration binding; no live connection file needs changing to build it.
- A private unbound `PlanningProfile` JSON (`runtime: null`), its independently
  reviewed raw SHA256, fresh tariff/account/funding/data-sharing evidence and
  bounded financial limits. No fixture tariffs, model or balance are substituted.
- A separate 0700 key directory containing exactly one owned, regular,
  single-link 0600 `openai.key`, plus an independently supplied fingerprint of
  exact key bytes. The preparator only checks descriptor metadata. The guarded
  gateway still verifies bytes after task authority, before provider I/O.
- A new candidate output directory under an owned canonical 0700 parent,
  outside the source and shared state roots. Existing output is never replaced.

```sh
PYTHONPATH=src python infra/vps/prepare_planning_candidate.py prepare \
  --previous-directory /private/previous --previous-pin PREVIOUS_BUNDLE_SHA256 \
  --disabled-directory /private/disabled-target --disabled-pin DISABLED_BUNDLE_SHA256 \
  --operator-file /private/operator/profile.json --operator-pin OPERATOR_RAW_SHA256 \
  --key-directory /private/planning-key --credential-sha256 KEY_RAW_SHA256 \
  --output /private/planning-candidate
```

Both rootless daemons and all five exact image/source pins are checked with the
existing Engine/image checks. The previous receipts, connection and operator
input are rechecked before output creation. Preparation binds profile, host
declaration, private mount paths and target revision without a circular hash.
It stages the same Telegram owner/bot with only the source revision changed.
Live files and old journals remain untouched.

The result contains the bundle/Compose, bound private profile/host, staged
connection, expected broker policy metadata and original input bundle snapshots.
`preparation.json` is written last as a completion marker and records each file's
raw hash, candidate/previous/disabled pins and a blocked review plan. It is not an
activation journal. Preserve an interrupted output for inspection; do not retry
over it or synthesize its completion marker.

The expected Docker document is a **prediction**, not rootless acceptance.
It includes actual inspected immutable image configuration plus rendered mounts,
secrets, public environment, policy/tmpfs and network names. Compose null/default
command and default secret-target representations are normalized; arbitrary
entrypoint, interpreter, endpoint, secret-target and resource overrides are denied.
Actual startup and postcheck must independently match this metadata and pass the
existing host gate. Docker/version differences may block acceptance safely.

```sh
PYTHONPATH=src python infra/vps/prepare_planning_candidate.py inspect \
  --directory /private/planning-candidate \
  --candidate-pin CANDIDATE_BUNDLE_SHA256 --preparation-pin PREPARATION_DIGEST
```

Inspection is read-only. It validates private inventory/custody, hashes, existing
release/profile contracts, immutable transition and staged Telegram binding.
Known activation/previous-connection journals may be present only with the exact
candidate/preparation/access scope; their presence is reported separately.
Inspection does not confer deployment or spending authorization. Prepared-state
provenance stays immutable after an actual activation.

## Exact access decision and activation

Get the concrete extra capability without changing anything:

```sh
PYTHONPATH=src python infra/vps/activate_planning_candidate.py capability \
  --candidate-directory /private/planning-candidate --approved-candidate CANDIDATE_BUNDLE_SHA256
```

The digest binds the candidate/source, broker, control-user socket, new egress
and key directory. **The control socket is an administrative Docker API, even
when mounted read-only.** Owner must separately authorize this exact capability
and deployment, with a short expiry. Printing the digest is not authorization.

Only after those exact decisions may the trusted operator run:

```sh
PYTHONPATH=src python infra/vps/activate_planning_candidate.py apply \
  --previous-directory /private/previous --approved-previous PREVIOUS_BUNDLE_SHA256 \
  --candidate-directory /private/planning-candidate --approved-candidate CANDIDATE_BUNDLE_SHA256 \
  --approved-preparation PREPARATION_DIGEST --approved-capability CONTROL_CAPABILITY_DIGEST \
  --approved-until OWNER_APPROVED_UNIX_DEADLINE
```

The adapter reuses the existing Telegram transition and `Deployment.apply`:
exact predecessor under lock, source/images, normal stop and drain **before**
binding replacement, backup, INTENT, bounded postcheck and VERIFIED. It does not
replace these with a raw Compose deployment. Previous optional planning expiry
does not prevent a safe quiesced update; the new profile must still be fresh.
Legacy memory-only apply rejects planning targets, even if someone sets its old
`external_ai_profile_enabled` marker false.

Additional planning postchecks verify admission remains halted, recovery is not
active, no uncertain F1 reserve remains, all external action hashes are anchored,
all external actions are COMPLETE with zero reserve, no runtime runs remain and
the target worker heartbeat is fresh. Historical complete charges are allowed.
These are added to the existing bounded postcheck loop and rootless/image/mount/
Telegram checks. No provider client or credential reader is constructed.

## Unknown outcome and reconciliation

An existing activation receipt blocks apply replay. Do not retry a failed apply
or overwrite receipts. Inspect systemd/Docker/current binding and both journals.
If the exact target is already running and all pinned checks pass, the separately
authorized bounded reconciliation path uses `Deployment.reconcile_intent` when
needed, then rechecks under the deployment lock and closes only that exact
DEPLOYMENT_ATTEMPTED activation. It never starts/stops services, swaps bindings,
resumes tasks, frees unknown money or sends a provider request.

The reconciliation CLI uses the same exact arguments as apply, replacing its
action with `reconcile` and supplying a fresh owner-approved deadline. PREPARED /
BINDING_ACTIVE partial failures, a different target, stale evidence, stale worker,
runtime/financial unknowns or changed receipts are blockers for separate bounded
investigation, not reasons for journal substitution or blind rollback.

After VERIFIED, admission remains halted. Owner resume, fresh `/plan_prepare`,
observed `/plan_authorize`, current context/source/profile/lease/fence and the
one-call financial admission are separate. Deployment permission never grants a
paid call or resumes old cancelled tasks.
