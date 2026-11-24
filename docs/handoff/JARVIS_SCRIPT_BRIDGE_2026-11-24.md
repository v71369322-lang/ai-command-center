# Signed Apps Script agenda bridge, 24 November 2026

Based on verified PR111 sourcef5b0d17 plus local readiness/checkpoint commits through
2b38fe3. No merge, VPS connection, deployment, paid AI call or Calendar event mutation.

## Implemented

Bridge.gs is a primary-calendar-only read interface. Request and response envelopes
use HMAC-SHA256 with different purpose prefixes, an exact connection identifier,
a random request nonce, time interval and60second freshness check. The key is not
transmitted as a credential/header/query parameter; only signatures are sent.
Intervals are bounded to7days; Google reads at most51events and returns at most50
titles/start/end with truncation indicated. No descriptions, guests, IDs or tokens.
The manifest retains the already authorized calendar.readonly scope.

The script uses ScriptProperties JARVIS_HMAC_KEY (64hex characters representing
32random bytes) and JARVIS_CONNECTION (64hex connection binding). They are not yet
provisioned. Missing/bad configuration, signature, freshness, interval or Google
failure returns only unavailable. CacheService/LockService provide best-effort
duplicate suppression, not durable replay protection; cache entries can be evicted.
The cryptographic response binding/freshness is independent of that cache.

ScriptCalendarHTTP verifies signed replies, binds owner/source/config/key fingerprint,
accepts only the exact script.google.com deployment URL and one ContentService redirect
to https://script.googleusercontent.com/macros/echo. The redirect is GET without
forwarded request body or authentication. No arbitrary URLs or further redirects.
Responses are bounded to64KiB. Short-lived content URLs are redacted from httpx logs.
There is at most one retry of a read after transport/502/503/504 failure, with fresh
nonce and250ms delay; no retry for401/403/429, invalid signatures or schema errors.
A single12second async timeout covers HTTP and retries, with5second HTTP phase
timeouts. Each synchronous agenda call owns a fresh async HTTP client/loop; this
avoids retaining connections tied to a closed event loop. No new process/service.

TelegramService adds mutually exclusive --calendar-script-config / --calendar-config,
sharing the existing explicit --approved-calendar digest. Protected runtime JSON is
ScriptRuntimeConfig(profile=ScriptCalendarProfile, key_file=absolute private path).
Owner/source/approval are checked before reading the32byte private key. The bridge
enters the existing telegram_agenda path, guard/epoch checks and durable owner delivery;
it has no publisher call method and cannot write an event or create task authority.
Without new options, existing runtime behavior is unchanged.

## Validation

32 transport/protocol tests passed locally, including execution of the real Bridge.gs
under a synthetic Node Google adapter, Python/JS HMAC interoperability, wrong binding,
tamper, expiry, replay suppression, query/size/redirect bounds, timeout cancellation,
redaction and bounded retries.49 focused real-PostgreSQL tests passed after the final
transport change, including natural owner query -> signed HTTP -> existing Telegram
delivery, unchanged grants/tasks, replay and no Control lock during HTTP. Google and
Bot HTTP are mocked in these tests. No duplicate test runs are added together.
Ruff, Bandit medium/high and Node syntax checks passed. Full final CI remains pending.

## Google UI preparation (not published)

The already verified owner project now contains Bridge.gs. Its copied-back editor
content matches the tested LF-normalized SHA256:
ae2e2d7fd1a365531fcc6db7e38752fafdcafc325b898b8bc004a32db3081550.
The existing readiness function and read-only manifest were retained.

New deployment form is prepared: Web app, execute as owner, access Anyone,
description `Jarvis read-only agenda v1 / ae2e2d7fd1a3`. Deploy has NOT been pressed.
There is no deployment ID, runtime key or live URL yet. Anonymous HTTP access is
needed for the server without Google browser cookies, but application data access
requires a valid fresh signature. This is a new Internet-facing entry point running
with the owner's calendar read grant. It needs concrete owner approval before key
provisioning/publication. Unauthenticated requests still consume Google execution quota;
do not claim immunity to quota exhaustion, outages or arbitrary availability.

## Remaining gates

1. Exact owner approval for this Google script version/publication and protected
   key provisioning. Do not infer it from the earlier readiness grant or generic
   development instruction. Never expose the shared key in chat, Git, screenshots,
   callback URLs, logs or model context. Provision via a protected operator path.
2. Inspect the resulting version/deployment ID, bind its runtime config, and test
   authenticated read plus unsigned/bad-signature rejection over real Google HTTP.
   The exact deployment ID/protocol is pinned by the client, not provider-side source
   attestation. Before replacing a deployment's target version, reverify exact source
   and get a new approval; a stable deployment ID alone does not prove unchanged code.
3. Finish the existing prepare/inspect/backup/install adapter for this optional
   runtime binding. New CLI arguments alone do not mount the protected files or
   activate the running VPS. Preserve data, Telegram/voice identities and controls.
4. Final head/merge-ref CI, a reviewed exact server candidate and fresh installation
   approval; then real owner Telegram agenda read, restart and failure acceptance.
   Existing deployment windows remain expired. New event publication is not included.

Official behavior references:
https://developers.google.com/apps-script/guides/web
https://developers.google.com/apps-script/guides/content
https://developers.google.com/apps-script/guides/services/quotas
