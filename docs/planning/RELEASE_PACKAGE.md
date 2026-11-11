# Offline release review package

The package is a protected **review artifact**, not a deployable live-planning
release. Its only state is `BLOCKED_NOT_ACTIVATABLE`. No package command can
apply, resume admission, approve F1 authority, read a provider key, reserve money,
or contact a provider. Preparation and verification use local files only.

Run as the dedicated control user on Linux, with a canonical private output
parent (0700). Inputs are separately prepared, image-pinned deployment bundles
from the existing deployment tool. Both input semantic SHA256 pins must come
from independent inspection; never derive approval from an untrusted package.

```sh
PYTHONPATH=src python infra/vps/prepare_planning_release.py prepare \
  --previous /private/previous --candidate /private/candidate \
  --output /private/planning-review \
  --previous-pin EXACT_PREDECESSOR_BUNDLE_SHA256 \
  --candidate-pin EXACT_CANDIDATE_BUNDLE_SHA256

PYTHONPATH=src python infra/vps/prepare_planning_release.py verify \
  --directory /private/planning-review --seal INDEPENDENTLY_RECORDED_SEAL_SHA256
```

`previous.json`, `candidate.json`, `plan.json` are written 0600 under an
exclusively created 0700 directory. The completion seal is written last and pins
the exact bytes of these three files. Its semantic checksum is returned for
independent recording. This is an integrity pin, **not a digital signature or
owner authorization**. Verification does not rewrite files, initialize databases,
migrate ledgers, run Docker, or access SSH. It rejects extra/missing files,
symlinks, hardlinks, permissive custody, changed hashes and even a freshly
resealed plan inconsistent with the independently validated release policy.
An interrupted output must be retained for inspection or removed explicitly;
preparation never overwrites it or silently retries.

Both bundles pass the existing manifest and compose validators. The transition
requires distinct exact revisions and unchanged schema/database/Redis pins,
control/execution users, state location, owner login, Telegram owner and bot.
External first-experiment bundles are out of scope. Source image labels and
actual engine/host state are **not proven by offline validation**. No credential
file is copied; input bundles must themselves contain configuration and paths,
not inline secrets. Keep the package private and out of Git.

## Activation plan and gates

The generated plan records predecessor/candidate bundle pins, revisions, all five
immutable application image IDs, migration hash, preconditions, postconditions
and failure policy. These are required checks, not claims that the server has
passed them. The plan cannot be promoted by editing `activation_authorized`.

Actual activation remains blocked on these concrete prerequisites:

1. Review the implemented [planning deployment binding](DEPLOYMENT_BINDING.md),
   including its additional control-daemon socket capability. Only exact bound
   planning environment/mount/network scope is accepted; default stays disabled.
2. Verify the connected broker factory against independently measured rootless
   control and execution daemons and actual self-container/image metadata.
3. Supply fresh operator-reviewed model/tariff, account/funding and data-sharing
   evidence, bounded limits, private profile, host metadata and credential identity.
   Do not substitute test tariffs or invent a balance. Do not put credentials
   in the release package.
4. Build and inspect the exact source/images, verify the live deployment and
   activation predecessor, rootless/cgroup/systemd, custody and host metadata.
5. Obtain separate exact, expiring deployment authorization, then use existing
   prepare/inspect/approval/update/postcheck interlocks. Quiesce intake and F1;
   check unresolved financial/runtime state and the existing backup/schema gates.
   Never substitute `compose up` or replay the failed historical apply.
6. Verify journals, watchdog and worker, actual pinned host attestation and all
   deployment postchecks. Only after stability may owner resume and check
   `/plan_prepare`. A separate observed `/plan_authorize` and financial admission
   remain necessary for one paid call; deployment permission does not grant it.

On any unknown outcome halt admission, retain reserves and append-only journals,
inspect current state, and use only existing bounded reconciliation with all
preconditions. No automatic retry, journal substitution or blind rollback.

The release review package does not remove any of these gates. The deployment
binding and factory are implemented, but live acceptance, exact built images,
fresh operator evidence and separate deployment/access authorization are still
required before a real activation. Existing packages retain their original
pinned source/version; do not reinterpret them through a newer verifier.
