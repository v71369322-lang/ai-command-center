# Calendar preparation, 24 November 2026

Continuation of [live Stage 1](JARVIS_STAGE1_LIVE_2026-11-24.md); dependency
is PR107 / source9351ba6, not main. No deployment or paid API calls in this step.

## Observed state

Owner-authorized browser inspection confirmed a signed-in Google Calendar and
Europe/Moscow primary timezone. No dedicated Jarvis calendar was visible.
No calendars, events, settings, OAuth grants or tokens were created or changed.
A browser login does not establish a persistent server-side connection.

## Local implementation

`google_calendar_access.py` adds a disabled-by-default, exact-profile-bound HTTP
adapter compatible with existing insert/reconciliation contracts. It is not
wired into production, and does not replace owner-confirmed calendar_sync or
CalendarPublisher authorization. Tokens must be injected by a trusted provider;
no token is discovered from a browser or environment.

Requested OAuth scopes are calendar.events.readonly (schedule) and
calendar.app.created (only calendars created by the OAuth app). The legacy
calendar.events contract is unchanged and must not be used for the new connection.
Desktop PKCE preparation accepts only explicit IPv4 loopback callbacks.

Writes are restricted to the exact secondary calendar in the approved profile,
the existing event-insert body without guests, and read-before-retry lookup.
No PATCH/DELETE, arbitrary URLs, redirects, environment proxies or HTTP retries.
Errors omit token headers and provider response bodies; responses are capped
at64KiB. Agenda reads cover at most31days/50events with truncation indicated;
unsolicited top-level event fields are discarded. This is a primary-calendar
read, not yet a complete multi-calendar availability calculation.

## Verification

44 focused tests passed: new adapter, existing Calendar wire contract and legacy
OAuth contract. Ruff passed for the two new Python files. HTTP tests use mocks;
they do not prove real Google OAuth, Calendar permissions, or VPS acceptance.

## Remaining before live connection

1. Configure a dedicated Google OAuth client and protected credential custody.
   Implement callback/state verification, token exchange/refresh and fail-closed
   handling of revoked/expanded scopes. Do not store credentials in Git or logs.
2. Obtain owner approval for the concrete persistent Google grant at consent.
   Create and verify the dedicated Jarvis secondary calendar using that client;
   record the exact calendar/profile binding without exposing account details.
3. Wire the approved client into the existing durable publication worker and
   calendar read interface; retain confirmation, audit and deduplication controls.
4. Run integration tests including uncertain insert/reconciliation, refresh failure,
   revocation and restart. Check final PR head and merge-ref CI.
5. Prepare a new exact release, backup and approval before VPS installation.
   Previous Stage1 installation windows do not authorize this release.
6. Live acceptance: authorized schedule read, one explicitly requested event in
   Jarvis, retry without duplicate, reminder, and Telegram readback. No modification
   of existing primary-calendar events. Google connection is not yet live.

Official permission reference:
https://developers.google.com/workspace/calendar/api/auth
Desktop OAuth/PKCE reference:
https://developers.google.com/identity/protocols/oauth2/native-app
