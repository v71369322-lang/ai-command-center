# F2.2 validation

Preparation is in progress. No real AI experiment has occurred.
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
with no configured remote. Final full-suite/CI results are pending.
All mock evidence is classified as a test and cannot supply live preconditions.

No new paid account, repository, App, token or secret was created/connected.
