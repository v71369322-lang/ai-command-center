# Calendar create activation review — not an approval

Owner selected the existing main Google calendar on26November. This choice is not a write-scope or deployment approval.

Phase2/6. Prepared application PR118/source
b104b78a21377df062f55244d1a7bc76fadae62a. Current installed source remains
1e5dd99; read-only Calendar and its existing Google project remain unchanged.

## Package

- Source bundle SHA256: 34f1d5f09bb3651fc7ad0fdf5e00fad5e9e6dc97057e6052ecfc3b827a09af37.
- Bridge.gs SHA256: bd19bf2498b2c38ea4cec330b2afde40d7427a01d1cc3311012db9ed8bdac4bc.
- appsscript.json SHA256: 7b923d8276fb4ccb7edd165a32f7a45a0f4a97c6f39e1a3e3dee1f15a4cca95a.
- Google package SHA256: 9da4c06efce5d8ed714f5b15021fd37bdec823a34a6bd98a96e0268f04c0d357.
- CI45688706551 for merge-ref 0d89dca063018a51eda871c22f613652a50a8d12:
  SUCCESS; main2799 passed/1 skipped/1 dependency warning; infrastructure1014 passed; speech44 passed. Overlapping suites are not summed. Head and merge-ref share treedb5dcdba544c82929e8c76372070d6251bba08b6.

## Proposed owner authorization — not yet granted

Within two hours after explicit confirmation: publish this separate Google
create/get script package, provision its separate protected HMAC connection,
request Google calendar.events.owned consent, bind it to the owner's explicitly
identified main calendar (actual calendar ID, not primary alias), and install
only the exact application source above through stock prepare/inspect/exact
approval/install/postcheck. Google OAuth includes read/write access to events
on owned calendars; the reviewed bridge itself admits only create/get on the
one pinned calendar. It cannot update/delete events or send invitations.

The real Google consent/passkey remains a user step when required. Do not bypass
Google warnings or substitute consent. Default Apps Script project API enabling
is documented, not yet verified for this new project. No billing/trial/paid AI.

For live acceptance, proposed single event: title «Тест Jarvis — проверка
календаря», 2026-11-27 15:00–15:10 Europe/Moscow, no attendees, visible20minute
reminder. Create only through an observed owner Telegram confirmation of those
exact details. If this time has passed before approval/activation, obtain a fresh
specific test time. Do not delete or alter real existing events. Removing this
test later is also not implied permission to delete other events.

## Exact retention proposal — deletion NOT authorized/performed

Only these four files under /home/acc-control/f30/state/backups are proposed
for removal from the server. All four remain in owner-only PC custody under
C:/Users/Zver/.codex/private-backups/jarvis-2/20261124. Remote and PC SHA256/size
matched; each PC archive independently decrypted in memory and its database
dump checksum verified. No plaintext written.

| Filename | Bytes | SHA256 |
|---|---:|---|
| backup_007fd621eea24049a8b3f9c14b555835.enc | 4209669 | 36a4212ade7534576f9cb0313f10971d1bf7d1b6ec491308972c515b6ea9ebaf |
| backup_10253e4c3c854806bc557c239b8150e0.enc | 4388392 | 885971f68c5681fc8644b48390dfd712fde1af5c99d4b6d6082fe96ec89e69a9 |
| backup_27871049d8814de1b7656d6fb7cad520.enc | 4469937 | cfc764b4b6356ab5f384a16ea194136d5a9d4297efb5bd0a5130bcdfddea6767 |
| backup_5592a2aadd1341de84337336e2255252.enc | 4400887 | b50e1f73cfb1ee2254c488bfe8b5b82e1321aeb4c8b7b310303c74ffa60f40c1 |

Total17468885bytes. Current quota268435456, used267657777; removal would leave
250188892 used and18246564 free. No quota expansion, recursive cleanup, image
prune or deletion of any other backup. Fresh sizes must be checked before each
new backup; capacity estimate is not a bypass of the existing quota.

Retain on both VPS and PC: pre-current backup42d2ef9df640436d9e7a892a6fd8a630,
current post-update backup96e9f805aa174337be064c3a13ce304b, all other server backups
and protected recovery deltas. Both retained PC archives were independently
decrypted/checksummed again. No latest pointer rewrite.

Before each approved deletion: resolve the exact regular non-symlink path,
recheck remote+PC hashes and the current latest pointer, record an operation
receipt, refuse changed/missing files or an expired approval, then unlink only
that named file. Keep the encrypted PC original. If an archived historical
point is later needed, restore that verified copy via the existing recovery
procedure with current quota/custody/compatibility checks and an isolated restore
drill; do not restore over production or bypass the quota blindly.

## Application migration and limits

No schema migration in this release. Preserve old models, image IDs, profiles,
Google read bridge and encrypted recovery material. Take and independently
verify a fresh pre-update backup and full disposable restore check after any
approved retention cleanup; stock apply also takes its own backup. Checkpoint
and copy the post-update backup/recovery delta to PC. Do not infer safe downgrade
only from an unchanged schema; new dialogue/audit and sync state must be assessed
before rolling back. Keep admission stopped during recovery if compatibility
is unproven. Other projects and developer services remain untouched/stopped.

Not approved by this document: deployment, Google publication/new scopes,
retention deletion, merge, paid AI, arbitrary shell execution by Jarvis, real
business operations or modification of existing calendar events.
