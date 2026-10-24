# F2.1 verification evidence

This record separates executed evidence from live deployment gates. The definitive
final-head CI status is linked in [PR #14 checks](https://github.com/v71369322-lang/ai-command-center/pull/14/checks). No earlier F2/F1 run
is substituted for F2.1 validation. Overlapping pytest selections are not added.

## Environment corrections

- HEAD `f324cfc4c168ec85b316b5e5ae5d1a370d227daa` initially referenced coding image
  `9edc157dc7dad943ba87a77a880a5a93905dd987c2ce89d4a80e0f7d3210a68e`, labelled
  `56d5ee5a8f710443739f976417835f6dcac25a2b`. Repeated checkpoints had advanced
  Git without rebuilding the image. Pinning correctly rejected it.
- Rebuilt immutable coding image
  `ab152891fbf372ce393c3c4e5ca13858722b4f8b81e586ac17e026c4ee8cb05f`, labelled
  exactly `f324cfc4c168ec85b316b5e5ae5d1a370d227daa`. No pinning change.
- The next check correctly stopped on `host_disk_low`: workspace had 243 MiB
  free, below the existing 256 MiB guard. Removed 49 untagged images whose labels
  were commits in this repository and 55 individually selected, reclaimable,
  unshared project cache records. Active services, database volumes and unrelated
  workspaces were retained. Free space rose to 5.1 GiB. No threshold reduction.
- The negative verifier test now requires the exact
  `independent_verifier_mismatch` failure and two completed AI fixture calls;
  a disk/image/other failure cannot make it pass accidentally.

## Development fixes

Fixed audit-intent argument collision, GitHub fixture committer timestamp
serialization, missing persistent heartbeat in the longer test fixture, ledger
row tamper detection, frozen request bodies, preservation of unresolved reserves,
blocked dependent writes after ambiguity, read-only GitHub reconciliation and
owner-visible stop reasons. None of these enabled live services or weakened tests.
The final review also closed the approval/scope-installation race: both now commit
in the existing F1 approval transaction, with rollback regression coverage.

## Executed final cloud run

2026-10-24, clean source commit
`f637581a722a8262607e60bb9e74b187a363b2f4`:
`F1_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt scripts/verify_cloud.sh`.
All images were rebuilt for that exact source; coding image:
`sha256:bd17791cb66d61ae908bc5b024cb59af8566d568d0e2c79e9078917f2c7d13bc`.
The source/image pinning and resource gates remained enabled.

| Gate | Status |
|---|---|
| 40 F2.1 readiness tests | **40/40 passed**, included in the full suite; atomic approval rollback and exact verifier refusal checked |
| Full Python suite, including mobile | **183 passed**, zero failures/errors/skips, 203.36 seconds |
| Infrastructure suite | **32 passed**, separate from Python application suite |
| Ruff (`src tests scripts` and `infra/vps`) / OpenAPI snapshot | PASS |
| TypeScript / Vite | PASS |
| All Python dependency audit | 64 dependencies; **0 known advisories** |
| npm audit | **0 known advisories** |
| Bandit | 0 MEDIUM/HIGH; 29 reviewed LOW findings retained |
| Current runtime-value secret scan / whitespace | PASS; not a universal secret detector |
| API / PG / Outbox / Redis / worker / broker container smoke | PASS |
| Encrypted backup → separate networkless PG restore / audit interlock | PASS |
| Restart / persisted result / cancel intent / new task | PASS |
| Worker SIGKILL → watchdog → confirmed absence / no orphan | PASS |
| F2 container smoke / runtime credential-mount boundaries | PASS |
| Full F2.1 HTTP-mock cycle with real coding/verifier sandboxes | PASS, including matching draft PR, two AI fixture calls and usage settlement |
| Mobile Chromium at 390×844 | PASS: create → exact budget approval → repair/test history → mock publication; no live PR link or horizontal overflow |
| Final-head GitHub CI | Must be green on the documentation follow-up commit; PR check records exact head and run |

HTTP tests use `httpx.MockTransport` at the documented OpenAI/GitHub URLs, fake
credentials and explicitly fictional tariffs. No real API calls or new-publisher
PRs. Real isolated coding/verifier containers are used in the full cycle; runtime
mode is explicitly cloud-rootful-test. Browser testing uses Chromium at 390×844,
not a physical iPhone or proof of real MFA/VPN.
The targeted run including the mobile F2.1 scenario passed 41 tests (the same
40 readiness tests plus one mobile test; these are not additional disjoint totals).
The full 183 also includes those tests; it must not be added to 40 or 41. The
infrastructure suite's 32 tests are disjoint. Existing test coverage remains intact.

F2.1 scenarios cover missing credentials, invalid scopes/model/fence/source,
unconfirmed tariffs, task/day/month limits, simultaneous requests, old disputed
costs, provider timeouts before/after response, credential echo, tool/scope/prompt
injection, cancellation/revocation during HTTP, PG loss before/after I/O,
audit/financial-row corruption, independent verifier mismatch, GitHub
403/409/429/500, duplicate publication, lost commit/ref/PR response and read-only
reconciliation after reconstructing the gateway. The full suite also retains F1
lease, isolation, watchdog, cancellation, resource and recovery negatives.

The two new Bandit B110 LOW findings are intentional fail-closed exception paths:
gateway cannot record interruption when PG/audit is unavailable and preserves
pre-I/O intent; runner cannot overwrite reports after cancellation/audit loss and
still stops execution. No swallowed exception grants completion or new authority.

Local evidence under ignored `.runtime/`: `f21-final-verification.log`,
`test-results.xml`, `f21-mobile.png`, `security-summary.json`, `all-pip-audit.json`,
`npm-audit.json`, `bandit.json`, and restore/restart/watchdog/boundary artifacts.
These are local synthetic evidence, not independent offsite operational checkpoints.

Known inherited warnings are retained: Starlette TestClient/httpx deprecation and
GitHub's Node 20 pinned-action runtime migration. Any new warning/failure will
remain visible. Actual provider credentials/prices, remote availability and all
VPS-specific gates are not verified by these tests.
