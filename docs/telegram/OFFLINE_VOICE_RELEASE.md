# Exact first offline voice release

This extends the worker implementation in PR103 with a first-addition release
adapter. Existing deployments without `voice` render exactly the same services.
There is no generic service/plugin injection and no paid/provider capability.

## Reviewable capability

The optional `manifest.voice` contains one immutable speech image ID, a protected
profile directory/digest, and a read-only model directory/exact four-file SHA-256
manifest under the existing private data root's `voice/` subtree. Only an existing
live owner/bot Telegram binding is retained, with its new source revision. No
planning/first-experiment provider binding can coexist in this first-addition
transition. Owner login, migration, PostgreSQL/Redis pins and both rootless users
must remain unchanged. The separate voice capability digest is mandatory at apply.

The speech service receives only the existing application DB password and exact
Telegram connection/token, its own protected profile, and local model. No Redis,
owner/admin login, Docker socket, broker, publisher or paid-provider credential.
It shares the existing control/Telegram network boundary, has no host ports,
read-only root/mounts, ALL capabilities dropped, no-new-privileges, one CPU, 1GiB
memory, 64 pids and 32MiB private temporary filesystem. Restart remains `no` to
retain the existing serialized boot/stop interlock. Inference is not a poller task.

Actual runtime postcheck verifies image, user, entrypoint/command, mounts,
networks, limits, read-only root, security flags, restart policy, environment and
absence of proxy/extra integration credentials. A fresh audited heartbeat must
match the exact source, profile and model and report PAUSED while normal stop is
held during installation. Default process startup/model import is not accepted
as live acceptance. Voice processing remains off until the owner resumes normal
admission through the existing channel. Saving a transcript never grants task
execution or spending.

## Operator stages

`infra/vps/activate_voice_candidate.py` provides fixed `profile`, `prepare`,
`inspect`, `apply`, and `reconcile` actions. These are operator operations, not
commands to ask the owner to copy into Telegram.

1. Prepare exact clean source and all standard images on their existing rootless
   daemons; additionally build the `speech` target on the control daemon. Do not
   relabel old images. Retain a plain provider-disabled bundle of that source.
2. Stage the reviewed model as a new privately owned read-only artifact under
   `data_root/voice`, without modifying prior artifacts. `profile` creates a new
   protected profile with the exact staged source/connection, local model and
   explicit offset-aware `since` cutoff. It never overwrites an existing file.
3. `prepare` checks the VERIFIED predecessor/current live connection, exact
   bundles, custody/source/images/model/profile and creates only a new private
   STAGED_NOT_ACTIVATED package. `inspect` reconstructs it, verifies all pins,
   inventory/custody and image/model/profile again. Live connection and deployment
   journals remain unchanged throughout preparation.
4. Obtain a concrete approval for exact previous/candidate/preparation/capability
   digests and a fresh bounded deadline. `apply` composes the existing global
   deployment lock, normal stop/drain, backup, connection activation, deployment
   INTENT/apply/postcheck/VERIFIED transaction. It does not use raw compose up.
5. If uncertain, inspect journals/runtime before doing anything. Only existing
   exact-target reconcile composition can close an attempted activation. Never
   replay apply or replace journals by hand. Backup/restore inspection remains
   available when optional voice is revoked. Future updates/boots stop an active
   voice service before replacing bindings or halting admission.
6. After observed owner resume, verify one genuine Telegram voice note, delivered
   readback, owner confirmation and saved request. Do not describe synthetic/mock
   tests, standalone recognition or a PAUSED worker as this live acceptance.

## Performance guard

An idle worker uses a bounded SQL `NOT EXISTS` selection rather than querying each
historical voice. It does not rescan the full audit chain every second when there
is no work. Full verification remains mandatory before every download and durable
write, including periodic health evidence. Stop/connection/profile/leadership
checks remain active on idle polling too; this optimization grants no authority.
