# F2.2 validation

Preparation and the local full verification have completed. No real AI experiment has occurred.
Public model/pricing/CBR sources were read on 2026-10-24; authenticated model
availability, bank terms, balance, repository ID, credentials and final owner
permission remain unverified. The live gate is blocked.

Offline arithmetic/precondition tests: 16 passed during development. A targeted
run passed **23 tests**: 22 F2.2 cases plus the existing mobile F2.1 test extended
to verify F2.2 preparation and a disabled final-permission button. These counts
overlap the forthcoming full suite and must not be added to its total.

The complete HTTP-mock API → approval → provider → real sandbox repair → verifier
→ fake GitHub draft PR scenario passed. Wrong numeric repository ID blocked the
first model request; a lost model response retained its reserve, stopped in
RECONCILING and denied a repeat. Model output/prices/credentials are fixtures.
The offline seed generator also produced the exact baseline SHA and three files,
with no configured remote.
All mock evidence is classified as a test and cannot supply live preconditions.

No new paid account, repository, App, token or secret was created/connected.

Full clean-source local verification at `870bb111c888471180de550f78457c612d1d43c9`:

* **205 Python tests passed**, including 22 new F2.2 cases; one upstream
  Starlette TestClient/httpx deprecation warning. Targeted counts above overlap.
* **32 infrastructure tests passed separately**.
* Ruff, OpenAPI contract, TypeScript/Vite, secret scan and dependency audits passed:
  64 Python dependencies, zero known advisories; npm zero advisories; Bandit zero
  MEDIUM/HIGH findings and 29 previously reviewed LOW findings.
* Encrypted backup into a different networkless PostgreSQL container, integrity
  verification, API/worker smoke, restart/persistence/cancellation, worker SIGKILL
  watchdog drill, F2 repair/verifier and runtime credential/binding checks passed.
* Chromium mobile viewport 390×844 checked the F2.2 preparation screen, task
  creation, disabled final-consent action and absence of horizontal overflow.

Dry-run evidence `.runtime/f22-dry-run.json`: two fake model HTTP responses,
first proposal 2/4 failing tests, repair 4/4 passing, independent sandbox replay,
fake draft publication; **zero paid calls and zero real publications**. The
39,420,000 nano-RUB fixture settlement is hypothetical, not a real expense.
Screenshots and machine evidence remain ignored local artifacts.

The first GitHub run (40083635209) passed all 205 tests but failed the subsequent
watchdog drill's final-state assertion. Local success does not override this CI
failure. The drill now waits for the broker's verified ACTIVE checkpoint, requires
a confirmed watchdog event for the exact task and actual container absence, and
accepts FAILED or CANCELLED after concurrent stop handlers while checking the
same terminal state survives control-plane resume. Production policy is unchanged.
Failure output includes bounded task-state diagnostics. Final-commit CI is tracked
on [PR #15](https://github.com/v71369322-lang/ai-command-center/pull/15);
the PR must remain draft until that run succeeds.

Live blockers: authenticated model availability; current all-in payment/fee upper
bound and sufficient existing credit; securely connected credentials; separately
authorized synthetic repository/App and numeric ID; runtime evidence; final exact
owner consent. Nine evidence gates expire and are checked again before each call.
The narrow synthetic Python grammar is intentional: arbitrary Python programming,
actual model output quality, provider billing and live publication remain untested.
