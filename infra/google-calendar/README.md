# Owner-only Calendar readiness probe

This is a Google Apps Script editor-run diagnostic, not a deployed Calendar proxy
or production Jarvis connection. The owner requested verification of Apps Script
as an alternative to the blocked first-use Google Cloud registration flow.

Files:

* Readiness.gs reads the primary calendar's next seven days and reports only status,
  timezone and count. No titles, IDs or event documents are logged. It performs no
  event mutation, external fetch, trigger creation or deployment.
* appsscript.json explicitly requests calendar.readonly, V8, Europe/Moscow and
  standard exception logging. This scope is read-only for calendars, broader than
  the direct API adapter's event-only read scope; the editor probe also reads
  calendar timezone metadata. It does not grant Gmail/Drive or calendar writes.

## Observed live setup, 24 November 2026

An owner-account Apps Script project was created successfully with GCP Default.
Both files were saved in the editor, the selected function was verified, and Run
reached Google authorization. Google then required a fresh passkey identity check;
the owner was asked to complete that personal authentication in the browser.
The embedded browser's initial passkey attempt reported an incompatible device. At the owner's request,
the same project was opened in their already signed-in normal Chrome window and
renamed to `Jarvis Calendar — Read-only check`. Run again reached Authorization
required / Review permissions. Native authentication dialogs are left to the owner;
no passkey, Google credential or security setting is automated or changed.

The owner then authorized and ran the probe on their phone. The agent independently
observed the execution history: jarvisCalendarReadiness completed at15:40:32 Moscow
time, duration0.69s. A fresh editor view in the other browser ran the same unchanged
function again at15:41:46–47 and returned CALENDAR_READ_OK, Europe/Moscow,
events_changed=false, external_fetch_performed=false, followed by Execution completed.
No new identity/permission prompt appeared on this repeat. Read-only editor access
and reuse of the saved grant are therefore verified. This is not evidence of token
expiry/revocation recovery, unattended operation or a Telegram/server connection.

Do not confuse an accessible dashboard or successful project creation with Calendar
API authorization or a functioning Jarvis connection. Do not copy OAuth flow URLs,
tokens or account identifiers into the repository or test evidence.

## Acceptance before choosing this route

1. Observe completed owner authentication and the exact read-only permission prompt.
   Obtain the concrete owner approval at the permission step; no write grant here.
2. Run this probe successfully, repeat in a fresh editor session and check the
   execution history. A success establishes editor access only, not server access.
3. Assess the smallest supported, authenticated connection to the existing Jarvis
   runtime. Do not expose an anonymous Calendar endpoint or replace the existing
   durable confirmation/idempotency system. No new deployment is authorized by
   running this probe. Do not use browser cookies as runtime credentials.
4. Verify timeouts, bounded retries for reads, revoked authorization, restart,
   stale-data reporting and notification of connection failure. Evaluate Apps Script
   quotas before claiming reliability. An outage must be reported, not represented
   as an empty calendar or silently lost task.
5. Prepare an exact reviewed installation, backup and owner approval before any VPS
   change. Real Telegram readback, explicit event creation without duplication and
   reminders remain separate acceptance steps. Do not promise uninterrupted Google
   service based on a successful one-off probe.

Official references:

* https://developers.google.com/apps-script/guides/cloud-platform-projects
* https://developers.google.com/apps-script/reference/calendar/calendar
* https://developers.google.com/apps-script/manifest
