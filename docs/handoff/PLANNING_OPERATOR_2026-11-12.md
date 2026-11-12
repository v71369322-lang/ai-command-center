# Operator profile preparation checkpoint

Branch `feat/planning-operator-profile-tools` depends on #94. Exact parent
`c904b3d8f038e13467fd4de56518ffd8186438cf` CI was rechecked: both full F1/F2 and
offline VPS workflows SUCCESS. Origin/main still f5ff8b2. Initial tree was clean.

Adds offline reviewed-input/profile conversion with strict decimal strings,
explicit prices/FX/funding references and owner limits. Tariff rates round up;
available money/ceilings round down; calculated maximum must fit the per-plan,
available, daily and monthly envelopes. Existing 100-RUB profile bounds, evidence
TTL, PlanningProfile, F1 permissions, runtime binding and paid consent are not
changed. No default model, tariff, balance or exchange rate is installed.
Output is private, new, unbound and not authority; input/hash provenance and
conversion are inspectable. No credentials, clients, DB, SSH or Docker are used
by the converter. CLI errors/field diagnostics cannot echo input values. The
security-check scope now includes its operator CLI.

Owner confirmed an existing prepaid API balance; the exact amount remains in
private conversation evidence rather than this repository. This is funding
attestation, not an expense or deployment permission. Daily/monthly limits and
reviewed FX/data-sharing parameters were requested and are not assumed.

A fresh, previously authorized read-only VPS check found deployment VERIFIED on
f5ff8b2, no live first-experiment/planning mount in the current broker, and the
historical OpenAI key reference still pointing to an existing private regular
single-link control-user-owned file. Only descriptor metadata was checked;
no key bytes/fingerprint or provider API was read/called. API provisioning need
not be repeated blindly, but provider validity/model access remain unverified.
No VPS binding, credential, daemon, service or journal was changed.

Validation: locked Linux UID 1001 operator/admission/profile/candidate/binding/
release scope 236 passed, including 41 operator cases and an end-to-end handoff
of the generated unbound profile to the existing candidate builder without manual
JSON edits. Ruff and existing Bandit triage passed; no gate/rule was relaxed.
A separate Windows pure arithmetic/validation subset passed 26 and overlaps the
Linux scope; do not add it. Core implementation is commit 4f4644e, later changes
add only the integration test and this verification record.
The local Docker Desktop app had been stopped; its existing user installation
was started hidden without settings changes, then Linux checks ran normally.
Final exact CI will be recorded in the dependent Draft PR; do not infer it from
local counts. Workflow: [OPERATOR_PROFILE.md](../planning/OPERATOR_PROFILE.md).
