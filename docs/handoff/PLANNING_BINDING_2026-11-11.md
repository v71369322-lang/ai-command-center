# Planning deployment binding / production factory checkpoint

Parent exact CI checked before implementation: #91
`db4337beb00aa3df5882819ffed2dff6582b0aee` and #92
`64c00d2c1b8c65a9365d17abd7a6b2de43a4c874`: both offline VPS preparation
and full F1/F2 synthetic workflows SUCCESS. Current origin/main still f5ff8b2.

Branch `feat/planning-deployment-binding` depends on #92. Implements the optional
`planning` manifest binding and existing deployment prepare/preflight/postcheck
composition, plus strict `configured_host()` in the production broker factory.
Default output remains disabled. Exact environment/mount/network scope is enforced;
no enabled flag or new public RPC/authority mechanism is introduced.

The factory now distinguishes the execution rootless daemon from the control
daemon containing the broker. Host declarations require a separate control
attestation endpoint in installed composition; actual self-container/image
inspection is performed there, retaining the execution backend for jobs. Metadata
pins now include tmpfs and actual attached network names. New source therefore
requires new declarations/profile pins.

Only broker receives key directory, planning egress and the control socket;
Telegram receives only the metadata directory. Private directories must be
outside both source and shared state roots, disjoint and exact-inventory. Raw
and semantic profile/host pins, source/image/socket/ledger identity, evidence
freshness, custody and key metadata are checked. Key bytes are never read by
prepare/preflight/startup/postcheck. Installed profile/host/directory guards and
existing observed consent, F1/fencing/source/context and financial guards remain.
Runtime postcheck measures mounts (including aliases/ancestor leaks), environment
and networks of every service, Telegram's actual profile and broker attestation.
Independent backup/status/restore inspection does not depend on planning expiry.

Important capability boundary: the additional read-only control socket bind is
**not a read-only Docker API**. It grants the trusted broker administrative access
to the control user's rootless daemon. This exact addition must be included in
separate deployment/access authorization; no live access was widened here.

Local locked checks completed before checkpoint: binding/release offline 104
passed; factory/host Linux/PG 58 passed. These suites are disjoint. An earlier
Offline binding/release also passed under UID 1001; fixtures use the current
operator UID instead of assuming UID 1000, retaining the actual ownership gate.
broader PG/control run passed 399 (overlaps factory/host, do not add). Ruff and
API contract passed. Full clean-source infra/deployment regression and exact
final CI are recorded with the resulting Draft PR; pending is not SUCCESS.
Invalid operator JSON returns a stable error code without echoing input values;
two negative tests retain this property. All Docker metadata, provider credentials
and HTTP in these tests are synthetic.
No rootless/systemd/VPS acceptance or real provider call is claimed.

Operator workflow and security properties:
[DEPLOYMENT_BINDING.md](../planning/DEPLOYMENT_BINDING.md).
The offline review plan now records planning pins and removes the missing-code
blockers; it remains BLOCKED_NOT_ACTIVATABLE until built/inspected exact images,
fresh operator evidence/private bindings, live rootless acceptance and separate
exact deployment/access authorization. No deployment, merge, real credential
connection, paid call or VPS write occurred. Production state is inherited from
the earlier verified checkpoint; this turn did not perform a fresh VPS probe.
