# F2.1 verification evidence

This record separates executed evidence from pending final gates. The definitive
final-head CI status will be linked in the development PR. No earlier F2/F1 run
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

## Final run status

Pending execution summary after current clean-source checks:

| Gate | Status |
|---|---|
| 40 F2.1 readiness tests | 40 passed after environment correction; full suite will recheck the final atomic-approval fix |
| Full Python suite, including mobile | Pending |
| 32 infrastructure tests | Pending |
| Ruff / OpenAPI | Passed on checkpoint |
| TypeScript/Vite | Passed during development; final run pending |
| Security/dependency audits | Pending F2.1 final run |
| Container API/worker, restore/restart/watchdog | Pending F2.1 final run |
| Final-head GitHub CI | Pending PR |

HTTP tests use `httpx.MockTransport` at the documented OpenAI/GitHub URLs, fake
credentials and explicitly fictional tariffs. No real API calls or new-publisher
PRs. Real isolated coding/verifier containers are used in the full cycle; runtime
mode is explicitly cloud-rootful-test. Browser testing uses Chromium at 390×844,
not a physical iPhone or proof of real MFA/VPN.
The targeted run including the mobile F2.1 scenario passed 41 tests (the same
40 readiness tests plus one mobile test; these are not additional disjoint totals).

Known inherited warnings are retained: Starlette TestClient/httpx deprecation and
GitHub's Node 20 pinned-action runtime migration. Any new warning/failure will
remain visible. Actual provider credentials/prices, remote availability and all
VPS-specific gates are not verified by these tests.
