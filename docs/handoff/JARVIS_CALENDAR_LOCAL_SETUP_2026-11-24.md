# Calendar private files and loopback callback, 24 November 2026

Dependency: PR109 /94fed29986f38d66dea86de87523370b7ce891d4, not main.
See [preceding OAuth checkpoint](JARVIS_CALENDAR_OAUTH_2026-11-24.md).

## Implemented and verified locally

`google_calendar_setup.py` supplies:

* Linux private credential files: explicit existing directory0700 and dedicated
  calendar.key0600/32bytes, exact owner, regular file, single hard link, no symlinks
  (including resolved directory aliases). Directory fd stays open and exclusively
  flocked for the custody lifetime, fencing a second cooperating owner process.
* Bounded encrypted archive reads and atomic0600 write/fsync/replace/directory-fsync.
  Pre-existing unsafe targets are refused. Failed replacement preserves the prior
  archive and removes the temporary file. No automatic key generation or chmod.
* Ephemeral localhost127.0.0.1 callback on a dynamically allocated port, exact
  path/Host, bounded query, correct state, no request/error logs. An absolute
  one-second request deadline prevents incomplete/trickling requests from blocking
  the five-minute authorization attempt. Receipt page does not claim authorization
  succeeded or echo code/state. Listener closes on completion, failure or timeout.
* Exact profile/source/client binding, credential completion into encrypted custody,
  and an approved client factory using the existing token provider. OAuth/storage
  lifetimes remain explicit. This does not authorize calendar publication.

85 focused tests passed in an unprivileged Linux container, including the earlier
OAuth and Calendar contracts. The16 new setup tests cover real localhost HTTP,
timeout/closure, Linux custody/link/permission/lock checks and atomic replace failure.
This is not a VPS acceptance test. Google HTTP remains mocked; no OAuth grants,
Google events, calendars, tokens, VPS files or paid calls changed.
Ruff and Bandit medium/high passed for the new module.

## CI reconciliation

PR108 exactef5dc1a: run45364141232 completed SUCCESS. PR merge
383c8f613c4a7eed99eda952d7df72b6984dc7e1 has the same tree
5e6263d07124d94068c81bed2a9743cc0f6f6999 as the source head.
PR109 exact94fed29: run45365268198 still in progress at last check; speech and
static checks passed. Merge2d7878f8c3920601b54a4bb7e41d1cbe9c95f2fd and source
have equal tree11929f04aee7bebfd88b4e015847edef758d1ce4.
Do not treat pending synthetic CI as a final pass.

## Remaining before a usable Google connection

The callback is portable Python and tested on Windows as well as Linux; file custody
is deliberately POSIX-only. An operator entry point and a protected enrollment path
from the Windows owner browser to Linux runtime are still needed. Do not expose the
loopback endpoint publicly, add an SSH/public port, or copy plaintext tokens to chat
to bridge hosts. A loopback callback runs on the same machine as its browser.

No dedicated OAuth client/consent or Jarvis calendar has been provisioned. The
complete_connection receipt explicitly reports calendar_id_verified=false. Verify
or create the dedicated calendar with the authorized client before activating
publication; do not silently use primary or arbitrary discovered calendars.

Next: finish operator enrollment/bootstrap and existing calendar_sync/Telegram
runtime wiring; obtain the concrete Google consent; final CI and exact approved
release/backup; live schedule read, explicit event, deduplication and reminder.
Old deployment windows remain expired. No new deployment is authorized here.
