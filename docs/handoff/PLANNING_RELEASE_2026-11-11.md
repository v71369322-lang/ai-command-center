# Local checkpoint: protected offline release review

Scope: offline packaging and a verifiable activation plan; no deployment,
provider connection, paid call, merge or production changes.

Parent Draft #91 initially failed synthetic CI because Bandit B608 rejected
concatenated SQL in the read-only ledger verifier. Fixed in parent commit
`db4337beb00aa3df5882819ffed2dff6582b0aee` using two literal queries. Locked
Ruff and existing Bandit triage passed; targeted compatibility/concurrency scope
24 passed. No security-gate waiver. Parent offline CI passed; synthetic result
must be checked at that exact SHA before treating the chain as green.

Child branch `feat/planning-release-package` depends on #91. Adds
`planning_release.py` and `infra/vps/prepare_planning_release.py` with prepare /
read-only verify, exclusive private package creation, last-written completion
seal and independent digest pin. Both existing bundle validators run before
accepting transition pins; schema/state/users/owner scope cannot silently change.
Current deployment validation explicitly rejects `F1_PLANNING_*` injections
across all services. Production factory is unchanged and planning remains closed.

The artifact is **BLOCKED_NOT_ACTIVATABLE**, not a live deployment candidate.
The plan records exact supplied revisions/images/schema, required live checks,
postchecks and concrete blockers. Recomputing the package seal cannot authorize
activation or spending. No real candidate was fabricated from absent images or
operator evidence. No private profile, tariff, funding, key fingerprint or live
host declaration was invented. No credential file is read/copied by the tool.

Locked Linux package scope: 29 passed. Covers byte tampering, external pin,
custody, symlink/hardlink, incomplete creation, scope drift, modified/resealed
authorization and planning environment injection in all seven services. These
tests use fixture images/TG IDs and offline Compose normalization, not host/VPS
acceptance. Broader regression and exact final CI are recorded in the completion
report; do not infer them from this checkpoint.

Operator workflow and remaining activation gates:
[RELEASE_PACKAGE.md](../planning/RELEASE_PACKAGE.md). Next implementation needs
a reviewed least-privilege deployment binding and broker factory composition;
fresh operator evidence is required before a real activatable package. Use only
existing deployment/reconciliation interlocks and separate exact authorization.
Production remains the previously verified f5ff8b2 release; this turn did not
probe or modify VPS, so this is inherited evidence, not a fresh server claim.
