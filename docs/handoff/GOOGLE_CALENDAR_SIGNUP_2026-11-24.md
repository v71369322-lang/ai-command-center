# Live Calendar enrollment checkpoint, 24 November 2026

Application source remains PR111 exactf5b0d17974b18c35a176cda842834f5e4f3dd040.
This is a documentation checkpoint, not a new application release or deployment.

## Browser observation and owner decision

The existing owner browser is signed in to Google Calendar. Opening the official
Google Cloud Credentials console reaches first-use registration, not a project or
OAuth client list. No existing OAuth client has been verified.

The owner explicitly specified Russia and accepted the Google Cloud Platform terms
in this conversation. On expanding Country, the current registration UI provides
no Russia option (Romania is followed by Rwanda). The country remains blank, the
agreement checkbox remains unchecked, and Agree and continue is disabled.
No alternative country was selected, no terms were submitted, and no account,
project, billing/trial, client, grant, token, event or calendar was created.

Google's official documentation currently states that new account signups for users
in Russia have been paused since10 March2022:
https://docs.cloud.google.com/billing/docs/resources/currency
This matches the observed UI; it does not prove that all pre-existing Google projects
or ordinary Google Calendar accounts are unavailable.

## Actual blocker and allowed continuation

Live OAuth bootstrap through this first-use Google Cloud account cannot currently
proceed with the country supplied by the owner. Do not substitute a VPN location,
calendar country, another country or another person's account. No country changes,
identity changes, billing activation or support message are authorized implicitly.

An existing legitimate accessible Google Cloud project/OAuth client, or resolution
through Google's supported account process, can unblock setup. Access and client
configuration must be verified before claiming it is reusable; a client from another
project/person is not automatically an authorization to use it. New persistent
access still needs the concrete owner consent at the actual Google permission step.

The application-side Calendar runtime is implemented but not activated. Protected
Windows-to-Linux enrollment/bootstrap, dedicated-calendar verification, final CI,
an exact approved release and live Telegram acceptance remain pending. No custom
browser automation is used as an OAuth/API substitute. No VPS or paid AI calls.

## CI reconciliation

PR110 exactf38069f / run45366956138 completed SUCCESS. Its merge-ref remains
7433c36579543d8eab47a1bddfdd0177ae2aa1f4; the preceding equal-tree check applies.
PR111 exactf5b0d17 / run45369287193 was still running at last check.
Merge-refdafaaff3f1b8367d58fcfd3ad08c4aa7690d2077 is unchanged from the equal-tree
check (treeaa08efdbcba8fe5a56c07139611d43fe9ff4f8a0).
Do not label the current application release CI or live Google acceptance complete.
