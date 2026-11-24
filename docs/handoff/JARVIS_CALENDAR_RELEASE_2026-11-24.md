# Optional Calendar release binding

Scope: owner's «Доделывай» after the successful Google publication/HTTP probe.
Local implementation/tests/commit/Draft PR only. No new Google publication,
paid calls, merge, VPS access or installation is inferred from this instruction.
Base is ccfbca3, including PR112 code8a676a7; its CI45398934953 completed SUCCESS.
Keep the dependent PR chain; this release targets feat/jarvis-calendar-script-bridge.

## Changes

An optional `calendar_script` release manifest field contains `directory`, `profile`
and `config_sha256`. Profile is the existing strict ScriptCalendarProfile; the
config digest covers ScriptRuntimeConfig(profile=profile,key_file=/run/calendar/calendar.key),
not just the profile. Enabled, exact revision and actual Telegram owner must match.
Only assistant-only releases with Telegram can enable the binding. No new service.

The directory must be below data_root/calendar. Before prepare/inspect/install,
private owner-only parents, config bytes/shape and raw32byte key fingerprint are
rechecked. Config and key are mounted as exact read-only files only into Telegram.
A private0700 bounded16KiB tmpfs provides their container parent; other directory
contents are not exposed. API, voice, DB and all developer components receive no key.
The existing Telegram egress network is reused; no new published port/network.

The existing assistant candidate transition now accepts an already assistant-only
verified predecessor. Migration/database/storage/UID/login invariants remain fixed;
Telegram owner/bot and offline voice model/cutoff are retained. New source and
immutable images remain mandatory. `prepare --calendar-binding-file` adds the
optional exact binding to the candidate and its hashed preparation inventory.
Inspect reconstructs the target and rechecks custody; existing activation journals,
exact approvals, stop/backup and reconcile tools remain the sole install path.

Postcheck verifies private host files and runtime mounts/command; it also constructs
and closes the actual Calendar client inside Telegram without HTTP. This verifies
the mounted config/key/owner/source/digest without reading or changing events.
Real Telegram agenda acceptance remains a separate required live check.

## Activation plan (not authorization)

1. Finish focused Linux tests and final HEAD/PR merge-ref CI. Preserve source pins.
2. Obtain permission for fresh read-only reconciliation of176.12.75.135; inspect
   actual installed source, VERIFIED journals, control state, containers, voice,
   backup readiness and resources. Historical9351ba6 is not a substitute.
3. Build source-pinned API/voice images and a plain assistant-only bundle using
   the existing release tools. Retain the actual predecessor migration hash,
   database/redis pins, identities, model and state. Do not use ordinary compose up.
4. Under a separate concrete provisioning permission, transfer the approved key
   directly from protected custody to a new private host directory. Never put it
   in shell arguments, Git, logs, clipboard dumps or model context. Create the
   exact ScriptRuntimeConfig using the verified owner and candidate source SHA;
   pin the already approved Google deployment v1 and connection/fingerprint.
5. Prepare voice profile, then assistant candidate with --calendar-binding-file;
   inspect and record exact previous/candidate/preparation digests, backup and
   compatibility evidence. Preparation must not activate/resume admission.
6. Request exact install approval with these digests and a finite time window.
   Apply through activate_assistant_candidate.py; on timeout reconcile actual
   state before any retry. Never hand-edit INTENT/DEPLOYMENT_ATTEMPTED journals.
7. Verify both journals, five services only, no developer daemon/access, offline
   voice heartbeat, Calendar private runtime binding and unchanged financial ledger.
8. Through real owner Telegram, test «что у меня завтра?» and /agenda, duplicate
   update delivery, stop rejection and provider failure (must not claim empty agenda).
   Check restart through the existing boot interlock. No paid AI, calendar writes
   or automatic resume are included. Record actual timings and limitations.

No new candidate digests or VPS acceptance are claimed before these checks.
Google Apps Script availability/quotas and upstream outages remain external risks.
Do not promise uninterrupted service based on one successful read.

## Recovery

Keep the verified predecessor bundle, encrypted backup and original Telegram binding.
Activation interlocks halt admission and preserve journal evidence. If a partial
apply occurs, use stock inspect/reconcile with the exact preconditions; do not
repeat apply blindly. Optional Calendar revocation must not block independent
backup/stop paths. Roll back only after current data compatibility is verified.
Google bridge publication is independent and has not been modified by this release.

## Verification

Linux regression209 checks passed (deployment, assistant and voice release suites,
including the earlier calendar test collection); final Calendar suite18 checks passed
separately after additional runtime/update cases. These overlapping runs are not added.
Ruff and Bandit medium/high passed. New final HEAD/merge-ref CI remains pending.
Existing protocol32 and
Google live HTTP acceptance belong to the predecessor; they do not prove this
new deployment binding. Tests use synthetic credentials/fake daemons, not VPS proof.
