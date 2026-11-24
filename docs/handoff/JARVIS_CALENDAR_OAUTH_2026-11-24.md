# Calendar OAuth and encrypted custody, 24 November 2026

Depends on PR108 exact ef5dc1aae48d54593182b937160361d30bd1b8b7;
separate continuation branch, no merge or deployment. See
[preceding preparation](JARVIS_CALENDAR_PREPARATION_2026-11-24.md).

## Implemented

`google_calendar_oauth.py` provides a five-minute in-memory Desktop PKCE attempt,
constant-time state matching, duplicate query rejection, and serialized one-time
callback consumption before token exchange. A matching denial or uncertain
exchange consumes the attempt; no automatic retry of an authorization code.
An unrelated state mismatch does not consume a valid pending attempt.

Token exchange/refresh uses only Google's fixed HTTPS token endpoint, no redirects
or environment proxy, a ten-second timeout and16KiB response limit. Exceptions
exclude request forms and provider bodies. Initial exchange requires both exact
Calendar scopes and a refresh token. Refresh may omit unchanged scopes and refresh
token, as documented by Google; explicitly expanded/reduced scopes are rejected.

AES-256-GCM encrypted archives use fresh nonces, separate Calendar purpose/AAD,
and caller-provided binding to the exact owner/access profile and OAuth client.
There is no reuse of the backup encryption key. Credential objects have redacted
repr. The archive is ciphertext, not a substitute for protected file permissions.

`CalendarTokenProvider` can be injected into PR108's bounded HTTP client. It reloads
encrypted custody, refreshes near expiry, and requires the trusted persistence
callback to atomically commit ciphertext before returning the new token. A failure
disables that provider instance; it cannot silently continue using an expired token
or retry a failed refresh. Single owning process only; no distributed refresh lease.
No additional dependencies, services or data migrations.

## Verification and limits

69 focused tests passed, including callback replay/concurrency/expiry, denial,
revoked/expanded grants, tampered/wrong-owner archives, refresh-token retention,
save failure and encrypted-provider-to-Calendar-client integration. All HTTP is
mocked. Ruff passed; Bandit medium/high passed for the new OAuth module.
Parent PR108 CI run45364141232 was still running when checked; speech passed,
synthetic static checks passed, full synthetic tests pending. Do not claim final CI.

No Google client/grant, calendar, event or credentials were created. No browser
access, VPS access, paid AI or live HTTP call was performed in this continuation.

## Next integration work

1. Implement the actual loopback HTTP listener, protected key/archive file adapter
   and operator setup entry point; these are not provided by the in-memory attempt
   or persistence callbacks. Callback listener must restrict exact path, loopback
   binding, method/query size and omit query/request logging.
2. Add an approved connection factory binding owner/profile/client and source,
   then wire it to existing calendar_sync/CalendarPublisher and read interfaces.
   Neither OAuth consent nor successful token exchange authorizes a local draft.
3. Configure the dedicated Desktop OAuth client, obtain concrete owner consent,
   and create/verify a dedicated Jarvis secondary calendar. Never derive a persistent
   grant from browser login alone. Google Cloud terms/billing require owner action.
4. Check final HEAD and merge-ref CI, prepare a new bounded release/backup and
   exact installation approval. Previous Stage1 windows do not authorize deployment.
5. Live schedule read, explicitly requested event, uncertain-outcome reconciliation,
   reminder and Telegram readback remain pending.

Official protocol reference:
https://developers.google.com/identity/protocols/oauth2/native-app
